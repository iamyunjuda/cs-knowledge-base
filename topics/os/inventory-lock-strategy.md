# 재고 동기화와 Lock 전략 — 이커머스 동시성 문제의 모든 것

## 핵심 정리

재고 차감은 Lock 관련 면접 질문에서 **가장 빈번하게 등장하는 시나리오**다. "선착순 쿠폰"과 본질은 같지만, 재고는 **상품별로 분리**되어 있고, **결제 실패 시 롤백**까지 고려해야 해서 더 복잡하다.

```
핵심 질문: 100개 남은 상품에 200명이 동시에 주문하면?

기대: 100명 성공, 100명 실패 (재고 정확히 0)
현실(Lock 없음): 200명 성공, 재고 -100 → 초과 판매(Overselling)
```

## 헷갈렸던 포인트

> 이 문서는 실무 재고 동기화 문제를 이야기 형식으로 풀어간다.

---

### Q1: 가장 단순한 구현이 왜 터지는가?

일반적인 "읽고 → 검증 → 쓰기" 패턴을 보자.

```java
public void order(Long productId, int quantity) {
    Product product = productRepository.findById(productId);

    if (product.getStock() >= quantity) {     // ① 읽기: 재고 100
        product.setStock(product.getStock() - quantity);  // ② 쓰기: 재고 99
        productRepository.save(product);
    }
}
```

**두 스레드가 동시에 실행하면:**

```
Thread A: ① 읽기 → stock = 100
Thread B: ① 읽기 → stock = 100  (A가 아직 저장 안 함)
Thread A: ② 쓰기 → stock = 99
Thread B: ② 쓰기 → stock = 99  ← 100에서 1을 뺐으니 99라고 판단

결과: 2개 팔렸는데 재고는 1만 줄었다!
```

이것이 **Lost Update** 문제다. 읽기(Read)와 쓰기(Write) 사이에 **간극(gap)**이 있기 때문에 발생한다.

---

### Q2: DB Lock으로 해결하면 되지 않나?

**맞다, 된다.** 하지만 "어떤 Lock을 쓰느냐"에 따라 성능 차이가 극적이다.

#### 방법 1: 비관적 Lock (Pessimistic Lock)

```java
// Spring Data JPA
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("SELECT p FROM Product p WHERE p.id = :id")
Product findByIdForUpdate(@Param("id") Long id);
```

```sql
-- 실제 실행되는 SQL
SELECT * FROM product WHERE id = 1 FOR UPDATE;
```

**동작 흐름:**
```
Thread A: SELECT ... FOR UPDATE → Lock 획득, stock = 100
Thread B: SELECT ... FOR UPDATE → 대기 (A가 Lock 해제할 때까지)
Thread A: UPDATE stock = 99, COMMIT → Lock 해제
Thread B: Lock 획득, stock = 99 → UPDATE stock = 98, COMMIT
```

**확실하지만 문제가 있다:**
- 트래픽이 몰리면 **모든 요청이 줄 서서 대기** → DB 커넥션 풀 고갈
- 100명이 동시에 같은 상품을 주문하면 99명이 대기 중
- **데드락** 위험: 상품 A, B를 동시에 주문하는 경우

```
Thread 1: Lock(상품A) → Lock(상품B) 시도
Thread 2: Lock(상품B) → Lock(상품A) 시도
→ 데드락!
```

#### 방법 2: 낙관적 Lock (Optimistic Lock)

```java
@Entity
public class Product {
    @Version
    private Long version;  // JPA가 자동 관리

    private int stock;
}
```

```sql
-- JPA가 자동 생성하는 SQL
UPDATE product SET stock = 99, version = 6
WHERE id = 1 AND version = 5;
-- 0 rows affected → OptimisticLockException → 재시도
```

**동작 흐름:**
```
Thread A: 읽기 (version=5, stock=100)
Thread B: 읽기 (version=5, stock=100)
Thread A: UPDATE WHERE version=5 → 성공, version=6
Thread B: UPDATE WHERE version=5 → 실패! (이미 version=6)
Thread B: 재시도 → 읽기 (version=6, stock=99) → UPDATE WHERE version=6 → 성공
```

**언제 쓰는가:**
- 충돌이 **드문** 경우에 적합 (대부분의 일반 상품)
- 충돌이 **잦은** 경우 → 재시도 폭탄 → 오히려 비관적 Lock보다 느려진다

```
동시 100명 주문 → 1명 성공, 99명 재시도
→ 99명 중 1명 성공, 98명 재시도
→ ... (최악의 경우 100 + 99 + 98 + ... = 5050번 시도!)
```

---

### Q3: 그러면 실무에서는 어떻게 하나? Redis!

**핵심 아이디어: DB에 Lock을 거는 대신, Redis에서 먼저 재고를 차감하고 DB는 나중에 처리한다.**

```
[주문 요청] → [Redis DECR] → 성공? → [Kafka 이벤트 발행] → [Consumer: DB 처리]
                  │
                  └── 실패 (재고 0 이하) → 즉시 "품절" 응답
```

#### 구현 코드:

```java
@Service
public class OrderService {

    private final StringRedisTemplate redis;
    private final KafkaTemplate<String, OrderEvent> kafka;

    public OrderResponse order(Long productId, int quantity) {
        String key = "stock:" + productId;

        // ① Redis에서 원자적 차감
        Long remaining = redis.opsForValue().decrement(key, quantity);

        if (remaining == null || remaining < 0) {
            // 차감했는데 음수 → 복구 후 품절 응답
            redis.opsForValue().increment(key, quantity);
            return OrderResponse.soldOut();
        }

        // ② 재고 확보 성공 → Kafka로 비동기 처리 위임
        String orderId = UUID.randomUUID().toString();
        try {
            kafka.send("order-topic", new OrderEvent(orderId, productId, quantity)).get();
            return OrderResponse.success(orderId);
        } catch (Exception e) {
            // ③ Kafka 발행 실패 → Redis 재고 복구!
            redis.opsForValue().increment(key, quantity);
            return OrderResponse.fail("주문 처리 실패, 다시 시도해주세요");
        }
    }
}
```

**⚠️ 주의: Kafka 발행 자체가 실패하는 경우**

위 코드에서 `kafka.send().get()`으로 **동기적으로 발행 성공을 확인**한다. 만약 이걸 안 하면:

```
Redis DECR → 99 (✅) → kafka.send() (fire-and-forget) → 응답 반환
                           │
                           └─ Kafka 브로커 장애로 유실! → 주문 처리 안 됨
                              고객은 "성공" 받았는데 실제로는 아무 일도 안 일어남
```

`get()`으로 확인하면 Kafka 응답을 기다리므로 레이턴시가 약간 올라가지만 (~0.5ms → ~2ms), 이벤트 유실을 방지할 수 있다. **정합성이 극도로 중요한 경우(결제 등)에는 Transactional Outbox 패턴(Q4의 전략 2)이 근본적 해결책이다.**

**왜 이게 Lock보다 좋은가:**

| 비교 항목 | DB Lock | Redis DECR |
|-----------|---------|------------|
| 처리 속도 | 수백 TPS | 수만~수십만 TPS |
| Lock 대기 | 있음 (줄 서기) | 없음 (원자적 연산) |
| DB 부하 | 높음 | Redis만 부담, DB는 비동기 |
| 데드락 | 가능 | 불가능 |

---

### Q4: Redis 재고와 DB 재고가 불일치하면?

**이것이 이 구조에서 가장 중요한 질문이다.**

```
시나리오:
1. Redis: stock = 99 (차감 성공)
2. Kafka 이벤트 발행
3. Consumer가 DB 업데이트 시도 → DB 장애로 실패!
4. Redis는 99인데 DB는 100 → 불일치!
```

**해결 전략들:**

#### 전략 1: 재시도 + Dead Letter Queue (DLQ)

**DLQ가 필요한 이유: "Redis는 성공했는데 DB가 실패"하는 경우**

```
정상 흐름:
  Redis DECR → 99 (✅ 재고 확보) → Kafka → Consumer → DB INSERT (✅)

실패 흐름:
  Redis DECR → 99 (✅ 재고 확보) → Kafka → Consumer → DB INSERT (❌ DB 장애!)
  → Redis는 99인데 DB에는 주문이 없다
  → 고객은 "주문 성공" 응답을 받았는데 실제로 처리 안 됨!
```

이때 Consumer가 할 수 있는 것:

```
Kafka Consumer:
  DB INSERT 시도 → 실패 (DB 타임아웃)
  → 재시도 1회 (2초 후) → 실패
  → 재시도 2회 (4초 후) → 실패
  → 재시도 3회 (8초 후) → 여전히 실패
  → 이 메시지를 DLQ(Dead Letter Queue)로 이동
  → 운영팀에 알림 발송
  → DB 복구 후 DLQ 메시지를 다시 처리

DLQ에 있는 메시지 = "Redis에서 재고는 차감했는데 DB 처리가 안 된 주문"
→ 반드시 나중에라도 처리해야 한다 (고객이 돈을 냈으므로)
```

**핵심: DLQ는 "앞단(Redis)에서 못 거른 것"이 아니라, "앞단은 통과했는데 뒷단(DB) 처리가 실패한 것"을 위한 안전망이다.** Redis에서 재고 차감이 실패하면 즉시 품절 응답을 주고 끝이지만, Redis는 성공했는데 DB가 실패하면 그 주문을 어딘가에 보관해야 한다. 그 "어딘가"가 DLQ다.

#### 전략 2: Transactional Outbox 패턴

```
[주문 서비스]
  BEGIN TRANSACTION
    INSERT INTO orders (...)          -- 주문 생성
    INSERT INTO outbox (event_data)   -- 이벤트를 DB에 저장
  COMMIT

[별도 프로세스 (Debezium/Polling)]
  outbox 테이블 변경 감지 → Kafka 발행 → 재고 차감
```

DB 트랜잭션 안에서 이벤트를 저장하므로 **주문과 이벤트가 원자적**이다.

#### 전략 3: 주기적 정합성 검증 (Reconciliation)

```
[Scheduler: 매 5분마다]
  Redis 재고 vs DB 재고 비교
  차이 발생 → 알림 + 자동/수동 보정
```

**실무에서는 전략 1 + 전략 3을 조합하는 경우가 가장 많다.**

---

### Q5: 여러 상품을 동시에 주문하면? (장바구니 문제)

```
장바구니: 상품A 2개 + 상품B 1개 + 상품C 3개
→ 3개 상품의 재고를 "모두 성공 or 모두 실패"로 처리해야 한다
```

#### 방법 1: Redis Lua 스크립트 (원자적 다중 차감)

```lua
-- 여러 상품 재고를 한 번에 원자적으로 차감하는 Lua 스크립트
local keys = KEYS       -- {"stock:A", "stock:B", "stock:C"}
local amounts = ARGV    -- {2, 1, 3}

-- 1단계: 모두 가능한지 먼저 확인
for i = 1, #keys do
    local stock = tonumber(redis.call('GET', keys[i]) or 0)
    if stock < tonumber(amounts[i]) then
        return -i  -- i번째 상품 재고 부족 (음수로 어떤 상품인지 반환)
    end
end

-- 2단계: 모두 가능하면 한꺼번에 차감
for i = 1, #keys do
    redis.call('DECRBY', keys[i], amounts[i])
end

return 0  -- 성공
```

**Lua 스크립트는 Redis에서 원자적으로 실행된다.** 스크립트 실행 중 다른 명령이 끼어들 수 없다.

#### 방법 2: Saga 패턴 (보상 트랜잭션)

```
상품A 재고 차감 → 성공
상품B 재고 차감 → 성공
상품C 재고 차감 → 실패!
→ 보상: 상품B 재고 복구, 상품A 재고 복구
```

MSA 환경에서 상품별 서비스가 분리되어 있을 때 사용한다.

---

### Q6: 타임세일/이벤트처럼 트래픽이 폭발하는 경우는?

**단계별 방어:**

```
[1단계: 프론트엔드]
  - 버튼 클릭 후 비활성화 (중복 요청 방지)
  - 대기열 UI (현재 N번째입니다)

[2단계: API Gateway / Rate Limiter]
  - Token Bucket 알고리즘으로 초당 요청 수 제한
  - 초과 요청 → 429 Too Many Requests

[3단계: Application]
  - Redis DECR로 즉시 재고 판단
  - Kafka로 비동기 처리

[4단계: 추가 방어]
  - 동일 유저 중복 주문 방지 (Redis SET NX로 user:{id}:order:{productId})
  - 봇 방지 (CAPTCHA, 행동 분석)
```

---

### Q7: 면접에서 "재고 동기화 어떻게 하실 건가요?" 라고 물으면

**단계별로 대답하라:**

```
1단계 (기본): "비관적 Lock으로 SELECT FOR UPDATE를 사용합니다"
  → 면접관: "트래픽 높으면요?"

2단계 (중급): "Redis DECR로 재고를 원자적으로 차감하고,
              실제 DB 처리는 Kafka로 비동기 처리합니다"
  → 면접관: "Redis와 DB 불일치는요?"

3단계 (고급): "DLQ 재처리와 주기적 정합성 검증(Reconciliation)을
              병행합니다. 필요하면 Transactional Outbox 패턴을 적용합니다"
  → 면접관: "장바구니처럼 여러 상품이면요?"

4단계 (심화): "Redis Lua 스크립트로 다중 상품 재고를 원자적으로 차감하거나,
              MSA 환경이면 Saga 패턴으로 보상 트랜잭션을 구성합니다"
```

## 참고 자료

- [Redis 원자적 연산 공식 문서](https://redis.io/docs/latest/develop/interact/transactions/)
- [Transactional Outbox Pattern — Microservices.io](https://microservices.io/patterns/data/transactional-outbox.html)
- [Saga Pattern — Microservices.io](https://microservices.io/patterns/data/saga.html)
