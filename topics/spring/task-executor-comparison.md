---
title: "SimpleAsyncTaskExecutor vs ThreadPoolTaskExecutor — Spring 비동기 실행기의 차이와 선택 기준"
parent: Spring
nav_order: 6
---

# SimpleAsyncTaskExecutor vs ThreadPoolTaskExecutor — Spring 비동기 실행기의 차이와 선택 기준

## 핵심 정리

### 한 줄 요약

**SimpleAsyncTaskExecutor**는 매번 새 스레드를 만들어 실행하는 "풀이 아닌 실행기"이고, **ThreadPoolTaskExecutor**는 스레드를 재사용하는 진짜 스레드 풀이다. 실무에서는 **거의 항상 ThreadPoolTaskExecutor를 써야 한다.**

---

### 내부 구조 비교

```
┌─────────── SimpleAsyncTaskExecutor ───────────┐
│                                                │
│  @Async 호출 1 → new Thread() → 실행 → 스레드 소멸
│  @Async 호출 2 → new Thread() → 실행 → 스레드 소멸
│  @Async 호출 3 → new Thread() → 실행 → 스레드 소멸
│  ...                                           │
│  @Async 호출 10000 → new Thread() → 실행 → 소멸│
│                                                │
│  ★ 스레드를 재사용하지 않음                     │
│  ★ 상한선 없음 (기본) → 스레드 무한 생성 가능    │
│  ★ 큐 없음 → 모든 요청을 즉시 새 스레드로 실행   │
└────────────────────────────────────────────────┘

┌─────────── ThreadPoolTaskExecutor ────────────┐
│                                                │
│  ┌── Core Threads (corePoolSize: 5) ────────┐ │
│  │ Thread-1: ████ 작업 실행 중              │ │
│  │ Thread-2: ████ 작업 실행 중              │ │
│  │ Thread-3: ░░░░ 대기 중 (유지됨)          │ │
│  │ Thread-4: ░░░░ 대기 중 (유지됨)          │ │
│  │ Thread-5: ████ 작업 실행 중              │ │
│  └──────────────────────────────────────────┘ │
│                                                │
│  ┌── Queue (queueCapacity: 100) ────────────┐ │
│  │ [작업6] [작업7] [작업8] ...               │ │
│  │ ★ 코어 스레드가 모두 바쁘면 여기 대기     │ │
│  └──────────────────────────────────────────┘ │
│                                                │
│  ┌── Max Threads (maxPoolSize: 20) ─────────┐ │
│  │ Thread-6~20: 큐도 가득 차면 추가 생성     │ │
│  │ ★ keepAliveSeconds 후 소멸 (기본 60초)    │ │
│  └──────────────────────────────────────────┘ │
│                                                │
│  큐도 가득, 스레드도 max → RejectedExecution!  │
└────────────────────────────────────────────────┘
```

---

### 핵심 차이 비교표

| | SimpleAsyncTaskExecutor | ThreadPoolTaskExecutor |
|---|---|---|
| **스레드 재사용** | ❌ 매번 `new Thread()` | ✅ 풀에서 재사용 |
| **스레드 수 제한** | 기본 없음 (`concurrencyLimit=-1`) | ✅ core/max로 제한 |
| **작업 큐** | ❌ 없음 (즉시 실행) | ✅ `LinkedBlockingQueue` |
| **스레드 생성 비용** | 매번 발생 (~1ms + ~1MB 스택) | 최초만 (이후 재사용) |
| **예외 처리** | UncaughtExceptionHandler 미등록 | `afterExecute()`로 처리 가능 |
| **모니터링** | 어려움 (스레드 추적 불가) | 풀 상태 메트릭 제공 |
| **Graceful Shutdown** | ❌ 실행 중 작업 추적 불가 | ✅ `setWaitForTasksToCompleteOnShutdown(true)` |
| **Spring Boot 기본** | ✅ `@EnableAsync` 기본값 | ❌ 직접 설정 필요 |

---

### ThreadPoolTaskExecutor의 작업 처리 흐름

```
새 작업 submit
    │
    ▼
┌─ 코어 스레드 여유 있음? ─┐
│  YES                      │  NO
│  → 코어 스레드에 할당      │  │
│                           │  ▼
│                     ┌─ 큐에 여유 있음? ─┐
│                     │  YES              │  NO
│                     │  → 큐에 추가       │  │
│                     │                   │  ▼
│                     │           ┌─ maxPoolSize 미만? ─┐
│                     │           │  YES                │  NO
│                     │           │  → 새 스레드 생성    │  │
│                     │           │    (추가 스레드)     │  ▼
│                     │           │                     │  RejectedExecutionException!
│                     │           │                     │  (기본: AbortPolicy)
```

**주의**: 큐가 가득 차야 maxPoolSize까지 스레드가 늘어남. 큐 크기가 크면 max 스레드가 생성되지 않을 수 있음.

```java
// 예시: corePoolSize=5, queueCapacity=100, maxPoolSize=20

// 동시 요청 5개  → 코어 스레드 5개가 처리
// 동시 요청 50개 → 코어 5개 처리 + 45개 큐 대기
// 동시 요청 105개 → 코어 5개 처리 + 큐 100개 + 추가 스레드 0개 ← 아직 큐가 안 참!
// 동시 요청 106개 → 코어 5개 + 큐 100개 가득 + 스레드 1개 추가 생성 (총 6개)
// 동시 요청 120개 → 코어 5개 + 큐 100개 + 추가 15개 (총 20개 = max)
// 동시 요청 121개 → RejectedExecutionException!
```

---

### 실제 설정 코드

#### SimpleAsyncTaskExecutor (기본값 — 문제 있는 코드)

```java
@Configuration
@EnableAsync  // 이것만 붙이면 SimpleAsyncTaskExecutor가 기본 사용
public class AsyncConfig {
    // 아무 설정 없음 → 위험!
}

@Service
public class NotificationService {
    @Async
    public void send(Long userId) {
        // 호출할 때마다 new Thread()
        // 트래픽 폭증 시 스레드 수천 개 생성 → OOM
    }
}
```

#### ThreadPoolTaskExecutor (올바른 설정)

```java
@Configuration
@EnableAsync
public class AsyncConfig implements AsyncConfigurer {

    @Override
    public Executor getAsyncExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(10);        // 항상 유지할 스레드
        executor.setMaxPoolSize(30);         // 최대 스레드
        executor.setQueueCapacity(50);       // 대기 큐 크기
        executor.setKeepAliveSeconds(60);    // 추가 스레드 유휴 시 소멸 시간
        executor.setThreadNamePrefix("async-");  // 스레드 이름 (로그 추적용)

        // Graceful Shutdown
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);

        // 큐 + 스레드 모두 가득 찼을 때 정책
        executor.setRejectedExecutionHandler(new ThreadPoolExecutor.CallerRunsPolicy());

        executor.initialize();
        return executor;
    }

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (ex, method, params) -> {
            log.error("@Async 예외 - method: {}, params: {}",
                method.getName(), Arrays.toString(params), ex);
        };
    }
}
```

#### 용도별 다중 Executor

```java
@Configuration
@EnableAsync
public class AsyncConfig {

    // 알림 전송용 (빠르고 가벼운 작업)
    @Bean("notificationExecutor")
    public Executor notificationExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(5);
        executor.setMaxPoolSize(10);
        executor.setQueueCapacity(200);      // 큐 넉넉히 (알림은 좀 밀려도 OK)
        executor.setThreadNamePrefix("notify-");
        executor.initialize();
        return executor;
    }

    // 파일 처리용 (무겁고 오래 걸리는 작업)
    @Bean("fileProcessExecutor")
    public Executor fileProcessExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(3);
        executor.setMaxPoolSize(5);          // 스레드 적게 (무거운 작업)
        executor.setQueueCapacity(20);       // 큐 작게 (밀리면 빨리 거부)
        executor.setThreadNamePrefix("file-");
        executor.setRejectedExecutionHandler(new ThreadPoolExecutor.CallerRunsPolicy());
        executor.initialize();
        return executor;
    }
}

@Service
public class OrderService {

    @Async("notificationExecutor")   // ← 이름으로 지정
    public void sendNotification(Long orderId) { ... }

    @Async("fileProcessExecutor")    // ← 이름으로 지정
    public CompletableFuture<String> generateReport(Long orderId) { ... }
}
```

---

### RejectedExecutionHandler 정책 비교

큐도 가득 차고 스레드도 maxPoolSize에 도달했을 때 어떻게 할 것인가:

```
┌──────────────────────┬──────────────────────────────────────────────┐
│ 정책                  │ 동작                                         │
├──────────────────────┼──────────────────────────────────────────────┤
│ AbortPolicy (기본)    │ RejectedExecutionException 발생              │
│                      │ → @Async면 예외가 삼켜질 수 있음!             │
├──────────────────────┼──────────────────────────────────────────────┤
│ CallerRunsPolicy ★   │ 호출한 스레드가 직접 실행                     │
│                      │ → Tomcat 스레드가 실행 → 자연스러운 백프레셔  │
│                      │ → 실무에서 가장 많이 사용                     │
├──────────────────────┼──────────────────────────────────────────────┤
│ DiscardPolicy        │ 조용히 버림 (예외도 없음)                     │
│                      │ → 위험! 작업 유실을 모름                      │
├──────────────────────┼──────────────────────────────────────────────┤
│ DiscardOldestPolicy  │ 큐에서 가장 오래된 작업 버리고 새 작업 추가   │
│                      │ → 오래된 작업이 중요할 수 있어 위험            │
└──────────────────────┴──────────────────────────────────────────────┘
```

**CallerRunsPolicy가 좋은 이유**:

```
[상황] 비동기 스레드 풀이 포화됨

AbortPolicy:
  Tomcat Thread → @Async 호출 → RejectedExecutionException
  → 작업 유실 또는 예외 처리 필요

CallerRunsPolicy:
  Tomcat Thread → @Async 호출 → 풀 포화 → Tomcat Thread가 직접 실행
  → 작업은 동기적으로 완료됨 (느려지지만 유실 없음)
  → Tomcat Thread가 잡혀 있으니 자연스럽게 요청 속도 감소
  → 시스템에 자동 백프레셔 효과!
```

---

### Spring Boot 버전별 기본 Executor 변화

```
Spring Boot 2.x:
  @EnableAsync 기본 → SimpleAsyncTaskExecutor
  ★ 위험! 반드시 직접 설정 필요

Spring Boot 3.2+:
  spring.threads.virtual.enabled=true 설정 시
  → SimpleAsyncTaskExecutor + Virtual Thread 조합
  ★ Virtual Thread는 경량이라 매번 생성해도 부담 없음
  ★ 이 경우에 한해 SimpleAsyncTaskExecutor가 합리적 선택

Spring Boot 3.x (일반):
  여전히 기본은 SimpleAsyncTaskExecutor
  → ThreadPoolTaskExecutor 직접 설정 권장
```

#### Virtual Thread + SimpleAsyncTaskExecutor (Spring Boot 3.2+)

```java
// application.yml
spring:
  threads:
    virtual:
      enabled: true

// 이 설정 시 SimpleAsyncTaskExecutor가 내부적으로
// Thread.ofVirtual()을 사용하여 Virtual Thread 생성
// → 스레드 생성 비용이 거의 없으므로 풀링 불필요
// → 10만 개를 만들어도 메모리 수 MB

// 단, Virtual Thread는 CPU-bound 작업에는 부적합
// I/O 대기가 많은 작업에만 효과적
```

---

### 모니터링

```java
// ThreadPoolTaskExecutor는 상태 조회 가능
@Scheduled(fixedRate = 30000)
public void monitorThreadPool() {
    ThreadPoolTaskExecutor executor = (ThreadPoolTaskExecutor) asyncExecutor;
    ThreadPoolExecutor pool = executor.getThreadPoolExecutor();

    log.info("Async Pool - active: {}, poolSize: {}, queueSize: {}, completed: {}",
        pool.getActiveCount(),         // 현재 실행 중인 스레드
        pool.getPoolSize(),            // 현재 풀 크기
        pool.getQueue().size(),        // 대기 중인 작업 수
        pool.getCompletedTaskCount()   // 완료된 작업 수
    );
}

// Micrometer로 자동 노출 (Spring Boot Actuator)
// executor.* 메트릭이 자동 등록됨
// → Grafana에서 executor_active, executor_queued, executor_pool_size 확인
```

```
SimpleAsyncTaskExecutor에서는 이런 모니터링이 불가능:
  - 현재 몇 개의 스레드가 실행 중인지 모름
  - 작업이 몇 개 완료되었는지 모름
  - 스레드가 몇 개나 생성되었는지 모름
  → "보이지 않는 것은 관리할 수 없다"
```

## 헷갈렸던 포인트

### Q1. SimpleAsyncTaskExecutor를 쓰는 게 맞는 경우가 있긴 한가?

있다. 딱 두 가지:

1. **Spring Boot 3.2+ Virtual Thread**: `spring.threads.virtual.enabled=true` 설정 시. Virtual Thread는 JVM이 관리하는 경량 스레드라서 매번 생성해도 OS 스레드처럼 부담이 없다.

2. **테스트/프로토타이핑**: 스레드 풀 설정을 고민할 단계가 아닌 초기 개발. 단, 프로덕션 전에 반드시 교체.

그 외에는 **항상 ThreadPoolTaskExecutor**를 써야 한다.

### Q2. corePoolSize, maxPoolSize, queueCapacity를 어떻게 정하나?

정해진 공식은 없지만 가이드라인:

```
① 작업 성격 파악
   - I/O 바운드 (외부 API, DB): 스레드 더 필요 → core 높게
   - CPU 바운드 (계산, 변환): 스레드 적게 → core ≈ CPU 코어 수

② 작업 처리 시간
   - 빠른 작업 (< 100ms): 큐 크게, 스레드 적게 (회전율 높으니까)
   - 느린 작업 (> 1초): 큐 작게, 스레드 좀 더 (안 밀리게)

③ 트래픽 패턴
   - 균일: core ≈ max (추가 스레드 불필요)
   - 버스트: core < max (피크 때만 추가 생성)

④ 일반적인 시작점
   - core: 5~10
   - max: 20~50
   - queue: 50~200
   → 모니터링 보면서 조정
```

### Q3. @Async 없이 ThreadPoolTaskExecutor를 직접 쓸 수 있나?

가능하다. `@Async`는 AOP 기반 편의 기능일 뿐:

```java
@Service
public class ReportService {

    private final ThreadPoolTaskExecutor executor;

    // 직접 submit
    public Future<Report> generateAsync(Long id) {
        return executor.submit(() -> {
            return generateReport(id);  // 풀의 스레드에서 실행
        });
    }

    // CompletableFuture와 조합
    public CompletableFuture<Report> generateAsync2(Long id) {
        return CompletableFuture.supplyAsync(
            () -> generateReport(id),
            executor  // ← Executor 지정
        );
    }
}
```

`@Async`보다 직접 사용이 더 명시적이고, 같은 클래스 내부 호출 문제(프록시 이슈)도 없다.

### Q4. ThreadPoolTaskExecutor와 Java의 ThreadPoolExecutor는 뭐가 다른가?

**ThreadPoolTaskExecutor는 ThreadPoolExecutor의 Spring 래퍼**:

```
ThreadPoolTaskExecutor (Spring)
  └── 내부에 java.util.concurrent.ThreadPoolExecutor를 가지고 있음
      └── Spring 생명주기 관리 (InitializingBean, DisposableBean)
      └── Graceful Shutdown 지원
      └── Micrometer 메트릭 자동 연동
      └── @Async 통합

// 실제로 ThreadPoolTaskExecutor.getThreadPoolExecutor()로
// 내부 Java ThreadPoolExecutor에 접근 가능
```

Spring 환경이면 ThreadPoolTaskExecutor, 순수 Java면 ThreadPoolExecutor 사용.

## 참고 자료

- [Spring Docs — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Boot 3.2 — Virtual Thread Support](https://spring.io/blog/2023/09/09/all-together-now-spring-boot-3-2-graalvm-native-images-java-21-and-virtual)
- [Java ThreadPoolExecutor Javadoc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
