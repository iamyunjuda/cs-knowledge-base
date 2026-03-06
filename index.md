---
layout: default
title: Home
nav_order: 0
permalink: /
---

# CS Knowledge Base

작성자가 매번 헷갈려하는 CS 지식들을 정리하는 저장소입니다.
{: .fs-6 .fw-300 }

---

## 목차

### Java / JVM

| 주제 | 키워드 |
|:-----|:-------|
| [JVM 동작 원리 — 다른 언어와의 비교 및 버전별 변화]({{ site.baseurl }}/java-jvm/jvm-internals.html) | HotSpot Tiered Compilation, 실행 모델 비교, Java 버전별 변화 |
| [JVM 메모리 구조]({{ site.baseurl }}/java-jvm/jvm-memory-structure.html) | Heap, G1GC, ZGC, Metaspace, String Pool, OOM 에러 |

### Network

| 주제 | 키워드 |
|:-----|:-------|
| [HTTP/HTTPS와 TCP의 관계]({{ site.baseurl }}/network/http-tcp-relationship.html) | 프로토콜 계층, localhost, DNS 해석, hosts 파일 |
| [L4 / L7 로드밸런서 — 차이점과 실무 선택 기준]({{ site.baseurl }}/network/l4-l7-load-balancer.html) | NAT/DSR, TLS 종료, K8s Ingress, AWS NLB vs ALB |
| [VPN 동작 원리 — 중국 GFW는 어떻게 VPN을 막고, 어떻게 뚫는가]({{ site.baseurl }}/network/vpn-and-traffic-inspection.html) | VPN 프로토콜 비교, DPI, Trojan/V2Ray 우회 |
| [WebSocket 심화 — 동작 원리부터 K8s 인프라 이슈까지]({{ site.baseurl }}/network/websocket-deep-dive.html) | WebSocket 프레임, 스레드 모델, Sticky Session, 스케일링 |

### Database

| 주제 | 키워드 |
|:-----|:-------|
| [Cache Stampede 해결기 — 주기적 DB 부하 급증의 원인을 찾아서]({{ site.baseurl }}/database/cache-stampede-solving.html) | Thundering Herd, TTL 지터, 분산 락, 사전 워밍 |

---

<sub>이 저장소는 [GitHub Pages](https://iamyunjuda.github.io/cs-knowledge-base/)로 자동 배포됩니다.</sub>
