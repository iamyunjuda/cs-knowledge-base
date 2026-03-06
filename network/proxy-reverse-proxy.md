# 프록시(Proxy)와 리버스 프록시(Reverse Proxy)

## 핵심 정리

### 프록시(Forward Proxy)란?

**클라이언트 측에서 동작**하는 중간 서버로, 클라이언트가 인터넷에 직접 접근하지 않고 프록시를 통해 요청을 보낸다.

```
[클라이언트] → [Forward Proxy] → [인터넷/서버]
```

- 클라이언트의 IP를 숨긴다 (서버는 프록시의 IP만 본다)
- 회사/학교에서 특정 사이트 차단 용도로 사용
- 캐싱을 통한 응답 속도 향상
- 대표 예시: Squid Proxy, 기업 방화벽 프록시

### 리버스 프록시(Reverse Proxy)란?

**서버 측에서 동작**하는 중간 서버로, 클라이언트는 리버스 프록시에 요청을 보내고, 리버스 프록시가 실제 백엔드 서버로 전달한다.

```
[클라이언트] → [Reverse Proxy] → [Backend Server A]
                                → [Backend Server B]
                                → [Backend Server C]
```

- 백엔드 서버의 IP/구조를 숨긴다
- 로드밸런싱: 여러 서버로 트래픽 분산
- SSL Termination: HTTPS 처리를 리버스 프록시가 담당
- 캐싱, 압축, 정적 파일 서빙
- 대표 예시: Nginx, HAProxy, AWS ALB/NLB

### 핵심 차이 비교

| 구분 | Forward Proxy | Reverse Proxy |
|------|---------------|---------------|
| **위치** | 클라이언트 앞 | 서버 앞 |
| **누구를 숨기나** | 클라이언트를 숨김 | 서버를 숨김 |
| **누가 설정하나** | 클라이언트(사용자) | 서버(운영자) |
| **주요 목적** | 접근 제어, 우회, 캐싱 | 로드밸런싱, 보안, SSL |
| **예시** | 기업 프록시, VPN | Nginx, CDN, API Gateway |

### 실무에서의 리버스 프록시 아키텍처

```
[사용자] → [CDN (CloudFront)] → [L7 LB (ALB/Nginx)] → [Application Server]
                                                      → [Application Server]
                                                      → [Application Server]
```

**Nginx 리버스 프록시 설정 예시:**
```nginx
upstream backend {
    server 10.0.0.1:8080;
    server 10.0.0.2:8080;
    server 10.0.0.3:8080;
}

server {
    listen 443 ssl;
    server_name api.example.com;

    # SSL Termination — 리버스 프록시가 HTTPS 처리
    ssl_certificate     /etc/ssl/cert.pem;
    ssl_certificate_key /etc/ssl/key.pem;

    location / {
        proxy_pass http://backend;  # 백엔드로는 HTTP로 전달
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### API Gateway도 리버스 프록시인가?

**맞다.** API Gateway는 리버스 프록시의 확장판이다.

| 기능 | 리버스 프록시 | API Gateway |
|------|---------------|-------------|
| 요청 라우팅 | O | O |
| 로드밸런싱 | O | O |
| SSL Termination | O | O |
| 인증/인가 | △ (제한적) | O (JWT, OAuth) |
| Rate Limiting | △ | O |
| 요청/응답 변환 | X | O |
| API 버전 관리 | X | O |

대표적인 API Gateway: Kong, AWS API Gateway, Spring Cloud Gateway

## 헷갈렸던 포인트

### Q1: CDN도 리버스 프록시인가?

**그렇다.** CDN은 전 세계에 분산된 리버스 프록시다. CloudFront, Cloudflare 같은 CDN은 사용자와 가까운 엣지 서버에서 캐싱된 컨텐츠를 제공하고, 캐시 미스 시 원본(Origin) 서버로 요청을 전달한다. 리버스 프록시의 **캐싱** 기능이 극대화된 형태다.

### Q2: 프록시와 VPN의 차이는?

| 구분 | Forward Proxy | VPN |
|------|---------------|-----|
| 동작 레이어 | L7 (Application) | L3 (Network) |
| 범위 | 특정 프로토콜(HTTP) | 모든 트래픽 |
| 암호화 | 선택적 | 항상 암호화 |
| 성능 | 상대적으로 빠름 | 암호화 오버헤드 있음 |

VPN은 **모든 네트워크 트래픽**을 암호화 터널로 감싸지만, Forward Proxy는 보통 **HTTP/HTTPS 트래픽**만 처리한다.

### Q3: Kubernetes에서의 리버스 프록시는?

K8s에서는 여러 계층의 리버스 프록시가 존재한다:

```
[외부 트래픽] → [Ingress Controller (Nginx/Traefik)] → [Service (kube-proxy)] → [Pod]
```

- **Ingress Controller**: L7 리버스 프록시. 도메인/경로 기반 라우팅
- **Service (ClusterIP)**: L4 레벨 로드밸런싱 (kube-proxy/iptables)
- **Service Mesh (Istio/Linkerd)**: 각 Pod에 사이드카 프록시(Envoy)를 배치하여 서비스 간 통신을 관리

## 참고 자료

- [Nginx 공식 문서 — Reverse Proxy](https://docs.nginx.com/nginx/admin-guide/web-server/reverse-proxy/)
- [Cloudflare — Proxy vs Reverse Proxy](https://www.cloudflare.com/learning/cdn/glossary/reverse-proxy/)
