---
title: "캐싱 전략 심층 분석 — 호텔 예약 vs 콘서트/쿠폰 시스템"
parent: Infra / 인프라 미들웨어
nav_order: 2
---

# 캐싱 전략 심층 분석 — 호텔 예약 vs 콘서트/쿠폰 시스템

## 핵심 정리

### 캐시 갱신 흐름: DB → Redis → Local Cache

모든 데이터의 원본은 DB이며, 갱신 방향은 단방향이다.

```
DB (원본) → Redis (L2 캐시) → Local Cache (L1 캐시)
```

#### 재고 차감 시 캐시 무효화 흐름

```
예약 발생 (어떤 인스턴스든)
   │
   ▼
DB 재고 차감 (UPDATE inventory SET count = count - 1)
   │
   ▼
Redis DEL "hotel:123:deluxe:2026-03-15"  ← 새 값을 넣지 않고 삭제만 함
   │
   ▼
Kafka 이벤트 발행 → 다른 인스턴스의 Local Cache evict
```

Redis에 새 값을 직접 넣는 게 아니라 **삭제만** 한다. 다음 조회 때 자연스럽게 채워지는 구조다.

#### Local Cache는 항상 Redis를 통해 갱신된다

```
요청 도착
   │
   ▼
Local Cache 조회 ── HIT ──→ 즉시 응답 (Redis, DB 안 감)
   │
   MISS
   │
   ▼
Redis 조회 ──── HIT ──→ 그 값을 Local Cache에 저장 후 응답
   │
   MISS (DEL 됐으니까)
   │
   ▼
DB 조회 → Redis에 SET → Local Cache에도 저장 → 응답
```

#### 전체 타임라인 예시

```
T=0s   재고 5개. Redis="5", 모든 Local Cache="5"

T=1s   Server A에서 예약 발생
       ├── DB: 5→4 (UPDATE)
       ├── Redis: DEL (키 삭제)
       ├── Server A Local Cache: evict
       └── Kafka 발행 → Server B,C Local Cache: evict

T=2s   Server B에 조회 요청 도착
       ├── Local Cache: MISS (evict 됐으니까)
       ├── Redis: MISS (DEL 됐으니까)
       ├── DB 조회: 4개
       ├── Redis SET "4" (TTL 1h)
       └── Local Cache 저장 "4" (TTL 5s)

T=3s   Server C에 조회 요청 도착
       ├── Local Cache: MISS (evict 됐으니까)
       ├── Redis: HIT → "4" ← DB까지 안 감!
       └── Local Cache 저장 "4"

T=4s   Server C에 또 조회 요청
       └── Local Cache: HIT → "4" ← Redis까지도 안 감!
```

---

### Stale 데이터: 왜 발생하고, 왜 허용하는가

#### Stale이 발생하는 구간

Stale 데이터는 **Kafka evict가 도착하기 전의 시간 차이** 때문에 발생한다.

```
T=0.000s  Server A: 예약 처리 시작
T=0.001s  Server A: DB UPDATE (5→4)
T=0.002s  Server A: Redis DEL
T=0.003s  Server A: Kafka 발행
                              ↓
                         네트워크 전파 중...
                              ↓
T=0.050s  Server B: Kafka 수신 → Local Cache evict

          ┌─────────────────────────────┐
          │  T=0.003s ~ T=0.050s 사이   │
          │  약 47ms 동안               │
          │  Server B Local Cache = "5" │  ← 이게 Stale!
          │  (아직 evict 안 됨)          │
          └─────────────────────────────┘
```

#### Stale 윈도우 계산

```
max(Stale 기간) = min(Local Cache TTL, Kafka 전파 지연)

실제로는:
- Local Cache TTL: 5초
- Kafka 전파: 보통 10~50ms
→ Stale 윈도우 ≈ 10~50ms (Kafka가 먼저 도착하니까)
```

#### 읽기에 Lock을 걸지 않는 이유

```
┌─────────────────────────────────────────────┐
│            Stale 허용 (캐시)                 │
│                                             │
│  장점: 항상 응답함 (가용성 높음)               │
│  단점: 잠깐 틀린 데이터 보일 수 있음           │
│                                             │
│  유저: "잔여 5개래서 눌렀더니 4개네"            │
│        → 별로 안 불편함                       │
├─────────────────────────────────────────────┤
│            Lock 사용 (정합성)                 │
│                                             │
│  장점: 항상 정확한 데이터                      │
│  단점: Lock 실패 시 에러 (응답 불가)           │
│                                             │
│  유저: "검색이 안 돼요" / "페이지가 안 떠요"    │
│        → 매우 불편함                          │
└─────────────────────────────────────────────┘
```

읽기에 Lock을 걸면 stale은 없지만 가용성을 잃는다. 호텔 검색 페이지가 에러 나는 것이 잔여 객실 수가 1~2개 틀리는 것보다 훨씬 치명적이기 때문에, **읽기에는 stale을 허용**한다.

```
조회 (읽기): Lock ❌ → stale 허용, SELECT로 자유롭게 읽음
예약 (쓰기): Lock ✅ → 정합성 필수, UPDATE + Lock
```

---

### Cache Stampede 방지: 한 놈만 DB 가게 하기

#### 문제: 캐시 전부 MISS → DB 폭주

```
Redis DEL 직후:

  요청 1 → Local MISS → Redis MISS → DB 조회!
  요청 2 → Local MISS → Redis MISS → DB 조회!
  요청 3 → Local MISS → Redis MISS → DB 조회!
  ...
  요청 1000 → Local MISS → Redis MISS → DB 조회!

  DB: 💀
```

#### 해결: setNx를 이용한 분산 락

`setNx`는 **SET if Not eXists**의 약자로, 키가 없을 때만 SET하고 true를 반환하는 atomic 연산이다.

```
redis.setNx("key", "value")

키가 없으면 → SET 하고 true 반환 (Lock 획득 성공)
키가 있으면 → 아무것도 안 하고 false 반환 (Lock 획득 실패)

  요청1: setNx("lock", "1") → 키 없음 → SET → true  ✅
  요청2: setNx("lock", "1") → 키 있음 →      → false ❌
  요청3: setNx("lock", "1") → 키 있음 →      → false ❌

→ 딱 한 놈만 true 받음 = Lock 획득
```

이것이 가능한 이유는 Redis가 싱글 스레드이기 때문이다. "확인"과 "세팅" 사이에 다른 요청이 끼어들 수 없다.

#### 구현

```java
public int getInventory(String key) {
    // 1. Redis 조회
    Integer cached = redis.get(key);
    if (cached != null) return cached;

    // 2. Redis MISS → 락 시도 (TTL 3초: 서버 죽어도 자동 해제)
    boolean locked = redis.setNx(key + ":lock", "1", 3초);

    if (locked) {
        // 내가 대표로 DB 조회
        int value = db.query("SELECT count FROM inventory ...");
        redis.set(key, value, 1시간);
        redis.del(key + ":lock");
        return value;
    } else {
        // 다른 놈이 이미 DB 가고 있음 → 채워질 때까지 재시도
        for (int i = 0; i < 10; i++) {
            Thread.sleep(20);                  // 20ms씩 대기
            Integer result = redis.get(key);
            if (result != null) return result;  // 채워졌으면 바로 리턴
        }
        // 10번 다 실패하면 (200ms) → 내가 직접 DB 조회
        // (Lock 잡은 서버가 죽었을 수 있음)
        return db.query("SELECT count FROM inventory ...");
    }
}
```

#### Lock에 TTL을 거는 이유

```
요청1이 Lock 잡고 DB 조회하러 갔는데 서버가 죽어버리면?
→ DEL을 못 함 → Lock이 영원히 남음 → 아무도 못 들어감

TTL 3초 걸어두면:
→ 서버가 죽어도 3초 후 자동으로 Lock 풀림
```

#### Lock 실패 시 spin retry

```
locked == true 인 놈이 아직 DB 조회 중이면:

  요청2: Lock 실패 → sleep(20ms) → redis.get(key) → null!
  DB 조회가 20ms 안에 안 끝났으면 Redis에 아직 값이 안 채워져 있음

그래서 spin retry가 필요하다:

  T=0ms    요청2: Lock 실패
  T=20ms   redis.get → null (아직)
  T=40ms   redis.get → null (아직)
  T=60ms   redis.get → 42 ✅ (요청1이 채워놨음!)
  return 42

최악의 경우 (요청1 서버가 죽었으면):
  200ms 동안 10번 다 null → 내가 직접 DB 조회
```

#### 같은 Redis 노드에서 관리

재고 캐시 키와 Lock 키는 같은 prefix를 가지므로 같은 노드에서 처리된다.

```
hotel:123:deluxe:20260315          ← 재고 캐시
hotel:123:deluxe:20260315:lock     ← 락

→ 같은 해시슬롯 → 같은 노드 → 싱글 스레드 → atomic
```

#### 현실적인 선택지

| 트래픽 수준 | 전략 | 설명 |
|-------------|------|------|
| 보통 | 중복 DB 조회 허용 | 몇 개 중복은 DB가 감당 가능, Lock 안 씀 |
| 많음 | setNx Lock + spin retry | 한 놈만 DB 가고 나머지 대기 |
| 극대 | Probabilistic Early Expiration | 캐시 만료 전에 미리 갱신, MISS 자체를 안 만듦 |

호텔 예약 수준이면 **중복 DB 조회 허용**으로도 충분하다. 동시에 같은 호텔 같은 날짜를 수천 명이 조회하는 경우는 드물기 때문이다.

---

### 호텔 vs 콘서트/쿠폰: 캐시 전략이 달라야 하는 이유

#### 호텔 예약 — 캐시 효과 극대화

```
특성:
- 재고: 한 호텔에 100~500개 객실
- 예약 속도: 하루에 수십~수백 건 (느림)
- 재고 변동 주기: 분~시간 단위

트래픽 비율:
  조회 ████████████████████████████ 99%
  예약 █                            1%

→ 캐시 HIT율 매우 높음, 캐시 invalidation 빈도 낮음
→ 캐시 효과 극대화
```

#### 콘서트 티켓팅 — 캐시가 오히려 문제

```
특성:
- 재고: 5만석
- 예약 속도: 오픈 후 수초 내 수만 건 (극단적으로 빠름)
- 재고 변동 주기: 밀리초 단위

티켓팅 오픈 순간:
  T=0.000s  재고 50,000
  T=0.001s  재고 49,997  ← 3건 동시
  T=0.010s  재고 49,800  ← 200건
  T=1.000s  재고 42,000  ← 8,000건
  T=5.000s  매진

문제:
  Local Cache TTL 5초? → 5초면 이미 매진됐는데?
  Redis 캐시? → 1ms마다 invalidation → 캐시 의미 없음
  캐시 SET → 즉시 DEL → SET → 즉시 DEL → SET → DEL ...
  → 캐시가 무의미해짐
```

#### 콘서트/쿠폰의 전략: Redis를 Primary 저장소로 승격

**재고 조회: 정확한 숫자 대신 상태만 캐싱**

```
if (remaining > 100)  → "예매 가능"
if (remaining > 0)    → "잔여석 소량"
if (remaining == 0)   → "매진"

→ 상태값은 변동이 적으니 캐싱 가능
→ 유저도 "좌석 49,127석 남음" 같은 정확한 숫자는 필요 없음
```

**실제 좌석 확보: Redis DECR (atomic 연산)**

```java
// Redis를 캐시가 아니라 "Primary 재고 저장소"로 사용
long result = redis.decr("concert:20260501:A구역");  // atomic하게 1 차감

if (result >= 0) {
    // 좌석 확보 성공 → DB에 예약 기록 (비동기)
    queue.publish("reservation", {userId, seatInfo});
} else {
    // 매진
    redis.incr("concert:20260501:A구역");  // 롤백
    return "매진되었습니다";
}
```

**선착순 쿠폰도 동일한 패턴**

```java
// 쿠폰 발급
long result = redis.decr("coupon:event123:remaining");

if (result >= 0) {
    // 쿠폰 발급 성공 → DB 비동기 기록
} else {
    redis.incr("coupon:event123:remaining");  // 롤백
    return "소진되었습니다";
}
```

**Lua Script로 중복 발급 방지까지 atomic하게 처리**

```lua
-- Redis Lua (전체가 atomic하게 실행)
if redis.call('SISMEMBER', 'coupon:users', userId) == 1 then
    return 'ALREADY_ISSUED'      -- 중복 발급 방지
end

local remain = redis.call('DECR', 'coupon:remaining')
if remain >= 0 then
    redis.call('SADD', 'coupon:users', userId)
    return 'SUCCESS'
else
    redis.call('INCR', 'coupon:remaining')
    return 'SOLD_OUT'
end
```

#### 핵심 아키텍처 비교

```
[호텔 예약]
  User → Local Cache → Redis Cache → DB(원본)
  느린 재고 변동, 읽기 최적화

[콘서트/쿠폰]
  User → Redis(원본) → DECR → 성공/실패 즉시 응답
                         │
                         ▼ (비동기)
                        DB 기록 + Kafka 이벤트
  빠른 재고 변동, 쓰기 최적화
```

| | 호텔 | 콘서트/쿠폰 |
|---|---|---|
| 읽기:쓰기 비율 | 99:1 | 1:1 (오픈 순간) |
| 캐시 효과 | 극대화 | 거의 없음 |
| 재고 원본 | DB | Redis |
| 핵심 연산 | SELECT + Cache | DECR (atomic) |
| DB 역할 | 원본 | 비동기 기록용 |

**읽기가 많으면 캐시, 쓰기가 많으면 atomic 연산**이 핵심이다.

---

### Redis 멀티 노드에서의 동시성 보장

#### 단일 노드: 싱글 스레드 → 동시성 문제 없음

```
Redis 노드 1개 = 싱글 스레드 = 명령이 한 줄로 들어옴

  요청A: DECR ──┐
  요청B: DECR ──┤──→ [큐] ──→ DECR → DECR → DECR
  요청C: DECR ──┘         순서대로 하나씩 실행

→ 동시성 문제 불가능
```

#### 멀티 노드: 각 노드가 싱글 스레드 + 키 분리

```
Redis-1: shard1 → 2,500장 (싱글 스레드)
Redis-2: shard2 → 2,500장 (싱글 스레드)
Redis-3: shard3 → 2,500장 (싱글 스레드)

각 노드는 여전히 싱글 스레드!
자기 데이터만 자기가 처리함

  User A → hash("A") % 3 = 1 → Redis-1에서 DECR
  User B → hash("B") % 3 = 2 → Redis-2에서 DECR
  User C → hash("C") % 3 = 1 → Redis-1에서 DECR (A와 같은 노드)

  Redis-1 입장: A, C 요청이 와도 싱글 스레드니까 순서대로 처리
  Redis-2 입장: B 요청만 처리

→ 노드 간 같은 키를 공유하지 않으니 충돌 자체가 없음
```

#### 절대 하면 안 되는 것

```
❌ 같은 키를 여러 노드가 나눠 갖는 경우

  Redis-1: coupon:remaining = 5000
  Redis-2: coupon:remaining = 5000  ← 같은 키 복제!

  User A → Redis-1: DECR → 4999
  User B → Redis-2: DECR → 4999
  → 쿠폰 2장 나갔는데 둘 다 4999

┌─────────────────────────────────────┐
│ 하나의 키는 반드시 하나의 노드에만   │
│ 존재해야 한다 (Redis Cluster 보장)   │
└─────────────────────────────────────┘
```

---

## 헷갈렸던 포인트

### Q1: 왜 Redis DEL 후 새 값을 바로 SET하지 않나?

```
[Cache-Aside 패턴 (Lazy Loading)]

  갱신 시: DEL만 하고, 다음 조회 때 자연스럽게 채움

  왜?
  1. Race Condition 방지
     T=0: 요청A가 DB에서 값 읽음 (4)
     T=1: 요청B가 DB 업데이트 (4→3) 후 Redis SET(3)
     T=2: 요청A가 Redis SET(4)  ← 오래된 값으로 덮어씀!

     DEL만 하면 이 문제 없음:
     T=0: 요청A가 DB에서 값 읽음 (4)
     T=1: 요청B가 DB 업데이트 (4→3) 후 Redis DEL
     T=2: 요청A가 Redis SET(4) → 다음 조회 시 Redis MISS → DB 재조회(3)

     → DEL이 SET 이후에 와도 결국 다음 조회에서 최신값으로 교정됨

  2. 불필요한 캐시 채움 방지
     업데이트했는데 아무도 안 읽으면? → SET은 낭비
     DEL만 하면 → 누가 읽을 때만 캐시 채움
```

### Q2: Local Cache TTL이 5초면 너무 짧지 않나?

```
[TTL 5초의 의미]

  최악의 경우 5초 동안 stale 데이터를 보여줌
  → 호텔 재고가 5초 동안 1~2개 틀릴 수 있음
  → 사용자 경험에 영향 없음

  만약 TTL을 길게 잡으면?
  TTL 60초: Kafka evict 실패 시 60초 동안 stale
  TTL 300초: Kafka evict 실패 시 5분 동안 stale

  → Local Cache TTL = Kafka 장애 시 최대 stale 기간
  → 5~10초가 적절

  Redis 조회 비용: ~1ms (Local Network)
  Local Cache HIT 비용: ~0.01ms

  TTL 5초여도 같은 요청이 초당 100번 오면:
  → Redis 조회 1번 + Local HIT 499번 = 99.8% Local HIT
```

### Q3: Probabilistic Early Expiration은 어떻게 동작하나?

```
[Cache Stampede의 근본 해결: 만료 전에 미리 갱신]

  일반 캐시:
  TTL 도달 → MISS → 여러 요청이 동시에 DB 조회 → Stampede

  Probabilistic Early Expiration:
  TTL 도달 전에 확률적으로 미리 갱신 → MISS가 안 생김

  알고리즘:
  현재시각 - (만료시각 - beta * ln(random())) > 만료시각?
  → true면 미리 갱신

  beta: 재계산 비용에 비례하는 값
  TTL에 가까울수록 갱신 확률 ↑
  여러 요청 중 하나만 확률적으로 당첨 → 한 놈만 갱신

  장점: Lock 불필요, MISS 자체를 방지
  단점: 약간의 불필요한 조기 갱신 발생
```

### Q4: Redis가 죽으면? — 캐시 장애 대응

```
[Redis 장애 시나리오]

  1. Redis 일시 장애 (몇 초)
     → Local Cache가 5초간 버팀
     → Redis 복구 후 자동 정상화

  2. Redis 장시간 장애
     → Circuit Breaker 발동
     → DB 직접 조회 모드로 전환
     → DB 부하 증가 → Connection Pool 제한 + Rate Limiting

  3. Redis 데이터 유실 (재시작)
     → 캐시 Cold Start
     → 점진적 워밍업: 인기 키부터 미리 로드
     → 또는 Stampede 방지 패턴으로 자연 복구

  코드 패턴:
  try {
      return redis.get(key);
  } catch (RedisException e) {
      // Circuit Breaker OPEN → DB Fallback
      return db.query(...);
  }
```

---

## 참고 자료

| 자료 | 설명 |
|------|------|
| [Redis SETNX 공식 문서](https://redis.io/commands/setnx/) | SET if Not eXists 명령어 상세 |
| [Redis Lua Scripting](https://redis.io/docs/interact/programmability/eval-intro/) | Lua 스크립트로 atomic 연산 구현 |
| [Cache Stampede 논문 — Optimal Probabilistic Cache Stampede Prevention](https://cseweb.ucsd.edu/~avattani/papers/cache_stampede.pdf) | XFetch 알고리즘 원본 논문 |
| [Facebook TAO 논문](https://www.usenix.org/system/files/conference/atc13/atc13-bronson.pdf) | Facebook의 분산 캐시 아키텍처 |
| [Redis Cluster 공식 문서](https://redis.io/docs/management/scaling/) | 멀티 노드 키 분배, 해시슬롯 |
