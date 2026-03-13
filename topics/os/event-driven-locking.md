---
title: "이벤트 기반 시스템에서의 Lock 처리 — 초고트래픽 환경의 동시성 제어"
parent: OS / 운영체제
nav_order: 7
---

# 이벤트 기반 시스템에서의 Lock 처리 — 초고트래픽 환경의 동시성 제어

## 핵심 정리

### 문제 상황 설정

이벤트 드리븐 아키텍처에서 수만~수십만 TPS의 트래픽이 들어오고, 특정 리소스에 대해 Lock을 잡아야 하는 상황이다.

```
시나리오: 선착순 100명 한정 쿠폰 발급

T=0.000000초: 사용자 A 요청 도착
T=0.000001초: 사용자 B 요청 도착  ← 0.000001초 차이!
T=0.000001초: 사용자 C 요청 도착  ← B와 동시!
...
T=0.000100초: 사용자 Z 요청 도착
```

## 헷갈렸던 포인트

> 이 문서는 Lock 문제를 단계적으로 파헤치는 대화 형식으로 구성했다.

---

### Q1: 이벤트 기반 시스템에서 Lock이 왜 문제가 되나?

이벤트 드리븐 시스템은 보통 **싱글 스레드 이벤트 루프**(Node.js, Redis, Nginx)거나 **비동기 논블로킹**(Spring WebFlux, Netty) 방식이다.

```
[Event Queue] → [Event Loop] → Handler A → Handler B → Handler C
                    │
                    └─ 하나씩 순서대로 처리 (싱글 스레드)
```

**싱글 스레드면 Lock이 필요 없지 않나?**

맞다, **단일 프로세스 내**에서는 그렇다. 하지만 현실에서는:

1. **다중 인스턴스**: 서버가 여러 대일 때 (K8s Pod 10개)
2. **다중 프로세스**: Node.js cluster 모드, PM2의 fork 모드
3. **분산 환경**: MSA에서 여러 서비스가 같은 리소스에 접근

```
[Pod 1 - Event Loop] ──┐
[Pod 2 - Event Loop] ──┼──→ [공유 리소스: DB의 쿠폰 잔여 수량]
[Pod 3 - Event Loop] ──┘
```

이 상황에서 Lock 없이는 **Race Condition**이 발생한다.

---

### Q2: 0.000001초 차이로 들어온 두 요청, 순서를 어떻게 보장하나?

**결론부터 말하면: "도착 순서"를 완벽히 보장하는 것은 사실상 불가능하고, 그럴 필요도 거의 없다.**

왜 불가능한가:
1. **네트워크 지연 비결정성**: 같은 시간에 보낸 요청도 라우팅 경로에 따라 도착 순서가 바뀐다
2. **NTP 시간 동기화 한계**: 서버 간 시간 동기화 정확도는 보통 ms 단위 (0.000001초 구분 불가)
3. **OS 스케줄링**: 커널의 프로세스 스케줄러가 요청 처리 순서를 바꿀 수 있다

**그러면 어떻게 해야 하나?**

"누가 먼저 도착했는가"가 아니라 **"누가 먼저 Lock을 획득했는가"** 로 문제를 전환한다.

```
요청 A (T=0.000000) ──→ Lock 획득 시도 ──→ 성공! → 처리
요청 B (T=0.000001) ──→ Lock 획득 시도 ──→ 대기... → A 완료 후 획득 → 처리
```

Lock을 FIFO(선입선출) 방식으로 제공하면, Lock 획득 순서가 곧 처리 순서가 된다.

---

### Q3: 분산 환경에서 Lock을 어떻게 잡나? 방법별 비교

#### 방법 1: Redis 분산 Lock (Redlock 아님, 단일 Redis)

```java
// Lettuce + Spring Boot 예시
public boolean tryLock(String key, String value, long ttlMs) {
    return redis.opsForValue()
        .setIfAbsent(key, value, Duration.ofMillis(ttlMs));  // SET NX EX
}

public void unlock(String key, String value) {
    // Lua 스크립트로 원자적 삭제 (본인이 잡은 Lock만 해제)
    String script = """
        if redis.call('get', KEYS[1]) == ARGV[1] then
            return redis.call('del', KEYS[1])
        else
            return 0
        end
    """;
    redis.execute(script, List.of(key), value);
}
```

**Redis의 `SET NX`가 0.000001초 차이를 해결하는 이유:**
- Redis는 **싱글 스레드**로 명령을 처리한다
- 두 요청이 동시에 와도 Redis 내부에서는 **하나씩 순서대로** 실행된다
- 먼저 처리되는 `SET NX`만 성공, 나머지는 실패

```
Pod 1: SET coupon_lock NX EX 3  →  Redis Queue에 먼저 도착  →  OK (성공)
Pod 2: SET coupon_lock NX EX 3  →  Redis Queue에 나중 도착  →  nil (실패)
```

**장점**: 구현 간단, 성능 우수 (수만 TPS)
**단점**: Redis 장애 시 Lock 유실 가능, 단일 장애점

#### 방법 2: Redisson (Redis 기반 고급 분산 Lock)

```java
RLock lock = redisson.getLock("coupon-lock");

try {
    // waitTime: 최대 대기 시간, leaseTime: Lock 유지 시간
    boolean acquired = lock.tryLock(5, 3, TimeUnit.SECONDS);
    if (acquired) {
        // 임계 영역: 쿠폰 잔여 수량 확인 → 차감 → 발급
        issueCoupon(userId);
    }
} finally {
    if (lock.isHeldByCurrentThread()) {
        lock.unlock();
    }
}
```

Redisson이 제공하는 것:
- **Pub/Sub 기반 Lock 대기**: Spin Lock이 아닌 이벤트 알림으로 대기 → CPU 낭비 없음
- **자동 갱신 (Watchdog)**: leaseTime을 지정하지 않으면 30초마다 자동 연장
- **재진입(Reentrant) Lock**: 같은 스레드가 중복 Lock 가능
- **공정(Fair) Lock**: FIFO 순서 보장 옵션

#### 방법 3: DB 비관적 Lock (Pessimistic Lock)

```sql
-- SELECT FOR UPDATE: 해당 행에 대해 배타적 Lock
BEGIN;
SELECT remaining FROM coupon WHERE id = 1 FOR UPDATE;  -- Lock 획득
-- 다른 트랜잭션은 이 행에 접근 시 대기
UPDATE coupon SET remaining = remaining - 1 WHERE id = 1;
COMMIT;  -- Lock 해제
```

**장점**: 추가 인프라 불필요, 데이터 정합성 확실
**단점**: DB에 부하 집중, 대량 트래픽 시 커넥션 풀 고갈, 데드락 위험

#### 방법 4: DB 낙관적 Lock (Optimistic Lock)

```sql
-- 버전 번호로 충돌 감지
SELECT remaining, version FROM coupon WHERE id = 1;
-- version=5, remaining=10 이라고 가정

UPDATE coupon
SET remaining = remaining - 1, version = version + 1
WHERE id = 1 AND version = 5;  -- version이 다르면 0 rows affected → 재시도

-- 0 rows affected → 다른 누군가 먼저 수정함 → 재시도 로직 필요
```

**장점**: Lock 대기 없음, 읽기 성능 좋음
**단점**: 충돌이 많으면 재시도 폭발 → **높은 트래픽에서 비효율적**

#### 방법 5: 메시지 큐를 활용한 직렬화

```
[수만 건 요청] → [Message Queue (Kafka/SQS)] → [Consumer 1개] → [DB 처리]
```

Lock을 잡는 대신 **요청을 큐에 넣어 직렬 처리**한다.

```
요청 A → Queue Offset 0 → Consumer 처리 (1번째)
요청 B → Queue Offset 1 → Consumer 처리 (2번째)
요청 C → Queue Offset 2 → Consumer 처리 (3번째)
```

**장점**: Lock 자체가 필요 없다! 순서도 보장된다.
**단점**: 처리 지연(Latency) 증가, Consumer가 병목이 될 수 있음

---

### Q4: 초당 10만 요청이 오는 선착순 쿠폰 발급, 어떻게 설계하나?

**실무적으로 가장 많이 쓰는 조합:**

```
[Client] → [API Server (다중 Pod)]
                  │
                  ▼
          [Redis DECR로 수량 차감]  ← 원자적 연산, Lock 불필요!
                  │
              수량 > 0 ?
             /        \
           Yes         No
            │           │
            ▼           ▼
    [Kafka에 발급     [즉시 "sold out"
     이벤트 발행]       응답 반환]
            │
            ▼
    [Consumer: DB에 실제 쿠폰 레코드 생성]
```

**핵심 포인트:**

1. **Redis `DECR`은 원자적(Atomic)** 이다
   ```
   DECR coupon:remaining  → 99 (성공)
   DECR coupon:remaining  → 98 (성공)
   ...
   DECR coupon:remaining  → 0  (성공, 마지막 쿠폰)
   DECR coupon:remaining  → -1 (실패! 복구: INCR)
   ```
   - Lock 없이도 동시성 문제가 해결된다
   - Redis의 싱글 스레드 특성 덕분

2. **실제 DB 쓰기는 비동기로** (Kafka Consumer)
   - API는 Redis 결과만 보고 즉시 응답 → 빠른 응답 시간
   - DB 쓰기 실패 시 Dead Letter Queue로 재처리

---

### Q5: Lock을 잡고 있는 서버가 죽으면 어떻게 되나?

이것이 분산 Lock의 가장 어려운 문제 중 하나다.

**시나리오:**
```
Pod 1: Lock 획득 → GC Pause 또는 네트워크 단절 → Lock 만료
Pod 2: Lock 획득 (Pod 1이 만료되었으므로)
Pod 1: GC 복귀 → 자기가 아직 Lock을 가진 줄 알고 처리 진행!
→ 두 Pod가 동시에 임계 영역 실행 → 데이터 정합성 깨짐
```

**해결 방법: Fencing Token**

```
[Lock 서버]
  Pod 1 Lock 획득 → Fencing Token = 34
  Pod 1 Lock 만료
  Pod 2 Lock 획득 → Fencing Token = 35

[DB/Storage 측]
  Pod 1: "Token 34로 업데이트 요청" → DB가 Token 34 < 35 확인 → 거부!
  Pod 2: "Token 35로 업데이트 요청" → 수락
```

- Lock 획득 시마다 단조 증가하는 Fencing Token을 발급
- Storage 측에서 **Token이 더 작은 요청은 거부**
- ZooKeeper의 `zxid`, etcd의 `revision`이 이 역할을 한다

---

### Q6: 이벤트 기반 + Lock, 정리하면 어떤 전략을 써야 하나?

| 상황 | 추천 전략 | 이유 |
|------|----------|------|
| **단일 서버, 단일 스레드** | Lock 불필요 | 이벤트 루프가 직렬 처리 |
| **단일 서버, 멀티 스레드** | `synchronized`, `ReentrantLock` | JVM 내 Lock으로 충분 |
| **다중 서버, 낮은 트래픽** | DB 비관적 Lock | 인프라 추가 불필요 |
| **다중 서버, 높은 트래픽** | Redis 분산 Lock (Redisson) | 높은 성능, 구현 편의 |
| **초고트래픽 + 단순 카운트** | Redis 원자적 연산 (DECR) | Lock 자체가 필요 없음 |
| **순서 보장 필수** | 메시지 큐 직렬 처리 | Kafka Partition 단위 순서 보장 |
| **강한 일관성 필수** | ZooKeeper/etcd 분산 Lock | CP 시스템, Fencing Token 지원 |

---

### Q7: 최종 정리 — Lock은 "정확히 한 번(Exactly Once)" 처리의 핵심이다

```
높은 동시성 환경에서의 설계 원칙:

1. Lock을 안 잡을 수 있으면 안 잡는다 (원자적 연산, 큐 직렬화)
2. 잡아야 한다면 가장 가벼운 Lock을 쓴다 (Redis > DB)
3. Lock의 범위(granularity)를 최소화한다 (글로벌 Lock ❌, Row-level Lock ✅)
4. Lock 유지 시간을 최소화한다 (빠르게 잡고 빠르게 풀기)
5. Lock 장애에 대비한다 (TTL, Fencing Token, Dead Letter Queue)
```

## 참고 자료

- [Martin Kleppmann — How to do distributed locking](https://martin.kleppmann.com/2016/02/08/how-to-do-distributed-locking.html)
- [Redisson 공식 문서 — Distributed Locks](https://redisson.org/docs/data-and-services/locks-and-synchronizers/)
- [Redis SET NX 공식 문서](https://redis.io/commands/set/)
