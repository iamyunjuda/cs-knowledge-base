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

### Database

- [Cache Stampede 해결기 — 주기적 DB 부하 급증의 원인을 찾아서](database/cache-stampede-solving.md)
  - Thundering Herd, TTL 지터, 분산 락, 사전 워밍, Cache Stampede 원인 분석과 해결 전략

### Infra / 인프라 미들웨어

- [Kafka 심화 — 정합성, 순서 보장, 핵심 옵션 총정리](infra/kafka-deep-dive.md)
  - Partition 기반 순서 보장, Partition Key, acks(0/1/all), ISR, enable.idempotence, Consumer offset 관리(auto/manual), At Least Once/Exactly Once, Rebalancing, CooperativeStickyAssignor, 실무 설정 가이드

### OS / 운영체제

- [CPU, RAM, SSD, HDD — 컴퓨터 핵심 부품의 근본적 차이와 트레이드오프](os/ssd-hdd-ram-comparison.md)
  - CPU 구조(Register/Cache/ALU), Cache Hit/Miss, HDD 물리적 한계(Seek/Rotation), SSD NAND Flash, SATA vs NVMe, RAM DRAM 동작, 저장장치 계층별 성능 비교, DB 인덱스/Redis/Kafka와의 연관
- [epoll, kqueue, io_uring — I/O 멀티플렉싱의 진화와 트레이드오프](os/epoll-kqueue-io-multiplexing.md)
  - select/poll 한계, epoll 동작 원리(LT/ET), kqueue 차이점, io_uring 공유 메모리 링 버퍼, Nginx/Redis/Node.js/Netty가 사용하는 I/O 모델, libuv/mio 크로스 플랫폼 추상화
- [비동기 처리 방식 비교 — Spring MVC, Netty, Coroutine, WebFlux](os/async-processing-comparison.md)
  - Thread-per-Request vs Event Loop, Netty 구조, WebFlux(Reactor), Kotlin Coroutine suspend, Java Virtual Thread(Loom), 실무 선택 기준
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

### Git

- [Rebase Merge vs Squash Merge — Git 병합 전략의 차이와 선택 기준](git/merge-strategies.md)
  - Merge Commit / Rebase Merge / Squash Merge 비교, 커밋 보존 여부, 히스토리 형태 차이, Squash 후 브랜치 삭제 이유, 실무 전략 선택 기준
