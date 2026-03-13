---
title: "비동기 처리 방식 비교 — Spring MVC, Netty, Coroutine, WebFlux"
parent: OS / 운영체제
nav_order: 3
---

# 비동기 처리 방식 비교 — Spring MVC, Netty, Coroutine, WebFlux 그리고 그 이면

## 핵심 정리

"비동기"라는 단어를 들으면 모두 같은 것 같지만, **기술마다 비동기를 구현하는 방식이 완전히 다르다.** 이 문서는 각 기술이 어떻게 동시성을 처리하는지, OS 스레드 레벨부터 애플리케이션 레벨까지 비교한다.

```
동기 vs 비동기의 핵심 차이:

[동기] 요청 → 스레드가 DB 응답 올 때까지 대기 → 응답 → 반환
       (스레드는 대기 중에도 메모리/CPU 점유)

[비동기] 요청 → DB에 쿼리 보내고 스레드 반환 → 다른 요청 처리
         → DB 응답 오면 콜백으로 이어서 처리
```

## 헷갈렸던 포인트

> 이 문서는 각 기술의 비동기 처리 방식을 이야기 형식으로 비교한다.

---

### Q1: 전통적인 Spring MVC는 어떻게 요청을 처리하나?

**Thread-per-Request (요청당 스레드) 모델이다.**

```
[Client 요청 1] → [Thread-1] → Controller → Service → DB 쿼리 (blocking) → 응답
[Client 요청 2] → [Thread-2] → Controller → Service → DB 쿼리 (blocking) → 응답
[Client 요청 3] → [Thread-3] → Controller → Service → DB 쿼리 (blocking) → 응답
...
[Client 요청 201] → 스레드 풀 고갈! → 대기 큐 → 타임아웃
```

**Tomcat 기본 설정:** 최대 200개 스레드 (`server.tomcat.threads.max=200`)

```java
@RestController
public class OrderController {

    @GetMapping("/order/{id}")
    public Order getOrder(@PathVariable Long id) {
        // 이 스레드는 DB 응답이 올 때까지 여기서 멈춰있다
        Order order = orderRepository.findById(id);  // ← blocking!
        return order;
    }
}
```

**문제점:**
- DB 쿼리가 100ms 걸리면, 200개 스레드로 초당 **최대 2000 TPS**
- 외부 API 호출이 느리면 스레드가 전부 대기 → **스레드 고갈**
- 스레드 하나당 **약 1MB 스택 메모리** → 200개 = 200MB

**그런데 실무에서는 이걸로 충분한 경우가 많다.** 대부분의 서비스는 수백~수천 TPS면 충분하고, DB 쿼리도 수 ms면 끝난다.

---

### Q2: Netty는 뭐가 다른가? — 이벤트 루프 모델

Netty는 **Java NIO 기반의 비동기 네트워크 프레임워크**다. Spring WebFlux, gRPC, Kafka, Elasticsearch 등이 내부적으로 Netty를 사용한다.

```
[Netty 구조]

Boss Group (1~2 스레드)          Worker Group (CPU 코어 수만큼 스레드)
  │                                │
  └─ 새 연결(Accept) 처리          └─ I/O 읽기/쓰기 + 비즈니스 로직
      │                                │
      ▼                                ▼
[ServerSocketChannel]           [SocketChannel + Pipeline]
      │                                │
      └─ 연결 수락 → Worker에 넘김      └─ Handler 체인으로 데이터 처리
```

**핵심: Event Loop**

```
[Event Loop (단일 스레드)]
  while (true) {
      events = selector.select();       // I/O 이벤트 감지 (epoll)
      for (event : events) {
          channel = event.channel();
          handler = channel.pipeline();
          handler.handle(event);         // 비동기로 처리
      }
  }
```

**하나의 Event Loop 스레드가 수천~수만 커넥션을 처리한다.**

왜 가능한가?
- **I/O 멀티플렉싱**: OS의 `epoll`(Linux)/`kqueue`(macOS)를 사용
- 스레드가 "데이터 올 때까지 기다리는" 대신 "데이터 오면 알려줘" 방식
- **Non-blocking I/O**: 읽기/쓰기가 즉시 반환 (데이터 없으면 0 바이트 반환)

```
[Spring MVC 방식 - blocking]
Thread-1: read() ────────────── 데이터 도착 ── 처리
           (대기 중... 아무것도 못함)

[Netty 방식 - non-blocking]
EventLoop: select() → 이벤트 없음 → 다른 채널 확인
           → 채널A 데이터 도착! → 처리
           → 채널B 데이터 도착! → 처리
           (놀지 않고 계속 일함)
```

**주의: Event Loop 스레드에서 blocking 작업을 하면 안 된다!**

```java
// ❌ 절대 하면 안 되는 코드
public class BadHandler extends ChannelInboundHandlerAdapter {
    @Override
    public void channelRead(ChannelHandlerContext ctx, Object msg) {
        // Event Loop 스레드에서 blocking!
        Thread.sleep(1000);           // ← Event Loop 전체가 1초간 멈춤
        jdbc.query("SELECT ...");     // ← JDBC는 blocking I/O!
    }
}

// ✅ blocking 작업은 별도 스레드풀로 분리
pipeline.addLast(new DefaultEventExecutorGroup(16), new BlockingHandler());
```

---

### Q3: Spring WebFlux는 Netty 위에서 뭘 더 하는 건가?

WebFlux = **Netty(또는 Undertow) + Reactor(Reactive Streams 구현체)**

Netty가 네트워크 I/O를 처리하면, **Reactor가 비동기 데이터 흐름을 관리**한다.

```java
@RestController
public class OrderController {

    @GetMapping("/order/{id}")
    public Mono<Order> getOrder(@PathVariable Long id) {
        // DB 쿼리를 비동기로! (R2DBC 사용)
        return orderRepository.findById(id)   // ← Non-blocking!
            .map(order -> {
                order.setViewed(true);
                return order;
            });
    }
}
```

**Spring MVC vs WebFlux 비교:**

```
[Spring MVC]
200개 스레드 → 각각 1개 요청 담당 → blocking 대기

[Spring WebFlux]
~4개 Event Loop 스레드 → 수만 개 요청을 번갈아 처리 → non-blocking

동시 접속 1만 명일 때:
  MVC: 스레드 200개 (나머지 9800명 대기)
  WebFlux: 스레드 4개로 1만 명 모두 처리 중
```

**그런데 왜 모든 프로젝트가 WebFlux를 안 쓰나?**

```
1. 코드가 어렵다:
   // MVC (직관적)
   Order order = orderService.findById(id);
   User user = userService.findById(order.getUserId());
   return new OrderDetail(order, user);

   // WebFlux (체이닝)
   return orderService.findById(id)
       .flatMap(order -> userService.findById(order.getUserId())
           .map(user -> new OrderDetail(order, user)));

2. 디버깅이 어렵다: 스택트레이스가 Reactor 내부 코드로 가득 찬다
3. 생태계 제약: JDBC, JPA 등 blocking 라이브러리 사용 불가
4. 대부분의 서비스는 MVC로 충분하다
```

---

### Q4: Kotlin Coroutine은 어떻게 다른가?

Coroutine은 **언어 레벨의 경량 스레드(Light-weight Thread)**다.

```
[OS 스레드 vs Coroutine]

OS 스레드:
- 1MB 스택 메모리
- OS가 스케줄링 (preemptive)
- Context Switch 비용 큼 (수 μs)
- 수백~수천 개가 한계

Coroutine:
- 수 KB 메모리
- 런타임이 스케줄링 (cooperative)
- 전환 비용 극소 (수십 ns)
- 수십만~수백만 개 가능
```

**핵심 개념: suspend (일시 중단)**

```kotlin
// suspend 함수: "이 지점에서 일시 중단될 수 있다"
suspend fun getOrder(id: Long): Order {
    val order = orderRepository.findById(id)    // suspend point: 여기서 중단
    val user = userService.findById(order.userId) // suspend point: 여기서 중단
    return OrderDetail(order, user)
}
```

**내부 동작:**

```
[Thread-1]
  Coroutine A: 실행 → DB 쿼리 보냄 → suspend(중단) → Thread-1 반환!
  Coroutine B: 실행 → API 호출 → suspend(중단) → Thread-1 반환!
  Coroutine A: DB 응답 도착 → resume(재개) → 이어서 실행 → 완료
  Coroutine C: 실행 → ...

하나의 스레드가 여러 Coroutine을 번갈아 실행한다!
```

**WebFlux(Reactor) vs Coroutine 비교:**

```kotlin
// Reactor (WebFlux) — 콜백 체이닝
fun getOrderDetail(id: Long): Mono<OrderDetail> {
    return orderRepo.findById(id)
        .flatMap { order ->
            userRepo.findById(order.userId)
                .map { user -> OrderDetail(order, user) }
        }
}

// Coroutine — 마치 동기 코드처럼
suspend fun getOrderDetail(id: Long): OrderDetail {
    val order = orderRepo.findById(id)       // 자연스럽다!
    val user = userRepo.findById(order.userId)
    return OrderDetail(order, user)
}
```

**Coroutine이 "동기처럼 보이지만 비동기"인 이유:**
- 컴파일러가 `suspend` 지점을 기준으로 코드를 **상태 머신(State Machine)**으로 변환
- 각 suspend 지점이 하나의 state가 되고, resume 시 해당 state부터 이어서 실행

```
// 컴파일러가 변환한 내부 구조 (개념적)
class GetOrderDetail_StateMachine {
    int state = 0;
    Order order;
    User user;

    void resume(Object result) {
        switch (state) {
            case 0:
                state = 1;
                orderRepo.findById(id, this::resume);  // 콜백 등록 후 반환
                return;
            case 1:
                order = (Order) result;
                state = 2;
                userRepo.findById(order.userId, this::resume);
                return;
            case 2:
                user = (User) result;
                complete(new OrderDetail(order, user));
                return;
        }
    }
}
```

---

### Q5: Java의 Virtual Thread(가상 스레드)는 뭔가?

Java 21에서 정식 도입된 **Project Loom**의 Virtual Thread는 Coroutine과 비슷한 개념이다.

```
[Platform Thread (기존)]
  OS 스레드 1:1 매핑 → 무겁다 (1MB), 수천 개 한계

[Virtual Thread (새로운)]
  JVM이 관리하는 경량 스레드 → 수 KB, 수백만 개 가능
  여러 Virtual Thread → 소수의 Platform Thread(Carrier Thread) 위에서 실행
```

```java
// Virtual Thread 사용 — 기존 코드 변경 없이!
try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    for (int i = 0; i < 100_000; i++) {
        executor.submit(() -> {
            // blocking I/O도 OK! JVM이 알아서 Virtual Thread를 unmount
            Order order = orderRepository.findById(id);  // JDBC blocking
            return order;
        });
    }
}
```

**Virtual Thread의 마법: blocking이 non-blocking으로 변환된다**

```
[Virtual Thread가 blocking I/O를 만나면]

VThread-1: JDBC 쿼리 호출 → JVM이 감지 → VThread-1을 Carrier Thread에서 분리(unmount)
                                          → Carrier Thread가 다른 VThread 실행
           ... DB 응답 도착 → VThread-1을 다시 Carrier Thread에 붙임(mount) → 이어서 실행
```

**기존 코드를 거의 안 바꿔도 된다는 것이 최대 장점!**

---

### Q6: 전체 비교 — 한눈에 보기

| 구분 | Spring MVC | Netty | WebFlux (Reactor) | Kotlin Coroutine | Java Virtual Thread |
|------|-----------|-------|------------------|-----------------|-------------------|
| **스레드 모델** | Thread-per-Request | Event Loop | Event Loop | Coroutine on Thread Pool | Virtual Thread on Carrier |
| **I/O 방식** | Blocking | Non-blocking | Non-blocking | suspend (Non-blocking) | Blocking → 자동 전환 |
| **동시 연결 수** | 수백 (스레드 수) | 수만~수십만 | 수만~수십만 | 수만~수십만 | 수만~수십만 |
| **코드 스타일** | 동기 (직관적) | 콜백/Future | Mono/Flux 체이닝 | suspend (동기처럼) | 동기 (기존 그대로) |
| **학습 난이도** | 낮음 | 높음 | 높음 | 중간 | 낮음 |
| **기존 라이브러리** | 모두 사용 가능 | 전용 필요 | R2DBC 등 전용 | suspend 지원 필요 | 기존 그대로 사용 |
| **디버깅** | 쉬움 | 어려움 | 어려움 | 중간 | 쉬움 |
| **적합한 상황** | 일반 웹 서비스 | 저수준 네트워크 | 고동시성 API | Spring + Kotlin | Java 21+ 프로젝트 |

---

### Q7: 그래서 뭘 써야 하나? — 실무 선택 기준

```
"우리 서비스는 뭘 써야 하나요?"

                       ┌─ 일반 CRUD, 수백 TPS
                       │  → Spring MVC (충분하다!)
                       │
 트래픽이 얼마나 되나? ─┤
                       │  ┌─ Java 21+ 가능?
                       └──┤  → Yes: Virtual Thread (기존 코드 유지!)
                          │  → No, Java 사용: WebFlux
                          └─ → Kotlin 사용: Coroutine + WebFlux

 저수준 네트워크 제어 필요? → Netty 직접 사용 (게임 서버, 프록시 서버 등)
```

**실무 조언:**
- **성급하게 WebFlux로 전환하지 마라.** MVC + DB 쿼리 최적화가 먼저다
- WebFlux를 쓰면 **팀 전체가 Reactive 패러다임을 이해**해야 한다
- Java 21 이상이면 **Virtual Thread가 가장 현실적인 선택**이다
- Kotlin을 이미 쓰고 있다면 **Coroutine이 자연스러운 선택**이다

## 참고 자료

- [Netty 공식 문서 — User Guide](https://netty.io/wiki/user-guide-for-4.x.html)
- [Spring WebFlux 공식 문서](https://docs.spring.io/spring-framework/reference/web/webflux.html)
- [Kotlin Coroutines 공식 가이드](https://kotlinlang.org/docs/coroutines-guide.html)
- [JEP 444: Virtual Threads](https://openjdk.org/jeps/444)
- [Project Loom — Ron Pressler 발표](https://cr.openjdk.org/~rpressler/loom/Loom-Proposal.html)
