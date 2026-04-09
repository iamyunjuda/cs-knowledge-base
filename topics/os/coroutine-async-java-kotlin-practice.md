# 코루틴과 비동기의 모든 것 Part 2 — Java/Kotlin 비동기 실전 심화

## 핵심 정리

Part 1에서 커널 레벨을 다뤘다면, 이 문서는 **Java/Kotlin에서 비동기를 실제로 어떻게 구현하고 사용하는지**, 내부 동작 원리와 함께 실무 수준 코드로 정리한다.

```
Java 비동기 진화 타임라인:
  Java 1.0 (1996)  : Thread + Runnable
  Java 5   (2004)  : ExecutorService + Future
  Java 7   (2011)  : ForkJoinPool
  Java 8   (2014)  : CompletableFuture
  Java 9   (2017)  : Flow (Reactive Streams)
  Java 19  (2022)  : Virtual Thread (Preview)
  Java 21  (2023)  : Virtual Thread (정식), Structured Concurrency (Preview)

Kotlin 비동기:
  Kotlin 1.1 (2017) : Coroutine (Experimental)
  Kotlin 1.3 (2018) : Coroutine (Stable), Structured Concurrency
  Kotlin 1.4+       : Flow (Cold Stream), Channel
```

---

## 헷갈렸던 포인트

---

### Q1: CompletableFuture — 내부에서 정확히 무슨 일이 일어나는가?

```java
// 단순해 보이지만 내부는 복잡하다
CompletableFuture<User> future = CompletableFuture
    .supplyAsync(() -> userRepo.findById(1L))           // (1)
    .thenApplyAsync(user -> enrichWithProfile(user))     // (2)
    .thenApplyAsync(user -> enrichWithOrders(user));     // (3)
```

```
내부 동작 분해:

(1) supplyAsync()
    → ForkJoinPool.commonPool()에서 스레드 하나가 실행
    → DB 호출하는 동안 이 스레드는 블로킹됨 ← 여기가 함정!
    → 결과가 나오면 CompletableFuture의 result 필드에 저장

(2) thenApplyAsync()
    → (1)이 완료되면 트리거
    → 또 ForkJoinPool에서 다른 스레드가 실행 (스레드 달라질 수 있음!)
    → 완료되면 다음 stage로 전달

실행 스레드 흐름:
  supplyAsync → ForkJoinPool-worker-1에서 실행
  thenApplyAsync → ForkJoinPool-worker-3에서 실행 (다른 스레드!)
  thenApplyAsync → ForkJoinPool-worker-1에서 실행 (재사용될 수도)

★ 핵심 함정: supplyAsync 안에서 Blocking I/O 하면
  ForkJoinPool의 스레드가 점유됨 → 다른 CompletableFuture도 지연
```

**실무에서 CompletableFuture를 올바르게 쓰는 법:**

```java
// ✅ 올바른 사용: 전용 Executor 지정
ExecutorService ioExecutor = Executors.newFixedThreadPool(32);

CompletableFuture<User> userFuture =
    CompletableFuture.supplyAsync(() -> userRepo.findById(id), ioExecutor);

CompletableFuture<List<Order>> ordersFuture =
    CompletableFuture.supplyAsync(() -> orderRepo.findByUserId(id), ioExecutor);

// 두 작업 병렬 실행 후 합치기
CompletableFuture<UserDetail> result = userFuture
    .thenCombine(ordersFuture, (user, orders) -> new UserDetail(user, orders));

// ❌ 흔한 실수: 전부 순차 실행됨
CompletableFuture<UserDetail> wrong = CompletableFuture
    .supplyAsync(() -> userRepo.findById(id))
    .thenApply(user -> {
        List<Order> orders = orderRepo.findByUserId(id); // 여기서 또 블로킹!
        return new UserDetail(user, orders);
    });
```

**CompletableFuture 에러 처리 실전:**

```java
CompletableFuture<User> result = CompletableFuture
    .supplyAsync(() -> userRepo.findById(id), ioExecutor)
    .thenApplyAsync(user -> enrichWithProfile(user), ioExecutor)
    .exceptionally(ex -> {
        // ★ 주의: ex는 CompletionException으로 감싸져 있다
        Throwable cause = ex.getCause();
        if (cause instanceof UserNotFoundException) {
            return User.EMPTY;
        }
        throw new RuntimeException(cause); // 다시 던지기
    })
    .orTimeout(3, TimeUnit.SECONDS)  // Java 9+: 타임아웃
    .whenComplete((user, ex) -> {
        if (ex != null) {
            metrics.incrementCounter("user.fetch.error");
        }
    });
```

---

### Q2: Virtual Thread (Project Loom) — 마법이 아니라 트레이드오프다

```
[Virtual Thread의 구조]

  ┌─────────────────────────────────────────────┐
  │              JVM (유저 스페이스)                │
  │                                               │
  │  Virtual Thread 1 ──┐                         │
  │  Virtual Thread 2 ──┤                         │
  │  Virtual Thread 3 ──┼──→ Carrier Thread 1     │──→ OS Thread 1
  │  ...                │    (Platform Thread)     │
  │  Virtual Thread N ──┘                         │
  │                                               │
  │  Virtual Thread A ──┐                         │
  │  Virtual Thread B ──┼──→ Carrier Thread 2     │──→ OS Thread 2
  │  Virtual Thread C ──┘    (Platform Thread)    │
  └─────────────────────────────────────────────┘

동작 원리:
  1. Virtual Thread가 Blocking I/O 호출 (예: Socket.read())
  2. JVM이 감지 → 해당 VT를 Carrier Thread에서 unmount
  3. Carrier Thread는 다른 VT를 mount하여 실행
  4. I/O 완료되면 → 아무 Carrier Thread에 다시 mount하여 재개

  ★ OS 입장에선 Carrier Thread(=Platform Thread) 몇 개만 보임
  ★ 10만 개 Virtual Thread를 8개 Carrier Thread로 처리 가능
```

**Virtual Thread가 빛나는 곳:**

```java
// ✅ I/O-bound 작업에 완벽
try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    List<Future<Response>> futures = urls.stream()
        .map(url -> executor.submit(() -> httpClient.send(
            HttpRequest.newBuilder().uri(URI.create(url)).build(),
            HttpResponse.BodyHandlers.ofString()
        )))
        .toList();

    List<Response> responses = futures.stream()
        .map(f -> {
            try { return f.get(); }
            catch (Exception e) { throw new RuntimeException(e); }
        })
        .toList();
}
// 1만 개 HTTP 요청을 동시에 — 각각 Virtual Thread
// OS 스레드는 CPU 코어 수만큼만 사용
```

**Virtual Thread의 함정들 (실무에서 터지는 것들):**

```java
// ❌ 함정 1: synchronized 블록에서 Carrier Thread Pinning
synchronized (lock) {
    // 이 안에서 Blocking I/O 하면 Carrier Thread가 pinning됨
    // → Virtual Thread의 이점이 사라짐!
    database.query("SELECT ...");  // Carrier Thread가 블로킹됨
}

// ✅ 해결: ReentrantLock 사용
private final ReentrantLock lock = new ReentrantLock();
lock.lock();
try {
    database.query("SELECT ...");  // VT가 unmount 가능
} finally {
    lock.unlock();
}

// ❌ 함정 2: ThreadLocal 남용
// Virtual Thread는 수십만 개 생성 가능 → ThreadLocal도 수십만 개
// 메모리 폭발 위험
static final ThreadLocal<ExpensiveObject> cache =
    ThreadLocal.withInitial(ExpensiveObject::new);  // VT마다 생성됨!

// ✅ 해결: ScopedValue (Java 21 Preview)
static final ScopedValue<RequestContext> CONTEXT = ScopedValue.newInstance();
ScopedValue.where(CONTEXT, new RequestContext(userId))
    .run(() -> handleRequest());

// ❌ 함정 3: CPU-bound 작업에 사용
// Virtual Thread는 I/O 대기를 효율화하는 것
// CPU를 100% 쓰는 작업엔 이점 없음 (오히려 스케줄링 오버헤드만 추가)
Executors.newVirtualThreadPerTaskExecutor().submit(() -> {
    // 이미지 리사이즈, 암호화 등 CPU-bound → 의미 없음
    return resizeImage(largeImage);
});
```

---

### Q3: Kotlin Coroutine — CPS 변환과 상태 머신의 실체

```kotlin
// 개발자가 작성한 코드
suspend fun fetchUserDetail(userId: Long): UserDetail {
    val user = userRepo.findById(userId)        // 중단점 1
    val orders = orderRepo.findByUserId(userId)  // 중단점 2
    return UserDetail(user, orders)
}
```

```
[컴파일러가 변환한 코드 (CPS - Continuation Passing Style)]

코루틴은 마법이 아니다. 컴파일러가 상태 머신으로 변환한다:

fun fetchUserDetail(userId: Long, cont: Continuation<UserDetail>): Any? {
    // 상태 머신 클래스 (각 suspend 지점이 하나의 상태)
    class FetchUserDetailSM : ContinuationImpl(cont) {
        var state = 0
        var user: User? = null
        var orders: List<Order>? = null

        override fun invokeSuspend(result: Result<Any?>): Any? {
            when (state) {
                0 -> {  // 초기 상태
                    state = 1
                    val suspendResult = userRepo.findById(userId, this)
                    if (suspendResult == COROUTINE_SUSPENDED) return COROUTINE_SUSPENDED
                    // 즉시 반환되면 fall-through
                }
                1 -> {  // findById 완료 후
                    user = result.getOrThrow() as User
                    state = 2
                    val suspendResult = orderRepo.findByUserId(userId, this)
                    if (suspendResult == COROUTINE_SUSPENDED) return COROUTINE_SUSPENDED
                }
                2 -> {  // findByUserId 완료 후
                    orders = result.getOrThrow() as List<Order>
                    return UserDetail(user!!, orders!!)
                }
            }
        }
    }
}

★ suspend 함수 하나가 → 상태 머신 클래스 하나로 변환
★ 각 suspend 지점이 → state 값 하나로 매핑
★ Continuation = "나중에 여기서 이어서 해줘" 콜백 객체
```

---

### Q4: Dispatcher — 코루틴이 실행되는 스레드를 결정하는 핵심

```kotlin
// Dispatcher별 특성과 사용 기준

// 1. Dispatchers.Default — CPU 집약 작업
//    스레드 수 = CPU 코어 수 (Runtime.getRuntime().availableProcessors())
//    예: JSON 파싱, 정렬, 계산
launch(Dispatchers.Default) {
    val sorted = hugeList.sortedBy { it.score }  // CPU-bound
}

// 2. Dispatchers.IO — I/O 블로킹 작업
//    스레드 수 = max(64, CPU 코어 수)
//    예: DB 쿼리, 파일 읽기, HTTP 호출
launch(Dispatchers.IO) {
    val result = database.query("SELECT ...")  // Blocking I/O
}

// 3. Dispatchers.Main — UI 스레드 (Android)
//    메인 스레드 1개
launch(Dispatchers.Main) {
    textView.text = "Updated"  // UI 업데이트
}

// 4. Dispatchers.Unconfined — 테스트/특수 용도
//    중단 전: 호출한 스레드에서 실행
//    중단 후: 재개하는 스레드에서 실행 (예측 불가!)
//    ❌ 실무에서 거의 안 씀
```

```
[Dispatchers.Default와 IO의 관계 — 같은 풀을 공유한다!]

  ┌──────────────────────────────────────────────┐
  │         Shared Thread Pool (LimitingDispatcher)│
  │                                                │
  │  ┌─ Default ──────────────────┐                │
  │  │ 최대 CPU 코어 수만큼 동시 실행│                │
  │  │ [worker-1][worker-2]...[N] │                │
  │  └────────────────────────────┘                │
  │          ↕ (같은 스레드들 공유)                   │
  │  ┌─ IO ───────────────────────┐                │
  │  │ 최대 64개까지 동시 실행       │                │
  │  │ [worker-1]...[worker-64]   │                │
  │  └────────────────────────────┘                │
  └──────────────────────────────────────────────┘

  ★ Default와 IO는 같은 스레드를 공유하되, 동시 실행 수만 제한
  ★ withContext(Dispatchers.IO)해도 스레드 전환이 안 일어날 수 있음!
```

---

### Q5: Structured Concurrency — 코루틴을 안전하게 쓰는 핵심 원칙

```kotlin
// ❌ 위험한 코드: GlobalScope
fun processOrder(orderId: Long) {
    GlobalScope.launch {
        // 부모가 없는 코루틴 → 누가 취소/관리하지?
        // 이 코루틴이 실패해도 아무도 모름
        // 메모리 릭 가능
        sendNotification(orderId)
    }
}

// ✅ Structured Concurrency
class OrderService(private val scope: CoroutineScope) {

    suspend fun processOrder(orderId: Long) {
        coroutineScope {
            // 이 블록 안의 모든 코루틴이 완료돼야 함수 반환
            val order = async { orderRepo.findById(orderId) }
            val user = async { userRepo.findById(order.await().userId) }

            // order나 user 중 하나가 실패하면 → 나머지도 자동 취소
            val notification = async { createNotification(user.await(), order.await()) }
            sendNotification(notification.await())
        }
        // 여기 도달 = 모든 코루틴 정상 완료
    }
}
```

**coroutineScope vs supervisorScope:**

```kotlin
// coroutineScope: 자식 하나 실패 → 전부 취소
suspend fun fetchAll() = coroutineScope {
    val a = async { fetchA() }  // 이게 실패하면
    val b = async { fetchB() }  // 이것도 취소됨
    Pair(a.await(), b.await())
}

// supervisorScope: 자식 실패해도 나머지 계속 실행
suspend fun fetchAllBestEffort() = supervisorScope {
    val a = async {
        try { fetchA() } catch (e: Exception) { defaultA() }
    }
    val b = async {
        try { fetchB() } catch (e: Exception) { defaultB() }
    }
    Pair(a.await(), b.await())
}

// ★ 실무 선택 기준:
// "전부 성공해야 의미 있다" → coroutineScope (주문 처리)
// "되는 것만이라도 보여줘야 한다" → supervisorScope (대시보드)
```

---

### Q6: Spring + Coroutine 실전 — 컨트롤러부터 레포지토리까지

```kotlin
// Spring WebFlux + Coroutine 전체 흐름

@RestController
class UserController(private val userService: UserService) {

    // suspend 함수를 직접 쓸 수 있음 (Spring 5.2+)
    @GetMapping("/users/{id}")
    suspend fun getUser(@PathVariable id: Long): UserDetailResponse {
        return userService.getUserDetail(id)
    }

    // Flow를 반환하면 SSE/스트리밍 가능
    @GetMapping("/users/{id}/events", produces = [MediaType.TEXT_EVENT_STREAM_VALUE])
    fun getUserEvents(@PathVariable id: Long): Flow<ServerSentEvent<String>> {
        return userService.getUserEventStream(id)
    }
}

@Service
class UserService(
    private val userRepo: UserRepository,
    private val orderClient: OrderClient,
    private val cacheService: CacheService
) {
    suspend fun getUserDetail(id: Long): UserDetailResponse {
        // 캐시 먼저 확인
        cacheService.get("user:$id")?.let { return it }

        // 병렬로 조회
        return coroutineScope {
            val userDeferred = async { userRepo.findByIdOrThrow(id) }
            val ordersDeferred = async { orderClient.getRecentOrders(id) }

            val user = userDeferred.await()
            val orders = ordersDeferred.await()

            UserDetailResponse(user, orders).also {
                // 캐시 저장 (fire-and-forget이 아닌 구조화된 방식)
                launch { cacheService.put("user:$id", it, ttl = 5.minutes) }
            }
        }
    }
}

// R2DBC + Coroutine Repository
interface UserRepository : CoroutineCrudRepository<User, Long> {
    suspend fun findByEmail(email: String): User?

    @Query("SELECT * FROM users WHERE status = :status")
    fun findByStatus(status: String): Flow<User>  // 스트리밍
}
```

**Spring MVC + Coroutine (WebFlux 없이):**

```kotlin
// Spring MVC에서도 suspend 함수 사용 가능 (Spring 6.1+)
// 내부적으로 Virtual Thread 또는 비동기 요청 처리 사용

@RestController
class OrderController(private val orderService: OrderService) {

    @GetMapping("/orders/{id}")
    suspend fun getOrder(@PathVariable id: Long): OrderResponse {
        // Spring MVC가 코루틴을 Mono로 브릿지
        // → 서블릿 스레드 반환 → 코루틴 완료 시 응답
        return orderService.findById(id)
    }
}

// ★ 주의: Spring MVC + suspend는 내부적으로 Mono bridge
//   완전한 non-blocking이 아닐 수 있음 (JDBC가 blocking이면 의미 반감)
//   진정한 non-blocking: R2DBC, WebClient, Lettuce(Redis) 사용 필요
```

---

### Q7: Virtual Thread vs Coroutine — 뭘 써야 하나?

```
[비교표]

특성              │ Virtual Thread        │ Kotlin Coroutine
─────────────────┼──────────────────────┼─────────────────────
추상화 수준       │ JVM 레벨 (Thread API) │ 언어 레벨 (suspend)
코드 스타일       │ 기존 blocking 코드 그대로│ suspend 함수 필요
학습 곡선        │ 낮음 (Thread와 동일)   │ 높음 (새로운 패러다임)
Structured       │ Java 21 Preview       │ 1.3부터 안정
Concurrency      │                       │
취소 (Cancel)    │ interrupt() 기반       │ 코루틴 취소 (cooperative)
백프레셔         │ 없음                  │ Flow + Channel
디버깅           │ 스택 트레이스 자연스러움│ 상태 머신이라 스택이 끊김
Spring 지원      │ Spring 6.1+           │ Spring 5.2+
생태계           │ 모든 Java 라이브러리    │ suspend 지원 라이브러리 필요

[선택 기준]
  "기존 Java 프로젝트, 코드 변경 최소화" → Virtual Thread
  "Kotlin 프로젝트, 세밀한 동시성 제어" → Coroutine
  "둘 다 가능한 상황" → Coroutine (더 풍부한 동시성 도구)
```

---

## 참고 자료

- JEP 444: Virtual Threads
- JEP 453: Structured Concurrency (Preview)
- Kotlin Coroutines Design Document — Roman Elizarov
- Spring Framework Reference: Coroutines Support
