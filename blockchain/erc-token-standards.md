---
title: "ERC 토큰 표준 심화 — ERC-20, 721, 1155, 4337, 백엔드 구현"
parent: Blockchain / Web3
nav_order: 6
---

# ERC 토큰 표준 심화 — ERC-20, 721, 1155, 4337, 백엔드 구현

## 핵심 정리

### 1. ERC란?

```
[ERC = Ethereum Request for Comments]

  이더리움 스마트 컨트랙트의 표준 인터페이스 제안
  EIP(Ethereum Improvement Proposal)의 하위 카테고리

  왜 표준이 중요한가:
  - 지갑: "이 컨트랙트는 ERC-20이므로 transfer() 호출하면 됨"
  - 거래소: "ERC-20 인터페이스만 구현하면 어떤 토큰이든 상장 가능"
  - DeFi: "ERC-20이면 Uniswap에서 자동으로 거래 가능"
  → 표준 덕분에 생태계 전체가 호환됨
```

---

### 2. ERC-20 — 대체 가능 토큰 (Fungible Token)

```
[ERC-20 = "내 1 USDT = 네 1 USDT" (동일한 가치)]

  대표 토큰: USDT, USDC, UNI, LINK, SHIB, DAI

[필수 인터페이스]

  interface IERC20 {
    // 읽기 함수
    function totalSupply() external view returns (uint256);
    function balanceOf(address account) external view returns (uint256);
    function allowance(address owner, address spender) external view returns (uint256);

    // 쓰기 함수
    function transfer(address to, uint256 amount) external returns (bool);
    function approve(address spender, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);

    // 이벤트
    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);
  }

[핵심 개념: approve + transferFrom 패턴]

  직접 전송: 내가 → 상대방 (transfer)
  위임 전송: 내가 → DEX에 "N개까지 써도 돼" 승인 (approve)
           → DEX가 내 토큰을 가져감 (transferFrom)

  유저 ────(approve)──── DEX 컨트랙트
    "100 USDT 쓸 수 있게 허락"
         │
  DEX ────(transferFrom)──── 유저 → 유동성 풀
    "유저의 USDT 50개를 풀로 이동"

  주의: approve(MAX_UINT256) — 무한 승인
  → 편리하지만 컨트랙트가 해킹당하면 모든 토큰 탈취 가능
  → 필요한 만큼만 승인하는 것이 안전

[decimals의 함정]

  ERC-20 토큰은 소수점이 없다!
  "10.5 USDT"는 실제로 10500000 (10.5 × 10^6)

  토큰별 decimals:
  USDT, USDC: decimals = 6   → 1 USDT = 1,000,000
  DAI, UNI:   decimals = 18  → 1 DAI = 1,000,000,000,000,000,000
  WBTC:       decimals = 8   → 1 WBTC = 100,000,000

  백엔드 주의사항:
  1. 항상 raw amount(정수)로 처리
  2. 표시할 때만 decimals로 나눔
  3. NUMERIC 타입 사용 (BIGINT 범위 초과 가능)
  4. 다른 토큰의 decimals를 하드코딩하지 말 것
     → decimals() 함수로 동적 조회

[백엔드에서 ERC-20 연동]

  // ethers.js v6
  const contract = new ethers.Contract(tokenAddress, ERC20_ABI, provider);

  // 잔액 조회
  const balance = await contract.balanceOf(userAddress);
  const decimals = await contract.decimals();
  const humanReadable = ethers.formatUnits(balance, decimals);

  // 토큰 전송 (서버 지갑에서)
  const signer = new ethers.Wallet(privateKey, provider);
  const contractWithSigner = contract.connect(signer);
  const tx = await contractWithSigner.transfer(
    toAddress,
    ethers.parseUnits("100", decimals)  // 100 토큰
  );

  // 입금 감지 (이벤트 리스닝)
  contract.on("Transfer", (from, to, value, event) => {
    if (depositAddresses.includes(to.toLowerCase())) {
      handleDeposit(from, to, value, event.log.transactionHash);
    }
  });
```

---

### 3. ERC-721 — 대체 불가 토큰 (NFT)

```
[ERC-721 = 각 토큰이 고유한 ID를 가짐]

  대표: BAYC, CryptoPunks, Azuki, ENS 도메인

[필수 인터페이스]

  interface IERC721 {
    function balanceOf(address owner) external view returns (uint256);
    function ownerOf(uint256 tokenId) external view returns (address);

    function safeTransferFrom(address from, address to, uint256 tokenId) external;
    function transferFrom(address from, address to, uint256 tokenId) external;

    function approve(address to, uint256 tokenId) external;
    function setApprovalForAll(address operator, bool approved) external;
    function getApproved(uint256 tokenId) external view returns (address);
    function isApprovedForAll(address owner, address operator) external view returns (bool);

    event Transfer(address indexed from, address indexed to, uint256 indexed tokenId);
    event Approval(address indexed owner, address indexed approved, uint256 indexed tokenId);
    event ApprovalForAll(address indexed owner, address indexed operator, bool approved);
  }

[ERC-20과의 핵심 차이]

  ┌──────────────┬────────────────────────┬────────────────────────┐
  │              │ ERC-20                 │ ERC-721                │
  ├──────────────┼────────────────────────┼────────────────────────┤
  │ 토큰 식별     │ 양(amount)으로 구분     │ tokenId로 구분          │
  │ 대체 가능     │ O (1 USDT = 1 USDT)   │ X (각 토큰이 유일)      │
  │ 전송          │ transfer(to, amount)   │ transferFrom(from,to,id)│
  │ 잔액          │ balanceOf → 숫자       │ balanceOf → 보유 개수   │
  │ 소유자 확인   │ 해당 없음              │ ownerOf(tokenId)       │
  │ 메타데이터    │ name, symbol, decimals │ tokenURI(tokenId)      │
  └──────────────┴────────────────────────┴────────────────────────┘

[tokenURI와 메타데이터]

  // tokenURI(1) 호출 → "https://api.example.com/metadata/1"
  // 또는 "ipfs://QmXyz.../1"

  반환되는 JSON:
  {
    "name": "Cool NFT #1",
    "description": "A very cool NFT",
    "image": "ipfs://QmImage.../1.png",
    "attributes": [
      {"trait_type": "Background", "value": "Blue"},
      {"trait_type": "Rarity", "value": "Legendary"}
    ]
  }

  메타데이터 저장 위치:
  - IPFS: 탈중앙 저장, 영구 보존 (CID 기반)
  - Arweave: 영구 저장 보장 (1회 결제)
  - 중앙 서버: 빠르지만 서버 다운 시 메타데이터 유실
  → 프로덕션에서는 IPFS/Arweave 권장

[safeTransferFrom vs transferFrom]

  transferFrom: 단순 전송
    → 받는 주소가 컨트랙트인데 NFT를 처리 못 하면? 영구 잠김!

  safeTransferFrom: 안전 전송
    → 받는 주소가 컨트랙트이면 onERC721Received() 호출
    → 컨트랙트가 "나 NFT 받을 수 있어"라고 응답해야 전송 완료
    → 응답 없으면 revert → NFT 잠김 방지
```

---

### 4. ERC-1155 — 멀티 토큰 표준

```
[ERC-1155 = 하나의 컨트랙트에서 FT + NFT 동시 관리]

  대표: 게임 아이템, OpenSea의 Shared Storefront

[왜 ERC-1155인가?]

  게임에서 필요한 토큰:
  - 골드 코인: 대체 가능 (FT) → ERC-20이 적합
  - 전설 검: 대체 불가 (NFT) → ERC-721이 적합
  - 포션 x100: 같은 종류지만 수량 있음 → ERC-20? ERC-721?

  ERC-20 + ERC-721을 각각 배포하면:
  → 컨트랙트 여러 개 → 배포 비용 높음
  → 토큰 간 거래 시 여러 Tx 필요

  ERC-1155 하나면:
  → 단일 컨트랙트에서 모든 토큰 관리
  → 배치 전송 지원 (한 Tx로 여러 토큰 전송)

[핵심 인터페이스]

  interface IERC1155 {
    // 단일/배치 전송
    function safeTransferFrom(
      address from, address to,
      uint256 id, uint256 amount, bytes data
    ) external;

    function safeBatchTransferFrom(
      address from, address to,
      uint256[] ids, uint256[] amounts, bytes data
    ) external;

    // 잔액 조회
    function balanceOf(address account, uint256 id) external view returns (uint256);
    function balanceOfBatch(
      address[] accounts, uint256[] ids
    ) external view returns (uint256[]);

    // 이벤트
    event TransferSingle(
      address indexed operator, address indexed from,
      address indexed to, uint256 id, uint256 value
    );
    event TransferBatch(
      address indexed operator, address indexed from,
      address indexed to, uint256[] ids, uint256[] values
    );
  }

[가스 효율 비교]

  5종류의 아이템을 5명에게 전송:

  ERC-20/721: 25개의 Tx (5종류 × 5명)
  ERC-1155: 5개의 Tx (safeBatchTransferFrom)
  → 가스비 ~80% 절감

[FT와 NFT의 구분]

  ERC-1155에서:
  - FT: 특정 id의 totalSupply > 1 (예: 골드 코인 id=1, supply=1,000,000)
  - NFT: 특정 id의 totalSupply = 1 (예: 전설 검 id=99, supply=1)
  - SFT(Semi-Fungible): 같은 종류지만 유한 수량 (예: 포션 id=5, supply=100)
```

---

### 5. ERC-4337 — 계정 추상화 (Account Abstraction)

```
[ERC-4337 = EOA 없이 스마트 컨트랙트 자체가 "계정" 역할]

  현재 문제:
  - MetaMask 설치 필요
  - 시드 구문 12단어 관리
  - 가스비를 ETH로 직접 지불
  - 비밀번호 분실 = 자산 영구 손실
  → Web2 사용자에게 진입장벽이 너무 높음

  ERC-4337 해결:
  - 이메일/소셜 로그인으로 지갑 생성
  - 가스비를 서비스가 대납 (Paymaster)
  - 비밀번호 분실 시 소셜 복구
  - 배치 트랜잭션 (여러 작업을 1번에)

[ERC-4337 아키텍처]

  ┌──────────────────────────────────────────────────────┐
  │ 사용자                                                │
  │  "USDT 100개를 0xABC에 보내고 싶어"                     │
  │                                                      │
  │  → UserOperation 생성 (Tx가 아님, 의도만 담은 데이터)     │
  └───────────────────────┬──────────────────────────────┘
                          │
                          ▼
  ┌──────────────────────────────────────────────────────┐
  │ Bundler (번들러)                                      │
  │  여러 UserOperation을 모아서 하나의 Tx로 묶음            │
  │  실제 온체인 Tx를 대신 전송 (EOA가 Bundler)             │
  └───────────────────────┬──────────────────────────────┘
                          │
                          ▼
  ┌──────────────────────────────────────────────────────┐
  │ EntryPoint (싱글톤 컨트랙트)                           │
  │  UserOperation을 검증하고 실행                         │
  │                                                      │
  │  1. Smart Account의 validateUserOp() 호출             │
  │     → 서명 검증 (ECDSA, Passkey, 멀티시그 등)          │
  │                                                      │
  │  2. Paymaster (선택):                                  │
  │     가스비 대납 검증                                    │
  │     → USDT로 가스비 지불 가능!                          │
  │                                                      │
  │  3. Smart Account의 execute() 호출                    │
  │     → 실제 토큰 전송 등 실행                            │
  └──────────────────────────────────────────────────────┘

[Paymaster — 가스비 대납]

  사용자가 ETH 없이도 트랜잭션 실행 가능!

  시나리오:
  1. 서비스가 Paymaster 컨트랙트를 배포하고 ETH를 충전
  2. 사용자가 UserOperation 생성 (가스비 = 0)
  3. Paymaster가 "이 사용자의 가스비를 대신 내겠다"
  4. Bundler가 Tx 전송, Paymaster에서 가스비 차감

  활용:
  - 게임: 첫 N회 무료 민팅
  - 서비스: 신규 가입자 가스비 지원
  - 기업: ERC-20(USDT 등)으로 가스비 결제

[백엔드 개발자에게 중요한 이유]

  기존: 사용자가 개인키 관리, 서버는 보조
  4337 이후: 서버가 Smart Account 인프라를 운영

  백엔드 업무:
  - Bundler 운영 (UserOperation 수집/번들링/전송)
  - Paymaster 관리 (가스비 예산, 정책, 잔액 충전)
  - Smart Account Factory (사용자 지갑 생성)
  - 소셜 복구 Guardian 서비스
  - UserOperation 유효성 검증 API
```

---

### 6. ERC-2612 — Permit (가스 없는 승인)

```
[문제: approve + transferFrom의 2 Tx 문제]

  DEX에서 토큰을 스왑하려면:
  Tx 1: approve(dex, amount) — 가스비 발생
  Tx 2: dex.swap() — 가스비 발생
  → 사용자가 2번의 Tx를 보내야 함

[ERC-2612 해결: 오프체인 서명으로 approve 대체]

  1. 사용자가 permit 데이터에 오프체인 서명 (가스비 없음)
  2. 서명을 DEX에 전달
  3. DEX가 permit() + transferFrom()을 한 Tx로 실행

  interface IERC20Permit {
    function permit(
      address owner,       // 토큰 소유자
      address spender,     // 승인받을 주소
      uint256 value,       // 승인 금액
      uint256 deadline,    // 서명 만료 시간
      uint8 v, bytes32 r, bytes32 s  // 서명
    ) external;
  }

  장점:
  - 사용자 Tx: 2개 → 1개 (가스비 절약)
  - 더 나은 UX
  - 백엔드가 permit을 모아서 배치 처리 가능

[백엔드 활용]

  // 사용자가 서명한 permit 데이터를 받아서 처리
  async function processPermitAndTransfer(permitData) {
    const { owner, spender, value, deadline, v, r, s } = permitData;

    // 한 번의 Tx로 permit + transfer 실행
    const tx = await batchContract.permitAndTransfer(
      tokenAddress, owner, spender, value, deadline, v, r, s,
      recipientAddress
    );
  }
```

---

### 7. 토큰 표준 비교 총정리

```
┌──────────┬──────────────┬──────────────┬──────────────┬──────────────┐
│          │ ERC-20       │ ERC-721      │ ERC-1155     │ ERC-4337     │
├──────────┼──────────────┼──────────────┼──────────────┼──────────────┤
│ 용도     │ 화폐, 포인트  │ NFT, 인증서  │ 게임 아이템   │ 스마트 지갑   │
│ 대체성   │ 대체 가능     │ 대체 불가    │ 둘 다 가능    │ 해당 없음    │
│ 식별     │ amount       │ tokenId      │ id + amount  │ 계정 주소    │
│ 배치전송  │ X            │ X            │ O            │ O           │
│ 메타데이터│ name/symbol  │ tokenURI     │ uri(id)      │ 해당 없음    │
│ 가스 효율│ 기준점        │ 높음         │ 매우 효율적   │ 상대적 높음  │
│ 대표 사례│ USDT, UNI    │ BAYC, ENS    │ 게임, OpenSea│ Safe, Alchemy│
└──────────┴──────────────┴──────────────┴──────────────┴──────────────┘
```

---

### 8. 거래소/서비스에서의 토큰 처리

```
[토큰 상장 시 백엔드 체크리스트]

  1. 컨트랙트 검증:
     □ ERC-20 인터페이스 완전 구현 확인
     □ decimals 확인 (6? 8? 18?)
     □ 비표준 구현 여부 (USDT는 transfer가 void 반환!)
     □ 프록시 패턴 여부 → 구현체 주소 확인
     □ 소스코드 Verified 여부 (Etherscan)

  2. 보안 검토:
     □ 관리자 민팅 권한 (무한 발행 가능?)
     □ Pause 기능 (거래 중단 가능?)
     □ 블랙리스트 기능 (특정 주소 차단?)
     □ 수수료 토큰 여부 (전송 시 일부 차감?)
     □ Rebase 토큰 여부 (잔액이 자동 변경?)

  3. 기술 구현:
     □ 입금 감지 이벤트 리스너 설정
     □ 출금 Tx 구성 로직
     □ decimals 변환 로직
     □ 잔액 조회 로직
     □ DB 스키마에 토큰 등록

[비표준 토큰 처리]

  USDT (Tether):
    문제: transfer()가 bool을 반환하지 않음 (void)
    → 일반적인 ERC-20 ABI로 호출하면 실패할 수 있음
    → SafeERC20 래퍼 사용 또는 low-level call 후 반환값 처리

  Fee-on-Transfer 토큰:
    문제: transfer(100) 했는데 받는 쪽은 98만 받음 (2% 수수료)
    → 전송 전후 balanceOf 차이로 실제 수령액 계산 필요

  Rebase 토큰 (stETH 등):
    문제: 보유량이 시간에 따라 자동 변경 (스테이킹 보상 반영)
    → DB 잔액이 자동으로 맞지 않음
    → 주기적 잔액 동기화 또는 shares 기반 관리

  → "ERC-20 표준을 따른다"고 해서 다 같지 않다!
  → 신규 토큰 상장 시 반드시 실제 컨트랙트 코드 확인
```

---

## 헷갈렸던 포인트

### Q1: approve(MAX_UINT256)은 왜 위험한가?

```
[무한 승인의 위험성]

  approve(spender, type(uint256).max)
  → "이 컨트랙트(spender)가 내 토큰을 무제한으로 사용 가능"

  정상적일 때:
  → 매번 approve 안 해도 됨 → 편리

  spender 컨트랙트가 해킹당했을 때:
  → 공격자가 내 모든 토큰을 가져갈 수 있음
  → revoke하기 전까지 무방비

  실제 피해 사례:
  - 다수의 DeFi 프로토콜 해킹 시 무한 승인된 사용자 피해
  - Badger DAO (2021, $120M) — 프론트엔드 해킹 → 무한 승인 유도

  방어:
  1. 필요한 금액만 approve (exact amount)
  2. 사용 후 approve(spender, 0)으로 해제
  3. ERC-2612 permit 사용 (deadline 설정 가능)
  4. 서비스 측: 백오피스에서 approve 현황 모니터링
```

### Q2: ERC-721의 tokenId는 어떻게 관리하나?

```
[tokenId 전략]

  순차 증가:
    tokenId = 0, 1, 2, 3 ...
    장점: 단순, 총 발행량 파악 쉬움
    단점: 다음 tokenId 예측 가능 → 프론트러닝 가능

  랜덤/해시 기반:
    tokenId = keccak256(creator, timestamp, nonce)
    장점: 예측 불가
    단점: 총 발행량 추적 어려움

  외부 ID 매핑:
    tokenId = DB의 item_id
    장점: 오프체인 데이터와 1:1 매핑 간편
    단점: DB 구조에 종속

  실무 권장: 순차 증가 + _safeMint
  → OpenZeppelin의 Counters 또는 자체 증가 변수 사용
```

---

## 참고 자료

| 자료 | 설명 |
|------|------|
| [EIP-20: Token Standard](https://eips.ethereum.org/EIPS/eip-20) | ERC-20 공식 스펙 |
| [EIP-721: Non-Fungible Token](https://eips.ethereum.org/EIPS/eip-721) | ERC-721 공식 스펙 |
| [EIP-1155: Multi Token Standard](https://eips.ethereum.org/EIPS/eip-1155) | ERC-1155 공식 스펙 |
| [EIP-4337: Account Abstraction](https://eips.ethereum.org/EIPS/eip-4337) | ERC-4337 공식 스펙 |
| [EIP-2612: Permit Extension](https://eips.ethereum.org/EIPS/eip-2612) | ERC-20 Permit 확장 스펙 |
| [OpenZeppelin Contracts](https://docs.openzeppelin.com/contracts/) | ERC 표준 레퍼런스 구현 |
| [eth-infinitism/account-abstraction](https://github.com/eth-infinitism/account-abstraction) | ERC-4337 레퍼런스 구현 |
