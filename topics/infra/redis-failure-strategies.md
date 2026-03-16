---
title: "Redis 장애 시나리오 분석 및 대응 전략 — 10만 트래픽 호텔 예약 시스템"
parent: Infra / 인프라 미들웨어
nav_order: 3
tags: [Redis, Circuit Breaker, Resilience4j, Caffeine, Sentinel, Cluster, 장애대응, 분산락]
description: "Redis 완전 다운/Slow/부분 장애 시나리오별 대응, Circuit Breaker, 2-Tier 캐싱, Sentinel vs Cluster 비교, 장애 플레이북을 정리합니다."
---

# Redis 장애 시나리오 분석 및 대응 전략 — 호텔 예약 시스템 10만 트래픽

## 핵심 정리

### 1. 현재 시스템 아키텍처 분석

현재 호텔 예약 시스템은 다음과 같은 구조로 되어 있다.

```
Client → Spring Boot API → JPA (Pessimistic Lock) → H2 (In-Memory DB)
```

#### 현재 동시성 제어 방식

- **비관적 락(Pessimistic Lock)**: `SELECT FOR UPDATE`로 재고 행을 잠근다
- **3계층 방어**: Application 검증 → DB Lock → CHECK 제약조건
- **단일 DB 의존**: 모든 읽기/쓰기가 RDB를 직접 타격한다

#### 현재 구조의 한계

10만 트래픽(동시 요청)이 들어오면, 모든 요청이 DB에 직접 접근한다. 특히 객실 가용성 조회(`GET /v1/hotels/{hotelId}/availability`)는 읽기 전용인데도 매번 DB 쿼리를 실행한다. 이는 불필요한 DB 부하를 만든다.

---

### 2. Redis를 도입한 이상적인 아키텍처

10만 트래픽을 감당하려면 Redis를 다음 용도로 활용해야 한다.

```
                          ┌─────────────┐
                          │   Redis     │
                          │  Cluster    │
                          ├─────────────┤
                          │ 1. 캐시     │  → 객실 가용성, 호텔 정보
                          │ 2. 분산 락  │  → 예약/취소 동시성 제어 (Redisson)
                          │ 3. Rate Limit│ → API 요청 제한
                          │ 4. 세션     │  → 사용자 세션 관리
                          └──────┬──────┘
                                 │
Client → API Gateway → Spring Boot API → RDB (MySQL/PostgreSQL)
```

#### 각 용도별 상세

**1. 캐시 (Cache)**

```
GET /v1/hotels/{hotelId}/availability?checkIn=2026-03-10&checkOut=2026-03-12

→ Redis Key: "hotel:1:avail:2026-03-10:2026-03-12"
→ TTL: 30초 ~ 1분
→ 10만 요청 중 99%는 Redis에서 응답, DB 쿼리 1%만 실행
```

- 객실 가용성 조회는 전체 트래픽의 70~80%를 차지하는 읽기 연산이다
- 짧은 TTL(30초)로 설정하면 재고 변동을 거의 실시간으로 반영하면서도 DB 부하를 99% 줄일 수 있다

**2. 분산 락 (Distributed Lock)**

```kotlin
// 현재: DB 비관적 락
@Lock(LockModeType.PESSIMISTIC_WRITE)
fun findByRoomTypeIdAndDateRangeForUpdate(...)

// Redis 도입 후: Redisson 분산 락
val lock = redissonClient.getLock("reservation:roomType:${roomTypeId}:${date}")
lock.tryLock(5, 10, TimeUnit.SECONDS)
try {
    // 재고 확인 및 차감
} finally {
    lock.unlock()
}
```

- DB 커넥션을 점유하지 않으면서 동시성을 제어할 수 있다
- DB 비관적 락은 커넥션 풀을 소진시키지만, Redis 분산 락은 DB 커넥션과 독립적이다

**3. Rate Limiting**

```
Key: "rate:user:{userId}"
Value: 요청 카운트
TTL: 1분
→ 사용자당 분당 100회 요청 제한
→ 악의적 대량 요청 차단
```

**4. 세션 스토어**

- Spring Session + Redis로 세션 관리
- 멀티 인스턴스 환경에서 세션 공유

---

### 3. Redis 장애 시나리오별 영향 분석

#### 시나리오 A: Redis 단일 노드 완전 다운

```
                    X (장애!)
Client → API → [Redis] → DB
```

**발생하는 문제들:**

| 문제 | 영향도 | 상세 |
|------|--------|------|
| 캐시 미스 폭풍 (Cache Stampede) | **치명적** | 10만 요청이 전부 DB로 직행. DB 커넥션 풀 즉시 고갈 |
| 분산 락 실패 | **치명적** | 동시성 제어 불가 → 오버부킹 발생 가능 |
| Rate Limiting 무력화 | **높음** | 악의적 요청을 차단할 수 없음 |
| 세션 유실 | **중간** | 로그인 상태 전체 초기화 |

**구체적 피해 시뮬레이션:**

```
[10만 동시 요청 상황]

평상시 (Redis 정상):
  - Redis 캐시 히트: 95,000건 (Redis에서 직접 응답)
  - DB 쿼리:         5,000건 (캐시 미스 + 쓰기 연산)
  - 평균 응답 시간:    ~50ms
  - DB 커넥션 사용:    50개 / 200개

Redis 장애 시:
  - Redis 캐시 히트:   0건
  - DB 쿼리:         100,000건 (전부 DB로!)
  - 평균 응답 시간:    ~5,000ms → Timeout
  - DB 커넥션 사용:    200개 / 200개 → 고갈 → 503 에러 폭주
```

#### 시나리오 B: Redis 네트워크 지연 (Slow Redis)

완전 다운보다 더 위험한 경우다. Redis가 살아있지만 응답이 느린 상황.

```
Client → API → [Redis ... 3초 대기 ...] → DB
```

**문제:**
- Redis 응답을 기다리느라 스레드가 블로킹된다
- 타임아웃 전까지 스레드 풀이 점유된다
- DB로 폴백하지도 못하고, Redis 응답도 못 받는 "지옥의 대기" 상태

#### 시나리오 C: Redis 부분 장애 (일부 노드만 다운)

Redis Cluster에서 특정 슬롯을 담당하는 노드가 다운된 경우.

```
[Slot 0-5460]    ✓ 정상
[Slot 5461-10922] X 장애
[Slot 10923-16383] ✓ 정상
```

**문제:**
- 특정 키 범위의 데이터만 접근 불가
- 예: "hotel:1" 관련 캐시는 정상인데 "hotel:2" 관련은 장애
- 장애 범위를 예측하기 어려워 디버깅이 힘들다

---

### 4. 대응 전략

#### 전략 1: Circuit Breaker 패턴

Redis 장애를 빠르게 감지하고, 장애 시 DB로 직접 폴백한다.

```
            [Circuit Breaker]
                 │
    ┌────────────┼────────────┐
    │            │            │
 CLOSED      HALF-OPEN      OPEN
 (정상)      (시험 요청)    (차단)
    │            │            │
  Redis로     일부만        전부
  요청        Redis로       DB로
              나머지 DB     직행
```

```kotlin
@Service
class ResilientCacheService(
    private val redisTemplate: RedisTemplate<String, String>,
    private val circuitBreakerFactory: CircuitBreakerFactory<*, *>,
) {
    private val circuitBreaker = circuitBreakerFactory.create("redis")

    fun <T> getOrLoad(key: String, loader: () -> T, ttl: Duration): T {
        return try {
            circuitBreaker.run {
                // Redis에서 조회 시도
                val cached = redisTemplate.opsForValue().get(key)
                if (cached != null) {
                    return@run deserialize(cached)
                }
                // 캐시 미스: DB에서 로드 후 Redis에 저장
                val value = loader()
                redisTemplate.opsForValue().set(key, serialize(value), ttl)
                value
            }
        } catch (e: Exception) {
            // Circuit OPEN 상태: Redis 스킵하고 DB 직접 조회
            log.warn("Redis circuit open, falling back to DB: {}", e.message)
            loader()
        }
    }
}
```

**Resilience4j 설정:**

```yaml
resilience4j:
  circuitbreaker:
    instances:
      redis:
        sliding-window-size: 10           # 최근 10개 요청 기준
        failure-rate-threshold: 50        # 50% 실패 시 OPEN
        wait-duration-in-open-state: 30s  # 30초 후 HALF-OPEN
        permitted-number-of-calls-in-half-open-state: 3  # 3개 시험 요청
  timelimiter:
    instances:
      redis:
        timeout-duration: 500ms           # Redis 응답 500ms 초과 시 실패 처리
```

#### 전략 2: Local Cache + Redis 2-Tier 캐싱

Redis 장애 시 로컬 캐시(Caffeine)가 1차 방어선 역할을 한다.

```
요청 → [L1: Caffeine 로컬 캐시] → [L2: Redis] → [L3: DB]
         (각 인스턴스 메모리)       (공유 캐시)     (원본)
```

```kotlin
@Configuration
class CacheConfig {
    @Bean
    fun cacheManager(): CacheManager {
        val caffeine = Caffeine.newBuilder()
            .maximumSize(10_000)          // 최대 1만 항목
            .expireAfterWrite(10.seconds) // 10초 TTL (Redis보다 짧게)
            .recordStats()                // 히트율 모니터링
            .build<Any, Any>()

        return CaffeineCacheManager().apply {
            setCaffeine(caffeine)
        }
    }
}
```

**각 계층의 역할:**

| 계층 | TTL | 용도 | Redis 장애 시 |
|------|-----|------|---------------|
| L1 (Caffeine) | 10초 | Hot 데이터 즉시 응답 | **유지됨** → 10초간 보호 |
| L2 (Redis) | 1분 | 인스턴스 간 공유 캐시 | **사용 불가** |
| L3 (DB) | - | 원본 데이터 | L1 만료 후 직접 접근 |

**장애 시 효과:**
- Redis가 다운돼도 L1 캐시가 10초간 트래픽을 흡수한다
- 10초 후 L1 만료되면 DB로 가지만, 그 사이에 Circuit Breaker가 작동한다
- 이 10초가 시스템이 장애 모드로 전환할 시간을 벌어준다

#### 전략 3: 분산 락 폴백 — DB 비관적 락 유지

**핵심: 현재 시스템의 비관적 락을 제거하지 않는다.**

```kotlin
@Service
class ReservationService(
    private val redissonClient: RedissonClient,
    private val reservationRepository: ReservationRepository,
) {
    @Transactional
    fun createReservation(command: CreateReservationCommand): ReservationDetail {
        // 1단계: Redis 분산 락 시도 (성능 최적화)
        val redisLock = tryRedisLock(command.roomTypeId, command.dateRange)

        try {
            if (!redisLock.acquired) {
                // Redis 장애 시: DB 비관적 락으로 폴백 (기존 로직 그대로)
                log.warn("Redis 락 실패, DB 비관적 락으로 폴백")
                return createReservationWithDbLock(command)
            }
            // Redis 락 획득 성공: DB 락 없이 빠른 경로
            return createReservationFastPath(command)
        } finally {
            redisLock.releaseIfHeld()
        }
    }

    private fun tryRedisLock(
        roomTypeId: Long,
        dateRange: DateRange
    ): RedisLockResult {
        return try {
            val lock = redissonClient.getLock("reservation:${roomTypeId}")
            val acquired = lock.tryLock(3, 10, TimeUnit.SECONDS)
            RedisLockResult(acquired = acquired, lock = lock)
        } catch (e: Exception) {
            log.warn("Redis 연결 실패: {}", e.message)
            RedisLockResult(acquired = false, lock = null)
        }
    }
}
```

**이 설계의 핵심:**
- Redis 정상 시: Redis 분산 락으로 DB 커넥션 점유 최소화 (성능 UP)
- Redis 장애 시: 기존 DB 비관적 락으로 자동 폴백 (안정성 유지)
- **두 가지를 동시에 유지**하는 것이 포인트다

#### 전략 4: Rate Limiting 폴백

```kotlin
@Component
class RateLimiter(
    private val redisTemplate: RedisTemplate<String, String>,
) {
    // Redis 장애 시 로컬 Rate Limiter로 폴백
    private val localLimiter = ConcurrentHashMap<String, AtomicInteger>()

    fun isAllowed(userId: String, limit: Int): Boolean {
        return try {
            // Redis 기반 글로벌 Rate Limiting
            val key = "rate:$userId"
            val count = redisTemplate.opsForValue().increment(key) ?: 0
            if (count == 1L) {
                redisTemplate.expire(key, Duration.ofMinutes(1))
            }
            count <= limit
        } catch (e: Exception) {
            // 폴백: 인스턴스별 로컬 Rate Limiting
            // 글로벌 정확도는 떨어지지만 기본적인 보호는 가능
            log.warn("Redis 장애, 로컬 Rate Limiter 사용")
            val counter = localLimiter.computeIfAbsent(userId) {
                AtomicInteger(0)
            }
            counter.incrementAndGet() <= limit * 2  // 로컬이므로 한도 2배로 여유
        }
    }
}
```

#### 전략 5: Redis 인프라 고가용성 (HA) 구성

```
                    ┌─────────────────────────────────┐
                    │       Redis Sentinel 클러스터     │
                    │                                  │
                    │  [Sentinel 1] [Sentinel 2] [Sentinel 3]  │
                    │       │            │           │  │
                    │  ┌────┴───┐   ┌────┴───┐      │  │
                    │  │ Master │──→│ Replica │      │  │
                    │  │ (쓰기) │   │ (읽기)  │      │  │
                    │  └────────┘   └────────┘      │  │
                    │                                  │
                    │  Master 장애 시 Replica가        │
                    │  자동으로 Master로 승격 (Failover) │
                    └─────────────────────────────────┘
```

**또는 Redis Cluster 구성:**

```
[Node 1: Slot 0-5460]     <-> [Replica 1]
[Node 2: Slot 5461-10922] <-> [Replica 2]
[Node 3: Slot 10923-16383]<-> [Replica 3]

→ 특정 노드 장애 시 해당 Replica가 자동 승격
→ 데이터 분산으로 단일 노드 부하 분산
```

**Spring Boot 설정:**

```yaml
spring:
  data:
    redis:
      sentinel:
        master: mymaster
        nodes:
          - sentinel1:26379
          - sentinel2:26379
          - sentinel3:26379
      timeout: 500ms
      lettuce:
        pool:
          max-active: 50
          max-idle: 20
          min-idle: 5
```

---

### 5. 장애 대응 플레이북 (운영팀용)

#### Phase 1: 감지 (0~30초)

```
[Prometheus + Grafana 모니터링]

알람 조건:
  - Redis 커넥션 실패율 > 10% (30초 내)
  - Redis 응답 시간 > 500ms (p99 기준)
  - Circuit Breaker OPEN 전환

자동 대응:
  - PagerDuty/Slack 알림
  - Circuit Breaker 자동 OPEN → DB 폴백 시작
```

#### Phase 2: 자동 복구 시도 (30초~5분)

```
[자동 복구 프로세스]

1. Sentinel/Cluster가 장애 감지
2. Replica → Master 자동 승격 (Failover)
3. 애플리케이션 Lettuce 클라이언트가 새 Master 자동 감지
4. Circuit Breaker HALF-OPEN → 시험 요청
5. 성공 시 CLOSED 복귀 → Redis 정상 사용 재개
```

#### Phase 3: 수동 대응 (자동 복구 실패 시)

```
[수동 대응 체크리스트]

- Redis 프로세스 상태 확인 (redis-cli ping)
- 메모리 사용량 확인 (maxmemory 초과 여부)
- 네트워크 연결 확인 (telnet redis-host 6379)
- AOF/RDB 파일 손상 여부 확인
- 필요 시 새 Redis 인스턴스 투입
- 캐시 워밍업 실행 (인기 호텔 데이터 선로딩)
```

#### Phase 4: 캐시 워밍업 (복구 후)

```kotlin
@Component
class CacheWarmupService(
    private val hotelRepository: HotelRepository,
    private val redisTemplate: RedisTemplate<String, String>,
) {
    // Redis 복구 후 호출 → 인기 데이터 미리 캐싱
    fun warmup() {
        val popularHotels = hotelRepository
            .findTop100ByOrderByReservationCountDesc()
        val today = LocalDate.now()
        val nextMonth = today.plusMonths(1)

        popularHotels.forEach { hotel ->
            val availability = availabilityService.getAvailableRoomTypes(
                hotelId = hotel.id,
                checkIn = today,
                checkOut = nextMonth,
                expectedDays = 30
            )
            redisTemplate.opsForValue().set(
                "hotel:${hotel.id}:avail:${today}:${nextMonth}",
                serialize(availability),
                Duration.ofMinutes(1)
            )
        }
        log.info("캐시 워밍업 완료: {}개 호텔 데이터 로딩", popularHotels.size)
    }
}
```

---

### 6. 종합 아키텍처: Redis 장애에도 견디는 시스템

```
                         ┌──── Monitoring ────┐
                         │  Prometheus        │
                         │  Grafana           │
                         │  PagerDuty Alert   │
                         └────────────────────┘
                                  │
Client → [API Gateway] → [Spring Boot App] → [RDB (MySQL)]
              │                  │
              │           ┌──────┴──────┐
              │           │             │
         Rate Limit   [L1 Cache]   [Circuit Breaker]
         (Redis/Local) (Caffeine)   (Resilience4j)
              │           │             │
              │           │        ┌────┴────┐
              │           │        │         │
              │           └───→ [Redis]   [DB 폴백]
              │                 Sentinel    (비관적 락)
              │                 Cluster
              │                    │
              └────────────────────┘

정상 시: Client → L1 캐시(10s) → Redis(1min) → DB
장애 시: Client → L1 캐시(10s) → DB 직접 (Circuit Breaker OPEN)
```

---

## 헷갈렸던 포인트

### Q1: Slow Redis가 완전 다운보다 왜 더 위험한가?

```
[완전 다운]
  Redis 연결 즉시 실패 → Exception → Circuit Breaker OPEN → DB 폴백
  장애 감지: ~수 ms
  → 빠르게 대체 경로로 전환

[Slow Redis]
  Redis 연결 성공 → 응답 대기... 대기... 대기... → 타임아웃 (3초)
  그 3초 동안 스레드가 블로킹됨
  동시 요청 200개 x 3초 대기 = 스레드 풀 전체 점유

  → 새 요청은 스레드를 얻지 못해 큐에 쌓임
  → 큐도 가득 차면 → 503 Service Unavailable
  → Redis뿐 아니라 전체 서비스가 죽음

[해결: 짧은 타임아웃]
  Redis 타임아웃: 500ms (기본값 수 초를 낮춤)
  → 500ms 안에 응답 없으면 즉시 실패 처리 → DB 폴백
```

### Q2: Circuit Breaker OPEN 상태에서 DB가 10만 요청을 감당할 수 있나?

```
[현실적으로 불가능할 수 있다]

  Redis가 95%의 읽기를 흡수하던 상황에서
  갑자기 100% DB로 몰리면 DB도 버틸 수 없다.

[추가 방어책]

  1. Connection Pool Bulkhead
     DB 커넥션 풀을 용도별로 분리:
     - 예약(쓰기): 50개 전용
     - 조회(읽기): 100개 전용
     → 읽기 폭주가 쓰기를 방해하지 못함

  2. 조회 API Rate Limiting 강화
     Redis 장애 감지 시 → 조회 Rate Limit을 1/10로 축소
     → DB 부하를 제한적으로 유지

  3. 읽기 전용 Replica
     Master: 쓰기 전용
     Replica: 읽기 전용 (Redis 장애 시 여기로 라우팅)
     → 쓰기와 읽기의 DB 부하 분리
```

### Q3: Redis Sentinel vs Cluster — 뭘 써야 하나?

```
[Sentinel]
  - Master 1대 + Replica N대
  - Master 장애 시 Replica 자동 승격
  - 모든 데이터가 하나의 Master에 → 메모리 한계
  - 적합: 데이터 < 25GB, 단순 캐시 용도

[Cluster]
  - N개 Master + 각 Replica
  - 데이터를 16384 슬롯으로 분산
  - 수평 확장 가능
  - 적합: 데이터 > 25GB, 대규모 트래픽

[호텔 예약 시스템]
  - 캐시 데이터: 수 GB 수준 → Sentinel로 충분
  - 하지만 10만 트래픽의 처리량 → Cluster가 유리
  - 결론: 트래픽 규모 기준으로 Cluster 추천
```

---

## 핵심 원칙 요약

| 원칙 | 설명 |
|------|------|
| **Graceful Degradation** | Redis 없어도 서비스는 계속 동작한다 (성능만 저하) |
| **No Single Point of Failure** | Redis는 성능 최적화 도구이지, 필수 의존성이 아니다 |
| **Fail Fast** | Redis 장애 감지 시 빠르게 폴백한다 (500ms 타임아웃) |
| **Defense in Depth** | L1 캐시 → Redis → DB, 각 계층이 독립적으로 동작 |
| **Observable** | 모든 폴백/장애 상황을 메트릭과 로그로 추적 가능 |

---

## 참고 자료

| 자료 | 설명 |
|------|------|
| [Resilience4j 공식 문서](https://resilience4j.readme.io/docs) | Circuit Breaker, Retry, Rate Limiter 구현 |
| [Redis Sentinel 공식 문서](https://redis.io/docs/management/sentinel/) | HA 구성 가이드 |
| [Redis Cluster 공식 문서](https://redis.io/docs/management/scaling/) | 클러스터 구성 및 운영 |
| [Caffeine Cache](https://github.com/ben-manes/caffeine) | 고성능 Java 로컬 캐시 라이브러리 |
| [Spring Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html) | Spring 캐시 추상화 가이드 |
