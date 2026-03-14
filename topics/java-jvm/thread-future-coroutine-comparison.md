# Java Thread vs CompletableFuture vs Kotlin Coroutine — 셋은 근본적으로 다른 계층의 개념이다

## 핵심 정리

### 한 줄 요약

**Thread**는 실행의 단위(OS 자원), **CompletableFuture**는 비동기 결과의 컨테이너(API), **Coroutine**은 중단 가능한 경량 실행 흐름(언어 기능)이다. 같은 "비동기"를 다루지만 **추상화 레벨이 완전히 다르다.**

---

### 세 개념의 위치

```
┌──────────────────────────────────────────────────────────┐
│                    개발자 코드                              │
│                                                           │
│  ┌─── Kotlin Coroutine ──────────────────────────────┐   │
│  │  suspend fun getOrder(id: Long): Order {           │   │
│  │      val order = repo.findById(id)  // 중단점       │   │
│  │      return order                                   │   │
│  │  }                                                  │   │
│  │  ★ 언어 레벨 추상화 — "중단 가능한 함수"             │   │
│  └────────────────────────────────────────────────────┘   │
│                          │ 내부적으로 사용                  │
│  ┌─── CompletableFuture ─┴───────────────────────────┐   │
│  │  CompletableFuture.supplyAsync(() -> fetchData())  │   │
│  │      .thenApply(data -> process(data))              │   │
│  │      .thenAccept(result -> save(result));            │   │
│  │  ★ API 레벨 추상화 — "미래에 완료될 결과"            │   │
│  └────────────────────────────────────────────────────┘   │
│                          │ 내부적으로 사용                  │
│  ┌─── Thread (OS 스레드) ─┴──────────────────────────┐   │
│  │  new Thread(() -> doWork()).start();                │   │
│  │  ★ OS 레벨 자원 — "실제 실행되는 흐름"              │   │
│  └────────────────────────────────────────────────────┘   │
│                          │                                 │
└──────────────────────────┼─────────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────┐
│              OS Kernel (스케줄링, 컨텍스트 스위칭)          │
└──────────────────────────────────────────────────────────┘
```

**비유로 이해하기**:
- **Thread** = 요리사 (실제로 일하는 사람)
- **CompletableFuture** = 주문서 ("이 요리 완성되면 알려줘")
- **Coroutine** = 멀티태스킹 요리사 ("파스타 삶는 동안 샐러드 만들기")

---

### 1. Java Thread — 실행의 물리적 단위

```java
// Thread는 OS 스레드와 1:1 매핑되는 실행 단위
Thread thread = new Thread(() -> {
    System.out.println("작업 실행: " + Thread.currentThread().getName());
});
thread.start();  // OS에 스레드 생성 요청
thread.join();   // 끝날 때까지 대기
```

```
Thread의 본질:
  ┌────────────────────────────────┐
  │ Java Thread                     │
  │  - 자기만의 스택 메모리 (~1MB)   │
  │  - 자기만의 Program Counter     │
  │  - 자기만의 실행 컨텍스트        │
  │                                │
  │  OS Thread와 1:1 매핑           │
  │  → OS 커널이 스케줄링           │
  │  → 컨텍스트 스위칭 비용 발생     │
  └────────────────────────────────┘

생성 비용: ~1ms + ~1MB 메모리
최대 개수: 수천 개 (OS 한계)
스케줄링: OS 커널 (Preemptive — 강제로 뺏김)
```

**Thread만으로 비동기를 구현하면 생기는 문제**:

```java
// ❌ 직접 Thread를 다루는 코드 — 매우 원시적
public Order getOrderWithUser(Long orderId) {
    // 결과를 담을 변수
    AtomicReference<User> userRef = new AtomicReference<>();

    Thread thread = new Thread(() -> {
        User user = userService.findById(orderId);
        userRef.set(user);
    });
    thread.start();

    Order order = orderService.findById(orderId);  // 메인 스레드에서 실행

    thread.join();  // user 스레드 끝날 때까지 대기
    order.setUser(userRef.get());

    return order;
    // 문제: 예외 처리는? 타임아웃은? 여러 작업 조합은?
}
```

---

### 2. CompletableFuture — 비동기 결과의 컨테이너

```java
// CompletableFuture는 "미래에 완료될 결과"를 표현하는 객체
// Thread를 직접 다루지 않고 비동기 파이프라인을 선언적으로 구성
CompletableFuture<Order> future = CompletableFuture
    .supplyAsync(() -> orderRepo.findById(id))       // ForkJoinPool에서 실행
    .thenApplyAsync(order -> {                        // 결과가 오면 이어서 실행
        order.setUser(userService.findById(order.getUserId()));
        return order;
    });

Order order = future.get();  // 결과 꺼내기 (blocking)
// 또는
future.thenAccept(order -> send(order));  // non-blocking 방식
```

```
CompletableFuture의 본질:
  ┌────────────────────────────────────────────────┐
  │ CompletableFuture<T>                            │
  │                                                 │
  │  ★ 자체는 스레드가 아님! 결과를 담는 상자일 뿐   │
  │                                                 │
  │  내부 구조:                                      │
  │  - result: T (완료된 결과 또는 예외)              │
  │  - stack: 완료 시 실행할 콜백 체인               │
  │  - executor: 실행할 스레드풀 (기본 ForkJoinPool) │
  │                                                 │
  │  상태:                                           │
  │  [미완료] → [완료(result)] 또는 [예외(exception)] │
  └────────────────────────────────────────────────┘

실행 주체: ForkJoinPool.commonPool() (기본) 또는 지정한 Executor
자체 메모리: 수십~수백 바이트 (객체 하나)
최대 개수: 수백만 개 가능 (가벼움 — 그냥 객체)
비동기 방식: 콜백 체인 (thenApply, thenCompose, ...)
```

**CompletableFuture가 Thread보다 나은 점**:

```java
// ✅ 여러 비동기 작업 조합이 깔끔
CompletableFuture<Order> orderFuture = supplyAsync(() -> getOrder(id));
CompletableFuture<User> userFuture = supplyAsync(() -> getUser(userId));
CompletableFuture<Coupon> couponFuture = supplyAsync(() -> getCoupon(userId));

// 세 작업이 동시에 실행되고, 모두 완료되면 합침
CompletableFuture<OrderDetail> result = orderFuture
    .thenCombine(userFuture, (order, user) -> new OrderWithUser(order, user))
    .thenCombine(couponFuture, (ow, coupon) -> new OrderDetail(ow, coupon));

// 예외 처리도 파이프라인에 포함
result.exceptionally(ex -> {
    log.error("주문 조회 실패", ex);
    return OrderDetail.empty();
});
```

**하지만 CompletableFuture의 한계**:

```java
// ❌ 복잡한 흐름은 콜백 지옥이 됨
CompletableFuture.supplyAsync(() -> getOrder(id))
    .thenCompose(order ->
        supplyAsync(() -> getUser(order.getUserId()))
            .thenCompose(user ->
                supplyAsync(() -> getPayment(order.getId()))
                    .thenApply(payment ->
                        new OrderDetail(order, user, payment)
                    )
            )
    )
    .thenCompose(detail ->
        supplyAsync(() -> enrichWithRecommendations(detail))
    )
    .exceptionally(ex -> handleError(ex));
// 읽기 어렵다!
```

---

### 3. Kotlin Coroutine — 중단 가능한 경량 실행 흐름

```kotlin
// Coroutine은 "코드를 중단점에서 멈췄다가 재개할 수 있는" 언어 기능
suspend fun getOrderDetail(id: Long): OrderDetail {
    val order = orderRepo.findById(id)          // 중단점 1: 여기서 멈춤
    val user = userRepo.findById(order.userId)   // 중단점 2: 여기서 멈춤
    return OrderDetail(order, user)              // 재개 후 반환
}
```

```
Coroutine의 본질:
  ┌────────────────────────────────────────────────┐
  │ Coroutine                                       │
  │                                                 │
  │  ★ OS 스레드가 아님! JVM 객체(상태 머신)일 뿐     │
  │  ★ suspend 지점에서 스레드를 반환하고 중단        │
  │  ★ 재개 시 아무 스레드에서나 이어서 실행 가능      │
  │                                                 │
  │  내부 구조:                                      │
  │  - state: 현재 중단 지점 (0, 1, 2...)            │
  │  - locals: 로컬 변수 저장 (스택 대신 힙에)        │
  │  - continuation: 재개 콜백                       │
  │                                                 │
  │  실행 흐름:                                      │
  │  코드 실행 → suspend 만남 → 상태 저장 → 스레드 반환│
  │  → (I/O 완료) → 상태 복원 → 스레드 할당 → 이어 실행│
  └────────────────────────────────────────────────┘

실행 주체: Dispatcher가 배정한 스레드 (IO, Default, Main 등)
자체 메모리: 수 KB (힙에 상태 머신 객체)
최대 개수: 수십만~수백만 개
비동기 방식: suspend/resume (컴파일러가 상태 머신으로 변환)
```

**같은 작업을 Coroutine으로 하면**:

```kotlin
// ✅ 동기 코드처럼 읽히지만 내부적으로 비동기
suspend fun getOrderDetail(id: Long): OrderDetail {
    // 이 두 작업을 병렬로 실행
    val order = async { orderRepo.findById(id) }
    val user = async { userRepo.findById(userId) }
    val coupon = async { couponRepo.findById(userId) }

    // 모두 완료되면 합침
    return OrderDetail(order.await(), user.await(), coupon.await())
}

// CompletableFuture의 thenCombine과 같은 효과지만 훨씬 읽기 쉽다
```

---

### 근본적 차이 비교표

| | Thread | CompletableFuture | Coroutine |
|---|---|---|---|
| **정체** | OS 자원 (실행 단위) | Java 객체 (결과 컨테이너) | 언어 기능 (중단 가능한 함수) |
| **추상화 레벨** | 가장 낮음 (OS 근접) | 중간 (API) | 가장 높음 (언어) |
| **메모리** | ~1MB (스택) | 수십 바이트 (객체) | 수 KB (상태 머신) |
| **생성 비용** | 높음 (~1ms) | 거의 없음 (객체 생성) | 매우 낮음 |
| **최대 개수** | 수천 | 수백만 (객체일 뿐) | 수십만~수백만 |
| **스케줄링** | OS 커널 (Preemptive) | Executor에 위임 | Dispatcher (Cooperative) |
| **코드 스타일** | 명령형 (join, wait) | 콜백 체이닝 (then) | 동기 코드처럼 (suspend) |
| **예외 처리** | try-catch + join | exceptionally/handle | try-catch (자연스러움) |
| **취소** | interrupt (불확실) | cancel (제한적) | Structured Concurrency (확실) |
| **언어** | Java | Java 8+ | Kotlin |

---

### 같은 문제를 세 가지 방식으로 풀기

"주문 + 사용자 + 쿠폰을 병렬로 조회해서 합치기"

#### Thread

```java
Order order;
User user;
Coupon coupon;

Thread t1 = new Thread(() -> order = orderRepo.findById(id));
Thread t2 = new Thread(() -> user = userRepo.findById(userId));
Thread t3 = new Thread(() -> coupon = couponRepo.findById(userId));

t1.start(); t2.start(); t3.start();
t1.join(); t2.join(); t3.join();  // 모두 끝날 때까지 대기

return new OrderDetail(order, user, coupon);
// 문제: 예외 처리 없음, 변수 가시성 문제, 타임아웃 없음
```

#### CompletableFuture

```java
var orderF = supplyAsync(() -> orderRepo.findById(id));
var userF = supplyAsync(() -> userRepo.findById(userId));
var couponF = supplyAsync(() -> couponRepo.findById(userId));

return CompletableFuture.allOf(orderF, userF, couponF)
    .thenApply(v -> new OrderDetail(orderF.join(), userF.join(), couponF.join()))
    .exceptionally(ex -> { log.error("실패", ex); return null; })
    .get(5, TimeUnit.SECONDS);  // 타임아웃 포함
```

#### Coroutine

```kotlin
suspend fun getOrderDetail(id: Long, userId: Long): OrderDetail =
    coroutineScope {
        val order = async { orderRepo.findById(id) }
        val user = async { userRepo.findById(userId) }
        val coupon = async { couponRepo.findById(userId) }

        OrderDetail(order.await(), user.await(), coupon.await())
        // 하나라도 실패하면 나머지 자동 취소 (Structured Concurrency)
    }
```

---

### Virtual Thread는 어디에 해당하나?

```
Java Virtual Thread (Java 21+):
  - Thread의 진화 버전
  - OS 스레드가 아닌 JVM이 관리하는 경량 스레드
  - Coroutine과 비슷한 포지션이지만 "기존 Thread API 그대로 사용"

  ┌────────────────────────────────────────────────┐
  │  Virtual Thread ≈ Thread의 옷을 입은 Coroutine  │
  │                                                 │
  │  - Thread API 호환 (기존 코드 수정 불필요)       │
  │  - 내부적으로 Carrier Thread 위에서 mount/unmount │
  │  - blocking I/O 만나면 자동으로 unmount           │
  │  - 메모리: 수 KB (Coroutine과 비슷)              │
  │  - 개수: 수백만 가능                             │
  └────────────────────────────────────────────────┘
```

```java
// Virtual Thread — 기존 코드 그대로 사용 가능
try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    var f1 = executor.submit(() -> orderRepo.findById(id));
    var f2 = executor.submit(() -> userRepo.findById(userId));
    var f3 = executor.submit(() -> couponRepo.findById(userId));

    return new OrderDetail(f1.get(), f2.get(), f3.get());
    // blocking이지만 Virtual Thread라서 OK
    // JVM이 알아서 Carrier Thread를 다른 Virtual Thread에 할당
}
```

## 헷갈렸던 포인트

### Q1. CompletableFuture는 새 스레드를 만드는 건가?

**아니다.** CompletableFuture 자체는 스레드를 만들지 않는다. 실행은 **Executor에 위임**한다.

```java
// supplyAsync()의 기본 동작:
CompletableFuture.supplyAsync(() -> doWork());
// → ForkJoinPool.commonPool()의 기존 스레드에서 실행

// Executor를 지정하면 해당 풀의 스레드에서 실행:
CompletableFuture.supplyAsync(() -> doWork(), myExecutor);

// ★ CompletableFuture = "누군가 해줄 작업"을 등록하는 API
// ★ 실제 실행은 스레드풀(Executor)이 담당
```

### Q2. Coroutine도 결국 스레드 위에서 돌아가는 거 아닌가?

**맞다.** Coroutine은 스레드를 없애는 게 아니라 **효율적으로 공유**하는 것이다.

```
OS Thread 4개로 Coroutine 10만 개를 실행:

Thread-1: [Coroutine A 실행] → [A suspend] → [Coroutine D 실행] → [D suspend] → [A resume] → ...
Thread-2: [Coroutine B 실행] → [B suspend] → [Coroutine E 실행] → ...
Thread-3: [Coroutine C 실행] → ...
Thread-4: [Coroutine F 실행] → ...

★ Coroutine이 suspend되면 스레드를 놓아줌
★ 다른 Coroutine이 그 스레드를 사용
★ 스레드 4개로 10만 개 작업을 처리하는 원리
```

핵심 차이: Thread는 blocking 시 **스레드가 잠김**, Coroutine은 suspend 시 **스레드를 반환**.

### Q3. CompletableFuture의 ForkJoinPool은 뭔가?

```
ForkJoinPool.commonPool():
  - JVM 전체에서 공유하는 기본 스레드풀
  - 크기: Runtime.getRuntime().availableProcessors() - 1
  - 4코어 CPU → 3개 스레드

★ 위험: 여러 곳에서 supplyAsync() 기본값을 쓰면
  → 모두 같은 3개 스레드를 공유
  → 한 곳에서 느린 작업이 전체를 블로킹

★ 해결: 용도별 Executor를 분리
  ExecutorService ioPool = Executors.newFixedThreadPool(10);
  CompletableFuture.supplyAsync(() -> dbQuery(), ioPool);
```

### Q4. 그러면 뭘 써야 하나?

```
Java만 사용:
  - Java 21+ → Virtual Thread (기존 코드 유지, 성능 향상)
  - Java 8~20 → CompletableFuture (비동기 파이프라인)
  - Thread 직접 사용 → 거의 안 함 (너무 저수준)

Kotlin 사용:
  - Coroutine (당연한 선택)
  - CompletableFuture → Coroutine으로 대체

Spring:
  - Spring MVC + @Async → ThreadPoolTaskExecutor + CompletableFuture
  - Spring MVC + Java 21 → Virtual Thread 활성화
  - Spring WebFlux → Reactor (Mono/Flux) 또는 Coroutine
```

### Q5. Coroutine의 Structured Concurrency가 CompletableFuture보다 나은 점은?

```kotlin
// Coroutine: 부모가 취소되면 자식도 자동 취소
coroutineScope {
    val order = async { getOrder(id) }       // 자식 1
    val user = async { getUser(userId) }     // 자식 2
    // user에서 예외 발생 → order도 자동 취소!
    // coroutineScope 전체가 예외로 종료
}
```

```java
// CompletableFuture: 수동으로 취소해야 함
var orderF = supplyAsync(() -> getOrder(id));
var userF = supplyAsync(() -> getUser(userId));

// userF에서 예외 발생해도 orderF는 계속 실행 중!
// 명시적으로 orderF.cancel(true) 해야 함
// → 취소 누락 시 리소스 낭비
```

## 참고 자료

- [JEP 444: Virtual Threads](https://openjdk.org/jeps/444)
- [Java CompletableFuture Javadoc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Kotlin Coroutines Guide](https://kotlinlang.org/docs/coroutines-guide.html)
- [Structured Concurrency — Roman Elizarov](https://elizarov.medium.com/structured-concurrency-722d765aa952)
