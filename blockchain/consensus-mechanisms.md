# 합의 메커니즘 심화 — PoW, PoS, Reorg, Block Finality

## 핵심 정리

### 1. 합의 메커니즘이란?

```
[왜 합의가 필요한가]

  중앙 서버 (Web2):
    서버 1대가 "이 거래가 유효하다"고 판단 → 끝
    → 신뢰 기반: 서버 운영자를 믿어야 함

  분산 네트워크 (Web3):
    수천 개 노드가 동시에 존재
    → "누가 다음 블록을 생성하는가?"
    → "어떤 트랜잭션이 유효한가?"
    → "충돌하는 블록이 생기면 어느 것을 채택하는가?"
    → 이 질문들에 모든 노드가 동의하는 규칙 = 합의 메커니즘

[합의 메커니즘의 핵심 목표]

  1. 단일 진실(Single Source of Truth): 모든 노드가 같은 상태에 동의
  2. 비잔틴 장애 허용(BFT): 악의적 노드가 있어도 정상 동작
  3. 이중 지불 방지: 같은 자산을 두 번 쓸 수 없음
  4. 활성(Liveness): 시스템이 멈추지 않고 계속 블록 생성
  5. 검열 저항성: 특정 트랜잭션을 영원히 차단할 수 없음
```

---

### 2. PoW (Proof of Work) — 작업 증명

```
[PoW 동작 원리]

  "수학 퍼즐을 가장 먼저 푸는 채굴자가 블록 생성권을 얻는다"

  채굴 과정:
  1. 채굴자가 pending Tx들을 모아 블록 후보를 만듦
  2. 블록 헤더 + nonce를 해싱
  3. 해시값이 목표 난이도(target) 이하가 되는 nonce를 찾을 때까지 반복
  4. 찾으면 블록을 네트워크에 전파
  5. 다른 노드들이 해시를 검증 (검증은 한 번의 해싱으로 즉시)
  6. 유효하면 블록 채택, 채굴자는 보상(Block Reward + Tx Fee) 수령

  핵심: "찾기는 어렵고, 검증은 쉽다" (비대칭적 난이도)

  Block Header:
  ┌──────────────────────────────┐
  │ parentHash                    │
  │ timestamp                     │
  │ transactionsRoot              │
  │ nonce: 0, 1, 2, ... N        │ ← 이 값을 변경하며 반복 해싱
  └──────────────────────────────┘
        │
        ▼ SHA-256 (비트코인) / Ethash (이더리움 PoW)
  hash = 0x0000000000000abcdef...
         ^^^^^^^^^^^^^^^^
         앞자리 0이 많을수록 난이도 높음

[난이도 조정]

  비트코인: 2016블록(~2주)마다 조정
    목표: 블록 1개당 평균 10분
    전체 해시파워 증가 → 난이도 상승 → 10분 유지

  이더리움(과거 PoW): 블록마다 동적 조정
    목표: 블록 1개당 약 13초
```

#### PoW의 장단점

```
[장점]
  1. 검증된 보안: 비트코인 15년+ 무사고 운영
  2. 탈중앙화: 누구나 채굴 참여 가능 (이론적으로)
  3. 단순한 모델: 해시파워 = 블록 생성 확률
  4. Sybil 공격 저항: 가짜 노드를 만들어도 해시파워 없으면 무력

[단점]
  1. 에너지 낭비: 비트코인만으로 아르헨티나 수준 전력 소비
  2. 51% 공격: 전체 해시파워의 51% 장악 시 이중 지불 가능
  3. 중앙화 경향: ASIC 채굴기 → 대형 채굴장 독점
  4. 처리 속도: TPS가 낮음 (비트코인 ~7, 이더리움 PoW ~15)
  5. 확정성 부재: 확률적 최종성만 제공 (블록이 깊어질수록 안전)

[51% 공격이란?]

  공격자가 전체 해시파워의 51% 이상을 장악하면:
  1. 자기 체인을 비밀리에 채굴
  2. 정상 체인보다 길어지면 공개
  3. 정상 체인이 무효화 → 이중 지불 성공

  현실성:
  비트코인: 사실상 불가능 (수조 원의 장비 + 전력 필요)
  소규모 PoW 체인: 실제 피해 사례 있음 (ETC, BTG 등)
```

---

### 3. PoS (Proof of Stake) — 지분 증명

```
[PoS 동작 원리]

  "ETH를 스테이킹한 검증자(Validator) 중에서 랜덤으로 블록 제안자를 선정"

  이더리움 PoS (The Merge 이후, 2022.09~):

  [Validator 되는 방법]
    1. 32 ETH를 Deposit Contract에 스테이킹
    2. Beacon Chain에 Validator로 등록
    3. 검증 노드 소프트웨어 실행 (24/7 운영 필수)

  [블록 생성 과정]
    1. 매 Slot(12초)마다 랜덤으로 1명의 Proposer 선정
    2. Proposer가 블록 생성 및 네트워크에 전파
    3. 나머지 Validator들이 해당 블록에 Attestation(투표)
    4. 2/3 이상 Attestation을 받으면 블록 채택
    5. 32 Slot = 1 Epoch, 각 Epoch 종료 시 Checkpoint 생성

  시간 구조:
  ┌─ Slot 0 ─┬─ Slot 1 ─┬─ Slot 2 ─┬─ ... ─┬─ Slot 31 ─┐
  │  12초     │  12초     │  12초     │       │  12초      │
  │ Proposer  │ Proposer  │ Proposer  │       │ Proposer   │
  │ + 투표    │ + 투표    │ + 투표    │       │ + 투표     │
  └───────────┴───────────┴───────────┴───────┴────────────┘
  ◄──────────────── 1 Epoch (약 6.4분) ──────────────────►

[Validator 보상과 처벌]

  보상:
  - 블록 제안 보상: ~0.02 ETH/블록
  - Attestation 보상: 정확한 투표에 비례
  - MEV 보상: Flashbots 등을 통한 추가 수익

  처벌 (Slashing):
  - 이중 투표: 같은 Slot에 2개 블록에 투표 → 스테이킹 일부 삭감
  - 서라운드 투표: 이전 투표를 감싸는 투표 → 삭감
  - 장기간 오프라인: 보상 감소 (삭감은 아님)
  - 대규모 동시 Slashing: 1/3 이상 동시 위반 시 전액 삭감 가능

  핵심: "잘못하면 스테이킹한 ETH를 잃는다"
  → 경제적 인센티브로 정직한 행동을 유도
```

#### PoS의 장단점

```
[장점]
  1. 에너지 효율: PoW 대비 99.95% 에너지 절감
  2. 더 빠른 최종성: ~15분 내 완전 최종성 (PoW는 확률적)
  3. Slashing: 악의적 행위에 대한 직접적 경제적 처벌
  4. 높은 참여 장벽 → 오히려 보안: 공격 비용이 해시파워가 아닌 자본
  5. Scalability 확장 용이: Sharding 등 확장 기술과 호환

[단점]
  1. 부의 집중: 많이 가진 자가 더 많이 벌 수 있음
  2. Nothing at Stake: 포크 시 양쪽에 투표하는 게 합리적
     → Slashing으로 해결
  3. Long-range Attack: 오래된 키로 대안 체인 생성
     → Weak Subjectivity Checkpoint로 방어
  4. 32 ETH 진입 장벽: 소액 보유자는 직접 검증 불가
     → Lido, RocketPool 등 리퀴드 스테이킹으로 해결
  5. MEV 문제: Proposer가 Tx 순서를 조작해 이익 추구
     → PBS(Proposer-Builder Separation)로 해결 시도 중
```

---

### 4. PoW vs PoS 비교

```
┌──────────────────┬──────────────────────┬──────────────────────┐
│                  │ PoW                  │ PoS                  │
├──────────────────┼──────────────────────┼──────────────────────┤
│ 블록 생성 자격    │ 해시파워 (채굴 장비)  │ 스테이킹된 자본       │
│ 에너지 소비      │ 매우 높음             │ 거의 없음             │
│ 블록 시간        │ 10분(BTC)/13초(ETH)  │ 12초(ETH PoS)        │
│ 최종성           │ 확률적 (6 conf ~1시간)│ 결정적 (2 epoch ~13분)│
│ 공격 비용        │ 해시파워 51% 확보     │ 스테이킹 1/3 확보     │
│ 공격 처벌        │ 장비+전력 낭비뿐      │ 스테이킹 삭감(Slash)  │
│ 대표 체인        │ Bitcoin, Litecoin    │ Ethereum, Solana     │
│ TPS             │ 7~15                 │ 15~100,000 (L2 포함) │
│ 탈중앙화         │ 채굴풀 집중 문제      │ 스테이킹풀 집중 문제   │
│ 하드웨어 요구     │ ASIC/GPU 필수        │ 일반 서버 가능        │
└──────────────────┴──────────────────────┴──────────────────────┘
```

---

### 5. Block Finality — 트랜잭션은 언제 "확정"되는가?

```
[Finality(최종성) = "이 트랜잭션은 절대 뒤집힐 수 없다"는 보장]

[PoW — 확률적 최종성 (Probabilistic Finality)]

  블록이 깊어질수록 뒤집힐 확률이 기하급수적으로 감소

  1 confirmation: ~25% 뒤집힐 확률 (Reorg 가능)
  3 confirmations: ~1% 이하
  6 confirmations: ~0.001% 이하 (비트코인 거래소 기준)
  12 confirmations: 사실상 불가능

  → "확정"이 아니라 "충분히 안전함"
  → 100% 보장은 이론적으로 없음

[PoS — 결정적 최종성 (Deterministic Finality)]

  이더리움 PoS의 최종성 단계:

  ┌──────────────────────────────────────────────────────┐
  │ Slot 내 (12초)                                       │
  │  블록 제안 + Attestation                              │
  │  → TENTATIVE: 아직 확정 아님                          │
  ├──────────────────────────────────────────────────────┤
  │ 1 Epoch 후 (~6.4분)                                  │
  │  Checkpoint로 Justified                               │
  │  → JUSTIFIED: 2/3 투표 확인, 높은 확률로 확정          │
  ├──────────────────────────────────────────────────────┤
  │ 2 Epochs 후 (~12.8분)                                │
  │  Justified Checkpoint가 Finalized                     │
  │  → FINALIZED: 완전 확정, 뒤집으려면 1/3 스테이킹 파괴   │
  └──────────────────────────────────────────────────────┘

  Finalized = 수학적으로 확정
  → PoW의 "충분히 안전함"과 질적으로 다름
  → 뒤집으려면 전체 스테이킹의 1/3을 Slash 당해야 함
  → 2024 기준 약 $30B+ 이상의 손실을 감수해야 함

[다른 체인의 Finality]

  Solana:       ~0.4초 (Optimistic Confirmation)
  Polygon PoS:  ~2분 (Checkpoint on Ethereum)
  Avalanche:    ~1초 (Snowball Consensus)
  Cosmos:       즉시 (Tendermint BFT, Single-Slot Finality)
  BSC:          ~3초 (15블록 / 45초 실사용)

  → 체인마다 Finality 시간이 완전히 다름
  → 서비스 설계 시 반드시 확인 필요
```

---

### 6. Reorg (Chain Reorganization) 심화

```
[Reorg = 이미 포함된 블록이 무효화되고 다른 블록으로 대체되는 현상]

[Reorg 발생 원리]

  정상 상태:
  Block 100 → Block 101 → Block 102

  두 검증자가 거의 동시에 블록 제안:
  Block 100 → Block 101a (검증자 A)
           └→ Block 101b (검증자 B)

  네트워크가 분리되어 각각 체인을 이어감:
  Block 100 → Block 101a → Block 102a
           └→ Block 101b → Block 102b → Block 103b

  더 무거운(또는 긴) 체인이 승리:
  → Block 101b → 102b → 103b가 정식 체인
  → Block 101a → 102a는 "Uncle/Ommer Block"으로 폐기
  → 101a에 포함됐던 Tx가 사라질 수 있음

[PoW에서의 Reorg]

  빈도: 비교적 잦음 (네트워크 지연 + 동시 채굴)
  깊이: 보통 1~2블록, 드물게 3+
  최악 사례: 2010년 비트코인 184억 BTC 버그 (Reorg로 수정)

  대응: N confirmations 대기
  비트코인 거래소: 보통 6 confirmations (약 1시간)
  이더리움 PoW: 12 confirmations (약 2.5분)

[PoS에서의 Reorg]

  이더리움 PoS Reorg 가능성:

  1. Finalized 이전 (< 2 Epochs):
     이론적으로 가능하지만 매우 드묾
     → 네트워크 파티션 또는 대규모 Validator 장애 시

  2. Finalized 이후 (>= 2 Epochs):
     불가능 (1/3 이상 Validator의 자발적 Slashing 필요)
     → 수십조 원의 경제적 손실을 감수해야 함

  실제 사례:
  2023.05: Ethereum Beacon Chain에서 7블록 Reorg 발생
    원인: 클라이언트 소프트웨어 버그
    영향: Finalized 전이었으므로 프로토콜 정상 동작
    교훈: PoS에서도 Finalized 전에는 Reorg 가능

[Reorg가 서비스에 미치는 영향]

  1. 입금 처리: "입금 완료"했는데 Reorg로 사라짐 → 잔액 불일치
  2. 출금 처리: 출금 Tx가 Reorg로 무효화 → 재전송 필요
  3. 이벤트 인덱싱: 인덱싱한 이벤트가 무효화 → DB 롤백 필요
  4. NFT 민팅: 민팅 완료 통보 후 Reorg → 사용자 혼란
  5. DEX 거래: 스왑 확정 후 Reorg → 가격 변동 리스크
```

#### Reorg 대응 아키텍처

```
[서비스별 Confirmation 전략]

  ┌─────────────────┬──────────────┬──────────────────────┐
  │ 서비스 유형      │ 필요 Conf    │ 이유                  │
  ├─────────────────┼──────────────┼──────────────────────┤
  │ 소액 결제 (<$10) │ 1~3 conf    │ 리스크 대비 UX 우선    │
  │ 일반 입금        │ 12 conf     │ 실질적 안전 (이더리움)  │
  │ 거래소 대량 입금  │ 32+ conf    │ 1 Epoch, Justified   │
  │ 고액 입금        │ 64 conf     │ 2 Epoch, Finalized   │
  │ 크로스체인 브릿지 │ Finalized   │ 되돌릴 수 없어야 함    │
  └─────────────────┴──────────────┴──────────────────────┘

[Reorg 감지 시스템 구현]

  // 블록 해시 체인 검증
  class ReorgDetector {
    private blockHashMap: Map<number, string>; // blockNumber → blockHash

    async onNewBlock(block) {
      const storedHash = this.blockHashMap.get(block.number - 1);

      if (storedHash && block.parentHash !== storedHash) {
        // Reorg 감지!
        const depth = await this.findReorgDepth(block);
        await this.handleReorg(depth);
      }

      this.blockHashMap.set(block.number, block.hash);
    }

    async findReorgDepth(newBlock) {
      let depth = 1;
      let current = newBlock;

      while (this.blockHashMap.has(current.number - 1) &&
             current.parentHash !== this.blockHashMap.get(current.number - 1)) {
        depth++;
        current = await provider.getBlock(current.number - 1);
      }
      return depth;
    }

    async handleReorg(depth) {
      // 1. 영향받는 블록 범위의 모든 Tx 조회
      // 2. DB 상태 롤백 (CONFIRMED → REORGED)
      // 3. 잔액/포인트 등 부수 효과 복원
      // 4. 알림 발송
      // 5. Tx 재처리 대기
    }
  }
```

---

### 7. 기타 합의 메커니즘

```
[DPoS (Delegated Proof of Stake)]
  투표로 소수의 대표 검증자를 선출
  선출된 검증자만 블록 생성
  대표 체인: EOS, TRON, BNB Chain

  장점: 매우 빠름 (TPS 수천)
  단점: 중앙화 우려 (소수 검증자에 권력 집중)

[PBFT (Practical Byzantine Fault Tolerance)]
  검증자 간 3단계 투표(Pre-Prepare → Prepare → Commit)
  2/3 이상 동의 시 블록 확정
  대표 체인: Hyperledger Fabric

  장점: 즉시 최종성
  단점: 검증자 수 제한 (~100), 통신 비용 O(n²)

[Proof of Authority (PoA)]
  사전 승인된 검증자만 블록 생성
  대표 체인: Ethereum Testnet (과거 Rinkeby), 프라이빗 체인

  장점: 매우 빠름, 설정 간단
  단점: 완전 중앙화

[Proof of History (PoH) — Solana]
  시간 순서를 암호학적으로 증명하는 타임스탬프 메커니즘
  VDF(Verifiable Delay Function) 기반
  실제로는 PoS와 결합하여 사용

  장점: 극한의 처리 속도 (TPS 65,000 이론치)
  단점: 하드웨어 요구사항 높음, 다운타임 이슈
```

---

## 헷갈렸던 포인트

### Q1: PoS에서 "Nothing at Stake" 문제란?

```
[문제 상황]

  PoW에서 포크 발생 시:
    채굴자는 한 체인만 선택해 채굴해야 함
    (해시파워를 분산하면 양쪽 다 불리)
    → 자연스럽게 하나의 체인에 수렴

  PoS에서 포크 발생 시:
    검증자가 양쪽 체인에 모두 투표하는 게 합리적
    (추가 비용 없이 양쪽에서 보상 가능)
    → 체인이 수렴하지 않을 위험

[해결: Slashing]

  양쪽에 투표(이중 투표)하면 스테이킹이 삭감된다.
  → 이중 투표의 기대 이익 < Slashing 손실
  → 합리적 검증자는 하나만 선택

  이더리움의 경우:
  이중 투표 감지 시 최소 1 ETH 삭감 (~$3,000+)
  대규모 동시 위반 시 최대 전액 삭감 (32 ETH)
```

### Q2: Finality가 왜 백엔드 개발자에게 중요한가?

```
[실무 임팩트]

  Finality를 모르면 이런 실수를 한다:

  1. 1 confirmation에서 입금 확정 처리
     → Reorg로 돈이 사라져도 DB에는 입금 완료
     → 사용자가 그 돈을 출금하면 → 거래소 손실

  2. 체인별 Finality 차이를 무시
     → BSC의 3초 Finality와 Bitcoin의 60분 Finality를 같게 취급
     → 크로스체인 브릿지에서 자금 유실

  3. Finalized 상태를 확인하지 않고 비가역적 작업 수행
     → NFT 전달, 포인트 확정, 출금 승인 등

[올바른 설계]

  // 체인별 Finality 설정
  const FINALITY_CONFIG = {
    ethereum: {
      tentative: 1,
      softConfirmed: 12,
      finalized: 64,        // 2 epochs
    },
    bitcoin: {
      tentative: 1,
      softConfirmed: 3,
      finalized: 6,
    },
    polygon: {
      tentative: 1,
      softConfirmed: 32,
      finalized: 128,       // L1 checkpoint 이후
    },
    solana: {
      tentative: 0,
      softConfirmed: 1,     // Optimistic Confirmation
      finalized: 31,        // Rooted
    }
  };
```

### Q3: The Merge 전후로 무엇이 달라졌나?

```
[The Merge (2022.09.15)]

  이더리움이 PoW → PoS로 전환한 역사적 이벤트

  변경된 것:
  - 합의 메커니즘: PoW → PoS
  - 블록 시간: 평균 13초(가변) → 정확히 12초(고정)
  - 에너지 소비: ~99.95% 감소
  - ETH 발행량: ~90% 감소 (Ultra Sound Money)
  - 최종성: 확률적 → 결정적 (2 Epochs)
  - Validator 최소 조건: GPU → 32 ETH

  변경되지 않은 것:
  - EVM, 스마트 컨트랙트 동작
  - Gas 모델 (EIP-1559)
  - 주소 체계 (EOA, CA)
  - Layer 2 호환성
  - JSON-RPC API (대부분)

  백엔드 영향:
  - 블록 시간이 고정적 → 더 예측 가능한 Tx 처리
  - Finality 개념 변경 → Confirmation 전략 재설계
  - Empty Slot 가능 → 빈 블록 처리 로직 필요
  - 새로운 Beacon API 사용 가능 (Validator 상태 조회 등)
```

---

## 참고 자료

| 자료 | 설명 |
|------|------|
| [Ethereum Proof of Stake](https://ethereum.org/en/developers/docs/consensus-mechanisms/pos/) | 이더리움 공식 PoS 문서 |
| [Bitcoin Whitepaper](https://bitcoin.org/bitcoin.pdf) | PoW 합의의 원본 논문 |
| [Ethereum Gasper](https://ethereum.org/en/developers/docs/consensus-mechanisms/pos/gasper/) | 이더리움 PoS 합의 프로토콜(Casper FFG + LMD GHOST) 설명 |
| [Vitalik — Proof of Stake FAQ](https://vitalik.eth.limo/general/2017/12/31/pos_faq.html) | PoS의 이론적 배경과 FAQ |
| [Paradigm — Guide to Chain Reorgs](https://www.paradigm.xyz/) | Reorg 이해와 대응 전략 |
| [EIP-3675: The Merge](https://eips.ethereum.org/EIPS/eip-3675) | PoW → PoS 전환 공식 제안 |
