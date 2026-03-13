---
title: "Kafka 심화 — 정합성, 순서 보장, 핵심 옵션 총정리"
parent: Infra / 인프라 미들웨어
nav_order: 1
---

# Kafka 심화 — 정합성, 순서 보장, 핵심 옵션 총정리

## 핵심 정리

Kafka는 **분산 이벤트 스트리밍 플랫폼**이다. 단순한 메시지 큐가 아니라 **로그 기반 저장소**에 가깝다. 메시지를 소비해도 사라지지 않고, 설정한 기간 동안 보관된다.

```
[Kafka의 핵심 구조]

Producer → [Topic: "order-events"]
            ├── Partition 0: [msg0, msg1, msg2, msg3, ...]  ← offset 순서 보장
            ├── Partition 1: [msg0, msg1, msg2, ...]
            └── Partition 2: [msg0, msg1, msg2, ...]
                                                    ↓
                                              Consumer Group
                                              ├── Consumer A → Partition 0
                                              ├── Consumer B → Partition 1
                                              └── Consumer C → Partition 2
```

**핵심 개념:**
- **Topic**: 메시지의 카테고리 (예: `order-events`, `payment-events`)
- **Partition**: Topic을 나눈 단위. **파티션 내에서만 순서 보장**
- **Offset**: 파티션 내 메시지의 위치 번호 (0, 1, 2, ...)
- **Consumer Group**: 같은 그룹의 Consumer끼리 파티션을 나눠 가짐
- **Broker**: Kafka 서버 노드. 여러 대가 클러스터를 구성

## 헷갈렸던 포인트

---

### Q1: Kafka는 어떻게 순서를 보장하는가?

**결론: Kafka는 "파티션 단위"로만 순서를 보장한다. Topic 전체의 순서는 보장하지 않는다.**

```
[Topic: order-events, 3 Partitions]

Producer가 보낸 순서: A → B → C → D → E → F

실제 파티션 배치:
  Partition 0: [A, D]      ← A 다음에 D (B, C는 다른 파티션)
  Partition 1: [B, E]
  Partition 2: [C, F]

Consumer가 읽는 순서:
  Consumer 0: A → D  (✅ 파티션 내 순서 보장)
  Consumer 1: B → E  (✅)
  Consumer 2: C → F  (✅)

하지만 A, B, C 간의 상대적 순서? → 보장 안 됨!
```

#### 특정 키의 순서를 보장하려면: Partition Key

```java
// 같은 key를 가진 메시지는 같은 파티션으로 간다
kafka.send("order-events", userId, orderEvent);
//                          ^key    ^value

// userId = "user-123"인 모든 메시지 → 항상 Partition 1 (해시 기반)
// userId = "user-456"인 모든 메시지 → 항상 Partition 2
```

```
user-123의 주문: 주문생성 → 결제완료 → 배송시작
  → 모두 Partition 1로 → 순서 보장!

user-456의 주문: 주문생성 → 결제완료 → 배송시작
  → 모두 Partition 2로 → 순서 보장!
```

**실무에서 Key 선택:**

| 상황 | Partition Key | 이유 |
|------|-------------|------|
| 주문 처리 | orderId | 같은 주문의 이벤트 순서 보장 |
| 사용자 행동 추적 | userId | 같은 사용자의 이벤트 순서 보장 |
| 재고 동기화 | productId | 같은 상품의 재고 변경 순서 보장 |
| 결제 | paymentId | 같은 결제의 상태 변경 순서 보장 |

**주의: Key가 편중되면 파티션 불균형 발생**

```
// ❌ 대형 셀러 하나의 주문이 전체 트래픽의 50%라면
key = sellerId
→ Partition 3에 전체 트래픽의 50%가 몰림
→ Consumer 3이 병목, 나머지 Consumer는 놀고 있음

// ✅ orderId를 key로 쓰면 자연스럽게 분산
key = orderId
→ 주문 ID는 고르게 분포 → 파티션 균등 분배
```

---

### Q2: Producer 옵션 — 메시지를 얼마나 안전하게 보낼 것인가?

#### acks — 가장 중요한 옵션

```
[acks=0] "보내고 끝, 확인 안 함"

  Producer → Broker   (응답 안 기다림)

  장점: 가장 빠름
  단점: 메시지 유실 가능 (Broker가 받았는지 모름)
  용도: 로그 수집, 메트릭 등 유실 허용 가능한 경우

[acks=1] "리더만 확인" (기본값)

  Producer → Leader Broker → "OK" 응답
                  │
                  └─ Follower에 복제는 아직 안 됐을 수 있음

  장점: 적당한 속도 + 적당한 안정성
  단점: Leader 장애 시 복제 안 된 메시지 유실 가능
  용도: 대부분의 일반적인 경우

[acks=all (-1)] "모든 ISR 복제 완료 후 확인"

  Producer → Leader Broker → Follower 1 복제 완료
                            → Follower 2 복제 완료
                            → "OK" 응답

  장점: 메시지 유실 거의 불가능
  단점: 가장 느림 (복제 대기 시간)
  용도: 결제, 주문 등 유실 불가 데이터
```

#### ISR (In-Sync Replicas)과 min.insync.replicas

```
[Replication Factor = 3 인 경우]

Partition 0:
  Leader:    Broker 1 (원본)
  Follower:  Broker 2 (복제본)
  Follower:  Broker 3 (복제본)

ISR = {Broker 1, Broker 2, Broker 3}  ← 리더와 동기화된 브로커 목록
```

```
acks=all + min.insync.replicas=2 의 의미:

  "최소 2개 브로커에 복제가 완료되어야 성공 응답"

  Broker 1(Leader) ✅ + Broker 2(Follower) ✅ → OK!
  Broker 3이 느려도 상관없음 (2개면 충분)

  만약 Broker 2, 3 둘 다 죽으면?
  ISR = {Broker 1} → min.insync.replicas=2를 못 채움
  → NotEnoughReplicasException → Producer에 실패 알림
  → 데이터 유실 방지! (1개 브로커에만 있는 건 위험하니까)
```

**실무 권장 설정:**

```properties
# 절대 유실 안 되는 데이터 (결제, 주문)
acks=all
min.insync.replicas=2
replication.factor=3

# 유실 허용 가능 (로그, 메트릭)
acks=1
replication.factor=2
```

#### 기타 Producer 핵심 옵션

```properties
# 재시도 관련
retries=2147483647          # 무한 재시도 (기본값, Kafka 2.1+)
delivery.timeout.ms=120000  # 이 시간 내에 전송 실패하면 포기 (2분)
retry.backoff.ms=100        # 재시도 간 대기 시간

# 배치 관련 (처리량 최적화)
batch.size=16384            # 배치 크기 (16KB)
linger.ms=5                 # 최대 5ms 대기하며 배치에 모음
compression.type=lz4        # 압축 (lz4 권장, snappy도 가능)

# 멱등성 (중복 방지)
enable.idempotence=true     # 네트워크 재시도로 인한 중복 메시지 방지
```

---

### Q3: enable.idempotence — 중복 메시지를 어떻게 방지하나?

네트워크 문제로 **같은 메시지가 두 번 전송**될 수 있다:

```
[enable.idempotence=false]

Producer → Broker: msg A 전송
Broker: 저장 완료, ACK 전송
          │
          └─ 네트워크 장애로 ACK 유실!

Producer: "ACK 안 왔네? 재전송!"
Producer → Broker: msg A 다시 전송
Broker: 또 저장 → msg A가 2번 저장됨! (중복)
```

```
[enable.idempotence=true]

Producer → Broker: msg A (PID=1, Sequence=0)
Broker: 저장 완료, ACK 전송
          │
          └─ ACK 유실!

Producer → Broker: msg A 재전송 (PID=1, Sequence=0)
Broker: "PID=1, Seq=0? 이미 받았잖아" → 무시 (저장 안 함) → ACK 반환
→ 중복 없음!
```

**Producer ID (PID) + Sequence Number**로 각 메시지를 식별한다. 같은 PID + 같은 Sequence면 이미 받은 것으로 간주하고 무시한다.

```
enable.idempotence=true 설정 시 자동으로 변경되는 값:
  acks=all                (강제)
  retries=Integer.MAX     (강제)
  max.in.flight.requests.per.connection ≤ 5  (강제)
```

---

### Q4: Consumer 옵션 — 메시지를 얼마나 정확하게 처리할 것인가?

#### auto.offset.reset — Consumer가 처음 시작하면 어디서부터 읽나?

```
[earliest] — 처음부터 전부 읽기
  Partition: [msg0, msg1, msg2, msg3, msg4]
                ↑ 여기서부터

[latest] — 지금부터 새로운 것만 읽기 (기본값)
  Partition: [msg0, msg1, msg2, msg3, msg4]
                                         ↑ 여기서부터 (이전 건 무시)

[none] — offset 정보가 없으면 에러
```

#### enable.auto.commit — offset을 언제 커밋하나?

```
[enable.auto.commit=true (기본값)]

Consumer: msg 읽기 → 처리 시작 → 5초 지남 → 자동 커밋!
                         │
                         └─ 여기서 Consumer 죽으면?
                            → offset은 커밋됨 → 메시지 유실!
                            (처리 안 했는데 "처리했다"고 기록됨)

[enable.auto.commit=false (수동 커밋)]

Consumer: msg 읽기 → 처리 완료 → 직접 커밋
                                    ↑
                                 처리 완료된 후에만 커밋
                                 → 메시지 유실 방지
```

**수동 커밋 코드:**

```java
@KafkaListener(topics = "order-events")
public void consume(ConsumerRecord<String, OrderEvent> record, Acknowledgment ack) {
    try {
        // 비즈니스 로직 처리
        orderService.processOrder(record.value());

        // 처리 성공 후에만 커밋!
        ack.acknowledge();
    } catch (Exception e) {
        // 커밋 안 함 → 다음에 다시 이 메시지를 받게 됨
        log.error("처리 실패, 재시도 예정: {}", record.value(), e);
    }
}
```

#### Consumer 처리 보증 수준 (Delivery Semantics)

```
[At Most Once — 최대 1번 (유실 가능)]
  offset 먼저 커밋 → 처리
  → 처리 전에 죽으면 메시지 유실

  auto.commit=true가 이 경우에 해당

[At Least Once — 최소 1번 (중복 가능)] ← 가장 많이 사용
  처리 → offset 커밋
  → 처리 후 커밋 전에 죽으면 같은 메시지 다시 받음 (중복)
  → Consumer 측에서 멱등성 보장 필요!

  auto.commit=false + 수동 커밋

[Exactly Once — 정확히 1번]
  Kafka Transactions + Idempotent Producer + Consumer의 read_committed
  → 가장 안전하지만 가장 느림
  → Kafka Streams 내부에서 주로 사용
```

---

### Q5: Exactly Once가 정말 가능한가?

**Kafka 자체로는 가능하다. 하지만 외부 시스템까지 포함하면 사실상 불가능하다.**

```
[Kafka 내부 Exactly Once — Transactional Producer]

producer.initTransactions();
try {
    producer.beginTransaction();
    producer.send(record1);
    producer.send(record2);
    producer.commitTransaction();    // 둘 다 성공하거나 둘 다 실패
} catch (Exception e) {
    producer.abortTransaction();     // 롤백
}
```

```
[하지만 외부 DB까지 포함하면?]

Kafka Consumer:
  1. 메시지 읽기
  2. DB INSERT (외부 시스템)
  3. offset 커밋

  2번은 성공했는데 3번 전에 죽으면?
  → 재시작 시 같은 메시지 다시 받음 → DB에 중복 INSERT!

  Kafka가 DB 트랜잭션을 제어할 수 없다!
```

**실무 해결법: Consumer 측 멱등성 보장**

```java
@KafkaListener(topics = "order-events")
public void consume(OrderEvent event, Acknowledgment ack) {
    // 멱등성 보장: 같은 orderId로 이미 처리했으면 스킵
    if (orderRepository.existsByOrderId(event.getOrderId())) {
        ack.acknowledge();  // 이미 처리됨, 커밋만 하고 넘어감
        return;
    }

    orderRepository.save(new Order(event));
    ack.acknowledge();
}
```

또는 DB의 Unique 제약 조건을 활용:

```sql
-- orderId에 Unique 인덱스 → 중복 INSERT 시 예외 발생
CREATE UNIQUE INDEX idx_order_id ON orders(order_id);
```

---

### Q6: Partition 수는 어떻게 정하나?

**Partition 수 = Consumer 병렬 처리의 상한**

```
Partition 3개 → Consumer 최대 3개까지 병렬 처리
Partition 3개 + Consumer 5개 → 2개 Consumer는 놀고 있음!

Partition 10개 + Consumer 3개 → 각 Consumer가 3~4개 파티션 담당
Partition 10개 + Consumer 10개 → 1:1 매핑, 최대 병렬성
```

**Partition 수 결정 기준:**

```
목표 처리량: 10,000 msg/s
Consumer 1개 처리 능력: 1,000 msg/s (DB 쓰기 포함)
→ 필요한 Partition 수: 10,000 / 1,000 = 최소 10개

여유를 두고: 12~15개 추천
```

**주의: Partition 수는 늘릴 수 있지만 줄일 수 없다!**

```
Partition 3 → 10: 가능 (하지만 기존 Key 기반 라우팅이 깨질 수 있음)
Partition 10 → 3: 불가능! (Topic을 새로 만들어야 함)

Key 해시가 바뀌면:
  user-123 → Partition 1 (3개일 때)
  user-123 → Partition 7 (10개일 때)
  → 같은 유저의 이벤트가 다른 파티션으로! → 순서 깨짐!
```

---

### Q7: Consumer Group과 Rebalancing

```
[Consumer Group: "order-service"]

초기 상태 (Consumer 3개, Partition 6개):
  Consumer A: Partition 0, 1
  Consumer B: Partition 2, 3
  Consumer C: Partition 4, 5

Consumer C가 죽으면 (Rebalancing 발생):
  Consumer A: Partition 0, 1, 4  ← Partition 4 추가
  Consumer B: Partition 2, 3, 5  ← Partition 5 추가
```

**Rebalancing의 문제:**

```
Rebalancing 동안 모든 Consumer가 잠시 멈춘다!

1. Consumer C 장애 감지 (heartbeat 실패, session.timeout.ms 경과)
2. Group Coordinator가 Rebalancing 트리거
3. 모든 Consumer가 파티션 할당 해제 (Stop-the-World!)
4. 새로운 파티션 할당
5. 각 Consumer가 새 파티션에서 읽기 시작

이 과정 동안 메시지 처리가 중단된다!
```

**Rebalancing 최소화 옵션:**

```properties
# Consumer가 살아있는데 느려서 Rebalancing 되는 것 방지
session.timeout.ms=45000         # heartbeat 타임아웃 (기본 45초)
heartbeat.interval.ms=15000      # heartbeat 주기 (session.timeout의 1/3)
max.poll.interval.ms=300000      # poll() 간 최대 간격 (기본 5분)
max.poll.records=500             # 한 번에 가져오는 메시지 수

# Cooperative Rebalancing (Kafka 2.4+)
# → Stop-the-World 없이 점진적 파티션 이동
partition.assignment.strategy=
  org.apache.kafka.clients.consumer.CooperativeStickyAssignor
```

**CooperativeStickyAssignor:**

```
[기존 Eager Rebalancing]
  Rebalancing 시작 → 모든 파티션 해제 → 전부 재할당
  → 전체 Consumer가 멈춤

[Cooperative Rebalancing]
  Rebalancing 시작 → 이동이 필요한 파티션만 해제 → 해당 파티션만 재할당
  → 나머지 Consumer는 계속 처리 중!
```

---

### Q8: 핵심 옵션 총정리 — 실무 설정 가이드

#### 결제/주문 (유실 불가, 순서 중요)

```properties
# Producer
acks=all
enable.idempotence=true
min.insync.replicas=2
replication.factor=3
compression.type=lz4

# Consumer
enable.auto.commit=false
auto.offset.reset=earliest
isolation.level=read_committed   # Transactional Producer 쓰면

# Topic
partitions=12                    # 충분한 병렬성
retention.ms=604800000           # 7일 보관
```

#### 로그/메트릭 (처리량 중요, 유실 허용)

```properties
# Producer
acks=1
batch.size=65536
linger.ms=10
compression.type=snappy

# Consumer
enable.auto.commit=true
auto.offset.reset=latest

# Topic
partitions=30                    # 높은 처리량
retention.ms=86400000            # 1일 보관
```

#### 이벤트 소싱 (정합성 + 감사 추적)

```properties
# Producer
acks=all
enable.idempotence=true
min.insync.replicas=2

# Consumer
enable.auto.commit=false
auto.offset.reset=earliest

# Topic
partitions=20
retention.ms=-1                  # 영구 보관!
cleanup.policy=compact           # 같은 Key의 최신 값만 유지
```

---

### Q9: 면접에서 "Kafka 순서 보장 어떻게 하나요?" 라고 물으면

```
1단계 (기본):
  "파티션 내에서 순서가 보장됩니다.
   같은 Key를 가진 메시지는 같은 파티션으로 가므로,
   Key 기반으로 순서를 보장합니다"

2단계 (심화):
  "enable.idempotence=true로 네트워크 재시도 시 중복과 순서 역전을 방지하고,
   max.in.flight.requests.per.connection ≤ 5로 파이프라이닝 중
   순서가 꼬이는 것을 막습니다"

3단계 (정합성):
  "acks=all + min.insync.replicas=2로 메시지 유실을 방지하고,
   Consumer는 수동 커밋으로 At Least Once를 보장합니다.
   중복 처리는 Consumer 측 멱등성(Unique Key 체크)으로 해결합니다"

4단계 (운영):
  "Partition 수 변경 시 Key 해시가 바뀌어 순서가 깨질 수 있으므로,
   초기에 충분한 Partition을 확보합니다.
   CooperativeStickyAssignor로 Rebalancing 영향을 최소화합니다"
```

## 참고 자료

- [Apache Kafka 공식 문서 — Configuration](https://kafka.apache.org/documentation/#configuration)
- [Kafka: The Definitive Guide (O'Reilly)](https://www.confluent.io/resources/kafka-the-definitive-guide-v2/)
- [Confluent — Exactly Once Semantics](https://www.confluent.io/blog/exactly-once-semantics-are-possible-heres-how-apache-kafka-does-it/)
- [Kafka Idempotent Producer 동작 원리](https://kafka.apache.org/documentation/#semantics)
