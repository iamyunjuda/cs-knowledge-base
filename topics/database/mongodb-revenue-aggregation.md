# MongoDB 복잡한 Order 구조에서 매출 총액 집계 설계

## 핵심 정리

주문(Order) 도큐먼트가 복잡한 구조(중첩 배열, 할인, 환불, 세금 등)를 가지고 있을 때, 매출 총액을 효율적으로 구하는 방법은 크게 **3가지 전략**으로 나뉜다.

### 전략 1: Aggregation Pipeline (기본)

MongoDB의 Aggregation Framework를 활용하여 실시간으로 집계한다.

```javascript
db.orders.aggregate([
  { $match: { status: "COMPLETED", orderDate: { $gte: ISODate("2024-01-01") } } },
  { $unwind: "$items" },
  { $group: {
      _id: null,
      totalRevenue: {
        $sum: {
          $subtract: [
            { $multiply: ["$items.price", "$items.quantity"] },
            { $ifNull: ["$items.discountAmount", 0] }
          ]
        }
      },
      totalRefund: { $sum: { $ifNull: ["$refundAmount", 0] } },
      orderCount: { $sum: 1 }
    }
  },
  { $project: {
      _id: 0,
      netRevenue: { $subtract: ["$totalRevenue", "$totalRefund"] },
      totalRevenue: 1,
      totalRefund: 1,
      orderCount: 1
    }
  }
])
```

**장점**: 항상 최신 데이터, 구현 단순
**단점**: 데이터 증가 시 느려짐, `$unwind`가 메모리 많이 사용
**적합**: 5,000건 수준에서는 충분히 빠름 (수백 ms 이내)

### 전략 2: 사전 계산 필드 (Pre-computed Field)

Order 저장 시점에 매출 관련 계산 값을 미리 넣어둔다.

```javascript
// Order 도큐먼트에 사전 계산 필드 추가
{
  _id: ObjectId("..."),
  status: "COMPLETED",
  orderDate: ISODate("2024-03-15"),
  items: [
    { productId: "P001", price: 15000, quantity: 2, discountAmount: 1000 },
    { productId: "P002", price: 8000, quantity: 1, discountAmount: 0 }
  ],
  refundAmount: 0,
  // ✅ 사전 계산 필드
  calculatedRevenue: {
    itemsTotal: 38000,       // sum(price * quantity)
    discountTotal: 1000,     // sum(discountAmount)
    grossRevenue: 37000,     // itemsTotal - discountTotal
    taxAmount: 3700,         // 부가세
    netRevenue: 37000        // grossRevenue - refundAmount
  }
}
```

집계 쿼리가 극적으로 단순해진다:

```javascript
db.orders.aggregate([
  { $match: { status: "COMPLETED", orderDate: { $gte: ISODate("2024-01-01") } } },
  { $group: {
      _id: null,
      totalNetRevenue: { $sum: "$calculatedRevenue.netRevenue" },
      totalGross: { $sum: "$calculatedRevenue.grossRevenue" },
      totalDiscount: { $sum: "$calculatedRevenue.discountTotal" },
      totalRefund: { $sum: "$refundAmount" },
      orderCount: { $sum: 1 }
    }
  }
])
```

**장점**: `$unwind` 불필요, 인덱스 활용 가능, 매우 빠름
**단점**: 주문 생성/수정 시 계산 로직 필요, 기존 데이터 마이그레이션 필요
**적합**: 프로덕션 환경에서 가장 권장되는 패턴

### 전략 3: Materialized View (대규모 집계)

일별/월별 매출 요약을 별도 컬렉션에 저장한다.

```javascript
// revenue_summary 컬렉션
{
  _id: "2024-03",           // 월별 키
  period: "monthly",
  year: 2024,
  month: 3,
  totalNetRevenue: 45000000,
  totalGrossRevenue: 48000000,
  totalDiscount: 2500000,
  totalRefund: 500000,
  orderCount: 4800,
  updatedAt: ISODate("2024-03-18T10:00:00Z")
}
```

**$merge로 자동 갱신**:

```javascript
db.orders.aggregate([
  { $match: { status: "COMPLETED" } },
  { $group: {
      _id: { $dateToString: { format: "%Y-%m", date: "$orderDate" } },
      totalNetRevenue: { $sum: "$calculatedRevenue.netRevenue" },
      totalGrossRevenue: { $sum: "$calculatedRevenue.grossRevenue" },
      totalDiscount: { $sum: "$calculatedRevenue.discountTotal" },
      totalRefund: { $sum: "$refundAmount" },
      orderCount: { $sum: 1 }
    }
  },
  { $merge: {
      into: "revenue_summary",
      on: "_id",
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
])
```

**장점**: 조회가 O(1), 대시보드에 최적
**단점**: 실시간성 부족 (갱신 주기에 따라 지연), 추가 저장 공간
**적합**: 수십만 건 이상, 대시보드/리포트 용도

---

## 5,000건 규모에서의 실전 권장 설계

### 결론부터: 전략 2 (사전 계산 필드) + 인덱스 최적화

5,000건은 MongoDB에게 아주 작은 규모다. 하지만 **프로덕션에서는 "지금 5,000건"이 아니라 "앞으로의 증가"를 고려**해야 한다.

### 인덱스 설계

```javascript
// 매출 집계용 복합 인덱스
db.orders.createIndex(
  { status: 1, orderDate: -1 },
  { name: "idx_revenue_query" }
)

// Covered Query가 가능한 인덱스 (최적)
db.orders.createIndex(
  { status: 1, orderDate: -1, "calculatedRevenue.netRevenue": 1 },
  { name: "idx_revenue_covered" }
)
```

### Spring Data MongoDB 구현 예시

```java
@Service
@RequiredArgsConstructor
public class RevenueService {

    private final MongoTemplate mongoTemplate;

    public RevenueSummary getRevenueSummary(LocalDate from, LocalDate to) {
        Aggregation aggregation = Aggregation.newAggregation(
            Aggregation.match(
                Criteria.where("status").is("COMPLETED")
                    .and("orderDate").gte(from).lte(to)
            ),
            Aggregation.group()
                .sum("calculatedRevenue.netRevenue").as("totalNetRevenue")
                .sum("calculatedRevenue.grossRevenue").as("totalGrossRevenue")
                .sum("calculatedRevenue.discountTotal").as("totalDiscount")
                .sum("refundAmount").as("totalRefund")
                .count().as("orderCount")
        );

        return mongoTemplate.aggregate(aggregation, "orders", RevenueSummary.class)
                .getUniqueMappedResult();
    }
}
```

```java
// Order 저장 시 사전 계산
@Document(collection = "orders")
public class Order {
    @Id
    private String id;
    private String status;
    private LocalDate orderDate;
    private List<OrderItem> items;
    private BigDecimal refundAmount;
    private CalculatedRevenue calculatedRevenue;

    // 주문 생성/수정 시 호출
    public void recalculateRevenue() {
        BigDecimal itemsTotal = items.stream()
            .map(i -> i.getPrice().multiply(BigDecimal.valueOf(i.getQuantity())))
            .reduce(BigDecimal.ZERO, BigDecimal::add);

        BigDecimal discountTotal = items.stream()
            .map(i -> Optional.ofNullable(i.getDiscountAmount()).orElse(BigDecimal.ZERO))
            .reduce(BigDecimal.ZERO, BigDecimal::add);

        BigDecimal gross = itemsTotal.subtract(discountTotal);
        BigDecimal net = gross.subtract(
            Optional.ofNullable(refundAmount).orElse(BigDecimal.ZERO)
        );

        this.calculatedRevenue = new CalculatedRevenue(
            itemsTotal, discountTotal, gross, net
        );
    }
}
```

### 기존 5,000건 마이그레이션 스크립트

```javascript
// 한 번만 실행하는 마이그레이션
db.orders.find({}).forEach(function(order) {
  var itemsTotal = 0;
  var discountTotal = 0;

  (order.items || []).forEach(function(item) {
    itemsTotal += (item.price || 0) * (item.quantity || 0);
    discountTotal += (item.discountAmount || 0);
  });

  var grossRevenue = itemsTotal - discountTotal;
  var netRevenue = grossRevenue - (order.refundAmount || 0);

  db.orders.updateOne(
    { _id: order._id },
    { $set: {
        "calculatedRevenue": {
          itemsTotal: itemsTotal,
          discountTotal: discountTotal,
          grossRevenue: grossRevenue,
          netRevenue: netRevenue
        }
      }
    }
  );
});
```

---

## 성능 비교

| 전략 | 5,000건 | 50,000건 | 500,000건 |
|------|---------|----------|-----------|
| Aggregation + `$unwind` | ~200ms | ~2s | ~20s+ |
| 사전 계산 + `$group` | ~50ms | ~200ms | ~1s |
| Materialized View 조회 | ~5ms | ~5ms | ~5ms |

> `$unwind`는 배열 요소 수만큼 도큐먼트를 확장하므로, 아이템이 평균 5개면 실질적으로 25,000건을 처리하는 셈이다.

---

## 헷갈렸던 포인트

### Q1: `$unwind` 없이도 배열 안의 필드를 집계할 수 있나?

**A**: MongoDB 3.6+에서 `$reduce`를 쓰면 `$unwind` 없이 배열 집계가 가능하다.

```javascript
db.orders.aggregate([
  { $match: { status: "COMPLETED" } },
  { $addFields: {
      itemRevenue: {
        $reduce: {
          input: "$items",
          initialValue: 0,
          in: { $add: [
            "$$value",
            { $subtract: [
              { $multiply: ["$$this.price", "$$this.quantity"] },
              { $ifNull: ["$$this.discountAmount", 0] }
            ]}
          ]}
        }
      }
    }
  },
  { $group: {
      _id: null,
      totalRevenue: { $sum: "$itemRevenue" }
    }
  }
])
```

하지만 **사전 계산 필드를 쓰면 이런 고민 자체가 불필요**해진다.

### Q2: 사전 계산 필드는 데이터 정합성이 깨질 위험이 없나?

**A**: 있다. 반드시 다음을 지켜야 한다:
- 주문 생성/수정하는 모든 경로에서 `recalculateRevenue()` 호출
- 직접 DB 수정(mongo shell 등)을 금지하거나, 수정 후 재계산 스크립트 실행
- 주기적 Reconciliation 배치로 불일치 검증

```java
// EventListener로 강제
@Component
public class OrderEventListener extends AbstractMongoEventListener<Order> {
    @Override
    public void onBeforeSave(BeforeSaveEvent<Order> event) {
        event.getSource().recalculateRevenue();
    }
}
```

### Q3: `allowDiskUse`는 언제 필요한가?

**A**: Aggregation Pipeline의 단일 스테이지가 **100MB 메모리 제한**을 초과하면 에러가 발생한다. `$unwind`로 대량 데이터를 펼칠 때 주로 발생.

```javascript
db.orders.aggregate([...], { allowDiskUse: true })
```

사전 계산 필드를 쓰면 `$unwind`가 없으므로 이 문제를 근본적으로 회피한다.

### Q4: Change Stream으로 실시간 Materialized View를 만들 수 있나?

**A**: 가능하다. Replica Set 환경에서 Change Stream을 구독하여 주문 변경 시 즉시 요약을 갱신할 수 있다.

```java
@Component
public class OrderChangeStreamListener {

    @PostConstruct
    public void listen() {
        mongoTemplate.getCollection("orders")
            .watch(List.of(
                Aggregates.match(Filters.in("operationType",
                    List.of("insert", "update", "replace")))
            ))
            .forEach(change -> updateRevenueSummary(change));
    }

    private void updateRevenueSummary(ChangeStreamDocument<Document> change) {
        // revenue_summary 컬렉션의 해당 월 도큐먼트를 $inc로 갱신
    }
}
```

### Q5: 5,000건인데 굳이 최적화가 필요한가?

**A**: 5,000건 자체는 MongoDB에게 아무것도 아니다. 그러나:
- 복잡한 `$unwind` + 다단계 계산은 5,000건에서도 **수백 ms**가 걸릴 수 있음
- API 응답 시간 요구사항이 100ms 이하라면 문제가 됨
- 동시 요청이 많으면 CPU/메모리 누적 부하 발생
- **데이터는 항상 늘어난다** — 설계 시점에 확장 가능한 구조를 잡는 것이 핵심

## 대규모 데이터 상황별 집계 전략

데이터가 수십만~수천만 건 이상으로 커지면 위의 기본 전략만으로는 부족하다. **데이터 규모와 요구사항에 따라** 전략이 달라진다.

---

### 상황 1: 10만~50만 건 — 사전 계산 + Sharding

사전 계산 필드만으로도 충분하지만, 단일 노드의 한계가 보이기 시작한다.

**핵심 전략: Shard Key 설계**

```javascript
// orderDate 기반 Range Sharding
sh.shardCollection("mydb.orders", { orderDate: 1 })

// 특정 고객의 주문이 몰리는 경우 → Hashed Sharding
sh.shardCollection("mydb.orders", { customerId: "hashed" })
```

**주의점:**
- `$group`에서 `_id: null` (전체 합산)은 **모든 Shard를 스캔**해야 하므로 여전히 느림
- 기간별 조회가 많다면 `orderDate`를 Shard Key로 → 특정 Shard만 조회
- 하지만 최신 주문이 한 Shard에 몰리는 **Hot Shard 문제** 발생 가능

```javascript
// Hot Shard 방지: 복합 Shard Key
sh.shardCollection("mydb.orders", { storeId: 1, orderDate: 1 })
```

**이 규모에서의 권장 조합:**

| 용도 | 전략 |
|------|------|
| 실시간 매출 조회 (오늘) | 사전 계산 필드 + `$group` (당일 데이터만 `$match`) |
| 월간 리포트 | Materialized View (`revenue_summary`) |
| 연간 통계 | Materialized View + 캐싱 (Redis) |

---

### 상황 2: 50만~500만 건 — Materialized View 필수 + 증분 갱신

이 규모에서 실시간 Aggregation은 비현실적이다. **반드시 사전 집계된 결과를 조회**해야 한다.

**증분 갱신 (Incremental Update) 패턴**

전체를 다시 집계하지 않고, 변경된 부분만 반영한다.

```java
@Service
@RequiredArgsConstructor
public class IncrementalRevenueUpdater {

    private final MongoTemplate mongoTemplate;

    /**
     * 새 주문이 완료될 때 호출
     * 전체 재집계 대신, 해당 월의 요약만 증분 업데이트
     */
    public void onOrderCompleted(Order order) {
        String monthKey = order.getOrderDate()
            .format(DateTimeFormatter.ofPattern("yyyy-MM"));

        Update update = new Update()
            .inc("totalNetRevenue", order.getCalculatedRevenue().getNetRevenue().longValue())
            .inc("totalGrossRevenue", order.getCalculatedRevenue().getGrossRevenue().longValue())
            .inc("totalDiscount", order.getCalculatedRevenue().getDiscountTotal().longValue())
            .inc("orderCount", 1)
            .set("updatedAt", LocalDateTime.now());

        mongoTemplate.upsert(
            Query.query(Criteria.where("_id").is(monthKey)),
            update,
            "revenue_summary"
        );
    }

    /**
     * 환불 발생 시
     */
    public void onOrderRefunded(Order order, BigDecimal refundAmount) {
        String monthKey = order.getOrderDate()
            .format(DateTimeFormatter.ofPattern("yyyy-MM"));

        Update update = new Update()
            .inc("totalRefund", refundAmount.longValue())
            .inc("totalNetRevenue", -refundAmount.longValue())
            .set("updatedAt", LocalDateTime.now());

        mongoTemplate.updateFirst(
            Query.query(Criteria.where("_id").is(monthKey)),
            update,
            "revenue_summary"
        );
    }
}
```

**증분 갱신의 정합성 보장 — Reconciliation 배치**

증분 갱신은 빠르지만, 버그나 장애로 불일치가 쌓일 수 있다. 주기적으로 전체 재계산하여 검증한다.

```java
@Scheduled(cron = "0 0 3 * * *") // 매일 새벽 3시
public void dailyReconciliation() {
    // 어제 날짜의 요약을 재계산
    LocalDate yesterday = LocalDate.now().minusDays(1);
    String monthKey = yesterday.format(DateTimeFormatter.ofPattern("yyyy-MM"));

    // 해당 월 전체를 Aggregation으로 재계산
    Aggregation agg = Aggregation.newAggregation(
        Aggregation.match(Criteria.where("status").is("COMPLETED")
            .and("orderDate").gte(yesterday.withDayOfMonth(1))
            .and("orderDate").lt(yesterday.plusMonths(1).withDayOfMonth(1))),
        Aggregation.group()
            .sum("calculatedRevenue.netRevenue").as("totalNetRevenue")
            .sum("calculatedRevenue.grossRevenue").as("totalGrossRevenue")
            .sum("calculatedRevenue.discountTotal").as("totalDiscount")
            .sum("refundAmount").as("totalRefund")
            .count().as("orderCount")
    );

    RevenueSummary recalculated = mongoTemplate
        .aggregate(agg, "orders", RevenueSummary.class)
        .getUniqueMappedResult();

    // 기존 요약과 비교 → 불일치 시 알림 + 보정
    RevenueSummary existing = mongoTemplate.findById(monthKey, RevenueSummary.class, "revenue_summary");
    if (!recalculated.equals(existing)) {
        log.warn("Revenue mismatch detected for {}. Expected: {}, Actual: {}",
            monthKey, recalculated, existing);
        // 재계산 값으로 덮어쓰기
        mongoTemplate.save(recalculated, "revenue_summary");
    }
}
```

---

### 상황 3: 500만 건 이상 — CQRS + 이벤트 소싱 / 외부 분석 엔진

MongoDB 단독으로 감당하기 어려운 규모. **읽기 전용 분석 경로를 완전히 분리**해야 한다.

**패턴 A: CQRS (Command Query Responsibility Segregation)**

```
┌─────────────┐     ┌─────────────┐     ┌──────────────────┐
│  주문 서비스  │────▶│   Kafka     │────▶│  매출 집계 서비스  │
│  (Command)  │     │  (Event)    │     │  (Query)         │
│  MongoDB    │     │             │     │  Redis / ES      │
└─────────────┘     └─────────────┘     └──────────────────┘
```

```java
// 주문 서비스: 주문 완료 시 이벤트 발행
@Service
public class OrderService {

    private final KafkaTemplate<String, OrderCompletedEvent> kafkaTemplate;

    @Transactional
    public void completeOrder(Order order) {
        order.setStatus("COMPLETED");
        order.recalculateRevenue();
        orderRepository.save(order);

        kafkaTemplate.send("order-events", new OrderCompletedEvent(
            order.getId(),
            order.getOrderDate(),
            order.getCalculatedRevenue().getNetRevenue(),
            order.getCalculatedRevenue().getGrossRevenue()
        ));
    }
}

// 매출 집계 서비스: 이벤트 소비하여 Redis에 실시간 집계
@Service
public class RevenueConsumer {

    private final StringRedisTemplate redis;

    @KafkaListener(topics = "order-events")
    public void onOrderCompleted(OrderCompletedEvent event) {
        String dailyKey = "revenue:daily:" + event.getOrderDate();
        String monthlyKey = "revenue:monthly:" + event.getOrderDate()
            .format(DateTimeFormatter.ofPattern("yyyy-MM"));

        redis.opsForHash().increment(dailyKey, "netRevenue",
            event.getNetRevenue().longValue());
        redis.opsForHash().increment(dailyKey, "orderCount", 1);
        redis.opsForHash().increment(monthlyKey, "netRevenue",
            event.getNetRevenue().longValue());
        redis.opsForHash().increment(monthlyKey, "orderCount", 1);
    }
}
```

**매출 조회가 O(1)** — Redis `HGETALL`로 즉시 응답.

**패턴 B: 분석 전용 DB로 동기화**

```
MongoDB (원본) ──▶ Change Stream / Debezium ──▶ Elasticsearch / ClickHouse
                                                       │
                                            Kibana / Grafana 대시보드
```

```javascript
// ClickHouse 같은 컬럼형 DB에 동기화하면
// 수천만 건도 서브초 집계 가능
// ClickHouse 테이블 예시
/*
CREATE TABLE order_revenue (
    order_id String,
    order_date Date,
    store_id String,
    net_revenue Decimal(18,2),
    gross_revenue Decimal(18,2),
    discount_total Decimal(18,2),
    refund_amount Decimal(18,2)
) ENGINE = MergeTree()
ORDER BY (order_date, store_id);

-- 월별 매출: 1억 건도 수백 ms
SELECT
    toYYYYMM(order_date) AS month,
    sum(net_revenue) AS total
FROM order_revenue
GROUP BY month
ORDER BY month;
*/
```

**패턴 C: MongoDB Atlas Charts / Atlas Data Federation**

MongoDB Atlas를 사용 중이라면 별도 인프라 없이 분석 가능.

```
MongoDB Atlas ──▶ Atlas Data Federation ──▶ $out to S3
                                           ──▶ Atlas Charts (시각화)
                                           ──▶ Atlas SQL Interface (BI 툴 연동)
```

---

### 상황별 최종 의사결정 표

| 규모 | 실시간 매출 | 일별/월별 리포트 | 대시보드 | 핵심 전략 |
|------|-----------|----------------|---------|----------|
| **~1만** | Aggregation Pipeline | Aggregation Pipeline | 같은 쿼리 | 사전 계산 필드 + 인덱스 |
| **1만~10만** | 사전 계산 + `$group` | Materialized View | Materialized View | 사전 계산 + `$merge` 스케줄링 |
| **10만~100만** | 증분 갱신 요약 테이블 | Materialized View | Materialized View + Redis 캐싱 | 증분 갱신 + Reconciliation 배치 |
| **100만~1000만** | Redis (CQRS) | Materialized View | Grafana + Redis | CQRS + Kafka 이벤트 |
| **1000만+** | Redis (CQRS) | ClickHouse / BigQuery | ClickHouse + Grafana | CQRS + 컬럼형 DB 분리 |

### 공통 원칙

1. **`$match`를 항상 파이프라인 최상단에** — 인덱스를 타고 스캔 범위를 줄인다
2. **`$unwind`를 피하라** — 사전 계산 필드로 대체
3. **전체 스캔을 하지 마라** — 기간 필터 필수, Materialized View로 우회
4. **실시간이 꼭 필요한지 따져라** — 대부분의 매출 리포트는 5분~1시간 지연 허용
5. **정합성 검증은 별도로** — 증분 갱신은 반드시 Reconciliation 배치와 함께

## 매출 집계 오차 검증 — 어떻게 테스트하고 판단하는가

매출 데이터는 **돈과 직결**되기 때문에, 집계 결과의 정확성을 검증하는 체계가 반드시 필요하다.

---

### 오차가 발생하는 원인

| 원인 | 설명 | 빈도 |
|------|------|------|
| **사전 계산 필드 누락** | 직접 DB 수정, 마이그레이션 누락으로 `calculatedRevenue`가 없는 도큐먼트 | 높음 |
| **이벤트 유실** | Kafka 메시지 유실, Consumer 장애로 증분 갱신 누락 | 중간 |
| **부동소수점 오차** | `double` 타입 사용 시 0.1 + 0.2 ≠ 0.3 문제 | 낮지만 누적됨 |
| **동시성 Race Condition** | 같은 주문의 수정/환불이 동시에 발생하여 증분 갱신 충돌 | 중간 |
| **상태 전이 중복** | 주문이 COMPLETED → REFUNDED → COMPLETED로 되돌아갈 때 이중 집계 | 낮음 |
| **타임존 경계** | UTC vs KST 날짜 경계에서 일별 집계가 어긋남 | 높음 |

---

### 테스트 전략 1: 단위 테스트 — 계산 로직 자체 검증

```java
@Test
void 사전_계산_필드가_정확히_계산되는지() {
    Order order = Order.builder()
        .items(List.of(
            OrderItem.of("P001", new BigDecimal("15000"), 2, new BigDecimal("1000")),
            OrderItem.of("P002", new BigDecimal("8000"), 1, BigDecimal.ZERO)
        ))
        .refundAmount(BigDecimal.ZERO)
        .build();

    order.recalculateRevenue();

    // 15000*2 + 8000*1 = 38000
    assertThat(order.getCalculatedRevenue().getItemsTotal())
        .isEqualByComparingTo(new BigDecimal("38000"));
    // 38000 - 1000 = 37000
    assertThat(order.getCalculatedRevenue().getGrossRevenue())
        .isEqualByComparingTo(new BigDecimal("37000"));
    assertThat(order.getCalculatedRevenue().getNetRevenue())
        .isEqualByComparingTo(new BigDecimal("37000"));
}

@Test
void 환불_반영_후_netRevenue가_감소하는지() {
    Order order = createCompletedOrder();
    BigDecimal beforeNet = order.getCalculatedRevenue().getNetRevenue();

    order.setRefundAmount(new BigDecimal("5000"));
    order.recalculateRevenue();

    assertThat(order.getCalculatedRevenue().getNetRevenue())
        .isEqualByComparingTo(beforeNet.subtract(new BigDecimal("5000")));
}

@Test
void 부동소수점_오차가_발생하지_않는지() {
    // BigDecimal을 쓰면 이 테스트가 통과해야 한다
    Order order = Order.builder()
        .items(List.of(
            OrderItem.of("P001", new BigDecimal("0.1"), 1, BigDecimal.ZERO),
            OrderItem.of("P002", new BigDecimal("0.2"), 1, BigDecimal.ZERO)
        ))
        .refundAmount(BigDecimal.ZERO)
        .build();

    order.recalculateRevenue();

    // double이면 0.30000000000000004가 되지만, BigDecimal이면 정확히 0.3
    assertThat(order.getCalculatedRevenue().getItemsTotal())
        .isEqualByComparingTo(new BigDecimal("0.3"));
}
```

> **핵심**: 금액 계산에는 반드시 `BigDecimal`을 사용하고, MongoDB에는 `Decimal128` (BSON) 또는 `String`으로 저장한다. `double`은 절대 쓰지 않는다.

---

### 테스트 전략 2: 통합 테스트 — Aggregation 결과 vs 직접 계산 비교

```java
@SpringBootTest
@Testcontainers
class RevenueAggregationIntegrationTest {

    @Container
    static MongoDBContainer mongo = new MongoDBContainer("mongo:7.0");

    @Autowired MongoTemplate mongoTemplate;
    @Autowired RevenueService revenueService;

    @Test
    void Aggregation_결과가_Java_직접_계산과_일치하는지() {
        // Given: 테스트 주문 100건 삽입
        List<Order> orders = generateRandomOrders(100);
        orders.forEach(o -> {
            o.recalculateRevenue();
            mongoTemplate.save(o);
        });

        // When: Aggregation으로 집계
        RevenueSummary aggregated = revenueService.getRevenueSummary(
            LocalDate.of(2024, 1, 1), LocalDate.of(2024, 12, 31));

        // Then: Java Stream으로 직접 계산한 값과 비교
        BigDecimal expectedNet = orders.stream()
            .filter(o -> "COMPLETED".equals(o.getStatus()))
            .map(o -> o.getCalculatedRevenue().getNetRevenue())
            .reduce(BigDecimal.ZERO, BigDecimal::add);

        assertThat(aggregated.getTotalNetRevenue())
            .isEqualByComparingTo(expectedNet);
    }

    @Test
    void Materialized_View가_원본_Aggregation과_일치하는지() {
        List<Order> orders = generateRandomOrders(500);
        orders.forEach(o -> {
            o.recalculateRevenue();
            mongoTemplate.save(o);
        });

        // Materialized View 갱신 실행
        revenueService.refreshMaterializedView();

        // 원본 Aggregation 직접 실행
        RevenueSummary fromAggregation = revenueService.getRevenueSummary(
            LocalDate.of(2024, 1, 1), LocalDate.of(2024, 12, 31));

        // Materialized View에서 조회
        RevenueSummary fromView = revenueService.getRevenueSummaryFromView("2024");

        assertThat(fromView.getTotalNetRevenue())
            .isEqualByComparingTo(fromAggregation.getTotalNetRevenue());
    }
}
```

---

### 테스트 전략 3: Reconciliation 배치 — 프로덕션 오차 감지

프로덕션에서는 테스트를 돌리는 게 아니라, **Reconciliation(재조정) 배치**로 오차를 감지하고 보정한다.

```java
@Component
@Slf4j
public class RevenueReconciliationJob {

    private final MongoTemplate mongoTemplate;
    private final MeterRegistry meterRegistry;  // Prometheus 메트릭
    private final SlackNotifier slackNotifier;

    /**
     * 오차 허용 범위 (원 단위)
     * - 0이면 완벽한 일치만 허용
     * - 실무에서는 반올림 등으로 1~10원 차이가 날 수 있음
     */
    private static final BigDecimal TOLERANCE = BigDecimal.ONE;

    @Scheduled(cron = "0 0 4 * * *") // 매일 새벽 4시
    public void reconcile() {
        LocalDate targetDate = LocalDate.now().minusDays(1);
        String monthKey = targetDate.format(DateTimeFormatter.ofPattern("yyyy-MM"));

        // 1. Source of Truth: 원본 orders에서 직접 집계
        RevenueSummary truth = aggregateFromOrders(monthKey);

        // 2. 검증 대상: revenue_summary에서 조회
        RevenueSummary cached = mongoTemplate.findById(
            monthKey, RevenueSummary.class, "revenue_summary");

        if (cached == null) {
            log.error("[Reconciliation] summary 없음: {}", monthKey);
            slackNotifier.alert("revenue_summary 누락: " + monthKey);
            mongoTemplate.save(truth, "revenue_summary");
            return;
        }

        // 3. 오차 판단
        BigDecimal diff = truth.getTotalNetRevenue()
            .subtract(cached.getTotalNetRevenue()).abs();

        // 메트릭 기록 (Grafana 대시보드용)
        meterRegistry.gauge("revenue.reconciliation.diff",
            Tags.of("month", monthKey), diff.doubleValue());

        if (diff.compareTo(TOLERANCE) > 0) {
            log.error("[Reconciliation] 오차 감지! month={}, diff={}, truth={}, cached={}",
                monthKey, diff, truth.getTotalNetRevenue(), cached.getTotalNetRevenue());

            slackNotifier.alert(String.format(
                "⚠️ 매출 오차 감지\n월: %s\n차이: %s원\n정확한 값: %s\n캐시 값: %s",
                monthKey, diff, truth.getTotalNetRevenue(), cached.getTotalNetRevenue()
            ));

            // 자동 보정 (선택적 — 금액이 크면 수동 확인 후 보정)
            if (diff.compareTo(new BigDecimal("10000")) < 0) {
                mongoTemplate.save(truth, "revenue_summary");
                log.info("[Reconciliation] 자동 보정 완료: {}", monthKey);
            } else {
                log.warn("[Reconciliation] 수동 확인 필요: 오차 {}원", diff);
            }
        } else {
            log.info("[Reconciliation] 정상: month={}, diff={}", monthKey, diff);
        }
    }
}
```

---

### 오차 판단 기준 — 실무 가이드

```
오차 = |Source of Truth 집계 값| - |캐시/요약 값|
```

| 오차 범위 | 판단 | 대응 |
|----------|------|------|
| **0원** | 완벽 일치 | 없음 |
| **1~10원** | 반올림/타임존 오차 | 자동 보정, 로그만 남김 |
| **10~10,000원** | 이벤트 유실 or 동시성 버그 | 자동 보정 + Slack 알림 |
| **10,000원 이상** | 심각한 로직 버그 or 데이터 손상 | **자동 보정 금지**, 수동 조사 필수 |

### 오차를 줄이는 설계 원칙

1. **금액은 반드시 `BigDecimal` / `Decimal128`** — `double`/`float` 금지
2. **타임존을 명시적으로 통일** — 저장은 UTC, 집계 기준도 UTC, 표시만 KST
3. **증분 갱신은 멱등성 보장** — 같은 이벤트가 두 번 와도 결과가 같도록
4. **Reconciliation은 매일 실행** — 오차를 빨리 잡을수록 원인 추적이 쉬움
5. **오차 메트릭을 모니터링** — Grafana에서 추세를 보면 버그 도입 시점을 알 수 있음

```java
// 멱등성 보장 예시: 이미 처리된 이벤트 무시
@KafkaListener(topics = "order-events")
public void onOrderCompleted(OrderCompletedEvent event) {
    String deduplicationKey = "processed:order:" + event.getOrderId();

    Boolean isNew = redis.opsForValue()
        .setIfAbsent(deduplicationKey, "1", Duration.ofDays(7));

    if (Boolean.FALSE.equals(isNew)) {
        log.debug("이미 처리된 이벤트: {}", event.getOrderId());
        return;
    }

    // 증분 갱신 수행
    updateRevenueSummary(event);
}
```

## 참고 자료

- [MongoDB Aggregation Pipeline 공식 문서](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/)
- [MongoDB $merge (Materialized View)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/merge/)
- [MongoDB Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
- [Spring Data MongoDB - Aggregation](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html)
