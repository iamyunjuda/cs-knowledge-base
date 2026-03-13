---
title: "판매 통계 API가 느려진 진짜 이유 — DB 커넥션 풀 고갈 추적기"
parent: Spring
nav_order: 1
---

# 판매 통계 API가 느려진 진짜 이유 — DB 커넥션 풀 고갈 추적기

## 사건의 시작

튼튼쇼핑이라는 이커머스 서비스가 있다고 해보겠음.

입점사에게 제공하는 판매자 어드민 서비스가 있고, 판매자들은 로그인 후 대시보드에서 판매 통계를 확인함. 어느 날 배포 이후부터 판매자들이 민원을 넣기 시작함.

> "대시보드가 너무 느려요. 가끔은 아예 에러가 뜨기도 합니다."

운영팀이 확인해보니 판매 통계 API에서 **500번대 HTTP 오류**가 간헐적으로 발생하고 있었음. 특히 트래픽이 몰리는 시간대에 집중됨.

**P95 응답 시간이 평소 대비 15배 이상** 치솟은 상태.

여기서 P95란, 전체 요청 100개를 응답 시간 순으로 세웠을 때 95번째 요청의 응답 시간을 의미함. 즉 대부분의 요청이 극심한 지연을 겪고 있다는 뜻.

---

## 수집된 단서 정리

서버 개발자 입장에서 확인할 수 있는 정보를 하나하나 정리해보겠음.

| 관찰 항목 | 상태 |
|---|---|
| 네트워크 / LB 로그 | 정상 — 별다른 오류나 지연 없음 |
| CPU / Memory | 정상 범위 |
| API 애플리케이션 로그 | **예외(Exception) 없음** |
| stdout / stderr 별도 수집 | **예외 없음** |
| 외부 API 호출 | **없음** — DB 트랜잭션만 사용 |
| 500 에러 빈도 | 트래픽 몰리는 시간대에 집중 |
| P95 응답 시간 | 평소 대비 **15배 이상 증가** |

이 단서들을 보고 가장 먼저 느끼는 위화감이 있음.

**"예외가 없는데 500이 뜬다고?"**

보통 500번대 오류는 서버 내부에서 Exception이 터질 때 발생함. 그런데 로그에 Exception이 없음. stdout/stderr까지 뒤져봤는데도 없음.

이 지점이 핵심 단서.

---

## 용의자 후보 세우기

하나씩 소거해보겠음.

### 용의자 1: 네트워크 / 인프라 문제

LB(로드밸런서)나 네트워크 구간에서 문제가 생기면 지연과 500 에러가 동시에 발생할 수 있음. 하지만 **게이트웨이 로그에서 별다른 오류나 지연이 관찰되지 않았음**. 네트워크 레이어는 무혐의.

### 용의자 2: CPU/Memory 리소스 부족

서버 자원이 부족하면 처리 자체가 느려짐. 하지만 **CPU, Memory 모두 정상 범위**. 리소스 병목도 무혐의.

### 용의자 3: 외부 API 의존성

외부 API가 느려지면 내부 API도 덩달아 느려짐. 하지만 **해당 API는 외부 API 호출을 하지 않음**. DB 트랜잭션만 사용. 외부 의존성도 무혐의.

### 용의자 4: 애플리케이션 코드 레벨 Exception

코드 내부에서 예외가 발생하면 500 응답과 함께 스택 트레이스가 남아야 함. 하지만 **API 로그에도, stdout/stderr에도 Exception이 없음**. 코드 레벨 예외도 무혐의.

### 남은 용의자: DB 커넥션 풀

모든 단서를 소거하고 나면 남는 것은 **애플리케이션과 DB 사이의 연결 구간** — 즉 **DB 커넥션 풀**.

---

## DB 커넥션 풀이 뭔데

Spring Boot 애플리케이션이 DB에 쿼리를 날리려면 **DB와의 연결(Connection)**이 필요함. 매 요청마다 연결을 새로 맺고 끊으면 비용이 크기 때문에 미리 일정 개수의 연결을 만들어두고 재사용함. 이 연결들을 담아두는 곳이 **커넥션 풀(Connection Pool)**.

Spring Boot에서 기본으로 사용하는 커넥션 풀 라이브러리는 **HikariCP**.

```
[ 요청 A ] ──→ [ 풀에서 커넥션 꺼냄 ] ──→ [ DB 쿼리 실행 ] ──→ [ 커넥션 반납 ]
[ 요청 B ] ──→ [ 풀에서 커넥션 꺼냄 ] ──→ [ DB 쿼리 실행 ] ──→ [ 커넥션 반납 ]
[ 요청 C ] ──→ [ 풀이 비었음... 대기 ] ──→ ⏳ ...
```

HikariCP의 기본 설정:
- `maximumPoolSize`: 기본값 **10**
- `connectionTimeout`: 기본값 **30,000ms (30초)**

즉, 커넥션 풀에 최대 10개의 연결만 존재하고, 10개가 전부 사용 중이면 다음 요청은 **최대 30초간 대기**함. 30초 안에 커넥션을 확보하지 못하면 `SQLTransientConnectionException`이 발생함.

---

## 범인이 특정되는 순간

여기서 모든 단서가 맞아떨어짐.

### 왜 P95가 15배 이상 증가했는가

트래픽이 몰리면 동시 요청 수가 커넥션 풀의 `maximumPoolSize`를 초과함. 초과한 요청들은 **커넥션을 확보할 때까지 대기**함.

정상적인 쿼리 실행 시간이 200ms라면, 앞선 요청이 커넥션을 반납할 때까지 기다려야 하므로:

```
실제 응답 시간 = 대기 시간 + 쿼리 실행 시간
```

10개 커넥션이 전부 점유된 상태에서 11번째~20번째 요청은 200ms를 대기하고, 21번째~30번째 요청은 400ms를 대기함. 이런 식으로 **대기 시간이 누적되면서 P95가 기하급수적으로 증가**함.

### 왜 500 에러가 발생했는가

`connectionTimeout`(30초) 안에 커넥션을 확보하지 못한 요청은 **타임아웃 예외가 발생**하면서 500 응답을 반환함.

### 왜 애플리케이션 로그에 Exception이 없었는가

**커넥션 풀 타임아웃은 애플리케이션 코드 진입 이전 단계에서 발생**함. 비즈니스 로직이 실행되기도 전에 커넥션 획득 단계에서 실패하므로, 일반적인 try-catch 로직이나 `@ExceptionHandler`에서 잡히지 않을 수 있음.

특히 Spring의 `@Transactional`이 선언된 메서드에서는 **AOP 프록시가 메서드 실행 전에 커넥션을 확보**하려고 시도함. 커넥션 확보 실패 시 프록시 단에서 예외가 발생하는데, 이 예외가 글로벌 예외 핸들러 설정에 따라 **로그에 남지 않을 수 있음**.

```
요청 → Filter → DispatcherServlet → AOP Proxy(@Transactional) → [여기서 커넥션 획득 실패] → 500
                                                                    ↑
                                                          비즈니스 로직 실행 전
                                                          → 애플리케이션 로그에 안 남음
```

### 왜 트래픽 몰리는 시간에 집중되었는가

커넥션 풀은 **고정된 크기의 공유 자원**. 동시 요청이 풀 사이즈를 넘는 순간 대기가 시작되고, 대기가 쌓이면서 타임아웃 확률이 급격히 올라감. 트래픽이 적은 시간에는 풀 사이즈 안에서 처리되므로 문제가 드러나지 않음.

### 왜 CPU/Memory는 정상이었는가

커넥션 풀 대기 상태의 스레드는 **블로킹 상태(WAITING/TIMED_WAITING)**로 전환됨. 블로킹 상태에서는 CPU를 소모하지 않음. 메모리도 스레드 스택 정도만 점유하므로 눈에 띄는 변화가 없음.

---

## 배포 이후 발생한 이유

"기존에는 문제없었는데 배포 후에 발생했다"는 점도 중요한 단서.

배포로 인해 변경되었을 수 있는 것들:

1. **슬로우 쿼리 유발 변경**: 새로운 통계 집계 로직이 추가되면서 쿼리 실행 시간이 길어짐. 커넥션 점유 시간이 늘어나면 풀 고갈 속도가 빨라짐.
2. **트랜잭션 범위 확대**: `@Transactional` 범위가 넓어지면서 커넥션 점유 시간이 증가.
3. **인덱스 누락**: 새로 추가된 쿼리가 적절한 인덱스 없이 Full Table Scan을 수행.
4. **N+1 쿼리 도입**: JPA에서 연관 엔티티를 Lazy Loading으로 가져오면서 쿼리 수가 급증.

이 중 하나라도 해당되면 **커넥션 하나당 점유 시간이 증가** → **같은 트래픽에도 풀이 더 빨리 고갈** → **대기/타임아웃 발생**.

---

## 해결 방향

### 1단계: 즉시 대응 — 커넥션 풀 모니터링 추가

문제의 원인이 커넥션 풀이라면, 먼저 **풀 상태를 관찰할 수 있어야** 함.

HikariCP는 JMX 메트릭을 제공함. Spring Boot Actuator + Micrometer를 통해 다음 지표를 확인할 수 있음:

```yaml
# application.yml
spring:
  datasource:
    hikari:
      pool-name: TunTunPool
      register-mbeans: true

management:
  metrics:
    enable:
      hikaricp: true
```

주요 관찰 지표:

| 메트릭 | 의미 |
|---|---|
| `hikaricp_connections_active` | 현재 사용 중인 커넥션 수 |
| `hikaricp_connections_idle` | 유휴 상태 커넥션 수 |
| `hikaricp_connections_pending` | 커넥션 대기 중인 스레드 수 |
| `hikaricp_connections_timeout_total` | 커넥션 타임아웃 누적 횟수 |

**`pending`이 0보다 큰 상태가 지속**되면 풀이 부족하다는 확실한 신호.

### 2단계: 근본 원인 제거 — 쿼리/트랜잭션 최적화

커넥션 풀 사이즈를 키우는 것은 임시 처방임. 근본적으로는 **커넥션 점유 시간을 줄여야** 함.

```java
// Before: 넓은 트랜잭션 범위
@Transactional
public DashboardResponse getDashboard(Long sellerId) {
    SellerInfo info = sellerRepository.findById(sellerId);     // 쿼리 1
    SalesStats stats = statsRepository.getMonthlyStats(sellerId); // 무거운 쿼리
    List<Product> products = productRepository.findTop10(sellerId); // 쿼리 3
    return DashboardResponse.of(info, stats, products);
}

// After: 트랜잭션 범위 축소 + 읽기 전용 분리
@Transactional(readOnly = true)
public SalesStats getMonthlyStats(Long sellerId) {
    return statsRepository.getMonthlyStats(sellerId);
}
```

핵심 점검 포인트:

- **슬로우 쿼리 식별**: MySQL의 `slow_query_log` 또는 `EXPLAIN ANALYZE`로 실행 계획 확인
- **N+1 쿼리 제거**: `FETCH JOIN` 또는 `@EntityGraph` 적용
- **인덱스 점검**: 새로 추가된 WHERE 조건에 맞는 인덱스 존재 여부 확인
- **트랜잭션 범위 최소화**: 읽기 전용 작업에는 `@Transactional(readOnly = true)` 적용

### 3단계: 커넥션 풀 사이즈 적정화

HikariCP 공식 문서에서 권장하는 풀 사이즈 공식:

```
Pool Size = (core_count * 2) + effective_spindle_count
```

하지만 실무에서는 부하 테스트를 통해 적정값을 찾는 것이 더 정확함.

```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 20        # 기본 10에서 상향
      minimum-idle: 10             # 유휴 커넥션 최소 유지
      connection-timeout: 5000     # 30초 → 5초 (빠른 실패)
      leak-detection-threshold: 10000  # 10초 이상 반납 안 되면 경고
```

`connection-timeout`을 줄이는 것도 중요한 전략. 30초 동안 대기하다 실패하는 것보다, **5초 안에 빠르게 실패하고 사용자에게 "잠시 후 다시 시도해주세요" 메시지를 보여주는 것**이 사용자 경험 측면에서 나음.

### 4단계: 커넥션 풀 타임아웃 로그 명시적 추가

앞서 "로그에 예외가 남지 않았다"는 점이 문제 파악을 늦춘 원인이었음. 커넥션 풀 관련 예외를 명시적으로 잡아서 로그에 남기도록 처리해야 함.

```java
@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(SQLTransientConnectionException.class)
    public ResponseEntity<ErrorResponse> handleConnectionPoolTimeout(
            SQLTransientConnectionException e) {
        log.error("[CONNECTION_POOL_TIMEOUT] 커넥션 풀 타임아웃 발생: {}", e.getMessage(), e);
        return ResponseEntity
            .status(HttpStatus.SERVICE_UNAVAILABLE)
            .body(new ErrorResponse("일시적으로 서비스 처리가 지연되고 있습니다."));
    }
}
```

---

## 정리하면

| 현상 | 원인 |
|---|---|
| P95 응답 시간 15배 증가 | 커넥션 풀 고갈로 인한 대기 시간 누적 |
| 간헐적 500 에러 | 커넥션 획득 타임아웃 (connectionTimeout 초과) |
| 트래픽 몰리는 시간대 집중 | 동시 요청 > maximumPoolSize일 때만 발생 |
| 애플리케이션 예외 없음 | 비즈니스 로직 진입 전, AOP 프록시 단에서 실패 |
| CPU/Memory 정상 | 블로킹 대기 상태 — CPU/Memory 소모 없음 |
| 배포 이후 발생 | 슬로우 쿼리/트랜잭션 범위 확대로 커넥션 점유 시간 증가 |

핵심 교훈: **"예외 로그가 없다"는 것은 "문제가 없다"는 뜻이 아님.** 애플리케이션 코드 바깥에서 발생하는 인프라 레벨 병목은 전통적인 예외 핸들링으로는 포착되지 않음. 커넥션 풀, 스레드 풀, OS 레벨 자원 같은 **공유 자원의 모니터링**이 반드시 병행되어야 함.

---

## 헷갈렸던 포인트

### Q. 커넥션 풀 타임아웃인데 왜 Exception이 안 남는 거임?

`@Transactional` 메서드는 실행 전에 AOP 프록시가 커넥션을 확보함. 이 단계에서 타임아웃이 발생하면 `SQLTransientConnectionException`이 던져지는데, 글로벌 예외 핸들러에서 이 타입을 명시적으로 잡지 않으면 Spring의 기본 에러 처리에 의해 로그 없이 500 응답만 나가는 경우가 있음.

또한 HikariCP의 내부 예외 로그는 `com.zaxxer.hikari` 로거의 레벨에 따라 출력 여부가 달라짐. WARN 이상만 출력하도록 설정되어 있으면 일부 커넥션 타임아웃 로그가 숨겨질 수 있음.

### Q. 커넥션 풀 사이즈를 무조건 늘리면 해결되는 거 아님?

아님. DB 서버도 동시에 수용할 수 있는 커넥션 수에 한계가 있음. MySQL의 `max_connections` 기본값은 151. 애플리케이션 서버가 여러 대라면 `서버 수 × maximumPoolSize`가 DB의 `max_connections`를 초과하면 DB 단에서 거부됨.

또한 커넥션 수가 늘어나면 DB 내부의 **컨텍스트 스위칭 비용**과 **메모리 사용량**이 증가함. 무작정 늘리면 DB 서버 자체의 성능이 저하될 수 있음.

근본적인 해결은 **커넥션 점유 시간을 줄이는 것**. 쿼리 최적화, 트랜잭션 범위 축소, 불필요한 트랜잭션 제거가 먼저.

### Q. `readOnly = true`는 실제로 뭐가 달라지는 건데?

JDBC 드라이버에 `readOnly` 힌트를 전달함. MySQL의 경우 Read Replica로 라우팅될 수 있고, JPA에서는 **더티 체킹을 생략**하여 메모리와 CPU를 절약함. 또한 플러시 모드가 `MANUAL`로 전환되므로 불필요한 DB 쓰기가 방지됨.

### Q. `leak-detection-threshold`은 무슨 설정임?

HikariCP에서 커넥션을 빌려간 후 **지정된 시간(ms) 이내에 반납하지 않으면 경고 로그**를 출력하는 설정. 커넥션 누수(Connection Leak)를 사전에 감지하는 용도. 트랜잭션이 오래 걸리거나, 커넥션을 명시적으로 반납하지 않는 코드가 있을 때 유용함.

---

## 참고 자료

- [HikariCP GitHub — About Pool Sizing](https://github.com/brettwooldridge/HikariCP/wiki/About-Pool-Sizing)
- [Spring Boot — Connection Pool Configuration](https://docs.spring.io/spring-boot/docs/current/reference/html/application-properties.html#application-properties.data.spring.datasource.hikari)
- [Baeldung — Hikari Connection Pool](https://www.baeldung.com/hikaricp)
