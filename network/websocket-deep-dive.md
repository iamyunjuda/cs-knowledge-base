# WebSocket 심화 — 동작 원리부터 K8s 인프라 이슈까지

## 핵심 정리

### WebSocket이란?

HTTP는 **요청-응답** 모델이다. 클라이언트가 물어봐야 서버가 대답한다. 서버가 먼저 말을 걸 수 없다.

WebSocket은 **양방향 실시간 통신**이다. 한번 연결되면 클라이언트도, 서버도 아무 때나 데이터를 보낼 수 있다.

```
[HTTP]
클라이언트 --요청--> 서버
클라이언트 <-응답-- 서버
(매번 이 사이클을 반복. 서버가 먼저 보낼 수 없음)

[WebSocket]
클라이언트 <--연결 유지--> 서버
(어느 쪽이든 아무 때나 데이터 전송 가능)
```

### WebSocket 연결 과정 (상세)

WebSocket은 **HTTP로 시작해서 TCP 직통으로 전환**한다:

```
[클라이언트]                                         [서버]
    |                                                  |
    |  ① TCP 3-way handshake (SYN → SYN+ACK → ACK)   |
    |                                                  |
    |  ② HTTP 업그레이드 요청 ---------------------->  |
    |     GET /chat HTTP/1.1                           |
    |     Host: example.com                            |
    |     Upgrade: websocket                           |
    |     Connection: Upgrade                          |
    |     Sec-WebSocket-Key: dGhlIHNhbXBsZQ==         |
    |     Sec-WebSocket-Version: 13                    |
    |                                                  |
    |  ③ 서버가 101 응답 <----------------------------  |
    |     HTTP/1.1 101 Switching Protocols             |
    |     Upgrade: websocket                           |
    |     Connection: Upgrade                          |
    |     Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
    |                                                  |
    |  ============================================    |
    |  ④ 이후부터 HTTP가 아닌 WebSocket 프레임 통신   |
    |  ============================================    |
    |                                                  |
    |  -- [FIN=0, opcode=0x1, "안녕하"] -->            |  ← 텍스트 프레임 (fragmented)
    |  -- [FIN=1, opcode=0x0, "세요"]   -->            |  ← 이어지는 프레임
    |  <-- [FIN=1, opcode=0x1, "반갑습니다"] --        |  ← 서버 → 클라이언트
    |                                                  |
    |  -- [opcode=0x9 PING] -->                        |  ← 연결 살아있나 확인
    |  <-- [opcode=0xA PONG] --                        |  ← 살아있다고 응답
    |                                                  |
    |  -- [opcode=0x8 CLOSE] -->                       |  ← 연결 종료 요청
    |  <-- [opcode=0x8 CLOSE] --                       |  ← 종료 확인
```

**Sec-WebSocket-Key가 하는 일:**
- 클라이언트가 랜덤 키를 보냄
- 서버가 이 키 + 고정 GUID를 SHA-1 해시해서 `Sec-WebSocket-Accept`로 응답
- "이 서버가 진짜 WebSocket을 이해하는 서버가 맞는지" 검증하는 용도
- 보안 목적이 아니라 **프로토콜 호환성 확인** 목적

### WebSocket 프레임 구조

HTTP 업그레이드 이후에는 더 이상 텍스트가 아니라 **바이너리 프레임** 단위로 통신한다:

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-------+-+-------------+-------------------------------+
|F|R|R|R| opcode|M| Payload len |    Extended payload length    |
|I|S|S|S|  (4)  |A|     (7)     |            (16/64)            |
|N|V|V|V|       |S|             |  (if payload len==126/127)    |
| |1|2|3|       |K|             |                               |
+-+-+-+-+-------+-+-------------+-------------------------------+
|     Masking-key (0 or 4 bytes)                                |
+---------------------------------------------------------------+
|     Payload Data                                              |
+---------------------------------------------------------------+
```

| 필드 | 역할 |
|------|------|
| **FIN** | 이 프레임이 메시지의 마지막 조각인지 (1=마지막) |
| **opcode** | 0x1=텍스트, 0x2=바이너리, 0x8=종료, 0x9=ping, 0xA=pong |
| **MASK** | 클라이언트→서버는 반드시 마스킹 (프록시 캐시 오염 방지) |
| **Payload len** | 데이터 길이. 126이면 다음 2바이트, 127이면 다음 8바이트에 실제 길이 |

### HTTP Polling vs SSE vs WebSocket 비교

WebSocket 이전에도 실시간 통신을 흉내내는 방법들이 있었다:

```
[HTTP Polling]
클라이언트: "새 메시지 있어?" → 서버: "없어"     (1초마다 반복)
클라이언트: "새 메시지 있어?" → 서버: "없어"
클라이언트: "새 메시지 있어?" → 서버: "있어! 여기"
→ 문제: 쓸데없는 요청이 엄청남. 서버 부하 큼.

[HTTP Long Polling]
클라이언트: "새 메시지 있어?" → 서버: (있을 때까지 응답 안 함... 30초 대기...)
                                서버: "있어! 여기" (이벤트 발생 시)
클라이언트: "또 새 메시지 있어?" → 서버: (또 대기...)
→ Polling보다 낫지만 매번 HTTP 연결을 다시 맺어야 함

[SSE (Server-Sent Events)]
클라이언트: "구독할게" → 서버: (HTTP 연결 유지한 채로)
                         서버: "data: 메시지1\n\n"
                         서버: "data: 메시지2\n\n"
                         서버: "data: 메시지3\n\n"
→ 서버→클라이언트 단방향만 가능. 클라이언트→서버는 별도 HTTP 요청 필요

[WebSocket]
클라이언트 ↔ 서버 (양방향, 언제든지)
→ 오버헤드 최소. 진짜 실시간.
```

| | HTTP Polling | Long Polling | SSE | WebSocket |
|---|---|---|---|---|
| **방향** | 클라이언트→서버 | 클라이언트→서버 | 서버→클라이언트 | **양방향** |
| **연결** | 매번 새로 | 매번 새로 | 유지 | **유지** |
| **오버헤드** | 매우 높음 | 높음 | 낮음 | **최소** |
| **실시간성** | 낮음 (폴링 간격) | 중간 | 높음 | **높음** |
| **프로토콜** | HTTP | HTTP | HTTP | WS (HTTP 업그레이드) |
| **적합한 곳** | 간단한 상태 확인 | 알림 | 주식 시세, 뉴스 피드 | **채팅, 게임, 협업** |

---

## WebSocket과 스레드 모델

### 연결 하나 = 스레드 하나? (스레드 모델에 따라 다름)

WebSocket은 **연결이 계속 유지**된다. HTTP처럼 요청-응답 후 끊기지 않는다. 이 때문에 스레드 모델이 매우 중요해진다.

#### Thread-per-Connection (전통적 모델 — Spring MVC, Tomcat 기본)

```
[클라이언트 1] ──WS 연결──→ [스레드 1] (연결 동안 점유)
[클라이언트 2] ──WS 연결──→ [스레드 2] (연결 동안 점유)
[클라이언트 3] ──WS 연결──→ [스레드 3] (연결 동안 점유)
      ...                      ...
[클라이언트 N] ──WS 연결──→ [스레드 N] (연결 동안 점유)
```

- Tomcat 기본 스레드 풀: **200개**
- 즉, WebSocket 연결이 200개를 넘으면 **더 이상 연결을 받을 수 없음**
- 연결이 살아있는 동안 스레드가 아무 일 안 해도 계속 점유됨
- **문제**: 채팅방에 1만 명이 있으면 1만 개의 스레드가 필요 → 메모리 폭발 (스레드 1개 ≈ 1MB 스택)

#### Event-Driven / Non-blocking (Node.js, Netty, Spring WebFlux)

```
[클라이언트 1] ──WS 연결──┐
[클라이언트 2] ──WS 연결──┤
[클라이언트 3] ──WS 연결──┼──→ [이벤트 루프 (스레드 1~4개)]
      ...                 │      - 이벤트가 발생한 연결만 처리
[클라이언트 N] ──WS 연결──┘      - 나머지는 OS의 epoll/kqueue에 등록만
```

- **Node.js**: 싱글 스레드 이벤트 루프. 1개 스레드로 수만 연결 처리 가능
- **Netty (Java)**: 소수의 이벤트 루프 스레드 (보통 CPU 코어 수)로 수만 연결 처리
- **Spring WebFlux + Reactor Netty**: Netty 기반. 적은 스레드로 대량 연결 처리

```
[Node.js 이벤트 루프 동작]

while (true) {
    events = epoll_wait(...)   // OS에게 "이벤트 있는 소켓 알려줘" (블로킹 없음)
    for (event in events) {
        if (event == 클라이언트3이 메시지 보냄)  → onMessage(client3, data)
        if (event == 클라이언트7이 연결 끊김)    → onClose(client7)
        if (event == 새 클라이언트 연결)         → onConnect(newClient)
    }
}
// 이벤트가 없는 클라이언트는 아예 CPU를 사용하지 않음!
```

#### 비교 정리

| | Thread-per-Connection | Event-Driven |
|---|---|---|
| **1만 연결 시 스레드** | 1만 개 (≈ 10GB 메모리) | 4~8개 (수십 MB) |
| **대표 기술** | Tomcat, Spring MVC | Node.js, Netty, WebFlux |
| **장점** | 코드가 직관적, 디버깅 쉬움 | 메모리 효율, 대량 연결 가능 |
| **단점** | 연결 많으면 메모리 폭발 | 콜백/비동기 코드 복잡 |
| **적합한 곳** | 연결 수 적은 내부 시스템 | 채팅, 알림, 게임 등 대량 연결 |

> **Spring Boot에서 WebSocket 쓸 때**: 기본 Tomcat은 thread-per-connection이지만, Spring의 WebSocket 지원은 내부적으로 NIO를 사용하므로 연결마다 스레드를 점유하지는 않는다. 단, 메시지 처리 로직은 스레드 풀에서 실행된다.

---

## 쿠버네티스(K8s)에서 WebSocket 운영 시 이슈

### 이슈 1: 로드밸런서가 WebSocket 연결을 끊는다

HTTP는 요청마다 독립적이라 아무 Pod에 보내도 된다. 하지만 WebSocket은 **연결이 유지**되어야 한다.

```
[문제 상황]

클라이언트 --WS 연결--> [L4/L7 로드밸런서] ---> Pod A (연결 유지 중)

60초 후... 로드밸런서가 "이 연결 idle 하네?" → 연결 끊어버림 💥
```

**원인**: 대부분의 로드밸런서/Ingress는 기본 **idle timeout**이 60초 정도다. WebSocket은 데이터를 안 보내는 시간이 길 수 있어서 타임아웃에 걸린다.

**해결:**

```yaml
# Nginx Ingress 설정
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  annotations:
    nginx.ingress.kubernetes.io/proxy-read-timeout: "3600"     # 1시간
    nginx.ingress.kubernetes.io/proxy-send-timeout: "3600"
    nginx.ingress.kubernetes.io/proxy-connect-timeout: "7"
    # WebSocket 업그레이드 허용 (Nginx Ingress는 기본 지원하지만 명시적으로)
    nginx.ingress.kubernetes.io/websocket-services: "chat-service"
```

```
# 애플리케이션 레벨 해결 — Ping/Pong
클라이언트 -- ping (30초마다) --> 서버
클라이언트 <-- pong ------------ 서버
→ 연결이 idle 하지 않으니 로드밸런서가 안 끊음
→ 동시에 연결이 살아있는지 헬스체크 역할도 함
```

### 이슈 2: Sticky Session (세션 고정) 문제

WebSocket 연결은 **특정 Pod에 고정**되어야 한다. 그런데 K8s Service는 기본적으로 라운드로빈이다.

```
[문제 상황]

1단계: HTTP 업그레이드 요청 → 로드밸런서 → Pod A (핸드셰이크 완료)
2단계: WebSocket 프레임 전송 → 로드밸런서 → Pod B (???) 💥
→ Pod B는 이 클라이언트의 핸드셰이크를 모름. 연결 실패.
```

**해결:**

```yaml
# K8s Service에 sessionAffinity 설정
apiVersion: v1
kind: Service
metadata:
  name: chat-service
spec:
  sessionAffinity: ClientIP    # 같은 클라이언트 IP는 같은 Pod로
  sessionAffinityConfig:
    clientIP:
      timeoutSeconds: 3600     # 1시간 유지
  ports:
    - port: 80
      targetPort: 8080
```

```yaml
# 또는 Nginx Ingress에서 cookie 기반 sticky session
metadata:
  annotations:
    nginx.ingress.kubernetes.io/affinity: "cookie"
    nginx.ingress.kubernetes.io/affinity-mode: "persistent"
    nginx.ingress.kubernetes.io/session-cookie-name: "WS_AFFINITY"
    nginx.ingress.kubernetes.io/session-cookie-expires: "3600"
```

> 단, L4 로드밸런서(TCP 레벨)라면 이 문제가 발생하지 않는다. TCP 연결 자체가 하나의 Pod에 고정되니까. 문제는 L7 로드밸런서가 HTTP와 WebSocket을 분리해서 처리할 때 발생한다.

### 이슈 3: 여러 Pod 간 메시지 브로드캐스트

가장 까다로운 문제. 채팅방에 유저 A, B, C가 있는데 각각 다른 Pod에 연결되어 있을 때:

```
[문제 상황]

유저 A ──WS──→ Pod 1
유저 B ──WS──→ Pod 2
유저 C ──WS──→ Pod 3

유저 A가 "안녕!" 전송
→ Pod 1은 유저 A의 메시지를 받음
→ 그런데 유저 B는 Pod 2에, 유저 C는 Pod 3에 연결되어 있음
→ Pod 1이 직접 유저 B, C에게 보낼 방법이 없음 💥
```

**해결 — 외부 메시지 브로커 (Pub/Sub)**

```
유저 A ──WS──→ [Pod 1] ──publish──→ [Redis Pub/Sub] ──subscribe──→ [Pod 2] ──WS──→ 유저 B
                                          │
                                          └─subscribe──→ [Pod 3] ──WS──→ 유저 C
```

모든 Pod가 Redis(또는 Kafka, RabbitMQ)를 **구독(subscribe)**하고 있다가, 메시지가 오면 자기에게 연결된 클라이언트들에게 전달한다.

**구체적인 구현 흐름:**

```
1. 유저 A가 "안녕!" 메시지를 Pod 1에 전송 (WebSocket)
2. Pod 1이 Redis의 "chatroom:123" 채널에 publish
3. Pod 1, 2, 3 모두 "chatroom:123"을 subscribe 하고 있음
4. Redis가 Pod 1, 2, 3 모두에게 "안녕!" 메시지를 전달
5. 각 Pod는 자기에게 연결된 WebSocket 클라이언트에게 전달
   - Pod 1 → 유저 A (보낸 사람 본인에게도)
   - Pod 2 → 유저 B
   - Pod 3 → 유저 C
```

**메시지 브로커 선택지:**

| 브로커 | 특징 | 적합한 경우 |
|--------|------|------------|
| **Redis Pub/Sub** | 가장 간단. 메시지 유실 가능 (구독 시점 이후만 받음) | 채팅, 알림 등 유실 허용 가능한 실시간 메시지 |
| **Redis Streams** | Pub/Sub + 메시지 저장. 재처리 가능 | 메시지 유실 불가, 히스토리 필요 |
| **Kafka** | 대용량, 영구 저장, 순서 보장 | 대규모 이벤트 스트리밍, 메시지 유실 절대 불가 |
| **RabbitMQ** | 라우팅 유연, ACK 기반 신뢰성 | 복잡한 라우팅 규칙이 필요한 경우 |

### 이슈 4: Pod 스케일링 / 재시작 시 연결 끊김

K8s는 Pod를 자유롭게 죽이고 새로 만든다. 그런데 WebSocket 연결은 Pod에 물려있다.

```
[문제 상황]

유저 100명 ──WS──→ Pod 1
                    ↓
              K8s가 Pod 1을 죽임 (스케일 다운, 배포, OOM 등)
                    ↓
              100명의 WebSocket 연결이 한꺼번에 끊김 💥
```

**해결 — Graceful Shutdown + 클라이언트 재연결:**

```yaml
# Pod의 Graceful Shutdown 설정
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 60  # 60초 동안 기존 연결 정리할 시간
```

```
[Graceful Shutdown 순서]

1. K8s가 Pod에 SIGTERM 보냄
2. Pod가 새 연결 수락 중지
3. 기존 WebSocket 클라이언트들에게 "곧 끊긴다" close 프레임 전송
4. terminationGracePeriodSeconds 동안 기존 연결 정리
5. 시간 초과 시 SIGKILL로 강제 종료
```

```javascript
// 클라이언트 측 — 자동 재연결 로직 (필수!)
function connectWebSocket() {
    const ws = new WebSocket('wss://example.com/chat');

    ws.onclose = (event) => {
        console.log('연결 끊김. 재연결 시도...');
        // 지수 백오프로 재연결 (1초, 2초, 4초, 8초...)
        setTimeout(() => connectWebSocket(), getBackoffDelay());
    };

    ws.onopen = () => {
        console.log('연결 성공');
        resetBackoff();     // 백오프 초기화
        resubscribe(ws);    // 채팅방 재구독 등
    };
}
```

> **핵심**: WebSocket을 쓰면 **클라이언트 측 재연결 로직은 필수**다. 네트워크 끊김, Pod 재시작, 배포 등 언제든 연결이 끊길 수 있다.

### 이슈 5: 연결 수 관리 (Connection Limit)

WebSocket은 연결이 유지되므로, Pod당 최대 연결 수를 관리해야 한다.

```
[Pod 1개의 한계]

연결 1개 ≈ 파일 디스크립터 1개 + 소켓 버퍼 메모리
Linux 기본 파일 디스크립터 제한: 1024개 (ulimit -n)
→ 조정하지 않으면 1024개 연결이 최대

실무에서는:
- ulimit -n 65535 로 올림
- Pod 메모리 기준으로 연결 수 제한 (연결 1개 ≈ 수십 KB)
- 10만 연결 ≈ 수 GB 메모리 필요
```

```yaml
# HPA (Horizontal Pod Autoscaler) — 연결 수 기반 스케일링
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: chat-server
  minReplicas: 2
  maxReplicas: 20
  metrics:
    - type: Pods
      pods:
        metric:
          name: websocket_connections   # 커스텀 메트릭
        target:
          type: AverageValue
          averageValue: "5000"          # Pod당 평균 5000연결이면 스케일 아웃
```

### 전체 아키텍처 그림

```
                          [클라이언트들]
                           ↕ WSS (443)
                    ┌──────────────────┐
                    │   Nginx Ingress   │  ← sticky session, timeout 설정
                    │   (L7 LB)         │
                    └──────┬───────────┘
                           │
              ┌────────────┼────────────┐
              ↓            ↓            ↓
         ┌─────────┐ ┌─────────┐ ┌─────────┐
         │  Pod 1   │ │  Pod 2   │ │  Pod 3   │  ← HPA로 자동 스케일링
         │ (WS 서버)│ │ (WS 서버)│ │ (WS 서버)│
         └────┬────┘ └────┬────┘ └────┬────┘
              │            │            │
              └────────────┼────────────┘
                           ↓
                  ┌──────────────────┐
                  │  Redis Pub/Sub    │  ← Pod 간 메시지 브로드캐스트
                  │  (또는 Kafka)     │
                  └──────────────────┘
```

---

## 헷갈렸던 포인트

### Q: WebSocket이 HTTP를 완전히 대체할 수 있나?

아니다. WebSocket은 **실시간 양방향 통신이 필요한 경우**에만 쓰는 게 맞다. 일반 API 호출(CRUD)은 HTTP가 더 적합하다. WebSocket은 연결을 유지해야 해서 서버 리소스를 더 많이 먹고, 로드밸런싱도 까다롭다.

### Q: WebSocket 연결이 유지되면 서버 메모리가 터지지 않나?

스레드 모델에 따라 다르다. Thread-per-connection이면 1만 연결 = 1만 스레드 ≈ 10GB로 터질 수 있다. Event-driven(Netty, Node.js)이면 1만 연결도 스레드 몇 개 + 소켓 버퍼 메모리만으로 처리 가능하다. 대량 연결이 필요하면 반드시 event-driven 모델을 써야 한다.

### Q: K8s에서 Pod가 여러 개면 채팅 메시지를 어떻게 전달하나?

Redis Pub/Sub 같은 **외부 메시지 브로커**로 해결한다. 모든 Pod가 동일한 채널을 구독하고, 메시지가 발행되면 각 Pod가 자기에게 연결된 클라이언트에게 전달한다. Pod 내부에서만 브로드캐스트하면 다른 Pod의 유저는 메시지를 못 받는다.

### Q: WebSocket에 Sticky Session이 꼭 필요한가?

L4 로드밸런서(TCP 레벨)라면 TCP 연결 자체가 하나의 Pod에 고정되므로 별도 설정이 필요 없다. L7 로드밸런서(HTTP 레벨)에서 HTTP 업그레이드와 이후 WebSocket 프레임을 같은 Pod로 보내려면 sticky session이 필요할 수 있다. Nginx Ingress는 WebSocket을 기본 지원하므로 일반적으로 별도 sticky session 없이도 동작한다.

### Q: WebSocket 서버가 싱글 스레드(Node.js)면 메시지 처리가 느리지 않나?

이벤트 루프가 **I/O 대기 시간에 다른 작업**을 하므로, I/O 중심 작업(메시지 수신/발신)은 싱글 스레드로도 충분히 빠르다. 하지만 메시지 처리에 CPU 연산이 많으면(암호화, 데이터 가공 등) 싱글 스레드가 병목이 된다. 이 경우 Worker Thread를 쓰거나, 무거운 연산은 별도 서비스로 분리해야 한다.

### Q: Socket.IO와 WebSocket은 같은 건가?

아니다. Socket.IO는 WebSocket을 **감싸는 라이브러리**다. WebSocket이 안 되는 환경에서 자동으로 Long Polling으로 폴백하고, 재연결/방(room)/브로드캐스트 등의 편의 기능을 제공한다. 단, Socket.IO 클라이언트는 순수 WebSocket 서버와 호환되지 않는다 (자체 프로토콜 사용).

## 참고 자료

- [MDN - WebSocket API](https://developer.mozilla.org/ko/docs/Web/API/WebSockets_API)
- [RFC 6455 - The WebSocket Protocol](https://datatracker.ietf.org/doc/html/rfc6455)
