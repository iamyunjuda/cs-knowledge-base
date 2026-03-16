---
title: "MongoDB 세션 관리 심화 — RDB 커넥션과의 근본적 차이, Spring Data MongoDB 실전"
parent: Database
nav_order: 5
---

# MongoDB 세션 관리 심화 — RDB 커넥션과의 근본적 차이, Spring Data MongoDB 실전

## 핵심 정리

### 1. RDB 커넥션/세션 vs MongoDB 세션 — 근본적 차이

#### RDB: 커넥션 = 세션 (1:1 바인딩)

```
┌──────────────────────────────────────────────────────────────┐
│                       RDB (MySQL/PostgreSQL)                 │
│                                                              │
│  Application                        DB Server                │
│  ┌────────┐    TCP Connection    ┌────────────────┐          │
│  │ Thread │◄═══════════════════►│ Session (=연결)  │          │
│  │   #1   │   1개의 TCP 소켓     │                 │          │
│  └────────┘                      │ - 트랜잭션 상태  │          │
│                                  │ - 임시 테이블    │          │
│  ┌────────┐    TCP Connection    │ - SET 변수      │          │
│  │ Thread │◄═══════════════════►│ - Lock 보유 정보 │          │
│  │   #2   │                      │ - Cursor 상태   │          │
│  └────────┘                      └────────────────┘          │
│                                                              │
│  핵심: TCP 연결 하나 = DB 세션 하나 = 트랜잭션 컨텍스트 하나   │
│  연결이 끊기면 → 세션 소멸 → 트랜잭션 롤백 → 락 해제          │
└──────────────────────────────────────────────────────────────┘
```

**RDB 세션의 특징:**
- TCP 커넥션과 세션이 **물리적으로 1:1 바인딩**
- 세션 안에서 `BEGIN → SQL → COMMIT/ROLLBACK` 트랜잭션 관리
- 커넥션 풀(HikariCP 등)은 **TCP 커넥션 자체를 재사용**
- 커넥션이 끊기면 세션도 사라짐 → 트랜잭션 자동 롤백

```java
// Spring + RDB: 커넥션 = 세션 = 트랜잭션 스코프
@Transactional  // 커넥션 풀에서 꺼낸 1개의 커넥션에 바인딩
public void transfer(Long from, Long to, int amount) {
    accountRepository.debit(from, amount);   // 같은 커넥션
    accountRepository.credit(to, amount);    // 같은 커넥션
    // 메서드 끝 → 같은 커넥션으로 COMMIT
}
```

#### MongoDB: 커넥션과 세션이 분리 (N:M)

```
┌──────────────────────────────────────────────────────────────┐
│                         MongoDB                              │
│                                                              │
│  Application (Driver)              mongod / mongos           │
│                                                              │
│  ┌────────────────────┐                                      │
│  │  Connection Pool   │          ┌───────────────────┐       │
│  │  ┌──────┐ ┌──────┐ │          │  Server Sessions   │       │
│  │  │Conn 1│ │Conn 2│ │          │                   │       │
│  │  │      │ │      │ │          │  Session A ───────│───┐   │
│  │  │      │ │      │ │          │  Session B ───────│─┐ │   │
│  │  └──────┘ └──────┘ │          │  Session C        │ │ │   │
│  └────────────────────┘          └───────────────────┘ │ │   │
│                                                        │ │   │
│      어떤 커넥션이든     ◄─── Session은 커넥션에 ───►   │ │   │
│      세션을 실어 보냄          바인딩되지 않음           │ │   │
│                                                        │ │   │
│  핵심: Session은 논리적 식별자(lsid)로 관리             │ │   │
│  커넥션이 바뀌어도 같은 세션 → 같은 트랜잭션 컨텍스트    │ │   │
└──────────────────────────────────────────────────────────┘ │
```

**MongoDB 세션의 특징:**
- 세션은 **Logical Session ID (lsid)**로 식별되는 **논리적 개념**
- 하나의 세션이 **여러 커넥션을 넘나들 수 있음**
- 커넥션 풀의 어떤 커넥션이든 세션 ID를 실어 보내면 서버가 인식
- 세션 타임아웃(기본 30분)으로 만료 관리 (커넥션과 독립)

```
RDB:   커넥션 끊김 → 세션 종료 → 트랜잭션 롤백 (강결합)
MongoDB: 커넥션 끊김 → 다른 커넥션으로 같은 세션 계속 사용 가능 (느슨한 결합)
```

---

### 2. MongoDB 세션의 내부 구조

#### Logical Session ID (lsid)

```
모든 MongoDB 명령에는 lsid가 포함된다 (3.6+ 암시적 세션):

{
  "find": "orders",
  "filter": { "status": "active" },
  "lsid": {                          ← 세션 식별자
    "id": UUID("a1b2c3d4-...")
  },
  "$clusterTime": { ... },
  "$db": "mydb"
}

서버는 lsid를 보고:
1. 어떤 세션인지 식별
2. 해당 세션의 트랜잭션 상태 확인
3. Causal Consistency 보장을 위한 시간 추적
4. Retryable Write의 중복 방지
```

#### 암시적 세션 vs 명시적 세션

```
┌─────────────────────────────────────────────────────────────┐
│  암시적 세션 (Implicit Session) — MongoDB 3.6+ 기본 동작     │
│                                                             │
│  - 모든 단일 명령에 자동으로 lsid 부여                       │
│  - 명령이 끝나면 세션도 끝 (1-shot)                          │
│  - 개발자가 세션을 의식할 필요 없음                           │
│  - Retryable Write 지원                                     │
│                                                             │
│  db.orders.insertOne({ orderId: "ORD-1" })                  │
│  // 내부적으로 lsid가 자동 생성되어 전송됨                    │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  명시적 세션 (Explicit Session) — 개발자가 직접 생성/관리     │
│                                                             │
│  - 멀티 도큐먼트 트랜잭션 사용 시 필수                       │
│  - Causal Consistency 보장 시 필수                           │
│  - 여러 명령을 하나의 세션으로 묶음                           │
│  - 반드시 endSession()으로 정리                              │
│                                                             │
│  const session = client.startSession()                      │
│  session.startTransaction()                                 │
│  // ... 여러 명령 ...                                       │
│  session.commitTransaction()                                │
│  session.endSession()                                       │
└─────────────────────────────────────────────────────────────┘
```

#### 세션이 필요한 기능들

| 기능 | 암시적 세션 | 명시적 세션 필요 |
|------|:---------:|:-------------:|
| 단일 CRUD | O | X |
| Retryable Write | O | X |
| 멀티 도큐먼트 트랜잭션 | X | **O** |
| Causal Consistency | X | **O** |
| Snapshot Read | X | **O** |
| Change Stream (resume) | O | X |

---

### 3. MongoDB 커넥션 풀 vs RDB 커넥션 풀

#### RDB 커넥션 풀 (HikariCP)

```
┌─────────────────────────────────────────┐
│           HikariCP (RDB)                │
│                                         │
│  Pool Size: 10개 TCP 커넥션              │
│                                         │
│  Thread-1 → Conn#3 (대출)              │
│             └→ BEGIN; UPDATE; COMMIT;    │
│             └→ 반환 (같은 커넥션!)        │
│                                         │
│  핵심: 1 Thread = 1 Connection = 1 Tx   │
│  트랜잭션 동안 커넥션 독점               │
│  풀이 고갈되면 대기 (병목)               │
└─────────────────────────────────────────┘
```

#### MongoDB 커넥션 풀 (MongoDB Driver)

```
┌─────────────────────────────────────────────────────────────┐
│           MongoDB Driver Connection Pool                    │
│                                                             │
│  Pool Size: 100개 TCP 커넥션 (기본 maxPoolSize=100)         │
│                                                             │
│  Request-1:                                                 │
│    Op #1 → Conn#7 (체크아웃) → 명령 전송 → Conn#7 (반환)    │
│    Op #2 → Conn#12 (체크아웃) → 명령 전송 → Conn#12 (반환)  │
│    (같은 세션이지만 다른 커넥션 사용 가능!)                    │
│                                                             │
│  단, 트랜잭션 중에는:                                        │
│    startTransaction()                                       │
│    Op #1 → Conn#7 (체크아웃) → 명령 전송 (반환 안 함!)       │
│    Op #2 → Conn#7 (같은 커넥션 유지)  ← 트랜잭션 동안 고정   │
│    commitTransaction() → Conn#7 (반환)                      │
│                                                             │
│  핵심: 트랜잭션 밖에서는 커넥션 공유 → 효율적                 │
│       트랜잭션 안에서만 커넥션 고정 (pinning)                 │
└─────────────────────────────────────────────────────────────┘
```

**핵심 차이 요약:**

```
RDB:     커넥션을 빌려서 → 트랜잭션 전체를 수행 → 반환 (독점)
MongoDB: 명령마다 커넥션을 빌려서 → 1개 명령 수행 → 즉시 반환 (공유)
         (트랜잭션 시에만 커넥션 고정)
```

> MongoDB가 **기본 maxPoolSize를 100으로** 높게 잡는 이유: 명령마다 빠르게 빌렸다 반환하므로, 동시 실행 중인 명령 수만큼 커넥션이 필요하다. RDB처럼 트랜잭션 동안 독점하는 것이 아니라서 풀 크기가 커도 괜찮다.

---

### 4. Spring Data MongoDB에서의 세션 사용

#### 4-1. 기본 사용 — 세션 없이 (암시적 세션)

```java
@Service
public class OrderService {

    @Autowired
    private MongoTemplate mongoTemplate;

    // 단일 명령 → 암시적 세션 → 세션 관리 불필요
    public Order createOrder(Order order) {
        return mongoTemplate.save(order);
        // 내부적으로 드라이버가 lsid를 자동 생성하여 전송
    }

    public Order findOrder(String orderId) {
        return mongoTemplate.findById(orderId, Order.class);
    }
}
```

#### 4-2. 명시적 세션 — MongoTemplate + ClientSession

```java
@Service
public class OrderService {

    @Autowired
    private MongoDatabaseFactory mongoDatabaseFactory;

    @Autowired
    private MongoTemplate mongoTemplate;

    public void transferWithSession() {
        // 1. ClientSession 직접 생성
        ClientSession session = mongoDatabaseFactory
            .getMongoDatabase()
            .getClient()
            .startSession();

        try {
            // 2. 세션과 함께 명령 실행
            mongoTemplate.withSession(() -> session)
                .execute(action -> {
                    // 이 블록 안의 모든 명령은 같은 세션
                    action.updateFirst(
                        Query.query(Criteria.where("accountId").is("A")),
                        new Update().inc("balance", -1000),
                        "accounts"
                    );
                    action.updateFirst(
                        Query.query(Criteria.where("accountId").is("B")),
                        new Update().inc("balance", 1000),
                        "accounts"
                    );
                    return null;
                });
        } finally {
            session.close();  // 반드시 세션 종료
        }
    }
}
```

#### 4-3. 멀티 도큐먼트 트랜잭션 — @Transactional

```java
// 1. 트랜잭션 매니저 설정
@Configuration
public class MongoConfig {

    @Bean
    MongoTransactionManager transactionManager(MongoDatabaseFactory dbFactory) {
        return new MongoTransactionManager(dbFactory);
    }
}

// 2. 서비스에서 @Transactional 사용
@Service
public class OrderService {

    @Autowired
    private MongoTemplate mongoTemplate;

    @Transactional  // ← Spring이 세션 생성 + 트랜잭션 시작/커밋/롤백 관리
    public void placeOrder(Order order, String userId) {
        // 같은 세션, 같은 트랜잭션
        mongoTemplate.save(order);

        mongoTemplate.updateFirst(
            Query.query(Criteria.where("userId").is(userId)),
            new Update().inc("orderCount", 1),
            "users"
        );

        // 메서드 정상 종료 → commitTransaction()
        // 예외 발생 → abortTransaction()
    }
}
```

**@Transactional의 내부 동작:**

```
1. MongoTransactionManager가 ClientSession 생성
2. session.startTransaction() 호출
3. ThreadLocal에 세션 바인딩 (TransactionSynchronizationManager)
4. MongoTemplate이 현재 스레드의 세션을 자동으로 사용
5. 메서드 종료 시:
   - 정상: session.commitTransaction()
   - 예외: session.abortTransaction()
6. session.close()

※ RDB의 @Transactional과 거의 동일한 방식!
   차이점: 내부에서 Connection이 아닌 ClientSession을 관리
```

#### 4-4. Causal Consistency Session in Spring

```java
@Service
public class OrderService {

    @Autowired
    private MongoDatabaseFactory dbFactory;

    @Autowired
    private MongoTemplate mongoTemplate;

    public Order createAndReadBack(Order order) {
        // Causal Consistency 세션 옵션
        ClientSessionOptions options = ClientSessionOptions.builder()
            .causallyConsistent(true)
            .build();

        try (ClientSession session = dbFactory.getMongoDatabase()
                .getClient().startSession(options)) {

            return mongoTemplate.withSession(() -> session)
                .execute(action -> {
                    // Write (Primary)
                    action.save(order);

                    // Read (Secondary에서 읽더라도 위 Write 이후 상태 보장)
                    return action.findOne(
                        Query.query(Criteria.where("orderId").is(order.getOrderId())),
                        Order.class
                    );
                });
        }
    }
}
```

#### 4-5. Reactive (WebFlux) 환경에서의 세션

```java
@Service
public class ReactiveOrderService {

    @Autowired
    private ReactiveMongoTemplate reactiveMongoTemplate;

    @Autowired
    private ReactiveMongoDatabaseFactory dbFactory;

    // Reactive 환경에서는 ReactiveClientSession 사용
    public Mono<Order> createOrderReactive(Order order) {
        return dbFactory.getSession()
            .flatMap(session -> {
                session.startTransaction();

                return reactiveMongoTemplate
                    .withSession(session)
                    .save(order)
                    .doOnSuccess(saved -> session.commitTransaction())
                    .doOnError(err -> session.abortTransaction())
                    .doFinally(signal -> session.close());
            });
    }
}

// 또는 ReactiveMongoTransactionManager + @Transactional
@Configuration
public class ReactiveMongoConfig {

    @Bean
    ReactiveMongoTransactionManager transactionManager(
            ReactiveMongoDatabaseFactory dbFactory) {
        return new ReactiveMongoTransactionManager(dbFactory);
    }
}

@Service
public class ReactiveOrderService {

    @Transactional  // Reactive에서도 동작!
    public Mono<Order> placeOrder(Order order) {
        return reactiveMongoTemplate.save(order);
    }
}
```

---

### 5. 세션 관련 주의사항과 트러블슈팅

#### 주의 1: MongoDB 트랜잭션은 Replica Set 필수

```
MongoDB 멀티 도큐먼트 트랜잭션 요구사항:
- Replica Set 또는 Sharded Cluster (4.2+)
- Standalone mongod에서는 트랜잭션 불가!
- 로컬 개발 시 단일 노드 Replica Set으로 구성 필요

// docker-compose.yml (로컬 개발용)
services:
  mongo:
    image: mongo:7.0
    command: ["--replSet", "rs0"]
    ports:
      - "27017:27017"

// 초기화
rs.initiate({ _id: "rs0", members: [{ _id: 0, host: "localhost:27017" }] })
```

#### 주의 2: 트랜잭션 시간 제한

```
MongoDB 트랜잭션 제한:
- 기본 최대 실행 시간: 60초 (transactionLifetimeLimitSeconds)
- 기본 maxTimeMS: 없음 (무제한)
- 트랜잭션 내 oplog 크기 제한: 16MB

→ RDB처럼 긴 트랜잭션을 유지하는 패턴은 안 맞음
→ 짧고 빠른 트랜잭션이 MongoDB 철학
→ 긴 비즈니스 로직은 Saga 패턴 고려
```

#### 주의 3: 세션 누수 (Session Leak)

```java
// ❌ 잘못된 코드 — 세션 누수
public void badExample() {
    ClientSession session = mongoClient.startSession();
    session.startTransaction();
    mongoTemplate.withSession(() -> session).execute(action -> {
        action.save(new Order());
        throw new RuntimeException("실패!");  // 세션 close가 안 됨!
    });
    // session.close() 호출 안 됨 → 세션 누수
    // 서버에 30분간 좀비 세션 잔류
}

// ✅ 올바른 코드 — try-with-resources
public void goodExample() {
    try (ClientSession session = mongoClient.startSession()) {
        session.startTransaction();
        try {
            mongoTemplate.withSession(() -> session).execute(action -> {
                action.save(new Order());
                return null;
            });
            session.commitTransaction();
        } catch (Exception e) {
            session.abortTransaction();
            throw e;
        }
    }  // auto close
}

// ✅ 가장 깔끔한 코드 — @Transactional 사용 (Spring이 관리)
@Transactional
public void bestExample() {
    mongoTemplate.save(new Order());
    // Spring이 세션 생성/커밋/롤백/종료 모두 관리
}
```

#### 주의 4: Sharded Cluster에서의 트랜잭션 (4.2+)

```
Sharded Cluster 트랜잭션 추가 제약:

1. 트랜잭션 안에서 Shard 간 명령 → 2-Phase Commit 발생
   → 단일 Shard 트랜잭션보다 느림

2. 트랜잭션 중 Chunk Migration 발생 시
   → TransientTransactionError → 재시도 필요

3. CrossShardTransaction은 Coordinator Shard 필요
   → mongos가 트랜잭션 코디네이터 역할

권장: 가능하면 같은 Shard에 트랜잭션 범위를 한정
     (Shard Key 설계가 핵심!)
```

---

### 6. 전체 비교 정리

```
┌─────────────────────┬──────────────────────┬──────────────────────┐
│       항목          │       RDB            │     MongoDB          │
├─────────────────────┼──────────────────────┼──────────────────────┤
│ 세션 식별           │ TCP 커넥션 자체       │ lsid (논리적 UUID)   │
│ 세션-커넥션 관계     │ 1:1 (강결합)         │ N:M (느슨한 결합)    │
│ 커넥션 반환 시점     │ 트랜잭션 종료 후      │ 명령 완료 후 즉시    │
│ 트랜잭션 중 커넥션   │ 독점 (pinned)        │ 고정 (pinned)        │
│ 세션 만료           │ 커넥션 끊기면 종료    │ 30분 타임아웃        │
│ 커넥션 풀 기본 크기  │ 10~20 (HikariCP)    │ 100 (Driver)         │
│ 트랜잭션 지원       │ 기본 (단일 행도 Tx)   │ 4.0+ (Replica Set)   │
│ 긴 트랜잭션         │ 가능 (주의 필요)      │ 비권장 (60초 제한)   │
│ Spring 관리 방식    │ DataSource +         │ MongoDatabaseFactory │
│                     │ TransactionManager   │ + MongoTxManager     │
│ @Transactional 동작 │ Connection 바인딩    │ ClientSession 바인딩 │
│ Reactive 지원       │ R2DBC               │ ReactiveMongoTemplate│
└─────────────────────┴──────────────────────┴──────────────────────┘
```

---

## 헷갈렸던 포인트

### Q1: MongoDB도 커넥션 풀을 쓰는데, RDB 커넥션 풀과 뭐가 다른 건가?
**용도가 다르다.** RDB 커넥션 풀(HikariCP)은 **트랜잭션 단위로 커넥션을 대출/반환**하지만, MongoDB 커넥션 풀은 **명령 단위로 대출/반환**한다. MongoDB에서는 세션(lsid)이 트랜잭션 컨텍스트를 추적하기 때문에, 커넥션이 바뀌어도 세션은 유지된다. 그래서 MongoDB는 풀 크기를 크게(100) 잡아도 **각 커넥션의 점유 시간이 짧아서** 효율적이다.

### Q2: Spring에서 MongoDB @Transactional을 쓰면 RDB처럼 커넥션을 독점하나?
**트랜잭션 동안에는 Yes.** `@Transactional` 범위 안에서 MongoDB도 **커넥션 pinning**이 발생한다. 트랜잭션의 모든 명령이 같은 커넥션을 통해 전송되어야 서버가 원자성을 보장할 수 있기 때문이다. 하지만 트랜잭션 밖에서는 명령마다 커넥션을 빠르게 교체한다.

### Q3: 암시적 세션이면 모든 명령에 세션이 만들어지는 건데, 오버헤드가 크지 않나?
**매우 가볍다.** 암시적 세션은 서버 측에서 UUID 하나를 키로 메모리에 간단한 메타데이터만 유지한다. 명령이 끝나면 즉시 정리된다. RDB에서 매번 TCP 핸드셰이크를 하는 것과 달리, MongoDB는 기존 커넥션에 lsid 필드 하나를 추가하는 것뿐이므로 오버헤드가 거의 없다.

### Q4: 로컬에서 Standalone MongoDB로 개발하다가 운영 환경(Replica Set)에서 트랜잭션 에러가 나는 이유는?
**Standalone에서는 멀티 도큐먼트 트랜잭션이 지원되지 않기 때문**이다. `@Transactional`이 Spring 레벨에서는 에러 없이 동작하는 것처럼 보이지만, 실제로 MongoDB 서버가 `startTransaction()`을 거부한다. 로컬에서도 **단일 노드 Replica Set**으로 구성해야 트랜잭션을 테스트할 수 있다.

### Q5: MongoDB의 Causal Consistency Session과 @Transactional을 같이 써야 하나?
**목적이 다르다.** `@Transactional`은 **여러 도큐먼트에 대한 원자적 쓰기**를 보장하고, Causal Consistency Session은 **내가 쓴 데이터를 내가 읽을 수 있는 순서 보장**을 한다. 동시에 쓸 수 있지만, 대부분의 경우 `@Transactional`은 Primary에서만 동작하므로 Causal Consistency는 **트랜잭션 없이 Secondary에서 읽기를 할 때** 더 의미가 있다.

---

## 참고 자료
- [MongoDB 공식 문서 — Sessions](https://www.mongodb.com/docs/manual/reference/server-sessions/)
- [MongoDB 공식 문서 — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB 공식 문서 — Connection Pool](https://www.mongodb.com/docs/manual/administration/connection-pool-overview/)
- [Spring Data MongoDB — Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html)
