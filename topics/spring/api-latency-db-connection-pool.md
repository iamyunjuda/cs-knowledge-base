---
title: "API 응답 지연의 원인 — DB 커넥션 풀 고갈 분석"
parent: Spring
nav_order: 1
---

# API 응답 지연의 원인 — DB 커넥션 풀 고갈 분석

## 상황

사내 물류 관리 시스템을 운영 중이었음. 창고 관리자들이 매일 아침 재고 현황 리포트를 조회하는 API가 있었는데, 신규 기능 배포 이후 이런 제보가 들어옴:

> "재고 리포트 페이지가 로딩이 안 되고, 간간이 오류 화면이 뜹니다."

모니터링을 확인해보니 재고 리포트 API에서 **HTTP 503/500 에러가 산발적으로 발생** 중이었음. 오전 업무 시작 시간(9시~10시)에 특히 몰렸음.

**P99 응답 시간이 평소의 약 20배** 가까이 치솟은 상태.

P99은 전체 요청 중 가장 느린 1%를 제외한 최대 응답 시간임. 이 값이 높다는 건 거의 모든 사용자가 체감할 수 있는 수준의 지연이 발생하고 있다는 의미.

---

## 수집한 정보

장애 분석을 위해 확인한 항목:

| 항목 | 결과 |
|---|---|
| 로드밸런서 / 네트워크 로그 | 이상 없음 |
| 서버 CPU / 메모리 | 정상 범위 |
| 애플리케이션 에러 로그 | **Exception 없음** |
| 표준 출력 / 표준 에러 | **역시 예외 없음** |
| 외부 API 호출 | **없음** — DB 조회만 수행 |
| 에러 발생 패턴 | 오전 9~10시에 집중 |
| P99 레이턴시 | 평소 대비 **약 20배 상승** |

가장 의아했던 부분:

**"Exception이 한 건도 없는데 왜 500이 나오지?"**

서버 에러는 보통 코드 내부에서 예외가 발생할 때 만들어짐. 그런데 로그 어디에도 예외 기록이 없었음.

이 모순이 핵심 단서였음.

---

## 소거법으로 원인 좁히기

### 네트워크 / 인프라

로드밸런서나 네트워크 단에서 장애가 발생하면 타임아웃이나 커넥션 에러가 동반됨. 그런데 **LB 로그는 깨끗했음**. 배제.

### 서버 리소스 한계

CPU/메모리가 과부하 상태면 전체적으로 느려짐. **두 지표 모두 여유로웠음**. 배제.

### 외부 의존성

외부 서비스가 느려서 내부 API도 느려지는 경우가 있음. 하지만 **이 API는 외부 호출 없이 자체 DB만 사용**함. 배제.

### 코드 레벨 예외

코드에서 Exception이 발생하면 스택 트레이스가 남아야 함. **어디에도 없었음**. 배제.

### 남은 용의자: DB 커넥션 풀

위 후보를 모두 제외하면, **앱과 DB 사이 연결을 관리하는 커넥션 풀**이 유일한 용의자.

---

## 커넥션 풀이란

Spring Boot가 DB 쿼리를 실행하려면 DB 커넥션이 필요함. 매 요청마다 커넥션을 새로 생성하고 닫으면 오버헤드가 크기 때문에, 일정 수의 커넥션을 미리 확보해두고 재활용하는 구조를 사용함. 이 구조가 **커넥션 풀**.

Spring Boot 기본 커넥션 풀은 **HikariCP**.

```
[ 요청 1 ] ──→ [ 풀에서 커넥션 획득 ] ──→ [ 쿼리 수행 ] ──→ [ 커넥션 반환 ]
[ 요청 2 ] ──→ [ 풀에서 커넥션 획득 ] ──→ [ 쿼리 수행 ] ──→ [ 커넥션 반환 ]
[ 요청 3 ] ──→ [ 풀 빈 상태... 대기 ] ──→ ⏳
```

HikariCP 기본 설정:
- `maximumPoolSize`: **10**
- `connectionTimeout`: **30,000ms (30초)**

풀에 10개 커넥션이 전부 사용 중이면, 다음 요청은 **최대 30초간 대기**함. 그 안에 확보 못 하면 `SQLTransientConnectionException` 발생.

---

## 원인 확정

수집한 정보와 커넥션 풀 동작 원리를 대조하면 모두 맞아떨어짐.

### P99 레이턴시가 20배 뛴 이유

오전 업무 시작 시간에 동시 접속이 몰리면 동시 요청 수가 `maximumPoolSize`(10)를 초과함. 초과 요청은 **앞 요청이 커넥션을 반환할 때까지 대기**해야 함.

쿼리 하나가 300ms 걸린다면:

```
실제 응답 시간 = 커넥션 대기 시간 + 쿼리 시간
```

10개가 점유된 상태에서 11~20번째 요청은 약 300ms 대기, 21~30번째는 약 600ms 대기... **대기 시간이 겹겹이 누적**되면서 P99이 폭등함.

### 500/503 에러가 나온 이유

`connectionTimeout`(30초) 내에 커넥션을 확보 못 한 요청은 **타임아웃 예외가 발생하면서 에러 응답**을 반환함.

### Exception이 로그에 안 남은 이유

`@Transactional`이 선언된 메서드는 **AOP 프록시가 메서드 실행 전에 먼저 커넥션을 확보**하려고 시도함. 커넥션 획득 자체가 실패하면 비즈니스 코드에 진입조차 못 하고 프록시 단에서 예외가 터짐. 글로벌 예외 핸들러에서 이 타입을 별도 처리하지 않으면 **500 응답만 나가고 로그에는 아무것도 안 남을 수 있음**.

```
요청 → Filter → DispatcherServlet → AOP Proxy(@Transactional) → [커넥션 획득 실패] → 500
                                                                    ↑
                                                          비즈니스 로직 실행 이전 단계
                                                          → 앱 로그에 기록되지 않음
```

### 오전 시간대에만 집중된 이유

커넥션 풀은 **크기가 고정된 공유 자원**임. 오전 업무 시작과 함께 창고 관리자들이 동시에 리포트를 조회하면 동시 요청 수가 풀 크기를 넘김. 오후에는 조회가 분산되어 문제가 노출되지 않았음.

### CPU/메모리가 멀쩡했던 이유

커넥션을 기다리는 스레드는 **블로킹 상태(WAITING/TIMED_WAITING)**로 들어감. CPU를 소모하지 않고 메모리도 스레드 스택 정도만 사용하므로 모니터링 지표에 변화가 없음.

---

## 왜 배포 이후에 터졌는가

이전에는 문제없다가 배포 후에 발생했다는 점도 분석 대상이었음.

배포에서 변경될 수 있는 요인:

1. **무거운 쿼리 추가**: 재고 이력을 새로 집계하는 로직이 들어가면서 쿼리 시간이 길어짐 → 커넥션 점유 시간 증가 → 풀 소진 속도 가속
2. **트랜잭션 범위 확대**: `@Transactional`로 감싸는 범위가 넓어지면서 커넥션 반환이 지연
3. **인덱스 누락**: 새로 추가된 조건절에 맞는 인덱스가 없어 풀 스캔 발생
4. **N+1 쿼리 유입**: JPA 연관 엔티티의 Lazy Loading으로 쿼리 수 폭증

하나만 해당돼도 **커넥션 점유 시간 증가 → 같은 트래픽에서도 풀 고갈 → 대기/타임아웃** 연쇄로 이어짐.

---

## 해결 과정

### 1단계: 커넥션 풀 모니터링 추가

원인이 커넥션 풀이라면 **풀 상태를 실시간으로 관측할 수 있어야** 함.

HikariCP의 JMX 메트릭을 Spring Boot Actuator + Micrometer로 수집할 수 있음.

```yaml
# application.yml
spring:
  datasource:
    hikari:
      pool-name: InventoryPool
      register-mbeans: true

management:
  metrics:
    enable:
      hikaricp: true
```

주시해야 할 지표:

| 메트릭 | 설명 |
|---|---|
| `hikaricp_connections_active` | 현재 사용 중인 커넥션 수 |
| `hikaricp_connections_idle` | 유휴 커넥션 수 |
| `hikaricp_connections_pending` | 커넥션 대기 중인 스레드 수 |
| `hikaricp_connections_timeout_total` | 타임아웃 누적 횟수 |

**`pending`이 지속적으로 0 초과**면 풀이 부족하다는 확실한 시그널.

### 2단계: 쿼리/트랜잭션 최적화

풀 크기를 늘리는 건 임시 조치일 뿐. 근본적으로는 **커넥션을 잡고 있는 시간을 줄여야** 함.

```java
// 변경 전: 여러 조회를 하나의 큰 트랜잭션으로 묶음
@Transactional
public ReportResponse getInventoryReport(Long warehouseId) {
    WarehouseInfo info = warehouseRepository.findById(warehouseId);
    StockSummary summary = stockRepository.aggregateByWarehouse(warehouseId); // 무거운 집계
    List<Item> lowStockItems = itemRepository.findLowStock(warehouseId);
    return ReportResponse.of(info, summary, lowStockItems);
}

// 변경 후: 읽기 전용 분리 + 범위 축소
@Transactional(readOnly = true)
public StockSummary getStockSummary(Long warehouseId) {
    return stockRepository.aggregateByWarehouse(warehouseId);
}
```

점검 항목:

- **슬로우 쿼리 탐지**: `slow_query_log`, `EXPLAIN ANALYZE`로 실행 계획 확인
- **N+1 제거**: `FETCH JOIN` 또는 `@EntityGraph`로 일괄 로딩
- **인덱스 점검**: 새로 추가된 WHERE 조건에 인덱스가 있는지 확인
- **트랜잭션 최소화**: 읽기 전용 로직은 `@Transactional(readOnly = true)` 적용

### 3단계: 커넥션 풀 사이즈 조정

HikariCP 문서의 권장 공식:

```
Pool Size = (CPU 코어 수 × 2) + 디스크 스핀들 수
```

실무에서는 부하 테스트로 적정값을 찾는 게 정확함.

```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 25        # 기본 10 → 상향
      minimum-idle: 10             # 최소 유휴 커넥션 유지
      connection-timeout: 3000     # 30초 → 3초 (빠른 실패)
      leak-detection-threshold: 15000  # 15초 이상 미반환 시 경고
```

`connection-timeout`을 줄이는 것도 중요함. 30초나 기다려서 실패하는 것보다 **빠르게 실패시키고 재시도 안내를 보여주는 것**이 사용자 경험 측면에서 나음.

### 4단계: 커넥션 풀 타임아웃 예외 핸들링

로그에 예외가 안 남았다는 것 자체가 디버깅을 어렵게 만든 주범이었음. 커넥션 풀 관련 예외를 명시적으로 잡아서 기록해야 함.

```java
@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(SQLTransientConnectionException.class)
    public ResponseEntity<ErrorResponse> handleConnectionPoolTimeout(
            SQLTransientConnectionException e) {
        log.error("[CONN_POOL_EXHAUSTED] 커넥션 풀 타임아웃: {}", e.getMessage(), e);
        return ResponseEntity
            .status(HttpStatus.SERVICE_UNAVAILABLE)
            .body(new ErrorResponse("일시적으로 요청 처리가 지연되고 있습니다. 잠시 후 다시 시도해주세요."));
    }
}
```

---

## 요약

| 현상 | 원인 |
|---|---|
| P99 레이턴시 약 20배 증가 | 커넥션 풀 소진 → 대기 시간 누적 |
| 간헐적 500/503 에러 | 커넥션 획득 타임아웃 |
| 오전 피크에 집중 발생 | 동시 요청 > maximumPoolSize |
| 앱 로그에 예외 없음 | 비즈니스 로직 진입 전 AOP 프록시 단에서 실패 |
| CPU/메모리 정상 | 대기 스레드는 블로킹 상태 — 리소스 미소모 |
| 배포 이후 발생 | 쿼리 부하 증가/트랜잭션 확대로 커넥션 점유 시간 증가 |

핵심 교훈: **"예외 로그가 없다"가 "문제가 없다"를 의미하지 않음.** 비즈니스 코드 바깥의 인프라 레벨 병목은 일반적인 예외 처리로는 감지되지 않음. 커넥션 풀, 스레드 풀, OS 자원 같은 **공유 자원의 모니터링이 필수적**임.

---

## 헷갈렸던 포인트

### Q. 커넥션 풀 타임아웃인데 왜 Exception이 로그에 안 남지?

`@Transactional` 메서드는 실행 전에 AOP 프록시가 먼저 커넥션을 확보함. 여기서 타임아웃이 걸리면 `SQLTransientConnectionException`이 발생하는데, 글로벌 예외 핸들러에서 이 타입을 별도 처리하지 않으면 Spring 기본 에러 응답만 반환되고 로그에는 아무것도 안 남을 수 있음.

HikariCP 내부 로그도 `com.zaxxer.hikari` 로거의 레벨 설정에 따라 출력 여부가 달라짐. WARN 이상만 출력하는 설정이면 일부 타임아웃 로그가 빠질 수 있음.

### Q. 풀 사이즈를 크게 잡으면 해결 아닌가?

아님. DB 측에서도 수용 가능한 커넥션 수에 한계가 있음. MySQL의 `max_connections` 기본값이 151인데, 앱 서버가 3대이고 각각 `maximumPoolSize=60`이면 합산 180으로 DB 한도를 초과함.

커넥션이 많아지면 DB 내부의 **컨텍스트 스위칭 부하**와 **메모리 사용량**도 늘어남. 무작정 키우면 DB 자체 성능이 저하됨.

결국 **커넥션 점유 시간을 줄이는 것**이 근본 해결임. 쿼리 튜닝, 트랜잭션 범위 축소, 불필요한 트랜잭션 제거가 우선.

### Q. `readOnly = true`를 붙이면 뭐가 달라지는데?

JDBC 드라이버에 읽기 전용 힌트를 전달함. MySQL에서는 Read Replica로 라우팅할 수 있고, JPA에서는 **더티 체킹을 생략**해서 메모리와 CPU를 절약함. 플러시 모드도 `MANUAL`로 바뀌어서 불필요한 쓰기 연산을 방지함.

### Q. `leak-detection-threshold`이 뭔데?

HikariCP에서 커넥션을 가져간 뒤 **설정 시간(ms) 안에 반환하지 않으면 경고 로그를 출력**하는 설정. 커넥션 누수를 조기에 탐지하는 목적임. 트랜잭션이 비정상적으로 오래 걸리거나, 커넥션 반환 누락이 있는 코드를 찾을 때 유용함.

---

## 참고 자료

- [HikariCP GitHub — About Pool Sizing](https://github.com/brettwooldridge/HikariCP/wiki/About-Pool-Sizing)
- [Spring Boot — Connection Pool Configuration](https://docs.spring.io/spring-boot/docs/current/reference/html/application-properties.html#application-properties.data.spring.datasource.hikari)
- [Baeldung — Hikari Connection Pool](https://www.baeldung.com/hikaricp)
