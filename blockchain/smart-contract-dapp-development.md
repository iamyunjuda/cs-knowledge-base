---
title: "스마트 컨트랙트 & dApp 개발 — 개발 라이프사이클, 테스트, 보안, 배포"
parent: Blockchain / Web3
nav_order: 9
---

# 스마트 컨트랙트 & dApp 개발 — 개발 라이프사이클, 테스트, 보안, 배포

## 핵심 정리

### 1. 스마트 컨트랙트 개발 라이프사이클

```
[전체 개발 흐름]

  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
  │ 설계      │ → │ 구현      │ → │ 테스트    │ → │ 감사      │
  │ 요구사항  │   │ Solidity  │   │ 유닛/통합 │   │ 보안 감사 │
  └──────────┘   └──────────┘   └──────────┘   └──────────┘
                                                     │
  ┌──────────┐   ┌──────────┐   ┌──────────┐        │
  │ 운영      │ ← │ 모니터링  │ ← │ 배포      │ ←─────┘
  │ 업그레이드│   │ 이벤트    │   │ 메인넷    │
  └──────────┘   └──────────┘   └──────────┘

[Web2와의 차이]

  ┌──────────────┬─────────────────────┬─────────────────────┐
  │              │ Web2                │ Web3                │
  ├──────────────┼─────────────────────┼─────────────────────┤
  │ 배포 후 수정  │ 핫픽스 즉시 배포    │ 불가능 (불변성)       │
  │ 버그 대응     │ 서버 롤백           │ 새 컨트랙트 배포      │
  │ 테스트 비용   │ 서버 리소스 수준    │ 가스비 (실제 비용)    │
  │ DB 마이그레이션│ ALTER TABLE        │ 새 컨트랙트 + 데이터 │
  │              │                     │ 마이그레이션          │
  │ 보안 영향     │ 데이터 유출 가능    │ 자산 탈취 (비가역)    │
  └──────────────┴─────────────────────┴─────────────────────┘

  핵심: "배포하면 되돌릴 수 없다"
  → 테스트와 감사가 Web2보다 훨씬 중요
```

---

### 2. 개발 도구 — Hardhat vs Foundry

```
[Hardhat — JavaScript/TypeScript 기반]

  장점:
  - JS/TS 생태계 활용 (ethers.js, TypeChain)
  - 풍부한 플러그인 (coverage, gas-reporter, upgrades)
  - 로컬 네트워크 내장 (Hardhat Network)
  - 디버깅 지원 (console.log in Solidity!)

  단점:
  - 테스트 속도 느림 (JS 런타임 오버헤드)
  - Solidity 네이티브 테스트 불가

  프로젝트 구조:
  my-project/
  ├── contracts/        # Solidity 소스
  │   ├── MyToken.sol
  │   └── interfaces/
  ├── test/            # 테스트 (JS/TS)
  │   └── MyToken.test.ts
  ├── scripts/         # 배포 스크립트
  │   └── deploy.ts
  ├── hardhat.config.ts
  └── package.json

[Foundry — Rust 기반, Solidity 네이티브 테스트]

  장점:
  - 극한의 테스트 속도 (Rust 바이너리)
  - Solidity로 테스트 작성 → 동일 언어
  - Fuzz Testing 내장
  - forge test, forge script 등 CLI 도구
  - Gas 스냅샷, 최적화 분석

  단점:
  - JS/TS 플러그인 생태계 부재
  - 프론트엔드 통합은 별도 작업

  프로젝트 구조:
  my-project/
  ├── src/             # Solidity 소스
  │   └── MyToken.sol
  ├── test/            # Solidity 테스트
  │   └── MyToken.t.sol
  ├── script/          # 배포 스크립트 (Solidity)
  │   └── Deploy.s.sol
  ├── lib/             # 의존성 (git submodule)
  │   └── forge-std/
  └── foundry.toml

[2025~2026 업계 트렌드]

  신규 프로젝트: Foundry 선호 (속도, Fuzz Testing)
  기존 프로젝트: Hardhat 유지 (마이그레이션 비용)
  실무: Foundry(컨트랙트 테스트) + Hardhat(배포 스크립트) 혼용도 흔함
```

---

### 3. 테스팅 전략

```
[테스트 피라미드]

  ┌───────────────┐
  │  E2E 테스트    │  ← 테스트넷 배포 후 실제 Tx로 검증
  │  (적게)        │
  ├───────────────┤
  │  통합 테스트    │  ← 컨트랙트 간 상호작용 검증
  │  (중간)        │
  ├───────────────┤
  │  유닛 테스트    │  ← 개별 함수 단위 검증
  │  (많이)        │
  └───────────────┘

[유닛 테스트 — Foundry 예시]

  // test/MyToken.t.sol
  contract MyTokenTest is Test {
    MyToken token;
    address alice = makeAddr("alice");
    address bob = makeAddr("bob");

    function setUp() public {
      token = new MyToken("Test", "TST", 1000e18);
      token.transfer(alice, 100e18);
    }

    function test_Transfer() public {
      vm.prank(alice);  // alice가 호출한 것으로 설정
      token.transfer(bob, 50e18);

      assertEq(token.balanceOf(alice), 50e18);
      assertEq(token.balanceOf(bob), 50e18);
    }

    function test_RevertWhen_InsufficientBalance() public {
      vm.prank(alice);
      vm.expectRevert("Insufficient balance");
      token.transfer(bob, 200e18);  // 잔액 초과
    }
  }

[Fuzz Testing — 랜덤 입력으로 버그 찾기]

  function testFuzz_Transfer(uint256 amount) public {
    // amount를 랜덤으로 생성하여 반복 테스트
    amount = bound(amount, 0, token.balanceOf(alice));

    vm.prank(alice);
    token.transfer(bob, amount);

    assertEq(token.balanceOf(alice), 100e18 - amount);
    assertEq(token.balanceOf(bob), amount);
  }

  // Foundry가 수백~수천 번 랜덤 입력으로 테스트
  // → 예상치 못한 엣지 케이스 발견

[Invariant Testing — 불변 조건 검증]

  function invariant_TotalSupplyConstant() public {
    // 어떤 작업을 해도 총 공급량은 변하지 않아야 함
    assertEq(token.totalSupply(), 1000e18);
  }

  // Foundry가 랜덤 함수 호출 시퀀스를 생성하여
  // 불변 조건이 깨지는 경우를 탐색

[Fork Testing — 메인넷 상태에서 테스트]

  // 실제 메인넷 데이터를 포크하여 테스트
  function test_SwapOnUniswap() public {
    // 메인넷 Uniswap V3 Router 주소 사용
    vm.createSelectFork("mainnet", 19000000);  // 특정 블록에서 포크

    // 실제 유동성, 실제 가격으로 스왑 테스트
    router.exactInputSingle(...);
  }

  // forge test --fork-url https://eth-mainnet.alchemyapi.io/v2/YOUR_KEY
```

---

### 4. 보안 — 주요 취약점과 방어

```
[1. Reentrancy (재진입 공격)]

  가장 유명한 스마트 컨트랙트 취약점
  2016 The DAO 해킹 ($60M) — 이더리움 하드포크의 원인

  취약 코드:
  function withdraw(uint amount) external {
    require(balances[msg.sender] >= amount);
    (bool success, ) = msg.sender.call{value: amount}("");  // ← 외부 호출
    require(success);
    balances[msg.sender] -= amount;  // ← 상태 변경이 외부 호출 뒤에!
  }

  공격: msg.sender가 컨트랙트 → receive()에서 다시 withdraw() 호출
  → 잔액 차감 전에 반복 출금 → 자금 탈취

  방어 — CEI 패턴 (Checks-Effects-Interactions):
  function withdraw(uint amount) external {
    require(balances[msg.sender] >= amount);  // Checks
    balances[msg.sender] -= amount;            // Effects (상태 변경 먼저!)
    (bool success, ) = msg.sender.call{value: amount}("");  // Interactions
    require(success);
  }

  + ReentrancyGuard (OpenZeppelin):
  function withdraw(uint amount) external nonReentrant {
    // nonReentrant 수정자가 재진입 차단
  }

[2. Flash Loan 공격]

  Flash Loan: 같은 Tx 내에서 빌리고 갚으면 무담보 대출 가능
  → 대량 자금으로 가격 조작 후 이익 실현

  공격 시나리오:
  1. Flash Loan으로 $10M 빌림
  2. DEX A에서 토큰 대량 매수 → 가격 상승
  3. DEX B에서 올라간 가격으로 담보 대출
  4. 원래 Flash Loan 상환
  5. 차익 탈취

  방어:
  - TWAP(Time-Weighted Average Price) 오라클 사용
  - Chainlink 같은 외부 오라클로 가격 검증
  - 단일 블록 내 가격 사용 금지

[3. Access Control (접근 제어)]

  문제: 관리자 함수에 접근 제어가 없으면?

  // ❌ 위험: 누구나 민팅 가능
  function mint(address to, uint amount) external {
    _mint(to, amount);
  }

  // ✅ 안전: 소유자만 민팅 가능
  function mint(address to, uint amount) external onlyOwner {
    _mint(to, amount);
  }

  OpenZeppelin AccessControl:
  - 역할 기반 접근 제어 (Role-Based Access Control)
  - DEFAULT_ADMIN_ROLE, MINTER_ROLE, PAUSER_ROLE 등
  - 관리자 키 탈취 시 영향 최소화

[4. Integer Overflow/Underflow]

  Solidity 0.8.0 이전:
  → uint8(255) + 1 = 0 (오버플로!)
  → uint8(0) - 1 = 255 (언더플로!)

  Solidity 0.8.0 이후:
  → 자동으로 revert (내장 체크)
  → unchecked {} 블록 안에서만 비검증 연산 가능

  주의: assembly(인라인 어셈블리)에서는 여전히 체크 안 됨

[보안 감사 도구]

  정적 분석:
  - Slither: Python 기반, 패턴 매칭으로 취약점 탐지
  - Mythril: 심볼릭 실행 기반 분석
  - Aderyn: Rust 기반, Cyfrin 개발

  동적 분석:
  - Echidna: Fuzz Testing 도구
  - Foundry Fuzz/Invariant: 내장 퍼징

  수동 감사:
  - OpenZeppelin Audits
  - Trail of Bits
  - Cyfrin
  → 프로덕션 배포 전 필수 (비용: $10K~$100K+)
```

---

### 5. 배포 전략

```
[테스트넷 → 메인넷 배포 흐름]

  1. 로컬 테스트 (Hardhat Network / Anvil)
     → 유닛/통합/퍼즈 테스트 통과
     → Gas 사용량 최적화 확인

  2. 테스트넷 배포 (Sepolia / Holesky)
     → 실제 네트워크 환경 검증
     → 프론트엔드/백엔드 통합 테스트
     → Faucet에서 테스트 ETH 확보

  3. 보안 감사
     → 외부 감사 업체 의뢰
     → 발견된 이슈 수정 → 재감사

  4. 메인넷 배포
     → 최종 검토 후 배포
     → Etherscan에서 소스코드 Verify
     → 모니터링 시작

[Proxy 패턴 — 업그레이드 가능한 컨트랙트]

  문제: 스마트 컨트랙트는 배포 후 수정 불가
  해결: Proxy 패턴으로 로직만 교체

  ┌──────────────┐     ┌──────────────────┐
  │   Proxy      │ ──→ │ Implementation V1 │  (현재 로직)
  │   (불변)      │     └──────────────────┘
  │   상태 저장   │
  │   주소 고정   │     ┌──────────────────┐
  └──────────────┘ ──→ │ Implementation V2 │  (업그레이드 후)
                       └──────────────────┘

  사용자는 항상 Proxy 주소로 호출
  → Proxy가 현재 Implementation으로 delegatecall
  → Implementation을 교체하면 로직 업데이트

  주요 패턴:
  - Transparent Proxy: 관리자와 사용자 호출을 분리
  - UUPS: Implementation 안에 업그레이드 로직 포함 (가스 효율적)
  - Beacon Proxy: 여러 Proxy가 하나의 Beacon을 참조

  위험:
  - 스토리지 충돌: V1과 V2의 변수 순서가 다르면 데이터 오염
  - 관리자 키 탈취: 업그레이드 권한 장악 → 악성 로직 주입
  → OpenZeppelin Upgrades 라이브러리로 안전하게 관리

[Etherscan Verification]

  배포 후 반드시 소스코드 검증:
  → 사용자가 컨트랙트 코드를 직접 확인 가능
  → 신뢰도 향상
  → 오픈소스 생태계 기여

  // Hardhat
  npx hardhat verify --network mainnet DEPLOYED_ADDRESS "arg1" "arg2"

  // Foundry
  forge verify-contract DEPLOYED_ADDRESS MyContract --etherscan-api-key KEY
```

---

### 6. dApp 백엔드 아키텍처

```
[dApp = 탈중앙 애플리케이션]

  실무에서 dApp은 순수 탈중앙이 아님!
  대부분 "Web2 백엔드 + Web3 온체인" 하이브리드

  ┌─────────────────────────────────────────────────────┐
  │ Frontend (React/Next.js + wagmi/viem)                │
  │  지갑 연결, Tx 서명 요청, 온체인 데이터 표시          │
  └────────────────────┬────────────────────────────────┘
                       │
  ┌────────────────────▼────────────────────────────────┐
  │ Backend (Spring Boot / Node.js / Go)                 │
  │                                                     │
  │  1. 인덱서: 온체인 이벤트 → DB 저장                   │
  │     → 빠른 조회, 복잡한 쿼리 지원                     │
  │                                                     │
  │  2. 메타데이터 서버: NFT 이미지/속성 제공              │
  │     → tokenURI가 가리키는 JSON 반환                   │
  │                                                     │
  │  3. 릴레이어: 사용자 대신 Tx 전송 (가스비 대납)        │
  │     → ERC-4337 Bundler / meta-transaction             │
  │                                                     │
  │  4. 오프체인 로직: 가격 피드, 매칭, 계산 등            │
  │     → 온체인에서 하기엔 비싸거나 불가능한 로직          │
  │                                                     │
  │  5. 관리 API: 컨트랙트 관리자 기능 호출               │
  │     → pause, unpause, grantRole 등                   │
  └─────────────────────────────────────────────────────┘

[The Graph — 탈중앙 인덱싱]

  온체인 이벤트를 GraphQL로 조회:

  // subgraph.yaml
  dataSources:
    - name: MyToken
      source:
        address: "0x..."
        abi: MyToken
      mapping:
        eventHandlers:
          - event: Transfer(indexed address,indexed address,uint256)
            handler: handleTransfer

  // mapping.ts
  export function handleTransfer(event: Transfer): void {
    let transfer = new TransferEntity(event.transaction.hash.toHex());
    transfer.from = event.params.from;
    transfer.to = event.params.to;
    transfer.value = event.params.value;
    transfer.save();
  }

  // 프론트엔드에서 GraphQL로 조회
  {
    transfers(first: 10, orderBy: value, orderDirection: desc) {
      from
      to
      value
    }
  }

[오프체인 서명 (Meta-Transaction)]

  사용자가 가스비 없이 Tx 실행:
  1. 사용자: 의도에 서명 (오프체인, 가스비 없음)
  2. 릴레이어(서버): 서명을 받아서 실제 Tx 전송 (가스비 부담)
  3. 컨트랙트: 서명 검증 후 사용자 의도 실행

  → ERC-2771 (Trusted Forwarder): 표준 meta-transaction
  → ERC-4337 (Account Abstraction): 더 발전된 형태
```

---

### 7. Clean Code in Solidity

```
[Solidity 코딩 컨벤션]

  NatSpec 주석:
  /// @notice 토큰을 전송합니다
  /// @param to 수신자 주소
  /// @param amount 전송할 양 (decimals 적용)
  /// @return success 전송 성공 여부
  function transfer(address to, uint256 amount) external returns (bool success);

  네이밍:
  - 컨트랙트/인터페이스: PascalCase (MyToken, IERC20)
  - 함수/변수: camelCase (balanceOf, totalSupply)
  - 상수: UPPER_SNAKE_CASE (MAX_SUPPLY, ADMIN_ROLE)
  - private/internal 변수: _prefix (_balances, _owner)

  가스 최적화:
  - storage 읽기 최소화 (로컬 변수에 캐싱)
  - 불필요한 storage 쓰기 제거
  - 짧은 revert 메시지 (Custom Error 사용)
  - unchecked {} 안전한 곳에서 활용

  Custom Error (Solidity 0.8.4+):
  // ❌ 구식: revert("Insufficient balance"); → 가스 비쌈
  // ✅ 최신: error InsufficientBalance(uint256 available, uint256 required);
  //         revert InsufficientBalance(balance, amount); → 가스 절약

[테스트 자동화 CI/CD]

  GitHub Actions 예시:
  name: Smart Contract CI
  on: [push, pull_request]
  jobs:
    test:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: foundry-rs/foundry-toolchain@v1
        - run: forge build
        - run: forge test -vvv
        - run: forge coverage --report summary
        # Slither 정적 분석
        - uses: crytic/slither-action@v0.3.0
```

---

## 헷갈렸던 포인트

### Q1: 스마트 컨트랙트에서 외부 API를 호출할 수 있나?

```
[불가능하다]

  EVM은 결정론적(Deterministic):
  → 모든 노드가 같은 입력에 같은 결과를 내야 함
  → 외부 API 호출 → 노드마다 다른 결과 → 합의 불가

  해결: Oracle (오라클)
  → 외부 데이터를 온체인에 주입하는 미들웨어

  Chainlink (가장 대표적):
  → 탈중앙 오라클 네트워크
  → 가격 피드, 랜덤 넘버(VRF), 외부 API 호출(Functions)
  → 여러 노드가 독립적으로 데이터를 수집 → 합의 → 온체인 제출

  백엔드 역할:
  → 오라클이 제공하지 않는 커스텀 데이터가 필요하면
  → 백엔드가 데이터를 수집하고 서명하여 컨트랙트에 제출
```

### Q2: delegatecall이 왜 위험한가?

```
[delegatecall = 다른 컨트랙트의 코드를 내 컨텍스트에서 실행]

  contract Proxy {
    address implementation;
    uint256 value;  // slot 1

    function _delegate() internal {
      implementation.delegatecall(msg.data);
      // implementation의 코드가 Proxy의 storage를 사용!
    }
  }

  위험 1 — 스토리지 충돌:
    Implementation의 변수 레이아웃이 Proxy와 다르면
    → 잘못된 slot에 데이터 쓰임 → 데이터 손상

  위험 2 — selfdestruct:
    delegatecall 대상이 selfdestruct를 실행하면
    → 호출한 컨트랙트(Proxy)가 파괴됨!

  → Proxy 패턴에서 Implementation은 반드시 검증된 코드만 사용
  → OpenZeppelin의 Upgrades 라이브러리가 스토리지 충돌을 자동 검증
```

### Q3: "런칭된 dApp"이란 어떤 수준을 말하는가?

```
[dApp 런칭의 단계]

  Level 1 — 학습/포트폴리오:
    테스트넷 배포, 기본 기능 구현
    → "Solidity를 할 줄 안다" 수준

  Level 2 — 테스트넷 서비스:
    사용자 테스트, 프론트엔드 연동
    → "풀스택 dApp을 만들어 봤다" 수준

  Level 3 — 메인넷 런칭:
    실제 자산이 오가는 서비스
    보안 감사 완료
    사용자가 실제로 사용 중
    → "프로덕션 dApp 경험이 있다" (채용 공고의 "런칭된 dApp")

  Level 4 — 대규모 운영:
    TVL(Total Value Locked) 보유
    멀티체인 배포
    거버넌스, 토크노믹스
    → DeFi 프로토콜 수준

  채용 공고에서 "실제 런칭된 dApp 서비스에 참여"란?
  → 최소 Level 3 이상
  → 메인넷에 배포되고, 실제 사용자가 Tx를 보내는 서비스
```

---

## 참고 자료

| 자료 | 설명 |
|------|------|
| [Foundry Book](https://book.getfoundry.sh/) | Foundry 공식 문서 |
| [Hardhat Documentation](https://hardhat.org/docs) | Hardhat 공식 문서 |
| [OpenZeppelin Contracts](https://docs.openzeppelin.com/contracts/) | 검증된 스마트 컨트랙트 라이브러리 |
| [Solidity by Example](https://solidity-by-example.org/) | Solidity 코드 예제 모음 |
| [Damn Vulnerable DeFi](https://www.damnvulnerabledefi.xyz/) | 스마트 컨트랙트 보안 CTF |
| [Crytic — Slither](https://github.com/crytic/slither) | Solidity 정적 분석 도구 |
| [The Graph Documentation](https://thegraph.com/docs/) | 탈중앙 인덱싱 프로토콜 문서 |
| [ERC-2771: Meta-Transaction](https://eips.ethereum.org/EIPS/eip-2771) | 메타 트랜잭션 표준 |
