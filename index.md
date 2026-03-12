---
layout: default
title: Home
nav_order: 0
permalink: /
---

# CS Knowledge Base

매번 헷갈리는 CS 지식들, 한 번 정리해두면 두고두고 꺼내 보기 좋잖아요. 여기에 주제별로 차곡차곡 모아두고 있어요.
{: .fs-6 .fw-300 }

---

## 목차

### Java / JVM

| 주제 | 키워드 |
|:-----|:-------|
| [JVM 동작 원리 — 다른 언어와의 비교 및 버전별 변화]({{ site.baseurl }}/java-jvm/jvm-internals.html) | JVM 코드 실행 과정, HotSpot Tiered Compilation, C/C++·Python·Go·JS와 비교, Java 버전별 JVM 변화 |
| [JVM 메모리 구조]({{ site.baseurl }}/java-jvm/jvm-memory-structure.html) | Heap(G1GC, ZGC), PermGen → Metaspace, JVM Stack, String Pool, Direct Memory, OOM 에러 정리 |

### Network

| 주제 | 키워드 |
|:-----|:-------|
| [HTTP/HTTPS와 TCP의 관계]({{ site.baseurl }}/network/http-tcp-relationship.html) | TCP 위에서 동작하는 HTTP/HTTPS/WebSocket, 프로토콜 계층, localhost와 DNS 해석, hosts 파일 |
| [L4 / L7 로드밸런서 — 차이점과 실무 선택 기준]({{ site.baseurl }}/network/l4-l7-load-balancer.html) | L4 vs L7 동작 차이, NAT/DSR, TLS 종료, K8s Service+Ingress, AWS NLB vs ALB, gRPC |
| [VPN 동작 원리 — 중국 GFW는 어떻게 VPN을 막고, 어떻게 뚫는가]({{ site.baseurl }}/network/vpn-and-traffic-inspection.html) | VPN 프로토콜 비교, GFW 차단 메커니즘, DPI, Trojan/V2Ray 우회 원리 |
| [프록시(Proxy)와 리버스 프록시(Reverse Proxy)]({{ site.baseurl }}/network/proxy-reverse-proxy.html) | Forward vs Reverse Proxy, SSL Termination, API Gateway, CDN, Nginx 설정 예시 |
| [WebSocket 심화 — 동작 원리부터 K8s 인프라 이슈까지]({{ site.baseurl }}/network/websocket-deep-dive.html) | WebSocket 프레임 구조, 스레드 모델, K8s Sticky Session·브로드캐스트·스케일링 |

### Database

| 주제 | 키워드 |
|:-----|:-------|
| [Cache Stampede 해결기 — 주기적 DB 부하 급증의 원인을 찾아서]({{ site.baseurl }}/database/cache-stampede-solving.html) | Thundering Herd, TTL 지터, 분산 락, 사전 워밍, 원인 분석과 해결 전략 |
| [MongoDB 심화 — mongos/mongod 아키텍처, Null 인덱스 처리, Replica 지연 해결]({{ site.baseurl }}/database/mongodb-replication-optimization.html) | Sharded Cluster 쿼리 흐름, Partial/Sparse Index, 복제 지연, Causal Consistency, Change Stream |

### Infra / 인프라 미들웨어

| 주제 | 키워드 |
|:-----|:-------|
| [Kafka 심화 — 정합성, 순서 보장, 핵심 옵션 총정리]({{ site.baseurl }}/infra/kafka-deep-dive.html) | Partition 순서 보장, acks, ISR, idempotence, Consumer offset, Exactly Once, Rebalancing |
| [캐싱 전략 심층 분석 — 호텔 예약 vs 콘서트/쿠폰 시스템]({{ site.baseurl }}/infra/cache-strategy-hotel-vs-concert.html) | 멀티 레이어 캐싱, 캐시 무효화, Stampede 방지, Redis DECR, Lua Script |
| [Redis 장애 시나리오 분석 및 대응 전략 — 10만 트래픽 호텔 예약 시스템]({{ site.baseurl }}/infra/redis-failure-strategies.html) | Redis 4가지 용도, Circuit Breaker, 2-Tier 캐싱, Sentinel vs Cluster, 장애 플레이북 |

### Blockchain / Web3

| 주제 | 키워드 |
|:-----|:-------|
| [Web3 / 지갑 / 이더리움 생태계 — 백엔드 개발자를 위한 총정리]({{ site.baseurl }}/blockchain/web3-ethereum-ecosystem.html) | Web2 vs Web3, EVM/Gas/EIP-1559, HD Wallet, 스마트 컨트랙트, DeFi/NFT, L2 Rollup |
| [블록체인 Tx 엣지 케이스 — 실전에서 터지는 것들]({{ site.baseurl }}/blockchain/blockchain-tx-edge-cases.html) | Pending/Lost Tx 복구, Reorg 감지, Nonce Gap, 멀티 RPC 폴백, EIP-1559 가스비 급등 |
| [블록체인 서비스 DB 스키마 설계 — 트랜잭션 무결성과 정합성]({{ site.baseurl }}/blockchain/blockchain-db-schema-design.html) | Tx 테이블 멱등성, 이벤트 인덱싱, 잔액 원장, Outbox 패턴, Reconciliation |
| [블록체인 모니터링 시스템 — 설계, 지표, 알림, 운영]({{ site.baseurl }}/blockchain/blockchain-monitoring-system.html) | Prometheus+Grafana, 알림 등급 설계, 온체인 감시, 인시던트 대응 플레이북 |
| [합의 메커니즘 심화 — PoW, PoS, Reorg, Block Finality]({{ site.baseurl }}/blockchain/consensus-mechanisms.html) | PoW vs PoS 비교, Slashing, Finality, DPoS/PBFT/PoA, The Merge |
| [ERC 토큰 표준 심화 — ERC-20, 721, 1155, 4337, 백엔드 구현]({{ site.baseurl }}/blockchain/erc-token-standards.html) | ERC-20 approve 함정, ERC-721 NFT, ERC-1155 배치, ERC-4337 계정 추상화, Permit |
| [풀노드 운영 — Geth, OpenEthereum, 동기화, 유지보수]({{ site.baseurl }}/blockchain/full-node-operations.html) | Full/Archive/Light Node, snap/full/archive 동기화, Pruning, 하드포크, JSON-RPC 보안 |
| [키 관리 및 보안 시스템 — KMS, HSM, MPC, 서명 아키텍처]({{ site.baseurl }}/blockchain/key-management-security.html) | HSM, AWS/GCP KMS, MPC vs 멀티시그, Hot/Warm/Cold Wallet, 실제 사고 사례 |
| [스마트 컨트랙트 & dApp 개발 — 테스트, 보안, 배포]({{ site.baseurl }}/blockchain/smart-contract-dapp-development.html) | Hardhat vs Foundry, Fuzz/Invariant 테스트, Reentrancy, Proxy 업그레이드, The Graph |
| [VASP 지갑 운영 — 거래소 지갑 아키텍처, Travel Rule, 규제 준수]({{ site.baseurl }}/blockchain/vasp-wallet-operations.html) | Sweep/Omnibus, 입출금 플로우, FATF Travel Rule, AML/KYC, 멀티체인 |

### OS / 운영체제

| 주제 | 키워드 |
|:-----|:-------|
| [CPU, RAM, SSD, HDD — 핵심 부품의 근본적 차이와 트레이드오프]({{ site.baseurl }}/os/ssd-hdd-ram-comparison.html) | CPU 캐시, HDD vs SSD, SATA vs NVMe, DRAM 동작, 저장장치 계층별 성능 비교 |
| [epoll, kqueue, io_uring — I/O 멀티플렉싱의 진화]({{ site.baseurl }}/os/epoll-kqueue-io-multiplexing.html) | select/poll 한계, epoll LT/ET, io_uring 링 버퍼, Nginx/Redis/Node.js I/O 모델 |
| [비동기 처리 방식 비교 — Spring MVC, Netty, Coroutine, WebFlux]({{ site.baseurl }}/os/async-processing-comparison.html) | Thread-per-Request vs Event Loop, Netty, WebFlux, Coroutine, Virtual Thread |
| [언어별 비동기 구현 방식 — 내부 동작 원리부터 프레임워크 주의점까지]({{ site.baseurl }}/os/async-patterns-by-language.html) | JS Event Loop, Python asyncio, Go Goroutine, Java Virtual Thread, Kotlin, Rust tokio |
| [운영체제 구조와 커널(Kernel) 심화]({{ site.baseurl }}/os/kernel-and-os-structure.html) | 유저 모드 vs 커널 모드, CPU Ring 구조, Monolithic vs Microkernel, 컨테이너와의 관계 |
| [커널(Kernel)이 뭔데? — 쉽게 이해하는 운영체제의 심장]({{ site.baseurl }}/os/kernel-easy-guide.html) | 커널의 5가지 역할, System Call, Java/Spring 개발자가 알아야 하는 커널 이슈 |
| [이벤트 기반 시스템에서의 Lock 처리 — 초고트래픽 동시성 제어]({{ site.baseurl }}/os/event-driven-locking.html) | 분산 Lock, 원자적 연산, 메시지 큐 직렬화, Fencing Token, 선착순 쿠폰 |
| [재고 동기화와 Lock 전략 — 이커머스 동시성 문제의 모든 것]({{ site.baseurl }}/os/inventory-lock-strategy.html) | 비관적/낙관적 Lock, Redis DECR, DLQ/Outbox, Lua/Saga, 면접 답변 전략 |
| [컨테이너 vs 가상머신 — Docker, K8s, 그리고 왜 컨테이너인가]({{ site.baseurl }}/os/container-vs-vm.html) | VM vs Container, Namespace/cgroups, Docker/K8s 관계, gVisor/Kata, 런타임 비교 |

### Design Pattern / 설계 패턴

| 주제 | 키워드 |
|:-----|:-------|
| [분산 시스템 핵심 패턴 — 동시성, 트랜잭션, 메시징, 데이터 정합성]({{ site.baseurl }}/design-pattern/distributed-system-patterns.html) | 분산 락, ACID vs BASE, 2PC/Saga/Outbox, 멱등성, Circuit Breaker, CAP 정리 |

### Git

| 주제 | 키워드 |
|:-----|:-------|
| [Rebase Merge vs Squash Merge — Git 병합 전략의 차이와 선택 기준]({{ site.baseurl }}/git/merge-strategies.html) | Merge Commit / Rebase / Squash 비교, 히스토리 차이, 실무 전략 선택 기준 |

### Map System / 지도 시스템

| 주제 | 키워드 |
|:-----|:-------|
| [공간 인덱싱과 지도 시스템 기초 — POI, 타일링, Geocoding]({{ site.baseurl }}/map-system/spatial-indexing-and-map-fundamentals.html) | R-Tree/Geohash/S2/H3, POI, 래스터/벡터 타일링, Dijkstra/A*/CH, PostGIS |
| [글로벌 로컬라이징 아키텍처 — i18n, L10n, 다국어/다지역 서비스 설계]({{ site.baseurl }}/map-system/global-localization-architecture.html) | BCP 47, 다국어 DB 패턴, RTL 아랍어, TMS 번역 관리 |
| [대규모 지도 데이터 파이프라인 — 실시간/배치 처리, ETL, 데이터 모델링]({{ site.baseurl }}/map-system/map-data-pipeline.html) | Spark/Flink, POI 중복 제거, CDC, Lambda/Kappa, Map Matching |
| [글로벌 트래픽 대응 아키텍처 — 멀티리전, CDN, 대규모 서비스 운영]({{ site.baseurl }}/map-system/global-traffic-architecture.html) | 멀티리전 배포, CDN 타일 캐싱, Circuit Breaker, Rate Limiting, OpenTelemetry |

---

<sub>이 저장소는 [GitHub Pages](https://iamyunjuda.github.io/cs-knowledge-base/)로 자동 배포됩니다.</sub>
