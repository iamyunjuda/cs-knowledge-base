# 면접 실전 — "서비스 하나가 느립니다, 어떻게 해결하시겠습니까?"

## 핵심 정리

### 면접 시나리오

```
면접관: "한 API에서 호출하는 서비스가 여러 개 있는데,
         모니터링에서 하나가 너무 오래 걸리는 게 잡혔습니다.
         어떻게 해결하시겠습니까?"
```

이 질문에 "코루틴(비동기)으로 해결하겠습니다"라고 답하면, **면접관의 집요한 후속 질문**이 시작된다. 그 전체 흐름을 대비하자.

---

### 0단계: 문제 상황 파악 (먼저 물어봐야 할 것)

바로 "코루틴 쓰겠습니다"라고 답하면 안 된다. **먼저 상황을 파악**해야 한다.

```
"먼저 몇 가지 확인하고 싶습니다.

① 느린 서비스는 외부 API 호출인가, DB 쿼리인가?
② 느린 서비스의 결과가 다른 서비스의 입력으로 필요한가? (의존관계)
③ 느린 서비스의 결과가 API 응답에 반드시 포함되어야 하는가?
④ 현재 사용 중인 기술 스택은? (Spring MVC? WebFlux? Kotlin?)"
```

왜 중요한가:

```
상황별 해결책이 다르다:

[느린 서비스 결과가 응답에 필요 + 독립적]
  → 병렬 처리 (Coroutine async, CompletableFuture)
  → 전체 응답 시간 = max(A, B, C) (가장 느린 것)

[느린 서비스 결과가 응답에 불필요]
  → 비동기 분리 (@Async, 메시지 큐)
  → 응답은 먼저, 느린 작업은 백그라운드

[느린 서비스가 다른 서비스에 의존]
  → 병렬화 불가, 근본 원인 해결 필요
  → 캐싱, 쿼리 최적화, 타임아웃 설정
```

---

### 1단계: 구체적인 시나리오와 해결 방안

```
[상황 예시]
주문 상세 조회 API에서 3개 서비스를 순차 호출:

fun getOrderDetail(orderId: Long): OrderDetail {
    val order = orderService.getOrder(orderId)       // 50ms
    val payment = paymentService.getPayment(orderId)  // 2000ms ← 이게 느림!
    val delivery = deliveryService.getStatus(orderId) // 100ms

    return OrderDetail(order, payment, delivery)
}
// 총 소요: 50 + 2000 + 100 = 2150ms
```

#### 해결: 병렬 실행 (Coroutine)

```kotlin
// 세 서비스가 서로 독립적이면 → 병렬로 실행 가능
suspend fun getOrderDetail(orderId: Long): OrderDetail =
    coroutineScope {
        val order = async { orderService.getOrder(orderId) }       // 동시 시작
        val payment = async { paymentService.getPayment(orderId) } // 동시 시작
        val delivery = async { deliveryService.getStatus(orderId)} // 동시 시작

        OrderDetail(order.await(), payment.await(), delivery.await())
    }
// 총 소요: max(50, 2000, 100) = 2000ms (2150 → 2000)
// ★ 하지만 이건 150ms밖에 안 줄어듦 — 근본 해결이 아님!
```

```
"병렬화는 총 시간을 줄이지만, 가장 느린 서비스 자체가 2초면
 여전히 2초 걸립니다. 근본적으로는 왜 2초인지를 찾아야 합니다.

 하지만 서비스 자체를 최적화할 수 없는 상황이라면
 (예: 외부 결제 API가 원래 느린 것)
 병렬화로 전체 응답 시간을 줄이는 것이 유효합니다."
```

---

### 2단계: "코루틴 설정은 어떻게 하시죠?"

```
면접관: "코루틴을 쓰신다고 했는데, 설정은 어떻게 하시죠?"
```

#### Spring + Kotlin Coroutine 설정

```kotlin
// ① build.gradle.kts — 의존성 추가
dependencies {
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-reactor") // WebFlux 연동 시
}

// ② 별도 설정 파일이 필요하지 않음 (기본적으로)
// Kotlin Coroutine은 언어 레벨 기능이라 어노테이션이나 @Enable 불필요
// suspend 키워드를 쓰면 바로 사용 가능
```

```
"Coroutine은 Spring의 @Async와 달리 @EnableAsync 같은 별도 설정이 필요 없습니다.
 Kotlin 언어 자체의 기능이기 때문에 의존성만 추가하면 바로 suspend 함수를 쓸 수 있습니다.
 다만 Dispatcher(스레드 풀)를 커스터마이징하고 싶으면 별도 Bean을 만듭니다."
```

#### Dispatcher 커스터마이징 (필요 시)

```kotlin
// Dispatcher = "코루틴이 어떤 스레드에서 실행될지" 결정

// 기본 제공 Dispatcher:
Dispatchers.Default  // CPU 바운드 (코어 수만큼 스레드)
Dispatchers.IO       // I/O 바운드 (기본 64개, 확장 가능)
Dispatchers.Main     // UI 스레드 (Android)

// 커스텀 Dispatcher가 필요하면:
@Configuration
class CoroutineConfig {
    @Bean
    fun customDispatcher(): CoroutineDispatcher {
        return Executors.newFixedThreadPool(10).asCoroutineDispatcher()
    }
}
```

---

### 2.5단계: "코루틴 스코프를 어떻게 여세요?" — runBlocking을 말하면 안 되는 이유

```
면접관: "코루틴 스코프를 어떻게 여시죠?"
응시자: "runBlocking으로 엽니다"
면접관: (놀란 표정)
```

**왜 면접관이 놀랐는가:**

```
runBlocking은 "현재 스레드를 블로킹하면서 코루틴을 실행"하는 것.
이건 코루틴의 존재 이유를 정면으로 부정하는 사용법이다.

코루틴의 핵심: "스레드를 블로킹하지 않고 비동기 작업을 하는 것"
runBlocking: "스레드를 블로킹하면서 코루틴을 실행하는 것"
→ 모순!
```

```kotlin
// runBlocking의 실제 동작
fun main() {
    println("시작")

    runBlocking {          // ← 현재 스레드(main)가 여기서 멈춤
        delay(1000)        //    코루틴 내부에서 1초 대기
        println("코루틴")
    }                      // ← 코루틴 끝날 때까지 main 스레드 블로킹

    println("끝")          // 1초 후에야 실행됨
}
```

**runBlocking은 언제 쓰는 건가?**

```
✅ 올바른 사용처 (딱 2곳):
  ① main() 함수 — 프로그램 진입점에서 코루틴 세계로 들어갈 때
  ② 테스트 코드 — JUnit에서 suspend 함수를 호출할 때

  fun main() = runBlocking {  // 여기서만 OK
      launch { doWork() }
  }

  @Test
  fun testSomething() = runBlocking {  // 테스트에서 OK
      val result = myService.getData()
      assertEquals("expected", result)
  }

❌ 절대 쓰면 안 되는 곳:
  - Spring Controller
  - Spring Service
  - 이미 코루틴 안에 있는 곳
  → 스레드를 블로킹해서 코루틴의 의미가 없어짐
```

**그러면 Spring에서 코루틴 스코프를 어떻게 열어야 하나?**

```kotlin
// ★ 핵심: Spring WebFlux에서는 "스코프를 직접 열 필요가 없다"

// ✅ Controller를 suspend로 선언 → Spring이 알아서 코루틴 컨텍스트 생성
@GetMapping("/orders/{id}")
suspend fun getOrder(@PathVariable id: Long): OrderDetail {
    return orderService.getOrderDetail(id)
    // Spring WebFlux가 내부적으로 Mono.asCoroutine()으로 변환
    // 개발자가 runBlocking이나 CoroutineScope을 직접 만들 필요 없음
}

// ✅ Service에서 coroutineScope 사용 — 이건 "스코프를 여는" 게 아니라
//    "자식 코루틴의 범위를 정하는" 것
suspend fun getOrderDetail(id: Long): OrderDetail = coroutineScope {
    val order = async { getOrder(id) }
    val payment = async { getPayment(id) }
    OrderDetail(order.await(), payment.await())
}
```

```
면접에서 이렇게 답했어야 한다:

"코루틴 스코프는 직접 열지 않습니다.
 Spring WebFlux에서는 Controller의 suspend 함수를 선언하면
 Spring이 자동으로 코루틴 컨텍스트를 생성합니다.

 Service에서 병렬 실행이 필요할 때는 coroutineScope을 사용하는데,
 이건 '스코프를 새로 여는 것'이 아니라
 '자식 코루틴의 생명주기 범위를 정하는 것'입니다.

 runBlocking은 스레드를 블로킹하므로
 main() 함수나 테스트 코드에서만 사용해야 합니다."
```

---

### 2.6단계: "Controller는 일반 fun이고 Service만 suspend이면 되나요?"

```
면접관: "Controller는 그냥 fun으로 정의하고
         Service만 suspend 함수이면 되는 건가요?"
```

**안 된다.** suspend 함수는 suspend 함수 안에서만 호출할 수 있다.

```kotlin
// ❌ 컴파일 에러!
@RestController
class OrderController(private val orderService: OrderService) {

    @GetMapping("/orders/{id}")
    fun getOrder(@PathVariable id: Long): OrderDetail {
        return orderService.getOrderDetail(id)
        //     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        //     컴파일 에러: Suspend function 'getOrderDetail'
        //     should be called only from a coroutine or
        //     another suspend function
    }
}

class OrderService {
    suspend fun getOrderDetail(id: Long): OrderDetail = coroutineScope {
        // ...
    }
}
```

```
suspend 함수의 규칙:
  suspend 함수는 반드시 아래 중 하나에서만 호출 가능:
  ① 다른 suspend 함수 안
  ② 코루틴 빌더 안 (launch, async, runBlocking 등)

  일반 fun에서 suspend를 호출하면 → 컴파일 에러
```

**그러면 어떻게 해야 하나? 3가지 방법:**

```kotlin
// 방법 1: Controller도 suspend로 만든다 (WebFlux — 가장 깔끔)
@GetMapping("/orders/{id}")
suspend fun getOrder(@PathVariable id: Long): OrderDetail {
    return orderService.getOrderDetail(id)
    // suspend → suspend 호출이므로 OK
    // Spring WebFlux가 자동으로 코루틴 실행 환경을 만들어줌
}

// 방법 2: Service를 suspend가 아닌 일반 함수로 만든다 (MVC — 권장)
// Service 내부에서 코루틴을 캡슐화
@Service
class OrderService(private val customDispatcher: CoroutineDispatcher) {

    // ✅ 일반 fun — Controller가 suspend일 필요 없음
    fun getOrderDetail(id: Long): OrderDetail {
        return runBlocking(customDispatcher) {  // 여기서만 bridge
            val order = async { getOrder(id) }
            val payment = async { getPayment(id) }
            OrderDetail(order.await(), payment.await())
        }
    }
}

// Controller는 일반 fun
@GetMapping("/orders/{id}")
fun getOrder(@PathVariable id: Long): OrderDetail {
    return orderService.getOrderDetail(id)  // OK — 일반 fun
}
// ⚠️ 하지만 이러면 결국 runBlocking... → 차라리 CompletableFuture

// 방법 3: CompletableFuture로 변환 (MVC — 가장 실용적)
@Service
class OrderService {
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    fun getOrderDetailAsync(id: Long): CompletableFuture<OrderDetail> {
        return scope.async {
            coroutineScope {
                val order = async { getOrder(id) }
                val payment = async { getPayment(id) }
                OrderDetail(order.await(), payment.await())
            }
        }.asCompletableFuture()
    }
}
```

```
정리:

┌──────────────────────────────────────────────────────────┐
│              WebFlux                    MVC              │
│                                                          │
│  Controller: suspend fun ✅        Controller: fun ✅    │
│       ↓                                  ↓               │
│  Service: suspend fun ✅           Service: fun ✅       │
│  (coroutineScope 사용)              (CompletableFuture    │
│                                     또는 내부 runBlocking)│
│                                                          │
│  ★ suspend 체인이 자연스러움        ★ 코루틴보다          │
│  ★ 스레드 블로킹 없음               CompletableFuture가  │
│  ★ 코루틴 100% 활용                 더 자연스러움         │
└──────────────────────────────────────────────────────────┘

결론:
  WebFlux → Controller도 Service도 suspend → 코루틴 체인
  MVC → 코루틴 쓰지 말고 CompletableFuture → 더 깔끔
```

---

### 3단계: "Controller에서 코루틴을 쓰면 안 되나요?"

```
면접관: "왜 Service에서 코루틴 스코프를 여세요?
         Controller에서 하면 안 되나요?"
```

#### 답변: Controller에서도 가능하다. 하지만 어디서 여느냐는 관심사 분리의 문제다.

```kotlin
// ✅ Controller에서 suspend 함수 — Spring WebFlux에서는 자연스럽다
@RestController
class OrderController(private val orderService: OrderService) {

    @GetMapping("/orders/{id}")
    suspend fun getOrder(@PathVariable id: Long): OrderDetail {
        return orderService.getOrderDetail(id)
        // Controller가 suspend면 Spring이 Coroutine 컨텍스트를 알아서 생성
    }
}

// ✅ Service에서 coroutineScope 사용
class OrderService {
    suspend fun getOrderDetail(id: Long): OrderDetail = coroutineScope {
        val order = async { orderRepo.findById(id) }
        val payment = async { paymentClient.getPayment(id) }
        OrderDetail(order.await(), payment.await())
    }
}
```

```
"Controller에서 suspend를 쓰는 것 자체는 문제가 없습니다.
 Spring WebFlux는 Controller의 suspend 함수를 네이티브로 지원합니다.

 하지만 '어디서 병렬화할지'는 Service의 책임입니다.

 Controller는 '요청을 받고 응답을 보내는 것'이 역할이고,
 '어떤 서비스를 병렬로 호출할지'는 비즈니스 로직입니다.
 그래서 coroutineScope(병렬 실행 결정)는 Service에 두는 것이
 관심사 분리 측면에서 맞습니다."
```

#### Spring MVC (WebFlux가 아닌 경우) 주의점

```kotlin
// ⚠️ Spring MVC에서는 Controller가 suspend를 직접 지원하지 않음
// → runBlocking으로 감싸야 하는데, 이러면 Tomcat 스레드를 블로킹함

// ❌ Spring MVC + runBlocking (비추)
@RestController
class OrderController {
    @GetMapping("/orders/{id}")
    fun getOrder(@PathVariable id: Long): OrderDetail {
        return runBlocking {  // Tomcat 스레드가 여기서 블로킹됨!
            orderService.getOrderDetail(id)
        }
    }
}
// → Tomcat 스레드를 점유하면서 코루틴의 장점을 못 살림

// ✅ Spring MVC에서는 CompletableFuture가 더 자연스러움
@GetMapping("/orders/{id}")
fun getOrder(@PathVariable id: Long): CompletableFuture<OrderDetail> {
    return CoroutineScope(Dispatchers.IO).async {
        orderService.getOrderDetail(id)
    }.asCompletableFuture()
}
```

```
"Spring MVC를 쓰고 있다면 코루틴보다 CompletableFuture가
 더 자연스러운 선택입니다.

 Spring WebFlux를 쓰고 있다면 코루틴이 자연스럽고,
 Controller에서 suspend를 바로 쓸 수 있습니다.

 핵심은: 코루틴을 쓸 거면 WebFlux와 함께 써야 진짜 이점이 있고,
 Spring MVC에서 runBlocking으로 감싸면 Tomcat 스레드를
 블로킹하는 거라 코루틴의 장점이 없습니다."
```

---

### 4단계: "더 집요한 후속 질문들"

#### Q: "coroutineScope과 GlobalScope의 차이는?"

```kotlin
// ❌ GlobalScope — 생명주기 관리 안 됨
GlobalScope.launch {
    // 이 코루틴은 앱이 종료될 때까지 살아있음
    // 취소 불가, 메모리 누수 위험
}

// ✅ coroutineScope — Structured Concurrency
suspend fun doWork() = coroutineScope {
    val a = async { taskA() }
    val b = async { taskB() }
    // a 또는 b가 실패하면 나머지도 자동 취소
    // 이 함수가 끝나면 모든 자식 코루틴도 끝남
}

// "coroutineScope을 사용하면 부모-자식 관계가 형성되어
//  생명주기가 자동 관리됩니다. GlobalScope은
//  fire-and-forget이라 실무에서 쓰면 안 됩니다."
```

#### Q: "코루틴에서 예외가 발생하면 어떻게 되나요?"

```kotlin
// coroutineScope: 하나 실패 → 나머지 전부 취소
suspend fun getOrderDetail(id: Long) = coroutineScope {
    val order = async { getOrder(id) }
    val payment = async { getPayment(id) }  // 여기서 예외!

    // → order도 자동 취소
    // → coroutineScope이 예외를 위로 전파
    // → Controller까지 올라감 → @ControllerAdvice에서 처리 가능

    OrderDetail(order.await(), payment.await())
}

// supervisorScope: 하나 실패해도 나머지 계속 실행
suspend fun getOrderDetail(id: Long) = supervisorScope {
    val order = async { getOrder(id) }
    val payment = async { getPayment(id) }  // 여기서 예외!

    // → order는 계속 실행
    // → payment.await()에서 예외 발생 → 직접 try-catch 필요

    val orderResult = order.await()
    val paymentResult = try { payment.await() } catch (e: Exception) { null }

    OrderDetail(orderResult, paymentResult)
}
```

```
"필수 데이터면 coroutineScope (하나라도 실패하면 전체 실패),
 선택 데이터면 supervisorScope (실패해도 나머지는 성공)을 씁니다.
 예를 들어 결제 정보 조회 실패는 전체 실패시키지만,
 추천 상품 조회 실패는 빈 리스트로 대체할 수 있습니다."
```

#### Q: "코루틴이 실행되는 스레드는 어떤 건가요?"

```kotlin
suspend fun example() = coroutineScope {
    // Dispatchers.IO에서 실행 — I/O 전용 스레드풀
    val data = withContext(Dispatchers.IO) {
        httpClient.get("/api/data")  // 네트워크 I/O
    }

    // Dispatchers.Default에서 실행 — CPU 연산용
    val processed = withContext(Dispatchers.Default) {
        heavyComputation(data)  // CPU 바운드 작업
    }

    return@coroutineScope processed
}
```

```
"Dispatchers.IO는 I/O 작업용 스레드풀 (기본 64개),
 Dispatchers.Default는 CPU 작업용 (코어 수만큼) 입니다.
 withContext로 작업 성격에 맞는 Dispatcher를 지정합니다.

 중요한 건, 코루틴이 suspend 되면 스레드를 반환하고
 resume 될 때 다른 스레드에서 실행될 수 있다는 점입니다."
```

#### Q: "그럼 Spring MVC 환경이면 어떻게 하시겠어요?"

```
"Spring MVC 환경이면 코루틴 대신 CompletableFuture를 쓰겠습니다."
```

```java
// Spring MVC + CompletableFuture (Java)
@Service
public class OrderService {

    @Autowired
    private Executor asyncExecutor;  // ThreadPoolTaskExecutor

    public OrderDetail getOrderDetail(Long id) {
        var orderF = CompletableFuture.supplyAsync(
            () -> orderRepo.findById(id), asyncExecutor);
        var paymentF = CompletableFuture.supplyAsync(
            () -> paymentClient.getPayment(id), asyncExecutor);
        var deliveryF = CompletableFuture.supplyAsync(
            () -> deliveryService.getStatus(id), asyncExecutor);

        CompletableFuture.allOf(orderF, paymentF, deliveryF).join();

        return new OrderDetail(
            orderF.join(), paymentF.join(), deliveryF.join()
        );
    }
}
```

```
"핵심은 코루틴이냐 CompletableFuture냐가 아니라,
 독립적인 작업을 병렬로 실행해서 총 소요 시간을 줄이는 것입니다.
 기술 스택에 맞는 도구를 선택하면 됩니다."
```

---

### 면접 답변 전체 흐름 요약

```
1. 상황 파악 질문 (30초)
   "느린 서비스는 외부 API인가요? 결과가 응답에 필요한가요?"

2. 해결 방안 제시 (1분)
   "독립적이면 병렬 실행, 응답에 불필요하면 비동기 분리"

3. 구체적 구현 (2분)
   Coroutine: coroutineScope + async/await
   또는 Java: CompletableFuture.supplyAsync

4. 설정 설명 (1분)
   "의존성만 추가. Dispatcher는 기본값 사용하거나 커스텀"

5. Controller vs Service (1분)
   "병렬화 결정은 Service의 책임.
    WebFlux면 Controller도 suspend 가능.
    Spring MVC면 CompletableFuture가 자연스러움."

6. 트레이드오프 (30초)
   "병렬화는 최대값으로 줄이는 것.
    근본 원인(슬로우 쿼리, 느린 API)도 함께 해결해야."
```

## 헷갈렸던 포인트

### Q1. "MVC에서 코루틴 써도 결국 Tomcat 스레드는 잡히는 거 아닌가요?"

**맞다. 정확한 지적이다.** 이것이 Spring MVC + Coroutine의 핵심 한계.

```
[Spring MVC에서 코루틴을 쓸 때 실제로 일어나는 일]

Tomcat Thread-1:
├── 요청 수신
├── Controller 진입
├── runBlocking {                    ← ★ Tomcat 스레드가 여기서 블로킹!
│     coroutineScope {
│       async(IO) { getOrder() }     → IO 스레드풀에서 실행
│       async(IO) { getPayment() }   → IO 스레드풀에서 실행
│       async(IO) { getDelivery() }  → IO 스레드풀에서 실행
│
│       ↓ 세 작업이 IO 스레드에서 병렬로 실행되는 동안
│       ↓ Tomcat Thread-1은 여기서 대기 중... (아무것도 안 함)
│
│       await(), await(), await()    → 결과 수집
│     }
│   }                                ← 여기서 풀림
├── 응답 반환
└── Tomcat Thread-1 반납

★ 코루틴 덕분에 3개 작업은 병렬로 실행됨 → 총 시간 단축 ✅
★ 하지만 Tomcat 스레드는 전체 시간 동안 잡혀 있음 ❌
```

```
그러면 코루틴의 이점이 뭔가?

[코루틴 없이 순차 실행]
Tomcat Thread-1: ────Order(50ms)────Payment(2000ms)────Delivery(100ms)────
                                                              총 2150ms 점유

[코루틴으로 병렬 실행]
Tomcat Thread-1: ────runBlocking(2000ms)────
IO Thread-1:     ────Order(50ms)──
IO Thread-2:     ────Payment(2000ms)──────
IO Thread-3:     ────Delivery(100ms)───
                              총 2000ms 점유

★ Tomcat 스레드 점유 시간: 2150ms → 2000ms (줄긴 줌)
★ 하지만 여전히 Tomcat 스레드 1개를 2초 동안 잡고 있음
★ 동시 요청 200개 넘으면 → Tomcat 스레드 고갈 → 같은 문제
```

**면접에서 이렇게 답하면 좋다:**

```
"맞습니다. Spring MVC에서는 코루틴을 써도
 Tomcat 스레드가 응답 완료까지 점유됩니다.

 코루틴의 이점은 '여러 I/O 작업을 병렬로 실행해서
 총 대기 시간을 줄이는 것'이지,
 'Tomcat 스레드를 해방하는 것'이 아닙니다.

 Tomcat 스레드까지 해방하려면 두 가지 방법이 있습니다:

 ① Spring WebFlux로 전환
    → Controller가 suspend를 직접 지원
    → Tomcat 스레드 대신 Event Loop 사용
    → 스레드 블로킹 없음

 ② Spring MVC + DeferredResult/Callable
    → 요청 처리를 별도 스레드로 넘기고 Tomcat 스레드 즉시 반환
    → 하지만 별도 스레드가 필요하므로 근본 해결은 아님

 결국 '스레드를 점유하지 않는 진짜 비동기'를 원하면
 WebFlux가 답이고, MVC에서 코루틴은
 '병렬화를 통한 응답 시간 단축'에 의미가 있습니다."
```

```
[정리: MVC에서 코루틴의 가치]

                        순차 실행    코루틴 병렬    WebFlux+코루틴
Tomcat 스레드 점유 시간   2150ms      2000ms        0ms (논블로킹)
응답 시간                2150ms      2000ms        2000ms
스레드 효율              ❌ 낭비      ❌ 여전히 점유  ✅ 스레드 해방

★ MVC + 코루틴 = "응답 시간 단축"에는 의미 있음
★ MVC + 코루틴 ≠ "스레드 효율 개선"
★ 스레드 효율까지 원하면 = WebFlux
```

#### 그러면 MVC에서 CompletableFuture도 같은 문제 아닌가?

```java
// 맞다. CompletableFuture도 .join()하는 순간 Tomcat 스레드 블로킹.
var result = CompletableFuture.allOf(f1, f2, f3).join();  // 여기서 블로킹

// MVC의 Thread-per-Request 모델에서는 피할 수 없는 한계.
// 이건 코루틴의 문제가 아니라 "MVC 모델 자체의 특성".
```

---

### Q1-1. "코루틴을 쓴다 = WebFlux를 써야 한다"인가?

**아니다.** 하지만 **WebFlux와 쓸 때 가장 효과적**이다.

```
Spring MVC + Coroutine:
  → 가능하지만 runBlocking이 필요한 경우 있음
  → Tomcat 스레드 블로킹 → 코루틴 장점 반감
  → CompletableFuture가 더 자연스러움

Spring WebFlux + Coroutine:
  → suspend 함수를 네이티브 지원
  → 스레드 블로킹 없음
  → 코루틴의 장점을 100% 활용

결론: MVC면 CompletableFuture, WebFlux면 Coroutine
```

### Q2. 면접에서 "왜 코루틴을 선택했나요?"라고 물어보면?

```
"세 가지 이유입니다.

① 가독성: CompletableFuture의 콜백 체이닝보다
   suspend 함수가 동기 코드처럼 읽힙니다.

② Structured Concurrency: 부모-자식 관계로
   생명주기가 자동 관리되어 리소스 누수가 없습니다.

③ 경량성: OS 스레드보다 훨씬 가벼워서
   수만 개를 동시에 실행할 수 있습니다.

다만 팀이 Java 기반이거나 Spring MVC를 쓰고 있다면
CompletableFuture를 선택하겠습니다.
도구는 팀과 기술 스택에 맞춰야 합니다."
```

### Q3. 이 문제에서 "코루틴"이 아닌 다른 답은 없나?

코루틴/CompletableFuture 외에도 여러 접근이 있다:

```
① 병렬 실행 (이 문서의 주제)
   → Coroutine async, CompletableFuture

② 캐싱
   → 느린 서비스 결과를 Redis에 캐시
   → 2초 → 수 ms로 단축

③ 비동기 분리
   → 느린 작업을 메시지 큐(Kafka)로 보내고 응답은 먼저
   → "결제 조회 중입니다" 상태로 응답

④ 타임아웃 + 폴백
   → 느린 서비스에 500ms 타임아웃 설정
   → 타임아웃 시 캐시된 이전 데이터 반환

⑤ 근본 원인 해결
   → 느린 쿼리 최적화, 인덱스 추가
   → 외부 API라면 벌크 호출, 배치 처리

면접에서는 "코루틴으로 병렬화하겠습니다" 한 가지만 답하지 말고,
여러 선택지를 제시하고 상황에 맞는 것을 고르는 모습을 보여주는 것이 좋다.
```

## 참고 자료

- [Kotlin Coroutines — Structured Concurrency](https://kotlinlang.org/docs/coroutines-basics.html#structured-concurrency)
- [Spring WebFlux — Kotlin Coroutines Support](https://docs.spring.io/spring-framework/reference/languages/kotlin/coroutines.html)
- [Spring MVC vs WebFlux 선택 기준](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html)
