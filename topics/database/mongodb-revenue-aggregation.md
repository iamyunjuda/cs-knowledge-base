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

## 배포 중 유입되는 주문의 통계 정합성

배포(Deploy)는 순간이 아니다. Rolling Update든 Blue-Green이든, **구버전과 신버전이 공존하는 시간**이 존재한다. 이 시간 동안 들어오는 주문이 통계에서 빠지거나 중복 집계되는 문제가 발생할 수 있다.

---

### 배포 시 통계가 깨지는 시나리오

```
시간축 ──────────────────────────────────────────▶

Pod A (v1)  ████████████████░░░░░░░░░  (종료)
Pod B (v1)  ████████████████████░░░░░  (종료)
Pod C (v2)  ░░░░░░░░████████████████████████████
Pod D (v2)  ░░░░░░░░░░░░████████████████████████

                    ▲ 이 구간이 위험
                    │ v1, v2 공존 구간
```

| 시나리오 | 원인 | 결과 |
|---------|------|------|
| **통계 누락** | v1 Pod이 주문을 받고 증분 갱신 전에 SIGTERM으로 종료됨 | 매출 집계에서 해당 주문 빠짐 |
| **이중 집계** | v1이 Kafka에 이벤트를 발행 → v1 Consumer 종료 → v2 Consumer가 리밸런싱 후 같은 파티션을 재소비 | 같은 주문이 두 번 집계 |
| **스키마 불일치** | v2에서 `calculatedRevenue`에 `taxAmount` 필드를 추가 → v1은 이 필드 없이 저장 | v2 Aggregation에서 `taxAmount`가 null/0 |
| **Materialized View 갱신 충돌** | v1의 스케줄러가 `$merge` 실행 중 v2의 스케줄러도 `$merge` 실행 | 덮어쓰기로 데이터 유실 |

---

### 전략 1: Graceful Shutdown — 진행 중 작업 완료 보장

배포 시 가장 기본적인 방어선. Pod 종료 전 진행 중인 주문 처리와 통계 갱신을 완료한다.

```java
@Component
@Slf4j
public class GracefulShutdownHandler {

    private final AtomicBoolean shuttingDown = new AtomicBoolean(false);
    private final AtomicInteger activeOrderProcessing = new AtomicInteger(0);

    @EventListener(ContextClosedEvent.class)
    public void onShutdown() {
        shuttingDown.set(true);
        log.info("Shutdown 시작. 진행 중인 주문 처리 대기: {}건",
            activeOrderProcessing.get());

        // 진행 중인 주문 처리가 완료될 때까지 대기 (최대 30초)
        long deadline = System.currentTimeMillis() + 30_000;
        while (activeOrderProcessing.get() > 0
               && System.currentTimeMillis() < deadline) {
            try { Thread.sleep(500); } catch (InterruptedException e) { break; }
        }

        if (activeOrderProcessing.get() > 0) {
            log.warn("타임아웃! 미완료 주문 {}건은 Reconciliation에서 보정됨",
                activeOrderProcessing.get());
        }
    }

    public boolean isShuttingDown() {
        return shuttingDown.get();
    }

    public void incrementActive() { activeOrderProcessing.incrementAndGet(); }
    public void decrementActive() { activeOrderProcessing.decrementAndGet(); }
}
```

```java
@Service
@RequiredArgsConstructor
public class OrderService {

    private final GracefulShutdownHandler shutdownHandler;

    public Order completeOrder(Order order) {
        if (shutdownHandler.isShuttingDown()) {
            // 종료 중이면 새 주문을 받지 않음 → 로드밸런서가 다른 Pod으로 라우팅
            throw new ServiceUnavailableException("서버 종료 중");
        }

        shutdownHandler.incrementActive();
        try {
            order.setStatus("COMPLETED");
            order.recalculateRevenue();
            orderRepository.save(order);
            publishRevenueEvent(order);  // 증분 갱신 이벤트
            return order;
        } finally {
            shutdownHandler.decrementActive();
        }
    }
}
```

**K8s 설정:**

```yaml
# Pod이 트래픽을 받지 않되, 진행 중 작업은 완료할 시간을 줌
spec:
  terminationGracePeriodSeconds: 60
  containers:
    - name: order-service
      lifecycle:
        preStop:
          exec:
            # LB에서 빠진 후 기존 요청 처리 시간 확보
            command: ["sh", "-c", "sleep 10"]
```

---

### 전략 2: 이벤트 기반 집계 — 배포와 통계를 완전히 분리

주문 저장과 통계 갱신을 **비동기 이벤트로 분리**하면, 배포가 통계에 직접 영향을 주지 않는다.

```
┌──────────────┐         ┌───────────┐         ┌──────────────────┐
│  주문 서비스   │───────▶│  Kafka    │───────▶│  통계 집계 서비스   │
│  (배포 대상)  │  이벤트  │  (독립)   │  소비   │  (별도 배포 주기)  │
└──────────────┘         └───────────┘         └──────────────────┘
      v1→v2 배포 중                              영향 없음
```

**핵심 포인트:**
- 주문 서비스가 재시작되더라도, Kafka에 이미 들어간 이벤트는 사라지지 않음
- 통계 집계 서비스는 별도로 배포 → 주문 서비스 배포와 무관하게 안정적으로 소비
- Consumer 리밸런싱이 발생해도 Kafka offset으로 정확히 이어서 처리

```java
// 주문 서비스: 주문 완료 시 이벤트만 발행하고 끝
@Service
public class OrderService {

    @Transactional
    public Order completeOrder(Order order) {
        order.setStatus("COMPLETED");
        order.recalculateRevenue();
        Order saved = orderRepository.save(order);

        // Outbox 패턴: 트랜잭션 안에서 이벤트 저장
        outboxRepository.save(new OutboxEvent(
            "ORDER_COMPLETED",
            saved.getId(),
            toJson(saved.getCalculatedRevenue())
        ));

        return saved;
    }
}

// Outbox → Kafka 릴레이 (별도 스레드 또는 Debezium CDC)
// 주문 서비스가 죽어도 outbox에 남아있으므로 이벤트 유실 없음
```

```java
// 통계 집계 서비스: 독립 배포, Consumer Group으로 exactly-once 처리
@Service
public class RevenueConsumer {

    @KafkaListener(
        topics = "order-events",
        groupId = "revenue-aggregator",
        properties = {
            "enable.auto.commit=false",        // 수동 커밋
            "isolation.level=read_committed"    // 트랜잭션 메시지만 읽기
        }
    )
    public void consume(OrderCompletedEvent event, Acknowledgment ack) {
        // 멱등성 체크
        if (isAlreadyProcessed(event.getEventId())) {
            ack.acknowledge();
            return;
        }

        updateRevenueSummary(event);
        markAsProcessed(event.getEventId());
        ack.acknowledge();  // 처리 완료 후에만 커밋
    }
}
```

---

### 전략 3: 배포 전후 Reconciliation — "배포 구간" 자동 재검증

배포 시각을 기록하고, 배포 구간에 해당하는 주문만 자동으로 재검증한다.

```java
@Component
@Slf4j
public class DeploymentAwareReconciliation {

    private final MongoTemplate mongoTemplate;

    /**
     * 배포 완료 후 호출 (CI/CD 파이프라인에서 트리거)
     * 또는 애플리케이션 시작 시 자동 실행
     */
    @EventListener(ApplicationReadyEvent.class)
    public void reconcileDeploymentWindow() {
        // 1. 배포 구간 파악: 마지막 배포 시각 ~ 현재
        DeploymentRecord lastDeploy = mongoTemplate.findOne(
            Query.query(Criteria.where("status").is("COMPLETED"))
                .with(Sort.by(Sort.Direction.DESC, "completedAt"))
                .limit(1),
            DeploymentRecord.class
        );

        if (lastDeploy == null) return;

        Instant deployStart = lastDeploy.getStartedAt();
        Instant deployEnd = lastDeploy.getCompletedAt();

        log.info("배포 구간 재검증: {} ~ {}", deployStart, deployEnd);

        // 2. 배포 구간에 생성된 주문만 검증
        List<Order> ordersInWindow = mongoTemplate.find(
            Query.query(Criteria.where("createdAt")
                .gte(deployStart.minus(5, ChronoUnit.MINUTES))  // 여유 5분
                .lte(deployEnd.plus(5, ChronoUnit.MINUTES))),
            Order.class
        );

        int fixed = 0;
        for (Order order : ordersInWindow) {
            // 사전 계산 필드가 없거나 잘못된 경우 재계산
            if (order.getCalculatedRevenue() == null
                || !isRevenueCorrect(order)) {
                order.recalculateRevenue();
                mongoTemplate.save(order);
                fixed++;
            }
        }

        if (fixed > 0) {
            log.warn("배포 구간 보정 완료: {}건 / {}건 중", fixed, ordersInWindow.size());
            // 영향받는 월의 Materialized View도 재갱신
            refreshAffectedMonths(ordersInWindow);
        }
    }

    private boolean isRevenueCorrect(Order order) {
        CalculatedRevenue existing = order.getCalculatedRevenue();
        order.recalculateRevenue();
        CalculatedRevenue recalculated = order.getCalculatedRevenue();
        // 원본 복원 후 비교
        order.setCalculatedRevenue(existing);
        return existing.getNetRevenue()
            .compareTo(recalculated.getNetRevenue()) == 0;
    }
}
```

---

### 전략 4: 스키마 변경이 포함된 배포 — 하위 호환성 보장

매출 계산 로직이 변경되는 배포가 가장 위험하다.

```
v1: netRevenue = grossRevenue - refundAmount
v2: netRevenue = grossRevenue - refundAmount - platformFee  ← 새 필드 추가
```

**2단계 배포로 안전하게 처리:**

```
Phase 1 배포: platformFee 필드 추가, 하지만 집계에는 아직 반영 안 함
  ↓
마이그레이션: 기존 도큐먼트에 platformFee = 0 설정 + recalculateRevenue()
  ↓
Phase 2 배포: 집계 로직에 platformFee 반영
```

```java
// Phase 1: 하위 호환 — platformFee가 없어도 동작
public void recalculateRevenue() {
    BigDecimal fee = Optional.ofNullable(this.platformFee)
        .orElse(BigDecimal.ZERO);  // null-safe

    this.calculatedRevenue = new CalculatedRevenue(
        itemsTotal, discountTotal, gross,
        gross.subtract(refundAmount).subtract(fee)
    );
}

// 마이그레이션 스크립트
db.orders.updateMany(
  { platformFee: { $exists: false } },
  { $set: { platformFee: NumberDecimal("0") } }
);

// Phase 2: 모든 도큐먼트에 platformFee가 존재함이 보장된 후
// 집계 파이프라인에 platformFee 포함
```

---

### 배포 전략별 통계 리스크 비교

| 배포 방식 | 공존 시간 | 통계 리스크 | 대응 |
|----------|----------|-----------|------|
| **Rolling Update** | 길다 (수 분) | v1/v2가 동시에 주문 처리 → 스키마 불일치 가능 | 하위 호환 필수 + 배포 후 Reconciliation |
| **Blue-Green** | 순간 전환 | 전환 순간 진행 중 요청 유실 가능 | Graceful Shutdown + Drain 대기 |
| **Canary** | 매우 길다 | 소량 트래픽만 v2로 → 불일치 범위 작음 | 카나리 비율만큼의 오차 모니터링 |
| **Recreate** | 다운타임 있음 | 다운타임 동안 주문 불가 → 통계 gap 없음 | 가장 안전하지만 서비스 중단 |

### 실전 체크리스트

```
배포 전:
  □ calculatedRevenue 계산 로직 변경이 있는가?
    → 있으면 2단계 배포 (Phase 1 호환 → 마이그레이션 → Phase 2 반영)
  □ 새 필드가 추가되는가?
    → 기존 도큐먼트에 기본값 마이그레이션 선행
  □ Materialized View 스케줄러가 v1/v2에서 동시 실행될 수 있는가?
    → 분산 락(ShedLock) 적용

배포 중:
  □ Graceful Shutdown으로 진행 중 주문 처리 완료 대기
  □ K8s preStop + terminationGracePeriodSeconds 설정 확인

배포 후:
  □ 배포 구간 주문 Reconciliation 자동 실행
  □ revenue_summary와 원본 orders 간 오차 확인
  □ Grafana 매출 대시보드에서 배포 시점 전후 급변 여부 확인
```

**ShedLock으로 Materialized View 중복 실행 방지:**

```java
// v1과 v2가 동시에 스케줄러를 실행해도 하나만 실행됨
@Scheduled(cron = "0 */10 * * * *")
@SchedulerLock(
    name = "revenue_materialized_view_refresh",
    lockAtLeastFor = "PT5M",
    lockAtMostFor = "PT9M"
)
public void refreshMaterializedView() {
    // $merge로 revenue_summary 갱신
}
```

## 참고 자료

- [MongoDB Aggregation Pipeline 공식 문서](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/)
- [MongoDB $merge (Materialized View)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/merge/)
- [MongoDB Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
- [Spring Data MongoDB - Aggregation](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html)
- [ShedLock - Distributed Lock for Schedulers](https://github.com/lukas-krecan/ShedLock)
