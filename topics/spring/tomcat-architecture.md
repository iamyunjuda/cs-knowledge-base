---
title: "Tomcat 내부 구조 — Catalina, Coyote, Jasper는 각각 뭔가"
parent: Spring
nav_order: 8
---

# Tomcat 내부 구조 — Catalina, Coyote, Jasper는 각각 뭔가

## 핵심 정리

### 한 줄 요약

**Tomcat은 하나의 프로그램이 아니라 3개의 핵심 컴포넌트의 조합**이다. **Coyote**가 HTTP 통신을 담당하고, **Catalina**가 Servlet을 실행하고, **Jasper**가 JSP를 처리한다. 우리가 "Tomcat"이라고 부르는 것의 실체는 대부분 **Catalina**다.

---

### Tomcat의 3대 컴포넌트

```
┌──────────────────────────────────────────────────────────────┐
│                        Apache Tomcat                          │
│                                                              │
│  ┌────────────────┐  ┌─────────────────┐  ┌──────────────┐  │
│  │    Coyote       │  │    Catalina      │  │   Jasper      │  │
│  │  (HTTP 엔진)    │  │  (Servlet 엔진)  │  │  (JSP 엔진)   │  │
│  │                 │  │                  │  │               │  │
│  │  - HTTP 파싱    │  │  - Servlet 관리  │  │  - JSP → Java │  │
│  │  - TCP 연결     │  │  - Filter Chain  │  │  - 컴파일     │  │
│  │  - 요청/응답    │  │  - Session 관리  │  │  - 캐싱       │  │
│  │    객체 생성    │  │  - 컨테이너 구조 │  │               │  │
│  │                 │  │                  │  │  (요즘은 거의 │  │
│  │  ★ 네트워크     │  │  ★ 핵심!         │  │   안 씀)      │  │
│  └───────┬─────────┘  └────────┬─────────┘  └──────────────┘  │
│          │                     │                               │
│          │  Request/Response   │                               │
│          │  객체를 넘겨줌       │                               │
│          └─────────────────────┘                               │
└──────────────────────────────────────────────────────────────┘
```

---

### 각 컴포넌트가 하는 일

#### Coyote — HTTP 통신 담당

```
클라이언트 (브라우저/앱)
    │
    │  TCP 연결 + HTTP 요청
    ▼
┌─────────────── Coyote ───────────────┐
│                                       │
│  ① TCP 연결 수락 (Acceptor Thread)    │
│  ② HTTP 요청 파싱                     │
│     - Method, URI, Headers, Body      │
│     - HTTP/1.1, HTTP/2, AJP 지원     │
│  ③ Request / Response 객체 생성       │
│     - org.apache.coyote.Request       │
│     - org.apache.coyote.Response      │
│  ④ Catalina에 처리 위임               │
│                                       │
│  ★ NIO Connector (기본)               │
│    - maxConnections: 8192             │
│    - acceptCount: 100                 │
│                                       │
│  ★ Coyote는 Servlet이 뭔지 모름!      │
│    그냥 HTTP 프로토콜만 처리           │
└───────────────────────────────────────┘
```

Coyote는 **순수 HTTP 서버**. Servlet 스펙을 전혀 모르고, HTTP 요청을 파싱해서 객체로 만들어 Catalina에 넘기는 역할만 한다.

#### Catalina — Servlet 컨테이너 (핵심)

```
Coyote로부터 Request/Response 수신
    │
    ▼
┌─────────────── Catalina ──────────────────────────────────┐
│                                                            │
│  ┌─── Server ──────────────────────────────────────────┐  │
│  │                                                      │  │
│  │  ┌─── Service ────────────────────────────────────┐  │  │
│  │  │                                                 │  │  │
│  │  │  Connector (Coyote 연결)                        │  │  │
│  │  │       │                                         │  │  │
│  │  │       ▼                                         │  │  │
│  │  │  ┌─── Engine (Catalina) ─────────────────────┐ │  │  │
│  │  │  │                                            │ │  │  │
│  │  │  │  ┌─── Host (localhost) ─────────────────┐  │ │  │  │
│  │  │  │  │                                       │  │ │  │  │
│  │  │  │  │  ┌─── Context (/my-app) ───────────┐ │  │ │  │  │
│  │  │  │  │  │                                  │ │  │ │  │  │
│  │  │  │  │  │  Filter Chain                    │ │  │ │  │  │
│  │  │  │  │  │    → Servlet (DispatcherServlet) │ │  │ │  │  │
│  │  │  │  │  │                                  │ │  │ │  │  │
│  │  │  │  │  └──────────────────────────────────┘ │  │ │  │  │
│  │  │  │  │                                       │  │ │  │  │
│  │  │  │  └───────────────────────────────────────┘  │ │  │  │
│  │  │  │                                            │ │  │  │
│  │  │  └────────────────────────────────────────────┘ │  │  │
│  │  │                                                 │  │  │
│  │  └─────────────────────────────────────────────────┘  │  │
│  │                                                      │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                            │
│  ★ "Catalina"라는 이름은 Tomcat의 Servlet 엔진 코드명       │
│  ★ Server → Service → Engine → Host → Context 계층 구조   │
│  ★ 이 계층이 server.xml에 그대로 반영됨                     │
└────────────────────────────────────────────────────────────┘
```

**Catalina의 계층 구조**:

| 계층 | 역할 | 예시 |
|---|---|---|
| **Server** | Tomcat 인스턴스 전체 | JVM 하나 = Server 하나 |
| **Service** | Connector + Engine 묶음 | 보통 하나 ("Catalina") |
| **Engine** | 요청을 적절한 Host로 라우팅 | 이름이 "Catalina" |
| **Host** | 가상 호스트 (도메인별) | localhost, www.example.com |
| **Context** | 하나의 웹 애플리케이션 | /my-app, / (루트) |
| **Wrapper** | 하나의 Servlet | DispatcherServlet |

```xml
<!-- server.xml — Catalina 계층이 그대로 반영 -->
<Server port="8005" shutdown="SHUTDOWN">
  <Service name="Catalina">
    <Connector port="8080" protocol="HTTP/1.1" />   <!-- Coyote -->
    <Engine name="Catalina" defaultHost="localhost">  <!-- Catalina Engine -->
      <Host name="localhost" appBase="webapps">       <!-- 가상 호스트 -->
        <!-- Context = 웹 애플리케이션 (Spring Boot는 자동 등록) -->
      </Host>
    </Engine>
  </Service>
</Server>
```

#### Jasper — JSP 엔진

```
JSP 파일 → Jasper가 Java Servlet 코드로 변환 → 컴파일 → 실행

index.jsp → index_jsp.java → index_jsp.class → Servlet으로 실행

★ 요즘은 JSP를 거의 안 쓰므로 (React/Vue + REST API 시대)
  Jasper는 사실상 레거시 컴포넌트
★ Spring Boot는 기본적으로 JSP 미지원 (Thymeleaf 권장)
```

---

### catalina.out은 뭔가?

```
Tomcat의 로그 파일 구조:

logs/
├── catalina.out          ← ★ Catalina 엔진의 표준 출력(stdout + stderr)
├── catalina.2026-03-14.log  ← 날짜별 Catalina 로그 (로테이션)
├── localhost.2026-03-14.log ← Host 레벨 로그
├── localhost_access_log.2026-03-14.txt ← HTTP 액세스 로그
└── host-manager.log      ← 관리 앱 로그
```

**catalina.out이 중요한 이유**:

```
Spring 앱 로그 (logback/log4j)
  → 우리가 설정한 로그 파일에 기록
  → 보통 잘 관리됨 ✅

catalina.out
  → JVM의 stdout/stderr가 여기로 감
  → System.out.println()이 여기로 감
  → Spring 밖에서 터진 에러가 여기로 감 ← ★

예를 들어:
  - Filter에서 catch 안 된 예외 → catalina.out
  - Tomcat 커넥터 레벨 에러 → catalina.out
  - OOM 에러 (JVM 레벨) → catalina.out
  - 직렬화 실패 (committed 후) → catalina.out

★ 앱 로그에 안 남는 에러가 catalina.out에는 남는 경우가 많다
★ 장애 분석 시 catalina.out을 반드시 확인해야 하는 이유
```

**Spring Boot 내장 Tomcat에서는?**

```
Spring Boot 내장 Tomcat:
  → catalina.out 파일이 별도로 생기지 않음
  → Tomcat 로그가 Spring의 로깅 프레임워크(Logback)로 통합됨
  → 콘솔(stdout)에 같이 출력됨

독립 Tomcat (WAR 배포):
  → catalina.out이 별도 파일로 존재
  → 무한 증가할 수 있어서 로그 로테이션 필수

# Spring Boot에서 Tomcat 내부 로그 보기
logging:
  level:
    org.apache.catalina: INFO     # Catalina 엔진 로그
    org.apache.coyote: INFO       # Coyote HTTP 로그
    org.apache.tomcat: INFO       # Tomcat 전반
```

---

### 요청 흐름 전체 정리 (Coyote → Catalina → Spring)

```
클라이언트 HTTP 요청
    │
    ▼
┌─── Coyote (HTTP 엔진) ────────────────────────────────────┐
│  Acceptor Thread: TCP 연결 수락                             │
│  Poller Thread: NIO selector로 I/O 이벤트 감지              │
│  Worker Thread Pool: 실제 요청 처리 (maxThreads=200)        │
│                                                             │
│  HTTP 파싱 → Request/Response 객체 생성                     │
└─────────────────┬───────────────────────────────────────────┘
                  │ CoyoteAdapter.service(request, response)
                  ▼
┌─── Catalina (Servlet 엔진) ────────────────────────────────┐
│                                                             │
│  Engine.invoke()                                            │
│    → Host.invoke()                                          │
│      → Context.invoke()                                     │
│        → Valve Pipeline (Tomcat 내부 필터 체인)              │
│          → Filter Chain (Servlet Filter)                    │
│            → Servlet.service()                              │
│              │                                              │
│              ▼                                              │
│  ┌─── Spring DispatcherServlet ────────────────────┐        │
│  │  HandlerMapping → Controller → Service → ...    │        │
│  │  ★ 여기서부터가 우리가 아는 Spring 세계          │        │
│  └─────────────────────────────────────────────────┘        │
│                                                             │
│  예외 발생 시:                                               │
│  ├─ Spring 안에서 발생 → @ControllerAdvice → JSON 응답      │
│  ├─ Filter에서 발생 → Catalina가 catch → /error forward     │
│  │   → BasicErrorController → JSON 또는 HTML                │
│  └─ Catalina에서 발생 → 기본 HTML 에러 페이지 ← ★ 이게 그것│
└─────────────────────────────────────────────────────────────┘
```

---

### Tomcat이 HTML 에러 페이지를 반환하는 이유 (이전 질문 보충)

```
Servlet 스펙의 에러 처리 순서:

① 예외 발생
    │
    ▼
② web.xml의 <error-page> 매핑 확인
   → 매핑 있으면: 해당 페이지로 forward
   → 매핑 없으면: ↓
    │
    ▼
③ Tomcat(Catalina)의 기본 ErrorReportValve 실행
   → org.apache.catalina.valves.ErrorReportValve
   → HTML을 하드코딩으로 생성!

// ErrorReportValve 내부 (실제 코드 요약)
public class ErrorReportValve extends ValveBase {
    protected void report(Request request, Response response, Throwable t) {
        // Content-Type을 강제로 text/html로 설정
        response.setContentType("text/html");
        response.setCharacterEncoding("utf-8");

        StringBuilder sb = new StringBuilder();
        sb.append("<html><head><title>");
        sb.append("HTTP Status ").append(statusCode);
        sb.append("</title></head><body><h1>");
        sb.append("HTTP Status ").append(statusCode);
        // ... HTML 생성
    }
}

★ ErrorReportValve는 Accept 헤더를 확인하지 않음
★ 무조건 text/html로 응답
★ Servlet 스펙이 브라우저 시대에 만들어졌기 때문

Spring Boot의 해결:
  → BasicErrorController가 /error 경로를 가로채서
  → Accept 헤더를 확인하고 JSON 또는 HTML로 분기
  → 하지만 이것도 DispatcherServlet을 거쳐야 작동
```

## 헷갈렸던 포인트

### Q1. "Catalina"라는 이름은 왜 Catalina인가?

Tomcat 개발자가 캘리포니아 산타카탈리나 섬(Santa Catalina Island)에서 이름을 따왔다. Tomcat(수고양이)이라는 이름이 먼저 있었고, 핵심 Servlet 엔진의 코드명으로 Catalina를 붙였다. 기술적 의미는 없고 그냥 코드명이다.

### Q2. Spring Boot 내장 Tomcat에서도 server.xml이 있나?

**없다.** 내장 Tomcat은 server.xml 대신 Java 코드로 프로그래밍 방식으로 설정된다:

```java
// Spring Boot가 내부적으로 하는 일 (자동 설정)
Tomcat tomcat = new Tomcat();
Connector connector = new Connector("HTTP/1.1");  // Coyote
connector.setPort(8080);
tomcat.getService().addConnector(connector);

Context context = tomcat.addContext("", null);     // Catalina Context
Tomcat.addServlet(context, "dispatcher", new DispatcherServlet());
context.addServletMappingDecoded("/", "dispatcher");

tomcat.start();

// application.yml의 server.* 설정이 이 코드에 반영됨
// server.port=8080 → connector.setPort(8080)
// server.tomcat.threads.max=200 → connector의 maxThreads 설정
```

### Q3. Coyote와 Catalina를 분리해놓은 이유는?

**관심사의 분리(Separation of Concerns)**:

```
Coyote: "나는 HTTP만 알아. Servlet이 뭔지 모름."
  → HTTP/1.1, HTTP/2, AJP 등 프로토콜 교체 가능
  → Catalina에 영향 없이 네트워크 레이어만 변경

Catalina: "나는 Servlet만 알아. HTTP가 어떻게 오는지 모름."
  → Servlet 스펙 구현에만 집중
  → Coyote 대신 다른 커넥터를 붙일 수도 있음

이 분리 덕분에:
  - HTTP/2 지원 추가 시 Coyote만 수정
  - Servlet 스펙 업데이트 시 Catalina만 수정
  - AJP (Apache 연동) 지원도 Coyote 레벨에서 처리
```

### Q4. Valve Pipeline은 Filter Chain과 뭐가 다른가?

```
Valve Pipeline (Tomcat/Catalina 내부):
  → Tomcat 자체의 처리 파이프라인
  → ErrorReportValve, AccessLogValve 등
  → Servlet 스펙이 아닌 Tomcat 전용 확장
  → 개발자가 보통 건드리지 않음

Filter Chain (Servlet 스펙):
  → javax.servlet.Filter / jakarta.servlet.Filter
  → Spring Security Filter, CORS Filter 등
  → Servlet 스펙 표준
  → 개발자가 직접 구현

실행 순서:
  Coyote → Valve Pipeline → Filter Chain → Servlet(DispatcherServlet)
                ↑                  ↑
          Tomcat 영역          Servlet 스펙 영역
```

## 참고 자료

- [Apache Tomcat Architecture — Official Docs](https://tomcat.apache.org/tomcat-10.1-doc/architecture/overview.html)
- [Tomcat Configuration — server.xml](https://tomcat.apache.org/tomcat-10.1-doc/config/index.html)
- [Catalina Source — ErrorReportValve](https://github.com/apache/tomcat/blob/main/java/org/apache/catalina/valves/ErrorReportValve.java)
