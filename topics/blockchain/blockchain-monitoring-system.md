---
title: "블록체인 모니터링 시스템 — 설계, 지표, 알림, 운영"
parent: Blockchain / Web3
nav_order: 4
tags: [모니터링, Prometheus, Grafana, 알림, Nonce, 가스비, RPC, 대시보드]
description: "Tx 상태/Nonce/가스비/RPC 모니터링 지표, Prometheus+Grafana 아키텍처, 알림 등급 설계, 인시던트 대응 플레이북을 정리합니다."
---

# 블록체인 모니터링 시스템 — 설계, 지표, 알림, 운영

## 핵심 정리

### 1. 블록체인 모니터링이 특별한 이유

```
[Web2 모니터링 vs 블록체인 모니터링]

  Web2:
    서버 CPU/메모리/디스크 → 로그 → APM(DataDog, Grafana)
    → 모든 것이 "내 서버" 안에서 발생

  블록체인:
    내 서버 + 블록체인 네트워크 + RPC 노드 + 스마트 컨트랙트
    → "내 통제 밖"에서 발생하는 이벤트를 추적해야 함

  추가 모니터링 대상:
  - 블록체인 네트워크 상태 (블록 생성, 가스비, Reorg)
  - RPC 노드 건강 상태 (응답 시간, 블록 동기화 수준)
  - 트랜잭션 라이프사이클 (CREATED → CONFIRMED)
  - 지갑 잔액 (Hot/Warm/Cold)
  - 스마트 컨트랙트 이벤트 (Transfer, Approval 등)
  - Nonce 정합성 (로컬 vs 온체인)
  - Mempool 상태 (pending Tx 수, 가스비 분포)
```

---

### 2. 핵심 모니터링 지표

```
[1. 트랜잭션 상태 지표]

  ┌─────────────────────┬────────────────────────────────────────┐
  │ 지표                 │ 설명 / 임계값                           │
  ├─────────────────────┼────────────────────────────────────────┤
  │ pending_tx_count    │ 현재 PENDING 상태 Tx 수                 │
  │                     │ > 50: WARNING, > 200: CRITICAL         │
  │ pending_tx_age_max  │ 가장 오래된 PENDING Tx 경과 시간          │
  │                     │ > 10분: WARNING, > 30분: CRITICAL       │
  │ tx_success_rate     │ CONFIRMED / (CONFIRMED + REVERTED)      │
  │                     │ < 95%: WARNING, < 80%: CRITICAL        │
  │ tx_lost_count       │ LOST 상태 Tx 수 (receipt 미확인)         │
  │                     │ > 0: WARNING                            │
  │ tx_avg_confirm_time │ 평균 SUBMITTED → CONFIRMED 시간          │
  │                     │ > 3분: WARNING (이더리움 기준)            │
  │ revert_rate_change  │ REVERTED 비율 급증 감지                  │
  │                     │ 1시간 내 2배 증가: CRITICAL              │
  └─────────────────────┴────────────────────────────────────────┘

[2. Nonce 건강도 지표]

  ┌─────────────────────┬────────────────────────────────────────┐
  │ 지표                 │ 설명 / 임계값                           │
  ├─────────────────────┼────────────────────────────────────────┤
  │ nonce_gap           │ 온체인 nonce와 로컬 nonce 차이           │
  │                     │ 차이 > 0: pending Tx 존재               │
  │                     │ 차이 < 0: 있을 수 없음 → CRITICAL       │
  │ nonce_gap_duration  │ Gap이 지속되는 시간                      │
  │                     │ > 15분: WARNING, > 30분: CRITICAL       │
  │ nonce_sequence_ok   │ 전송된 Tx nonce가 순차적인지             │
  │                     │ Gap 감지 시: CRITICAL                   │
  └─────────────────────┴────────────────────────────────────────┘

[3. 가스비 지표]

  ┌─────────────────────┬────────────────────────────────────────┐
  │ 지표                 │ 설명 / 임계값                           │
  ├─────────────────────┼────────────────────────────────────────┤
  │ current_base_fee    │ 현재 블록의 baseFee (Gwei)              │
  │                     │ > 100 Gwei: WARNING                    │
  │ gas_cost_per_tx_usd │ Tx당 평균 가스 비용 (USD)               │
  │                     │ 비즈니스별 한도 초과 시 WARNING           │
  │ gas_price_trend     │ 최근 20블록 baseFee 추세 (상승/하락)      │
  │                     │ 급격한 상승 시 큐잉 시스템 가동           │
  │ queued_tx_count     │ 가스비 초과로 큐에 대기 중인 Tx          │
  │                     │ > 100: WARNING                          │
  └─────────────────────┴────────────────────────────────────────┘

[4. 지갑 잔액 지표]

  ┌─────────────────────┬────────────────────────────────────────┐
  │ 지표                 │ 설명 / 임계값                           │
  ├─────────────────────┼────────────────────────────────────────┤
  │ hot_wallet_eth      │ Hot Wallet의 ETH 잔액 (가스비용)         │
  │                     │ < 0.5 ETH: WARNING, < 0.1: CRITICAL   │
  │ hot_wallet_token    │ Hot Wallet의 토큰 잔액                  │
  │                     │ < 일일 처리량의 50%: WARNING            │
  │ warm_wallet_balance │ Warm Wallet 잔액                       │
  │                     │ < Hot Wallet 충전 3회분: WARNING        │
  │ unexpected_outflow  │ 예상치 못한 자금 유출 감지               │
  │                     │ 미등록 Tx 발생: CRITICAL (보안 사고)     │
  └─────────────────────┴────────────────────────────────────────┘

[5. RPC 노드 지표]

  ┌─────────────────────┬────────────────────────────────────────┐
  │ 지표                 │ 설명 / 임계값                           │
  ├─────────────────────┼────────────────────────────────────────┤
  │ rpc_response_time   │ RPC 호출 평균 응답 시간                  │
  │                     │ > 1초: WARNING, > 3초: CRITICAL         │
  │ rpc_error_rate      │ RPC 호출 에러 비율                      │
  │                     │ > 5%: WARNING, > 20%: CRITICAL         │
  │ rpc_block_height    │ 각 RPC 노드의 최신 블록 번호             │
  │                     │ 노드 간 차이 > 10블록: WARNING           │
  │ rpc_rate_limit_hits │ 429 응답 수                             │
  │                     │ > 0: WARNING (플랜 업그레이드 고려)       │
  │ rpc_active_node     │ 현재 사용 중인 RPC (Primary/Fallback)   │
  │                     │ Fallback 사용 중: WARNING               │
  └─────────────────────┴────────────────────────────────────────┘

[6. 이벤트 리스너 지표]

  ┌─────────────────────┬────────────────────────────────────────┐
  │ 지표                 │ 설명 / 임계값                           │
  ├─────────────────────┼────────────────────────────────────────┤
  │ listener_block_lag  │ 최신 블록 - 마지막 처리 블록             │
  │                     │ > 50블록: WARNING, > 500: CRITICAL     │
  │ events_per_minute   │ 분당 처리 이벤트 수                     │
  │                     │ 0 (5분 이상): WARNING                  │
  │ reorg_detected      │ Reorg 감지 횟수                        │
  │                     │ 감지 즉시: ALERT                       │
  │ duplicate_events    │ 중복 처리된 이벤트 수                   │
  │                     │ > 0: INFO (멱등성 동작 중)              │
  └─────────────────────┴────────────────────────────────────────┘
```

---

### 3. 모니터링 아키텍처

```
[전체 모니터링 시스템 구조]

  ┌────────────────────────────────────────────────────────────┐
  │                     데이터 수집 계층                        │
  │                                                            │
  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐ │
  │  │ Tx 상태   │ │ Wallet   │ │ RPC 헬스  │ │ Event        │ │
  │  │ Collector │ │ Monitor  │ │ Checker  │ │ Listener     │ │
  │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └──────┬───────┘ │
  └───────┼────────────┼────────────┼───────────────┼─────────┘
          │            │            │               │
          ▼            ▼            ▼               ▼
  ┌────────────────────────────────────────────────────────────┐
  │                    메트릭 저장 계층                         │
  │                                                            │
  │  Prometheus (시계열 메트릭)  +  Elasticsearch (로그/이벤트) │
  │                                                            │
  └───────────────────────┬────────────────────────────────────┘
                          │
                          ▼
  ┌────────────────────────────────────────────────────────────┐
  │                    시각화 / 알림 계층                       │
  │                                                            │
  │  ┌──────────┐  ┌──────────────┐  ┌────────────────────┐  │
  │  │ Grafana   │  │ AlertManager │  │ PagerDuty/Slack    │  │
  │  │ Dashboard │  │ (규칙 기반)   │  │ (알림 전달)         │  │
  │  └──────────┘  └──────────────┘  └────────────────────┘  │
  └────────────────────────────────────────────────────────────┘

[Prometheus 메트릭 예시]

  # Tx 상태별 카운트
  blockchain_tx_total{status="CONFIRMED", chain="ethereum"} 15234
  blockchain_tx_total{status="PENDING", chain="ethereum"} 12
  blockchain_tx_total{status="REVERTED", chain="ethereum"} 45
  blockchain_tx_total{status="LOST", chain="ethereum"} 2

  # Hot Wallet 잔액
  wallet_balance_eth{wallet="hot-withdraw", chain="ethereum"} 2.45
  wallet_balance_token{wallet="hot-mint", token="USDT"} 50000

  # RPC 응답 시간 히스토그램
  rpc_request_duration_seconds_bucket{provider="alchemy", le="0.1"} 9800
  rpc_request_duration_seconds_bucket{provider="alchemy", le="1.0"} 9950
  rpc_request_duration_seconds_bucket{provider="alchemy", le="3.0"} 9999

  # Nonce 상태
  nonce_local{wallet="hot-withdraw"} 1523
  nonce_onchain{wallet="hot-withdraw"} 1520
  # 차이 = 3 → 3개의 pending Tx 존재
```

---

### 4. 알림 규칙 설계

```
[알림 등급 체계]

  P1 (CRITICAL) — 즉시 대응, 24/7 당직 호출:
  - 예상치 못한 자금 유출 감지
  - Nonce가 온체인보다 낮음 (있을 수 없는 상태)
  - 모든 RPC 노드 동시 장애
  - 서명 서비스(KMS/HSM) 접근 불가
  - Reorg 깊이 > 3블록

  P2 (WARNING) — 30분 내 확인:
  - Pending Tx가 30분 이상 지속
  - Hot Wallet 잔액 부족
  - RPC Primary → Fallback 전환
  - 가스비 한도 초과로 Tx 큐잉 시작
  - 이벤트 리스너 50블록+ 지연

  P3 (INFO) — 업무 시간 내 확인:
  - 일일 Tx 통계 리포트
  - 가스비 추세 리포트
  - 이벤트 중복 처리 로그
  - RPC 비용 사용량 알림

[Grafana Alert 규칙 예시]

  # P1: 미등록 출금 감지
  ALERT UnauthorizedOutflow
    IF blockchain_tx_unauthorized_outflow > 0
    FOR 0m
    LABELS { severity = "critical" }
    ANNOTATIONS {
      summary = "미등록 출금 트랜잭션 감지!",
      description = "{{ $labels.wallet }}에서 미등록 Tx 발생. 즉시 확인 필요."
    }

  # P2: Pending Tx 지연
  ALERT PendingTxStuck
    IF blockchain_pending_tx_age_max_seconds > 1800
    FOR 5m
    LABELS { severity = "warning" }
    ANNOTATIONS {
      summary = "Pending Tx 30분 이상 지속",
      description = "{{ $labels.wallet }}의 Tx가 30분 이상 pending. Nonce/Gas 확인 필요."
    }

  # P2: Hot Wallet 잔액 부족
  ALERT HotWalletLowBalance
    IF wallet_balance_eth{type="hot"} < 0.5
    FOR 1m
    LABELS { severity = "warning" }
    ANNOTATIONS {
      summary = "Hot Wallet ETH 잔액 부족",
      description = "{{ $labels.wallet }} 잔액: {{ $value }} ETH. 가스비 충전 필요."
    }
```

---

### 5. Grafana 대시보드 설계

```
[대시보드 레이아웃]

  ┌─────────────────────────────────────────────────────────┐
  │ 블록체인 서비스 운영 대시보드                               │
  ├─────────────────────────────────────────────────────────┤
  │                                                         │
  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐    │
  │  │ 24h Tx 성공률  │ │ Pending Tx   │ │ 현재 Gas Fee  │    │
  │  │   98.5%       │ │    12건       │ │  25 Gwei      │    │
  │  │   ▲ 0.3%     │ │   ▼ 3건      │ │  ▼ 5 Gwei    │    │
  │  └──────────────┘ └──────────────┘ └──────────────┘    │
  │                                                         │
  │  ┌────────────────────────────────────────────────┐    │
  │  │ Tx 상태 타임라인 (Area Chart)                    │    │
  │  │  ████ CONFIRMED  ░░ PENDING  ▓▓ REVERTED       │    │
  │  │  ────────────────────────────────── (24h)       │    │
  │  └────────────────────────────────────────────────┘    │
  │                                                         │
  │  ┌──────────────────────┐ ┌──────────────────────┐    │
  │  │ Wallet 잔액 현황      │ │ RPC 노드 상태         │    │
  │  │                      │ │                      │    │
  │  │ HW-출금: 2.4 ETH ✅  │ │ Alchemy:  OK (45ms) │    │
  │  │ HW-민팅: 1.1 ETH ⚠️  │ │ Infura:   OK (67ms) │    │
  │  │ HW-가스: 5.0 ETH ✅  │ │ 자체노드:  WARN (2s) │    │
  │  │ Warm:   50.2 ETH ✅  │ │ 블록 차이: 2블록     │    │
  │  └──────────────────────┘ └──────────────────────┘    │
  │                                                         │
  │  ┌────────────────────────────────────────────────┐    │
  │  │ Nonce 건강도 (Table)                             │    │
  │  │ Wallet     | Local | Onchain | Gap | Status     │    │
  │  │ HW-출금    | 1523  | 1520    |  3  | ⚠️ PENDING │    │
  │  │ HW-민팅    |  847  |  847    |  0  | ✅ OK      │    │
  │  │ HW-가스    |  234  |  234    |  0  | ✅ OK      │    │
  │  └────────────────────────────────────────────────┘    │
  │                                                         │
  │  ┌────────────────────────────────────────────────┐    │
  │  │ 가스비 추이 (Line Chart, 24h)                    │    │
  │  │  baseFee ─── / priorityFee --- / 한도 ═══       │    │
  │  └────────────────────────────────────────────────┘    │
  │                                                         │
  │  ┌────────────────────────────────────────────────┐    │
  │  │ 이벤트 리스너 상태                               │    │
  │  │ 최신 블록: 19,500,000                           │    │
  │  │ 처리 블록: 19,499,998 (2블록 차이) ✅             │    │
  │  │ 이벤트/분: 23.5                                  │    │
  │  │ 마지막 Reorg: 3일 전 (깊이: 1)                   │    │
  │  └────────────────────────────────────────────────┘    │
  └─────────────────────────────────────────────────────────┘
```

---

### 6. 온체인 모니터링 — 스마트 컨트랙트 감시

```
[컨트랙트 모니터링 항목]

  1. 이벤트 모니터링:
     - Transfer: 토큰 이동 추적
     - Approval: 권한 부여 감시 (무한 승인 위험)
     - OwnershipTransferred: 소유권 변경 감지
     - Paused/Unpaused: 컨트랙트 일시정지 상태

  2. 상태 변수 모니터링:
     - 컨트랙트 잔액 변화
     - 관리자 주소 변경
     - 설정값(수수료율 등) 변경

  3. 비정상 패턴 감지:
     - 대량 Transfer 이벤트 발생 (드레인 공격 의심)
     - 알 수 없는 주소에 approve(unlimited) 호출
     - 짧은 시간 내 반복적 컨트랙트 호출 (봇/공격)

[OpenZeppelin Defender / Forta 활용]

  OpenZeppelin Defender:
    - 자동 Tx 실행 (Autotask)
    - 컨트랙트 모니터링 (Sentinel)
    - 관리자 기능 관리 (Admin)
    - 사고 알림 (Notifications)

  Forta Network:
    - 탈중앙 보안 모니터링 네트워크
    - 커뮤니티가 만든 Detection Bot
    - 실시간 위협 감지 (Reentrancy, Flash Loan 등)
    - 커스텀 Bot 개발 가능

  Tenderly:
    - Tx 시뮬레이션 및 디버깅
    - 실시간 알림 (Alert)
    - Gas 프로파일링
    - Web3 Action (자동화)
```

---

### 7. 백오피스(관리자 페이지) 연동

```
[관리자 페이지에서 필요한 블록체인 운영 기능]

  1. 트랜잭션 관리:
     ┌──────────────────────────────────────────────────┐
     │ Tx 목록 (검색/필터링)                              │
     │ ─────────────────────────────────────────────     │
     │ Tx Hash  | 상태      | 금액   | 생성시간  | 액션   │
     │ 0xabc... | PENDING  | 1 ETH | 10:23   | [재전송] │
     │ 0xdef... | CONFIRMED| 2 ETH | 10:20   | [상세]  │
     │ 0x123... | LOST     | 0.5ETH| 10:15   | [복구]  │
     └──────────────────────────────────────────────────┘

  2. 수동 작업:
     - Stuck Tx 재전송 (가스비 높여서)
     - Nonce Gap 수동 해결 (빈 Tx 전송)
     - 출금 수동 승인/거절
     - Hot Wallet 수동 충전 요청
     - 긴급 컨트랙트 일시정지

  3. 대시보드:
     - 실시간 지갑 잔액
     - 일일/주간/월간 Tx 통계
     - 가스비 사용량 및 비용 추적
     - 서비스 상태 한눈에 보기

  4. 감사 로그:
     - 누가 어떤 작업을 수행했는지 기록
     - 모든 수동 승인/거절 이력
     - IP, 시간, 작업 내용 기록
     - 변경 불가능한 로그 저장
```

---

### 8. 인시던트 대응 플레이북

```
[시나리오 1: Pending Tx 대량 발생]

  증상: pending_tx_count > 200, pending_tx_age_max > 30분

  대응 순서:
  1. 가스비 확인 → 현재 baseFee vs Tx의 maxFeePerGas 비교
  2-a. 가스비 급등 → 긴급 Tx만 가스비 높여 재전송, 나머지 큐잉
  2-b. Nonce Gap → Gap 위치 확인 → 빈 Tx로 Gap 채우기
  2-c. RPC 장애 → 폴백 노드로 전환 → 전환 후 재전송
  3. 해소 후: 원인 분석 → 재발 방지 조치

[시나리오 2: Hot Wallet 잔액 급감]

  증상: unexpected_outflow 알림

  대응 순서:
  1. 즉시 해당 지갑의 서명 서비스 차단
  2. 미인가 Tx인지 확인 (DB에 해당 Tx 기록이 있는지)
  3-a. 인가된 Tx → 알림 오탐, 서비스 복구
  3-b. 미인가 Tx → 보안 사고!
     → 모든 Hot Wallet 서명 차단
     → 나머지 자산 비상 주소로 이동
     → Cold Wallet 키 안전 확인
     → 경영진/규제기관 보고
     → 포렌식 시작

[시나리오 3: Reorg 감지]

  증상: reorg_detected 알림, 깊이 N

  대응 순서:
  1. Reorg 깊이 확인
  2. 영향받는 블록 범위의 처리된 Tx 목록 조회
  3. 각 Tx의 새 블록 포함 여부 확인
  4-a. 새 블록에 포함됨 → DB 블록 번호만 업데이트
  4-b. 새 블록에 미포함 → 상태 REORGED로 변경 → 재전송 대기
  5. 이벤트 리스너 재처리 범위 설정
  6. 잔액 정합성 검증 (온체인 vs DB)

[시나리오 4: RPC 전체 장애]

  증상: 모든 RPC 노드 응답 없음

  대응 순서:
  1. 신규 Tx 전송 중단 → 큐에 쌓기
  2. 대체 RPC 제공자 긴급 추가 (QuickNode, Ankr 등)
  3. 자체 풀노드 상태 확인 → 가용하면 전환
  4. 복구 후: 큐에 쌓인 Tx 순차 처리
  5. 이벤트 리스너 Gap Recovery 실행
```

---

## 헷갈렸던 포인트

### Q1: Prometheus vs ELK Stack, 뭘 써야 하나?

```
[용도가 다름 — 둘 다 필요]

  Prometheus + Grafana:
    → 숫자 지표(Metric) 모니터링에 최적
    → Tx 수, 응답 시간, 잔액, 가스비 등
    → 시계열 데이터, 임계값 기반 알림
    → 대시보드 시각화

  ELK Stack (Elasticsearch + Logstash + Kibana):
    → 로그/이벤트 데이터 분석에 최적
    → Tx 상세 로그, 에러 스택트레이스
    → 전문 검색, 로그 패턴 분석
    → 사후 분석(포렌식)

  실무 조합:
    Prometheus → "지금 무슨 일이 일어나고 있는가?" (실시간)
    ELK → "왜 그런 일이 일어났는가?" (사후 분석)
```

### Q2: 모니터링 시스템이 블록체인에도 접근해야 하나?

```
[직접 접근 vs 간접 접근]

  방법 1: 모니터링 시스템이 직접 RPC 호출
    장점: 실시간, 독립적
    단점: RPC 비용 증가, Rate Limit 이슈

  방법 2: 서비스가 메트릭 노출, 모니터링이 수집
    서비스 → /metrics 엔드포인트 → Prometheus scrape
    장점: RPC 부하 없음, 서비스와 동일한 뷰
    단점: 서비스 다운 시 모니터링도 중단

  권장: 하이브리드
    - 기본 지표는 서비스의 /metrics에서 수집 (방법 2)
    - 크로스체크용으로 독립 RPC 조회 (방법 1)
      예: 5분마다 온체인 잔액 직접 조회 → DB 잔액과 비교
    → 서비스 버그로 인한 잔액 불일치도 감지 가능
```

---

## 참고 자료

| 자료 | 설명 |
|------|------|
| [Prometheus — Monitoring Best Practices](https://prometheus.io/docs/practices/) | Prometheus 메트릭 설계 가이드 |
| [Grafana Dashboard Examples](https://grafana.com/grafana/dashboards/) | 커뮤니티 대시보드 템플릿 |
| [OpenZeppelin Defender](https://docs.openzeppelin.com/defender/) | 스마트 컨트랙트 모니터링/자동화 도구 |
| [Forta Network](https://forta.org/) | 탈중앙 보안 모니터링 네트워크 |
| [Tenderly](https://tenderly.co/) | Web3 DevOps 플랫폼 (모니터링, 시뮬레이션, 알림) |
| [Alchemy Enhanced APIs](https://docs.alchemy.com/) | 블록체인 데이터 조회 최적화 API |
