# VPN 동작 원리 — 중국 GFW는 어떻게 VPN을 막고, 어떻게 뚫는가

## 핵심 정리

### VPN이란?

VPN(Virtual Private Network)은 **인터넷 위에 암호화된 터널**을 만들어서, 마치 다른 네트워크에 직접 연결된 것처럼 통신하는 기술이다.

```
[VPN 없이]
내 PC ──평문 요청──→ ISP ──→ google.com
                      │
                ISP가 어디 접속하는지 다 보임
                정부가 원하면 차단 가능

[VPN 사용 시]
내 PC ──암호화된 터널──→ ISP ──→ [VPN 서버 (해외)] ──→ google.com
                          │              │
                    암호화되어 있어서     VPN 서버가 대신 접속
                    뭘 하는지 모름       google.com은 VPN 서버 IP만 보임
```

### VPN 프로토콜별 동작 계층

VPN도 L4/L7 개념이 적용된다. **어느 계층에서 터널을 만드느냐**에 따라 특성이 다르다:

```
[OSI 계층과 VPN 프로토콜]

L7  응용 계층    ← SSL VPN (OpenVPN, AnyConnect)
                   HTTPS 위에서 동작. 웹 트래픽처럼 보임
L5  세션 계층
L4  전송 계층    ← SSTP (TCP 443 사용)
                   WireGuard (UDP 사용)
L3  네트워크 계층 ← IPSec, L2TP/IPSec
                   IP 패킷 자체를 암호화
L2  데이터링크    ← PPTP, L2TP
                   가장 오래된 방식. 보안 취약
```

### 주요 VPN 프로토콜 비교

```
[PPTP — 1990년대, 이제는 쓰면 안 됨]
동작: L2에서 GRE 프로토콜로 터널링 + MPPE 암호화
포트: TCP 1723 + GRE (프로토콜 47)
문제: 암호화가 뚫림. MS-CHAPv2 취약점. 몇 시간이면 해독 가능.
차단: GRE 프로토콜 번호(47)만 차단하면 끝 → 매우 쉽게 차단됨

[L2TP/IPSec — 조금 나아졌지만 역시 차단 쉬움]
동작: L2TP(터널) + IPSec(암호화) 조합
포트: UDP 500 (IKE) + UDP 4500 (NAT-T) + ESP (프로토콜 50)
문제: 고정 포트 사용 → 포트만 막으면 차단됨

[OpenVPN — 가장 널리 쓰이는 오픈소스 VPN]
동작: OpenSSL 기반, TLS로 암호화. TCP 또는 UDP 사용 가능
포트: 기본 UDP 1194, 하지만 TCP 443으로 변경 가능
특징: TCP 443으로 쓰면 HTTPS 트래픽과 같은 포트 → 포트 차단이 어려움

[WireGuard — 최신, 가장 빠름]
동작: UDP 기반, 최소한의 코드 (약 4000줄)
포트: 기본 UDP 51820
특징: 매우 빠르고 가벼움. 하지만 프로토콜 패턴이 독특해서 DPI로 탐지 가능

[Shadowsocks — 중국에서 태어난 프로토콜]
동작: SOCKS5 프록시 + 암호화. VPN은 아니지만 유사한 역할
특징: 트래픽이 랜덤 데이터처럼 보이도록 설계 (난독화)
```

---

## 중국 GFW(Great Firewall)의 차단 메커니즘

GFW가 VPN을 차단하는 방식은 **L4/L7 로드밸런서가 트래픽을 판단하는 것과 정확히 같은 원리**다. 로드밸런서는 "어디로 보낼까"를 판단하지만, GFW는 "이걸 차단할까"를 판단한다.

### 차단 레벨 1: IP 블랙리스트 (L3)

```
[가장 단순한 차단]

내 PC ──→ GFW ──→ VPN 서버 (1.2.3.4)
              │
         "1.2.3.4는 알려진 VPN 서버 IP"
         → 차단! 💥

방법: 알려진 VPN 서비스의 IP 대역을 블랙리스트에 추가
대상: NordVPN, ExpressVPN 등 유명 VPN 서비스의 서버 IP

우회: 새 IP로 서버를 만들면 일시적으로 됨 → GFW가 발견하면 다시 차단
```

### 차단 레벨 2: 포트 차단 (L4)

```
[L4 로드밸런서와 같은 원리 — IP+Port로 판단]

내 PC ──→ GFW
            │
       패킷 헤더 확인:
       dst port = 1194 (OpenVPN 기본 포트)? → 차단!
       dst port = 1723 (PPTP)? → 차단!
       프로토콜 = GRE (47)? → 차단!
       프로토콜 = ESP (50)? → 차단!

→ PPTP, L2TP/IPSec은 이 단계에서 거의 다 막힘
→ 고정 포트를 쓰는 프로토콜은 매우 취약
```

### 차단 레벨 3: DPI — 심층 패킷 검사 (L7)

**여기가 핵심이다.** L7 로드밸런서가 HTTP 헤더를 읽어서 라우팅하듯, GFW는 **패킷 내용을 열어서 VPN 프로토콜의 패턴**을 찾는다.

```
[L7 로드밸런서]                    [GFW의 DPI]
패킷을 열어서                      패킷을 열어서
HTTP 헤더를 읽고                   프로토콜 패턴을 분석하고
→ 적절한 서버로 라우팅              → VPN이면 차단

같은 기술, 다른 목적!
```

```
[DPI가 VPN을 탐지하는 방법들]

① 프로토콜 시그니처 매칭
   OpenVPN 패킷의 첫 바이트: 0x38 또는 0x40 (opcode)
   → "이 바이트 패턴 = OpenVPN이다" → 차단!

② TLS 핸드셰이크 분석
   OpenVPN이 TCP 443으로 위장해도:
   - TLS Client Hello의 확장 필드가 일반 HTTPS와 다름
   - 인증서 체인이 없거나 자체 서명
   - SNI(Server Name Indication)가 없거나 이상함
   → "이건 진짜 HTTPS가 아니라 VPN이다" → 차단!

③ 트래픽 패턴 분석 (통계적 방법)
   - 패킷 크기 분포가 웹 브라우징과 다름
   - 업/다운로드 비율이 일반 HTTPS와 다름
   - 연결 지속 시간이 비정상적으로 김
   - 일정한 간격으로 패킷이 오감 (VPN keepalive)
   → 머신러닝으로 VPN 트래픽 판별

④ Active Probing (능동적 탐지)
   GFW가 의심스러운 서버에 직접 접속 시도:
   - 해당 포트에 HTTP 요청 → 웹 서버 응답이 없으면 의심
   - OpenVPN 핸드셰이크 시도 → 응답하면 VPN 서버 확정
   - Shadowsocks 핸드셰이크 시도 → 응답 패턴으로 판별
   → 서버 IP를 블랙리스트에 추가
```

```
[DPI 검사 흐름 — L7 로드밸런서와 비교]

L7 로드밸런서:
  패킷 수신 → TLS 복호화 → HTTP 파싱 → URL/Host 확인 → 라우팅

GFW DPI:
  패킷 수신 → 프로토콜 시그니처 매칭 → TLS 핸드셰이크 분석
  → 트래픽 패턴 분석 → 차단/통과 결정

둘 다 "패킷을 열어서 내용을 분석한다"는 점에서 L7 검사!
```

---

## 중국에서 되는 VPN vs 안 되는 VPN

### 안 되는 것들 (쉽게 차단됨)

```
[PPTP]
차단 난이도: ★☆☆☆☆ (매우 쉬움)
이유: GRE 프로토콜(47번) 차단 → L4 수준에서 끝

[L2TP/IPSec]
차단 난이도: ★★☆☆☆ (쉬움)
이유: UDP 500/4500, ESP 프로토콜 차단 → L4 수준에서 끝

[기본 설정 OpenVPN]
차단 난이도: ★★★☆☆ (보통)
이유: UDP 1194 포트 차단(L4) + DPI로 OpenVPN 시그니처 탐지(L7)

[기본 설정 WireGuard]
차단 난이도: ★★★☆☆ (보통)
이유: UDP 패킷의 고유한 핸드셰이크 패턴을 DPI로 탐지(L7)

[일반 상용 VPN (NordVPN, ExpressVPN 기본 모드)]
차단 난이도: ★★★☆☆ (보통)
이유: 서버 IP 블랙리스트(L3) + DPI(L7)
```

### 되는 것들 (차단 우회 기술 적용)

```
[Shadowsocks / V2Ray / Trojan]
원리: 트래픽을 "진짜 HTTPS처럼" 위장

┌─────────────────────────────────────────────────────┐
│ Trojan의 동작                                        │
│                                                      │
│ 클라이언트 ──진짜 TLS──→ [서버 (443 포트)]           │
│                             │                        │
│              TLS 안에 비밀 암호(password)가 있으면    │
│              → VPN 터널로 동작                       │
│                                                      │
│              비밀 암호가 없으면 (GFW가 탐지 시도 시)  │
│              → 진짜 웹사이트를 보여줌!               │
│                                                      │
│ GFW: "이 서버에 접속해봤는데 진짜 웹사이트네" → 통과  │
└─────────────────────────────────────────────────────┘

[Obfuscation (난독화) 적용 OpenVPN / WireGuard]
원리: VPN 프로토콜의 시그니처를 제거하거나 변형

OpenVPN + obfs4:
- OpenVPN 패킷을 랜덤 데이터처럼 변환
- DPI가 "이건 아무 패턴도 없는 데이터네" → 통과
- 단점: "패턴이 없다"는 것 자체가 의심 (엔트로피 분석)

[Domain Fronting]
원리: CDN을 이용한 우회

클라이언트 ──HTTPS──→ [Cloudflare CDN]
  TLS SNI: allowed-site.com  (GFW가 보는 부분)
  HTTP Host: blocked-vpn.com (암호화 안에 숨겨진 진짜 목적지)

GFW: "allowed-site.com에 접속하네" → 통과
CDN: HTTP Host 헤더를 보고 blocked-vpn.com으로 전달

→ CDN 업체들이 막아서 현재는 거의 사용 불가

[Tunneling over WebSocket / gRPC]
원리: VPN 트래픽을 WebSocket이나 gRPC 안에 담아서 전송

클라이언트 ──WebSocket──→ [CDN] ──→ [VPN 서버]
   wss://cdn.example.com/ws

GFW가 보기에는 일반 WebSocket 통신
실제로는 WebSocket 안에 VPN 데이터가 흐르고 있음
```

### 차단 vs 우회 — 레벨별 정리

```
┌─────────┬──────────────────────┬──────────────────────────┐
│  검사   │   GFW 차단 방식      │   우회 방법              │
│  레벨   │                      │                          │
├─────────┼──────────────────────┼──────────────────────────┤
│  L3     │ IP 블랙리스트        │ 새 IP, CDN 경유          │
│  (IP)   │                      │                          │
├─────────┼──────────────────────┼──────────────────────────┤
│  L4     │ 포트/프로토콜 차단   │ TCP 443 사용 (HTTPS 위장)│
│  (Port) │ (1194, GRE, ESP)     │                          │
├─────────┼──────────────────────┼──────────────────────────┤
│  L7     │ DPI 시그니처 탐지    │ 난독화 (obfuscation)     │
│  (DPI)  │ TLS 핸드셰이크 분석 │ 진짜 TLS + 위장 웹서버  │
│         │ 트래픽 패턴 분석     │ (Trojan, V2Ray)          │
│         │ Active Probing       │ WebSocket/gRPC 터널링    │
└─────────┴──────────────────────┴──────────────────────────┘

하위 레벨 차단은 우회가 쉬움 (포트 바꾸면 끝)
상위 레벨 차단은 우회가 어려움 (프로토콜 자체를 변형해야 함)
→ GFW는 점점 L7 검사를 강화하는 추세
```

---

## 헷갈렸던 포인트

### Q: L4/L7 로드밸런서와 GFW의 관계가 정확히 뭔가?

기술적 원리가 같다. **L4 LB**가 IP+Port로 라우팅하듯 GFW도 IP+Port로 차단한다. **L7 LB**가 HTTP 내용을 파싱해서 라우팅하듯 GFW도 패킷 내용을 DPI로 분석해서 차단한다. LB는 "어디로 보낼까", GFW는 "이걸 막을까"라는 목적만 다르고, 패킷을 분석하는 기술은 동일하다.

### Q: OpenVPN을 TCP 443으로 바꾸면 HTTPS와 구분 못 하지 않나?

L4 수준에서는 구분 못 한다 (같은 포트니까). 하지만 **L7(DPI) 수준에서 구분 가능**하다. OpenVPN의 TLS 핸드셰이크 패턴이 일반 HTTPS와 다르다. TLS Client Hello의 cipher suite 목록, 확장 필드, 인증서 체인 등이 브라우저의 것과 다르기 때문에 DPI가 "이건 진짜 HTTPS가 아니다"라고 판단할 수 있다.

### Q: Shadowsocks는 VPN인가?

엄밀히는 **암호화된 프록시**지, VPN이 아니다. VPN은 OS 레벨에서 모든 트래픽을 터널링하지만, Shadowsocks는 SOCKS5 프록시로 **설정된 앱의 트래픽만** 프록시한다. 하지만 중국에서 "VPN"이라고 부르는 것들 중 상당수가 실제로는 Shadowsocks/V2Ray 기반이다.

### Q: WireGuard가 빠른데 왜 중국에서는 안 쓰나?

WireGuard는 성능은 최고지만, **프로토콜 설계 목표에 "검열 우회"가 없다**. 핸드셰이크 패턴이 고유하고 난독화 기능이 없어서 DPI로 쉽게 탐지된다. 중국에서 쓰려면 WireGuard를 WebSocket이나 obfs4 같은 난독화 레이어로 감싸야 하는데, 그럴 바에는 처음부터 Trojan이나 V2Ray를 쓰는 게 낫다.

### Q: GFW가 모든 패킷을 DPI하면 인터넷이 느려지지 않나?

맞다. 실제로 중국의 국제 인터넷 속도는 느린 편이다. GFW는 **모든 패킷을 다 검사하지는 않고**, 의심스러운 트래픽(알 수 없는 프로토콜, 해외 IP, 비정상 패턴)만 정밀 검사한다. 일반적인 HTTPS 트래픽(구글 제외)은 대부분 통과시킨다. 하지만 국제 회선 대역폭 자체를 제한하는 **쓰로틀링**도 병행한다.

## 참고 자료

- [GFW Report](https://gfw.report/) — 중국 방화벽 기술 분석 연구
- [WireGuard Protocol](https://www.wireguard.com/protocol/)
- [How the Great Firewall of China Detects and Blocks Fully Encrypted Traffic (USENIX 2023)](https://www.usenix.org/conference/usenixsecurity23/presentation/wu-mingshi)
