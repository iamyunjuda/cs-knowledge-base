# CS Knowledge Base

헷갈리기 쉬운 CS 지식들을 주제별로 정리하는 저장소입니다.

📖 **블로그**: [https://iamyunjuda.github.io/cs-knowledge-base/](https://iamyunjuda.github.io/cs-knowledge-base/)

## 목차

### Java / JVM

- [JVM 동작 원리 — 다른 언어와의 비교 및 버전별 변화](java-jvm/jvm-internals.md)
  - JVM의 코드 실행 과정, HotSpot Tiered Compilation, 다른 언어(C/C++, Python, C#, Go, JS)와의 실행 모델 비교, Java 버전별 JVM 주요 변화
- [JVM 메모리 구조](java-jvm/jvm-memory-structure.md)
  - Heap(세대별 구조, G1GC, ZGC), Method Area(PermGen → Metaspace), JVM Stack, String Pool, Direct Memory, 주요 OOM 에러 정리

### Network

- [HTTP/HTTPS와 TCP의 관계](network/http-tcp-relationship.md)
  - TCP 위에서 동작하는 HTTP/HTTPS/WebSocket, 프로토콜 계층 구조, localhost와 DNS 해석 순서, hosts 파일 활용
- [L4 / L7 로드밸런서 — 차이점과 실무 선택 기준](network/l4-l7-load-balancer.md)
  - L4(IP+Port) vs L7(HTTP 내용) 동작 차이, NAT/DSR 방식, TLS 종료, K8s Service(L4)+Ingress(L7) 구조, AWS NLB vs ALB 선택 기준, gRPC 로드밸런싱
- [VPN 동작 원리 — 중국 GFW는 어떻게 VPN을 막고, 어떻게 뚫는가](network/vpn-and-traffic-inspection.md)
  - VPN 프로토콜별 비교(PPTP~WireGuard), GFW의 L3/L4/L7 차단 메커니즘, DPI 심층 패킷 검사, 중국에서 되는 VPN vs 안 되는 VPN, Trojan/V2Ray 우회 원리
- [프록시(Proxy)와 리버스 프록시(Reverse Proxy)](network/proxy-reverse-proxy.md)
  - Forward Proxy vs Reverse Proxy 차이, SSL Termination, API Gateway와의 관계, CDN, K8s Ingress Controller, Nginx 설정 예시
- [WebSocket 심화 — 동작 원리부터 K8s 인프라 이슈까지](network/websocket-deep-dive.md)
  - WebSocket 연결/프레임 구조, 스레드 모델(Thread-per-Connection vs Event-Driven), K8s 운영 이슈(Sticky Session, Pod간 브로드캐스트, 스케일링, Graceful Shutdown)
- [BLE 기반 친구 탐지 앱 — 블루투스 근접 감지, 거리 측정, 방향 표시의 기술 원리](network/bluetooth-friend-locator.md)
  - BLE Advertising/Scanning, RSSI 기반 거리 추정(칼만 필터), GPS 좌표 교환 방위각 계산, UWB(AoA/ToF), iOS iBeacon Region Monitoring, Android CompanionDeviceManager, WidgetKit/Live Activity, 백그라운드 BLE 스캔 전략

### Database

- [Cache Stampede 해결기 — 주기적 DB 부하 급증의 원인을 찾아서](database/cache-stampede-solving.md)
  - Thundering Herd, TTL 지터, 분산 락, 사전 워밍, Cache Stampede 원인 분석과 해결 전략

### Infra / 인프라 미들웨어

- [Kafka 심화 — 정합성, 순서 보장, 핵심 옵션 총정리](infra/kafka-deep-dive.md)
  - Partition 기반 순서 보장, Partition Key, acks(0/1/all), ISR, enable.idempotence, Consumer offset 관리(auto/manual), At Least Once/Exactly Once, Rebalancing, CooperativeStickyAssignor, 실무 설정 가이드
- [캐싱 전략 심층 분석 — 호텔 예약 vs 콘서트/쿠폰 시스템](infra/cache-strategy-hotel-vs-concert.md)
  - 멀티 레이어 캐싱(L1 Local/L2 Redis/L3 DB), 캐시 무효화 흐름(DEL+Kafka evict), Stale 윈도우, Cache Stampede 방지(setNx+spin retry), 호텔(읽기 heavy→캐시) vs 콘서트(쓰기 heavy→Redis DECR), Lua Script 중복 방지, Redis 멀티 노드 동시성 보장
- [Redis 장애 시나리오 분석 및 대응 전략 — 10만 트래픽 호텔 예약 시스템](infra/redis-failure-strategies.md)
  - Redis 4가지 용도(캐시/분산락/Rate Limit/세션), 장애 시나리오(완전 다운/Slow Redis/부분 장애), Circuit Breaker(Resilience4j), 2-Tier 캐싱(Caffeine+Redis), 분산 락 폴백(DB 비관적 락 유지), Redis Sentinel vs Cluster, 장애 대응 플레이북

### Blockchain / Web3

- [Web3 / 지갑 / 이더리움 네트워크 생태계 — 백엔드 개발자를 위한 총정리](blockchain/web3-ethereum-ecosystem.md)
  - Web2 vs Web3 차이, 이더리움 구조(EVM/Gas/EIP-1559), EOA/CA 계정 체계, HD Wallet(BIP-39/44), 스마트 컨트랙트(Solidity), DeFi/NFT/ERC 토큰 표준, L2(Optimistic/ZK Rollup), SIWE 인증, 이벤트 인덱싱, 트랜잭션 관리, 참고 레포 정리
- [블록체인 Tx 엣지 케이스 — 패턴을 넘어 실전에서 터지는 것들](blockchain/blockchain-tx-edge-cases.md)
  - Tx 상태 불확실성(Pending/Lost 복구), Reorg 감지·대응(Confirmation 단계별 처리), Nonce Gap/충돌(NonceManager, 멀티 월렛 풀), RPC 노드 장애(멀티 RPC 폴백), EIP-1559 가스비 급등(동적 계산, 큐잉), 서비스별 전략 차이, Gap Recovery

### OS / 운영체제

- [CPU, RAM, SSD, HDD — 컴퓨터 핵심 부품의 근본적 차이와 트레이드오프](os/ssd-hdd-ram-comparison.md)
  - CPU 구조(Register/Cache/ALU), Cache Hit/Miss, HDD 물리적 한계(Seek/Rotation), SSD NAND Flash, SATA vs NVMe, RAM DRAM 동작, 저장장치 계층별 성능 비교, DB 인덱스/Redis/Kafka와의 연관
- [epoll, kqueue, io_uring — I/O 멀티플렉싱의 진화와 트레이드오프](os/epoll-kqueue-io-multiplexing.md)
  - select/poll 한계, epoll 동작 원리(LT/ET), kqueue 차이점, io_uring 공유 메모리 링 버퍼, Nginx/Redis/Node.js/Netty가 사용하는 I/O 모델, libuv/mio 크로스 플랫폼 추상화
- [비동기 처리 방식 비교 — Spring MVC, Netty, Coroutine, WebFlux](os/async-processing-comparison.md)
  - Thread-per-Request vs Event Loop, Netty 구조, WebFlux(Reactor), Kotlin Coroutine suspend, Java Virtual Thread(Loom), 실무 선택 기준
- [언어별 비동기 구현 방식 — 내부 동작 원리부터 프레임워크 주의점까지](os/async-patterns-by-language.md)
  - JS/Node.js(Event Loop, libuv), Python(asyncio, GIL), Go(Goroutine, GMP), Java(CompletableFuture, Virtual Thread), Kotlin(Structured Concurrency), C#(async/await, SynchronizationContext), Rust(Future, tokio), 리액티브 프로그래밍(Reactive Streams, Backpressure, Mono/Flux, RxJS, Kotlin Flow), 프레임워크별 주의점
- [운영체제 구조와 커널(Kernel) 심화](os/kernel-and-os-structure.md)
  - 유저 모드 vs 커널 모드, CPU Ring 구조, 커널 구성 요소(프로세스/메모리/파일시스템/네트워크), Monolithic vs Microkernel, Linux 커널과 컨테이너 기술의 관계
- [커널(Kernel)이 뭔데? — 쉽게 이해하는 운영체제의 심장](os/kernel-easy-guide.md)
  - 커널의 5가지 역할(프로세스/메모리/파일시스템/디바이스/네트워크), 유저 모드 vs 커널 모드 쉬운 설명, System Call, Java/Spring 개발자가 알아야 하는 커널 이슈
- [이벤트 기반 시스템에서의 Lock 처리 — 초고트래픽 환경의 동시성 제어](os/event-driven-locking.md)
  - 분산 Lock(Redis/Redisson/DB), 0.000001초 차이 요청 처리, 원자적 연산(DECR), 메시지 큐 직렬화, Fencing Token, 선착순 쿠폰 발급 설계
- [재고 동기화와 Lock 전략 — 이커머스 동시성 문제의 모든 것](os/inventory-lock-strategy.md)
  - Lost Update, 비관적/낙관적 Lock, Redis DECR 재고 차감, Redis-DB 불일치 해결(DLQ/Outbox/Reconciliation), 장바구니 다중 차감(Lua/Saga), 면접 답변 전략
- [컨테이너 vs 가상머신 — Docker, Kubernetes, 그리고 왜 컨테이너인가](os/container-vs-vm.md)
  - VM vs Container 구조 비교, Namespace/cgroups/OverlayFS, Docker와 K8s의 관계, 컨테이너 보안(gVisor/Kata), 컨테이너 런타임(containerd/CRI-O/Podman)

### Design Pattern / 설계 패턴

- [분산 시스템 핵심 패턴 — 동시성, 트랜잭션, 메시징, 데이터 정합성](design-pattern/distributed-system-patterns.md)
  - 비관적/낙관적/분산 락, ACID vs BASE, 2PC/Saga/Outbox 패턴, 전달 보장 모델(At-Least-Once), 멱등성, Block Finality/Nonce/ERC-20/HD Wallet/Gas, Circuit Breaker/CEI/Graceful Degradation, Reconciliation/Source of Truth/Eventual Consistency, CAP 정리, Node.js 이벤트 루프, Reentrancy 공격

### Git

- [Rebase Merge vs Squash Merge — Git 병합 전략의 차이와 선택 기준](git/merge-strategies.md)
  - Merge Commit / Rebase Merge / Squash Merge 비교, 커밋 보존 여부, 히스토리 형태 차이, Squash 후 브랜치 삭제 이유, 실무 전략 선택 기준

### Map System / 지도 시스템

- [공간 인덱싱과 지도 시스템 기초 — POI, 타일링, Geocoding](map-system/spatial-indexing-and-map-fundamentals.md)
  - R-Tree/Geohash/S2/H3 공간 인덱싱, POI 데이터 모델, 지도 타일링(래스터/벡터), Geocoding/Reverse Geocoding, 경로 탐색 알고리즘(Dijkstra/A*/CH), PostGIS vs OpenSearch, 사우디 지도 특수성
- [글로벌 로컬라이징 아키텍처 — i18n, L10n, 다국어/다지역 서비스 설계](map-system/global-localization-architecture.md)
  - Locale 체계(BCP 47), API Locale 전달, 다국어 DB 저장 패턴(JSONB/번역 테이블), OpenSearch 다국어 분석기, 날짜/시간/통화 로컬라이징, RTL 아랍어 지원, L10n Layer 아키텍처, TMS 번역 관리
- [대규모 지도 데이터 파이프라인 — 실시간/배치 처리, ETL, 데이터 모델링](map-system/map-data-pipeline.md)
  - 지도 데이터 소스, Spark/Flink 배치·실시간 파이프라인, POI 중복 제거(Entity Resolution), CDC(Debezium), 영업시간 모델링, Lambda/Kappa 아키텍처, Map Matching, 데이터 품질 관리
- [글로벌 트래픽 대응 아키텍처 — 멀티리전, CDN, 대규모 서비스 운영](map-system/global-traffic-architecture.md)
  - 멀티리전 배포(Single-Writer + Read Replica), CDN 타일 캐싱 전략, API 성능 최적화, Circuit Breaker/Graceful Degradation, Rate Limiting, 분산 추적(OpenTelemetry), 해외 개발자 협업
