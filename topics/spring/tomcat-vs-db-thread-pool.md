---
title: "Tomcat Thread Pool vs DB Connection Pool — 완전히 다른 두 풀의 역할과 관계"
parent: Spring
nav_order: 9
---

# Tomcat Thread Pool vs DB Connection Pool — 완전히 다른 두 풀의 역할과 관계

## 핵심 정리

### 한 줄 요약

**Tomcat Thread Pool**은 HTTP 요청을 처리할 **워커 스레드**를 관리하고, **DB Connection Pool(HikariCP)**은 DB 서버와의 **TCP 커넥션**을 관리한다. 완전히 다른 자원을 풀링하는 별개의 메커니즘이다.

---

### 전체 요청 흐름에서 두 풀의 위치

```
클라이언트 (브라우저/앱)
  │
  │  HTTP 요청
  ▼
┌─────────────────────────────────────────────────────┐
│              Tomcat Thread Pool                      │
│                                                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │ Worker   │ │ Worker   │ │ Worker   │  ...       │
│  │ Thread-1 │ │ Thread-2 │ │ Thread-3 │  (max 200) │
│  └────┬─────┘ └──────────┘ └──────────┘            │
│       │                                              │
│       │  ★ 이 스레드가 요청 하나를 처음부터 끝까지   │
│       │    담당 (Filter → Controller → Service)      │
└───────┼──────────────────────────────────────────────┘
        │
        │  Service에서 DB 접근 필요
        ▼
┌─────────────────────────────────────────────────────┐
│              HikariCP Connection Pool                │
│                                                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │ Conn A   │ │ Conn B   │ │ Conn C   │  ...       │
│  │ (TCP)    │ │ (TCP)    │ │ (TCP)    │  (max 10)  │
│  └────┬─────┘ └──────────┘ └──────────┘            │
└───────┼──────────────────────────────────────────────┘
        │
        │  TCP 커넥션 (이미 맺어져 있음)
        ▼
┌─────────────────────────────────────────────────────┐
│                    DB 서버 (MySQL 등)                 │
│  Session A, Session B, Session C ...                 │
└─────────────────────────────────────────────────────┘
```

---

### 두 풀의 핵심 차이

| | Tomcat Thread Pool | DB Connection Pool (HikariCP) |
|---|---|---|
| **풀링하는 자원** | OS 스레드 (Worker Thread) | TCP 커넥션 (DB 세션) |
| **역할** | HTTP 요청을 받아 처리 | DB에 쿼리를 실행 |
| **기본 크기** | 200 (maxThreads) | 10 (maximumPoolSize) |
| **자원 생성 비용** | 스레드 생성 (~1ms, ~1MB 스택) | TCP 핸드셰이크 + 인증 (~수십ms) |
| **고갈 시 증상** | 새 HTTP 요청 수락 불가 (타임아웃) | 쿼리 실행 불가 (SQLTransientConnectionException) |
| **설정 위치** | `server.tomcat.threads.max` | `spring.datasource.hikari.maximum-pool-size` |
| **관리 주체** | Servlet Container (Tomcat) | Spring/HikariCP |

---

### 왜 크기가 이렇게 다른가 (200 vs 10)

```
Tomcat 스레드 200개가 동시에 DB 커넥션 10개를 나눠 쓰는 구조:

Thread-1   ──요청 처리 중──▶ [커넥션 A 획득] ──쿼리──▶ [반납]
Thread-2   ──요청 처리 중──▶ [커넥션 B 획득] ──쿼리──▶ [반납]
Thread-3   ──요청 처리 중──▶ [대기... 커넥션 없음]──▶ [A 반납됨! 획득] ──쿼리──▶ [반납]
...
Thread-200 ──요청 처리 중──▶ [JSON 파싱만 하고 DB 안 감]

★ 모든 요청이 DB를 쓰는 건 아님
★ DB 쿼리는 보통 수 ms로 빠르게 끝남 → 커넥션 회전율이 높음
★ DB 서버 CPU 코어가 보통 4~16개 → 커넥션이 많으면 오히려 역효과
```

**Tomcat 스레드는 많아야 하는 이유**: 스레드 하나가 요청을 처음부터 끝까지 잡고 있음 (블로킹 모델). 동시 사용자가 많으면 스레드도 많아야 함.

**DB 커넥션은 적어야 하는 이유**: DB 서버의 CPU 코어 수가 한정적. HikariCP 공식 권장 = `(코어 수 × 2) + 디스크 스핀들`. 4코어 DB면 10개 정도가 최적.

---

### 두 풀의 불균형이 만드는 장애

#### 케이스 1: 커넥션 풀 고갈 (Thread 200 >> Connection 10)

```
[상황] 슬로우 쿼리 발생 → 커넥션 반납 지연

Tomcat Threads:
  Thread-1:  ████ DB 커넥션 A 잡고 슬로우 쿼리 실행 중 (30초)
  Thread-2:  ████ DB 커넥션 B 잡고 슬로우 쿼리 실행 중 (30초)
  ...
  Thread-10: ████ DB 커넥션 J 잡고 슬로우 쿼리 실행 중 (30초)
  Thread-11: ████ 커넥션 대기 중... (connectionTimeout 30초)
  Thread-12: ████ 커넥션 대기 중...
  ...
  Thread-200: ████ 커넥션 대기 중...

→ 결과: 190개 스레드가 커넥션 대기로 블로킹
→ 새 HTTP 요청도 처리 불가 (스레드가 전부 대기 중)
→ DB 안 쓰는 API도 같이 죽음! (헬스체크, 정적 자원 등)
```

#### 케이스 2: 스레드 풀 포화 (외부 API 호출 등)

```
[상황] 외부 API 응답 지연 → Tomcat 스레드 고갈

Tomcat Threads:
  Thread-1:   ████ 외부 결제 API 응답 대기 (60초)
  Thread-2:   ████ 외부 결제 API 응답 대기 (60초)
  ...
  Thread-200: ████ 외부 결제 API 응답 대기 (60초)

→ 결과: DB 커넥션은 여유 있지만 스레드가 없음
→ 새 HTTP 요청 자체를 받을 수 없음
→ HikariCP 커넥션은 놀고 있는데 서버는 죽은 상태
```

---

### 스레드와 커넥션의 1:1 관계가 아닌 이유

```
하나의 요청 처리 타임라인:

Tomcat Thread-1의 시간 사용:
├─ JSON 파싱 ──────┤                          ← DB 안 씀
├──────────────────┤ 커넥션 획득 → 쿼리 → 반납 ← DB 씀 (짧음)
├─ 비즈니스 로직 ──┤                          ← DB 안 씀
├──────────────────┤ 커넥션 획득 → 쿼리 → 반납 ← DB 씀 (짧음)
├─ 응답 직렬화 ────┤                          ← DB 안 씀

★ 하나의 요청에서도 커넥션을 잡고 있는 시간은 전체의 일부
★ @Transactional이 없으면 쿼리마다 커넥션을 잡았다 놓았다 함
★ @Transactional이 있으면 트랜잭션 시작~끝까지 커넥션을 점유

→ 그래서 @Transactional 범위를 최소화하는 것이 커넥션 효율에 중요
```

---

### 정리: 어떤 풀이 부족할 때 어디서 터지는가

```
┌──────────────────────────────────────────────────────────────┐
│                        문제 진단 플로우                        │
│                                                              │
│  서버가 느리다!                                               │
│    │                                                         │
│    ├─ 모든 API가 느림 → Tomcat 스레드 풀 확인                 │
│    │   └─ tomcat_threads_busy ≈ max → 스레드 포화!           │
│    │       └─ 원인: 외부 API 지연 / 슬로우 쿼리 / 커넥션 대기 │
│    │                                                         │
│    ├─ DB 관련 API만 느림 → HikariCP 메트릭 확인              │
│    │   └─ hikaricp_connections_pending > 0 → 커넥션 부족!    │
│    │       └─ 원인: 슬로우 쿼리 / 과도한 트랜잭션 범위        │
│    │                                                         │
│    └─ 특정 API만 느림 → 해당 로직 프로파일링                  │
│                                                              │
│  모니터링 키 메트릭:                                          │
│  - tomcat_threads_busy_threads (Tomcat)                      │
│  - hikaricp_connections_active (HikariCP)                    │
│  - hikaricp_connections_pending (커넥션 대기 수)              │
└──────────────────────────────────────────────────────────────┘
```

## 헷갈렸던 포인트

### Q1. "DB Thread Pool"이라는 말을 쓰기도 하는데 그게 뭔가?

두 가지 의미로 쓰임:

1. **애플리케이션 측 커넥션 풀 (HikariCP)**: 엄밀히 Thread Pool이 아니라 **Connection Pool**. TCP 커넥션을 풀링하는 것. 하지만 커넥션을 잡으면 해당 스레드가 블로킹되니까 "스레드를 묶는다"는 의미에서 Thread Pool과 혼용되기도 함.

2. **DB 서버 내부 스레드 풀**: MySQL의 경우 커넥션 하나당 Worker Thread 하나를 할당(one-thread-per-connection). Enterprise 에디션은 Thread Pool 플러그인으로 M:N 매핑 가능. 이건 DB 서버 내부의 이야기.

**결론**: 보통 "DB Thread Pool"이라고 하면 HikariCP 같은 커넥션 풀을 가리키는 경우가 많다. 정확한 용어는 **Connection Pool**.

### Q2. Tomcat 스레드 200개인데 커넥션 10개면, 190개 스레드는 항상 대기하나?

아니다. 모든 요청이 DB를 쓰는 건 아님:

- 정적 자원 요청 → DB 불필요
- 캐시 히트 → DB 불필요
- 인증/인가만 하는 요청 → DB 불필요 (JWT면)
- DB 쿼리가 1~5ms로 빠르면 → 커넥션 회전율이 높아서 10개로 충분

200개 스레드가 **동시에** DB를 쓰는 상황이 아니라면 커넥션 10개로 충분. 동시에 10개 이상이 DB를 써야 할 때만 대기 발생.

### Q3. @Transactional을 크게 잡으면 왜 위험한가?

```java
// ❌ 위험: 커넥션을 오래 점유
@Transactional
public void processOrder(OrderRequest req) {
    Order order = orderRepository.save(req.toEntity());  // DB
    paymentClient.charge(order);         // ★ 외부 API 3초 대기 (커넥션 잡고 있음!)
    notificationService.send(order);     // ★ 알림 전송 2초 (커넥션 잡고 있음!)
    orderRepository.updateStatus(order); // DB
}
// → 5초간 커넥션 1개 점유 → 10개 커넥션이 순식간에 고갈

// ✅ 개선: 트랜잭션 범위 최소화
public void processOrder(OrderRequest req) {
    Order order = saveOrder(req);        // @Transactional 여기만
    paymentClient.charge(order);         // 커넥션 없이 실행
    notificationService.send(order);     // 커넥션 없이 실행
    updateOrderStatus(order);            // @Transactional 여기만
}
```

### Q4. 둘 중 하나만 모니터링해야 한다면?

**HikariCP를 먼저** 모니터링해라. 이유:

- 커넥션 풀 고갈은 Tomcat 스레드 풀 포화로 **연쇄**됨 (커넥션 대기 → 스레드 블로킹 → 스레드 부족)
- 반대는 덜 흔함 (스레드 포화가 커넥션 풀에 영향을 주는 경우는 적음)
- `hikaricp_connections_pending > 0`이면 이미 위험 신호

```yaml
# Spring Boot Actuator에서 둘 다 볼 수 있음
management:
  endpoints:
    web:
      exposure:
        include: metrics, health, prometheus
  metrics:
    tags:
      application: my-app

# 확인 엔드포인트
# GET /actuator/metrics/tomcat.threads.busy
# GET /actuator/metrics/hikaricp.connections.active
# GET /actuator/metrics/hikaricp.connections.pending
```

## 참고 자료

- [Tomcat Configuration — HTTP Connector (maxThreads, acceptCount)](https://tomcat.apache.org/tomcat-10.1-doc/config/http.html)
- [HikariCP — About Pool Sizing](https://github.com/brettwooldridge/HikariCP/wiki/About-Pool-Sizing)
- [Spring Boot — Connection Pool 설정](https://docs.spring.io/spring-boot/docs/current/reference/html/data.html#data.sql.datasource.connection-pool)
