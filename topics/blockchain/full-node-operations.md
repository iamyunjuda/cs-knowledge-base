---
title: "풀노드 운영 — Geth, OpenEthereum(Parity), 동기화, 유지보수"
parent: Blockchain / Web3
nav_order: 7
---

# 풀노드 운영 — Geth, OpenEthereum(Parity), 동기화, 유지보수

## 핵심 정리

### 1. 풀노드란?

```
[이더리움 노드 유형]

  ┌──────────────┬─────────────────────────────────────────────────┐
  │ 유형          │ 설명                                             │
  ├──────────────┼─────────────────────────────────────────────────┤
  │ Full Node    │ 모든 블록을 검증, 최근 상태(State)만 보관          │
  │              │ 과거 상태는 Pruning으로 삭제                       │
  │              │ 디스크: ~1TB (이더리움 메인넷)                     │
  ├──────────────┼─────────────────────────────────────────────────┤
  │ Archive Node │ 모든 블록 + 모든 과거 상태를 보관                  │
  │              │ 과거 시점 잔액 조회 가능 (eth_getBalance at block) │
  │              │ 디스크: ~15TB+ (이더리움 메인넷)                   │
  ├──────────────┼─────────────────────────────────────────────────┤
  │ Light Node   │ 블록 헤더만 저장, 필요 시 Full Node에 요청         │
  │              │ 디스크: ~1GB                                     │
  │              │ 보안: Full Node에 의존 (신뢰 필요)                │
  └──────────────┴─────────────────────────────────────────────────┘

[왜 자체 풀노드를 운영하는가?]

  SaaS RPC (Alchemy, Infura) 대비:
  1. Rate Limit 없음: 무제한 요청 가능
  2. 지연 시간 최소: 같은 네트워크 내 통신 (~1ms vs ~50ms)
  3. 프라이버시: Tx 정보가 제3자에 노출되지 않음
  4. 검열 저항: Infura가 차단한 주소도 처리 가능
  5. 비용: 대량 요청 시 SaaS보다 저렴할 수 있음
  6. 커스텀 API: 트레이싱, 디버그 등 고급 API 사용 가능

  단점:
  - 운영 인력 필요 (24/7 모니터링)
  - 하드웨어 비용 ($500~5000/월)
  - 초기 동기화 시간 (수일~수주)
  - 업데이트/포크 대응 필수
```

---

### 2. Geth (Go-Ethereum)

```
[Geth = 이더리움의 사실상 표준 실행 클라이언트]

  언어: Go
  점유율: ~80% (이더리움 노드 중)
  저장소: github.com/ethereum/go-ethereum

[The Merge 이후 노드 구성]

  이더리움 PoS에서 노드 = 실행 클라이언트 + 합의 클라이언트

  ┌─────────────────────────────────────────────┐
  │         합의 클라이언트 (Consensus Layer)      │
  │  Prysm / Lighthouse / Teku / Nimbus / Lodestar│
  │  → Beacon Chain, 블록 제안, Attestation       │
  └──────────────────────┬──────────────────────┘
                         │ Engine API (JWT 인증)
                         │ localhost:8551
                         ▼
  ┌─────────────────────────────────────────────┐
  │         실행 클라이언트 (Execution Layer)      │
  │  Geth / Nethermind / Besu / Erigon / Reth    │
  │  → EVM 실행, State 관리, Tx Pool, JSON-RPC   │
  └─────────────────────────────────────────────┘

  → 둘 다 실행해야 완전한 노드!

[Geth 설치 및 실행]

  # Ubuntu
  sudo add-apt-repository -y ppa:ethereum/ethereum
  sudo apt-get update
  sudo apt-get install geth

  # 또는 소스 빌드
  git clone https://github.com/ethereum/go-ethereum.git
  cd go-ethereum && make geth

  # 메인넷 풀노드 실행 (Snap Sync)
  geth \
    --mainnet \
    --http \
    --http.addr "0.0.0.0" \
    --http.port 8545 \
    --http.api "eth,net,web3,txpool" \
    --http.corsdomain "*" \
    --ws \
    --ws.addr "0.0.0.0" \
    --ws.port 8546 \
    --authrpc.addr "0.0.0.0" \
    --authrpc.port 8551 \
    --authrpc.jwtsecret /path/to/jwt.hex \
    --datadir /data/geth \
    --cache 8192 \
    --maxpeers 50 \
    --syncmode snap

[Geth 동기화 모드]

  ┌──────────────┬───────────────────────────────────────────┐
  │ 모드          │ 설명                                       │
  ├──────────────┼───────────────────────────────────────────┤
  │ snap (기본)   │ 최신 상태를 스냅샷으로 빠르게 동기화          │
  │              │ 초기 동기화: ~12시간 (SSD 기준)              │
  │              │ 디스크: ~800GB                             │
  ├──────────────┼───────────────────────────────────────────┤
  │ full         │ 제네시스부터 모든 블록을 순서대로 실행         │
  │              │ 초기 동기화: 수 일~수 주                     │
  │              │ 검증 수준이 가장 높음                        │
  ├──────────────┼───────────────────────────────────────────┤
  │ archive      │ snap + 모든 과거 상태 보존                  │
  │              │ --gcmode archive 플래그                     │
  │              │ 디스크: ~15TB+                              │
  │              │ 과거 시점 조회 필요할 때                      │
  └──────────────┴───────────────────────────────────────────┘
```

---

### 3. Parity / OpenEthereum (레거시)

```
[역사]

  Parity (2015~):
    Rust로 작성된 이더리움 클라이언트
    Gavin Wood(이더리움 공동 창시자)가 개발
    한때 Geth와 함께 양대 클라이언트

  OpenEthereum (2020~2022):
    Parity의 후속 프로젝트 (이름 변경)
    커뮤니티 주도로 유지보수

  Deprecated (2022):
    The Merge와 함께 개발 중단
    → 후속 Rust 클라이언트: Reth (Paradigm)

[현재 실행 클라이언트 선택지]

  ┌──────────────┬────────┬──────────────────────────────────┐
  │ 클라이언트    │ 언어    │ 특징                              │
  ├──────────────┼────────┼──────────────────────────────────┤
  │ Geth         │ Go     │ 사실상 표준, 가장 안정적            │
  │ Nethermind   │ C#     │ .NET 생태계, 풍부한 플러그인       │
  │ Besu         │ Java   │ 기업용, Permissioned 지원         │
  │ Erigon       │ Go     │ 디스크 효율 극대화 (~2TB Archive) │
  │ Reth         │ Rust   │ 최신, 고성능, Paradigm 개발       │
  └──────────────┴────────┴──────────────────────────────────┘

  합의 클라이언트:
  ┌──────────────┬────────┬──────────────────────────────────┐
  │ 클라이언트    │ 언어    │ 특징                              │
  ├──────────────┼────────┼──────────────────────────────────┤
  │ Prysm        │ Go     │ 가장 많이 사용, 문서 풍부          │
  │ Lighthouse   │ Rust   │ 성능 우수, 메모리 효율적           │
  │ Teku         │ Java   │ ConsenSys 개발, 기업용            │
  │ Nimbus       │ Nim    │ 경량, 리소스 최소                  │
  │ Lodestar     │ TS     │ JavaScript/TypeScript 생태계     │
  └──────────────┴────────┴──────────────────────────────────┘

  클라이언트 다양성이 중요한 이유:
  → 특정 클라이언트에 버그가 있어도 네트워크 전체는 정상 동작
  → 2023년 Prysm 버그로 7블록 Reorg 발생 → 다양성의 중요성 입증
```

---

### 4. 하드웨어 요구사항

```
[풀노드 최소/권장 사양]

  ┌──────────────┬──────────────────┬──────────────────────┐
  │              │ 최소             │ 권장                   │
  ├──────────────┼──────────────────┼──────────────────────┤
  │ CPU          │ 4코어            │ 8코어+                │
  │ RAM          │ 16GB             │ 32GB+                 │
  │ 디스크        │ 1TB NVMe SSD    │ 2TB+ NVMe SSD        │
  │ 네트워크      │ 25 Mbps         │ 100 Mbps+            │
  │ OS           │ Linux (Ubuntu)   │ Ubuntu 22.04 LTS     │
  └──────────────┴──────────────────┴──────────────────────┘

  Archive Node:
  │ 디스크        │ 15TB+ NVMe SSD  │ 주기적으로 증가        │
  │ RAM          │ 32GB            │ 64GB+                  │

  중요:
  - 반드시 NVMe SSD! HDD는 동기화가 사실상 불가능
  - SATA SSD도 느림 → NVMe 권장
  - 디스크 공간은 매월 ~50GB씩 증가
  - State Pruning 없이 운영하면 디스크 빠르게 소진

[클라우드 비용 예시]

  AWS (2024 기준):
  - i3.xlarge (4 CPU, 30GB RAM, 950GB NVMe): ~$200/월
  - i3.2xlarge (Archive): ~$400/월 + EBS 추가

  자체 서버:
  - 초기 투자: $2,000~5,000 (장비)
  - 월 비용: $100~200 (전력, 인터넷)
  - 장기적으로 클라우드보다 저렴
```

---

### 5. 운영 및 유지보수

```
[일상 운영 체크리스트]

  □ 동기화 상태 확인:
    eth.syncing 또는 eth_syncing RPC 호출
    → false면 동기화 완료
    → 블록 차이가 크면 문제

  □ 피어 수 확인:
    net.peerCount
    → 10 이상 유지 권장
    → 0이면 네트워크 연결 문제

  □ 디스크 사용량 모니터링:
    df -h /data/geth
    → 80% 이상이면 확장 또는 Pruning

  □ 메모리/CPU 모니터링:
    → Geth 메모리 누수 발생 가능 (알려진 이슈)
    → 주기적 재시작 스케줄링 (주 1회)

  □ 로그 확인:
    → "Imported new chain segment" → 정상
    → "Synchronisation failed" → 문제 발생
    → "Looking for peers" → 피어 부족

[Pruning — 디스크 관리]

  State Trie Pruning:
    오래된 상태 데이터를 삭제하여 디스크 절약
    Geth: --gcmode full (기본) → 자동 Pruning

  오프라인 Pruning:
    geth snapshot prune-state --datadir /data/geth
    → 노드를 멈추고 실행 (몇 시간 소요)
    → ~100GB 이상 절약 가능

  주의:
  - Pruning 중에는 노드 사용 불가
  - 백업 후 실행 권장
  - Archive 모드에서는 Pruning 불가

[하드포크/업그레이드 대응]

  이더리움 네트워크 업그레이드 시:
  1. 공지 확인 (ethereum.org, Discord, Twitter)
  2. 새 버전 릴리즈 확인 (github releases)
  3. 테스트넷에서 먼저 업그레이드 검증
  4. 하드포크 블록 전에 업데이트 완료!

  업데이트 절차:
  1. 새 바이너리 다운로드 & 빌드
  2. 노드 중지 (graceful shutdown)
  3. 바이너리 교체
  4. 노드 재시작
  5. 동기화 상태 확인

  업데이트를 놓치면:
  → 이전 규칙으로 동작 → 네트워크에서 이탈
  → 잘못된 블록 데이터 수신 → 서비스 장애

[백업 전략]

  데이터 디렉토리 전체 백업:
  - 노드 정지 → 디스크 스냅샷 → 노드 재시작
  - 주 1회 권장
  - 클라우드: EBS 스냅샷, GCP 디스크 스냅샷

  체인데이터만 백업:
  - /data/geth/chaindata
  - 노드 재구축 시 초기 동기화 건너뛸 수 있음

  JWT Secret 백업:
  - 실행/합의 클라이언트 간 인증에 사용
  - 분실 시 재생성 필요 (양쪽 모두 업데이트)
```

---

### 6. JSON-RPC API 노출 설정

```
[서비스용 RPC 설정]

  # 외부 서비스에 RPC 제공 시
  geth \
    --http \
    --http.addr "0.0.0.0" \        # 모든 IP 허용 (방화벽으로 제어)
    --http.port 8545 \
    --http.api "eth,net,web3" \     # 필요한 API만 노출
    --http.corsdomain "*" \
    --http.vhosts "*" \
    --ws \                          # WebSocket (이벤트 구독용)
    --ws.addr "0.0.0.0" \
    --ws.port 8546 \
    --ws.api "eth,net,web3" \
    --ws.origins "*"

[보안 주의사항]

  절대 노출하면 안 되는 API:
  - personal: 계정 잠금/해제, 서명
  - admin: 노드 관리, 피어 추가/제거
  - debug: 트레이싱, 메모리 덤프
  - miner: 채굴 제어 (PoW)

  안전하게 노출 가능한 API:
  - eth: 블록, 트랜잭션, 잔액 조회
  - net: 네트워크 상태
  - web3: 유틸리티 (sha3 등)
  - txpool: 트랜잭션 풀 상태 (주의해서)

  방화벽 설정:
  - RPC 포트(8545/8546)는 내부 네트워크에서만 접근
  - 외부 노출 필요 시 Nginx 리버스 프록시 + Rate Limit
  - P2P 포트(30303)는 외부에 오픈 (피어 연결용)

[Nginx 리버스 프록시 설정]

  server {
    listen 443 ssl;
    server_name rpc.example.com;

    location / {
      proxy_pass http://localhost:8545;
      proxy_http_version 1.1;

      # Rate Limiting
      limit_req zone=rpc burst=20 nodelay;

      # 허용 메서드만 (eth_sendRawTransaction 차단 가능)
      # 커스텀 미들웨어로 JSON-RPC 메서드 필터링
    }

    # WebSocket
    location /ws {
      proxy_pass http://localhost:8546;
      proxy_http_version 1.1;
      proxy_set_header Upgrade $http_upgrade;
      proxy_set_header Connection "upgrade";
    }
  }
```

---

### 7. 모니터링

```
[노드 모니터링 지표]

  Geth 내장 메트릭 (--metrics 플래그):
  - chain/head/block: 최신 블록 번호
  - chain/head/receipt: 최신 receipt 블록
  - p2p/peers: 연결된 피어 수
  - txpool/pending: pending Tx 수
  - chain/reorg/add: Reorg로 추가된 블록
  - chain/reorg/drop: Reorg로 제거된 블록
  - system/memory/allocs: 메모리 할당량

  Prometheus 연동:
  geth --metrics --metrics.addr "0.0.0.0" --metrics.port 6060

  외부 도구:
  - ethstats.net: 이더리움 노드 상태 대시보드
  - Beaconcha.in: Validator 상태 모니터링
  - Grafana + Prometheus: 커스텀 대시보드

[알림 규칙]

  CRITICAL:
  - 블록 동기화 10분 이상 지연
  - 피어 수 0
  - 디스크 사용률 95% 이상
  - 프로세스 다운

  WARNING:
  - 블록 동기화 2분 이상 지연
  - 피어 수 5 미만
  - 디스크 사용률 80% 이상
  - 메모리 사용률 90% 이상
  - 하드포크 7일 이내 (업데이트 필요)
```

---

### 8. 멀티노드 아키텍처

```
[프로덕션 환경 노드 구성]

  ┌─────────────────────────────────────────────────────┐
  │                  Load Balancer                       │
  │  (Round Robin + Health Check)                       │
  └───────┬──────────────┬──────────────┬───────────────┘
          │              │              │
  ┌───────▼──────┐ ┌────▼─────────┐ ┌──▼──────────────┐
  │ Geth Node 1  │ │ Geth Node 2  │ │ Erigon Node 3   │
  │ (Primary)    │ │ (Secondary)  │ │ (Archive)        │
  │ Snap Sync    │ │ Snap Sync    │ │ Full History     │
  │ 읽기/쓰기    │ │ 읽기 전용    │ │ 과거 조회 전용   │
  └──────────────┘ └──────────────┘ └─────────────────┘

  역할 분리:
  - Node 1: Tx 전송 + 이벤트 리스닝 (Primary)
  - Node 2: 잔액/블록 조회 (읽기 부하 분산)
  - Node 3: Archive 조회 (과거 시점 잔액, 디버깅)

  + SaaS RPC (Alchemy/Infura): 최후 폴백

  Health Check:
  - eth_blockNumber 호출 → 최신 블록 번호 비교
  - 노드 간 10블록 이상 차이 → 비정상 노드 제외
  - 응답 시간 3초 이상 → 비정상 노드 제외

[클라이언트 다양성]

  단일 클라이언트(예: Geth만)의 위험:
  → Geth 버그가 발생하면 모든 노드가 동시에 문제
  → 네트워크에서 이탈 가능

  권장:
  Primary: Geth
  Secondary: Nethermind 또는 Reth
  → 한쪽에 버그가 있어도 다른 쪽이 정상 동작
```

---

## 헷갈렸던 포인트

### Q1: 풀노드 vs Alchemy/Infura, 어떤 걸 써야 하나?

```
[선택 기준]

  SaaS RPC (Alchemy, Infura) 적합:
  - 초기 스타트업 / MVP
  - 요청량이 적음 (일 100만 건 이하)
  - 운영 인력 부족
  - 빠른 시작 필요

  자체 풀노드 적합:
  - 대량 요청 (일 1000만+ 건)
  - 프라이버시 중요 (Tx 정보 비노출)
  - SaaS 장애 리스크 회피
  - 커스텀 RPC 기능 필요 (debug, trace)
  - 규제 요구 (데이터 주권)

  실무 권장: 하이브리드
  - Primary: 자체 풀노드
  - Fallback: Alchemy/Infura
  - Archive 조회: Alchemy (자체 Archive 비용 높음)
```

### Q2: 초기 동기화가 너무 오래 걸리면?

```
[동기화 가속 방법]

  1. Snap Sync 사용 (Geth 기본):
     12~24시간 소요 (NVMe SSD 기준)
     최신 상태 스냅샷을 받고 이후 블록만 실행

  2. Checkpoint Sync (합의 클라이언트):
     최근 Finalized Checkpoint에서 시작
     → 합의 계층 동기화가 훨씬 빠름

  3. 스냅샷 복원:
     다른 노드의 chaindata를 복사해서 시작
     → 동기화 시간 거의 없음
     → 신뢰할 수 있는 소스에서만!

  4. 하드웨어 최적화:
     NVMe SSD 필수 (SATA SSD도 느림)
     RAM 32GB+ (캐시 효율)
     네트워크 100Mbps+ (피어 통신)
```

### Q3: Execution Client + Consensus Client, 왜 둘 다 필요한가?

```
[The Merge 이후의 이더리움 아키텍처]

  The Merge 이전 (PoW):
    Geth 하나로 모든 것을 처리
    블록 생성(채굴) + EVM 실행 + 상태 관리

  The Merge 이후 (PoS):
    역할이 분리됨

    Consensus Client (합의 계층):
    - Beacon Chain 동기화
    - Validator 관리
    - 블록 제안/투표
    - Finality 추적

    Execution Client (실행 계층):
    - EVM으로 트랜잭션 실행
    - State Trie 관리
    - Transaction Pool 관리
    - JSON-RPC API 제공

  통신: Engine API (JWT 인증, localhost:8551)

  Consensus → Execution: "이 블록의 Tx들을 실행해 줘"
  Execution → Consensus: "실행 결과는 이거야 (stateRoot)"

  → 둘 중 하나만 있으면 노드가 동작하지 않음
```

---

## 참고 자료

| 자료 | 설명 |
|------|------|
| [Geth Documentation](https://geth.ethereum.org/docs/) | Geth 공식 문서 |
| [Ethereum Node Guide](https://ethereum.org/en/developers/docs/nodes-and-clients/) | 이더리움 공식 노드/클라이언트 가이드 |
| [Reth Book](https://paradigmxyz.github.io/reth/) | Reth(Rust 실행 클라이언트) 문서 |
| [Prysm Documentation](https://docs.prylabs.network/) | Prysm 합의 클라이언트 문서 |
| [Lighthouse Book](https://lighthouse-book.sigmaprime.io/) | Lighthouse 합의 클라이언트 문서 |
| [ethPandaOps — Node Monitoring](https://ethpandaops.io/) | 이더리움 인프라 모니터링 도구 |
| [Client Diversity](https://clientdiversity.org/) | 클라이언트 다양성 현황 대시보드 |
