---
title: "블록체인 Tx 엣지 케이스 — 패턴을 넘어 실전에서 터지는 것들"
parent: Blockchain / Web3
nav_order: 2
---

# 블록체인 트랜잭션 엣지 케이스 — 패턴을 넘어 실전에서 터지는 것들

## 핵심 정리

### "패턴을 아는 것"과 "실제로 돌아가게 만드는 것"의 차이

```
[공식 패턴이 알려주는 것]
  "Tx 실패하면 보상 트랜잭션을 실행하세요"

[실제로 개발자가 풀어야 하는 것]
  - Tx가 실패인지 아직 pending인지 모르는 상황은?
  - 확정된 줄 알았던 Tx가 Reorg로 사라지면?
  - Nonce 3번이 실패해서 4,5,6번이 전부 막혔으면?
  - RPC 노드가 다운되면?
  - 가스비가 갑자기 10배 뛰면?

비유:
  요리 레시피 = 공식 패턴 (Outbox, Saga, CQRS...)
  셰프 = 개발자

  "된장찌개 끓이기"는 누구나 알지만
  "100인분을 동시에, 맛 일정하게, 재료 떨어지면 대체하고,
   주방 불나면 대응하면서" 만드는 건 다른 문제
```

---

### 1. Tx 상태의 불확실성 — 실패인가, 아직 pending인가?

#### 문제: 블록체인 Tx의 3가지 상태

```
[일반 DB 트랜잭션]
  성공 or 실패. 2가지. 즉시 알 수 있음.

[블록체인 트랜잭션]
  1. 성공 (Confirmed)  — 블록에 포함되고 receipt 받음
  2. 실패 (Reverted)   — 블록에 포함됐지만 실행 실패 (가스만 날림)
  3. 불명 (Unknown)    — 어디에도 없음. 성공할 수도 실패할 수도 있음

  세 번째 상태가 문제다.

[Unknown 상태가 발생하는 경우들]

  1. Mempool에서 대기 중
     → 가스비가 너무 낮아서 채굴자/검증자가 안 가져감
     → 네트워크 혼잡 시 몇 시간~며칠 대기 가능

  2. Mempool에서 드랍됨
     → 노드가 재시작하면 Mempool이 날아감
     → Tx가 전파되지 않았을 수도 있음
     → 전송한 쪽은 "보냈는데 결과를 모름"

  3. RPC 노드와 연결 끊김
     → Tx를 보냈는데 응답을 못 받음
     → 실제로 전파됐는지조차 불명

  4. 노드 간 상태 불일치
     → 노드 A에서는 pending, 노드 B에서는 존재하지 않음
     → 어떤 노드를 믿을 것인가?
```

#### 실전 대응: Tx 상태 추적 시스템

```
[Tx Lifecycle 관리]

  ┌─────────┐     ┌──────────┐     ┌──────────────┐
  │ CREATED │ →   │ SUBMITTED│ →   │ PENDING      │
  │ DB 기록  │     │ 노드 전송 │     │ Mempool 대기 │
  └─────────┘     └──────────┘     └──────┬───────┘
                                          │
                         ┌────────────────┼──────────────┐
                         ▼                ▼              ▼
                  ┌──────────┐    ┌────────────┐  ┌──────────┐
                  │ CONFIRMED│    │ REVERTED   │  │ LOST     │
                  │ 블록 포함  │    │ 실행 실패   │  │ 소실     │
                  │ receipt OK│    │ receipt ERR│  │ 결과 불명 │
                  └──────────┘    └────────────┘  └──────────┘

  핵심 규칙:
  1. Tx를 보내기 전에 반드시 DB에 CREATED로 기록
  2. 노드에 전송 성공하면 txHash를 DB에 업데이트 (SUBMITTED)
  3. 주기적으로 txHash로 receipt 조회 (PENDING → CONFIRMED/REVERTED)
  4. 일정 시간(예: 30분) 내 receipt 없으면 LOST로 마킹
```

#### LOST 상태 복구 전략

```
[LOST Tx 복구]

  Tx가 LOST 상태가 되면:

  1. 같은 nonce로 재전송 (Replace-by-Fee)
     → 가스비를 높여서 같은 nonce의 새 Tx를 보냄
     → 원래 Tx가 이미 처리됐으면? 새 Tx가 nonce 충돌로 거절됨 → 안전
     → 원래 Tx가 드랍됐으면? 새 Tx가 처리됨

  2. Nonce 확인 후 판단
     → 온체인 nonce = 기대 nonce → Tx가 이미 처리됨 (어딘가에)
     → 온체인 nonce < 기대 nonce → Tx가 아직 pending 또는 드랍

  코드 패턴:

  async function recoverLostTx(savedTx) {
    const onchainNonce = await provider.getTransactionCount(wallet);

    if (onchainNonce > savedTx.nonce) {
      // 이미 처리됨 — receipt를 찾아서 상태 업데이트
      const receipt = await findReceiptByNonce(savedTx.nonce);
      if (receipt) {
        updateTxStatus(savedTx.id, receipt.status ? 'CONFIRMED' : 'REVERTED');
      }
    } else {
      // 아직 미처리 — 가스비 높여서 재전송
      const newTx = await resendWithHigherGas(savedTx);
      updateTxHash(savedTx.id, newTx.hash);
    }
  }
```

---

### 2. Reorg — 확정된 줄 알았던 Tx가 사라지는 공포

#### Reorg란?

```
[정상 상황]
  Block 100 → Block 101 → Block 102 → Block 103
  Tx가 Block 101에 포함됨 ✓

[Reorg 발생]
  Block 100 → Block 101  → Block 102  → Block 103
                  ↕ (경쟁)
              Block 101' → Block 102' → Block 103' → Block 104'

  더 긴 체인(')이 승리 → Block 101~103이 무효화
  → Block 101에 있던 내 Tx가 사라짐!
  → Block 101'에 다시 포함될 수도 있고, 안 될 수도 있음

[PoS 이후 Reorg 빈도]
  - 1블록 Reorg: 드물지만 발생 (몇 달에 1번)
  - 2블록 Reorg: 극히 드묾
  - 7블록+ Reorg: 사실상 불가능 (Finality 보장)
  - 32블록 (1 epoch): 이론적 최종성
  - 64블록 (2 epoch): 완전 최종성
```

#### 실전 문제: "적립 완료" 알림을 보냈는데 Reorg

```
[시나리오]

  T=0s    유저가 호텔 예약 → 포인트 적립 요청
  T=12s   Block N에 민팅 Tx 포함됨 (1 confirmation)
  T=24s   2 confirmations → 서버: "확인됨"으로 처리
  T=25s   유저에게 "500 포인트 적립 완료!" 푸시 알림 전송
  T=30s   Reorg 발생! Block N이 무효화됨
  T=31s   민팅 Tx가 사라짐

  → 유저는 "적립 완료" 알림을 받았는데 포인트가 없다
  → CS 폭주

[교훈]
  Confirmation 수가 적을 때 유저에게 확정 통보하면 안 된다.
```

#### 실전 대응: Confirmation 단계별 처리

```
[Confirmation 전략]

  1 confirmation:
    DB: status = TENTATIVE (잠정)
    유저: "처리 중..." 표시
    → 아직 확정 아님

  6 confirmations:
    DB: status = SOFT_CONFIRMED
    유저: "포인트가 곧 반영됩니다"
    → 높은 확률로 확정이지만 보장은 안 됨

  12 confirmations:
    DB: status = CONFIRMED
    유저: "500 포인트 적립 완료!"
    → 실질적 최종성, 알림 전송 OK

  구현:

  // 이벤트 리스너에서 블록 수신 시
  async function onNewBlock(blockNumber) {
    const pendingTxs = await db.find({ status: 'TENTATIVE' });

    for (const tx of pendingTxs) {
      const receipt = await provider.getTransactionReceipt(tx.hash);

      if (!receipt) {
        // Reorg로 Tx가 사라짐!
        tx.status = 'REORGED';
        await requeueForResubmission(tx);
        continue;
      }

      const confirmations = blockNumber - receipt.blockNumber;

      if (confirmations >= 12) {
        tx.status = 'CONFIRMED';
        await notifyUser(tx.userId, "포인트 적립 완료!");
      } else if (confirmations >= 6) {
        tx.status = 'SOFT_CONFIRMED';
      }
      // 1~5: TENTATIVE 유지
    }
  }
```

#### Reorg 감지 시스템

```
[Reorg 감지 방법]

  방법 1: 블록 해시 체인 검증
    매 블록 수신 시 parentHash가 이전 저장 블록의 hash와 일치하는지 확인
    불일치 → Reorg 발생

    let lastBlockHash = null;

    async function onNewBlock(block) {
      if (lastBlockHash && block.parentHash !== lastBlockHash) {
        // Reorg 감지!
        const depth = await calculateReorgDepth(block);
        await handleReorg(depth);
      }
      lastBlockHash = block.hash;
    }

  방법 2: 이벤트 재검증
    Confirmed 처리한 이벤트의 블록 번호/해시를 주기적으로 재확인
    해당 블록이 여전히 존재하는지 검증

[Reorg 대응]

  1. 영향받는 Tx 식별
     → Reorg 깊이 내의 블록에 포함된 모든 Tx 조회
  2. DB 상태 롤백
     → CONFIRMED → REORGED로 변경
     → 포인트 잔액 복원 (이미 반영했다면)
  3. Tx 재제출 또는 대기
     → 대부분의 Tx는 새 블록에 다시 포함됨
     → 일정 시간 후에도 미포함 → 재전송
```

---

### 3. Nonce 관리 — 순서가 꼬이면 모든 게 멈춘다

#### Nonce의 기본 규칙

```
[Nonce = 계정별 트랜잭션 순번]

  계정 0xABC의 Tx 이력:
  nonce 0: 전송 완료 ✓
  nonce 1: 전송 완료 ✓
  nonce 2: 전송 완료 ✓
  nonce 3: ← 다음 Tx는 반드시 nonce 3이어야 함

  핵심 규칙:
  - nonce는 0부터 시작, 빈 번호 없이 순서대로
  - nonce N이 처리되기 전에는 nonce N+1은 절대 처리 안 됨
  - 같은 nonce의 Tx가 2개 오면 가스비 높은 것만 처리 (나머지 드랍)
```

#### Nonce Gap 문제

```
[Nonce Gap = 중간 번호가 비어서 후속 Tx가 전부 막힘]

  nonce 3: 전송 → 실패 (가스 부족)
  nonce 4: 전송 → Mempool에서 대기 (nonce 3 기다리는 중)
  nonce 5: 전송 → Mempool에서 대기
  nonce 6: 전송 → Mempool에서 대기

  → nonce 3이 해결되지 않으면 4,5,6 전부 영원히 대기

[발생 원인]
  1. Tx 전송 실패 후 nonce를 증가시킴 (버그)
  2. Tx가 Mempool에서 드랍됨 (낮은 가스비)
  3. 서버 재시작 시 로컬 nonce 카운터와 온체인 nonce 불일치
  4. 멀티 인스턴스에서 같은 지갑으로 동시 전송 (Nonce 충돌)

[해결 방법]

  방법 1: 빈 nonce 채우기
    빈 nonce로 0 ETH 자기 전송 Tx를 보냄
    → 가스비만 소모되지만, 후속 Tx 막힘 해소

    async function fillNonceGap(walletAddress, gapNonce) {
      const tx = {
        to: walletAddress,  // 자기 자신에게
        value: 0,           // 0 ETH
        nonce: gapNonce,
        gasPrice: currentGasPrice * 1.5  // 빨리 처리되도록
      };
      await wallet.sendTransaction(tx);
    }

  방법 2: 모든 pending Tx 취소 후 재전송
    → 같은 nonce로 가스비 높인 Tx를 보내 기존 Tx를 대체
    → 전부 대체 후 깨끗한 상태에서 재시작
```

#### NonceManager 구현 패턴

```
[싱글 인스턴스 — Mutex 패턴]

  class NonceManager {
    private nextNonce: number;
    private mutex = new Mutex();

    async getNextNonce(): Promise<number> {
      const release = await this.mutex.acquire();
      try {
        const nonce = this.nextNonce;
        this.nextNonce++;
        return nonce;
      } finally {
        release();
      }
    }

    async syncWithChain() {
      const release = await this.mutex.acquire();
      try {
        this.nextNonce = await provider.getTransactionCount(wallet);
      } finally {
        release();
      }
    }

    // Tx 실패 시 nonce 반환 (Gap 방지)
    async releaseNonce(nonce: number) {
      const release = await this.mutex.acquire();
      try {
        if (nonce < this.nextNonce) {
          this.nextNonce = nonce;
        }
      } finally {
        release();
      }
    }
  }

[멀티 인스턴스 — Redis 기반 분산 Nonce 관리]

  // Redis에 nonce를 중앙 관리
  async function getNextNonce(walletAddress) {
    const lockKey = `nonce:lock:${walletAddress}`;
    const nonceKey = `nonce:${walletAddress}`;

    const lock = await redisLock(lockKey, 5000);
    try {
      let nonce = await redis.get(nonceKey);
      if (nonce === null) {
        // Redis에 없으면 온체인에서 동기화
        nonce = await provider.getTransactionCount(walletAddress);
      }
      await redis.set(nonceKey, nonce + 1);
      return parseInt(nonce);
    } finally {
      await lock.release();
    }
  }

  문제점:
  - Redis 장애 시 nonce 관리 불가
  - 온체인과 Redis nonce 불일치 가능
  → 주기적 Reconciliation(대사)으로 보정
```

---

### 4. RPC 노드 장애 — 블록체인의 "눈"이 멀면

#### RPC 노드란?

```
[RPC 노드 = 블록체인과 소통하는 창구]

  서버 → JSON-RPC → [RPC 노드] → [이더리움 네트워크]

  모든 블록체인 작업이 RPC를 통함:
  - 잔액 조회 (eth_getBalance)
  - Tx 전송 (eth_sendRawTransaction)
  - 이벤트 조회 (eth_getLogs)
  - 블록 조회 (eth_getBlockByNumber)
  - Receipt 조회 (eth_getTransactionReceipt)

  RPC 다운 = 블록체인과 단절 = 모든 블록체인 기능 중단
```

#### RPC 장애 유형

```
[유형 1: 완전 다운]
  → 연결 자체가 안 됨
  → 즉시 감지 가능
  → 폴백 노드로 전환

[유형 2: 느린 응답]
  → Redis Slow와 같은 문제
  → 응답 대기 중 스레드/코루틴 블로킹
  → 타임아웃 설정 필수 (3~5초)

[유형 3: 잘못된 데이터]
  → 노드 동기화가 뒤처져서 옛날 블록 데이터 반환
  → "최신 블록: 19,000,000"인데 노드는 "18,999,500" 반환
  → 이벤트 누락, 잔액 불일치 발생
  → 가장 위험: 에러 없이 잘못된 데이터를 받음

[유형 4: Rate Limiting]
  → Infura, Alchemy 등 SaaS 노드의 요청 한도 초과
  → 429 Too Many Requests
  → 갑자기 트래픽 증가 시 예고 없이 발생
```

#### RPC 폴백 전략

```
[멀티 RPC 구성]

  ┌──────────────────────────────────┐
  │        RPC Load Balancer          │
  │   (라운드로빈 + 헬스체크)          │
  └────┬──────────┬──────────┬───────┘
       │          │          │
       ▼          ▼          ▼
  [Alchemy]  [Infura]   [자체 노드]
   Primary   Secondary   Fallback

  헬스체크:
  - 주기적으로 eth_blockNumber 호출
  - 최신 블록 번호가 다른 노드보다 10+ 뒤처지면 → 제외
  - 응답 시간 3초 초과 → 제외

  전환 전략:
  1. Primary 실패 → Secondary로 자동 전환
  2. Secondary도 실패 → 자체 노드 (최후 수단)
  3. 전체 실패 → Tx 큐에 쌓아두고, 복구 후 일괄 처리

[주의: 노드 간 블록 높이 차이]

  Alchemy:  Block 19,000,100  (최신)
  Infura:   Block 19,000,098  (2블록 뒤)
  자체노드:  Block 19,000,050  (50블록 뒤!)

  폴백 전환 시:
  → "방금 Alchemy에서 확인한 이벤트가 Infura에는 아직 없다"
  → 이벤트 중복 처리 or 누락 발생 가능
  → 해결: 이벤트 처리에 멱등성 + 마지막 처리 블록 번호 기록
```

---

### 5. 가스비 급등 — 비용이 10배 뛰는 순간

#### EIP-1559 가스 구조

```
[가스비 = baseFee + priorityFee (tip)]

  baseFee:
    - 네트워크가 자동 결정 (블록 사용률에 따라)
    - 블록이 50% 이상 차면 baseFee 증가
    - 블록이 50% 미만이면 baseFee 감소
    - 최대 변동: 블록당 12.5%

  priorityFee (tip):
    - 사용자가 설정
    - 검증자에게 주는 팁
    - 높을수록 빨리 처리됨

[가스비 급등 시나리오]

  평상시: baseFee 10 Gwei  → Tx 비용 ~$0.50
  NFT 민팅 이벤트: baseFee 300 Gwei → Tx 비용 ~$15.00
  극한 혼잡: baseFee 1000+ Gwei → Tx 비용 ~$50.00

  → 12.5%씩 증가해도 20블록(4분)이면 10배 가능
  → 예산 없이 보내면 Tx가 영원히 pending
  → 예산 넘겨서 보내면 불필요한 비용 지출
```

#### 동적 가스비 전략

```
[가스비 계산 전략]

  async function calculateGasParams() {
    const feeData = await provider.getFeeData();
    const block = await provider.getBlock('latest');

    return {
      // maxFeePerGas: 이 이상은 절대 안 냄
      maxFeePerGas: feeData.maxFeePerGas * 2n,  // 현재의 2배까지 허용

      // maxPriorityFeePerGas: 검증자 팁
      maxPriorityFeePerGas: feeData.maxPriorityFeePerGas,

      // gasLimit: 실행에 필요한 가스량 (estimateGas로 계산)
      gasLimit: estimatedGas * 120n / 100n  // 20% 여유
    };
  }

[가스비 한도 초과 시]

  비즈니스별 다른 전략:

  호텔 포인트 적립 (급하지 않음):
    한도: $5
    초과 시: 큐에 쌓아두고 가스비 떨어지면 전송
    → "적립이 지연되고 있습니다" 알림

  결제/출금 (급함):
    한도: $20
    초과 시: 관리자 승인 후 전송
    → 비용 대비 금액 비율 검증

  긴급 보안 (최우선):
    한도: 없음
    → 즉시 전송 (컨트랙트 일시정지 등)

[가스비 큐잉 시스템]

  ┌────────────┐    ┌──────────────┐    ┌──────────┐
  │ Tx 요청     │ → │ Gas Oracle   │ → │ 판단     │
  │ (포인트 적립)│    │ 현재 가스비   │    │          │
  └────────────┘    └──────────────┘    └────┬─────┘
                                             │
                              ┌───────────────┼──────────┐
                              ▼               ▼          ▼
                        [즉시 전송]      [큐 대기]     [관리자 승인]
                        가스비 < 한도    가스비 > 한도   가스비 >>> 한도
                                       30분마다 재확인
```

---

### 6. 서비스별로 답이 다른 이유

```
[같은 "Nonce 꼬임" 문제, 다른 해결책]

┌──────────────┬──────────────────┬──────────────────┬──────────────────┐
│              │ 호텔 포인트 적립   │ 게임 아이템 민팅   │ 결제 시스템        │
├──────────────┼──────────────────┼──────────────────┼──────────────────┤
│ 긴급도       │ 낮음 (분~시간)    │ 중간 (초~분)      │ 높음 (즉시)       │
│ 실패 허용    │ 지연 OK          │ 재시도 OK         │ 실패 불가          │
│ Nonce Gap 시 │ 큐에 쌓고 대기    │ Gap 채우고 재전송  │ 별도 Hot Wallet   │
│ 가스비 급등  │ 대기             │ 한도 내 전송       │ 무조건 전송        │
│ Reorg 대응   │ 12 conf 대기     │ 6 conf 후 지급    │ 32 conf 대기      │
│ RPC 장애     │ Outbox 큐잉      │ 즉시 폴백         │ 멀티 RPC 상시     │
└──────────────┴──────────────────┴──────────────────┴──────────────────┘

[Hot Wallet vs Cold Wallet 전략]

  Hot Wallet: 서버가 프라이빗 키를 가지고 자동 서명
    → 빠른 처리, 보안 위험
    → 적은 금액만 보관 (일일 한도 설정)

  Cold Wallet: 오프라인 키, 수동 서명
    → 느린 처리, 보안 강력
    → 대량 자금 보관

  실무 패턴:
  - Hot Wallet에 하루 처리량의 2배 정도만 충전
  - Hot Wallet 잔액 부족 알림 → Cold에서 수동 충전
  - Hot Wallet 별로 용도 분리 (민팅용, 전송용, 가스비 지급용)
  - 각 Hot Wallet은 독립적 nonce → 서로 영향 없음
```

---

### 7. 모니터링과 복구 — 패턴에는 없는 "운영"

```
[블록체인 서비스 필수 모니터링 항목]

  1. Tx 상태 분포
     PENDING 비율이 급증 → 가스비 문제 또는 Nonce Gap
     REVERTED 비율 증가 → 컨트랙트 로직 오류

  2. Nonce 건강도
     로컬 nonce vs 온체인 nonce 차이
     차이 > 0 → pending Tx 존재
     차이 < 0 → 있을 수 없음, 심각한 버그

  3. 가스비 추이
     현재 baseFee + 이동 평균
     한도 초과 시 알림

  4. RPC 노드 상태
     응답 시간, 에러율, 블록 높이
     노드 간 블록 높이 차이

  5. Hot Wallet 잔액
     ETH(가스비용) + 토큰 잔액
     임계값 이하 시 충전 알림

  6. 이벤트 리스너 지연
     최신 블록 vs 처리 완료 블록 차이
     차이 > 100블록 → 리스너 장애

[Gap Recovery — 놓친 이벤트 복구]

  이벤트 리스너가 다운됐다가 복구되면:

  마지막 처리 블록: 19,000,000
  현재 블록:        19,000,500

  → 19,000,001 ~ 19,000,500 사이의 이벤트를 모두 재조회
  → eth_getLogs로 범위 조회 (한 번에 너무 많으면 분할)
  → 이미 처리한 이벤트는 멱등성으로 걸러냄

  async function gapRecovery(fromBlock, toBlock) {
    const BATCH_SIZE = 1000;

    for (let start = fromBlock; start <= toBlock; start += BATCH_SIZE) {
      const end = Math.min(start + BATCH_SIZE - 1, toBlock);
      const logs = await contract.queryFilter('*', start, end);

      for (const log of logs) {
        await processEventIdempotent(log);  // 멱등 처리
      }

      await saveLastProcessedBlock(end);
    }
  }
```

---

## 헷갈렸던 포인트

### Q1: Tx가 Reverted 됐는데 가스비는 왜 나가나?

```
[블록체인의 가스비 규칙]

  Tx 실행이 시작되면 → 가스비는 무조건 소모된다.
  실행 도중 require()에서 실패해도 → 거기까지 쓴 가스는 돌려받지 못한다.

  이유:
  검증자는 "이 Tx를 실행해 봤다"는 작업을 했다.
  실패한 Tx라도 연산 자원을 사용했으므로 비용을 지불해야 한다.

  → 컨트랙트 로직에서 가능한 빨리 실패하는 게 가스비 절약
  → require()를 함수 최상단에 배치 (CEI 패턴의 Checks)

  성공 Tx: gasUsed = 80,000 → 비용 지불
  실패 Tx: gasUsed = 30,000 → 비용 지불 (더 적긴 함)
  전송 안 됨: gasUsed = 0   → 비용 없음 (Mempool에도 안 감)
```

### Q2: 왜 단일 지갑으로 여러 Tx를 동시에 못 보내나?

```
[Nonce의 순차 특성]

  nonce 5, 6, 7을 동시에 전송하는 것은 가능하다.
  하지만 처리는 반드시 5 → 6 → 7 순서.

  문제:
  - nonce 5가 Mempool에서 대기 중이면 6, 7도 대기
  - nonce 5가 실패하면 6, 7은 영원히 처리 안 됨

[해결: 멀티 월렛 풀]

  지갑 A: nonce 0, 1, 2, 3 ... (포인트 적립 전용)
  지갑 B: nonce 0, 1, 2, 3 ... (아이템 민팅 전용)
  지갑 C: nonce 0, 1, 2, 3 ... (보상 지급 전용)

  → 각 지갑이 독립적인 nonce 시퀀스
  → 지갑 A의 Nonce Gap이 지갑 B에 영향 없음
  → 병렬 처리 가능

  지갑 풀 관리:
  - 풀에서 사용 가능한 지갑 할당
  - Tx 완료 후 지갑 반환
  - 각 지갑 잔액 모니터링
```

### Q3: "At-Least-Once + 멱등성"이면 Exactly-Once 아닌가?

```
[미묘한 차이]

  At-Least-Once + 멱등성 = "관찰 가능한 Exactly-Once"

  실제로 Tx는 2번 전송될 수 있다:
  1. 첫 전송: 성공했는데 확인 응답을 못 받음 (네트워크 단절)
  2. 재전송: 같은 nonce → 네트워크에서 거절 (이미 처리됨)
     또는: 같은 mintRequestId → 컨트랙트에서 거절 (이미 처리됨)

  결과: 유저 입장에서는 1번만 처리된 것처럼 보임
  → "관찰 가능한" Exactly-Once

  진정한 Exactly-Once와의 차이:
  - 네트워크 비용은 2번 발생 (가스비 2번)
  - 두 번째는 "이미 처리됨" 응답을 받으므로 큰 비용은 아님
  - 하지만 시스템 자원(네트워크, 노드 연산)은 소모됨
```

---

## 참고 자료

| 자료 | 설명 |
|------|------|
| [Ethereum Yellow Paper](https://ethereum.github.io/yellowpaper/paper.pdf) | Nonce, Gas, Tx 실행 모델의 원본 스펙 |
| [EIP-1559](https://eips.ethereum.org/EIPS/eip-1559) | 동적 가스비 모델 공식 제안 |
| [ethers.js NonceManager](https://docs.ethers.org/v6/api/providers/#NonceManager) | Nonce 관리 래퍼 클래스 |
| [Alchemy — Handling Nonce Issues](https://docs.alchemy.com/docs/handling-nonce-issues) | Nonce 실전 트러블슈팅 가이드 |
| [Paradigm — Guide to Chain Reorgs](https://www.paradigm.xyz/) | Reorg 이해와 대응 전략 |
| [OpenZeppelin Defender](https://docs.openzeppelin.com/defender/) | Tx 관리, 모니터링, 자동화 도구 |
