---
title: "@Transactional과 예외 처리 — 커넥션 풀 타임아웃이 500인데 로그가 안 남는 이유"
parent: Spring
nav_order: 2
tags: [Spring, Transactional, AOP, HikariCP, 커넥션풀, 예외처리, 500에러, ExceptionHandler, DispatcherServlet]
description: "Spring @Transactional AOP 프록시의 커넥션 획득 시점, 커넥션 풀 타임아웃이 로그 없이 500을 반환하는 원리, 예외가 삼켜지는 경우와 해결법을 정리합니다."
---

# @Transactional과 예외 처리 — 커넥션 풀 타임아웃이 500인데 로그가 안 남는 이유

## 핵심 정리

Spring에서 `@Transactional` 메서드를 호출하면, 비즈니스 로직 실행 **이전에** AOP 프록시가 DB 커넥션을 확보함. 이 커넥션 확보 단계에서 타임아웃이 발생하면 `SQLTransientConnectionException`이 던져지는데, **예외 핸들러 설정에 따라 로그에 아무것도 남지 않고 500만 반환되는 상황이 발생**할 수 있음.

이 문서에서는 Spring의 요청 처리 파이프라인을 따라가면서, 어떤 지점에서 예외가 발생하고, 왜 로그에 안 남을 수 있는지, 어떤 경우에 500으로 잡히는지를 정리함.

---

## Spring 요청 처리 파이프라인 전체 흐름

```
Client 요청
  │
  ▼
┌─────────────────────────────────────────────────────┐
│  Servlet Container (Tomcat)                         │
│  └─ Filter Chain (Security, CORS, etc.)             │
│      └─ DispatcherServlet                           │
│          └─ HandlerMapping → Controller 결정         │
│          └─ HandlerAdapter → 실제 메서드 호출        │
│              └─ AOP Proxy (@Transactional)          │ ← 여기서 커넥션 확보
│                  └─ TransactionInterceptor           │
│                      └─ PlatformTransactionManager   │
│                          └─ DataSource.getConnection()│ ← HikariCP에서 꺼냄
│                              └─ [비즈니스 로직 실행]  │
│                              └─ commit / rollback     │
│                              └─ 커넥션 반납           │
│          └─ 결과 반환 or 예외 처리                    │
│              └─ HandlerExceptionResolver              │
│                  └─ @ExceptionHandler 탐색            │
└─────────────────────────────────────────────────────┘
  │
  ▼
Client 응답
```

핵심은 **커넥션 확보가 비즈니스 로직 진입 전에 일어난다**는 것.

---

## @Transactional AOP 프록시가 커넥션을 확보하는 시점

### Spring의 트랜잭션 처리 내부 순서

```
1. HandlerAdapter가 Controller 메서드 호출
2. Controller가 @Transactional이 붙은 Service 메서드 호출
3. CGLIB/JDK Dynamic Proxy가 호출을 가로챔
4. TransactionInterceptor.invoke() 실행
5. PlatformTransactionManager.getTransaction() 호출
6. DataSourceTransactionManager.doBegin() 에서 DataSource.getConnection()
7. HikariCP의 HikariPool.getConnection(timeout) 실행
   → 풀에 여유 커넥션이 있으면 즉시 반환
   → 없으면 connectionTimeout(기본 30초)까지 대기
   → 타임아웃 초과 시 SQLTransientConnectionException 발생
8. 예외가 TransactionInterceptor → Proxy → Controller → DispatcherServlet으로 전파
```

여기서 중요한 건 **6~7번 단계에서 실패하면 비즈니스 로직(8번 이후)은 아예 실행되지 않는다**는 것.

### 코드로 보면

```java
// TransactionInterceptor (Spring 내부 코드 요약)
public Object invoke(MethodInvocation invocation) throws Throwable {
    // 1. 트랜잭션 시작 — 여기서 커넥션 확보
    TransactionInfo txInfo = createTransactionIfNecessary(tm, txAttr, joinpointIdentification);

    Object retVal;
    try {
        // 2. 실제 비즈니스 로직 실행
        retVal = invocation.proceed();
    } catch (Throwable ex) {
        // 3. 비즈니스 로직에서 예외 발생 시 롤백
        completeTransactionAfterThrowing(txInfo, ex);
        throw ex;
    }
    // 4. 정상 완료 시 커밋
    commitTransactionAfterReturning(txInfo);
    return retVal;
}
```

커넥션 풀 타임아웃은 **1번 단계**에서 발생함. `createTransactionIfNecessary()` 내부에서 `DataSource.getConnection()`을 호출하는데, 여기서 `SQLTransientConnectionException`이 터짐.

이 예외는 `try` 블록 바깥에서 발생하므로 **비즈니스 로직의 catch에 잡히지 않고**, 그대로 호출 스택을 타고 올라감.

---

## 예외가 로그에 안 남는 시나리오들

### 시나리오 1: @ExceptionHandler에서 해당 예외 타입을 안 잡는 경우

가장 흔한 케이스.

```java
@RestControllerAdvice
public class GlobalExceptionHandler {

    // 비즈니스 예외만 잡고 있음
    @ExceptionHandler(BusinessException.class)
    public ResponseEntity<ErrorResponse> handleBusiness(BusinessException e) {
        log.warn("비즈니스 예외: {}", e.getMessage());
        return ResponseEntity.badRequest().body(new ErrorResponse(e.getMessage()));
    }

    // 일반 Exception만 잡는데, 로그를 안 남기는 경우
    @ExceptionHandler(Exception.class)
    public ResponseEntity<ErrorResponse> handleGeneral(Exception e) {
        // ⚠️ 여기서 log를 안 찍거나, 메시지만 찍고 스택트레이스를 안 찍으면
        // 커넥션 타임아웃이 조용히 500으로 처리됨
        return ResponseEntity.status(500).body(new ErrorResponse("서버 오류"));
    }
}
```

`SQLTransientConnectionException`은 `Exception`의 하위 타입이므로 `handleGeneral`에 잡힘. 근데 **로그를 안 찍으면** 개발자 입장에서 "예외 로그가 없는데 500이 나온다"는 상황이 됨.

### 시나리오 2: @ExceptionHandler가 아예 없거나 Exception을 안 잡는 경우

```java
@RestControllerAdvice
public class GlobalExceptionHandler {
    // BusinessException만 잡고 있고, Exception은 안 잡음
    @ExceptionHandler(BusinessException.class)
    public ResponseEntity<ErrorResponse> handleBusiness(BusinessException e) { ... }
}
```

이 경우 `SQLTransientConnectionException`은 어떤 `@ExceptionHandler`에도 잡히지 않음.

그러면 Spring의 `DefaultHandlerExceptionResolver` → `BasicErrorController`(/error)로 넘어감. 이 기본 에러 처리기는:

```
1. /error 엔드포인트로 포워딩
2. BasicErrorController가 status 500 + 기본 에러 JSON 반환
3. 로그? → Spring Boot의 기본 설정에 따라 다름
```

**Spring Boot 기본 동작**: `server.error.include-stacktrace=never`가 기본값이고, 기본 에러 처리기는 **ERROR 레벨 로그를 찍지 않음**. Tomcat이 `WARN` 레벨로 한 줄 정도 남길 수 있지만, 로그 설정에 따라 보이지 않을 수 있음.

### 시나리오 3: CannotCreateTransactionException으로 감싸지는 경우

실제로 Spring은 `SQLTransientConnectionException`을 그대로 던지지 않는 경우가 많음.

`DataSourceTransactionManager.doBegin()` 내부에서 커넥션 획득 실패 시:

```java
// DataSourceTransactionManager 내부
protected void doBegin(Object transaction, TransactionDefinition definition) {
    try {
        Connection newCon = obtainDataSource().getConnection();
        // ...
    } catch (SQLException ex) {
        throw new CannotCreateTransactionException(
            "Could not open JDBC Connection for transaction", ex);
    }
}
```

`SQLException` → `CannotCreateTransactionException` (Spring의 `TransactionException`)으로 감싸짐.

그래서 `@ExceptionHandler(SQLTransientConnectionException.class)`로 잡으려 해도 **실제 던져지는 건 `CannotCreateTransactionException`**이라 안 잡힐 수 있음.

```
실제 예외 체인:
CannotCreateTransactionException
  └─ caused by: SQLTransientConnectionException
       └─ caused by: HikariPool$PoolInitializationException (또는 ConnectionNotAvailableException)
```

### 시나리오 4: HikariCP 로거 레벨 설정

HikariCP 자체적으로도 커넥션 풀 관련 로그를 남기는데:

```yaml
# application.yml
logging:
  level:
    com.zaxxer.hikari: WARN  # ← 이게 INFO나 DEBUG가 아니면 일부 로그가 안 보임
    com.zaxxer.hikari.pool.HikariPool: DEBUG  # ← 이걸 켜야 풀 상태 변화가 보임
```

HikariCP는 커넥션 타임아웃 시 `WARN` 레벨로 로그를 남기긴 하지만, **짧은 로그**만 남김:

```
HikariPool-1 - Connection is not available, request timed out after 30000ms.
```

이 로그가 보이지 않는 경우:
- `com.zaxxer.hikari` 로거 레벨이 `ERROR`로 설정된 경우
- 로그 출력 대상(appender)이 파일인데 확인하지 않은 경우
- 로그 프레임워크 설정에서 해당 패키지가 제외된 경우

---

## 어떤 경우에 500으로 잡히는가 — 완전 정리

| 상황 | 예외 타입 | HTTP 응답 | 로그 남는가 |
|---|---|---|---|
| 커넥션 풀 타임아웃, @ExceptionHandler 없음 | `CannotCreateTransactionException` | 500 (Spring 기본 에러) | 기본적으로 안 남음 |
| 커넥션 풀 타임아웃, `Exception` 핸들러에서 로그 안 찍음 | `CannotCreateTransactionException` | 500 (커스텀 응답) | 안 남음 |
| 커넥션 풀 타임아웃, `Exception` 핸들러에서 `log.error` 찍음 | `CannotCreateTransactionException` | 500 (커스텀 응답) | **남음** |
| 커넥션 풀 타임아웃, `TransactionException` 전용 핸들러 있음 | `CannotCreateTransactionException` | 503 등 커스텀 | **남음** |
| 비즈니스 로직 내 DB 쿼리 타임아웃 | `QueryTimeoutException` | 500 | 핸들러 설정에 따라 다름 |
| 비즈니스 로직 내 NullPointerException | `NullPointerException` | 500 | 핸들러 설정에 따라 다름 |

핵심 차이: **비즈니스 로직 예외**는 개발자가 익숙한 패턴이라 보통 잡아서 로그를 남김. 반면 **인프라 레벨 예외(커넥션 풀 타임아웃)**는 예상 밖의 예외라 핸들러에서 누락되기 쉬움.

---

## 500이 나는데 예외 로그가 없는 다른 케이스들

커넥션 풀 타임아웃만이 아님. 같은 패턴으로 로그 없이 500이 나는 케이스들:

### 1. 스레드 풀 포화

```java
// Tomcat 기본: maxThreads=200
// 모든 스레드가 점유된 상태에서 새 요청이 들어오면
// acceptCount 큐마저 꽉 차면 → Connection Refused (클라이언트에서 에러)
// 큐에서 대기 중 타임아웃 → 503 또는 연결 끊김
```

이 경우 애플리케이션 레벨 로그는 없고, Tomcat 로그에만 남을 수 있음.

### 2. @Async 메서드 내부 예외

```java
@Async
public void sendNotification(Long userId) {
    // 여기서 예외 터지면?
    userService.notify(userId); // ← NPE 발생
}
```

`@Async`는 별도 스레드에서 실행됨. 기본 `SimpleAsyncTaskExecutor`는 **예외를 삼켜버림**. `AsyncUncaughtExceptionHandler`를 설정하지 않으면 로그가 안 남음.

### 3. Filter 단에서 발생하는 예외

```java
public class CustomFilter extends OncePerRequestFilter {
    @Override
    protected void doFilterInternal(...) {
        // 여기서 예외 터지면 DispatcherServlet에 도달하기 전이므로
        // @ExceptionHandler가 전혀 동작하지 않음
        String token = request.getHeader("Authorization");
        jwtValidator.validate(token); // ← 예외 발생
    }
}
```

Filter 예외는 `@ControllerAdvice`의 `@ExceptionHandler` 범위 밖. Servlet Container(Tomcat)가 직접 500을 반환하고, 로그는 Tomcat 설정에 따라 남거나 안 남음.

### 4. ResponseBody 직렬화 실패

```java
@GetMapping("/user")
public UserResponse getUser() {
    return userService.getUser(); // ← 정상 리턴
    // 근데 UserResponse를 JSON으로 직렬화할 때 Jackson에서 에러
    // 예: 순환 참조, getter에서 예외 발생
}
```

Controller 메서드는 정상 종료됐지만, **응답을 쓰는 단계에서 실패**. `HttpMessageNotWritableException`이 발생하는데, 이미 Controller 실행은 끝난 상태라 `@ExceptionHandler` 동작이 보장되지 않음.

---

## 헷갈렸던 포인트

### Q. CannotCreateTransactionException이면 SQLTransientConnectionException을 잡아봤자 소용없는 거 아님?

맞음. 실제로 잡아야 하는 건 `CannotCreateTransactionException` 또는 그 상위인 `TransactionException`.

```java
@RestControllerAdvice
public class GlobalExceptionHandler {

    // 이렇게 잡아야 커넥션 풀 타임아웃이 확실히 잡힘
    @ExceptionHandler(CannotCreateTransactionException.class)
    public ResponseEntity<ErrorResponse> handleConnectionPoolTimeout(
            CannotCreateTransactionException e) {
        log.error("[CONN_POOL_TIMEOUT] 트랜잭션 생성 실패 - 커넥션 풀 고갈 가능성: {}",
                  e.getMessage(), e);
        return ResponseEntity
            .status(HttpStatus.SERVICE_UNAVAILABLE)
            .body(new ErrorResponse("일시적으로 서비스가 지연되고 있습니다. 잠시 후 다시 시도해주세요."));
    }

    // 보험용: 모든 예외에 대해 스택트레이스 로깅
    @ExceptionHandler(Exception.class)
    public ResponseEntity<ErrorResponse> handleUnexpected(Exception e) {
        log.error("[UNEXPECTED] 처리되지 않은 예외: {}", e.getMessage(), e);
        return ResponseEntity
            .status(HttpStatus.INTERNAL_SERVER_ERROR)
            .body(new ErrorResponse("서버 오류가 발생했습니다."));
    }
}
```

`Exception` 핸들러에 **반드시 `log.error(..., e)`로 스택트레이스를 남겨야** 함. 메시지만 찍으면 원인 파악이 불가능.

### Q. 그러면 @Transactional 없이 직접 DataSource에서 커넥션 꺼내면 다른 흐름인가?

맞음. `@Transactional` 없이 JdbcTemplate이나 MyBatis를 직접 사용하는 경우:

```java
// @Transactional 없는 경우
public List<User> getUsers() {
    // JdbcTemplate 내부에서 DataSource.getConnection() 호출
    return jdbcTemplate.query("SELECT * FROM users", rowMapper);
}
```

이 경우 커넥션 획득은 **쿼리 실행 시점**에 일어남. JdbcTemplate 내부에서 `SQLTransientConnectionException`이 발생하면 `DataAccessResourceFailureException`으로 감싸짐.

| 방식 | 커넥션 획득 시점 | 감싸지는 예외 |
|---|---|---|
| `@Transactional` | 메서드 진입 전 (AOP) | `CannotCreateTransactionException` |
| JdbcTemplate | 쿼리 실행 시 | `DataAccessResourceFailureException` |
| EntityManager 직접 사용 | `em.find()` 등 호출 시 | `PersistenceException` |

### Q. 500이 아니라 503으로 내려주는 게 맞는 거 아님?

맞음. 커넥션 풀 고갈은 **서버가 일시적으로 요청을 처리할 수 없는 상태**이므로 `503 Service Unavailable`이 의미적으로 정확함.

500은 "서버 내부에 예상치 못한 오류가 발생했다"는 뜻이고, 503은 "서버가 일시적으로 과부하 상태라 처리할 수 없다"는 뜻. 클라이언트 입장에서 503을 받으면 **재시도(Retry)가 의미 있다**는 신호로 받아들일 수 있음.

```
500 → "서버 버그일 수 있으니 재시도해도 같은 결과일 수 있음"
503 → "잠시 후 다시 시도하면 될 수 있음" + Retry-After 헤더 활용 가능
```

### Q. log.error에서 두 번째 인자로 `e`를 넘기는 거랑 `e.getMessage()`만 넘기는 거 차이가 뭔데?

```java
// 이렇게 하면 메시지만 출력됨 — 원인 추적 불가
log.error("에러 발생: {}", e.getMessage());

// 이렇게 해야 전체 스택트레이스가 출력됨
log.error("에러 발생: {}", e.getMessage(), e);
```

SLF4J에서 마지막 인자가 `Throwable` 타입이면 자동으로 스택트레이스를 출력함. `e.getMessage()`만 찍으면 `CannotCreateTransactionException: Could not open JDBC Connection` 한 줄만 나오고, **어떤 DataSource에서, 어떤 타임아웃 설정으로, HikariCP 풀 상태가 어땠는지** 등의 정보를 알 수 없음.

---

## 실무 체크리스트 — "로그 없는 500" 방지

1. **`@ExceptionHandler(Exception.class)`에 반드시 `log.error(..., e)` 포함** — 최후의 보험
2. **`@ExceptionHandler(CannotCreateTransactionException.class)` 별도 등록** — 커넥션 풀 이슈 즉시 감지
3. **HikariCP 로거 레벨 `WARN` 이상 보장** — `com.zaxxer.hikari: WARN`
4. **`leak-detection-threshold` 설정** — 커넥션 누수 사전 감지
5. **Actuator + Micrometer로 `hikaricp_connections_pending` 모니터링** — pending > 0이 지속되면 알림
6. **`connection-timeout`을 30초에서 5초로 단축** — 빠른 실패(Fail Fast) 전략

---

## 참고 자료

- [Spring Framework — TransactionInterceptor 소스 코드](https://github.com/spring-projects/spring-framework/blob/main/spring-tx/src/main/java/org/springframework/transaction/interceptor/TransactionInterceptor.java)
- [Spring Framework — DataSourceTransactionManager 소스 코드](https://github.com/spring-projects/spring-framework/blob/main/spring-jdbc/src/main/java/org/springframework/jdbc/datasource/DataSourceTransactionManager.java)
- [HikariCP GitHub — About Pool Sizing](https://github.com/brettwooldridge/HikariCP/wiki/About-Pool-Sizing)
- [Baeldung — Spring @ExceptionHandler](https://www.baeldung.com/exception-handling-for-rest-with-spring)
