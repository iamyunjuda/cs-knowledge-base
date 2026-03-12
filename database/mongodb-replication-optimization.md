---
title: "MongoDB 심화 — mongos/mongod 아키텍처, Null 인덱스 처리, Replica 지연 해결 전략"
parent: Database
nav_order: 2
---

# MongoDB 심화 — mongos/mongod 아키텍처, Null 인덱스 처리, Replica 지연 해결 전략

## 핵심 정리

### 1. mongod와 mongos의 역할

#### mongod (MongoDB Daemon)
MongoDB의 **핵심 데이터 서버 프로세스**로, 실제 데이터를 저장하고 쿼리를 처리한다.

```
┌─────────────────────────────────────┐
│              mongod                 │
│                                     │
│  ┌───────────┐  ┌───────────────┐   │
│  │ Storage   │  │ Query Engine  │   │
│  │ Engine    │  │               │   │
│  │ (WiredTiger)│ │ - CRUD 처리   │   │
│  │           │  │ - 인덱스 관리  │   │
│  │ - B-Tree  │  │ - Aggregation │   │
│  │ - 압축    │  │               │   │
│  └───────────┘  └───────────────┘   │
│                                     │
│  ┌───────────────────────────────┐   │
│  │ Replication / Journaling     │   │
│  │ - oplog 관리                  │   │
│  │ - WAL (Write-Ahead Logging)  │   │
│  └───────────────────────────────┘   │
└─────────────────────────────────────┘
```

**역할 요약:**
- 데이터 저장/조회/수정/삭제 (CRUD)
- 인덱스 생성 및 관리
- Replica Set의 멤버로 동작 (Primary / Secondary)
- WiredTiger 스토리지 엔진으로 데이터 관리
- oplog(Operation Log)를 통한 복제 데이터 전파

#### mongos (MongoDB Router / Query Router)
**Sharded Cluster에서만 존재**하는 라우팅 프로세스로, 자체적으로 데이터를 저장하지 않는다.

```
┌──────────────────────────────────────────────────────┐
│                    Application                       │
│                        │                             │
│                   ┌────▼────┐                        │
│                   │  mongos │  (Query Router)        │
│                   └────┬────┘                        │
│            ┌───────────┼───────────┐                 │
│       ┌────▼────┐ ┌────▼────┐ ┌────▼────┐           │
│       │ Shard A │ │ Shard B │ │ Shard C │           │
│       │(mongod) │ │(mongod) │ │(mongod) │           │
│       │ RS Set  │ │ RS Set  │ │ RS Set  │           │
│       └─────────┘ └─────────┘ └─────────┘           │
│                                                      │
│       ┌──────────────────────────────┐               │
│       │  Config Server (mongod)     │               │
│       │  - Shard 메타데이터 저장      │               │
│       │  - Chunk 분배 정보           │               │
│       └──────────────────────────────┘               │
└──────────────────────────────────────────────────────┘
```

**역할 요약:**
- 클라이언트 요청을 적절한 Shard로 **라우팅**
- Config Server에서 메타데이터(어떤 데이터가 어떤 Shard에 있는지)를 읽어 판단
- Shard Key 기반으로 **Targeted Query** vs **Scatter-Gather Query** 결정
- 여러 Shard에서 온 결과를 **병합(merge)** 하여 클라이언트에 반환
- Stateless이므로 **여러 개를 띄워서 로드 밸런싱** 가능

#### mongod vs mongos 비교

| 구분 | mongod | mongos |
|------|--------|--------|
| **역할** | 데이터 저장 및 처리 | 쿼리 라우팅 |
| **데이터 보유** | O (실제 데이터 저장) | X (Stateless) |
| **단독 실행** | 가능 (Standalone / Replica Set) | 불가능 (Sharded Cluster 전용) |
| **스케일링** | Replica Set으로 가용성 확보 | 여러 인스턴스를 띄워 분산 |
| **oplog** | 있음 | 없음 |
| **Config Server** | 불필요 (단독 가능) | 필수 (메타데이터 의존) |

#### Sharded Cluster에서의 쿼리 흐름

```
1. 클라이언트 → mongos로 쿼리 전송
2. mongos → Config Server에서 Shard Key ↔ Chunk 매핑 확인
3. mongos → 해당 Shard(mongod)로 쿼리 전달

   Case A: Shard Key 포함 쿼리 → Targeted Query (특정 Shard만)
   Case B: Shard Key 미포함 → Scatter-Gather (모든 Shard에 브로드캐스트)

4. 각 Shard(mongod) → 결과 반환
5. mongos → 결과 병합 후 클라이언트에 응답
```

> **Scatter-Gather는 성능 병목의 주범이다.** Shard Key를 쿼리에 포함시키는 것이 핵심 최적화 포인트.

---

### 2. 인덱스 값이 null일 때의 처리

#### 기본 동작: null도 인덱스에 포함된다

MongoDB는 기본적으로 **필드가 없거나(missing), 값이 null인 도큐먼트도 인덱스에 포함**한다.

```javascript
// 컬렉션 예시
{ _id: 1, name: "Alice", email: "alice@test.com" }
{ _id: 2, name: "Bob", email: null }           // 명시적 null
{ _id: 3, name: "Charlie" }                     // email 필드 자체가 없음 (missing)

// email에 인덱스 생성
db.users.createIndex({ email: 1 })

// null 검색 → _id:2, _id:3 모두 반환
db.users.find({ email: null })
// → 인덱스를 타고 조회됨 (IXSCAN)
```

**핵심:** MongoDB에서 `null`과 `missing`은 인덱스 관점에서 동일하게 `null` 키로 저장된다.

#### 문제 1: Unique Index + null 충돌

```javascript
db.users.createIndex({ email: 1 }, { unique: true })

// 첫 번째 삽입 → 성공
db.users.insertOne({ name: "Alice" })  // email missing → null로 인덱스 저장

// 두 번째 삽입 → 실패! (duplicate key error)
db.users.insertOne({ name: "Bob" })    // email missing → null 중복
// E11000 duplicate key error
```

#### 해결: Partial Index (부분 인덱스)

```javascript
// email 필드가 존재하는 도큐먼트만 인덱스에 포함
db.users.createIndex(
  { email: 1 },
  {
    unique: true,
    partialFilterExpression: { email: { $exists: true, $type: "string" } }
  }
)

// 이제 email이 없는 도큐먼트는 여러 개 삽입 가능
db.users.insertOne({ name: "Alice" })  // OK (인덱스에 포함 안 됨)
db.users.insertOne({ name: "Bob" })    // OK (인덱스에 포함 안 됨)
db.users.insertOne({ name: "Charlie", email: "c@test.com" })  // OK
db.users.insertOne({ name: "Dave", email: "c@test.com" })      // 실패! (중복)
```

#### 해결: Sparse Index (희소 인덱스)

```javascript
// 필드가 존재하는 도큐먼트만 인덱스에 포함
db.users.createIndex({ email: 1 }, { unique: true, sparse: true })

// email 필드가 없는 도큐먼트 → 인덱스에 미포함 → 중복 에러 안 남
// 단, email: null (명시적 null)은 인덱스에 포함됨!
```

#### Sparse vs Partial Index 비교

| 구분 | Sparse Index | Partial Index |
|------|-------------|---------------|
| **조건** | 필드 존재 여부만 판단 | 세밀한 필터 표현식 가능 |
| **명시적 null** | 포함됨 | `$type`으로 제외 가능 |
| **유연성** | 낮음 | 높음 |
| **권장** | 레거시 | **MongoDB 3.2+ 권장** |

#### 주의: Partial Index의 쿼리 커버리지

```javascript
// Partial Index 생성
db.orders.createIndex(
  { status: 1 },
  { partialFilterExpression: { status: { $exists: true } } }
)

// 이 쿼리는 인덱스를 탐 → status가 존재하는 것만 찾으니까
db.orders.find({ status: "active" })

// 이 쿼리는 인덱스를 안 탐! → null/missing 도큐먼트가 인덱스에 없으므로
db.orders.find({ status: null })          // COLLSCAN
db.orders.find({ status: { $in: [null, "active"] } })  // COLLSCAN
```

> **Partial Index를 사용하면 해당 인덱스가 커버하지 않는 범위의 쿼리는 COLLSCAN으로 빠진다.** 쿼리 패턴을 반드시 함께 고려해야 한다.

---

### 3. Replica Set 복제 지연(Replication Lag) — 실시간성 확보 전략

#### 문제 상황

```
┌──────────┐    write     ┌──────────┐
│  Client  │─────────────▶│ Primary  │
│          │              │ (mongod) │
│          │    read      │          │
│          │──────┐       └────┬─────┘
│          │      │            │ oplog 복제
└──────────┘      │       ┌────▼─────┐
                  └──────▶│Secondary │  ← 여기서 읽으면 0.1~수 초 전 데이터!
                          │ (mongod) │
                          └──────────┘

문제: Primary에 쓴 직후 Secondary에서 읽으면 아직 복제가 안 된 상태
→ "방금 등록한 데이터가 안 보여요" 현상
```

이것이 바로 **Read-Your-Own-Write 문제** (Stale Read)이다.

#### 지연 원인 분석

```
복제 지연 발생 원인 (단계별):

1. Primary에서 write 발생
   └→ oplog에 기록

2. Secondary가 oplog를 tailing (폴링 방식)
   └→ 네트워크 지연 (특히 cross-region)

3. Secondary가 oplog entry 수신
   └→ 수신한 연산을 로컬에 적용 (apply)
   └→ 인덱스 업데이트, 디스크 I/O

4. Secondary 적용 완료
   └→ 이제서야 읽기 가능

각 단계에서 지연 발생 가능:
- 네트워크 RTT (cross-region이면 50~200ms)
- Secondary의 디스크 I/O 부하
- Secondary에서 장시간 실행 쿼리 (lock 경합)
- Primary의 write 부하가 oplog 생성 속도 > Secondary 소비 속도
- 대규모 인덱스 빌드
```

---

#### 해결 단계 1: Read Preference 조정

```javascript
// ❌ 기본값: Secondary에서 읽기 → Stale Read 위험
db.collection.find().readPref("secondaryPreferred")

// ✅ 실시간성 필요한 쿼리 → Primary에서 직접 읽기
db.collection.find({ userId: "abc" }).readPref("primary")
```

**Read Preference 옵션:**

| 옵션 | 동작 | 실시간성 | 가용성 |
|------|------|---------|--------|
| `primary` | Primary에서만 읽기 | 최신 보장 | Primary 장애 시 읽기 불가 |
| `primaryPreferred` | Primary 우선, 불가 시 Secondary | 거의 최신 | 높음 |
| `secondary` | Secondary에서만 읽기 | 지연 가능 | Primary 부하 감소 |
| `secondaryPreferred` | Secondary 우선 | 지연 가능 | 높음 |
| `nearest` | 네트워크 지연 최소 노드 | 불확실 | 가장 높음 |

> **전략:** 모든 읽기를 Primary로 보내면 Primary에 부하가 집중된다. **실시간 필요 쿼리만 선별적으로 `primary`로 설정**하는 것이 핵심.

---

#### 해결 단계 2: Read Concern / Write Concern 조합

```javascript
// Write 시: majority 노드에 복제 완료될 때까지 기다림
db.collection.insertOne(
  { userId: "abc", data: "..." },
  { writeConcern: { w: "majority" } }
)

// Read 시: majority가 커밋한 데이터만 읽음
db.collection.find({ userId: "abc" }).readConcern("majority")
```

**Write Concern + Read Concern 조합 전략:**

```
┌─────────────────────┬───────────────────┬─────────────────────────────┐
│    Write Concern    │   Read Concern    │          효과               │
├─────────────────────┼───────────────────┼─────────────────────────────┤
│ w: 1 (기본)         │ "local" (기본)    │ 최고 속도, Stale Read 가능  │
│ w: "majority"       │ "majority"        │ 과반수 노드 기준 일관성 보장│
│ w: "majority"       │ "linearizable"    │ 최강 일관성, 성능 저하 큼   │
└─────────────────────┴───────────────────┴─────────────────────────────┘
```

> `readConcern: "linearizable"`는 사실상 모든 복제 완료를 기다리기 때문에 **결제, 재고 같은 강일관성(Strong Consistency) 시나리오에서만** 사용한다.

---

#### 해결 단계 3: Causal Consistency Session (인과적 일관성)

MongoDB 3.6+에서 제공하는 **가장 실용적인 해결책**이다.

```javascript
// 세션을 생성하여 "내가 쓴 데이터는 내가 읽을 수 있다"를 보장
const session = db.getMongo().startSession({ causalConsistency: true })
const coll = session.getDatabase("mydb").getCollection("orders")

// 1. Write (Primary)
coll.insertOne({ orderId: "ORD-001", status: "created" })

// 2. Read (Secondary에서 읽더라도 1번 Write 이후 상태를 보장)
const order = coll.find({ orderId: "ORD-001" }).readPref("secondaryPreferred")
// → 반드시 "created" 상태의 도큐먼트가 보임

session.endSession()
```

**동작 원리:**

```
1. 세션 내 write 시 → operationTime(클러스터 타임) 기록
2. 같은 세션 내 read 시 → "최소 이 시점 이후의 데이터를 줘" 요청
3. Secondary가 해당 시점까지 oplog 적용이 안 됐으면 → 적용될 때까지 대기
4. 적용 완료 후 → 결과 반환

핵심: 세션 단위로 "나의 write → 나의 read" 순서를 보장
다른 클라이언트의 write까지는 보장하지 않음
```

> Causal Consistency는 **Read-Your-Own-Write**를 보장하면서도 Secondary 읽기를 활용하여 **Primary 부하를 줄일 수 있는** 가장 균형 잡힌 전략이다.

---

#### 해결 단계 4: 아키텍처 레벨 최적화

위 MongoDB 옵션으로도 부족할 때, 아키텍처 레벨에서 해결하는 방법들:

##### 4-1. Write-Through 캐시 패턴 (Redis)

```
┌────────┐ write ┌─────────┐ async ┌──────────┐
│ Client │──────▶│  Redis  │──────▶│ MongoDB  │
│        │       │ (캐시)  │       │ Primary  │
│        │ read  │         │       └──────────┘
│        │◀──────│         │
└────────┘       └─────────┘

1. 쓰기: Redis에 즉시 반영 + MongoDB에 비동기 저장
2. 읽기: Redis에서 먼저 조회 → 최신 데이터 즉시 응답
3. MongoDB Replica 지연과 무관하게 실시간성 확보
```

```javascript
// 쓰기
async function createOrder(order) {
  // 1. Redis에 즉시 저장 (실시간 읽기용)
  await redis.set(`order:${order.orderId}`, JSON.stringify(order), 'EX', 300)

  // 2. MongoDB에 저장 (영구 저장소)
  await db.collection('orders').insertOne(order)
}

// 읽기 (Redis 우선)
async function getOrder(orderId) {
  // 1. Redis에서 먼저 조회
  const cached = await redis.get(`order:${orderId}`)
  if (cached) return JSON.parse(cached)

  // 2. 캐시 미스 → MongoDB Primary에서 읽기
  return await db.collection('orders').findOne(
    { orderId },
    { readPreference: 'primary' }
  )
}
```

##### 4-2. CQRS (Command Query Responsibility Segregation)

```
┌──────────────────────────────────────────────┐
│              CQRS 패턴 적용                   │
│                                              │
│  Command (쓰기)          Query (읽기)         │
│  ┌──────────┐           ┌──────────────┐     │
│  │  Write   │  Event/   │  Read Model  │     │
│  │  Model   │──CDC─────▶│ (Elasticsearch│    │
│  │ (MongoDB)│           │  / Redis)    │     │
│  └──────────┘           └──────────────┘     │
│                                              │
│  - Write는 MongoDB로  - Read는 최적화된       │
│  - 정합성 보장           별도 저장소에서        │
│  - 느려도 OK            - 실시간 반영          │
└──────────────────────────────────────────────┘
```

쓰기와 읽기를 분리하여, **읽기용 저장소는 쓰기 이벤트를 받아 즉시 업데이트**한다. MongoDB의 Replica 지연과 무관하게 실시간 데이터를 제공할 수 있다.

##### 4-3. Change Stream 활용 (이벤트 드리븐)

```javascript
// MongoDB Change Stream으로 실시간 변경 감지
const changeStream = db.collection('orders').watch(
  [{ $match: { operationType: { $in: ['insert', 'update'] } } }],
  { fullDocument: 'updateLookup' }
)

changeStream.on('change', async (change) => {
  const doc = change.fullDocument

  // 변경 즉시 캐시 업데이트
  await redis.set(`order:${doc.orderId}`, JSON.stringify(doc))

  // 또는 WebSocket으로 클라이언트에 실시간 Push
  io.to(`user:${doc.userId}`).emit('orderUpdate', doc)
})
```

> Change Stream은 **oplog 기반**으로 동작하며, Secondary가 아닌 **변경 이벤트 자체를 구독**하므로 Replica 지연 문제를 우회할 수 있다.

---

#### 해결 전략 종합 요약 (상황별 권장)

```
┌──────────────────────────────┬──────────────────────────────────────────┐
│         상황                 │             권장 전략                     │
├──────────────────────────────┼──────────────────────────────────────────┤
│ 단순 "방금 쓴 거 읽기"       │ Causal Consistency Session               │
│                              │ + readPref("secondaryPreferred")         │
├──────────────────────────────┼──────────────────────────────────────────┤
│ 결제/재고 등 강일관성 필요    │ writeConcern: "majority"                 │
│                              │ + readConcern: "linearizable"            │
│                              │ + readPref("primary")                    │
├──────────────────────────────┼──────────────────────────────────────────┤
│ 대시보드/실시간 모니터링      │ Change Stream → Redis/WebSocket Push     │
├──────────────────────────────┼──────────────────────────────────────────┤
│ 읽기 트래픽 매우 높음         │ Write-Through Cache (Redis)              │
│                              │ 또는 CQRS 패턴                           │
├──────────────────────────────┼──────────────────────────────────────────┤
│ Cross-Region 배포             │ 쓰기: Primary Region 고정               │
│                              │ 읽기: nearest + Causal Consistency       │
│                              │ + 지역별 Redis 캐시                      │
└──────────────────────────────┴──────────────────────────────────────────┘
```

---

## 헷갈렸던 포인트

### Q1: mongos 없이도 MongoDB를 사용할 수 있나?
**Yes.** mongos는 **Sharded Cluster 전용**이다. Standalone 모드나 Replica Set만으로 운영할 때는 mongod만 있으면 된다. mongos는 데이터가 여러 Shard에 분산되었을 때 라우팅 역할을 위해 필요하다.

### Q2: Sparse Index에서 `email: null`(명시적)과 email 필드 없음(missing)은 다르게 처리되나?
**Yes.** Sparse Index는 **필드가 존재하는 도큐먼트만** 인덱스에 포함한다.
- `{ email: null }` → 필드가 존재함 → **인덱스에 포함**
- `{ name: "Bob" }` → email 필드 자체가 없음 → **인덱스에 미포함**

따라서 Unique + Sparse 조합에서도 `email: null`이 2개 이상이면 duplicate key 에러가 발생한다. 이걸 완전히 해결하려면 **Partial Index + `$type` 조건**을 써야 한다.

### Q3: Causal Consistency는 모든 클라이언트 간에 일관성을 보장하나?
**No.** Causal Consistency는 **같은 세션(session) 내에서만** 인과적 순서를 보장한다. 사용자 A가 쓴 데이터를 사용자 B가 즉시 보는 것은 보장하지 않는다. 그런 수준의 일관성이 필요하면 `readConcern: "linearizable"`를 써야 한다 (성능 비용이 크다).

### Q4: Write Concern `w: "majority"`를 쓰면 성능이 얼마나 떨어지나?
Primary 혼자 확인하는 `w: 1` 대비 **과반수 노드의 디스크 기록 확인을 기다리므로** 지연이 추가된다. 같은 데이터센터(같은 리전) 내 Replica Set이면 1~5ms 추가 정도지만, Cross-Region이면 네트워크 RTT만큼 (50~200ms) 추가될 수 있다. **데이터 정합성이 중요한 쓰기에만 선택적으로** 적용하는 것이 현실적이다.

### Q5: Change Stream은 Primary에서만 watch할 수 있나?
**No.** MongoDB 4.0+부터 Change Stream은 **Secondary에서도 watch 가능**하다. 하지만 Secondary에서 watch하면 해당 Secondary까지 oplog가 복제된 시점부터의 이벤트만 수신한다. 가장 빠른 이벤트 수신이 필요하면 Primary에서 watch하는 것이 좋다.

---

## 참고 자료
- [MongoDB 공식 문서 — Replication](https://www.mongodb.com/docs/manual/replication/)
- [MongoDB 공식 문서 — Sharding](https://www.mongodb.com/docs/manual/sharding/)
- [MongoDB 공식 문서 — Causal Consistency](https://www.mongodb.com/docs/manual/core/causal-consistency-read-write-concerns/)
- [MongoDB 공식 문서 — Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/)
- [MongoDB 공식 문서 — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
