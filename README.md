# CS Knowledge Base

헷갈리기 쉬운 CS 지식들을 정리하는 저장소입니다.

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
- [WebSocket 심화 — 동작 원리부터 K8s 인프라 이슈까지](network/websocket-deep-dive.md)
  - WebSocket 연결/프레임 구조, 스레드 모델(Thread-per-Connection vs Event-Driven), K8s 운영 이슈(Sticky Session, Pod간 브로드캐스트, 스케일링, Graceful Shutdown)
