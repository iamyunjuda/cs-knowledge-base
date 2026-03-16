---
title: "DB 커넥션 풀 동작 원리 — HikariCP 내부 구조부터 DB별 스레드 모델까지"
parent: Spring
nav_order: 3
tags: [HikariCP, Connection Pool, 커넥션풀, JDBC, 멀티스레드, MySQL, PostgreSQL, Oracle, R2DBC, DataSource]
description: "HikariCP 커넥션 풀의 내부 동작 원리, 커넥션 획득/반납 흐름, @Transactional 유무에 따른 차이, DB별 멀티스레드 모델 비교를 정리합니다."
---

# DB 커넥션 풀 동작 원리 — HikariCP 내부 구조부터 DB별 스레드 모델까지

## 핵심 정리

### 왜 커넥션 풀이 필요한가

DB 커넥션 하나를 만드는 데 드는 비용:

```
[애플리케이션]                    [DB 서버]
     |--- TCP 3-way handshake ---→|     ← 네트워크 왕복
     |←--- SYN-ACK ---|           |
     |--- ACK --------|           |
     |                            |
     |--- 인증 요청 (user/pw) ---→|     ← 인증 처리
     |←--- 인증 완료 -------------|
     |                            |
     |--- 세션 초기화 요청 ------→|     ← charset, timezone 등 설정
     |←--- 세션 준비 완료 --------|

     총 비용: 수 ms ~ 수십 ms (네트워크 거리에 따라)
```

매 요청마다 이걸 반복하면 성능이 바닥남. 그래서 **미리 만들어놓고 빌려 쓰는 것**이 커넥션 풀.

---

### HikariCP 내부 구조

Spring Boot 2.0부터 기본 커넥션 풀. 핵심 자료구조는 `ConcurrentBag`.

```
┌─────────────── HikariPool ───────────────┐
│                                           │
│  ConcurrentBag<PoolEntry>                 │
│  ┌───────────────────────────────────┐    │
│  │ sharedList (CopyOnWriteArrayList) │    │ ← 전체 커넥션 목록
│  │  [PoolEntry0] [PoolEntry1] [...]  │    │
│  └───────────────────────────────────┘    │
│                                           │
│  threadList (ThreadLocal<List>)           │ ← 스레드별 최근 사용 커넥션
│  ┌──────────┐ ┌──────────┐               │
│  │ Thread-1 │ │ Thread-2 │  ...          │
│  │ [Entry2] │ │ [Entry5] │               │
│  └──────────┘ └──────────┘               │
│                                           │
│  handoffQueue (SynchronousQueue)         │ ← 대기 스레드에 직접 전달
│                                           │
│  addConnectionExecutor                   │ ← 새 커넥션 생성 전용 스레드
│                                           │
└───────────────────────────────────────────┘
```

#### 커넥션 획득 순서 (borrow)

```java
// HikariCP ConcurrentBag.borrow() 의 실제 로직 흐름
public PoolEntry borrow(long timeout, TimeUnit timeUnit) {

    // ① ThreadLocal에서 먼저 찾기 (가장 빠름, CAS 1회)
    List<PoolEntry> list = threadList.get();
    for (PoolEntry entry : list) {
        if (entry.compareAndSet(STATE_NOT_IN_USE, STATE_IN_USE)) {
            return entry;  // 히트! → 이전에 이 스레드가 쓰던 커넥션 재사용
        }
    }

    // ② sharedList 전체 스캔 (CAS로 선점 시도)
    for (PoolEntry entry : sharedList) {
        if (entry.compareAndSet(STATE_NOT_IN_USE, STATE_IN_USE)) {
            return entry;
        }
    }

    // ③ 둘 다 실패 → handoffQueue에서 대기 (타임아웃까지)
    //    다른 스레드가 반납하면 여기서 받음
    PoolEntry entry = handoffQueue.poll(timeout, timeUnit);
    if (entry == null) {
        throw new SQLTransientConnectionException(
            "Connection is not available, request timed out after " + timeout + "ms"
        );
    }
    return entry;
}
```

**왜 ThreadLocal을 먼저 보는가?**
- 같은 스레드가 같은 커넥션을 재사용하면 CPU 캐시 히트율이 높음
- Lock 없이 CAS(Compare-And-Swap) 한 번으로 획득 가능
- HikariCP가 다른 풀(DBCP, C3P0)보다 빠른 핵심 이유

#### 커넥션 반납 (requite)

```java
// 반납 흐름
public void requite(PoolEntry entry) {
    entry.setState(STATE_NOT_IN_USE);  // 상태 변경

    // 대기 중인 스레드가 있으면 직접 전달 (handoff)
    if (waiters.get() > 0) {
        handoffQueue.offer(entry);     // SynchronousQueue로 즉시 전달
    }
    // 아니면 그냥 sharedList에 남겨둠 (다음 borrow에서 ②단계로 찾음)
}
```

---

### @Transactional 유무에 따른 커넥션 흐름

#### @Transactional이 있을 때

```
HTTP 요청
  → DispatcherServlet
    → Controller
      → AOP Proxy (TransactionInterceptor)
        → PlatformTransactionManager.getTransaction()
          → DataSourceTransactionManager.doBegin()
            → DataSourceUtils.getConnection(dataSource)
              → HikariDataSource.getConnection()     ← ★ 여기서 풀에서 빌림
            → connection.setAutoCommit(false)
          → TransactionSynchronizationManager에 커넥션 바인딩 (ThreadLocal)

        → 실제 Service 로직 실행
          → Repository.findById()
            → DataSourceUtils.getConnection()
              → TransactionSynchronizationManager에서 꺼냄  ← ★ 같은 커넥션 재사용!
          → Repository.save()
            → 역시 같은 커넥션 사용

        → 예외 없으면 commit / 있으면 rollback
        → DataSourceUtils.releaseConnection()           ← ★ 풀에 반납
```

**핵심**: `TransactionSynchronizationManager`가 ThreadLocal로 현재 스레드의 커넥션을 관리. 같은 트랜잭션 안에서는 **어떤 Repository를 호출하든 같은 커넥션**을 씀.

#### @Transactional이 없을 때

```
HTTP 요청
  → Controller
    → Service (AOP 개입 없음)
      → repo.findById(1L)
        → JdbcTemplate / EntityManager 내부
          → DataSourceUtils.getConnection(dataSource)
            → TransactionSynchronizationManager 확인 → 없음
            → HikariDataSource.getConnection()        ← ★ 커넥션 A 획득
          → SQL 실행
          → DataSourceUtils.releaseConnection()        ← ★ 커넥션 A 반납

      → repo.save(entity)
        → JdbcTemplate / EntityManager 내부
          → HikariDataSource.getConnection()           ← ★ 커넥션 B 획득 (A와 다를 수 있음!)
          → SQL 실행
          → releaseConnection()                        ← ★ 커넥션 B 반납
```

**결과**: 쿼리마다 독립적으로 커넥션을 잡았다 놓았다 함. 두 쿼리 사이에 **일관성 보장 없음**.

---

### 커넥션 = 독립된 세션, 그러면 멀티스레딩인가?

맞다. **커넥션 하나 = DB 서버의 독립된 세션(프로세스 또는 스레드)**. 각 커넥션은:

- 자기만의 트랜잭션 컨텍스트
- 자기만의 락 상태
- 자기만의 임시 테이블, 세션 변수

```
┌─────────────────────────────────────────────────────────┐
│                   애플리케이션 서버                        │
│                                                          │
│  Thread-1 ──conn A──┐                                   │
│  Thread-2 ──conn B──┤      ┌─────────────────────┐      │
│  Thread-3 ──conn C──┼─────→│   HikariCP Pool     │      │
│  Thread-4 (대기중)  │      │  [A] [B] [C] [D]    │      │
│  Thread-5 ──conn D──┘      └──────┬──────────────┘      │
│                                    │                     │
└────────────────────────────────────┼─────────────────────┘
                                     │ TCP 커넥션들
                                     ▼
┌────────────────────────────────────────────────────────┐
│                     DB 서버                             │
│                                                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │ Session A │ │ Session B │ │ Session C │ │ Session D │ │
│  │ (독립)    │ │ (독립)    │ │ (독립)    │ │ (독립)    │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
│                                                        │
│  공유 자원: Buffer Pool, Lock Manager, Log Buffer      │
│  → 여기서 경합 발생 (Row Lock, Table Lock 등)          │
└────────────────────────────────────────────────────────┘
```

**각 세션은 독립적이지만, 공유 자원에서 만남**:
- 같은 Row를 UPDATE하면 → Row Lock 경합
- 같은 페이지를 읽으면 → Buffer Pool에서 공유
- 로그를 쓸 때 → Log Buffer 경합 (WAL)

---

### DB별 멀티스레드 모델 비교

#### MySQL (InnoDB)

```
┌─────────────── mysqld 프로세스 (1개) ──────────────┐
│                                                     │
│  ┌─────────────────────────────────────────────┐   │
│  │          Thread Pool / One-Thread-Per-Conn   │   │
│  │                                              │   │
│  │  Worker Thread 1 ← conn A의 쿼리 실행        │   │
│  │  Worker Thread 2 ← conn B의 쿼리 실행        │   │
│  │  Worker Thread 3 ← conn C의 쿼리 실행        │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  공유 메모리:                                       │
│  - InnoDB Buffer Pool (페이지 캐시)                │
│  - Redo Log Buffer                                 │
│  - Adaptive Hash Index                             │
│  - Lock System (row-level locking)                 │
│                                                     │
│  ★ 기본 모드: 커넥션 1개 = 스레드 1개              │
│  ★ Enterprise: Thread Pool 모드 (M:N 매핑)         │
└─────────────────────────────────────────────────────┘
```

- **단일 프로세스, 멀티스레드**
- 기본: `one-thread-per-connection` — 커넥션 수 = OS 스레드 수
- 커넥션 1000개 → 스레드 1000개 → 컨텍스트 스위칭 폭발
- Enterprise Edition은 Thread Pool 지원 (커넥션 수 > 스레드 수)
- `max_connections` 기본값 151

#### PostgreSQL

```
┌─────────────── postmaster (메인 프로세스) ──────────┐
│                                                      │
│  fork()으로 커넥션마다 자식 프로세스 생성              │
│                                                      │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐       │
│  │ Backend    │ │ Backend    │ │ Backend    │       │
│  │ Process 1  │ │ Process 2  │ │ Process 3  │       │
│  │ (conn A)   │ │ (conn B)   │ │ (conn C)   │       │
│  └────────────┘ └────────────┘ └────────────┘       │
│       ↕ 공유 메모리 (shared_buffers) ↕               │
│                                                      │
│  보조 프로세스들:                                     │
│  - WAL Writer (로그 기록)                            │
│  - Autovacuum (죽은 튜플 정리)                       │
│  - Background Writer (더티 페이지 플러시)             │
│  - Checkpointer                                     │
│                                                      │
│  ★ 커넥션 1개 = 프로세스 1개 (fork)                  │
│  ★ 프로세스라서 메모리 오버헤드 큼 (약 5~10MB/conn)  │
│  ★ 그래서 PgBouncer 같은 외부 풀러가 거의 필수       │
└──────────────────────────────────────────────────────┘
```

- **멀티 프로세스** 모델 (스레드가 아님!)
- `fork()` 비용이 크기 때문에 **PgBouncer**(외부 커넥션 풀러)를 앞에 둠
- `max_connections` 기본값 100 (MySQL보다 적음 — 프로세스라서)
- 프로세스 간 통신은 공유 메모리 (`shared_buffers`)

#### Oracle

```
┌──────────────── Oracle Instance ────────────────────┐
│                                                      │
│  ┌──── Dedicated Server Mode (기본) ────┐            │
│  │ Server Process 1 ← conn A           │            │
│  │ Server Process 2 ← conn B           │            │
│  │ (1:1 매핑, PostgreSQL과 유사)        │            │
│  └──────────────────────────────────────┘            │
│                                                      │
│  ┌──── Shared Server Mode ──────────────┐            │
│  │ Dispatcher → Shared Server Pool      │            │
│  │              [S1] [S2] [S3]          │            │
│  │ 여러 커넥션이 서버 프로세스 공유      │            │
│  │ (M:N 매핑)                           │            │
│  └──────────────────────────────────────┘            │
│                                                      │
│  SGA (System Global Area) — 공유 메모리              │
│  - Buffer Cache                                     │
│  - Shared Pool (SQL 파싱 캐시)                      │
│  - Redo Log Buffer                                  │
│                                                      │
│  PGA (Process Global Area) — 프로세스별 전용 메모리   │
│  - Sort Area, Hash Area                             │
└──────────────────────────────────────────────────────┘
```

- Dedicated Mode: PostgreSQL처럼 **1커넥션 = 1프로세스**
- Shared Mode: 디스패처가 요청을 공유 서버 프로세스에 분배 (커넥션 수 >> 프로세스 수)
- 대규모 환경에서는 Shared Mode + Connection Multiplexing

#### 한눈에 비교

| | MySQL | PostgreSQL | Oracle |
|---|---|---|---|
| **모델** | 멀티스레드 | 멀티프로세스 | 멀티프로세스 (기본) |
| **커넥션 처리** | 1 conn = 1 thread | 1 conn = 1 process (fork) | 1 conn = 1 process (Dedicated) |
| **메모리 오버헤드/conn** | ~256KB~1MB | ~5~10MB | ~5~10MB (PGA) |
| **max 기본값** | 151 | 100 | sessions 파라미터 |
| **외부 풀러 필요성** | 선택 (ProxySQL) | **거의 필수** (PgBouncer) | 선택 (Shared Mode) |
| **컨텍스트 스위칭** | 스레드 (가벼움) | 프로세스 (무거움) | 프로세스 (무거움) |
| **장점** | 커넥션 생성 빠름 | 프로세스 격리 (안정성) | 유연한 모드 전환 |
| **단점** | 스레드 안전성 버그 위험 | fork 비용, 메모리 | 복잡한 설정 |

---

### 커넥션 풀 사이즈 공식

HikariCP 공식 위키에서 권장하는 공식:

```
Pool Size = (core_count * 2) + effective_spindle_count
```

- `core_count`: DB 서버의 CPU 코어 수
- `effective_spindle_count`: 디스크 스핀들 수 (SSD면 0~1)
- 예: 4코어 SSD 서버 → (4 * 2) + 1 = **9~10개**

**직관**: CPU 코어보다 커넥션이 많으면 컨텍스트 스위칭만 늘어남. 커넥션을 늘린다고 처리량이 늘지 않음.

```
┌─ 커넥션 수 vs 처리량 그래프 ─┐
│                               │
│  처리량                       │
│    ↑        ┌────────────     │
│    │       /                  │
│    │      /                   │
│    │     /   ← 여기가 최적    │
│    │    /                     │
│    │   /                      │
│    │  /                       │
│    └──────────────→ 커넥션 수  │
│         ↑                     │
│    이 이후로는 오히려 느려짐    │
└───────────────────────────────┘
```

---

### WebFlux/Netty 환경에서의 커넥션 관리 (R2DBC)

```
┌────────── WebFlux + R2DBC ──────────┐
│                                      │
│  Event Loop Thread (소수, 보통 N개)  │
│       │                              │
│       ▼                              │
│  R2DBC ConnectionFactory             │
│  (r2dbc-pool)                        │
│  ┌──────────────────────────┐        │
│  │ Connection 1 (논블로킹)  │        │
│  │ Connection 2 (논블로킹)  │        │
│  │ Connection 3 (논블로킹)  │        │
│  └──────────────────────────┘        │
│                                      │
│  ★ 커넥션을 잡고 있는 동안에도       │
│    스레드가 블로킹되지 않음          │
│  ★ 쿼리 날리고 → 콜백 등록 →        │
│    스레드는 다른 요청 처리           │
└──────────────────────────────────────┘

vs

┌────────── Spring MVC + HikariCP ────┐
│                                      │
│  Tomcat Thread (200개)               │
│       │                              │
│       ▼                              │
│  HikariCP                            │
│  ┌──────────────────────────┐        │
│  │ Connection 1 (블로킹)    │        │
│  │ Connection 2 (블로킹)    │        │
│  │ Connection 3 (블로킹)    │        │
│  └──────────────────────────┘        │
│                                      │
│  ★ 커넥션 잡고 쿼리 결과 올 때까지  │
│    스레드가 블로킹됨                 │
│  ★ 스레드 200개 중 10개만            │
│    커넥션 확보 → 190개 대기          │
└──────────────────────────────────────┘
```

## 헷갈렸던 포인트

### Q1. 커넥션 풀의 커넥션들끼리는 완전 독립적인가?

**애플리케이션 측에서는 완전 독립적**. 각 커넥션은 자기만의 TCP 소켓, 자기만의 DB 세션을 가짐. 서로의 트랜잭션 상태를 전혀 모름.

**하지만 DB 측에서는 공유 자원에서 만남**:
- 같은 Row를 수정하면 → InnoDB의 Row Lock에서 경합
- 같은 인덱스 페이지를 읽으면 → Buffer Pool에서 공유
- 커밋할 때 → Redo/WAL Log Buffer에서 순서 대기

그래서 "커넥션 간은 멀티스레딩"이라는 직관이 **거의 맞음**. 정확히는:
- MySQL: 멀티스레딩 맞음 (1 conn = 1 thread)
- PostgreSQL: 멀티프로세싱 (1 conn = 1 process) — 근데 공유 메모리로 통신하니까 효과는 비슷

### Q2. DB 자체가 멀티스레드인가?

**MySQL**: Yes. 단일 프로세스 안에서 멀티스레드로 동작.
**PostgreSQL**: No. 멀티프로세스. 커넥션마다 `fork()`로 새 프로세스 생성.
**Oracle**: 기본은 멀티프로세스(Dedicated), Shared Mode는 멀티스레드 + 멀티프로세스 혼합.

### Q3. PostgreSQL이 fork()를 쓰는데 왜 느리지 않은가?

- 실제로 커넥션 생성은 MySQL보다 느림 (fork 비용)
- 그래서 **PgBouncer** 같은 외부 커넥션 풀러를 거의 반드시 사용
- PgBouncer가 수천 개 클라이언트 커넥션을 수십 개 실제 PostgreSQL 커넥션으로 멀티플렉싱
- 프로세스 격리 덕분에 한 커넥션이 크래시해도 다른 커넥션에 영향 없음 (안정성 이점)

### Q4. HikariCP에서 커넥션을 못 잡으면 어떻게 되는가?

```
connectionTimeout (기본 30초) 내에 못 잡으면:
  → SQLTransientConnectionException 발생
    → @Transactional이면: CannotCreateTransactionException으로 래핑
    → @Transactional이 아니면: DataAccessResourceFailureException
```

### Q5. @Transactional 없이 2개 쿼리를 날리면 같은 커넥션을 쓸 수도 있는가?

**가능하다**. 첫 번째 쿼리가 반납한 커넥션을 두 번째 쿼리가 다시 잡을 수 있음. 특히 HikariCP의 ThreadLocal 최적화 때문에 같은 스레드에서는 같은 커넥션을 재사용할 확률이 높음. 하지만 **보장되지는 않음** — 다른 스레드가 그 사이에 가져갈 수 있음.

## 참고 자료

- [HikariCP GitHub — Down the Rabbit Hole](https://github.com/brettwooldridge/HikariCP/wiki/Down-the-Rabbit-Hole)
- [HikariCP — About Pool Sizing](https://github.com/brettwooldridge/HikariCP/wiki/About-Pool-Sizing)
- [PostgreSQL: Connection and Authentication](https://www.postgresql.org/docs/current/runtime-config-connection.html)
- [MySQL: Thread Pool](https://dev.mysql.com/doc/refman/8.0/en/thread-pool.html)
