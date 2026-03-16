---
title: "면접 실전 — 서비스 하나가 느릴 때 코루틴/비동기 해결 전략"
parent: Spring
nav_order: 5
---

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
// ★ 핵심: Spring MVC 5.3+ / WebFlux 둘 다 "스코프를 직접 열 필요가 없다"

// ✅ Controller를 suspend로 선언 → Spring이 알아서 코루틴 컨텍스트 생성
@GetMapping("/orders/{id}")
suspend fun getOrder(@PathVariable id: Long): OrderDetail {
    return orderService.getOrderDetail(id)
    // Spring이 내부적으로 suspend → Mono로 변환하여 비동기 처리
    // 개발자가 runBlocking이나 CoroutineScope을 직접 만들 필요 없음
    // ★ MVC 5.3+ (Boot 2.4+)에서도 동일하게 동작!
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
 Spring MVC 5.3+ / WebFlux 모두 Controller의 suspend 함수를 선언하면
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

**그러면 어떻게 해야 하나?**

```kotlin
// ★ Spring MVC 5.3+ 부터 Controller에서 suspend fun을 네이티브 지원!
// ★ runBlocking 필요 없음!

// ✅ Controller — suspend fun (Spring MVC 5.3+ / Spring Boot 2.4+)
@RestController
class OrderController(private val orderService: OrderService) {

    @GetMapping("/orders/{id}")
    suspend fun getOrder(@PathVariable id: Long): OrderDetail {
        return orderService.getOrderDetail(id)
        // Spring MVC가 내부적으로 suspend → Mono로 변환하여 비동기 처리
        // runBlocking 불필요!
    }
}

// ✅ Service — suspend fun
@Service
class OrderService {
    suspend fun getOrderDetail(id: Long): OrderDetail = coroutineScope {
        val order = async { orderRepo.findById(id) }
        val payment = async { paymentClient.getPayment(id) }
        OrderDetail(order.await(), payment.await())
    }
}
```

```
★ 이전 답변에서 "MVC는 suspend를 지원하지 않는다"고 했는데 이건 틀렸다!
★ Spring Framework 5.3 (Spring Boot 2.4) 부터 MVC에서도 suspend를 네이티브 지원
★ 내부적으로 suspend 함수를 Mono로 변환 → MVC의 비동기 요청 처리 활용

필요한 의존성:
  - kotlinx-coroutines-core
  - kotlinx-coroutines-reactor  ← ★ 이게 있어야 suspend → Mono 변환이 됨
```

---

### 2.7단계: Spring MVC + Coroutine — 실제로 가능하다! (정정)

```
이전에 "MVC에서 코루틴은 어색하다, CompletableFuture를 써라"라고 했는데,
Spring 5.3부터 상황이 바뀌었다.
```

#### MVC에서 suspend fun이 동작하는 원리

```
Spring MVC가 suspend fun을 감지하면:

@GetMapping("/orders/{id}")
suspend fun getOrder(id: Long): OrderDetail { ... }

내부적으로 이렇게 변환됨:

① Spring이 KotlinDetector로 suspend 함수 감지
② suspend 함수를 Mono<OrderDetail>로 변환 (coroutines-reactor 사용)
③ Spring MVC의 비동기 요청 처리(DeferredResult와 동일한 메커니즘) 활용
④ Tomcat 스레드를 반환하고, 코루틴 완료 시 응답 전송

[실제 흐름]
Tomcat Thread-1: 요청 수신 → suspend fun 감지 → Mono로 변환 → 스레드 반환!
Coroutine (IO):  suspend fun 실행 → 병렬 처리 → 완료
Tomcat Thread-N: Mono 완료 신호 수신 → 응답 전송

★ Tomcat 스레드가 블로킹되지 않는다!
★ WebFlux가 아니어도!
★ runBlocking도 필요 없다!
```

#### 올바른 MVC + Coroutine 패턴

```kotlin
// ═══════════════════════════════════════════════════════
// ✅ 방법 1: Controller suspend + Service suspend (가장 깔끔 — 추천)
// ═══════════════════════════════════════════════════════

@RestController
class OrderController(private val orderService: OrderService) {

    @GetMapping("/orders/{id}")
    suspend fun getOrder(@PathVariable id: Long): OrderDetail {
        return orderService.getOrderDetail(id)
    }
}

@Service
class OrderService(private val webClient: WebClient) {

    suspend fun getOrderDetail(id: Long): OrderDetail = coroutineScope {
        val order = async { getOrder(id) }
        val payment = async { getPayment(id) }
        val delivery = async { getDelivery(id) }

        OrderDetail(order.await(), payment.await(), delivery.await())
    }

    private suspend fun getPayment(id: Long): Payment {
        // WebClient의 suspend 확장 함수 사용 (non-blocking I/O)
        return webClient.get()
            .uri("/payments/$id")
            .retrieve()
            .awaitBody()  // ← suspend 확장 함수 (kotlinx-coroutines-reactor)
    }
}

// ★ runBlocking 없음
// ★ Controller도 Service도 suspend
// ★ WebClient + awaitBody()로 진짜 non-blocking I/O
// ★ Spring MVC 5.3+에서 완벽 동작
```

```kotlin
// ═══════════════════════════════════════════════════════
// ✅ 방법 2: CompletableFuture (코루틴 안 쓸 때)
// ═══════════════════════════════════════════════════════

@Service
class OrderService(
    @Qualifier("asyncExecutor") private val executor: Executor
) {
    fun getOrderDetail(id: Long): OrderDetail {
        val orderF = CompletableFuture.supplyAsync(
            { orderRepo.findById(id) }, executor)
        val paymentF = CompletableFuture.supplyAsync(
            { paymentClient.getPayment(id) }, executor)

        CompletableFuture.allOf(orderF, paymentF).join()

        return OrderDetail(orderF.join(), paymentF.join())
    }
}

// ★ 코루틴 없이도 병렬 처리 가능
// ★ JDBC 등 블로킹 I/O만 쓰는 프로젝트에서는 이게 더 현실적
```

#### 그러면 "runBlocking + async + WebClient" 패턴은 뭔가?

```kotlin
// 이런 패턴이 실무에서 돌아다니긴 한다:
@GetMapping("/orders/{id}")
fun getOrder(@PathVariable id: Long): OrderDetail {
    return runBlocking {
        val order = async { webClient.get().uri("/orders/$id").retrieve().awaitBody<Order>() }
        val payment = async { webClient.get().uri("/payments/$id").retrieve().awaitBody<Payment>() }
        OrderDetail(order.await(), payment.await())
    }
}

// 이건 "동작은 하지만 비효율적인" 패턴이다:
//
// ① runBlocking이 Tomcat 스레드를 블로킹함
// ② 그 안에서 async로 WebClient(non-blocking I/O) 병렬 실행
// ③ 병렬 실행의 이점은 있음 (총 시간 = max(A, B))
// ④ 하지만 Tomcat 스레드는 잡혀 있음
//
// ★ 안티패턴이 아니라 "차선책"
// ★ Spring 5.3 이전에는 이게 유일한 방법이었음
// ★ 5.3 이후에는 Controller를 suspend fun으로 바꾸면 runBlocking 불필요
```

```
정리: MVC + 코루틴의 시대별 변화

Spring 5.3 이전:
  MVC Controller = 일반 fun만 가능
  → 코루틴 쓰려면 runBlocking 필수 (차선책)
  → "MVC에서 코루틴은 어색하다"가 맞는 말이었음

Spring 5.3 이후 (Spring Boot 2.4+):
  MVC Controller = suspend fun 네이티브 지원!
  → runBlocking 불필요
  → Controller suspend → Service suspend → 자연스러운 코루틴 체인
  → Tomcat 스레드 블로킹 없음 (내부적으로 Mono 변환)

★ "MVC에서 코루틴이 안 된다"는 옛날 이야기
★ 현재는 MVC에서도 코루틴이 1급 시민(first-class citizen)
```

```
면접에서 이렇게 답하면 좋다:

"Spring MVC 5.3부터 Controller에서 suspend fun을 네이티브 지원합니다.
 내부적으로 suspend를 Mono로 변환하고 Servlet 비동기 처리를 활용하여
 Tomcat 스레드를 블로킹하지 않습니다.

 Kotlin 프로젝트라면 MVC에서도 코루틴을 자연스럽게 쓸 수 있습니다.
 Controller를 suspend fun으로 선언하고,
 Service에서 coroutineScope + async로 병렬 처리합니다.
 runBlocking은 필요 없습니다.

 Java 프로젝트라면 CompletableFuture.supplyAsync로
 병렬 호출하는 것이 자연스럽습니다.

 핵심은 기술 스택(Kotlin/Java)에 맞는 도구를 선택하는 것입니다."
```

---

### 3단계: "Controller에서 코루틴을 쓰면 안 되나요?"

```
면접관: "왜 Service에서 코루틴 스코프를 여세요?
         Controller에서 하면 안 되나요?"
```

#### 답변: Controller에서도 가능하다. 하지만 어디서 여느냐는 관심사 분리의 문제다.

```kotlin
// ✅ Controller에서 suspend 함수 — MVC 5.3+ / WebFlux 모두 자연스럽다
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
 Spring MVC 5.3+ / WebFlux 모두 Controller의 suspend 함수를 네이티브로 지원합니다.

 하지만 '어디서 병렬화할지'는 Service의 책임입니다.

 Controller는 '요청을 받고 응답을 보내는 것'이 역할이고,
 '어떤 서비스를 병렬로 호출할지'는 비즈니스 로직입니다.
 그래서 coroutineScope(병렬 실행 결정)는 Service에 두는 것이
 관심사 분리 측면에서 맞습니다."
```

#### Spring MVC 5.3+ 에서의 동작 (정정!)

```
★ 이전에 "MVC에서는 suspend를 지원하지 않아서 runBlocking이 필요하다"고 했는데
★ 이건 Spring 5.3 이전의 이야기다!
★ Spring MVC 5.3+ (Spring Boot 2.4+)부터 suspend fun을 네이티브 지원한다.
```

```kotlin
// ✅ Spring MVC 5.3+ — Controller suspend fun 네이티브 지원!
@RestController
class OrderController(private val orderService: OrderService) {

    @GetMapping("/orders/{id}")
    suspend fun getOrder(@PathVariable id: Long): OrderDetail {
        return orderService.getOrderDetail(id)
        // Spring MVC가 suspend → Mono로 변환 → 비동기 요청 처리
        // runBlocking 불필요!
    }
}

// ★ MVC도 WebFlux도 Controller에서 suspend fun을 쓸 수 있다
// ★ 차이점은 "스레드 모델"에 있다 (아래 Q1에서 상세 설명)
```

```
"Spring MVC 5.3부터 Controller에서 suspend fun을 네이티브 지원합니다.
 내부적으로 suspend 함수를 Mono로 변환하여 비동기 요청 처리를 합니다.

 다만 MVC와 WebFlux의 차이는 여전히 존재합니다:
 - MVC: suspend 중에도 Servlet 비동기 처리 (AsyncContext) 활용
 - WebFlux: Netty Event Loop 기반 완전한 논블로킹

 두 경우 모두 Tomcat/Netty 스레드를 블로킹하지 않습니다."
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

**⚠️ 위 supervisorScope 코드의 문제: 예외가 조용히 삼켜진다!**

```kotlin
// ❌ 위 코드에서 실제로 일어나는 일:
val paymentResult = try {
    payment.await()
} catch (e: Exception) {
    null  // 예외를 잡고 null 반환 — 로그 없음, 알림 없음!
}

// 결과:
// - 클라이언트는 200 OK + OrderDetail(order=정상, payment=null) 수신
// - 서버 로그에 아무것도 안 남음
// - payment 조회가 실패했는지 아무도 모름
// - 장애가 조용히 묻힘!
```

**✅ 실무에서는 반드시 로깅 + 의미 있는 폴백을 해야 한다:**

```kotlin
suspend fun getOrderDetail(id: Long) = supervisorScope {
    val order = async { getOrder(id) }
    val payment = async { getPayment(id) }
    val recommendation = async { getRecommendation(id) }

    val orderResult = order.await()  // 필수 — 실패하면 그대로 예외 전파

    // 선택 데이터 — 실패해도 폴백
    val paymentResult = try {
        payment.await()
    } catch (e: Exception) {
        log.error("결제 정보 조회 실패 - orderId: {}", id, e)  // ★ 반드시 로깅
        PaymentInfo.unknown()  // null 대신 의미 있는 기본값
    }

    val recommendationResult = try {
        recommendation.await()
    } catch (e: Exception) {
        log.warn("추천 조회 실패 - orderId: {}", id, e)
        emptyList()  // 빈 리스트로 폴백
    }

    OrderDetail(orderResult, paymentResult, recommendationResult)
}
```

```
실제 응답 비교:

[예외 삼키기 — ❌]
{
  "order": { "id": 1, "amount": 50000 },
  "payment": null,                        ← 왜 null인지 모름
  "recommendation": null
}

[로깅 + 의미 있는 폴백 — ✅]
{
  "order": { "id": 1, "amount": 50000 },
  "payment": { "status": "UNKNOWN" },     ← 조회 실패를 명시
  "recommendation": []                    ← 빈 배열 (정상 구조 유지)
}

+ 서버 로그:
  ERROR - 결제 정보 조회 실패 - orderId: 1 - ConnectionTimeoutException: ...
  WARN  - 추천 조회 실패 - orderId: 1 - ServiceUnavailableException: ...
```

```
정리: supervisorScope에서 catch 할 때의 3원칙

① 반드시 로깅 (log.error / log.warn)
   → 예외가 삼켜지면 장애 원인을 찾을 수 없다

② null 대신 의미 있는 기본값 반환
   → PaymentInfo.unknown(), emptyList(), default 객체
   → 클라이언트가 null 체크를 안 해도 되게

③ 필수 데이터는 catch하지 말기
   → order 조회 실패는 전체를 실패시켜야 함
   → catch 없이 그대로 예외 전파 → @ControllerAdvice에서 처리
```

```
"필수 데이터면 coroutineScope (하나라도 실패하면 전체 실패),
 선택 데이터면 supervisorScope (실패해도 나머지는 성공)을 씁니다.
 예를 들어 결제 정보 조회 실패는 전체 실패시키지만,
 추천 상품 조회 실패는 빈 리스트로 대체할 수 있습니다.
 단, 예외를 잡을 때는 반드시 로깅하고 의미 있는 기본값을 반환해야 합니다."
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

**Kotlin이면 코루틴, Java이면 CompletableFuture.**

```kotlin
// ✅ Spring MVC 5.3+ (Kotlin) — suspend fun으로 코루틴 사용 가능!
@RestController
class OrderController(private val orderService: OrderService) {

    @GetMapping("/orders/{id}")
    suspend fun getOrder(@PathVariable id: Long): OrderDetail {
        return orderService.getOrderDetail(id)
        // Tomcat 스레드 블로킹 없음, runBlocking 불필요
    }
}

@Service
class OrderService {
    suspend fun getOrderDetail(id: Long): OrderDetail = coroutineScope {
        val order = async(Dispatchers.IO) { orderRepo.findById(id) }
        val payment = async(Dispatchers.IO) { paymentClient.getPayment(id) }
        val delivery = async(Dispatchers.IO) { deliveryService.getStatus(id) }
        OrderDetail(order.await(), payment.await(), delivery.await())
    }
}
```

```java
// ✅ Spring MVC (Java) — CompletableFuture
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

 Spring MVC 5.3+에서는 Kotlin이면 코루틴, Java이면 CompletableFuture.
 둘 다 MVC에서 잘 동작합니다."
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
    MVC 5.3+ / WebFlux 모두 Controller suspend 가능.
    Kotlin이면 코루틴, Java이면 CompletableFuture."

6. 트레이드오프 (30초)
   "병렬화는 최대값으로 줄이는 것.
    근본 원인(슬로우 쿼리, 느린 API)도 함께 해결해야."
```

## 헷갈렸던 포인트

### Q1. "MVC에서 코루틴 써도 결국 Tomcat 스레드는 잡히는 거 아닌가요?"

**Spring 5.3 이전에는 맞았지만, 5.3 이후에는 아니다!**

```
[Spring MVC 5.3 이전 — runBlocking 시절]

Tomcat Thread-1:
├── 요청 수신
├── Controller 진입
├── runBlocking {                    ← ★ Tomcat 스레드가 여기서 블로킹!
│     coroutineScope {
│       async(IO) { getOrder() }     → IO 스레드풀에서 실행
│       async(IO) { getPayment() }   → IO 스레드풀에서 실행
│     }
│   }                                ← 여기서 풀림
├── 응답 반환
└── Tomcat Thread-1 반납

★ runBlocking 때문에 Tomcat 스레드가 잡혀 있었음 ❌
```

```
[Spring MVC 5.3+ — suspend fun 네이티브 지원]

Tomcat Thread-1:
├── 요청 수신
├── Controller suspend fun 감지
├── suspend → Mono 변환 (kotlinx-coroutines-reactor)
├── AsyncContext 시작 → Tomcat 스레드 반환! ★
└── (Tomcat Thread-1은 다른 요청 처리 가능)

Coroutine (IO Dispatcher):
├── coroutineScope {
│     async { getOrder() }
│     async { getPayment() }
│   }
└── 완료 → Mono 완료 신호

Tomcat Thread-N:
├── Mono 완료 신호 수신
├── 응답 전송
└── 스레드 반환

★ Tomcat 스레드가 블로킹되지 않는다!
★ MVC의 Servlet 3.0 비동기 처리(AsyncContext) 활용
★ runBlocking도 필요 없다!
```

**MVC vs WebFlux — 코루틴 사용 시 차이:**

```
                        MVC 5.3+ (suspend)   WebFlux (suspend)
Tomcat 스레드 블로킹       ❌ 안 함            ❌ 안 함
내부 메커니즘             AsyncContext         Netty Event Loop
suspend → 변환           Mono (reactor)       Mono (reactor)
스레드 모델              Thread Pool          Event Loop
I/O 방식                블로킹 I/O도 가능      반드시 non-blocking I/O
코루틴 효과              ✅ 병렬화 + 스레드 반환  ✅ 병렬화 + 완전 논블로킹

★ 둘 다 Tomcat/Netty 스레드를 블로킹하지 않음
★ 차이는 "I/O 모델" — MVC는 블로킹 I/O도 허용, WebFlux는 논블로킹만
```

**⚠️ 주의: MVC에서 블로킹 I/O를 쓰면?**

```kotlin
// MVC 5.3+ suspend Controller에서 블로킹 I/O를 쓰는 경우:
@GetMapping("/orders/{id}")
suspend fun getOrder(@PathVariable id: Long): OrderDetail = coroutineScope {
    val order = async(Dispatchers.IO) {
        jdbcTemplate.query(...)  // ← 블로킹 I/O (JDBC)
    }
    val payment = async(Dispatchers.IO) {
        restTemplate.getForObject(...)  // ← 블로킹 I/O (RestTemplate)
    }
    OrderDetail(order.await(), payment.await())
}

// Tomcat 스레드는 반환됨 ✅
// 하지만 Dispatchers.IO 스레드가 블로킹됨
// → IO 스레드풀 크기(기본 64)가 한계
// → 완전한 논블로킹을 원하면 WebClient + awaitBody() 사용

// ★ 그래도 "Tomcat 스레드 고갈"은 방지됨 — 이것만으로도 큰 이점!
```

**면접에서 이렇게 답하면 좋다:**

```
"Spring MVC 5.3부터 Controller에서 suspend fun을 네이티브 지원합니다.
 내부적으로 suspend를 Mono로 변환하고, Servlet 비동기 처리를 활용하여
 Tomcat 스레드를 블로킹하지 않습니다.

 다만 JDBC 같은 블로킹 I/O를 쓰면 IO Dispatcher 스레드가 블로킹됩니다.
 이건 MVC의 한계가 아니라 JDBC의 한계입니다.

 완전한 논블로킹을 원하면:
 ① WebClient + awaitBody()로 non-blocking I/O 사용
 ② R2DBC로 논블로킹 DB 드라이버 사용
 ③ 또는 WebFlux로 전환

 핵심은: MVC 5.3+에서 suspend fun만으로도
 Tomcat 스레드 고갈 문제는 해결됩니다."
```

#### 그러면 MVC에서 CompletableFuture도 같은 효과인가?

```java
// CompletableFuture도 MVC의 비동기 반환 타입으로 지원됨
@GetMapping("/orders/{id}")
public CompletableFuture<OrderDetail> getOrder(@PathVariable Long id) {
    var orderF = CompletableFuture.supplyAsync(() -> orderRepo.findById(id), executor);
    var paymentF = CompletableFuture.supplyAsync(() -> paymentClient.getPayment(id), executor);

    return CompletableFuture.allOf(orderF, paymentF)
        .thenApply(v -> new OrderDetail(orderF.join(), paymentF.join()));
    // ★ CompletableFuture를 반환하면 MVC가 비동기로 처리
    // ★ Tomcat 스레드를 블로킹하지 않음 (DeferredResult와 동일 메커니즘)
    // ★ 단, .join()으로 결과를 동기적으로 꺼내면 해당 스레드 블로킹!
}
```

---

### Q1-1. "코루틴을 쓴다 = WebFlux를 써야 한다"인가?

**아니다.** Spring MVC 5.3+에서도 코루틴을 잘 쓸 수 있다.

```
Spring MVC 5.3+ + Coroutine:
  → Controller suspend fun 네이티브 지원
  → runBlocking 불필요
  → Tomcat 스레드 블로킹 없음 (AsyncContext)
  → JDBC 같은 블로킹 I/O도 Dispatchers.IO로 처리 가능
  → ★ 대부분의 프로젝트에서 충분!

Spring WebFlux + Coroutine:
  → 동일하게 suspend 함수 지원
  → Netty Event Loop 기반 완전 논블로킹
  → 블로킹 I/O 사용 불가 (R2DBC, WebClient 필수)
  → 처리량이 극도로 높아야 할 때 선택

결론:
  MVC 5.3+ = 코루틴 충분히 활용 가능 (대부분의 프로젝트)
  WebFlux = 극한의 논블로킹이 필요할 때 (높은 동시 접속)
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

---

### 부록: Kotlin + Spring MVC vs Kotlin + Spring WebFlux — 코루틴 사용 비교

두 환경에서 코루틴 사용법이 공존하면서 헷갈리기 쉽다. 명확히 분리해서 정리한다.

#### 공통점 (MVC 5.3+ / WebFlux 동일)

```kotlin
// ✅ Controller suspend fun — 둘 다 동일하게 작성
@RestController
class OrderController(private val orderService: OrderService) {

    @GetMapping("/orders/{id}")
    suspend fun getOrder(@PathVariable id: Long): OrderDetail {
        return orderService.getOrderDetail(id)
    }
}

// ✅ Service suspend fun — 둘 다 동일하게 작성
@Service
class OrderService {
    suspend fun getOrderDetail(id: Long): OrderDetail = coroutineScope {
        val order = async { getOrder(id) }
        val payment = async { getPayment(id) }
        OrderDetail(order.await(), payment.await())
    }
}

// ✅ coroutineScope / supervisorScope — 둘 다 동일
// ✅ runBlocking 불필요 — 둘 다 동일
// ✅ 의존성 — 둘 다 kotlinx-coroutines-core + kotlinx-coroutines-reactor
```

```
공통점 정리:
  - Controller / Service 코드가 완전히 동일
  - suspend, coroutineScope, async/await 모두 동일하게 사용
  - runBlocking 불필요
  - 의존성 동일
  → 코루틴 코드만 보면 MVC인지 WebFlux인지 구분 불가!
```

#### 차이점 1: 내부 동작 메커니즘

```
┌─────────────────────────────────────────────────────────────────┐
│              Kotlin + Spring MVC 5.3+                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  [요청] → Tomcat Thread Pool → Controller suspend fun 감지      │
│           ↓                                                     │
│  suspend → Mono 변환 (coroutines-reactor)                       │
│           ↓                                                     │
│  Servlet AsyncContext 시작 → Tomcat 스레드 반환                  │
│           ↓                                                     │
│  코루틴이 Dispatchers.IO 등에서 실행                              │
│           ↓                                                     │
│  완료 → Mono 완료 → Tomcat 스레드에서 응답 전송                   │
│                                                                 │
│  ★ 스레드 모델: Thread Pool (Tomcat, 기본 200개)                 │
│  ★ 서블릿 기반: Servlet API 3.0+ 비동기 처리                     │
│  ★ 블로킹 I/O 허용: JDBC, RestTemplate 등 사용 가능              │
│    (단, Dispatchers.IO에서 실행해야 함)                           │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│              Kotlin + Spring WebFlux                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  [요청] → Netty Event Loop → Controller suspend fun 감지        │
│           ↓                                                     │
│  suspend → Mono 변환 (coroutines-reactor)                       │
│           ↓                                                     │
│  Event Loop에서 논블로킹으로 처리                                 │
│           ↓                                                     │
│  완료 → Mono 완료 → Event Loop에서 응답 전송                     │
│                                                                 │
│  ★ 스레드 모델: Event Loop (Netty, CPU 코어 수만큼)              │
│  ★ Reactive 기반: Reactor / Mono / Flux                         │
│  ★ 블로킹 I/O 금지!: JDBC, RestTemplate 사용 불가                │
│    (R2DBC, WebClient만 사용)                                     │
└─────────────────────────────────────────────────────────────────┘
```

#### 차이점 2: I/O 클라이언트 선택

```
┌───────────────┬─────────────────────┬─────────────────────────┐
│               │ Spring MVC 5.3+     │ Spring WebFlux          │
├───────────────┼─────────────────────┼─────────────────────────┤
│ HTTP 클라이언트│ ✅ RestTemplate      │ ❌ RestTemplate          │
│               │ ✅ WebClient         │ ✅ WebClient             │
│               │ ✅ Retrofit          │ ✅ Retrofit              │
├───────────────┼─────────────────────┼─────────────────────────┤
│ DB 드라이버    │ ✅ JDBC/JPA          │ ❌ JDBC/JPA              │
│               │ ✅ R2DBC            │ ✅ R2DBC                 │
│               │ ✅ MyBatis          │ ❌ MyBatis               │
├───────────────┼─────────────────────┼─────────────────────────┤
│ 블로킹 I/O    │ ✅ 허용              │ ❌ 금지 (Event Loop 블로킹)│
│               │ (Dispatchers.IO에서) │                         │
├───────────────┼─────────────────────┼─────────────────────────┤
│ 논블로킹 극대화│ △ 가능하지만 선택적   │ ✅ 강제 (모든 I/O가 논블로킹)│
└───────────────┴─────────────────────┴─────────────────────────┘
```

#### 차이점 3: 프로젝트 선택 기준

```
★ Spring MVC 5.3+ + Coroutine을 선택해야 할 때:
  - 기존 MVC 프로젝트에 코루틴을 도입하고 싶을 때
  - JDBC / JPA / MyBatis 등 블로킹 DB 드라이버를 쓸 때
  - 팀이 서블릿 기반에 익숙할 때
  - 점진적 마이그레이션이 필요할 때
  → 대부분의 기존 프로젝트에 해당

★ Spring WebFlux + Coroutine을 선택해야 할 때:
  - 신규 프로젝트에서 처음부터 논블로킹으로 설계할 때
  - 높은 동시 접속 처리가 필요할 때 (채팅, 스트리밍, IoT)
  - R2DBC / WebClient / Redis Reactive 등 논블로킹 스택으로 통일 가능할 때
  - 팀이 Reactive 프로그래밍에 익숙할 때
```

#### 차이점 4: 코루틴에서 블로킹 I/O 처리 방식

```kotlin
// ═══════════════════════════════════════
// Spring MVC 5.3+ — 블로킹 I/O도 자연스럽게 처리
// ═══════════════════════════════════════
@Service
class OrderService(
    private val orderRepo: OrderRepository,     // JPA (블로킹)
    private val webClient: WebClient            // 논블로킹
) {
    suspend fun getOrderDetail(id: Long): OrderDetail = coroutineScope {
        // 블로킹 I/O → Dispatchers.IO에서 실행
        val order = async(Dispatchers.IO) {
            orderRepo.findById(id).orElseThrow()  // JDBC — 블로킹
        }
        // 논블로킹 I/O → 기본 Dispatcher에서 실행 가능
        val payment = async {
            webClient.get().uri("/payments/$id")
                .retrieve().awaitBody<Payment>()  // 논블로킹
        }
        OrderDetail(order.await(), payment.await())
    }
}

// ═══════════════════════════════════════
// Spring WebFlux — 모든 I/O가 논블로킹이어야 함
// ═══════════════════════════════════════
@Service
class OrderService(
    private val orderRepo: R2dbcOrderRepository,  // R2DBC (논블로킹)
    private val webClient: WebClient               // 논블로킹
) {
    suspend fun getOrderDetail(id: Long): OrderDetail = coroutineScope {
        val order = async {
            orderRepo.findById(id)  // R2DBC — 논블로킹 (suspend 확장)
        }
        val payment = async {
            webClient.get().uri("/payments/$id")
                .retrieve().awaitBody<Payment>()  // 논블로킹
        }
        OrderDetail(order.await(), payment.await())
    }
}
```

```
한 줄 정리:
  - 코루틴 코드 자체는 MVC / WebFlux 동일
  - 차이는 "어떤 I/O 클라이언트를 쓰느냐"와 "내부 스레드 모델"
  - MVC: 블로킹 I/O 허용 (Dispatchers.IO 활용), 점진적 도입 가능
  - WebFlux: 논블로킹 I/O 강제, 처음부터 설계 필요
```

## 참고 자료

- [Kotlin Coroutines — Structured Concurrency](https://kotlinlang.org/docs/coroutines-basics.html#structured-concurrency)
- [Spring WebFlux — Kotlin Coroutines Support](https://docs.spring.io/spring-framework/reference/languages/kotlin/coroutines.html)
- [Spring MVC vs WebFlux 선택 기준](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html)
- [Spring Framework 5.3 Release Notes — Coroutines](https://github.com/spring-projects/spring-framework/wiki/What%27s-New-in-Spring-Framework-5.x#spring-web-mvc)
