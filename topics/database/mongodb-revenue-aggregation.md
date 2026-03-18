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

## 참고 자료

- [MongoDB Aggregation Pipeline 공식 문서](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/)
- [MongoDB $merge (Materialized View)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/merge/)
- [MongoDB Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
- [Spring Data MongoDB - Aggregation](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html)
