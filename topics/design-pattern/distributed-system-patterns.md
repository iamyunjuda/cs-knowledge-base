---
title: "분산 시스템 핵심 패턴 — 동시성, 트랜잭션, 메시징, 데이터 정합성"
parent: Design Pattern / 설계 패턴
nav_order: 1
tags: [분산시스템, Saga, Outbox, 2PC, 멱등성, CAP, Circuit Breaker, Eventual Consistency]
description: "비관적/낙관적/분산 락, 2PC/Saga/Outbox, 멱등성, Circuit Breaker, CAP 정리, Eventual Consistency 등 분산 시스템 핵심 패턴을 총정리합니다."
---

# 분산 시스템 핵심 패턴 — 동시성, 트랜잭션, 메시징, 데이터 정합성

## 핵심 정리

### 1. 동시성 제어 (Concurrency Control)

#### 비관적 락 (Pessimistic Lock)

```
[정의]
"충돌이 발생할 것이다"라고 가정하고, 데이터에 접근하기 전에 먼저 잠근다.
다른 트랜잭션은 락이 해제될 때까지 대기한다.

[SQL]
SELECT * FROM user_points WHERE user_id = 1 FOR UPDATE;
-- 이 행을 잠금. 다른 트랜잭션은 이 SELECT도 기다려야 함.

[사용 시점]
- 충돌이 자주 발생하는 경우 (높은 동시성)
- 포인트 결제 시 잔액 차감 (SELECT FOR UPDATE)
- 객실 재고 차감

[장점]
- 데이터 정합성 확실히 보장
- 구현이 단순 (DB가 알아서 처리)

[단점]
- 대기 시간 발생 → 처리량(throughput) 감소
- 데드락 가능성 → 잠금 순서를 일관되게 유지해야 함
- DB 커넥션을 오래 점유
```

#### 낙관적 락 (Optimistic Lock)

```
[정의]
"충돌이 거의 없을 것이다"라고 가정하고, 잠그지 않고 작업한다.
커밋 시점에 충돌을 감지하여 실패 처리한다.

[구현]
테이블에 version 컬럼을 추가:

  UPDATE user_points SET balance = 200, version = 2
  WHERE id = 1 AND version = 1;

  -- version이 1이 아니면 다른 트랜잭션이 먼저 수정한 것
  -- → 0 rows updated → 재시도

[JPA]
@Version
var version: Long = 0
→ JPA가 자동으로 version 체크 + OptimisticLockException 발생

[사용 시점]
- 충돌이 드문 경우 (읽기가 많고 쓰기가 적은 경우)

[장점]
- 락 대기 없음 → 높은 처리량
- 데드락 불가

[단점]
- 충돌 시 재시도 필요 → 충돌이 잦으면 성능 저하
- 재시도 로직을 애플리케이션에서 구현해야 함
```

#### 분산 락 (Distributed Lock)

```
[정의]
여러 서버(인스턴스)에서 동시에 같은 자원에 접근할 때,
단일 DB 락으로는 부족하므로 외부 시스템(Redis, ZooKeeper)으로 락을 구현한다.

[Redis 분산 락 (Redisson)]

val lock = redissonClient.getLock("point:user:1")
if (lock.tryLock(5, 10, TimeUnit.SECONDS)) {
    try {
        // 임계 영역 (한 번에 하나의 인스턴스만 실행)
    } finally {
        lock.unlock()
    }
}

[사용 시점]
- 멀티 인스턴스 환경에서 동시성 제어

[RedLock 알고리즘]
- Redis 단일 노드 장애 시에도 락을 보장하기 위한 알고리즘
- N개의 Redis 노드 중 과반수(N/2 + 1)에서 락을 획득해야 성공
- Martin Kleppmann vs Salvatore Sanfilippo 논쟁으로 유명
```

#### EVM의 동시성 모델

```
[핵심]
EVM(Ethereum Virtual Machine)은 트랜잭션을 순차 실행한다.
→ 컨트랙트 내부에서는 동시성 문제가 존재하지 않는다.
→ 두 Tx가 같은 상태를 변경하려 해도, 하나씩 순서대로 처리된다.

[하지만]
- Reentrancy 공격: 외부 컨트랙트 호출 시 제어권이 넘어가면서
  원래 함수가 완료되기 전에 다시 호출될 수 있다.
  → ReentrancyGuard 또는 Checks-Effects-Interactions 패턴으로 방지

- 오프체인 동시성: DB와 블록체인 사이의 정합성은
  애플리케이션 레벨에서 해결해야 한다. EVM이 도와주지 않는다.
```

---

### 2. 분산 트랜잭션 (Distributed Transactions)

#### ACID vs BASE

```
ACID (전통 RDB):
  - Atomicity: 전부 성공 or 전부 실패
  - Consistency: 제약조건 항상 유지
  - Isolation: 트랜잭션 간 간섭 없음
  - Durability: 커밋 후 영구 보존

BASE (분산 시스템):
  - Basically Available: 항상 응답 가능
  - Soft State: 상태가 일시적으로 불일치할 수 있음
  - Eventually Consistent: 시간이 지나면 일관성이 맞춰짐

[실무 적용]
- DB 내부 작업: ACID (Spring @Transactional)
- DB + 블록체인: BASE (최종 일관성)
  → 민팅 요청 후 즉시는 DB와 온체인이 불일치하지만,
    이벤트 확인 후 일관성이 맞춰진다.
```

#### 2PC (Two-Phase Commit)

```
[정의]
분산 트랜잭션에서 모든 참여자가 "커밋 준비 완료"를 확인한 후,
한꺼번에 커밋하는 프로토콜.

Phase 1 (Prepare):
  코디네이터 → 참여자들: "커밋할 준비 됐나?"
  참여자들 → 코디네이터: "YES" or "NO"

Phase 2 (Commit/Abort):
  모두 YES → 코디네이터: "커밋 하라"
  하나라도 NO → 코디네이터: "롤백 하라"

[블록체인에서 2PC가 불가능한 이유]
- 블록체인 트랜잭션은 "제출 후 결과 대기" 모델이다.
- "준비만 하고 커밋은 나중에" 할 수 없다.
- Tx를 보내면 블록에 포함되는 순간 즉시 확정된다.
- 블록체인 노드가 "Prepare" 메시지에 응답하는 프로토콜이 없다.
→ 따라서 DB + 블록체인을 2PC로 묶는 것은 원천적으로 불가능하다.
```

#### Saga 패턴

```
[정의]
긴 트랜잭션을 여러 로컬 트랜잭션으로 분해하고,
각 단계가 실패하면 이전 단계를 "보상(Compensate)"하는 패턴.

[포인트 결제 Saga 예시]

정방향 (Happy Path):
  T1: DB에서 포인트 잔액 차감 (SELECT FOR UPDATE + reserve)
  T2: 블록체인에 소각 Tx 전송
  T3: Tx 확인 → DB에서 reservedBalance 제거

보상 (Compensation — T2 실패 시):
  C1: DB에서 포인트 잔액 복원 (cancelReservation)
  C2: 예약 상태를 PAYMENT_FAILED로 변경

[Choreography vs Orchestration]

Choreography (이벤트 기반):
  각 서비스가 이벤트를 발행하고, 다음 서비스가 구독하여 자율적으로 처리
  장점: 느슨한 결합, 서비스 추가 용이
  단점: 전체 흐름 파악 어려움, 디버깅 어려움

Orchestration (중앙 조율자):
  하나의 "오케스트레이터"가 각 단계를 순서대로 호출
  장점: 전체 흐름이 한 곳에서 보임
  단점: 오케스트레이터가 SPOF가 될 수 있음
```

#### Transactional Outbox 패턴

```
[정의]
DB 트랜잭션 안에서 "메시지/이벤트"를 outbox 테이블에 기록하고,
별도 프로세스가 이를 읽어 외부 시스템에 전달하는 패턴.

[왜 필요한가?]

단순 접근 (잘못된 방법):
  @Transactional
  fun process() {
      db.save(record)          // ← DB 트랜잭션
      messageBroker.send(msg)  // ← 외부 호출 (DB 트랜잭션 밖!)
  }
  → DB 커밋 성공 + 메시지 전송 실패 → 불일치
  → 메시지 전송 성공 + DB 롤백 → 불일치

Outbox 패턴:
  @Transactional
  fun process() {
      db.save(record)          // ← 같은 DB 트랜잭션
      outbox.save(event)       // ← 같은 DB 트랜잭션 (원자적)
  }
  // 별도 프로세스 (폴링 or CDC):
  // outbox에서 PENDING 상태 읽기 → 외부 시스템에 전달 → CONFIRMED로 변경

[변형: CDC (Change Data Capture)]
- outbox 테이블의 변경을 DB 로그(binlog, WAL)에서 직접 캡처
- Debezium 같은 도구 사용
- 폴링보다 실시간성이 높고 DB 부하가 적음
```

---

### 3. 메시징 시스템 (Messaging Systems)

#### 전달 보장 모델

```
At-Most-Once (최대 1회):
  메시지를 보내고 확인하지 않는다.
  유실 가능, 중복 없음.
  예: UDP, Fire-and-Forget

At-Least-Once (최소 1회):
  메시지 전달이 확인될 때까지 재전송한다.
  유실 없음, 중복 가능 → 수신 측에서 멱등성 처리 필요.

Exactly-Once (정확히 1회):
  유실도 중복도 없음.
  분산 환경에서 구현이 매우 어렵다.
  Kafka의 idempotent producer + transactional consumer가 근접.
  → 실제로는 "At-Least-Once + 멱등성"이 현실적인 대안.
```

#### 멱등성 (Idempotency)

```
[정의]
같은 연산을 여러 번 실행해도 결과가 동일한 성질.
f(f(x)) = f(x)

[왜 중요한가?]
At-Least-Once 전달에서는 같은 메시지가 여러 번 올 수 있다.
멱등성이 없으면 이중 처리가 발생한다.

[구현 방법]

1. 고유 키로 중복 체크:
   - mintRequestId로 이중 적립 방지
   - 컨트랙트: processedMintRequests[mintRequestId] mapping
   - DB: UNIQUE(mint_request_id) 제약조건

2. 상태 기반 멱등성:
   - 이미 CONFIRMED 상태면 같은 요청 무시

3. UPSERT (INSERT ON CONFLICT):
   INSERT INTO ... ON CONFLICT DO NOTHING
```

#### 메시지 큐 비교

```
                  Redis Pub/Sub    Redis Streams    Kafka
───────────────────────────────────────────────────────────
영속성              ✗               ✓               ✓
Consumer Group     ✗               ✓               ✓
재처리 가능         ✗               ✓               ✓
순서 보장          ✗               ✓ (스트림 내)    ✓ (파티션 내)
처리량             높음             높음             매우 높음
운영 복잡도        낮음             중간             높음
장애 시            메시지 유실      Redis 의존       내구성 높음
───────────────────────────────────────────────────────────
```

---

### 4. 블록체인 핵심 개념

#### Block Finality (블록 최종성)

```
[정의]
트랜잭션이 포함된 블록이 "절대 변경되지 않을 것"이라는 보장.

[이더리움 PoS]
- 1 confirmation: 블록이 생성됨 (~12초). Reorg 가능.
- 6 confirmations: 대부분의 거래소 기준 (~72초).
- 12 confirmations: 높은 안정성 (~2.4분).
- 32 confirmations: 1 epoch, 이론적 최종성 (~6.4분).
- 2 epochs (64 confirmations): 완전 최종성 (~12.8분).

[Reorg (블록 재구성)]
- 같은 높이에서 두 개의 블록이 경쟁할 때, 더 긴 체인이 승리
- 패배한 블록의 트랜잭션은 무효화 → "확인된 줄 알았는데 사라짐"
- PoS 이후 매우 드물지만 0은 아님
```

#### Nonce

```
[정의]
각 계정이 보내는 트랜잭션의 순번. 0부터 시작하여 1씩 증가.

[규칙]
- 같은 nonce의 Tx가 2개면 → 하나만 처리 (가스 가격 높은 것 우선)
- nonce에 빈 숫자가 있으면 → 그 이후 Tx 전부 대기 (Nonce Gap)

[문제 상황]

Nonce Gap: nonce 5가 실패 → nonce 6, 7, 8 전부 멈춤
  해결: 빈 nonce로 빈 Tx (0 ETH 자기 전송) 보내기

Nonce Collision: 동시에 여러 Tx에 같은 nonce 사용
  해결: NonceManager에서 mutex로 원자적 할당

NonceManager 클래스:
  - getNextNonce(): mutex로 원자적 할당
  - syncWithChain(): 서버 재시작 시 온체인 nonce와 동기화
  - releaseNonce(): Tx 실패 시 nonce 반환
```

#### ERC-20 토큰 표준

```
[정의]
이더리움에서 "토큰"을 만드는 표준 인터페이스.
이 표준을 따르면 어떤 지갑이든 토큰을 인식하고 표시할 수 있다.

[필수 함수]
totalSupply()               → 전체 발행량
balanceOf(account)           → 특정 주소의 잔액
transfer(to, amount)         → 토큰 전송
approve(spender, amount)     → 위임 승인
transferFrom(from, to, amt)  → 위임 전송
allowance(owner, spender)    → 위임 잔액 조회

[필수 이벤트]
Transfer(from, to, value)    → 전송 시 발행
Approval(owner, spender, val) → 승인 시 발행
```

#### HD Wallet (Hierarchical Deterministic)

```
[정의]
하나의 마스터 시드(니모닉)에서 무한한 자식 키를 수학적으로 파생하는 지갑 구조.

[BIP-44 표준 경로]
m / purpose' / coin_type' / account' / change / index
m / 44'      / 60'        / 0'       / 0      / {userId}

  44' = BIP-44 목적
  60' = Ethereum (코인 번호)
  0'  = 첫 번째 계정
  0   = 외부 체인 (수신용)
  idx = 사용자별 인덱스

[특징]
- 같은 시드 + 같은 경로 → 항상 같은 키/주소 (결정론적)
- 마스터 시드만 백업하면 모든 지갑 복구 가능
- 공개 키만으로도 자식 공개 키 파생 가능 (xpub)

[보안]
- 마스터 시드 유출 = 모든 지갑 탈취
- 프라이빗 키는 메모리에서만 다루고, 저장 시 반드시 암호화
- HSM(Hardware Security Module) 사용 권장 (프로덕션)
```

#### Gas (가스)

```
[정의]
EVM에서 연산을 실행하는 비용 단위.
스토리지 읽기/쓰기, 산술 연산, 이벤트 발행 등 모든 연산에 가스가 필요.

[가스비 = gasUsed x gasPrice]
- gasUsed: 실제 사용된 가스 (컨트랙트 코드 복잡도에 비례)
- gasPrice: 단위 가스당 지불하는 ETH (네트워크 혼잡도에 따라 변동)

[최적화]
- 스토리지 쓰기가 가장 비쌈 (SSTORE: 20,000 gas)
- 이벤트 로그는 스토리지보다 저렴 (LOG: ~375 gas + data cost)
- 배치 처리로 base cost 절약 (Tx 하나의 기본 비용: 21,000 gas)
- batchMint로 100건을 1 Tx로 묶어 가스비 절약
```

---

### 5. 설계 패턴 (Design Patterns)

#### Circuit Breaker 패턴

```
[정의]
외부 시스템 장애 시 빠르게 실패하여 연쇄 장애를 방지하는 패턴.
전기 차단기(Circuit Breaker)에서 이름을 따왔다.

[상태 전이]

CLOSED → (실패율 > 임계값) → OPEN → (대기 시간 경과) → HALF-OPEN
                                                        │
                                ← (시험 요청 성공) ──────┘
                                → (시험 요청 실패) → OPEN

CLOSED:   정상. 모든 요청을 외부 시스템으로 전달.
OPEN:     차단. 요청을 즉시 실패 처리 (외부 시스템 호출 안 함).
HALF-OPEN: 일부 요청만 시험적으로 전달. 성공하면 CLOSED로 복귀.
```

#### Checks-Effects-Interactions (CEI) 패턴

```
[정의]
Solidity에서 Reentrancy 공격을 방지하는 코딩 패턴.
함수를 3단계로 구분한다.

[순서]
1. Checks: require()로 조건 검증
2. Effects: 상태 변수 변경
3. Interactions: 외부 컨트랙트 호출 또는 ETH 전송

[잘못된 예]
function withdraw(uint amount) {
    // 1. Check
    require(balances[msg.sender] >= amount);
    // 3. Interaction (상태 변경 전에 외부 호출!)
    (bool ok, ) = msg.sender.call{value: amount}("");
    // 2. Effect (너무 늦음! 공격자가 재진입 가능)
    balances[msg.sender] -= amount;
}

[올바른 예]
function withdraw(uint amount) {
    // 1. Check
    require(balances[msg.sender] >= amount);
    // 2. Effect (먼저 상태 변경)
    balances[msg.sender] -= amount;
    // 3. Interaction (마지막에 외부 호출)
    (bool ok, ) = msg.sender.call{value: amount}("");
    require(ok);
}
```

#### Graceful Degradation (우아한 성능 저하)

```
[정의]
시스템 일부가 장애가 나도 전체 서비스는 계속 동작하되,
일부 기능이 제한되는 방식으로 운영하는 전략.

[핵심 원칙]
"Redis(또는 블록체인 노드)는 성능 최적화 도구이지, 필수 의존성이 아니다."

[예시]
- Redis 장애 시: 캐시 미스 → DB 직접 조회 (느리지만 동작)
- 블록체인 RPC 장애 시: 요청을 Outbox에 쌓아두고 복구 후 처리
- 이벤트 리스너 다운 시: Gap Recovery로 놓친 이벤트 복구
```

---

### 6. 데이터 정합성 (Data Consistency)

#### Reconciliation (대사)

```
[정의]
두 개 이상의 데이터 소스의 상태를 비교하여 불일치를 발견하고 보정하는 프로세스.
금융 시스템에서는 "대사(對査)"라고 부른다.

[왜 필요한가?]
비동기 시스템에서는 이벤트 유실/중복/지연이 발생할 수 있다.
아무리 정교한 이벤트 처리를 해도 100% 정합성은 보장할 수 없다.
→ 주기적 대사로 "실제로 맞는지" 확인하는 것이 최후의 안전망이다.

[예시: BalanceReconciler]
  DB 잔액 (available_balance + reserved_balance)
  vs
  온체인 잔액 (contract.balanceOf(walletAddress))

  불일치 시:
  - DB > 온체인: 민팅 누락 → 재민팅 또는 알림
  - DB < 온체인: DB 기록 누락 → 이벤트 재처리 또는 DB 보정
```

#### Source of Truth (진실의 원천)

```
[정의]
데이터가 불일치할 때 "어느 쪽이 진짜인가?"를 결정하는 기준.

[블록체인 시스템에서]
블록체인이 Source of Truth이다.

이유:
  - 블록체인은 불변(immutable)이고 위변조가 불가능
  - DB는 서버 버그, 장애 등으로 상태가 어긋날 수 있음
  - 온체인에 기록된 트랜잭션은 전 세계 노드가 검증한 결과

단, 블록체인을 "언제 확인하느냐"가 중요:
  - 1 confirmation: 아직 Reorg 가능 → Source of Truth로 부족
  - 12+ confirmations: 실질적 최종성 → 신뢰 가능
```

#### Eventual Consistency (최종 일관성)

```
[정의]
분산 시스템에서 모든 복제본이 즉시 일치하지 않지만,
충분한 시간이 지나면 결국 일관성이 맞춰지는 모델.

[CAP 정리와의 관계]
분산 시스템은 다음 3가지를 동시에 만족할 수 없다:

  C (Consistency): 모든 노드가 같은 데이터를 가짐
  A (Availability): 모든 요청에 응답
  P (Partition Tolerance): 네트워크 분할에도 동작

네트워크 분할(P)은 필연적이므로, C vs A 중 하나를 선택해야 한다.
  - CP: 일관성 우선 (은행 계좌 이체)
  - AP: 가용성 우선 (SNS 좋아요 수)

[실무 적용]
포인트 적립은 AP + Eventual Consistency:
  1. 예약 완료 → DB에 PENDING으로 기록 (즉시 응답)
  2. 블록체인 Tx 전송 → 비동기 처리
  3. 12 confirmations 후 → DB를 CONFIRMED로 변경
  → 중간에는 DB와 온체인이 불일치하지만, 결국 맞춰진다.
```

---

### 7. Node.js 동시성 모델

```
[싱글 스레드 + 이벤트 루프]
Node.js는 싱글 스레드이지만, 비동기 I/O로 동시성을 구현한다.

  setTimeout(fn, 0)
  fetch(url)
  fs.readFile(path)

  → 이런 비동기 작업은 이벤트 루프에 등록되고,
    완료되면 콜백이 실행된다.

[논리적 동시성 (Interleaving)]
Thread가 하나이므로 "진짜 동시 실행"은 없지만,
async/await 사이에서 다른 작업이 끼어들 수 있다.

  async function process() {
    const nonce = currentNonce;  // 5를 읽음
    await sendTx(nonce);          // ← 여기서 양보 (yield)
    // ← 이 사이에 다른 async 함수가 nonce를 5로 또 읽을 수 있음!
    currentNonce++;
  }

[해결: Mutex 패턴]
Promise 체이닝으로 직렬화:

  let mutex = Promise.resolve();

  async function getNextNonce() {
    return new Promise(resolve => {
      mutex = mutex.then(() => {
        nonce++;
        resolve(nonce);
      });
    });
  }

  → 동시에 호출해도 순서대로 실행된다.
```

---

### 8. 보안 — Reentrancy (재진입 공격)

```
[정의]
외부 컨트랙트를 호출할 때, 호출된 컨트랙트가 원래 함수를
"상태 변경 전에" 다시 호출하여 자금을 반복 인출하는 공격.

2016년 DAO 해킹 사건: 이더리움 360만 ETH (~$50M) 탈취.
→ 이더리움 하드포크의 원인이 된 역사적 사건.

[방어]
1. ReentrancyGuard (OpenZeppelin)
   - 함수 진입 시 플래그를 세우고, 완료 후 해제
   - 재진입 시 플래그가 이미 세워져 있으므로 revert

2. CEI 패턴 (위 5. Checks-Effects-Interactions 참고)

3. Pull 패턴
   - "보내기" 대신 "가져가기"로 설계
   - withdraw() 함수에서 사용자가 직접 인출
```

---

## 헷갈렸던 포인트

### Q1: 비관적 락 vs 낙관적 락 — 언제 뭘 쓰나?

```
[선택 기준]

  충돌 빈도가 높은가?
  ├── YES → 비관적 락 (대기하더라도 확실히 처리)
  │         예: 재고 차감, 좌석 예약, 포인트 차감
  └── NO  → 낙관적 락 (대기 없이 빠르게, 가끔 재시도)
            예: 프로필 수정, 설정 변경, 리뷰 작성

  멀티 인스턴스인가?
  ├── YES → 분산 락 (Redis/ZooKeeper)
  └── NO  → DB 락으로 충분
```

### Q2: Outbox 패턴 vs 이벤트 직접 발행 — 왜 번거로운 Outbox를 쓰나?

```
[직접 발행의 문제]

  @Transactional
  fun process() {
      db.save(order)        // 1. DB 저장
      kafka.send(event)     // 2. Kafka 발행
  }

  시나리오 1: DB 성공, Kafka 실패 → 주문은 있는데 이벤트 없음
  시나리오 2: Kafka 성공, DB 롤백 → 이벤트는 있는데 주문 없음

  둘 다 데이터 불일치.

[Outbox가 해결하는 것]
  DB와 이벤트를 같은 트랜잭션에 넣어 원자성 보장.
  "이벤트 발행"을 "DB 쓰기"로 변환하는 것이 핵심.
```

---

## 키워드 인덱스

| 키워드 | 섹션 | 한줄 요약 |
|--------|------|----------|
| Pessimistic Lock | 1 | 먼저 잠그고 작업 (SELECT FOR UPDATE) |
| Optimistic Lock | 1 | 작업 후 충돌 감지 (@Version) |
| Distributed Lock | 1 | 멀티 인스턴스 환경에서의 락 (Redis/Redisson) |
| ACID | 2 | 전통 DB 트랜잭션의 4가지 특성 |
| BASE | 2 | 분산 시스템의 최종 일관성 모델 |
| 2PC | 2 | 분산 커밋 프로토콜 (블록체인에서 불가) |
| Saga | 2 | 보상 트랜잭션으로 분산 트랜잭션 해결 |
| Outbox Pattern | 2 | DB 트랜잭션 + 비동기 메시징 정합성 보장 |
| At-Least-Once | 3 | 최소 1회 전달 보장 (중복 가능) |
| Idempotency | 3 | 같은 연산 여러 번 = 같은 결과 |
| Block Finality | 4 | 블록이 변경되지 않을 것이라는 보장 |
| Reorg | 4 | 블록 재구성 (확인된 블록이 사라짐) |
| Nonce | 4 | 트랜잭션 순번 (gap 발생 시 멈춤) |
| ERC-20 | 4 | 이더리움 토큰 표준 인터페이스 |
| HD Wallet | 4 | 시드에서 무한 키 파생하는 결정론적 지갑 |
| Gas | 4 | EVM 연산 비용 단위 |
| Circuit Breaker | 5 | 외부 시스템 장애 시 빠른 실패 |
| CEI Pattern | 5 | Checks-Effects-Interactions (Reentrancy 방지) |
| Graceful Degradation | 5 | 부분 장애 시 제한된 기능으로 계속 운영 |
| Reconciliation | 6 | 두 데이터 소스 비교/보정 (대사) |
| Source of Truth | 6 | 데이터 불일치 시 기준이 되는 원천 |
| Eventual Consistency | 6 | 시간이 지나면 일관성이 맞춰지는 모델 |
| CAP Theorem | 6 | C, A, P 중 2개만 동시 만족 가능 |
| Event Loop | 7 | Node.js 비동기 처리 모델 |
| Reentrancy | 8 | 스마트 컨트랙트 재진입 공격 |

## 참고 자료

| 자료 | 설명 |
|------|------|
| [Martin Kleppmann — Designing Data-Intensive Applications](https://dataintensive.net/) | 분산 시스템 설계의 바이블 |
| [Chris Richardson — Microservices Patterns](https://microservices.io/patterns/) | Saga, Outbox 등 마이크로서비스 패턴 |
| [OpenZeppelin — ReentrancyGuard](https://docs.openzeppelin.com/contracts/5.x/api/utils#ReentrancyGuard) | Solidity 재진입 방어 표준 구현 |
| [Ethereum — ERC-20 표준](https://eips.ethereum.org/EIPS/eip-20) | 토큰 표준 공식 스펙 |
| [Redisson 분산 락](https://github.com/redisson/redisson/wiki/8.-distributed-locks-and-synchronizers) | Redis 분산 락 구현 레퍼런스 |
