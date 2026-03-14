---
title: "Web3 / 지갑 / 이더리움 네트워크 생태계 — 백엔드 개발자를 위한 총정리"
parent: Blockchain / Web3
nav_order: 1
tags: [Web3, 이더리움, EVM, Gas, HD Wallet, DeFi, NFT, L2, Rollup, SIWE]
description: "Web2 vs Web3 차이, 이더리움 EVM/Gas/EIP-1559, HD Wallet, 스마트 컨트랙트, DeFi/NFT, L2 Rollup 등 백엔드 개발자를 위한 Web3 총정리입니다."
---

# Web3 / 지갑 / 이더리움 네트워크 생태계 — 백엔드 개발자를 위한 총정리

## 핵심 정리

### 1. Web3란 무엇인가

```
[Web1] 읽기 전용 (1990s~2000s)
  정적 웹페이지, 서버가 콘텐츠 제공 → 사용자는 소비만

[Web2] 읽기 + 쓰기 (2000s~현재)
  SNS, 플랫폼 경제 → 사용자가 콘텐츠 생성
  문제: 데이터를 플랫폼(Google, Meta)이 소유·통제

[Web3] 읽기 + 쓰기 + 소유 (현재~)
  블록체인 기반 → 사용자가 자산과 데이터를 직접 소유
  중앙 서버 없이 스마트 컨트랙트가 비즈니스 로직 실행
```

**백엔드 개발자 관점에서 Web3의 핵심 차이:**

| | Web2 | Web3 |
|---|---|---|
| **서버** | AWS/GCP의 중앙 서버 | 블록체인 노드(분산) |
| **DB** | MySQL, PostgreSQL | 블록체인 자체가 상태 저장소 |
| **인증** | JWT, Session, OAuth | 지갑 서명 (ECDSA) |
| **API** | REST/GraphQL → 서버 | JSON-RPC → 블록체인 노드 |
| **배포** | CI/CD → 서버 | 스마트 컨트랙트 Deploy → 블록체인 |
| **결제** | PG사 연동 (카드, 계좌) | 토큰 전송 (ETH, USDT) |
| **비즈니스 로직** | Spring, Node.js 서버 | Solidity 스마트 컨트랙트 |

---

### 2. 이더리움 네트워크 구조

```
[이더리움 네트워크의 전체 구조]

사용자 지갑 (MetaMask)
    │
    │ 트랜잭션 서명 & 전송
    ▼
RPC 노드 (Infura / Alchemy / 자체 노드)
    │
    │ JSON-RPC 요청 전달
    ▼
이더리움 네트워크 (P2P)
    ├── Execution Layer (실행 계층)
    │    └── EVM: 스마트 컨트랙트 실행
    │    └── State: 모든 계정/잔액/컨트랙트 상태
    │
    └── Consensus Layer (합의 계층, PoS)
         └── Validator: ETH 32개 스테이킹
         └── Slot/Epoch: 12초마다 블록 생성
```

#### 핵심 개념

**블록과 트랜잭션:**
```
Block #18,500,000
├── Header
│   ├── parentHash: 이전 블록 해시
│   ├── timestamp: 1697000000
│   ├── baseFeePerGas: 30 Gwei     ← EIP-1559 기본 수수료
│   └── stateRoot: 상태 트리 루트
│
└── Transactions (최대 ~1500개)
    ├── tx0: 0xABC → 0xDEF, 1 ETH 전송
    ├── tx1: 0x123 → Contract, swap() 호출
    └── tx2: Contract Deploy (Uniswap V4)
```

**Gas — 이더리움의 연산 비용:**
```
Gas = 블록체인 연산의 "수수료"

트랜잭션 비용 = Gas Used × Gas Price

예시:
  ETH 전송:        21,000 Gas (고정)
  ERC-20 전송:     ~65,000 Gas
  Uniswap Swap:    ~150,000 Gas
  NFT Mint:        ~100,000~200,000 Gas

Gas Price = 30 Gwei = 0.00000003 ETH일 때:
  ETH 전송 비용 = 21,000 × 30 Gwei = 630,000 Gwei = 0.00063 ETH ≈ $2
```

**EIP-1559 수수료 모델:**
```
[EIP-1559 이전]
  Gas Price = 사용자가 직접 설정 (경매 방식)
  → 가격 예측 어렵고, 과다 지불 빈번

[EIP-1559 이후]
  총 수수료 = (Base Fee + Priority Fee) × Gas Used

  Base Fee: 네트워크가 자동 결정 (블록 혼잡도 기반)
            → 소각됨 (burn) → ETH 디플레이션 압력
  Priority Fee (Tip): 사용자 → Validator 직접 지급
            → 빠른 처리를 원하면 높게 설정
```

---

### 3. 계정 체계와 지갑

```
[이더리움 계정 2가지]

1. EOA (Externally Owned Account) — 사용자 지갑
   ├── 개인키(Private Key)로 제어
   ├── 트랜잭션을 "시작"할 수 있음
   └── 코드 없음

   주소 예: 0x742d35Cc6634C0532925a3b844Bc9e7595f2bD18
   개인키: 0x4c0883a69102937d6231471b5dbb... (256bit, 절대 노출 금지)

2. CA (Contract Account) — 스마트 컨트랙트
   ├── 코드(바이트코드)를 가짐
   ├── 트랜잭션을 스스로 "시작"할 수 없음
   ├── EOA가 호출해야 실행됨
   └── 개인키 없음

   주소 예: 0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984 (UNI 토큰)
```

**개인키 → 공개키 → 주소 생성 과정:**
```
Private Key (256bit 난수)
    │
    │  타원곡선 암호(secp256k1)
    ▼
Public Key (512bit)
    │
    │  Keccak-256 해시 → 마지막 20바이트
    ▼
Address (160bit = 20바이트 = 40 hex chars)
    = "0x" + 40자리 hex

핵심: Private Key → Public Key는 가능
      Public Key → Private Key는 불가능 (역함수 없음)
```

#### 지갑의 종류와 동작 원리

```
[Hot Wallet — 인터넷 연결됨]
├── 브라우저 지갑: MetaMask, Rabby
├── 모바일 지갑: Trust Wallet, Rainbow
└── 서버 지갑: 거래소 커스터디 지갑

[Cold Wallet — 인터넷 미연결]
├── 하드웨어 지갑: Ledger, Trezor
└── 페이퍼 지갑: 개인키를 종이에 인쇄

[MPC Wallet — 키 분산 관리]
└── 개인키를 여러 조각으로 나눠 보관
    예: Fireblocks, Coinbase WaaS
    → 기업용 커스터디 솔루션에서 많이 사용
```

**HD Wallet (Hierarchical Deterministic):**
```
시드 구문 (Mnemonic) 12~24 단어:
  "witch collapse practice feed shame open despair creek road again ice least"

    │
    │  BIP-39: 시드 → 마스터 키
    ▼
Master Key
    │
    │  BIP-44: 파생 경로
    ▼
m / purpose' / coin_type' / account' / change / address_index

이더리움 기본 경로: m/44'/60'/0'/0/0

m/44'/60'/0'/0/0  → 0xABC... (첫 번째 주소)
m/44'/60'/0'/0/1  → 0xDEF... (두 번째 주소)
m/44'/60'/0'/0/2  → 0x123... (세 번째 주소)

→ 시드 하나로 무한히 많은 주소를 생성 가능!
→ 시드만 백업하면 모든 주소 복구 가능!
```

---

### 4. 스마트 컨트랙트

```
[스마트 컨트랙트 = 블록체인 위의 백엔드 코드]

Web2:
  Client → REST API → Spring Controller → Service → Repository → DB

Web3:
  지갑 → JSON-RPC → 블록체인 노드 → EVM → 스마트 컨트랙트 → State 변경
```

**Solidity 기본 예시 — ERC-20 토큰:**
```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract MyToken {
    string public name = "MyToken";
    string public symbol = "MTK";
    uint8 public decimals = 18;
    uint256 public totalSupply;

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 value);

    // 토큰 전송 — DB UPDATE가 아니라 상태 변경
    function transfer(address to, uint256 amount) external returns (bool) {
        require(balanceOf[msg.sender] >= amount, "Insufficient balance");

        balanceOf[msg.sender] -= amount;  // 보내는 사람 차감
        balanceOf[to] += amount;          // 받는 사람 증가

        emit Transfer(msg.sender, to, amount);  // 이벤트 로그 (인덱싱용)
        return true;
    }
}
```

**백엔드 개발자가 알아야 할 스마트 컨트랙트 특성:**

```
1. 불변성(Immutability)
   배포 후 코드 수정 불가!
   → Proxy 패턴으로 업그레이드 가능하게 설계 (UUPS, Transparent Proxy)

2. 가스 최적화 필수
   모든 연산에 Gas 비용 → 비효율적 코드 = 돈 낭비
   storage 읽기: 2,100 Gas / memory 읽기: 3 Gas
   → storage 접근 최소화가 핵심

3. 외부 데이터 접근 불가
   컨트랙트는 외부 API 호출 불가!
   → Oracle(Chainlink)로 외부 데이터 주입

4. 동시성 없음
   트랜잭션은 순차 실행 (블록 내에서)
   → Race Condition 대신 Front-running 공격이 이슈
```

---

### 5. 이더리움 생태계 핵심 프로토콜

#### DeFi (탈중앙 금융)

```
[Uniswap — DEX (탈중앙 거래소)]
  중앙 거래소 없이 토큰 교환
  AMM (Automated Market Maker): x * y = k 공식
  유동성 풀에 토큰 쌍을 예치 → 자동 가격 결정

[Aave / Compound — 대출 프로토콜]
  은행 없이 암호화폐 대출/차입
  담보 → 대출 (과담보 방식, 보통 150%)
  청산(Liquidation): 담보 가치 하락 시 자동 청산

[MakerDAO — 스테이블코인]
  DAI: ETH 담보로 발행하는 달러 페깅 스테이블코인
  CDP (Collateralized Debt Position) 구조
```

#### NFT & 토큰 표준

```
[ERC-20]  — 대체 가능 토큰 (Fungible Token)
  USDT, UNI, LINK 등
  내 1 USDT = 네 1 USDT (동일한 가치)

[ERC-721] — 대체 불가 토큰 (NFT)
  BAYC, CryptoPunks 등
  각 토큰이 고유한 tokenId를 가짐

[ERC-1155] — 멀티 토큰
  하나의 컨트랙트에서 FT + NFT 동시 관리
  게임 아이템 등에 적합

[ERC-4337] — 계정 추상화 (Account Abstraction)
  EOA 없이 스마트 컨트랙트 자체가 계정 역할
  → 소셜 로그인, 가스비 대납, 배치 트랜잭션 가능
  → Web2 수준의 UX를 Web3에서 구현하는 핵심 기술
```

#### Layer 2 — 확장성 솔루션

```
[이더리움 L1의 한계]
  TPS: ~15 (초당 15 트랜잭션)
  Gas비: $2~$50+ (혼잡 시)

[Layer 2 솔루션]
  L1에 최종 결과만 기록, 연산은 L2에서 수행

  ┌─ Optimistic Rollup (Optimism, Arbitrum, Base)
  │   트랜잭션을 L2에서 실행 → L1에 요약 제출
  │   "일단 유효하다고 가정" → 7일간 이의제기 가능
  │   장점: EVM 호환성 높음
  │   단점: 출금에 7일 대기
  │
  └─ ZK Rollup (zkSync, StarkNet, Polygon zkEVM)
      영지식 증명(ZKP)으로 유효성 즉시 검증
      장점: 출금 빠름, 보안 강함
      단점: EVM 호환성 제한적 (개선 중)

[L2 효과]
  TPS: 수천~수만
  Gas비: $0.01~$0.10
  → 실질적인 Web3 서비스는 대부분 L2에서 운영
```

---

### 6. 백엔드 개발자의 Web3 기술 스택

```
[Web3 백엔드 아키텍처]

┌──────────── Frontend ────────────┐
│  React/Next.js + wagmi/viem      │
│  지갑 연결 (MetaMask, WalletConnect) │
└──────────────┬───────────────────┘
               │
┌──────────────▼───────────────────┐
│         Backend (Web2 서버)        │
│  Spring Boot / Node.js / Go       │
│  ├── 블록체인 이벤트 인덱싱         │
│  ├── 트랜잭션 구성 & 서명 (서버 지갑) │
│  ├── 유저 인증 (SIWE)              │
│  ├── 메타데이터 관리                │
│  └── 오프체인 데이터 처리            │
└──────────────┬───────────────────┘
               │
┌──────────────▼───────────────────┐
│       블록체인 인프라                │
│  ├── RPC 노드: Alchemy / Infura   │
│  ├── 인덱서: The Graph / Goldsky   │
│  ├── 스토리지: IPFS / Arweave      │
│  └── Oracle: Chainlink             │
└──────────────┬───────────────────┘
               │
┌──────────────▼───────────────────┐
│         블록체인 네트워크            │
│  Ethereum / Polygon / Arbitrum    │
│  └── Smart Contracts (Solidity)   │
└──────────────────────────────────┘
```

**핵심 라이브러리 / 도구:**

| 도구 | 용도 | 비고 |
|------|------|------|
| **ethers.js** | JS/TS에서 블록체인 상호작용 | 가장 보편적, v6 최신 |
| **viem** | ethers.js 대안 (타입 안전) | wagmi 팀 개발, 최근 인기 급상승 |
| **web3.js** | 초기 Web3 라이브러리 | 레거시, 새 프로젝트엔 viem/ethers 권장 |
| **web3j** | Java에서 블록체인 상호작용 | Spring Boot + Web3 시 사용 |
| **Hardhat** | 스마트 컨트랙트 개발/테스트 | JS/TS 기반, 풍부한 플러그인 |
| **Foundry** | 스마트 컨트랙트 개발/테스트 | Rust 기반, Solidity로 테스트 작성, 빠름 |
| **OpenZeppelin** | 검증된 컨트랙트 라이브러리 | ERC-20/721 구현, 보안 감사 완료 |
| **The Graph** | 블록체인 데이터 인덱싱 | GraphQL로 온체인 데이터 조회 |
| **SIWE** | Sign-In with Ethereum | 지갑 기반 인증 (JWT 대체) |

**SIWE (Sign-In with Ethereum) — Web3 인증:**
```
[Web2 로그인]
  이메일 + 비밀번호 → 서버 검증 → JWT 발급

[Web3 로그인 (SIWE)]
  1. 서버가 nonce 생성 → 프론트에 전달
  2. 지갑이 메시지 서명: sign("로그인 메시지 + nonce")
  3. 서명을 서버에 전송
  4. 서버가 서명 검증 → 지갑 주소 확인 → JWT 발급

  → 비밀번호 없음! 개인키로 서명 = 본인 증명
```

---

### 7. 블록체인 백엔드에서 자주 다루는 작업

#### 이벤트 리스닝 & 인덱싱

```
[스마트 컨트랙트 이벤트를 DB에 인덱싱하는 패턴]

Smart Contract:
  event Transfer(address indexed from, address indexed to, uint256 value);

Backend:
  1. RPC 노드에서 이벤트 구독 (WebSocket or Polling)
  2. 이벤트 파싱 → DB 저장
  3. 블록 재정리(Reorg) 처리

// ethers.js 예시
const contract = new ethers.Contract(address, abi, provider);
contract.on("Transfer", (from, to, value, event) => {
    // DB에 저장
    saveTransfer({ from, to, value, txHash: event.transactionHash });
});

주의사항:
  - 블록 Reorg: 최근 몇 블록은 뒤집힐 수 있음
    → 12 confirmations 이후에 "확정"으로 처리
  - 누락 방지: 서버 다운 시 놓친 블록 범위를 배치로 재조회
  - 대규모 인덱싱: The Graph 또는 자체 인덱서 사용
```

#### 트랜잭션 관리

```
[서버에서 트랜잭션 보내기 — 주의사항]

1. Nonce 관리
   각 EOA는 순차적 nonce를 가짐 (0, 1, 2, 3...)
   동시에 여러 tx 전송 시 nonce 충돌 → 트랜잭션 실패
   → Nonce Manager 필요 (Redis 등으로 순차 관리)

2. Gas 추정
   eth_estimateGas로 예상 Gas 계산
   실패 방지를 위해 20~30% 여유분 추가
   Gas 급등 시 트랜잭션 stuck → Speed up(가격 올려 재전송)

3. 트랜잭션 상태 추적
   Pending → Confirmed → Finalized
   mempool에서 drop될 수 있음 → 모니터링 필수
```

---

## 헷갈렸던 포인트

### Q1: 이더리움 메인넷 vs 테스트넷 vs L2, 뭐가 다른가?

```
[메인넷] — 실제 돈이 오가는 네트워크
  Chain ID: 1
  통화: ETH (실제 가치)

[테스트넷] — 개발/테스트용 (무료 ETH 제공)
  Sepolia (Chain ID: 11155111) ← 현재 주력 테스트넷
  Holesky (Chain ID: 17000)   ← 스테이킹/인프라 테스트용

[L2] — 메인넷 위의 확장 레이어
  Arbitrum One (Chain ID: 42161)
  Optimism (Chain ID: 10)
  Base (Chain ID: 8453)       ← Coinbase가 만든 L2
  Polygon PoS (Chain ID: 137) ← 엄밀히 사이드체인이지만 L2로 취급
```

### Q2: 프라이빗 키 관리 — 서버에서 지갑을 어떻게 안전하게 관리하나?

```
[❌ 하면 안 되는 것]
  환경변수에 개인키 평문 저장
  소스코드에 개인키 하드코딩
  일반 DB에 개인키 저장

[✅ 실무 방법]
  1. KMS (Key Management Service)
     AWS KMS, GCP Cloud KMS
     → 키가 HSM(하드웨어 보안 모듈) 안에서만 존재
     → 서명 요청만 보내고, 키 자체를 꺼낼 수 없음

  2. Vault (HashiCorp Vault)
     → 비밀 관리 전용 시스템
     → 접근 제어, 감사 로그

  3. MPC (Multi-Party Computation)
     → 키를 여러 조각으로 나눠 보관
     → 서명 시 조각들이 협력해서 서명 생성
     → 단일 장애점 제거
     예: Fireblocks, Dfns

  4. Account Abstraction (ERC-4337)
     → EOA 대신 스마트 컨트랙트 지갑 사용
     → 멀티시그, 가스비 대납, 소셜 복구 가능
```

### Q3: 면접에서 "Web3 백엔드 경험" 어필 포인트

```
1. 블록체인 이벤트 인덱싱 경험
   "스마트 컨트랙트 이벤트를 실시간으로 수집·가공하여
    오프체인 DB에 저장하는 파이프라인을 구축했습니다.
    블록 Reorg 처리, 누락 블록 복구 등도 구현했습니다."

2. 트랜잭션 파이프라인
   "서버 사이드에서 트랜잭션을 구성·서명·전송하고,
    Nonce 관리, Gas 추정, 실패 재시도 로직을 설계했습니다."

3. 지갑 인증 (SIWE)
   "MetaMask 서명 기반 인증 시스템을 구현하여
    기존 JWT 인증과 통합했습니다."

4. 보안
   "KMS/Vault를 활용한 프라이빗 키 관리,
    스마트 컨트랙트 보안 감사(Reentrancy, Flash Loan 공격 방어)
    경험이 있습니다."
```

---

## 참고 레포지토리

### 핵심 라이브러리 & 도구

| 레포 | 설명 |
|------|------|
| [ethereum/go-ethereum](https://github.com/ethereum/go-ethereum) | Go 이더리움 클라이언트(Geth). 이더리움 노드 구현체의 사실상 표준 |
| [ethers-io/ethers.js](https://github.com/ethers-io/ethers.js) | 가장 많이 쓰이는 이더리움 JS 라이브러리. Provider/Signer/Contract 추상화 |
| [wevm/viem](https://github.com/wevm/viem) | TypeScript 우선 이더리움 라이브러리. 타입 안전성과 성능에 중점, ethers.js 대안 |
| [wevm/wagmi](https://github.com/wevm/wagmi) | React Hooks 기반 이더리움 연동 라이브러리. viem 위에 구축 |
| [web3j/web3j](https://github.com/web3j/web3j) | Java/Android용 이더리움 라이브러리. Spring Boot 통합 지원 |
| [ChainSafe/web3.js](https://github.com/ChainSafe/web3.js) | 원조 이더리움 JS 라이브러리. **2025.3 아카이브됨**, 신규 프로젝트엔 viem/ethers 권장 |

### 스마트 컨트랙트 개발

| 레포 | 설명 |
|------|------|
| [NomicFoundation/hardhat](https://github.com/NomicFoundation/hardhat) | JS/TS 기반 스마트 컨트랙트 개발 환경. 로컬 네트워크, 테스트, 배포 |
| [foundry-rs/foundry](https://github.com/foundry-rs/foundry) | Rust 기반 초고속 개발 도구. Solidity로 테스트 작성, forge/cast/anvil 포함 |
| [OpenZeppelin/openzeppelin-contracts](https://github.com/OpenZeppelin/openzeppelin-contracts) | 업계 표준 보안 감사 완료 컨트랙트 라이브러리 (ERC-20/721/1155, Access Control 등) |
| [transmissions11/solmate](https://github.com/transmissions11/solmate) | 가스 최적화된 Solidity 컨트랙트. OpenZeppelin보다 효율적이지만 덜 방어적 |

### DeFi 프로토콜 (소스 코드 학습용)

| 레포 | 설명 |
|------|------|
| [Uniswap/v3-core](https://github.com/Uniswap/v3-core) | Uniswap V3 코어 컨트랙트. AMM, Concentrated Liquidity 학습의 교과서 |
| [Uniswap/v4-core](https://github.com/Uniswap/v4-core) | Uniswap V4 코어. Hooks 아키텍처, Singleton 패턴 등 최신 DeFi 설계 |
| [aave/aave-v3-core](https://github.com/aave/aave-v3-core) | Aave V3 대출 프로토콜. 대출/차입/청산 메커니즘 학습 |
| [makerdao/dss](https://github.com/makerdao/dss) | MakerDAO 핵심 시스템. CDP, 스테이블코인(DAI) 발행 로직 |

### 인프라 & 인덱싱

| 레포 | 설명 |
|------|------|
| [graphprotocol/graph-node](https://github.com/graphprotocol/graph-node) | The Graph 노드 구현. 블록체인 데이터를 GraphQL로 인덱싱 |
| [paradigmxyz/reth](https://github.com/paradigmxyz/reth) | Rust 이더리움 실행 클라이언트. 고성능 노드 아키텍처 학습 |
| [WalletConnect/walletconnect-monorepo](https://github.com/WalletConnect/walletconnect-monorepo) | 지갑 연결 프로토콜. 모바일 지갑-dApp 연동 표준 |
| [eth-infinitism/account-abstraction](https://github.com/eth-infinitism/account-abstraction) | ERC-4337 레퍼런스 구현. 계정 추상화의 공식 구현체 |

### 학습 & 튜토리얼

| 레포 | 설명 |
|------|------|
| [scaffold-eth/scaffold-eth-2](https://github.com/scaffold-eth/scaffold-eth-2) | 풀스택 Web3 dApp 보일러플레이트. Next.js + Hardhat + wagmi. 빠른 프로토타이핑에 최적 |
| [smartcontractkit/full-blockchain-solidity-course-js](https://github.com/smartcontractkit/full-blockchain-solidity-course-js) | Patrick Collins의 Solidity 풀코스 (32시간 무료 강의 코드) |
| [Cyfrin/foundry-full-course-cu](https://github.com/Cyfrin/foundry-full-course-cu) | Foundry 기반 Solidity 최신 풀코스. Cyfrin Updraft 커리큘럼 |
| [DeFiVulnLabs](https://github.com/SunWeb3Sec/DeFiVulnLabs) | DeFi 보안 취약점 실습. Reentrancy, Flash Loan, Oracle Manipulation 등 |
| [AmazingAng/WTF-Solidity](https://github.com/AmazingAng/WTF-Solidity) | ⭐11.2k. 초보자 친화 Solidity 튜토리얼. ERC-20/721, 에어드랍, 서명 검증 등 |
| [theredguild/damn-vulnerable-defi](https://github.com/theredguild/damn-vulnerable-defi) | 스마트 컨트랙트 보안 CTF. Flash Loan, Oracle, DEX, 거버넌스 공격 실습 |
| [smartcontractkit/defi-minimal](https://github.com/smartcontractkit/defi-minimal) | DeFi 핵심 개념(DEX, 토큰 스왑 등)의 최소 구현. 복잡한 프로덕션 코드 없이 원리 파악에 최적 |
| [OffcierCia/DeFi-Developer-Road-Map](https://github.com/OffcierCia/DeFi-Developer-Road-Map) | ⭐8.8k. DeFi 개발자 로드맵. 도구, 보안 팁, 학습 경로 큐레이션 |

### 보안

| 레포 | 설명 |
|------|------|
| [crytic/slither](https://github.com/crytic/slither) | Solidity 정적 분석 도구. 취약점 자동 탐지 |
| [consensys/mythril](https://github.com/consensys/mythril) | EVM 바이트코드 보안 분석 도구. Symbolic Execution 기반 |
| [pcaversaccio/snapper](https://github.com/pcaversaccio/snapper) | 스마트 컨트랙트 스토리지 스냅샷 도구 |

### 한국어 리소스

| 레포 | 설명 |
|------|------|
| [yunho0130/awesome-blockchain-kor](https://github.com/yunho0130/awesome-blockchain-kor) | "블록체인의 정석" 서적 소스코드 및 참고자료. 블록체인 원리, ICO 이해 등 |
| [mingrammer/blockchain-tutorial](https://github.com/mingrammer/blockchain-tutorial) | "Building Blockchain in Go" 한국어 번역. Go로 블록체인 직접 구현하며 학습 |
| [solidity-docs/ko-korean](https://github.com/solidity-docs/ko-korean) | Solidity 공식 문서 한국어 번역 프로젝트 |
| [ConsenSys/ethereum-developer-tools-list (한국어)](https://github.com/ConsenSys/ethereum-developer-tools-list/blob/master/README_Korean.md) | ConsenSys 이더리움 개발 도구 모음 한국어 번역 |

---

## 추천 학습 로드맵 (백엔드 개발자용)

```
[1단계: 기초 이해]
  Patrick Collins 풀코스 (full-blockchain-solidity-course-js)
  → 블록체인 기초 + Solidity + Hardhat

[2단계: 실습]
  CryptoZombies 또는 SpeedRunEthereum 챌린지
  → 게임형 학습으로 Solidity 문법 체득

[3단계: 표준 학습]
  OpenZeppelin Contracts 소스 코드 읽기
  → ERC-20/721 구현, Access Control 패턴 이해

[4단계: 실전 DeFi]
  Uniswap V3/V4 소스 코드 분석
  → AMM, Concentrated Liquidity, Hooks 아키텍처

[5단계: 보안]
  Damn Vulnerable DeFi + DeFiVulnLabs
  → Reentrancy, Flash Loan, Oracle 공격 이해

[6단계: 모던 도구]
  Foundry + viem으로 직접 프로젝트 구축
  → 2025~2026 기준 업계 표준 도구 체인

참고: web3.js는 2025.3 아카이브됨 → viem 또는 ethers.js 사용 권장
```
