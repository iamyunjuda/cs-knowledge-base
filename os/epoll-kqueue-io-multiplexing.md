# epoll, kqueue, io_uring — I/O 멀티플렉싱의 진화와 트레이드오프

## 핵심 정리

서버가 동시에 수만 개의 클라이언트 연결을 처리하려면, 각 연결마다 스레드를 만드는 것은 불가능하다. **I/O 멀티플렉싱**은 소수의 스레드로 수만 개의 I/O를 동시에 감시하는 OS 커널 기능이다.

```
[문제 상황]
클라이언트 10,000개 동시 접속

방법 1: Thread-per-Connection
  → 10,000개 스레드 생성 → 메모리 10GB (1MB × 10K) → 💀 OOM

방법 2: I/O 멀티플렉싱
  → 1개 스레드가 10,000개 소켓을 감시 → 데이터 온 소켓만 처리
  → 이것이 Nginx, Redis, Node.js, Netty가 쓰는 방법
```

**I/O 멀티플렉싱 API 진화:**

```
select (1983)  →  poll (1986)  →  epoll (Linux, 2002)
                                   kqueue (BSD/macOS, 2000)
                                   IOCP (Windows, 1994)
                                   io_uring (Linux, 2019)
```

## 헷갈렸던 포인트

---

### Q1: select/poll은 왜 느린가? — 역사적 배경

#### select — 최초의 I/O 멀티플렉싱 (1983)

```c
// select 사용 방식
fd_set read_fds;
FD_ZERO(&read_fds);
FD_SET(socket1, &read_fds);
FD_SET(socket2, &read_fds);
// ...10,000개 소켓 등록

// "이 중에 읽을 데이터가 있는 소켓이 있나?" 물어봄
int ready = select(max_fd + 1, &read_fds, NULL, NULL, &timeout);

// 어떤 소켓인지 모르니까 전부 검사해야 함!
for (int fd = 0; fd <= max_fd; fd++) {
    if (FD_ISSET(fd, &read_fds)) {
        // 이 소켓에 데이터 있음 → 처리
    }
}
```

**select의 문제:**

```
1. fd 제한: 최대 1024개 (FD_SETSIZE)
2. 매번 전체 복사: fd_set을 매 호출마다 유저→커널 복사
3. O(n) 스캔: 리턴 후 어떤 fd가 준비됐는지 전부 순회해야 함

10,000개 소켓 감시 시:
  매 호출마다: 10,000개 fd 복사 + 커널에서 10,000개 스캔 + 리턴 후 10,000개 검사
  → 실제 데이터 온 건 5개뿐인데 10,000개를 3번 훑는다
```

#### poll — select의 개선 (1986)

```c
struct pollfd fds[10000];
fds[0].fd = socket1;
fds[0].events = POLLIN;
// ...

int ready = poll(fds, 10000, timeout);

// 여전히 전부 순회해야 함!
for (int i = 0; i < 10000; i++) {
    if (fds[i].revents & POLLIN) {
        // 처리
    }
}
```

**poll이 select보다 나은 점:** fd 수 제한 없음 (1024 한계 제거)
**여전히 느린 이유:** 매번 전체 배열 복사 + O(n) 순회는 동일

---

### Q2: epoll은 무엇이 다른가? — Linux의 해결책

**핵심: "관심 있는 fd를 커널에 미리 등록해두고, 이벤트가 발생한 fd만 알려준다"**

```c
// 1. epoll 인스턴스 생성
int epfd = epoll_create1(0);

// 2. 관심 있는 소켓을 커널에 등록 (한 번만!)
struct epoll_event ev;
ev.events = EPOLLIN;
ev.data.fd = socket1;
epoll_ctl(epfd, EPOLL_CTL_ADD, socket1, &ev);  // 커널에 등록

// 3. 이벤트 대기 — 준비된 fd만 돌려받는다!
struct epoll_event events[100];
int nready = epoll_wait(epfd, events, 100, timeout);

// 4. 준비된 것만 처리 (O(ready) — 전체가 아님!)
for (int i = 0; i < nready; i++) {
    int fd = events[i].data.fd;
    // 이 fd에 데이터 있음 → 처리
}
```

**select/poll vs epoll 비교:**

```
[select/poll]
매 호출마다:
  유저 → 커널: "이 10,000개 fd 중에 준비된 거 있어?" (전체 복사)
  커널: 10,000개 전부 확인 → "있다"
  커널 → 유저: 결과 반환 (전체 복사)
  유저: 10,000개 순회하며 준비된 fd 찾기

[epoll]
초기 등록:
  유저 → 커널: "이 소켓 감시해줘" (epoll_ctl, 한 번만)

매 호출마다:
  유저 → 커널: "뭐 준비됐어?" (epoll_wait)
  커널: 준비된 5개만 반환 (복사 최소!)
  유저: 5개만 처리 (O(5), O(n) 아님!)
```

**성능 차이 (10,000개 소켓, 5개만 활성):**

```
select: O(10,000)  — 매번 전체 스캔
poll:   O(10,000)  — 매번 전체 스캔
epoll:  O(5)       — 활성 소켓만!

소켓 100,000개일 때:
  select: 사용 불가 (1024 한계)
  poll:   O(100,000) — 매 호출마다 — CPU 99%
  epoll:  O(활성 수) — 10개 활성이면 O(10)
```

#### epoll의 두 가지 모드: Level Triggered vs Edge Triggered

```
[Level Triggered (LT) — 기본 모드]
  "소켓 버퍼에 데이터가 남아있는 한 계속 알려줌"

  데이터 100바이트 도착 → epoll_wait 리턴
  50바이트만 읽음 (50바이트 남음) → 다음 epoll_wait에서 또 리턴!
  → 안전하지만 epoll_wait 호출이 잦아질 수 있음

[Edge Triggered (ET) — 고성능 모드]
  "상태가 변할 때만 알려줌 (새 데이터가 올 때만)"

  데이터 100바이트 도착 → epoll_wait 리턴
  50바이트만 읽음 (50바이트 남음) → 다음 epoll_wait에서 안 알려줌!
  → 반드시 한 번에 다 읽어야 한다 (EAGAIN까지 읽기)
  → 더 효율적이지만 실수하면 데이터 유실

Nginx는 ET 모드 사용 (최고 성능)
Redis는 LT 모드 사용 (안전성 우선)
```

---

### Q3: kqueue는 뭔가? — BSD/macOS의 해결책

kqueue는 **FreeBSD(2000)**에서 만들어진 I/O 이벤트 알림 시스템이다. macOS가 FreeBSD 기반이라 **macOS에서도 kqueue를 사용**한다.

```c
// 1. kqueue 인스턴스 생성
int kq = kqueue();

// 2. 이벤트 등록 (changelist)
struct kevent change;
EV_SET(&change, socket_fd, EVFILT_READ, EV_ADD, 0, 0, NULL);

// 3. 이벤트 대기 + 등록을 한 번에!
struct kevent events[100];
int nready = kevent(kq, &change, 1, events, 100, &timeout);
//                   ^등록 목록^    ^결과 목록^
//                   등록과 대기를 하나의 시스템 콜로!

// 4. 준비된 것만 처리
for (int i = 0; i < nready; i++) {
    int fd = events[i].ident;
    // 처리
}
```

**kqueue가 epoll보다 나은 점:**

```
1. 등록 + 대기를 하나의 시스템 콜로:
   epoll: epoll_ctl(등록) + epoll_wait(대기) = 2번 시스템 콜
   kqueue: kevent(등록 + 대기) = 1번 시스템 콜

2. 다양한 이벤트 타입:
   epoll: 파일 디스크립터(소켓, 파이프) 이벤트만
   kqueue: 소켓 + 파일 변경 + 프로세스 종료 + 시그널 + 타이머
           → macOS의 FSEvents도 내부적으로 kqueue 활용

3. 더 깔끔한 API:
   epoll: EPOLLIN, EPOLLOUT, EPOLLET 등 비트 플래그 조합
   kqueue: 필터(EVFILT_READ, EVFILT_WRITE, EVFILT_PROC...) 방식
```

**epoll vs kqueue 비교:**

| 구분 | epoll (Linux) | kqueue (BSD/macOS) |
|------|--------------|-------------------|
| **OS** | Linux 전용 | FreeBSD, macOS, OpenBSD |
| **API** | epoll_create + epoll_ctl + epoll_wait | kqueue + kevent |
| **이벤트 등록** | 별도 시스템 콜 | 대기와 동시에 가능 |
| **이벤트 종류** | fd 이벤트만 | fd + 파일 + 프로세스 + 시그널 + 타이머 |
| **Edge Trigger** | EPOLLET 플래그 | EV_CLEAR 플래그 |
| **성능** | 매우 좋음 | 매우 좋음 (약간 더 유연) |

---

### Q4: io_uring은 왜 나왔나? — Linux의 차세대 I/O (2019)

epoll도 훌륭하지만 **시스템 콜 자체의 비용**이 문제가 된다.

```
[epoll의 한계]

epoll_wait() 호출 시:
  유저 모드 → 커널 모드 전환 (~수백 ns)
  커널에서 이벤트 확인
  커널 모드 → 유저 모드 전환 (~수백 ns)

초당 수십만 번 호출하면 → 이 전환 비용이 누적된다!
```

**io_uring의 핵심: 시스템 콜 없이 커널과 통신**

```
[io_uring 구조]

유저 공간                         커널 공간
┌──────────────┐               ┌──────────────┐
│ Submission   │  ─── 공유 ──→ │              │
│ Queue (SQ)   │   메모리 링   │   커널이     │
├──────────────┤   버퍼        │   처리하고   │
│ Completion   │  ←── 공유 ──  │   결과 넣음  │
│ Queue (CQ)   │   메모리 링   │              │
└──────────────┘               └──────────────┘

1. 유저: SQ에 요청 넣기 (시스템 콜 없이 메모리 쓰기만!)
2. 커널: SQ에서 요청 꺼내서 처리
3. 커널: CQ에 결과 넣기
4. 유저: CQ에서 결과 꺼내기 (시스템 콜 없이 메모리 읽기만!)
```

**epoll vs io_uring:**

```
epoll:
  이벤트 감지 → epoll_wait (시스템 콜)
  데이터 읽기 → read (시스템 콜)
  데이터 쓰기 → write (시스템 콜)
  → 최소 3번의 시스템 콜

io_uring:
  요청 제출 + 결과 수신 = 공유 메모리로 처리
  → 시스템 콜 0~1번 (io_uring_enter, 생략 가능)
```

**io_uring 성능:**

```
[파일 I/O 벤치마크 — 랜덤 읽기 IOPS]

epoll + read():     ~200K IOPS
io_uring:           ~500K IOPS (+150%)

[네트워크 I/O — HTTP 요청 처리]

epoll 기반 서버:    ~300K req/s
io_uring 기반 서버: ~450K req/s (+50%)
```

---

### Q5: 각 기술/도구가 어떤 I/O 모델을 쓰는가?

| 기술/도구 | Linux | macOS | 왜 이 선택? |
|-----------|-------|-------|-----------|
| **Nginx** | epoll (ET) | kqueue | 최고 성능, Edge Trigger로 이벤트 최소화 |
| **Redis** | epoll (LT) | kqueue | 안전한 LT 모드, 싱글 스레드이므로 충분 |
| **Node.js** | epoll | kqueue | libuv 라이브러리가 OS별 자동 선택 |
| **Netty** | epoll | kqueue | Java NIO 또는 네이티브 epoll/kqueue |
| **Go runtime** | epoll | kqueue | netpoller가 OS별 자동 선택 |
| **Tokio (Rust)** | epoll / io_uring | kqueue | mio 라이브러리 사용 |
| **Spring WebFlux** | epoll (via Netty) | kqueue (via Netty) | Netty가 처리 |

**크로스 플랫폼 추상화 라이브러리:**

```
[libuv] — Node.js의 이벤트 루프
  Linux: epoll
  macOS: kqueue
  Windows: IOCP
  → 개발자가 OS를 몰라도 됨

[libevent / libev]
  동일하게 OS별 최적 API를 자동 선택

[mio] — Rust Tokio의 기반
  Linux: epoll (io_uring 지원 진행 중)
  macOS: kqueue
  Windows: IOCP

[Java NIO Selector]
  Linux: epoll
  macOS: kqueue
  Windows: select (→ 성능 약간 떨어짐)
```

---

### Q6: 트레이드오프 정리

```
[선택 기준 플로우차트]

어떤 OS에서 돌아가나?
├── Linux만 → epoll (안정적) 또는 io_uring (최신, 고성능)
├── macOS만 → kqueue
├── Windows만 → IOCP
└── 크로스 플랫폼 → libuv, libevent, 또는 프레임워크에 맡기기

성능 요구사항은?
├── 일반 웹 서비스 → epoll/kqueue로 충분 (Nginx, Redis가 이걸로 동작)
├── 초고성능 I/O → io_uring 검토
└── 파일 I/O 집중 → io_uring이 압도적 (epoll은 네트워크에 강함)
```

| 방식 | 장점 | 단점 | 적합한 상황 |
|------|------|------|-----------|
| **select** | 이식성 최고, 모든 OS 지원 | O(n), 1024 fd 한계 | 소규모, 레거시 호환 |
| **poll** | fd 수 제한 없음 | O(n), 매번 전체 복사 | select 한계 초과 시 |
| **epoll** | O(1) 이벤트 감지, 검증됨 | Linux 전용, fd만 감시 | 대부분의 Linux 서버 |
| **kqueue** | 다양한 이벤트, 깔끔한 API | BSD/macOS 전용 | macOS/FreeBSD 서버 |
| **io_uring** | 시스템 콜 최소, 최고 성능 | Linux 5.1+, 아직 성숙 중 | 극한 성능, 파일 I/O |
| **IOCP** | Windows 최적 | Windows 전용 | Windows 서버 |

---

### Q7: 면접에서 "epoll이 뭐예요?" 라고 물으면

```
1단계 (기본): "I/O 멀티플렉싱 API입니다. 하나의 스레드가 수만 개의
              소켓을 효율적으로 감시할 수 있습니다"

2단계 (비교): "select/poll은 매번 전체 fd를 순회하지만 O(n),
              epoll은 이벤트가 발생한 fd만 반환합니다 O(활성 수)"

3단계 (동작 원리): "커널에 fd를 미리 등록(epoll_ctl)해두고,
                   epoll_wait로 준비된 이벤트만 받습니다.
                   Level Triggered와 Edge Triggered 두 모드가 있습니다"

4단계 (실무 연결): "Nginx, Redis, Netty가 내부적으로 epoll을 사용하고,
                   macOS에서는 같은 역할을 kqueue가 합니다.
                   최신 Linux에서는 io_uring이 더 나은 성능을 제공합니다"
```

## 참고 자료

- [The C10K Problem — Dan Kegel](http://www.kegel.com/c10k.html)
- [Linux epoll man page](https://man7.org/linux/man-pages/man7/epoll.7.html)
- [FreeBSD kqueue man page](https://www.freebsd.org/cgi/man.cgi?query=kqueue)
- [io_uring — Efficient I/O with io_uring (kernel.dk)](https://kernel.dk/io_uring.pdf)
- [libuv Design Overview](https://docs.libuv.org/en/v1.x/design.html)
