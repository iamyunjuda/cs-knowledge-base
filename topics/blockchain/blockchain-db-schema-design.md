---
title: "블록체인 서비스 DB 스키마 설계 — 트랜잭션 무결성과 정합성"
parent: Blockchain / Web3
nav_order: 3
tags: [DB스키마, 멱등성, Outbox패턴, 이중기장, 잔액원장, Reconciliation]
description: "Tx 테이블 멱등성 키, 지갑/입금 주소 관리, 잔액 원장 이중 기장, Outbox 패턴, Reconciliation 등 블록체인 DB 스키마 설계를 정리합니다."
---

# 블록체인 서비스 DB 스키마 설계 — 트랜잭션 무결성과 정합성

## 핵심 정리

### 1. 블록체인 서비스 DB 설계가 특별한 이유

```
[일반 서비스 vs 블록체인 서비스의 데이터 특성]

  일반 서비스:
    DB에 쓰면 끝. 즉시 확정. ACID 보장.
    → 서버가 유일한 진실의 원천(Source of Truth)

  블록체인 서비스:
    DB + 블록체인 양쪽에 데이터가 존재
    블록체인의 상태가 "진짜"이고, DB는 "캐시/인덱스"
    → 양쪽 정합성을 맞춰야 함

  핵심 도전:
  1. 이중 진실 원천: 온체인 데이터 vs 오프체인 DB
  2. 비동기 확정: Tx 전송 → Pending → Confirmed (시간 차)
  3. 상태 뒤집힘: Reorg로 확정된 데이터가 무효화될 수 있음
  4. 비용 제약: 모든 것을 온체인에 저장할 수 없음 (가스비)
```

---

### 2. 핵심 테이블 — 트랜잭션 관리

```
[transactions 테이블 — 블록체인 Tx 생명주기 관리]

  CREATE TABLE transactions (
    id              BIGSERIAL PRIMARY KEY,
    -- 식별
    request_id      UUID NOT NULL UNIQUE,    -- 멱등성 키 (서비스 요청 ID)
    tx_hash         VARCHAR(66),             -- 0x + 64 hex chars (전송 후 할당)
    chain_id        INTEGER NOT NULL,        -- 1=Ethereum, 137=Polygon ...

    -- Tx 내용
    from_address    VARCHAR(42) NOT NULL,
    to_address      VARCHAR(42) NOT NULL,
    value_wei       NUMERIC(78, 0),          -- ETH 전송량 (wei)
    data            TEXT,                     -- contract call data (hex)
    tx_type         VARCHAR(20) NOT NULL,     -- TRANSFER, MINT, SWAP, APPROVE ...

    -- Nonce & Gas
    nonce           INTEGER,
    gas_limit       BIGINT,
    max_fee_per_gas BIGINT,                  -- EIP-1559
    max_priority_fee BIGINT,
    gas_used        BIGINT,                  -- 실제 사용량 (확정 후)
    effective_gas_price BIGINT,              -- 실제 가스 가격 (확정 후)

    -- 상태
    status          VARCHAR(20) NOT NULL DEFAULT 'CREATED',
    -- CREATED → SUBMITTED → PENDING → CONFIRMED / REVERTED / LOST / REORGED

    -- 블록 정보 (확정 후)
    block_number    BIGINT,
    block_hash      VARCHAR(66),
    block_timestamp TIMESTAMP,
    confirmations   INTEGER DEFAULT 0,

    -- 재시도
    retry_count     INTEGER DEFAULT 0,
    replaced_by     BIGINT REFERENCES transactions(id),  -- Speed-up Tx
    replaces        BIGINT REFERENCES transactions(id),  -- 원래 Tx

    -- 감사
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    confirmed_at    TIMESTAMP,

    -- 인덱스
    INDEX idx_tx_status (status),
    INDEX idx_tx_hash (tx_hash),
    INDEX idx_tx_from (from_address, nonce),
    INDEX idx_tx_created (created_at),
    INDEX idx_tx_block (block_number)
  );

  -- 상태 전이 이력
  CREATE TABLE transaction_status_history (
    id              BIGSERIAL PRIMARY KEY,
    transaction_id  BIGINT NOT NULL REFERENCES transactions(id),
    from_status     VARCHAR(20),
    to_status       VARCHAR(20) NOT NULL,
    reason          TEXT,                    -- 상태 변경 사유
    metadata        JSONB,                   -- 추가 정보 (gas price 변경 등)
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),

    INDEX idx_tsh_tx (transaction_id)
  );

[설계 포인트]

  1. request_id (UNIQUE): 멱등성의 핵심
     → 같은 요청을 2번 보내도 Tx가 1개만 생성됨
     → INSERT ... ON CONFLICT (request_id) DO NOTHING

  2. tx_hash는 NULL 허용: CREATED 시점에는 아직 없음
     → SUBMITTED 후 할당

  3. value_wei는 NUMERIC(78, 0): 이더리움 최대값 처리
     → BIGINT 범위 초과 가능 (uint256 = 최대 78자리)

  4. replaced_by / replaces: Speed-up Tx 추적
     → 같은 nonce로 새 Tx를 보낼 때 관계 기록
```

---

### 3. 핵심 테이블 — 지갑 관리

```
[wallets 테이블 — Hot/Warm/Cold Wallet 관리]

  CREATE TABLE wallets (
    id              BIGSERIAL PRIMARY KEY,
    address         VARCHAR(42) NOT NULL,
    chain_id        INTEGER NOT NULL,
    wallet_type     VARCHAR(10) NOT NULL,    -- HOT, WARM, COLD
    wallet_purpose  VARCHAR(20) NOT NULL,    -- WITHDRAW, DEPOSIT, MINT, GAS
    key_reference   VARCHAR(255),            -- KMS ARN / MPC 키 ID
    is_active       BOOLEAN DEFAULT TRUE,

    -- 잔액 (캐시, 온체인이 진실)
    eth_balance_wei NUMERIC(78, 0) DEFAULT 0,
    last_balance_sync TIMESTAMP,

    -- Nonce (캐시, 온체인이 진실)
    local_nonce     INTEGER DEFAULT 0,
    last_nonce_sync TIMESTAMP,

    -- 한도
    daily_limit_wei NUMERIC(78, 0),          -- 일일 한도
    single_tx_limit_wei NUMERIC(78, 0),      -- 단일 Tx 한도
    daily_used_wei  NUMERIC(78, 0) DEFAULT 0,

    -- 메타
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW(),

    UNIQUE (address, chain_id)
  );

[deposit_addresses 테이블 — 사용자별 입금 주소]

  CREATE TABLE deposit_addresses (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT NOT NULL,
    address         VARCHAR(42) NOT NULL,
    chain_id        INTEGER NOT NULL,
    derivation_path VARCHAR(50),             -- m/44'/60'/0'/0/N
    derivation_index INTEGER,                -- N
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),

    UNIQUE (address, chain_id),
    INDEX idx_da_user (user_id)
  );

  -- HD Wallet에서 사용자별 주소를 생성하는 경우:
  -- derivation_path로 언제든 키를 재파생할 수 있음
  -- 주소 자체가 곧 사용자 식별자
```

---

### 4. 핵심 테이블 — 이벤트 인덱싱

```
[indexed_events 테이블 — 온체인 이벤트 오프체인 저장]

  CREATE TABLE indexed_events (
    id              BIGSERIAL PRIMARY KEY,
    -- 유니크 식별: 같은 이벤트 중복 저장 방지 (멱등성)
    event_key       VARCHAR(200) NOT NULL UNIQUE,
    -- format: "{chain_id}:{tx_hash}:{log_index}"

    chain_id        INTEGER NOT NULL,
    contract_address VARCHAR(42) NOT NULL,
    event_name      VARCHAR(100) NOT NULL,   -- Transfer, Approval ...
    tx_hash         VARCHAR(66) NOT NULL,
    log_index       INTEGER NOT NULL,
    block_number    BIGINT NOT NULL,
    block_hash      VARCHAR(66) NOT NULL,

    -- 파싱된 이벤트 데이터
    args            JSONB NOT NULL,          -- {"from": "0x...", "to": "0x...", "value": "1000"}

    -- Reorg 관련
    is_valid        BOOLEAN DEFAULT TRUE,    -- Reorg 시 FALSE로 마킹
    confirmations   INTEGER DEFAULT 0,

    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),

    INDEX idx_ie_block (chain_id, block_number),
    INDEX idx_ie_contract (contract_address, event_name),
    INDEX idx_ie_tx (tx_hash)
  );

[block_tracker 테이블 — 블록 처리 진행 상황]

  CREATE TABLE block_tracker (
    id              BIGSERIAL PRIMARY KEY,
    chain_id        INTEGER NOT NULL UNIQUE,
    last_processed_block BIGINT NOT NULL,
    last_finalized_block BIGINT NOT NULL,
    last_block_hash VARCHAR(66),             -- Reorg 감지용
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
  );

[설계 포인트]

  1. event_key (UNIQUE):
     chain_id + tx_hash + log_index 조합으로 전 세계에서 유일
     → INSERT ... ON CONFLICT (event_key) DO NOTHING
     → Gap Recovery 시 이미 처리된 이벤트 자동 스킵

  2. is_valid 플래그:
     Reorg 시 DELETE 대신 is_valid = FALSE로 마킹
     → 감사 추적 가능, 복구 시 참고

  3. block_tracker:
     리스너 재시작 시 어디서부터 재개할지 알려줌
     서비스 인스턴스가 여러 개일 때 중복 처리 방지
```

---

### 5. 핵심 테이블 — 잔액 및 원장

```
[balances 테이블 — 사용자 잔액 관리]

  CREATE TABLE balances (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT NOT NULL,
    asset_type      VARCHAR(20) NOT NULL,    -- ETH, ERC20, ERC721
    token_address   VARCHAR(42),             -- NULL이면 네이티브(ETH)
    chain_id        INTEGER NOT NULL,

    -- 잔액
    available       NUMERIC(78, 0) NOT NULL DEFAULT 0,  -- 사용 가능
    locked          NUMERIC(78, 0) NOT NULL DEFAULT 0,  -- 출금/거래 대기 중
    pending_deposit NUMERIC(78, 0) NOT NULL DEFAULT 0,  -- 입금 대기 (미확정)

    -- 검증
    CHECK (available >= 0),
    CHECK (locked >= 0),

    updated_at      TIMESTAMP NOT NULL DEFAULT NOW(),

    UNIQUE (user_id, token_address, chain_id)
  );

[balance_ledger 테이블 — 모든 잔액 변동 이력 (원장)]

  CREATE TABLE balance_ledger (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT NOT NULL,
    token_address   VARCHAR(42),
    chain_id        INTEGER NOT NULL,

    -- 변동 내역
    entry_type      VARCHAR(20) NOT NULL,
    -- DEPOSIT, WITHDRAW, LOCK, UNLOCK, FEE, REWARD, REORG_REVERSAL
    amount          NUMERIC(78, 0) NOT NULL,  -- 양수: 증가, 음수: 감소
    balance_after   NUMERIC(78, 0) NOT NULL,  -- 변동 후 잔액

    -- 참조
    reference_type  VARCHAR(20),              -- TRANSACTION, EVENT, MANUAL
    reference_id    BIGINT,                   -- 참조 테이블의 ID
    tx_hash         VARCHAR(66),

    -- 메타
    description     TEXT,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),

    INDEX idx_bl_user (user_id, created_at),
    INDEX idx_bl_ref (reference_type, reference_id)
  );

[설계 포인트 — 이중 기장(Double-Entry)]

  모든 잔액 변동은 반드시 balance_ledger에 기록
  → 어떤 시점이든 원장을 합산하면 현재 잔액과 일치해야 함
  → 불일치 시 Reconciliation으로 발견 가능

  입금 흐름:
  1. Tx TENTATIVE → pending_deposit += amount
     ledger: { entry_type: 'DEPOSIT', balance_after: ... }
  2. Tx CONFIRMED (12 conf) → available += amount, pending_deposit -= amount
     ledger: { entry_type: 'DEPOSIT_CONFIRMED', balance_after: ... }
  3. Tx REORGED → pending_deposit -= amount
     ledger: { entry_type: 'REORG_REVERSAL', balance_after: ... }

  출금 흐름:
  1. 출금 요청 → available -= amount, locked += amount
     ledger: { entry_type: 'LOCK', balance_after: ... }
  2. Tx CONFIRMED → locked -= amount
     ledger: { entry_type: 'WITHDRAW', balance_after: ... }
  3. Tx REVERTED → locked -= amount, available += amount
     ledger: { entry_type: 'UNLOCK', balance_after: ... }
```

---

### 6. 트랜잭션 무결성 패턴

```
[패턴 1: Outbox 패턴 — DB와 Tx의 원자적 처리]

  문제:
    1. DB에 출금 기록 저장 (성공)
    2. 블록체인 Tx 전송 (실패!)
    → DB에는 기록, 블록체인에는 없음 = 불일치

  해결:
    1. DB에 출금 기록 + outbox 메시지를 하나의 DB 트랜잭션으로 저장
    2. 별도 프로세서가 outbox를 읽어 블록체인 Tx 전송
    3. 전송 성공 시 outbox 상태 업데이트

  BEGIN TRANSACTION;
    INSERT INTO transactions (request_id, ...) VALUES (...);
    INSERT INTO outbox (event_type, payload, status)
      VALUES ('SEND_TX', '{"tx_id": 123, ...}', 'PENDING');
  COMMIT;

  -- Outbox Processor (별도 프로세스)
  SELECT * FROM outbox WHERE status = 'PENDING' ORDER BY created_at LIMIT 10;
  -- 각 항목에 대해 블록체인 Tx 전송 → 성공 시 status = 'PROCESSED'

[패턴 2: 비관적 잠금 — 잔액 차감의 동시성 제어]

  문제:
    사용자가 동시에 2건의 출금 요청
    잔액 100 → 출금 80 + 출금 80 → 둘 다 통과? → 마이너스 잔액!

  해결:
    SELECT ... FOR UPDATE로 잔액 행 잠금

  BEGIN TRANSACTION;
    -- 잔액 행 락 (다른 트랜잭션은 대기)
    SELECT available FROM balances
    WHERE user_id = 123 AND token_address = '0x...'
    FOR UPDATE;

    -- 잔액 검증
    IF available >= withdraw_amount THEN
      UPDATE balances SET
        available = available - withdraw_amount,
        locked = locked + withdraw_amount
      WHERE user_id = 123;

      INSERT INTO transactions (...) VALUES (...);
      INSERT INTO balance_ledger (...) VALUES (...);
    END IF;
  COMMIT;

[패턴 3: Reconciliation — 온체인/오프체인 정합성 검증]

  정기적으로 (매시간 or 매일):
  1. 온체인 잔액 조회 (eth_getBalance, balanceOf)
  2. DB 잔액과 비교
  3. 불일치 발생 시 알림 → 수동 조사

  CREATE TABLE reconciliation_results (
    id              BIGSERIAL PRIMARY KEY,
    wallet_address  VARCHAR(42) NOT NULL,
    token_address   VARCHAR(42),
    chain_id        INTEGER NOT NULL,
    onchain_balance NUMERIC(78, 0) NOT NULL,
    offchain_balance NUMERIC(78, 0) NOT NULL,
    difference      NUMERIC(78, 0) NOT NULL,
    is_matched      BOOLEAN NOT NULL,
    resolution      TEXT,                    -- 불일치 해결 내용
    checked_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    resolved_at     TIMESTAMP
  );

  -- 허용 오차: pending Tx 고려
  -- onchain - offchain의 차이가 pending Tx 합계와 같으면 OK
  -- 다르면 MISMATCH → 조사 필요
```

---

### 7. 인덱스 전략

```
[블록체인 서비스에서 자주 쓰는 쿼리와 인덱스]

  1. 상태별 Tx 조회 (모니터링, 배치 처리):
     WHERE status = 'PENDING' AND created_at < NOW() - INTERVAL '30 minutes'
     → INDEX (status, created_at)

  2. 특정 지갑의 Tx 이력:
     WHERE from_address = '0x...' ORDER BY created_at DESC
     → INDEX (from_address, created_at DESC)

  3. Nonce 충돌 확인:
     WHERE from_address = '0x...' AND nonce = 42 AND status NOT IN ('REPLACED', 'DROPPED')
     → INDEX (from_address, nonce, status)

  4. 블록 범위 이벤트 조회 (Gap Recovery):
     WHERE chain_id = 1 AND block_number BETWEEN 19000000 AND 19000500
     → INDEX (chain_id, block_number)

  5. 사용자 잔액 조회:
     WHERE user_id = 123 AND chain_id = 1
     → UNIQUE INDEX (user_id, token_address, chain_id)

  6. 대사(Reconciliation) 불일치 조회:
     WHERE is_matched = FALSE AND resolved_at IS NULL
     → INDEX (is_matched, resolved_at)

[파티셔닝 전략]

  transactions 테이블이 수백만 건 이상일 때:
  → created_at 기준 월별 파티셔닝

  CREATE TABLE transactions (
    ...
  ) PARTITION BY RANGE (created_at);

  CREATE TABLE transactions_2026_01 PARTITION OF transactions
    FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

  indexed_events 테이블:
  → block_number 범위 기준 파티셔닝

  장점:
  - 오래된 데이터 조회 성능 유지
  - 파티션 단위 삭제/아카이빙 용이
  - 인덱스 크기 관리
```

---

### 8. 마이그레이션 및 스키마 변경

```
[블록체인 서비스 스키마 변경 시 주의사항]

  1. Zero-downtime 필수:
     블록체인 이벤트는 24/7 발생
     리스너를 멈출 수 없음
     → Online DDL 필수 (pg_repack, pt-online-schema-change)

  2. 하위 호환성 유지:
     신규 필드 추가 시 DEFAULT 값 설정
     NOT NULL 제약은 데이터 채운 후 추가
     컬럼 삭제 전 충분한 마이그레이션 기간

  3. 데이터 백필:
     신규 필드에 온체인 데이터를 채워야 하는 경우
     → 별도 배치 잡으로 온체인에서 조회하여 채움
     → RPC Rate Limit 고려하여 천천히

  4. 롤백 계획:
     스키마 변경은 항상 롤백 스크립트와 함께
     블록체인 데이터는 온체인에서 언제든 재구축 가능
     → 최악의 경우 이벤트 테이블을 Drop & Rebuild
```

---

## 헷갈렸던 포인트

### Q1: 블록체인 잔액을 왜 DB에 저장하나? 온체인이 진짜인데?

```
[온체인 조회의 한계]

  매번 온체인에서 잔액을 조회하면:
  1. RPC 호출 필요 → 지연 시간 (50~200ms)
  2. Rate Limit → 대량 요청 불가
  3. 과거 시점 잔액 조회 어려움

  DB에 잔액을 캐싱하는 이유:
  1. 빠른 조회 (< 1ms)
  2. 복잡한 쿼리 가능 (특정 금액 이상 사용자 등)
  3. 출금 시 즉각적인 잔액 차감 (Lock)
  4. 히스토리 추적 (ledger)

  핵심 원칙:
  "DB는 캐시, 온체인이 진실. 불일치 시 온체인이 우선."
  → Reconciliation으로 정기 검증
```

### Q2: NUMERIC vs BIGINT, 왜 NUMERIC(78,0)을 쓰나?

```
[이더리움의 숫자 체계]

  Solidity uint256: 최대 2^256 - 1 ≈ 1.15 × 10^77 (78자리)
  PostgreSQL BIGINT: 최대 2^63 - 1 ≈ 9.2 × 10^18 (19자리)

  1 ETH = 10^18 Wei (18자리)
  BIGINT 최대 = ~9.2 ETH (Wei 단위)
  → BIGINT로는 10 ETH도 표현 못 함!

  NUMERIC(78, 0):
  - 소수점 없는 78자리 정수
  - uint256의 모든 값을 표현 가능
  - 연산 속도는 BIGINT보다 느리지만, 정확성이 우선

  대안:
  - VARCHAR: 문자열로 저장, 비교/연산 어려움
  - DECIMAL(36, 18): ETH 단위로 변환하여 저장 (실무에서 자주 사용)
```

### Q3: 멱등성 키(request_id)는 왜 필수인가?

```
[시나리오]

  1. 사용자가 "1 ETH 출금" 요청
  2. 서버가 Tx를 생성하고 블록체인에 전송
  3. 전송 중 네트워크 타임아웃 → 서버는 결과를 모름
  4. 사용자가 재시도 → 또 "1 ETH 출금" 요청
  5. request_id 없으면 → 2번 출금!

  request_id가 있으면:
  INSERT INTO transactions (request_id, ...)
    VALUES ('user-123-withdraw-20260311-001', ...)
    ON CONFLICT (request_id) DO NOTHING;
  → 같은 request_id가 이미 있으면 무시
  → 기존 Tx의 상태를 반환

  request_id 생성 전략:
  - 클라이언트가 생성: UUID v4 (가장 간단)
  - 서버가 생성: user_id + action + timestamp hash
  - 비즈니스 키: "withdraw:{user_id}:{amount}:{nonce}" (중복 방지)
```

---

## 참고 자료

| 자료 | 설명 |
|------|------|
| [PostgreSQL Numeric Types](https://www.postgresql.org/docs/current/datatype-numeric.html) | PostgreSQL 숫자 타입 공식 문서 |
| [Designing Data-Intensive Applications](https://dataintensive.net/) | 분산 시스템 데이터 설계의 바이블 |
| [Outbox Pattern — Microservices.io](https://microservices.io/patterns/data/transactional-outbox.html) | Outbox 패턴 상세 설명 |
| [Ethereum JSON-RPC Spec](https://ethereum.github.io/execution-apis/api-documentation/) | 이더리움 RPC API 스펙 |
| [OpenZeppelin Defender — Transaction Management](https://docs.openzeppelin.com/defender/) | 트랜잭션 관리 자동화 |
