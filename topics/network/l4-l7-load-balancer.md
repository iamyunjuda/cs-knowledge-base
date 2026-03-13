---
title: L4 / L7 로드밸런서 — 차이점과 실무 선택 기준
parent: Network
nav_order: 2
---

# L4 / L7 로드밸런서 — 차이점과 실무 선택 기준

## 핵심 정리

### 로드밸런서란?

트래픽을 **여러 서버(백엔드)에 분산**시키는 장치다. "L4", "L7"은 **OSI 7계층 중 어느 레벨에서 트래픽을 판단하느냐**의 차이다.

```
[OSI 7계층과 로드밸런서 위치]

L7  응용 계층 (Application)   ← L7 로드밸런서가 여기서 판단
L6  표현 계층 (Presentation)     (HTTP 헤더, URL, 쿠키, Body 등을 봄)
L5  세션 계층 (Session)
L4  전송 계층 (Transport)     ← L4 로드밸런서가 여기서 판단
L3  네트워크 계층 (Network)      (IP + Port만 봄)
L2  데이터링크 계층
L1  물리 계층
```

---

### L4 로드밸런서 (Transport Layer)

**TCP/UDP 레벨**에서 동작한다. 패킷의 **IP 주소와 Port 번호**만 보고 라우팅한다. 패킷 내용(HTTP 헤더, URL 등)은 전혀 보지 않는다.

```
[L4 로드밸런서 동작]

클라이언트 ──TCP SYN (dst: LB:443)──→ [L4 LB]
                                         │
                                         │ IP+Port만 보고 판단
                                         │ "192.168.1.10:443 → 서버 A로"
                                         │
                                         ├──→ 서버 A (10.0.0.1:8080)
                                         ├──→ 서버 B (10.0.0.2:8080)
                                         └──→ 서버 C (10.0.0.3:8080)

패킷을 열어보지 않음! TCP 연결을 그대로 전달(또는 NAT)할 뿐.
```

**L4 로드밸런서의 동작 방식 (상세):**

```
[방식 1: NAT (Network Address Translation) — 가장 일반적]

클라이언트(1.1.1.1:5000)                    서버 A(10.0.0.1:8080)
        │                                         ▲
        │  dst: LB(2.2.2.2:443)                   │
        ▼                                         │
   [L4 LB]                                        │
        │  dst IP를 서버 A로 변환                  │
        │  src: 2.2.2.2, dst: 10.0.0.1:8080       │
        └──────────────────────────────────────────┘
           응답도 LB를 거쳐서 src IP를 다시 변환

[방식 2: DSR (Direct Server Return) — 고성능]

클라이언트(1.1.1.1:5000)
        │
        │  요청은 LB를 거침
        ▼
   [L4 LB] ──→ 서버 A
                  │
                  │  응답은 LB를 거치지 않고 직접 클라이언트에게!
                  └──────→ 클라이언트(1.1.1.1:5000)

→ 응답 트래픽이 LB를 안 거치므로 LB 부하가 크게 줄어듦
→ 동영상 스트리밍 같은 응답이 큰 서비스에 유리
```

**대표 제품/기술:**
- AWS **NLB** (Network Load Balancer)
- K8s **Service** (type: LoadBalancer, 기본 동작)
- **HAProxy** (TCP 모드)
- **IPVS** (Linux 커널 레벨)
- 하드웨어: F5 BIG-IP, Citrix ADC

---

### L7 로드밸런서 (Application Layer)

**HTTP/HTTPS 레벨**에서 동작한다. 패킷을 **열어서** HTTP 헤더, URL 경로, 쿠키, Host 헤더 등을 읽고 라우팅한다.

```
[L7 로드밸런서 동작]

클라이언트 ──HTTP 요청──→ [L7 LB]
                            │
  GET /api/users            │  HTTP 내용을 파싱해서 판단
  Host: example.com         │
  Cookie: session=abc123    │  "/api/*" → API 서버로
                            │  "/static/*" → CDN으로
                            │  "Cookie: session=abc" → 같은 서버로 (sticky)
                            │
                            ├──→ API 서버 A
                            ├──→ API 서버 B
                            └──→ 정적 파일 서버

패킷을 열어서 HTTP를 이해함! 내용 기반으로 똑똑한 라우팅 가능.
```

**L7에서만 가능한 것들:**

```
[1. URL 경로 기반 라우팅]

/api/v1/users  → user-service 클러스터
/api/v1/orders → order-service 클러스터
/static/*      → CDN / 정적 파일 서버
/ws/*          → WebSocket 서버

[2. Host 헤더 기반 라우팅 (가상 호스팅)]

Host: api.example.com    → API 서버
Host: web.example.com    → 웹 서버
Host: admin.example.com  → 관리자 서버
→ 하나의 LB IP로 여러 도메인 서비스 가능!

[3. HTTP 헤더/쿠키 기반 라우팅]

X-API-Version: v2        → v2 서버로
Cookie: canary=true      → 카나리 배포 서버로
Authorization: Bearer ... → 인증 서비스로

[4. TLS 종료 (SSL Termination)]

클라이언트 ──HTTPS(암호화)──→ [L7 LB] ──HTTP(평문)──→ 백엔드
                                │
                       여기서 TLS 복호화
                       인증서 관리를 LB에서 집중

[5. 요청/응답 변환]

- 헤더 추가/삭제 (X-Forwarded-For, X-Real-IP 등)
- 응답 압축 (gzip)
- 요청 본문 검사 (WAF 기능)
- 리다이렉트 (HTTP → HTTPS)
```

**대표 제품/기술:**
- AWS **ALB** (Application Load Balancer)
- K8s **Ingress** (Nginx Ingress, Traefik, Istio Gateway)
- **Nginx** (proxy_pass)
- **HAProxy** (HTTP 모드)
- **Envoy** (Istio 사이드카 프록시)
- Cloudflare, AWS CloudFront (CDN + L7 LB)

---

### L4 vs L7 비교

```
                    L4 로드밸런서              L7 로드밸런서
                ┌─────────────────────┐  ┌─────────────────────────┐
 판단 기준      │ IP + Port           │  │ HTTP 헤더, URL, 쿠키 등 │
                ├─────────────────────┤  ├─────────────────────────┤
 패킷 해석     │ 안 함 (그대로 전달) │  │ 해석함 (HTTP 파싱)      │
                ├─────────────────────┤  ├─────────────────────────┤
 속도          │ 빠름 (커널 레벨)    │  │ 상대적으로 느림         │
                ├─────────────────────┤  ├─────────────────────────┤
 CPU 부하      │ 낮음               │  │ 높음 (TLS + HTTP 파싱)  │
                ├─────────────────────┤  ├─────────────────────────┤
 TLS 처리      │ 패스스루 (못 봄)   │  │ 종료 가능 (복호화)      │
                ├─────────────────────┤  ├─────────────────────────┤
 WebSocket     │ TCP라서 자연스럽게  │  │ 업그레이드 설정 필요    │
               │ 지원됨              │  │                         │
                ├─────────────────────┤  ├─────────────────────────┤
 Sticky Session│ 클라이언트 IP 기반  │  │ 쿠키/헤더 기반 (정교)   │
                ├─────────────────────┤  ├─────────────────────────┤
 비용 (AWS)    │ NLB: 저렴           │  │ ALB: 상대적으로 비쌈    │
                └─────────────────────┘  └─────────────────────────┘
```

---

### 실무에서 자주 보는 아키텍처 패턴

#### 패턴 1: L4 + L7 조합 (가장 일반적)

```
인터넷
  │
  ▼
[L4 LB (NLB)] ─── TCP 레벨 분산, DDoS 방어, 고가용성
  │
  ├──→ [L7 LB (Nginx/ALB) - AZ-a] ─── HTTP 라우팅, TLS 종료
  │         ├──→ API 서버 1
  │         └──→ API 서버 2
  │
  └──→ [L7 LB (Nginx/ALB) - AZ-b] ─── HTTP 라우팅, TLS 종료
            ├──→ API 서버 3
            └──→ API 서버 4

→ L4가 앞단에서 L7 LB 자체의 이중화를 담당
→ L7이 뒷단에서 똑똑한 HTTP 라우팅 담당
```

#### 패턴 2: K8s에서의 구조

```
인터넷
  │
  ▼
[Cloud LB (NLB/ALB)]        ← 클라우드 프로바이더가 제공
  │
  ▼
[Ingress Controller]         ← L7 (Nginx Ingress, Traefik 등)
  │
  ├── /api/*  → [K8s Service] → [API Pod 1, 2, 3]        ← Service는 L4
  ├── /web/*  → [K8s Service] → [Web Pod 1, 2]
  └── /ws/*   → [K8s Service] → [WebSocket Pod 1, 2, 3]
```

```yaml
# K8s Ingress 예시 (L7 라우팅)
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: app-ingress
spec:
  rules:
    - host: example.com
      http:
        paths:
          - path: /api
            pathType: Prefix
            backend:
              service:
                name: api-service      # L4 Service
                port:
                  number: 80
          - path: /ws
            pathType: Prefix
            backend:
              service:
                name: websocket-service
                port:
                  number: 80
```

#### 패턴 3: gRPC 서비스

```
gRPC는 HTTP/2 기반이므로 L7 로드밸런서가 필수!

[문제]
gRPC는 HTTP/2 하나의 TCP 연결에 여러 요청을 멀티플렉싱함
→ L4 LB는 TCP 연결 단위로 분산하므로, 하나의 연결이 하나의 서버에 고정됨
→ 모든 요청이 같은 서버로 감 = 로드밸런싱이 안 됨 💥

[해결]
L7 LB가 HTTP/2 스트림 단위로 분산
→ 같은 TCP 연결 안에서도 요청별로 다른 서버에 분배 가능

클라이언트 ──HTTP/2──→ [L7 LB (Envoy)]
                          │
                          ├── stream 1 → gRPC 서버 A
                          ├── stream 2 → gRPC 서버 B
                          └── stream 3 → gRPC 서버 A
```

---

### 로드밸런싱 알고리즘

L4/L7 공통으로 사용되는 분산 알고리즘:

```
[라운드 로빈 (Round Robin)] — 가장 기본
요청 1 → 서버 A
요청 2 → 서버 B
요청 3 → 서버 C
요청 4 → 서버 A  (다시 처음부터)

[가중치 라운드 로빈 (Weighted Round Robin)]
서버 A (weight=3): 요청 1, 2, 3
서버 B (weight=1): 요청 4
서버 A (weight=3): 요청 5, 6, 7
→ 서버 스펙이 다를 때 유용

[최소 연결 (Least Connections)]
서버 A: 현재 연결 10개
서버 B: 현재 연결 3개  ← 이쪽으로!
서버 C: 현재 연결 7개
→ WebSocket처럼 연결이 오래 유지되는 경우에 적합

[IP 해시 (IP Hash)]
hash(클라이언트 IP) % 서버 수 = 서버 인덱스
→ 같은 클라이언트는 항상 같은 서버로 (L4 sticky session)

[Consistent Hashing]
서버가 추가/제거되어도 기존 매핑이 최소한으로 변경됨
→ 캐시 서버 앞단에서 주로 사용
```

---

### WebSocket과 로드밸런서의 관계

앞서 WebSocket 문서에서 다룬 내용을 L4/L7 관점에서 정리:

```
[L4 LB + WebSocket]
- TCP 연결이 그대로 유지되므로 WebSocket이 자연스럽게 동작
- 별도 설정 불필요
- 단점: URL 기반 라우팅 불가 (/ws/* 만 WebSocket 서버로 보내기 등)

[L7 LB + WebSocket]
- HTTP → WebSocket 업그레이드를 LB가 이해해야 함
- Nginx: proxy_set_header Upgrade, Connection 설정 필요
- idle timeout 설정 필수 (기본 60초면 WebSocket 끊김)
- 장점: /ws/* 경로만 WebSocket 서버로 라우팅 가능
```

```nginx
# Nginx L7에서 WebSocket 프록시 설정
location /ws/ {
    proxy_pass http://websocket_backend;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;      # 필수!
    proxy_set_header Connection "upgrade";        # 필수!
    proxy_set_header Host $host;
    proxy_read_timeout 3600s;                     # 1시간
    proxy_send_timeout 3600s;
}
```

---

## 헷갈렸던 포인트

### Q: L4 로드밸런서가 더 빠른데 왜 L7을 쓰나?

L4는 **빠르지만 멍청하다**. IP+Port만 보니까 "이 요청이 API 호출인지, 정적 파일 요청인지, WebSocket인지" 구분을 못 한다. MSA 환경에서 URL 경로별로 다른 서비스에 라우팅하려면 L7이 필수다. 실무에서는 **L4로 앞단 분산 + L7으로 뒷단 라우팅**을 조합하는 게 일반적이다.

### Q: TLS 종료를 L7에서 하면 백엔드 구간은 평문인데 보안 괜찮나?

내부 네트워크(VPC, K8s 클러스터 내부)라면 일반적으로 괜찮다고 본다. 백엔드 구간까지 암호화가 필요하면 **mTLS (mutual TLS)**를 쓴다. Istio 같은 서비스 메시가 사이드카 프록시 간 mTLS를 자동으로 처리해준다.

### Q: K8s Service는 L4인데 Ingress는 L7인가?

맞다. K8s **Service**(ClusterIP, NodePort, LoadBalancer)는 **L4**다. iptables/IPVS로 IP+Port 기반 분산만 한다. K8s **Ingress**는 **L7**이다. Nginx 같은 Ingress Controller가 HTTP 요청을 파싱해서 Host, Path 기반으로 라우팅한다. 두 가지가 함께 동작하는 구조다.

### Q: AWS에서 NLB와 ALB 중 뭘 써야 하나?

| 상황 | 선택 |
|------|------|
| 일반 HTTP/HTTPS API 서비스 | **ALB** (L7 라우팅, TLS 종료) |
| WebSocket이 주 트래픽 | **NLB** (TCP 패스스루, 간단) 또는 ALB |
| gRPC 서비스 | **ALB** (HTTP/2 지원) |
| 극한의 성능/초저지연 | **NLB** (커널 레벨 처리) |
| 고정 IP 필요 (방화벽 화이트리스트) | **NLB** (Elastic IP 할당 가능) |
| L4 + L7 둘 다 필요 | **NLB → ALB** 조합 |

### Q: DSR(Direct Server Return)은 왜 안 쓰나?

DSR은 응답이 LB를 거치지 않아 성능이 좋지만, **서버에 특수 설정**이 필요하고(loopback에 VIP 바인딩 등), **L7 기능을 쓸 수 없고**, **클라우드 환경에서 지원이 제한적**이다. AWS NLB도 DSR과 유사한 방식을 내부적으로 쓰지만 사용자가 직접 설정하지는 않는다. 온프레미스에서 동영상 스트리밍 같은 **응답 트래픽이 매우 큰 서비스**에 주로 사용된다.

## 참고 자료

- [AWS - NLB vs ALB 비교](https://aws.amazon.com/elasticloadbalancing/features/)
- [Nginx - TCP/UDP Load Balancing](https://docs.nginx.com/nginx/admin-guide/load-balancer/tcp-udp-load-balancer/)
- [Kubernetes - Service, Ingress 공식 문서](https://kubernetes.io/docs/concepts/services-networking/)
