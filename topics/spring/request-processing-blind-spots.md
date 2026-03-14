---
title: "Spring 요청 처리 사각지대 — 로그가 안 남는 에러들의 정체"
parent: Spring
nav_order: 4
tags: [Tomcat, 스레드풀, SimpleAsyncTaskExecutor, Filter, JWT, Servlet Container, 직렬화, Jackson, 모니터링, JMX, Micrometer]
description: "Tomcat 스레드 풀 포화, SimpleAsyncTaskExecutor 예외 삼킴, Filter 단 JWT 검증 실패, ResponseBody 직렬화 실패 등 애플리케이션 로그에 안 남는 에러들의 원인과 모니터링 방법을 정리합니다."
---

# Spring 요청 처리 사각지대 — 로그가 안 남는 에러들의 정체

## 핵심 정리

### 요청이 처리되는 전체 파이프라인과 사각지대

```
클라이언트 요청
  │
  ▼
┌──────────────────────────────────────────────────────────────┐
│ ❶ OS 레벨 (TCP backlog)                                     │
│   - TCP SYN 큐 / Accept 큐 가득 차면 → 클라이언트 타임아웃  │
│   - 로그: 없음. netstat/ss로만 확인 가능                     │
├──────────────────────────────────────────────────────────────┤
│ ❷ Tomcat Connector (Acceptor Thread)                        │
│   - TCP 연결 수락, NIO 채널 등록                             │
│   - maxConnections(기본 8192) 초과 시 → 대기                 │
│   - 로그: 없음. Tomcat JMX 메트릭으로만 확인                 │
├──────────────────────────────────────────────────────────────┤
│ ❸ Tomcat Thread Pool (Worker Thread) ★ 사각지대 1           │
│   - maxThreads(기본 200) 모두 바쁘면 → acceptCount 큐 대기   │
│   - 큐도 가득 차면(기본 100) → connection refused            │
│   - 로그: 클라이언트에는 타임아웃, 서버 로그에 안 남을 수 있음│
├──────────────────────────────────────────────────────────────┤
│ ❹ Servlet Filter Chain ★ 사각지대 2                         │
│   - Spring Security Filter (JWT 검증 등)                     │
│   - CORS Filter, Encoding Filter                            │
│   - 여기서 예외 → DispatcherServlet에 안 들어감              │
│   - 로그: ErrorPage로 넘어가거나, 컨테이너가 처리            │
├──────────────────────────────────────────────────────────────┤
│ ❺ DispatcherServlet                                         │
│   - HandlerMapping → HandlerAdapter → Controller            │
│   - @ControllerAdvice가 잡는 영역 ← 우리가 아는 세계        │
├──────────────────────────────────────────────────────────────┤
│ ❻ 응답 직렬화 (MessageConverter) ★ 사각지대 3               │
│   - Controller return 이후 Jackson 직렬화                    │
│   - 여기서 실패하면 → 이미 200 status 세팅된 후일 수 있음    │
├──────────────────────────────────────────────────────────────┤
│ ❼ 비동기 처리 ★ 사각지대 4                                  │
│   - @Async, SimpleAsyncTaskExecutor                         │
│   - 다른 스레드에서 실행 → 예외가 호출자에게 전파 안 됨      │
└──────────────────────────────────────────────────────────────┘
```

---

### 1. Tomcat 스레드 풀 포화 모니터링

스레드 풀이 포화되면 **애플리케이션 코드가 실행 자체가 안 됨** → 당연히 앱 로그 안 남음.

#### 어떤 상황에서 발생하는가

```
[Tomcat Thread Pool]
maxThreads = 200 (기본값)

Thread-1:  ████████████████████  (슬로우 쿼리 30초)
Thread-2:  ████████████████████  (외부 API 타임아웃 60초)
Thread-3:  ████████████████████  (DB 커넥션 대기)
...
Thread-200: ███████████████████  (모두 바쁨)

→ 201번째 요청: acceptCount 큐(기본 100)에서 대기
→ 301번째 요청: connection refused ← 여기서 로그 안 남음!
```

#### 모니터링 방법

**① Micrometer + Prometheus (가장 권장)**

```java
// Spring Boot Actuator 자동 노출 메트릭들
// application.yml
management:
  endpoints:
    web:
      exposure:
        include: metrics, prometheus
  metrics:
    tags:
      application: my-app
```

```
# Prometheus에서 볼 수 있는 Tomcat 메트릭
tomcat_threads_current_threads    ← 현재 생성된 스레드 수
tomcat_threads_busy_threads       ← 현재 요청 처리 중인 스레드 수
tomcat_threads_config_max_threads ← maxThreads 설정값

# 알림 조건 (Grafana Alert)
tomcat_threads_busy_threads / tomcat_threads_config_max_threads > 0.8
→ "스레드 80% 이상 사용 중" 알림
```

**② JMX 직접 조회**

```bash
# jconsole이나 VisualVM으로 MBean 확인
# MBean: Catalina:type=ThreadPool,name="http-nio-8080"

currentThreadCount    # 현재 스레드 수
currentThreadsBusy    # 바쁜 스레드 수
maxThreads            # 최대 스레드
connectionCount       # 현재 연결 수
```

**③ Tomcat Access Log (이건 남는다)**

```yaml
# application.yml
server:
  tomcat:
    accesslog:
      enabled: true
      pattern: "%h %l %u %t \"%r\" %s %b %D"
      #                                    ↑ 처리 시간(ms)
      directory: /var/log/tomcat
```

Access log는 Tomcat 레벨에서 기록 → 앱 로그와 독립. 응답 시간이 갑자기 늘어나면 스레드 포화 징후.

**④ 커널 레벨 확인 (TCP 큐 오버플로우)**

```bash
# Accept 큐 오버플로우 횟수
netstat -s | grep "listen queue"
# 또는
ss -tnlp | grep 8080

# SYN 큐 드롭
cat /proc/net/netstat | grep -i overflow
```

#### 사전 방지 설정

```yaml
server:
  tomcat:
    threads:
      max: 200          # 최대 워커 스레드
      min-spare: 20     # 최소 유지 스레드
    max-connections: 8192  # NIO 최대 커넥션
    accept-count: 100     # 모든 스레드 바쁠 때 대기 큐 크기
    connection-timeout: 20000  # 커넥션 타임아웃 (ms)
```

---

### 2. SimpleAsyncTaskExecutor가 예외를 삼키는 이유

#### 핵심 원인: 다른 스레드에서 실행되기 때문

```java
@Service
public class OrderService {

    @Async
    public void sendNotification(Long orderId) {
        // 이 코드는 호출자 스레드가 아닌 별도 스레드에서 실행됨
        throw new RuntimeException("알림 전송 실패!");
        // → 이 예외는 어디로 가는가?
    }
}
```

```
호출자 스레드 (Thread-1)         비동기 스레드 (SimpleAsync-1)
─────────────────────          ─────────────────────────
orderService.sendNotification()
  → 즉시 return (void)              → sendNotification() 실행
  → 다음 코드 진행                   → RuntimeException 발생!
  → 예외를 모름                      → 누가 잡아주나?
                                      → SimpleAsyncTaskExecutor는
                                        UncaughtExceptionHandler 없음
                                      → Thread.run()에서 예외 발생
                                      → JVM이 스레드 종료시키며 stderr에 출력
                                      → 끝. 로그 프레임워크 안 탐.
```

#### 왜 SimpleAsyncTaskExecutor가 특히 문제인가

```java
// SimpleAsyncTaskExecutor 내부 (실제 코드 요약)
public class SimpleAsyncTaskExecutor {

    @Override
    public void execute(Runnable task) {
        // 매번 새 스레드 생성 (풀 없음!)
        Thread t = new Thread(task);
        t.start();
        // 끝. 예외 핸들러 등록 안 함.
    }
}

// vs ThreadPoolTaskExecutor는 afterExecute()에서 예외를 처리할 수 있음
```

**SimpleAsyncTaskExecutor의 문제점**:
1. 스레드 풀이 아님 — 매 호출마다 `new Thread()` (스레드 폭발 위험)
2. UncaughtExceptionHandler 미설정
3. Spring Boot `@EnableAsync` 기본값이 이것

#### 해결 방법

```java
@Configuration
@EnableAsync
public class AsyncConfig implements AsyncConfigurer {

    @Override
    public Executor getAsyncExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(5);
        executor.setMaxPoolSize(20);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("async-");
        executor.initialize();
        return executor;
    }

    // ★ 이걸 등록해야 예외가 로그에 남음
    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (throwable, method, params) -> {
            log.error("비동기 메서드 예외 - method: {}, params: {}",
                method.getName(), Arrays.toString(params), throwable);
        };
    }
}
```

또는 `@Async` 메서드의 리턴 타입을 `CompletableFuture`로 바꾸면 호출자가 예외를 받을 수 있음:

```java
@Async
public CompletableFuture<Void> sendNotification(Long orderId) {
    // 예외 발생 시 CompletableFuture에 담겨서 호출자에게 전달
    notificationClient.send(orderId);
    return CompletableFuture.completedFuture(null);
}

// 호출자
orderService.sendNotification(1L)
    .exceptionally(ex -> {
        log.error("알림 실패", ex);
        return null;
    });
```

---

### 3. Filter 단 예외와 JWT 검증 — Servlet Container에서 일어나는 일

#### Filter에서 예외가 발생하면 흐름

```
요청 → Tomcat → Filter Chain → DispatcherServlet → Controller
                    ↑
              여기서 예외 발생!

[Filter에서 예외 시 흐름]

① Filter.doFilter()에서 예외 throw
    ↓
② Servlet Container(Tomcat)가 catch
    ↓
③ Container는 web.xml 또는 ErrorPage 매핑 확인
    ↓
④-A. ErrorPage 있으면 → /error 경로로 내부 forward
     → DispatcherServlet → BasicErrorController
     → JSON 에러 응답 생성
    ↓
④-B. ErrorPage 없으면 → Tomcat 기본 HTML 에러 페이지 반환
     → 스택트레이스가 포함된 못생긴 HTML
     → ★ 이때 앱 로그에 안 남을 수 있음!
```

#### Spring Security의 JWT 검증은 Filter에서 수행

```
┌─── Servlet Filter Chain ──────────────────────────────────────┐
│                                                                │
│  ① SecurityContextPersistenceFilter                           │
│  ② HeaderWriterFilter                                         │
│  ③ CorsFilter                                                 │
│  ④ LogoutFilter                                               │
│  ⑤ JwtAuthenticationFilter (커스텀) ★ JWT 검증 여기서!        │
│     │                                                          │
│     ├─ 토큰 유효 → SecurityContext에 Authentication 저장       │
│     │   → 다음 필터로 진행                                     │
│     │                                                          │
│     └─ 토큰 무효/만료 → ???                                    │
│        → 그냥 throw하면 Tomcat이 잡음 (위의 ④-B 케이스)       │
│        → 앱 로그 안 남고, 에러 응답도 제각각                   │
│                                                                │
│  ⑥ UsernamePasswordAuthenticationFilter                       │
│  ⑦ ExceptionTranslationFilter ← Security 예외 변환           │
│  ⑧ FilterSecurityInterceptor ← 인가 (Authorization)          │
│                                                                │
│  ⑨ DispatcherServlet (여기서부터 Spring 세계)                  │
└────────────────────────────────────────────────────────────────┘
```

**핵심**: `ExceptionTranslationFilter(⑦)`는 **자기 뒤에 있는 필터(⑧)**의 예외만 잡음. 커스텀 JWT Filter(⑤)에서 throw하면 `ExceptionTranslationFilter`에 도달하기도 전이라 **Spring Security 예외 처리가 적용 안 됨**.

#### 올바른 JWT Filter 예외 처리

```java
// ❌ 잘못된 방식 — 예외를 그냥 던짐
public class JwtFilter extends OncePerRequestFilter {
    @Override
    protected void doFilterInternal(HttpServletRequest req,
                                     HttpServletResponse resp,
                                     FilterChain chain) {
        String token = extractToken(req);
        if (!jwtProvider.validate(token)) {
            throw new AuthenticationException("Invalid JWT");
            // → Tomcat이 잡음 → 500 HTML 페이지 → 앱 로그 없음
        }
        chain.doFilter(req, resp);
    }
}

// ✅ 올바른 방식 — Filter 안에서 직접 응답 작성
public class JwtFilter extends OncePerRequestFilter {
    @Override
    protected void doFilterInternal(HttpServletRequest req,
                                     HttpServletResponse resp,
                                     FilterChain chain) throws IOException, ServletException {
        try {
            String token = extractToken(req);
            if (token != null && jwtProvider.validate(token)) {
                Authentication auth = jwtProvider.getAuthentication(token);
                SecurityContextHolder.getContext().setAuthentication(auth);
            }
            chain.doFilter(req, resp);
        } catch (JwtException e) {
            log.warn("JWT 검증 실패: {}", e.getMessage());

            // 직접 응답 작성 (DispatcherServlet을 거치지 않으므로)
            resp.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            resp.setContentType("application/json;charset=UTF-8");
            resp.getWriter().write(
                "{\"error\": \"UNAUTHORIZED\", \"message\": \"" + e.getMessage() + "\"}"
            );
        }
    }
}
```

또는 Spring Security의 `AuthenticationEntryPoint`를 활용:

```java
// SecurityConfig에서 entryPoint 설정
@Bean
public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
    http
        .exceptionHandling(ex -> ex
            .authenticationEntryPoint((req, resp, authEx) -> {
                resp.setStatus(401);
                resp.setContentType("application/json;charset=UTF-8");
                resp.getWriter().write("{\"error\": \"인증 필요\"}");
            })
        )
        .addFilterBefore(jwtFilter, UsernamePasswordAuthenticationFilter.class);
    return http.build();
}
```

#### Servlet Container 구현도 Spring에서 할 수 있나?

**Servlet Container ≠ Spring**이지만, Spring Boot가 **내장(Embedded)** Tomcat을 포함하고 있어서 사실상 Spring에서 설정 가능:

```
[관계 정리]

Servlet Container (Tomcat, Jetty, Undertow)
  └── Servlet API 구현체 (javax.servlet / jakarta.servlet)
       └── Spring MVC는 Servlet 위에서 동작
            └── DispatcherServlet = 하나의 Servlet

Spring Boot = 내장 Tomcat을 포함
  → Tomcat 설정을 application.yml이나 Java Config로 제어 가능
  → 하지만 Tomcat 자체가 Spring은 아님
```

```java
// Spring Boot에서 Tomcat 커스터마이징
@Component
public class TomcatCustomizer implements WebServerFactoryCustomizer<TomcatServletWebServerFactory> {
    @Override
    public void customize(TomcatServletWebServerFactory factory) {
        factory.addConnectorCustomizers(connector -> {
            connector.setMaxPostSize(10 * 1024 * 1024);  // 10MB
        });

        // 에러 페이지 등록 (Filter 예외 시 여기로 옴)
        factory.addErrorPages(new ErrorPage(HttpStatus.UNAUTHORIZED, "/error/401"));
    }
}
```

---

### 4. ResponseBody 직렬화 실패 — 이미 200인데 에러

#### 언제 발생하는가

```java
@GetMapping("/users")
public List<UserDto> getUsers() {
    return userService.findAll();
    // Controller 로직은 성공 → Spring이 200 OK 준비
    // → Jackson이 List<UserDto>를 JSON으로 변환 시도
    // → 여기서 실패하면?!
}
```

#### 직렬화 실패가 나는 대표적 케이스

```java
// ① 순환 참조 (가장 흔함)
public class User {
    private List<Order> orders;  // User → Order
}
public class Order {
    private User user;           // Order → User → 무한루프!
}

// ② Lazy Loading 프록시 (Hibernate)
public class User {
    @OneToMany(fetch = FetchType.LAZY)
    private List<Order> orders;
    // Jackson이 getter 호출 → 프록시 초기화 → 세션 이미 닫힘
    // → LazyInitializationException
}

// ③ 직렬화 불가능한 타입
public class Response {
    private InputStream data;  // Jackson이 직렬화 못함
}
```

#### 직렬화 실패 시 실제 흐름

```
Controller 정상 리턴
  → HandlerAdapter
    → RequestResponseBodyMethodProcessor
      → MappingJackson2HttpMessageConverter.write()
        → ObjectMapper.writeValue(outputStream, returnValue)

[여기서 두 가지 시나리오]

시나리오 A: 아직 응답 버퍼가 flush 안 됐을 때
  → HttpMessageNotWritableException 발생
  → DispatcherServlet이 catch
  → @ControllerAdvice에서 처리 가능 ← 다행히 잡힘
  → 500 JSON 에러 응답 가능

시나리오 B: 응답 버퍼가 이미 일부 flush 됐을 때 ★ 진짜 문제
  → 클라이언트는 이미 "HTTP/1.1 200 OK" + 헤더를 받은 상태
  → 응답 body 중간에 에러 발생
  → status code 변경 불가 (이미 200 보냄)
  → resp.isCommitted() == true
  → 클라이언트: 불완전한 JSON 수신 → 파싱 에러
  → ★ @ControllerAdvice 무력화
  → ★ Tomcat catalina.out에만 로그 남을 수 있음
```

```
[시나리오 B의 클라이언트가 받는 응답]

HTTP/1.1 200 OK
Content-Type: application/json

[{"id":1,"name":"홍길동","orders":[{"id":1,"user":{"id":1,"name":"홍길동","orders":[{"id":1,"user":
    ↑ 여기서 끊김 (순환 참조로 StackOverflowError)
```

#### 방지 방법

```java
// ① DTO 분리 (근본 해결)
// Entity를 직접 반환하지 말고 DTO로 변환
public record UserResponse(Long id, String name) {
    public static UserResponse from(User user) {
        return new UserResponse(user.getId(), user.getName());
    }
}

// ② Jackson 설정으로 안전장치
@Configuration
public class JacksonConfig {
    @Bean
    public ObjectMapper objectMapper() {
        ObjectMapper mapper = new ObjectMapper();
        // Lazy 프록시 직렬화 방지
        mapper.registerModule(new Hibernate5JakartaModule());
        // 순환 참조 시 예외 대신 null
        mapper.configure(SerializationFeature.FAIL_ON_SELF_REFERENCES, true);
        return mapper;
    }
}

// ③ 응답 버퍼 사이즈를 충분히 설정
//    버퍼가 크면 flush 전에 에러를 잡을 확률 높아짐
server:
  tomcat:
    max-http-response-header-size: 8KB
```

---

### 사각지대 종합 모니터링 체크리스트

```
┌────────────────────────────────┬──────────────────────────────────────┐
│ 사각지대                        │ 모니터링 방법                         │
├────────────────────────────────┼──────────────────────────────────────┤
│ Tomcat 스레드 풀 포화           │ Micrometer + Prometheus              │
│                                │ tomcat_threads_busy_threads 알림     │
│                                │ Tomcat Access Log 응답 시간 추이      │
├────────────────────────────────┼──────────────────────────────────────┤
│ TCP 큐 오버플로우               │ netstat -s, ss -tnlp                 │
│                                │ node_netstat_* (Prometheus)          │
├────────────────────────────────┼──────────────────────────────────────┤
│ Filter 단 예외 (JWT 등)        │ Filter 내부에서 직접 로깅            │
│                                │ AuthenticationEntryPoint 설정         │
├────────────────────────────────┼──────────────────────────────────────┤
│ @Async 예외 삼킴               │ AsyncUncaughtExceptionHandler 등록   │
│                                │ CompletableFuture로 리턴 타입 변경    │
├────────────────────────────────┼──────────────────────────────────────┤
│ 직렬화 실패 (committed 후)     │ DTO 분리로 근본 방지                 │
│                                │ Tomcat catalina.out 별도 모니터링     │
│                                │ 클라이언트 측 파싱 에러 추적          │
├────────────────────────────────┼──────────────────────────────────────┤
│ OOM / GC 정지                  │ -XX:+HeapDumpOnOutOfMemoryError     │
│                                │ jvm_gc_pause_seconds 메트릭           │
└────────────────────────────────┴──────────────────────────────────────┘
```

## 헷갈렸던 포인트

### Q1. Filter는 Spring 영역인가, Servlet Container 영역인가?

**둘 다**. Servlet Filter 자체는 Servlet 스펙(javax.servlet.Filter)이라 Container가 관리하지만, Spring Boot에서는 `FilterRegistrationBean`이나 `@Component`로 등록하면 Spring이 Filter 인스턴스를 생성하고 DI도 가능함.

```
Tomcat (Container)
  └── FilterChain 실행 순서 관리
       └── 각 Filter 인스턴스 ← Spring이 생성, DI 주입
            └── Filter 안에서 Spring Bean 사용 가능
```

그래서 JWT Filter에서 `@Autowired JwtProvider`를 쓸 수 있는 것. 하지만 **예외 처리 체계는 Container 규칙을 따름** — `@ControllerAdvice`가 안 먹히는 이유.

### Q2. 그러면 Filter 예외를 @ControllerAdvice에서 잡는 방법은 없는가?

직접은 불가능하지만 우회 가능:

```java
// HandlerExceptionResolver를 Filter에서 직접 호출하는 방식
@Component
public class FilterExceptionHandler extends OncePerRequestFilter {

    @Autowired
    private HandlerExceptionResolver resolver;  // "handlerExceptionResolver" Bean

    @Override
    protected void doFilterInternal(HttpServletRequest req,
                                     HttpServletResponse resp,
                                     FilterChain chain) throws IOException, ServletException {
        try {
            chain.doFilter(req, resp);
        } catch (Exception e) {
            // @ControllerAdvice로 예외 위임
            resolver.resolveException(req, resp, null, e);
        }
    }
}

// 이 Filter를 Filter Chain 가장 바깥에 두면
// 다른 모든 Filter의 예외를 잡아서 @ControllerAdvice로 넘길 수 있음
```

### Q3. resp.isCommitted()가 true면 정말 아무것도 못하나?

맞다. HTTP는 스트리밍 프로토콜 — 한번 보낸 status line과 헤더는 되돌릴 수 없음. 할 수 있는 건:

1. 서버 로그에 에러 남기기
2. 연결 강제 종료 (클라이언트가 incomplete response 감지)
3. **사전 방지가 유일한 답** — Entity 직접 반환 금지, DTO 사용

### Q4. Tomcat 외에 Jetty, Undertow는 어떻게 다른가?

스레드 모델이 다르지만 사각지대 패턴은 동일:

| | Tomcat | Jetty | Undertow |
|---|---|---|---|
| 스레드 모델 | NIO + Worker Pool | NIO + QTP | XNIO + Worker Pool |
| 기본 스레드 수 | 200 | 200 | 코어 * 8 |
| Filter 예외 처리 | 동일 | 동일 | 동일 |
| Spring Boot 기본 | ✅ | | |

## 참고 자료

- [Spring Boot — Embedded Servlet Container](https://docs.spring.io/spring-boot/docs/current/reference/html/web.html#web.servlet.embedded-container)
- [Spring Security — Architecture (Filter Chain)](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Tomcat Configuration — HTTP Connector](https://tomcat.apache.org/tomcat-10.1-doc/config/http.html)
