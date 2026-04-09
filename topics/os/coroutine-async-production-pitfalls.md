# 코루틴과 비동기의 모든 것 Part 3 — 실무에서 터지는 것들과 해결 패턴

## 핵심 정리

비동기/코루틴을 도입하면 성능은 올라가지만, **새로운 종류의 버그와 장애**가 발생한다. 이 문서는 실무에서 실제로 터지는 문제들과 그 해결 패턴을 정리한다.

```
실무 비동기 장애 Top 5:
  1. 스레드풀/커넥션풀 고갈 (Blocking in async context)
  2. 예외 삼킴 (Fire-and-forget에서 에러 무시)
  3. 코루틴 누수 (취소 안 된 코루틴이 영원히 살아있음)
  4. 컨텍스트 유실 (MDC, 트랜잭션, 인증 정보 사라짐)
  5. 디버깅 불가 (스택 트레이스가 끊김)
```

---

## 헷갈렸던 포인트

---

### Q1: "Blocking in Non-blocking Context" — 가장 흔하고 치명적인 실수

```kotlin
// ❌ 재앙의 시작: Dispatchers.Default에서 Blocking I/O
suspend fun getUser(id: Long): User = withContext(Dispatchers.Default) {
    // Default는 CPU 코어 수만큼만 스레드!
    // JDBC는 Blocking I/O!
    // 4코어 서버 → 4개 스레드가 전부 DB 대기 → 모든 코루틴 멈춤
    jdbcTemplate.queryForObject("SELECT * FROM users WHERE id = ?", id)
}

// ✅ 해결 1: Dispatchers.IO 사용
suspend fun getUser(id: Long): User = withContext(Dispatchers.IO) {
    jdbcTemplate.queryForObject("SELECT * FROM users WHERE id = ?", id)
}

// ✅ 해결 2: 전용 Dispatcher (더 안전)
val dbDispatcher = Dispatchers.IO.limitedParallelism(32)
// → IO 풀에서 최대 32개만 DB 용으로 사용 (다른 IO 작업에 영향 없음)

suspend fun getUser(id: Long): User = withContext(dbDispatcher) {
    jdbcTemplate.queryForObject("SELECT * FROM users WHERE id = ?", id)
}

// ✅ 해결 3: 근본적 해결 — Non-blocking 드라이버 사용
// R2DBC (Reactive DB), Lettuce (Redis), WebClient (HTTP)
suspend fun getUser(id: Long): User {
    return r2dbcRepository.findById(id)  // 진짜 Non-blocking
        ?: throw UserNotFoundException(id)
}
```

```
[limitedParallelism으로 격리하는 이유]

상황: 외부 API가 3초씩 걸림

  Dispatchers.IO (64 스레드 공유):
    외부 API 호출 60개 → IO 스레드 60개 점유
    → DB 쿼리용 IO 스레드 4개만 남음
    → DB도 느려짐 → 전체 서비스 장애 (연쇄 반응)

  limitedParallelism으로 격리:
    val externalApiDispatcher = Dispatchers.IO.limitedParallelism(16)
    val dbDispatcher = Dispatchers.IO.limitedParallelism(32)

    → 외부 API가 아무리 느려도 16개만 점유
    → DB용 32개는 안전하게 보장
    → Bulkhead 패턴을 Dispatcher로 구현!
```

---

### Q2: 예외가 삼켜지는 5가지 패턴과 해결법

```kotlin
// ❌ 패턴 1: launch에서 예외 → 로그만 찍히고 묻힘
scope.launch {
    processOrder(orderId)  // 여기서 예외 터지면?
    // → CoroutineExceptionHandler 없으면 stderr에만 출력
    // → 호출한 쪽은 성공한 줄 앎
}

// ✅ 해결: CoroutineExceptionHandler 설치
val handler = CoroutineExceptionHandler { _, exception ->
    logger.error("Uncaught coroutine exception", exception)
    alertService.notify(exception)
}
scope.launch(handler) {
    processOrder(orderId)
}

// ❌ 패턴 2: async에서 예외 → await() 안 하면 영원히 묻힘
val deferred = scope.async {
    riskyOperation()  // 예외 발생!
}
// await()를 안 부르면 예외가 영원히 숨겨짐

// ✅ 해결: 반드시 await() 하거나 coroutineScope 사용
coroutineScope {
    val result = async { riskyOperation() }
    result.await()  // 여기서 예외 전파됨
}

// ❌ 패턴 3: CompletableFuture 체인에서 exceptionally 누락
CompletableFuture.supplyAsync(() -> riskyCall())
    .thenApply(result -> transform(result));
    // exceptionally 없음 → 예외가 Future 안에 갇힘
    // get() 안 하면 아무도 모름

// ✅ 해결
CompletableFuture.supplyAsync(() -> riskyCall())
    .thenApply(result -> transform(result))
    .whenComplete((result, ex) -> {
        if (ex != null) {
            logger.error("Pipeline failed", ex);
            metrics.increment("pipeline.error");
        }
    });

// ❌ 패턴 4: runBlocking 안에서 예외
fun handleRequest(): Response {
    return runBlocking {
        val data = async { fetchData() }  // 예외 발생
        val extra = async { fetchExtra() }
        Response(data.await(), extra.await())
        // data에서 예외 → extra도 취소 → runBlocking이 예외 던짐
        // 하지만 취소된 extra의 자원 정리는 됐나?
    }
}

// ✅ 해결: 명시적 정리
fun handleRequest(): Response {
    return runBlocking {
        coroutineScope {
            val data = async { fetchData() }
            val extra = async { fetchExtra() }
            Response(data.await(), extra.await())
        }
        // coroutineScope가 자식 전부 완료/취소 보장
    }
}

// ❌ 패턴 5: SupervisorJob에서 자식 예외 무시
val scope = CoroutineScope(SupervisorJob())
scope.launch { taskA() }  // 실패해도 taskB 계속
scope.launch { taskB() }
// 하지만 taskA 실패를 아무도 감지 못함!

// ✅ 해결: 각 자식에 개별 에러 처리
scope.launch {
    try { taskA() }
    catch (e: Exception) { errorReporter.report("taskA", e) }
}
```

---

### Q3: 코루틴 컨텍스트 유실 — MDC, 트랜잭션, 인증 정보

```kotlin
// ❌ 문제: 코루틴이 다른 스레드에서 실행되면 MDC(로그 추적 ID) 사라짐
@GetMapping("/orders/{id}")
suspend fun getOrder(@PathVariable id: Long): Order {
    MDC.put("traceId", UUID.randomUUID().toString())
    logger.info("요청 시작")  // traceId 있음

    val order = withContext(Dispatchers.IO) {
        logger.info("DB 조회")  // ❌ traceId 없음! 다른 스레드니까
        orderRepo.findById(id)
    }
    return order
}

// ✅ 해결: MDCContext 사용 (kotlinx-coroutines-slf4j)
@GetMapping("/orders/{id}")
suspend fun getOrder(@PathVariable id: Long): Order {
    MDC.put("traceId", UUID.randomUUID().toString())

    val order = withContext(Dispatchers.IO + MDCContext()) {
        logger.info("DB 조회")  // ✅ traceId 있음!
        orderRepo.findById(id)
    }
    return order
}

// ★ Spring Security 컨텍스트도 마찬가지
// ReactiveSecurityContextHolder 사용하거나
// SecurityCoroutineContext() 커스텀 구현 필요
```

```kotlin
// 실무 패턴: 커스텀 CoroutineContext 요소
class RequestContext(
    val traceId: String,
    val userId: Long,
    val permissions: Set<String>
) : AbstractCoroutineContextElement(RequestContext) {
    companion object Key : CoroutineContext.Key<RequestContext>
}

// 미들웨어/인터셉터에서 설정
suspend fun handleRequest(request: ServerRequest): ServerResponse {
    val context = RequestContext(
        traceId = request.headers().firstHeader("X-Trace-Id") ?: UUID.randomUUID().toString(),
        userId = extractUserId(request),
        permissions = extractPermissions(request)
    )

    return withContext(context + MDCContext()) {
        // 이후 모든 코루틴에서 접근 가능
        val ctx = coroutineContext[RequestContext]!!
        logger.info("Processing request for user ${ctx.userId}")
        orderService.process(request)
    }
}
```

---

### Q4: 코루틴 취소 — 제대로 안 하면 리소스 누수

```kotlin
// ❌ 취소를 무시하는 코루틴
suspend fun uploadLargeFile(file: File) {
    val chunks = file.readChunks()
    for (chunk in chunks) {
        // 취소 시그널을 확인하지 않음
        // 코루틴이 취소돼도 계속 업로드함!
        httpClient.upload(chunk)
    }
}

// ✅ 취소를 존중하는 코루틴
suspend fun uploadLargeFile(file: File) {
    val chunks = file.readChunks()
    for (chunk in chunks) {
        ensureActive()  // 취소됐으면 CancellationException 던짐
        httpClient.upload(chunk)
    }
}

// ★ suspend 함수 호출(yield, delay 등)은 자동으로 취소 확인
// ★ CPU-bound 루프에서는 ensureActive() 또는 yield() 명시 필요

// 취소 시 자원 정리
suspend fun processWithCleanup() {
    val resource = acquireResource()
    try {
        doWork(resource)
    } finally {
        // ★ 주의: finally에서 suspend 함수 호출 시
        // 이미 취소된 상태라 바로 CancellationException 발생
        withContext(NonCancellable) {
            resource.release()  // 취소 상태에서도 정리 보장
        }
    }
}
```

**타임아웃 실전 패턴:**

```kotlin
// withTimeout: 초과 시 CancellationException (자동 취소)
suspend fun fetchWithTimeout(): Data {
    return withTimeout(3.seconds) {
        externalApi.fetch()  // 3초 초과하면 취소
    }
}

// withTimeoutOrNull: 초과 시 null 반환 (예외 없음)
suspend fun fetchOrDefault(): Data {
    return withTimeoutOrNull(3.seconds) {
        externalApi.fetch()
    } ?: Data.DEFAULT  // 타임아웃이면 기본값

}

// 실무 패턴: 재시도 + 타임아웃 조합
suspend fun <T> retryWithBackoff(
    times: Int = 3,
    initialDelay: Duration = 100.milliseconds,
    maxDelay: Duration = 2.seconds,
    factor: Double = 2.0,
    block: suspend () -> T
): T {
    var currentDelay = initialDelay
    repeat(times - 1) { attempt ->
        try {
            return withTimeout(5.seconds) { block() }
        } catch (e: Exception) {
            if (e is CancellationException && e !is TimeoutCancellationException) throw e
            logger.warn("Attempt ${attempt + 1} failed: ${e.message}")
        }
        delay(currentDelay)
        currentDelay = (currentDelay * factor).coerceAtMost(maxDelay)
    }
    return withTimeout(5.seconds) { block() }  // 마지막 시도
}
```

---

### Q5: 디버깅 — 스택 트레이스가 끊기는 문제

```
[일반 스레드의 스택 트레이스]
java.lang.RuntimeException: DB error
  at OrderRepo.findById(OrderRepo.java:42)
  at OrderService.getOrder(OrderService.java:28)
  at OrderController.handleRequest(OrderController.java:15)
  → 명확하게 호출 경로가 보인다

[코루틴의 스택 트레이스 — 기본]
java.lang.RuntimeException: DB error
  at OrderRepo.findById(OrderRepo.kt:42)
  at OrderService$getOrder$2.invokeSuspend(OrderService.kt:28)
  at BaseContinuationImpl.resumeWith(ContinuationImpl.kt:33)
  → "누가 이 코루틴을 시작했는지" 안 보임!
```

```kotlin
// ✅ 해결 1: -Dkotlinx.coroutines.debug 플래그 (개발/스테이징)
// JVM 옵션에 추가
// → 코루틴 생성 스택 트레이스를 추가로 캡처
// → 성능 오버헤드 있어서 프로덕션 비추

// ✅ 해결 2: CoroutineName으로 추적
launch(CoroutineName("order-processing-${orderId}")) {
    // 로그에 코루틴 이름 표시됨
    processOrder(orderId)
}

// ✅ 해결 3: 구조화된 로깅 패턴
suspend fun processOrder(orderId: Long) {
    val ctx = coroutineContext
    logger.info(
        "Processing order",
        "orderId" to orderId,
        "coroutineName" to ctx[CoroutineName]?.name,
        "dispatcher" to ctx[ContinuationInterceptor]?.toString()
    )
}
```

---

### Q6: 실무 아키텍처 패턴 — 비동기를 어디에 적용하나?

```
[패턴 1: API 응답 시간 단축 — 병렬 조회]

Before (순차): 200ms + 150ms + 100ms = 450ms
After (병렬):  max(200, 150, 100) = 200ms

suspend fun getDashboard(userId: Long): Dashboard = coroutineScope {
    val profile = async { profileService.get(userId) }      // 200ms
    val orders = async { orderService.getRecent(userId) }    // 150ms
    val notifications = async { notificationService.get(userId) } // 100ms

    Dashboard(
        profile = profile.await(),
        orders = orders.await(),
        notifications = notifications.await()
    )
}
```

```
[패턴 2: 무거운 작업 비동기 분리 — 이메일/알림]

@Service
class OrderService(
    private val orderRepo: OrderRepository,
    private val notificationScope: CoroutineScope  // DI로 주입
) {
    @Transactional
    suspend fun createOrder(request: CreateOrderRequest): Order {
        val order = orderRepo.save(request.toEntity())

        // 알림은 비동기 (주문 생성과 무관하게)
        notificationScope.launch {
            try {
                emailService.sendOrderConfirmation(order)
                pushService.sendNotification(order.userId, "주문 완료!")
            } catch (e: Exception) {
                logger.error("알림 전송 실패 (주문은 성공)", e)
                // 알림 실패가 주문을 롤백시키면 안 됨!
            }
        }

        return order
    }
}

// ★ 주의: @Transactional과 코루틴
// - launch로 분리한 코루틴은 트랜잭션 범위 밖!
// - Outbox 패턴이 더 안전 (DB에 이벤트 저장 → 별도 폴러가 전송)
```

```
[패턴 3: 대량 데이터 처리 — Flow + 배치]

fun processAllUsers(): Flow<ProcessResult> = flow {
    userRepository.findAll()  // Flow<User> 반환 (스트리밍)
        .chunked(100)         // 100개씩 묶어서
        .collect { batch ->
            coroutineScope {
                val results = batch.map { user ->
                    async(dbDispatcher) {
                        processUser(user)
                    }
                }.awaitAll()

                results.forEach { emit(it) }
            }
        }
}
// → 100만 건을 메모리에 올리지 않고, 100건씩 병렬 처리
```

```
[패턴 4: Rate Limiting이 있는 외부 API 호출]

// Semaphore로 동시 요청 수 제한
val rateLimiter = Semaphore(10)  // 동시 10개까지만

suspend fun callExternalApi(request: ApiRequest): ApiResponse {
    rateLimiter.withPermit {
        return httpClient.post(request)
    }
}

// 1000개 요청을 동시 10개씩 제한하며 처리
suspend fun batchProcess(requests: List<ApiRequest>): List<ApiResponse> {
    return coroutineScope {
        requests.map { request ->
            async { callExternalApi(request) }
        }.awaitAll()
    }
    // 1000개 코루틴이 생기지만, Semaphore가 10개씩만 통과시킴
}
```

---

### Q7: 실무 체크리스트 — 비동기 도입 전 확인해야 할 것

```
[도입 전 체크리스트]

□ Blocking I/O 식별
  - JDBC? → Dispatchers.IO 또는 R2DBC 전환 검토
  - RestTemplate? → WebClient로 전환
  - Jedis(Redis)? → Lettuce로 전환

□ 스레드풀 격리 설계
  - DB용, 외부API용, CPU 연산용 Dispatcher 분리
  - limitedParallelism으로 영향 범위 제한

□ 에러 처리 전략
  - CoroutineExceptionHandler 전역 설정
  - 각 코루틴의 실패가 다른 코루틴에 미치는 영향 파악
  - 알림/모니터링 연동

□ 컨텍스트 전파
  - MDC (로그 추적) → MDCContext
  - Spring Security → SecurityCoroutineContext
  - 분산 추적 (OpenTelemetry) → 전파 설정 확인

□ 취소/타임아웃 정책
  - 모든 외부 호출에 타임아웃 설정
  - 취소 시 리소스 정리 (finally + NonCancellable)

□ 테스트
  - runTest { } 사용 (kotlinx-coroutines-test)
  - TestDispatcher로 시간 제어
  - 동시성 버그 재현용 테스트

□ 모니터링
  - 코루틴 수 메트릭 (kotlinx-coroutines-debug)
  - Dispatcher 스레드 사용률
  - 대기 중 코루틴 수 (큐 사이즈)
```

```
[최종 판단 플로우차트]

비동기 도입해야 하나?
  │
  ├─ I/O-bound인가? (DB, HTTP, File)
  │   ├─ Yes → 비동기 이점 있음
  │   │   ├─ Java 프로젝트 → Virtual Thread (가장 낮은 변경 비용)
  │   │   ├─ Kotlin 프로젝트 → Coroutine
  │   │   └─ 리액티브 전체 전환 가능 → WebFlux + Coroutine
  │   └─ No (CPU-bound) → 비동기 이점 없음
  │       └─ 병렬 처리 필요하면 → parallelStream 또는 ForkJoinPool
  │
  ├─ 단순히 느린 작업 분리? (이메일, 알림)
  │   └─ 메시지 큐 (Kafka, SQS)가 더 안정적
  │
  └─ 동시 요청 수 문제? (스레드 고갈)
      ├─ 즉시 해결 → Virtual Thread
      └─ 장기적 → Non-blocking 스택 전환
```

---

## 참고 자료

- Kotlin Coroutines Best Practices — Google Android Guide
- Effective Kotlin: Item 53 — Consider using coroutineScope
- Spring WebFlux + Coroutines Guide
- JEP 444: Virtual Threads — Pinning 이슈
- Structured Concurrency in Practice — Roman Elizarov (KotlinConf)
