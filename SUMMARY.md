# 목차

### Spring

- [판매 통계 API가 느려진 진짜 이유 — DB 커넥션 풀 고갈 추적기](topics/spring/api-latency-db-connection-pool.md)
  - HikariCP 커넥션 풀 고갈 원인 분석, 예외 없는 500 에러의 정체, @Transactional AOP 프록시 단 실패, 커넥션 풀 모니터링/사이즈 적정화, 슬로우 쿼리/트랜잭션 최적화
- [@Transactional과 예외 처리 — 커넥션 풀 타임아웃이 500인데 로그가 안 남는 이유](topics/spring/transactional-exception-flow.md)
  - Spring 요청 처리 파이프라인, AOP 프록시 커넥션 획득 시점, CannotCreateTransactionException, 예외가 삼켜지는 4가지 시나리오, 500 vs 503 선택, 로그 없는 500 방지 체크리스트
- [DB 커넥션 풀 동작 원리 — HikariCP 내부 구조부터 DB별 스레드 모델까지](topics/spring/connection-pool-internals.md)
  - HikariCP ConcurrentBag/ThreadLocal 최적화, 커넥션 획득·반납 흐름, @Transactional 유무에 따른 커넥션 생명주기, MySQL(멀티스레드) vs PostgreSQL(멀티프로세스) vs Oracle 비교, 커넥션 풀 사이즈 공식, R2DBC
- [Spring 요청 처리 사각지대 — 로그가 안 남는 에러들의 정체](topics/spring/request-processing-blind-spots.md)
  - Tomcat 스레드 풀 포화 모니터링(Micrometer/JMX), SimpleAsyncTaskExecutor 예외 삼킴 원인, Filter 단 JWT 검증과 예외 처리, ResponseBody 직렬화 실패(committed 후 문제), Servlet Container vs Spring 관계
- [SimpleAsyncTaskExecutor vs ThreadPoolTaskExecutor — Spring 비동기 실행기의 차이와 선택 기준](topics/spring/task-executor-comparison.md)
  - SimpleAsyncTaskExecutor(매번 new Thread) vs ThreadPoolTaskExecutor(풀 재사용) 내부 구조, core/max/queue 동작 흐름, RejectedExecutionHandler 정책(CallerRunsPolicy), 용도별 다중 Executor 설정, Virtual Thread 조합, 모니터링
- [면접 실전 — 서비스 하나가 느릴 때 코루틴/비동기 해결 전략](topics/spring/coroutine-async-interview-deep-dive.md)
  - 면접 시나리오별 해결책(병렬/비동기분리/캐싱), Coroutine 설정·Dispatcher, Controller vs Service 역할, coroutineScope vs supervisorScope, Spring MVC vs WebFlux 선택, CompletableFuture 대안, 집요한 후속 질문 대비
- [Tomcat 내부 구조 — Catalina, Coyote, Jasper는 각각 뭔가](topics/spring/tomcat-architecture.md)
  - Coyote(HTTP 엔진) vs Catalina(Servlet 엔진) vs Jasper(JSP 엔진), Server→Service→Engine→Host→Context 계층, Valve Pipeline vs Filter Chain, catalina.out 로그, ErrorReportValve가 HTML을 반환하는 이유, 내장 Tomcat 설정
- [Tomcat Thread Pool vs DB Connection Pool — 완전히 다른 두 풀의 역할과 관계](topics/spring/tomcat-vs-db-thread-pool.md)
  - Tomcat 워커 스레드 풀 vs HikariCP 커넥션 풀 차이, 요청 흐름에서의 위치, 크기 불균형(200 vs 10) 이유, 풀 고갈 시 연쇄 장애, @Transactional 범위와 커넥션 점유, 모니터링 키 메트릭

### Java / JVM

- [JVM 동작 원리 — 다른 언어와의 비교 및 버전별 변화](topics/java-jvm/jvm-internals.md)
  - JVM의 코드 실행 과정, HotSpot Tiered Compilation, 다른 언어(C/C++, Python, C#, Go, JS)와의 실행 모델 비교, Java 버전별 JVM 주요 변화
- [JVM 메모리 구조](topics/java-jvm/jvm-memory-structure.md)
  - Heap(세대별 구조, G1GC, ZGC), Method Area(PermGen → Metaspace), JVM Stack, String Pool, Direct Memory, 주요 OOM 에러 정리
- [Java Thread vs CompletableFuture vs Kotlin Coroutine — 근본적으로 다른 계층의 개념](topics/java-jvm/thread-future-coroutine-comparison.md)
  - Thread(OS 자원) vs CompletableFuture(결과 컨테이너/API) vs Coroutine(언어 기능), 추상화 레벨 비교, 동일 문제 세 가지 풀이, ForkJoinPool, Virtual Thread 포지션, Structured Concurrency
- [JVM 아키텍처 심화 — ClassLoader·Class 파일 구조·Execution Engine](topics/java-jvm/jvm-architecture-deep-dive.md)
  - JDK/JRE/JVM 관계, JDK 8→9 모듈 시스템, Class 파일 구조와 javap 바이트코드 분석, ClassLoader 3단계(Loading/Linking[Verification·Preparation·Resolution]/Initialization), Parent Delegation Model, Execution Engine(Interpreter·JIT·GC), JNI, `<clinit>` vs `<init>`, ClassNotFoundException vs NoClassDefFoundError

### Network

- [HTTP/HTTPS와 TCP의 관계](topics/network/http-tcp-relationship.md)
  - TCP 위에서 동작하는 HTTP/HTTPS/WebSocket, 프로토콜 계층 구조, localhost와 DNS 해석 순서, hosts 파일 활용
- [L4 / L7 로드밸런서 — 차이점과 실무 선택 기준](topics/network/l4-l7-load-balancer.md)
  - L4(IP+Port) vs L7(HTTP 내용) 동작 차이, NAT/DSR 방식, TLS 종료, K8s Service(L4)+Ingress(L7) 구조, AWS NLB vs ALB 선택 기준, gRPC 로드밸런싱
- [VPN 동작 원리 — 중국 GFW는 어떻게 VPN을 막고, 어떻게 뚫는가](topics/network/vpn-and-traffic-inspection.md)
  - VPN 프로토콜별 비교(PPTP~WireGuard), GFW의 L3/L4/L7 차단 메커니즘, DPI 심층 패킷 검사, 중국에서 되는 VPN vs 안 되는 VPN, Trojan/V2Ray 우회 원리
- [프록시(Proxy)와 리버스 프록시(Reverse Proxy)](topics/network/proxy-reverse-proxy.md)
  - Forward Proxy vs Reverse Proxy 차이, SSL Termination, API Gateway와의 관계, CDN, K8s Ingress Controller, Nginx 설정 예시
- [Tor와 어니언 라우팅 — 익명 통신의 원리부터 블록체인 활용까지](topics/network/tor-onion-routing.md)
  - 어니언 라우팅(3중 암호화/복호화), Guard/Middle/Exit 노드 역할, Circuit Telescoping, Hidden Service(.onion), Tor vs VPN vs 프록시 비교, 비트코인 Tor 노드 운영, 트래픽 상관관계 공격, Dandelion++, Directory Authority
- [Tor vs Nostr — 둘 다 탈중앙화인데 뭐가 다른 거야?](topics/network/tor-vs-nostr.md)
  - Tor(익명 통신) vs Nostr(검열 저항 SNS) 근본 차이, Nostr 이벤트/릴레이 구조, 공개키 기반 계정, Tor+Nostr 조합, 비트코인 생태계 내 위치, 검열 저항 메커니즘
- [WebSocket 심화 — 동작 원리부터 K8s 인프라 이슈까지](topics/network/websocket-deep-dive.md)
  - WebSocket 연결/프레임 구조, 스레드 모델(Thread-per-Connection vs Event-Driven), K8s 운영 이슈(Sticky Session, Pod간 브로드캐스트, 스케일링, Graceful Shutdown)
- [Cross-Region 라우팅 헤더 설계 — X-Region-Info 기반 지역 간 서버 통신](topics/network/cross-region-routing-header.md)
  - X-Region-Info 헤더 설계, Gateway 라우팅 로직, Region Registry, 헤더 위조 방지(Strip+HMAC), mTLS 지역 간 인증, Replay Attack 방지, Data Residency, Hop Count 무한루프 방지, Rate Limiting, 장애 Fallback

### Database

- [Cache Stampede 해결기 — 주기적 DB 부하 급증의 원인을 찾아서](topics/database/cache-stampede-solving.md)
  - Thundering Herd, TTL 지터, 분산 락, 사전 워밍, Cache Stampede 원인 분석과 해결 전략
- [ORM vs ODM vs OOM — 객체 매핑 기술의 차이](topics/database/orm-odm-oom-comparison.md)
  - ORM(객체↔RDB), ODM(객체↔Document DB), OOM(객체↔객체) 비교, JPA/Hibernate vs Mongoose vs MapStruct, MyBatis는 SQL Mapper, Spring Data 추상화
- [MongoDB 심화 — mongos/mongod 아키텍처, Null 인덱스 처리, Replica 지연 해결 전략](topics/database/mongodb-replication-optimization.md)
  - mongod/mongos 역할 비교, Sharded Cluster 쿼리 흐름, null/missing 인덱스 처리(Partial/Sparse Index), Replica Set 복제 지연 원인 분석, Causal Consistency Session, Write-Through Cache, CQRS, Change Stream 실시간 전략
- [MongoDB 복잡한 Order 구조에서 매출 총액 집계 설계](topics/database/mongodb-revenue-aggregation.md)
  - Aggregation Pipeline, 사전 계산 필드(Pre-computed Field), Materialized View($merge), $unwind vs $reduce, 복합 인덱스/Covered Query, Spring Data MongoDB 구현, Change Stream 실시간 갱신, 대규모 데이터 전략(Sharding/CQRS/ClickHouse), 증분 갱신+Reconciliation, 매출 오차 검증·테스트·자동 보정, 멱등성 보장, 배포 중 통계 정합성(Graceful Shutdown/Outbox/배포 구간 재검증/스키마 하위 호환/ShedLock)
- [MongoDB 세션 관리 심화 — RDB 커넥션과의 근본적 차이, Spring Data MongoDB 실전](topics/database/mongodb-session-management.md)
  - RDB 커넥션=세션(1:1) vs MongoDB lsid 기반 논리 세션(N:M), 커넥션 풀 동작 차이, 암시적/명시적 세션, MongoTemplate+ClientSession, @Transactional, Causal Consistency Session, Reactive 환경, 세션 누수 방지, Sharded 트랜잭션 주의점

### Infra / 인프라 미들웨어

- [Kafka 심화 — 정합성, 순서 보장, 핵심 옵션 총정리](topics/infra/kafka-deep-dive.md)
  - Partition 기반 순서 보장, Partition Key, acks(0/1/all), ISR, enable.idempotence, Consumer offset 관리(auto/manual), At Least Once/Exactly Once, Rebalancing, CooperativeStickyAssignor, 실무 설정 가이드
- [캐싱 전략 심층 분석 — 호텔 예약 vs 콘서트/쿠폰 시스템](topics/infra/cache-strategy-hotel-vs-concert.md)
  - 멀티 레이어 캐싱(L1 Local/L2 Redis/L3 DB), 캐시 무효화 흐름(DEL+Kafka evict), Stale 윈도우, Cache Stampede 방지(setNx+spin retry), 호텔(읽기 heavy→캐시) vs 콘서트(쓰기 heavy→Redis DECR), Lua Script 중복 방지, Redis 멀티 노드 동시성 보장
- [Redis 장애 시나리오 분석 및 대응 전략 — 10만 트래픽 호텔 예약 시스템](topics/infra/redis-failure-strategies.md)
  - Redis 4가지 용도(캐시/분산락/Rate Limit/세션), 장애 시나리오(완전 다운/Slow Redis/부분 장애), Circuit Breaker(Resilience4j), 2-Tier 캐싱(Caffeine+Redis), 분산 락 폴백(DB 비관적 락 유지), Redis Sentinel vs Cluster, 장애 대응 플레이북

### Blockchain / Web3

- [Web3 / 지갑 / 이더리움 네트워크 생태계 — 백엔드 개발자를 위한 총정리](topics/blockchain/web3-ethereum-ecosystem.md)
  - Web2 vs Web3 차이, 이더리움 구조(EVM/Gas/EIP-1559), EOA/CA 계정 체계, HD Wallet(BIP-39/44), 스마트 컨트랙트(Solidity), DeFi/NFT/ERC 토큰 표준, L2(Optimistic/ZK Rollup), SIWE 인증, 이벤트 인덱싱, 트랜잭션 관리, 참고 레포 정리
- [블록체인 Tx 엣지 케이스 — 패턴을 넘어 실전에서 터지는 것들](topics/blockchain/blockchain-tx-edge-cases.md)
  - Tx 상태 불확실성(Pending/Lost 복구), Reorg 감지·대응(Confirmation 단계별 처리), Nonce Gap/충돌(NonceManager, 멀티 월렛 풀), RPC 노드 장애(멀티 RPC 폴백), EIP-1559 가스비 급등(동적 계산, 큐잉), 서비스별 전략 차이, Gap Recovery
- [블록체인 서비스 DB 스키마 설계 — 트랜잭션 무결성과 정합성](topics/blockchain/blockchain-db-schema-design.md)
  - Tx 테이블(멱등성 키, 상태 전이 이력), 지갑/입금 주소 관리, 이벤트 인덱싱 스키마, 잔액 원장(이중 기장), Outbox 패턴, 비관적 잠금, Reconciliation, NUMERIC(78,0), 인덱스/파티셔닝 전략
- [블록체인 모니터링 시스템 — 설계, 지표, 알림, 운영](topics/blockchain/blockchain-monitoring-system.md)
  - Tx 상태/Nonce/가스비/지갑 잔액/RPC/이벤트 리스너 모니터링 지표, Prometheus+Grafana 아키텍처, 알림 등급(P1~P3) 설계, 대시보드 레이아웃, 온체인 감시(Defender/Forta), 백오피스 연동, 인시던트 대응 플레이북
- [블록체인 분산 네트워크 — 중앙 서버 없이 20만 노드가 연결되는 원리](topics/blockchain/distributed-network-p2p.md)
  - 부트스트랩 노드(Seed Node), Kademlia DHT 노드 탐색, devp2p/RLPx 프로토콜 스택, 가십 프로토콜(Gossip) 블록/Tx 전파, 비트코인 DNS Seed/addr 메시지/Compact Block Relay(BIP 152)/Headers-First Sync/Eviction 정책/BIP 324 암호화, 이더리움 vs 비트코인 설계 철학 비교
- [합의 메커니즘 심화 — PoW, PoS, Reorg, Block Finality](topics/blockchain/consensus-mechanisms.md)
  - PoW 채굴/난이도 조정/51% 공격, PoS Validator/Slashing/Epoch, PoW vs PoS 비교, Block Finality(확률적 vs 결정적), Reorg 심화(PoS Reorg, 감지 시스템), DPoS/PBFT/PoA/PoH, The Merge 전후 변화
- [ERC 토큰 표준 심화 — ERC-20, 721, 1155, 4337, 백엔드 구현](topics/blockchain/erc-token-standards.md)
  - ERC-20(approve/transferFrom, decimals 함정, 비표준 토큰), ERC-721(NFT, tokenURI, 메타데이터), ERC-1155(멀티 토큰, 배치 전송, 가스 효율), ERC-4337(계정 추상화, Bundler, Paymaster), ERC-2612(Permit), 거래소 토큰 상장 체크리스트
- [풀노드 운영 — Geth, OpenEthereum(Parity), 동기화, 유지보수](topics/blockchain/full-node-operations.md)
  - Full/Archive/Light Node 차이, Geth 설치·설정·동기화 모드(snap/full/archive), Execution+Consensus 클라이언트, 하드웨어 요구사항, Pruning, 하드포크 대응, JSON-RPC 보안 설정, 멀티노드 아키텍처, 클라이언트 다양성
- [키 관리 및 보안 시스템 — KMS, HSM, MPC, 서명 아키텍처](topics/blockchain/key-management-security.md)
  - HSM 물리적 보안, AWS/GCP KMS 서명 흐름, MPC(TSS/DKG) vs 멀티시그, Hot/Warm/Cold Wallet 계층 구조, 서명 파이프라인(Policy Engine), 키 순환, 보안 감사, 실제 사고 사례(Ronin/Atomic/Slope)
- [스마트 컨트랙트 & dApp 개발 — 개발 라이프사이클, 테스트, 보안, 배포](topics/blockchain/smart-contract-dapp-development.md)
  - Hardhat vs Foundry, 테스트 전략(유닛/Fuzz/Invariant/Fork), 보안 취약점(Reentrancy/Flash Loan/Access Control), CEI 패턴, Proxy 업그레이드(UUPS/Transparent), dApp 백엔드 아키텍처, The Graph, Meta-Transaction, Solidity Clean Code
- [VASP 지갑 운영 — 거래소 지갑 아키텍처, Travel Rule, 규제 준수](topics/blockchain/vasp-wallet-operations.md)
  - VASP 정의/유형, 거래소 지갑 구조(Sweep/Omnibus), 입출금 처리 플로우, Travel Rule(FATF/특금법/CODE/VerifyVASP), AML/KYC 연동, 주소 귀속 확인, 거래소 백엔드 시스템 구성, 멀티체인 지원

### OS / 운영체제

- [CPU, RAM, SSD, HDD — 컴퓨터 핵심 부품의 근본적 차이와 트레이드오프](topics/os/ssd-hdd-ram-comparison.md)
  - CPU 구조(Register/Cache/ALU), Cache Hit/Miss, HDD 물리적 한계(Seek/Rotation), SSD NAND Flash, SATA vs NVMe, RAM DRAM 동작, 저장장치 계층별 성능 비교, DB 인덱스/Redis/Kafka와의 연관
- [epoll, kqueue, io_uring — I/O 멀티플렉싱의 진화와 트레이드오프](topics/os/epoll-kqueue-io-multiplexing.md)
  - select/poll 한계, epoll 동작 원리(LT/ET), kqueue 차이점, io_uring 공유 메모리 링 버퍼, Nginx/Redis/Node.js/Netty가 사용하는 I/O 모델, libuv/mio 크로스 플랫폼 추상화
- [비동기 처리 방식 비교 — Spring MVC, Netty, Coroutine, WebFlux](topics/os/async-processing-comparison.md)
  - Thread-per-Request vs Event Loop, Netty 구조, WebFlux(Reactor), Kotlin Coroutine suspend, Java Virtual Thread(Loom), 실무 선택 기준
- [언어별 비동기 구현 방식 — 내부 동작 원리부터 프레임워크 주의점까지](topics/os/async-patterns-by-language.md)
  - JS/Node.js(Event Loop, libuv), Python(asyncio, GIL), Go(Goroutine, GMP), Java(CompletableFuture, Virtual Thread), Kotlin(Structured Concurrency), C#(async/await, SynchronizationContext), Rust(Future, tokio), 리액티브 프로그래밍(Reactive Streams, Backpressure, Mono/Flux, RxJS, Kotlin Flow), 프레임워크별 주의점
- [면접에서 "비동기를 구현해보라"고 했을 때 — 접근법과 답변 전략](topics/os/async-implementation-interview.md)
  - 비동기 본질(커피숍 비유), 3단계 답변 전략, Thread+Callback→Future 패턴 구현, 언어별 답변(Java/JS/Kotlin/Python), 후속 질문 대비(Event Loop, Non-blocking vs 비동기, 트레이드오프)
- [운영체제 구조와 커널(Kernel) 심화](topics/os/kernel-and-os-structure.md)
  - 유저 모드 vs 커널 모드, CPU Ring 구조, 커널 구성 요소(프로세스/메모리/파일시스템/네트워크), Monolithic vs Microkernel, Linux 커널과 컨테이너 기술의 관계
- [커널(Kernel)이 뭔데? — 쉽게 이해하는 운영체제의 심장](topics/os/kernel-easy-guide.md)
  - 커널의 5가지 역할(프로세스/메모리/파일시스템/디바이스/네트워크), 유저 모드 vs 커널 모드 쉬운 설명, System Call, Java/Spring 개발자가 알아야 하는 커널 이슈
- [이벤트 기반 시스템에서의 Lock 처리 — 초고트래픽 환경의 동시성 제어](topics/os/event-driven-locking.md)
  - 분산 Lock(Redis/Redisson/DB), 0.000001초 차이 요청 처리, 원자적 연산(DECR), 메시지 큐 직렬화, Fencing Token, 선착순 쿠폰 발급 설계
- [재고 동기화와 Lock 전략 — 이커머스 동시성 문제의 모든 것](topics/os/inventory-lock-strategy.md)
  - Lost Update, 비관적/낙관적 Lock, Redis DECR 재고 차감, Redis-DB 불일치 해결(DLQ/Outbox/Reconciliation), 장바구니 다중 차감(Lua/Saga), 면접 답변 전략
- [컨테이너 vs 가상머신 — Docker, Kubernetes, 그리고 왜 컨테이너인가](topics/os/container-vs-vm.md)
  - VM vs Container 구조 비교, Namespace/cgroups/OverlayFS, Docker와 K8s의 관계, 컨테이너 보안(gVisor/Kata), 컨테이너 런타임(containerd/CRI-O/Podman)
- [코루틴과 비동기의 모든 것 Part 1 — 커널 레벨에서 이해하는 비동기의 본질](topics/os/coroutine-async-kernel-deep-dive.md)
  - syscall과 I/O 처리 흐름, Blocking/Non-blocking/Multiplexing, epoll/io_uring 동작 원리, 스레드 컨텍스트 스위칭 비용, 코루틴 유저 스페이스 스위칭, M:N 스케줄링(Go GMP/Kotlin Dispatcher), 커널 지식이 디버깅 무기가 되는 순간
- [코루틴과 비동기의 모든 것 Part 2 — Java/Kotlin 비동기 실전 심화](topics/os/coroutine-async-java-kotlin-practice.md)
  - CompletableFuture 내부 동작과 함정, Virtual Thread 구조/Pinning/ThreadLocal 이슈, Kotlin Coroutine CPS 변환/상태 머신, Dispatcher별 특성(Default/IO/limitedParallelism), Structured Concurrency(coroutineScope/supervisorScope), Spring+Coroutine 통합, Virtual Thread vs Coroutine 선택 기준
- [코루틴과 비동기의 모든 것 Part 3 — 실무에서 터지는 것들과 해결 패턴](topics/os/coroutine-async-production-pitfalls.md)
  - Blocking in Non-blocking Context, 예외 삼킴 5가지 패턴, MDC/Security 컨텍스트 유실, 코루틴 취소와 리소스 누수, 디버깅(스택 트레이스 끊김), 실무 아키텍처 패턴(병렬 조회/비동기 분리/Flow 배치/Rate Limiting), 비동기 도입 체크리스트

### Design Pattern / 설계 패턴

- [분산 시스템 핵심 패턴 — 동시성, 트랜잭션, 메시징, 데이터 정합성](topics/design-pattern/distributed-system-patterns.md)
  - 비관적/낙관적/분산 락, ACID vs BASE, 2PC/Saga/Outbox 패턴, 전달 보장 모델(At-Least-Once), 멱등성, Block Finality/Nonce/ERC-20/HD Wallet/Gas, Circuit Breaker/CEI/Graceful Degradation, Reconciliation/Source of Truth/Eventual Consistency, CAP 정리, Node.js 이벤트 루프, Reentrancy 공격

### Git

- [Rebase Merge vs Squash Merge — Git 병합 전략의 차이와 선택 기준](topics/git/merge-strategies.md)
  - Merge Commit / Rebase Merge / Squash Merge 비교, 커밋 보존 여부, 히스토리 형태 차이, Squash 후 브랜치 삭제 이유, 실무 전략 선택 기준

### Frontend / 프론트엔드

- [React 번들링 — Webpack, Vite, 그리고 모듈 시스템의 진화](topics/frontend/react-bundling.md)
  - JS 모듈 시스템 진화(CJS/ESM), Webpack 핵심 개념(Entry/Loader/Plugin), Vite 동작 원리(ESM 기반 개발 서버, Rollup 프로덕션 빌드), Webpack vs Vite 비교, Code Splitting/Lazy Loading, Source Map, CRA→Vite 마이그레이션
- [브라우저 동작 원리 — Chrome 기준, URL 입력부터 화면 렌더링까지](topics/frontend/browser-rendering.md)
  - Chrome 멀티 프로세스 아키텍처, URL→DNS→TCP/TLS→HTTP 흐름, HTML 파싱→DOM/CSSOM→Render Tree→Layout→Paint→Composite, V8 엔진(Ignition/TurboFan JIT), 이벤트 루프와 렌더링 관계, React Virtual DOM과 브라우저 렌더링, DevTools 성능 분석

### Map System / 지도 시스템

- [공간 인덱싱과 지도 시스템 기초 — POI, 타일링, Geocoding](topics/map-system/spatial-indexing-and-map-fundamentals.md)
  - R-Tree/Geohash/S2/H3 공간 인덱싱, POI 데이터 모델, 지도 타일링(래스터/벡터), Geocoding/Reverse Geocoding, 경로 탐색 알고리즘(Dijkstra/A*/CH), PostGIS vs OpenSearch, 사우디 지도 특수성
- [글로벌 로컬라이징 아키텍처 — i18n, L10n, 다국어/다지역 서비스 설계](topics/map-system/global-localization-architecture.md)
  - Locale 체계(BCP 47), API Locale 전달, 다국어 DB 저장 패턴(JSONB/번역 테이블), OpenSearch 다국어 분석기, 날짜/시간/통화 로컬라이징, RTL 아랍어 지원, L10n Layer 아키텍처, TMS 번역 관리
- [대규모 지도 데이터 파이프라인 — 실시간/배치 처리, ETL, 데이터 모델링](topics/map-system/map-data-pipeline.md)
  - 지도 데이터 소스, Spark/Flink 배치·실시간 파이프라인, POI 중복 제거(Entity Resolution), CDC(Debezium), 영업시간 모델링, Lambda/Kappa 아키텍처, Map Matching, 데이터 품질 관리
- [글로벌 트래픽 대응 아키텍처 — 멀티리전, CDN, 대규모 서비스 운영](topics/map-system/global-traffic-architecture.md)
  - 멀티리전 배포(Single-Writer + Read Replica), CDN 타일 캐싱 전략, API 성능 최적화, Circuit Breaker/Graceful Degradation, Rate Limiting, 분산 추적(OpenTelemetry), 해외 개발자 협업
