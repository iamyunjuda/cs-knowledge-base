# 코루틴과 비동기의 모든 것 Part 1 — 커널 레벨에서 이해하는 비동기의 본질

## 핵심 정리

비동기를 제대로 이해하려면 **"왜 비동기가 필요한가"** 부터 커널 레벨에서 시작해야 한다. 코루틴, CompletableFuture, Virtual Thread 모두 결국 **OS 커널의 I/O 처리 방식** 위에서 동작한다. 이 문서는 그 바닥부터 파고든다.

```
비동기의 존재 이유 (한 줄 요약):
  "CPU는 나노초 단위로 일하는데, I/O(디스크/네트워크)는 밀리초 단위다.
   그 수백만 배 차이를 놀리지 않으려고 비동기가 존재한다."

시간 스케일 비교:
  CPU 레지스터 접근  : ~0.3ns
  L1 Cache          : ~1ns
  L3 Cache          : ~10ns
  RAM               : ~100ns
  NVMe SSD          : ~25,000ns (25μs)
  네트워크 (같은 DC)  : ~500,000ns (0.5ms)
  네트워크 (서울→미국) : ~150,000,000ns (150ms)

→ CPU가 RAM 한 번 읽는 동안 100ns, 네트워크 응답 기다리면 150ms.
  CPU 입장에선 1초 vs 17일 기다리는 것과 같다.
```

---

## 헷갈렸던 포인트

---

### Q1: 프로세스가 I/O를 요청하면 커널에서 정확히 무슨 일이 벌어지나?

**System Call → 커널 모드 전환 → I/O 요청 → 완료 대기 or 즉시 반환**

```
[유저 프로세스]                    [커널]                      [하드웨어]
     │                              │                            │
     │  read(fd, buf, size)         │                            │
     │  ─── syscall ───────────────>│                            │
     │  (유저→커널 모드 전환)         │                            │
     │                              │  DMA 요청 전송              │
     │                              │  ─────────────────────────>│
     │                              │                            │
     │    [Blocking I/O]            │                            │
     │    프로세스 SLEEP 상태        │     디스크/NIC 작업 중      │
     │    (스케줄러가 다른 프로세스    │                            │
     │     실행하도록 전환)           │                            │
     │                              │  ◀── 인터럽트 (완료!) ─────│
     │                              │  데이터를 커널 버퍼→유저 버퍼│
     │  ◀── return ────────────────│                            │
     │  (커널→유저 모드 복귀)         │                            │
     ▼                              ▼                            ▼
```

**핵심**: Blocking I/O에서 `read()` 호출하면 **프로세스가 SLEEP 상태**로 바뀐다. 이 동안 해당 스레드는 아무것도 못 한다. 스레드 1개가 점유당한다.

---

### Q2: Non-blocking I/O는 커널에서 뭐가 다른가?

```
[Blocking I/O]
  read(fd) → 데이터 올 때까지 프로세스 SLEEP → 데이터 도착 → return

[Non-blocking I/O]  (O_NONBLOCK 플래그)
  read(fd) → 데이터 없으면 즉시 return -1 (EAGAIN) → 개발자가 다시 시도
  read(fd) → 아직 없음 → EAGAIN
  read(fd) → 데이터 있음! → return 데이터

[I/O Multiplexing]  (epoll/kqueue)
  epoll_wait(fds[]) → "이 1만개 fd 중 준비된 거 알려줘"
                    → 커널이 준비된 fd 목록만 반환
                    → 그 fd만 read() (이건 즉시 반환됨)
```

**Non-blocking 자체는 쓸모없다** — busy-waiting(계속 확인)이 되니까. 진짜 핵심은 **I/O Multiplexing(epoll/kqueue/io_uring)** 이다.

---

### Q3: epoll이 코루틴/비동기 런타임의 심장인 이유

**모든 고성능 비동기 런타임은 결국 epoll (Linux) / kqueue (macOS) 위에서 동작한다.**

```
[epoll 기반 비동기 런타임의 동작 원리]

   Nginx, Node.js, Netty, tokio, Go runtime, Kotlin Dispatcher.IO
   전부 이 구조 위에 있다:

   1. epoll_create()  → epoll 인스턴스 생성
   2. epoll_ctl(ADD, fd) → 감시할 소켓/파일 등록
   3. epoll_wait()     → 이벤트 발생할 때까지 블로킹 (여기서만!)
   4. 이벤트 발생      → 해당 fd에 대한 콜백/코루틴 실행
   5. 다시 3번으로

   이게 "Event Loop"의 정체다.
```

```c
// epoll의 실제 사용 (C 코드 — 모든 비동기 런타임의 근간)
int epfd = epoll_create1(0);

struct epoll_event ev;
ev.events = EPOLLIN | EPOLLET;  // Edge Triggered
ev.data.fd = client_socket;
epoll_ctl(epfd, EPOLL_CTL_ADD, client_socket, &ev);

struct epoll_event events[MAX_EVENTS];
while (1) {
    // ★ 여기서만 블로킹! — 이벤트 올 때까지 스레드 하나만 대기
    int nfds = epoll_wait(epfd, events, MAX_EVENTS, -1);

    for (int i = 0; i < nfds; i++) {
        if (events[i].events & EPOLLIN) {
            // 데이터 준비된 fd만 처리 — non-blocking read
            handle_read(events[i].data.fd);
        }
    }
}
```

**이 구조가 왜 강력한가:**
- 스레드 1개로 **수만 개 동시 연결** 처리 가능
- `epoll_wait()`에서만 블로킹 → CPU 낭비 없음
- 커널이 "준비된 것만" 알려주니까 O(준비된 수)만큼만 작업

---

### Q4: 스레드 컨텍스트 스위칭이 비싼 이유 — 커널이 실제로 하는 일

```
[Thread A → Thread B 컨텍스트 스위칭 과정]

1. Thread A의 상태 저장
   - CPU 레지스터 전체 (범용 레지스터 16개 + SIMD 레지스터 등)
   - Program Counter (다음 실행할 명령어 주소)
   - Stack Pointer
   - FPU/SSE/AVX 레지스터 상태
   → 커널의 task_struct에 저장

2. TLB (Translation Lookaside Buffer) 플러시
   - 가상 주소 → 물리 주소 캐시가 무효화됨
   - 같은 프로세스 내 스레드면 안 플러시 (주소 공간 공유)
   - 다른 프로세스면 TLB 전체 플러시 → 매우 비쌈

3. Thread B의 상태 복원
   - 저장했던 레지스터 전부 복원
   - 스택 포인터 교체
   - 새 명령어 주소부터 실행 재개

4. 캐시 미스 폭발 (진짜 비싼 부분)
   - L1/L2/L3 캐시에 Thread A의 데이터가 있었음
   - Thread B의 데이터는 캐시에 없음 → Cold Start
   - 캐시가 "따뜻해지기"까지 수천 사이클 소요

비용 정리:
  직접 비용 (레지스터 저장/복원): ~1-2μs
  간접 비용 (캐시 미스):         ~5-30μs (상황에 따라 더)
  → 1만 개 스레드가 경쟁하면 컨텍스트 스위칭만으로 CPU 시간 상당 부분 소모
```

**이게 왜 코루틴과 관련 있나?**
- 코루틴은 **유저 스페이스에서 전환**한다 → syscall 없음, TLB 플러시 없음
- 코루틴 전환 비용: ~100ns vs 스레드 전환: ~5-30μs → **50~300배 차이**

---

### Q5: 코루틴의 "유저 스페이스 스위칭"이란 정확히 뭔가?

```
[OS 스레드 스위칭]
  커널 개입 → syscall → 레지스터 저장/복원 → TLB 관리 → 스케줄러 실행

[코루틴 스위칭]
  유저 스페이스에서 함수 호출 수준으로 전환
  → "현재 실행 지점(Continuation) 저장" + "다른 코루틴의 실행 지점 복원"
  → 커널은 이 전환을 모른다. 그냥 같은 스레드에서 다른 함수 호출한 것처럼 보임.

구체적으로:
  suspend fun fetchUser(): User {
      val response = httpClient.get("/users/1")  // ← 여기서 중단(suspend)
      return response.body()                      // ← 응답 오면 여기서 재개(resume)
  }

  "중단" = 현재 로컬 변수 + 실행 지점을 Continuation 객체에 저장하고, 스레드 반환
  "재개" = Continuation에서 상태 복원하고, (아무) 스레드에서 이어서 실행

  ★ 스레드는 반환되었으므로 다른 코루틴 실행 가능!
```

```
[1개 OS 스레드 위에서 코루틴 N개 실행]

Thread-1 시간축:
  ──[코루틴A 실행]──[A suspend]──[코루틴B 실행]──[B suspend]──[코루틴C]──[A resume]──
                        │                           │
                        ▼                           ▼
                  I/O 요청 보냄              I/O 요청 보냄
                  (epoll에 등록)             (epoll에 등록)

  → OS 입장에선 Thread-1이 쭉 바쁘게 일하는 것처럼 보임
  → 실제로는 코루틴 A, B, C가 번갈아 실행 중
  → 컨텍스트 스위칭 비용 거의 없음 (같은 스레드 안에서 함수 호출 수준)
```

---

### Q6: 커널 스레드 모델과 코루틴의 관계 — M:N 스케줄링

```
[스레드 모델 비교]

1:1 모델 (Java 전통, pthread)
  유저 스레드 1개 = OS 스레드 1개
  → 10,000 유저 스레드 = 10,000 OS 스레드 → 메모리/스위칭 비용 폭발

  유저:  [T1] [T2] [T3] ... [T10000]
          │    │    │          │
  커널:  [T1] [T2] [T3] ... [T10000]

M:N 모델 (Go goroutine, Kotlin Coroutine, Java Virtual Thread)
  유저 스레드(코루틴) M개를 OS 스레드 N개 위에서 실행 (M >> N)
  → 100,000 코루틴을 8개 OS 스레드에서 실행 가능

  유저:  [C1] [C2] [C3] [C4] [C5] ... [C100000]
          │    │    │    │    │
          ▼    ▼    ▼    ▼    ▼
  커널:  [Thread-1] [Thread-2] ... [Thread-8]
         (Dispatcher가 코루틴을 스레드에 분배)

N:1 모델 (초기 Green Thread)
  모든 코루틴이 OS 스레드 1개에서 실행
  → 멀티코어 활용 불가, CPU-bound 작업에 부적합
```

**Go의 GMP 모델 — M:N의 대표적 구현:**

```
G = Goroutine (유저 레벨 경량 스레드)
M = Machine  (OS 스레드)
P = Processor (논리 프로세서, GOMAXPROCS 개)

  [G1][G2][G3]──→[P1]──→[M1 (OS Thread)]──→ CPU Core 1
  [G4][G5]──────→[P2]──→[M2 (OS Thread)]──→ CPU Core 2
  [G6]──────────→[P3]──→[M3 (OS Thread)]──→ CPU Core 3

  G가 I/O로 블로킹되면:
    → P가 그 G를 빼고, 큐에서 다른 G를 가져와서 실행
    → M(OS 스레드)은 절대 놀지 않음

  Work Stealing:
    P1의 큐가 비면 → P2의 큐에서 G를 훔쳐옴 → 부하 균등 분배
```

**Kotlin Coroutine도 비슷한 구조:**

```
Dispatchers.Default = CPU 코어 수만큼 스레드 풀
Dispatchers.IO     = 최대 64개 (또는 코어 수 중 큰 값) 스레드 풀

  [coroutine1][coroutine2]...──→ Dispatchers.Default ──→ [4개 OS 스레드]
  [coroutine3][coroutine4]...──→ Dispatchers.IO      ──→ [64개 OS 스레드]
```

---

### Q7: io_uring — 리눅스 최신 비동기 I/O의 게임 체인저

```
[기존 epoll의 한계]
  - epoll_wait()로 "준비 알림"만 받고, 실제 read()/write()는 별도 syscall
  - 즉, 이벤트당 syscall 2번: epoll_wait + read
  - 고성능 환경에서 syscall 오버헤드가 병목

[io_uring (Linux 5.1+)]
  - 커널과 유저 스페이스가 공유 메모리 링 버퍼로 통신
  - syscall 없이 I/O 요청 제출 + 완료 확인 가능!

  ┌─────────────────────────────────────────────┐
  │            유저 스페이스                       │
  │  Submission Queue (SQ) ──제출──→              │
  │                              공유 메모리       │
  │  Completion Queue (CQ) ◀──완료──              │
  └──────────────────┬──────────────────────────┘
                     │ (메모리 매핑, syscall 불필요)
  ┌──────────────────┴──────────────────────────┐
  │            커널 스페이스                       │
  │  SQ에서 요청 읽음 → I/O 수행 → CQ에 결과 기록  │
  └─────────────────────────────────────────────┘

  성능 향상:
  - syscall 횟수 대폭 감소 (배치 처리)
  - zero-copy 가능
  - Netty 5.x, io_uring 네이티브 지원 예정
  - Java의 Virtual Thread도 내부적으로 활용 가능성
```

---

### Q8: 이 모든 커널 지식이 실무에서 왜 중요한가?

```
[실무 시나리오: API 서버가 느려졌다]

증상: p99 latency가 200ms → 2초로 증가
원인 추적:

1단계: 스레드 덤프 확인
  → 200개 Tomcat 스레드 중 195개가 WAITING 상태
  → 전부 DB 커넥션 대기 중 (HikariCP pool exhausted)

2단계: 왜 커넥션이 부족한가?
  → 외부 API 호출이 느려짐 (타임아웃 5초)
  → 스레드가 5초간 블로킹 → 커넥션 5초간 점유
  → 다른 요청도 커넥션 못 받아서 줄줄이 대기

3단계: 커널 레벨 이해가 있으면?
  → "이건 Blocking I/O가 스레드를 점유하는 전형적 문제"
  → 외부 API 호출을 Non-blocking으로 전환 (WebClient)
  → 또는 별도 스레드풀로 격리 (Bulkhead 패턴)
  → 또는 Virtual Thread로 전환 (스레드 점유 비용 제거)

[커널 지식이 디버깅 무기가 되는 순간들]
  - "왜 스레드 100개 넘으면 느려지지?" → 컨텍스트 스위칭 비용
  - "왜 코루틴이 빠르다고 하지?" → 유저 스페이스 전환, M:N 모델
  - "왜 Netty가 스레드 적게 써도 고성능?" → epoll 기반 Event Loop
  - "Virtual Thread가 만능이 아닌 이유?" → synchronized 블록에서 carrier 스레드 pin
  - "왜 CPU-bound 작업에 코루틴이 의미 없지?" → I/O 대기가 없으면 비동기 이점 없음
```

---

## 참고 자료

- Linux `epoll(7)` man page
- io_uring: Efficient Asynchronous I/O for Linux — Jens Axboe
- Understanding the Linux Kernel (O'Reilly)
- Linux kernel source: `fs/eventpoll.c`, `io_uring/io_uring.c`
