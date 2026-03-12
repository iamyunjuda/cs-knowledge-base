---
title: "키 관리 및 보안 시스템 — KMS, HSM, MPC, 서명 아키텍처"
parent: Blockchain / Web3
nav_order: 8
---

# 키 관리 및 보안 시스템 — KMS, HSM, MPC, 서명 아키텍처

## 핵심 정리

### 1. 블록체인에서 키 관리가 중요한 이유

```
[Web2 vs Web3 인증의 근본적 차이]

  Web2:
    비밀번호 유출 → 비밀번호 변경으로 복구
    DB 해킹 → 서비스 제공자가 계정 복구
    → "서비스 제공자"가 최후의 보루

  Web3:
    개인키 유출 → 자산 전부 탈취, 복구 불가
    서버 키 유출 → 서비스 지갑의 모든 자산 탈취
    → "개인키"가 곧 모든 것. 분실 = 영구 손실

[서버 사이드 키 관리가 필요한 이유]

  거래소/서비스에서 자동으로 수행해야 하는 작업:
  - 사용자 입금 주소 생성
  - 출금 트랜잭션 서명 및 전송
  - 토큰 전송, NFT 민팅
  - 가스비 충전 (Hot Wallet → 개별 주소)
  - 스마트 컨트랙트 관리자 기능 호출

  → 서버가 개인키를 보유하고 자동 서명해야 함
  → 키 보안이 서비스의 생사를 결정
```

---

### 2. 키 저장 방식의 스펙트럼

```
[보안 수준별 키 저장 방식]

  ❌ 최악 ──────────────────────────────────────── ✅ 최선

  소스코드     환경변수     암호화 파일     Vault     KMS/HSM     MPC
  하드코딩     (.env)     (AES-256)     (중앙관리)  (하드웨어)   (키 분산)

  Git에       서버 메모리   디스크에        접근제어   키가 HSM    키 자체가
  개인키 노출  에 평문 존재  암호화 저장     감사로그   밖으로      존재하지
                                        자동 순환   안 나옴     않음
```

---

### 3. HSM (Hardware Security Module)

```
[HSM = 암호화 키를 물리적 하드웨어 내부에서만 처리하는 전용 장비]

  핵심 원칙: "키는 HSM 밖으로 절대 나오지 않는다"

  ┌───────────────────────────────────┐
  │         서버 (Application)         │
  │                                    │
  │  "이 데이터에 서명해 줘"             │
  │         │                          │
  └─────────┼──────────────────────────┘
            │ (PKCS#11 / API)
            ▼
  ┌───────────────────────────────────┐
  │         HSM 장비                   │
  │  ┌──────────────────────────┐     │
  │  │ Private Key (절대 외부    │     │
  │  │ 노출 불가, 물리적 보호)   │     │
  │  │                          │     │
  │  │ 서명 연산 수행            │     │
  │  └──────────────────────────┘     │
  │  → 서명 결과만 반환                │
  │  → 키 자체는 추출 불가             │
  │  → 탬퍼 감지 시 키 자동 파괴       │
  └───────────────────────────────────┘

[HSM의 물리적 보안]

  FIPS 140-2 Level 3/4 인증:
  - 물리적 탬퍼 감지 (분해 시도 시 키 자동 파괴)
  - 온도, 전압 이상 감지
  - 엑스레이, 프로빙 방어
  - 독립적 난수 생성기 (TRNG)

  제품 예시:
  - Thales Luna Network HSM
  - nCipher nShield
  - Yubico YubiHSM (소형, 개발용)
```

---

### 4. KMS (Key Management Service)

```
[KMS = 클라우드 환경에서 HSM을 서비스로 제공]

  본질적으로 "클라우드 호스팅 HSM + 관리 인터페이스"

[AWS KMS 동작 흐름]

  1. 키 생성
     aws kms create-key --key-usage SIGN_VERIFY \
                        --key-spec ECC_SECG_P256K1  # secp256k1 (이더리움용)

  2. 서명 요청
     서버 → AWS KMS API → HSM 내부에서 서명 → 서명 결과 반환

     // SDK 예시
     const { KMSClient, SignCommand } = require("@aws-sdk/client-kms");

     const command = new SignCommand({
       KeyId: "arn:aws:kms:ap-northeast-2:123:key/abc-def",
       Message: txHash,           // 서명할 트랜잭션 해시
       MessageType: "DIGEST",
       SigningAlgorithm: "ECDSA_SHA_256"
     });

     const response = await kmsClient.send(command);
     // response.Signature → DER 인코딩된 서명

  3. 서명을 이더리움 Tx에 적용
     DER → {r, s, v} 변환 → RLP 인코딩 → 전송

[GCP Cloud KMS]

  비슷한 구조, API만 다름:
  - HSM 보호 수준 선택 가능 (SOFTWARE / HSM)
  - secp256k1 지원
  - IAM으로 접근 제어

[AWS KMS vs GCP Cloud KMS]

  ┌──────────────┬─────────────────┬─────────────────┐
  │              │ AWS KMS         │ GCP Cloud KMS   │
  ├──────────────┼─────────────────┼─────────────────┤
  │ secp256k1    │ 지원            │ 지원             │
  │ HSM 보호     │ 기본 제공       │ 보호 수준 선택   │
  │ 자동 키 순환  │ 대칭키만 자동   │ 대칭키만 자동    │
  │ 감사 로그     │ CloudTrail      │ Cloud Audit Log │
  │ 비용         │ $1/key/월       │ 유사             │
  │ 리전 격리     │ 리전별 키 격리  │ 리전별 키 격리   │
  └──────────────┴─────────────────┴─────────────────┘

[KMS의 한계]

  1. 단일 장애점(SPOF): 클라우드 제공자에 의존
     → AWS 장애 시 서명 불가 → 폴백 전략 필요

  2. 응답 지연: 네트워크 호출 필요 (~50~200ms)
     → 대량 서명 시 병목 → 배치 서명 또는 사전 서명

  3. 벤더 종속: AWS KMS ↔ GCP KMS 이전 불가 (키 추출 불가)
     → 멀티 클라우드 전략 시 주의

  4. 비용: 서명 API 호출당 과금
     → 대량 Tx 서비스에서 비용 이슈
```

---

### 5. MPC (Multi-Party Computation)

```
[MPC = 개인키를 여러 조각으로 나눠 보관하고, 서명 시 조각들이 협력]

  핵심: "완전한 개인키가 어디에도 존재하지 않는다"

  ┌────────────────────────────────────────┐
  │        MPC 서명 과정                    │
  │                                        │
  │  Party A (키 조각 1)  → ─┐             │
  │  Party B (키 조각 2)  → ─┤ MPC 프로토콜 │
  │  Party C (키 조각 3)  → ─┘     │       │
  │                               ▼       │
  │                          유효한 서명    │
  │                                        │
  │  * 각 Party는 자기 조각만 알고,         │
  │    다른 Party의 조각은 모름             │
  │  * 서명 과정에서도 완전한 키가           │
  │    한 곳에 모이지 않음                  │
  └────────────────────────────────────────┘

[MPC vs 멀티시그(Multisig)]

  ┌──────────────┬─────────────────────┬─────────────────────┐
  │              │ MPC                 │ Multisig            │
  ├──────────────┼─────────────────────┼─────────────────────┤
  │ 키 구조      │ 키 조각 분산         │ 독립적 키 여러 개    │
  │ 서명 결과     │ 일반 서명 1개       │ 서명 여러 개         │
  │ 온체인 비용   │ 일반 Tx와 동일      │ 서명 수만큼 가스 증가 │
  │ 체인 호환     │ 모든 체인 호환      │ 체인별 지원 필요     │
  │ 프라이버시    │ 외부에서 MPC 여부   │ 온체인에서 멀티시그   │
  │              │ 알 수 없음          │ 임이 드러남          │
  │ 키 교체      │ 키 조각만 재분배     │ 새 키 생성+자산 이동  │
  │ 적용 예      │ Fireblocks, Dfns    │ Gnosis Safe         │
  └──────────────┴─────────────────────┴─────────────────────┘

[TSS (Threshold Signature Scheme)]

  MPC의 구체적 구현 방식:
  t-of-n: n개 조각 중 t개 이상 모이면 서명 가능

  예: 3-of-5 TSS
    5명이 키 조각 보유
    3명 이상 동의 시 서명 생성
    1~2명 탈퇴/해킹되어도 서명 가능

  DKG (Distributed Key Generation):
    처음에 키 조각을 생성하는 과정
    → 중앙 관리자 없이 각 Party가 자신의 조각을 생성
    → 완전한 키가 한 번도 한 곳에 모이지 않음

[MPC 서비스 제공자]

  Fireblocks:
    - 기관용 MPC 지갑 (거래소, 펀드 등)
    - 정책 엔진: 금액/시간/승인자 규칙 설정
    - SGX(Intel) + MPC 하이브리드

  Dfns:
    - API-first MPC 지갑 서비스
    - 개발자 친화적
    - Passkey 기반 인증 지원

  Coinbase WaaS (Wallet as a Service):
    - Coinbase의 MPC 지갑 인프라
    - REST API로 키 생성/서명
    - 규제 준수 내장
```

---

### 6. Hot/Cold Wallet 아키텍처

```
[계층형 지갑 구조]

  ┌─────────────────────────────────────────────────────┐
  │                    Cold Storage                      │
  │  ┌─────────────────────────────────────────────┐    │
  │  │ 전체 자산의 95%                               │    │
  │  │ HSM + Air-gapped 환경                        │    │
  │  │ 멀티시그 또는 MPC (3-of-5)                    │    │
  │  │ 수동 승인 (관리자 N명 동의 필요)               │    │
  │  └─────────────────────┬───────────────────────┘    │
  │                        │ 수동 충전 (일일 1~2회)       │
  └────────────────────────┼────────────────────────────┘
                           ▼
  ┌─────────────────────────────────────────────────────┐
  │                    Warm Wallet                       │
  │  ┌─────────────────────────────────────────────┐    │
  │  │ 일일 처리량의 3~5배                           │    │
  │  │ KMS 보호                                     │    │
  │  │ 자동 승인 (금액 한도 내)                       │    │
  │  │ Hot Wallet 충전 전용                          │    │
  │  └─────────────────────┬───────────────────────┘    │
  │                        │ 자동 충전 (임계값 기반)       │
  └────────────────────────┼────────────────────────────┘
                           ▼
  ┌─────────────────────────────────────────────────────┐
  │                    Hot Wallets (풀)                   │
  │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐              │
  │  │ HW-1 │ │ HW-2 │ │ HW-3 │ │ HW-4 │              │
  │  │ 입금  │ │ 출금  │ │ 민팅  │ │ 가스  │              │
  │  └──────┘ └──────┘ └──────┘ └──────┘              │
  │  서버에서 자동 서명                                   │
  │  소액만 보유 (도난 시 손실 최소화)                     │
  │  각 지갑별 일일 한도 설정                             │
  └─────────────────────────────────────────────────────┘

[Hot Wallet 보안 규칙]

  1. 용도 분리: 입금 수집용, 출금용, 가스비 충전용 등
  2. 잔액 최소화: 24시간 예상 처리량의 1~2배만 보유
  3. 일일 한도: 단일 Tx 한도 + 일일 총량 한도
  4. 자동 알림: 한도 초과, 잔액 부족, 비정상 패턴 감지
  5. 키 순환: 주기적으로 새 주소 생성 + 자산 이동

[잔액 관리 자동화]

  async function autoRefillHotWallet(hotWallet) {
    const balance = await getBalance(hotWallet.address);
    const threshold = hotWallet.minBalance;

    if (balance < threshold) {
      const refillAmount = hotWallet.targetBalance - balance;

      // Warm Wallet에서 충전
      await requestRefill({
        from: warmWallet,
        to: hotWallet.address,
        amount: refillAmount,
        // 자동 승인 (한도 내)
      });

      alert(`Hot Wallet ${hotWallet.name} 충전: ${refillAmount} ETH`);
    }
  }

  // 5분마다 체크
  cron.schedule('*/5 * * * *', checkAllHotWallets);
```

---

### 7. 서명 아키텍처 설계

```
[트랜잭션 서명 파이프라인]

  ┌──────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────┐
  │ 서비스    │ →  │ Tx Builder   │ →  │ Policy       │ →  │ Signer   │
  │ (출금요청)│    │ (Tx 구성)     │    │ Engine       │    │ (서명)    │
  └──────────┘    └──────────────┘    │ (정책 검증)   │    └──────────┘
                                      └──────────────┘

  1. Tx Builder:
     - Nonce 할당
     - Gas 추정
     - 데이터 인코딩 (contract call 등)

  2. Policy Engine (핵심):
     - 단일 Tx 금액 한도 검증
     - 일일 총 출금 한도 검증
     - 화이트리스트 주소 검증
     - 속도 제한 (시간당 Tx 수)
     - 비정상 패턴 감지 (갑자기 대량 출금 등)
     - 관리자 수동 승인 필요 여부 판단

  3. Signer:
     - KMS/HSM/MPC에 서명 요청
     - DER → {r, s, v} 변환
     - 서명 검증 (의도한 주소에서 서명됐는지)

[정책 엔진 규칙 예시]

  정책 레벨:
  Level 1 (자동 승인): 단일 Tx < $1,000 && 일일 총량 < $50,000
  Level 2 (1인 승인): 단일 Tx < $10,000
  Level 3 (2인 승인): 단일 Tx < $100,000
  Level 4 (3인 승인): 단일 Tx >= $100,000

  추가 규칙:
  - 화이트리스트에 없는 주소 → Level 3 이상
  - 야간(00:00~06:00) 출금 → 레벨 +1
  - 동일 주소 10분 내 중복 요청 → 자동 차단
  - 가스비가 평소의 5배 이상 → 관리자 알림
```

---

### 8. 키 순환 (Key Rotation)

```
[블록체인 키 순환의 특수성]

  일반 시스템: 키 교체 → 새 키로 암호화/복호화 → 끝
  블록체인: 키 교체 = 주소 변경 → 자산도 이동해야 함!

  키 순환 절차:
  1. 새 키(주소) 생성
  2. 스마트 컨트랙트 관리자 변경 (필요시)
  3. 구 지갑 → 신 지갑으로 자산 이동
  4. 구 지갑 주소 수신 차단
  5. 관련 시스템 설정 업데이트
  6. 구 키 안전 보관 (일정 기간 후 폐기)

  → Web2의 키 교체보다 훨씬 복잡하고 비용 발생 (가스비)
  → 대량 토큰 보유 시 이동 비용 상당

[MPC의 키 순환 장점]

  MPC에서는 키 자체를 바꾸지 않고 "조각만 재분배":
  - 기존 주소(공개키) 유지
  - 키 조각만 새로 생성하여 분배
  - 이전 조각은 무효화
  - 자산 이동 불필요 → 가스비 절약
  → 이것이 MPC가 기관에서 선호되는 핵심 이유
```

---

### 9. 보안 감사 및 사고 대응

```
[보안 감사 항목]

  1. 키 접근 제어
     - 누가 서명 API를 호출할 수 있는가?
     - IAM 정책이 최소 권한 원칙을 따르는가?
     - 서비스 계정 키는 순환되고 있는가?

  2. 감사 로그
     - 모든 서명 요청/결과가 기록되는가?
     - 로그가 변조 불가능한가? (CloudTrail, Immutable Storage)
     - 비정상 패턴 알림이 설정되어 있는가?

  3. 네트워크 보안
     - KMS/HSM 접근이 VPC 내부로 제한되어 있는가?
     - TLS 통신이 강제되는가?
     - 서명 서버가 인터넷에 직접 노출되어 있지 않은가?

  4. 재해 복구
     - 키 백업이 존재하는가?
     - 백업은 지리적으로 분산되어 있는가?
     - 복구 절차가 문서화되고 테스트되었는가?

[실제 보안 사고 사례]

  2022 Ronin Bridge ($625M):
    원인: Validator 키 5개 중 4개가 단일 조직에 보관
    교훈: 키 분산의 중요성, 진정한 탈중앙화 필요

  2023 Atomic Wallet ($100M):
    원인: 키 암호화 방식 취약점
    교훈: 자체 구현보다 검증된 HSM/KMS 사용

  2022 Slope Wallet (Solana, $8M):
    원인: 시드 구문이 Sentry 로그 서버에 평문 기록
    교훈: 민감 데이터 로깅 금지, 시크릿 스캐닝 도구 도입

[사고 대응 절차]

  1. 탐지: 비정상 출금 패턴 알림
  2. 격리: 해당 Hot Wallet 서명 즉시 차단
  3. 분석: 어떤 키가 어떻게 유출됐는지 파악
  4. 차단: 가능하면 컨트랙트 일시정지 (pause)
  5. 이동: 영향받지 않은 키의 자산을 새 주소로 이동
  6. 통보: 사용자/규제기관 통보
  7. 포렌식: 상세 원인 분석 및 재발 방지
```

---

## 헷갈렸던 포인트

### Q1: KMS에서 이더리움 서명을 하면 주소는 어떻게 알아내나?

```
[KMS 서명 → 이더리움 주소 도출 과정]

  문제: KMS는 공개키만 제공하고, 이더리움 주소는 직접 안 줌

  해결:
  1. KMS에서 공개키 조회 (GetPublicKey API)
  2. 공개키를 비압축 형태로 변환 (65 bytes, 0x04 prefix)
  3. 0x04 prefix 제거 (64 bytes)
  4. Keccak-256 해싱
  5. 마지막 20 bytes = 이더리움 주소

  const { KMSClient, GetPublicKeyCommand } = require("@aws-sdk/client-kms");

  async function getEthereumAddress(keyId) {
    const response = await kmsClient.send(new GetPublicKeyCommand({ KeyId: keyId }));
    const publicKey = response.PublicKey;  // DER encoded

    // DER → uncompressed public key (64 bytes, 04 prefix 제거)
    const uncompressedKey = extractUncompressedKey(publicKey);

    // Keccak-256 → 마지막 20 bytes
    const hash = keccak256(uncompressedKey);
    const address = "0x" + hash.slice(-40);

    return address;
  }
```

### Q2: MPC와 Shamir's Secret Sharing의 차이는?

```
[Shamir's Secret Sharing (SSS)]
  1. 키를 생성한 후 조각으로 분배
  2. 서명 시 조각을 모아서 키를 복원한 후 서명
  3. 복원 순간 완전한 키가 메모리에 존재 → 취약점!

[MPC (TSS)]
  1. 키 자체를 생성하지 않고, 각 파티가 조각만 생성 (DKG)
  2. 서명 시 조각이 협력하여 서명을 생성 (키 복원 없이)
  3. 전체 과정에서 완전한 키가 한 번도 존재하지 않음

  핵심 차이: SSS는 복원 시점에 키가 노출될 수 있지만,
           MPC는 키가 한 번도 완전한 형태로 존재하지 않음
```

### Q3: 소규모 서비스에서도 HSM/MPC가 필요한가?

```
[단계적 보안 전략]

  초기 (MVP / 소규모):
    AWS KMS 사용 (비용 대비 보안 효과 최고)
    Hot Wallet 1~2개
    일일 한도 설정
    → 비용: $10~50/월

  성장기 (MAU 10만+):
    KMS + Policy Engine
    Hot/Warm/Cold 3계층
    모니터링 대시보드
    → 비용: $100~500/월

  성숙기 (거래소급):
    MPC (Fireblocks 등)
    전문 보안팀
    정기 감사 (연 1~2회)
    → 비용: $5,000+/월

  핵심: 관리 자산 규모에 비례하여 보안 투자
```

---

## 참고 자료

| 자료 | 설명 |
|------|------|
| [AWS KMS — ECDSA Signing](https://docs.aws.amazon.com/kms/latest/developerguide/asymmetric-key-specs.html) | AWS KMS 비대칭 키 사양 및 서명 가이드 |
| [Fireblocks Architecture](https://www.fireblocks.com/platforms/mpc-wallet/) | Fireblocks MPC 지갑 아키텍처 소개 |
| [Ethereum Key Management Best Practices](https://ethereum.org/en/developers/docs/accounts/) | 이더리움 공식 계정/키 관리 문서 |
| [GG20 MPC Protocol](https://eprint.iacr.org/2020/540.pdf) | Gennaro-Goldfeder TSS 프로토콜 논문 |
| [HashiCorp Vault — Ethereum Plugin](https://github.com/immutability-io/vault-ethereum) | Vault 기반 이더리움 키 관리 플러그인 |
| [OWASP Cryptographic Storage](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html) | 암호화 저장소 보안 가이드 |
