# HTTP/HTTPS와 TCP의 관계

## 핵심 정리

### TCP는 텍스트를 전송하는 기술이다

TCP는 채팅앱처럼 **텍스트(바이트)를 전송하는 기술**이다. TCP 자체는 전송하는 내용이 뭔지 관심 없다.

그 텍스트를 **해석하는 방식**에 따라 다른 프로토콜이 완성된다:

| 해석 방식 | 결과 | 포트 |
|-----------|------|------|
| HTTP 규격으로 해석 | 웹 통신 (HTTP/HTTPS) | 80 / 443 |
| SSH 규격으로 해석 | 원격 접속 (SSH) | 22 |
| 자체 규격으로 해석 | 소켓 채팅 | 임의 |
| WebSocket 규격으로 해석 | 실시간 양방향 통신 | 80 / 443 |
| FTP 규격으로 해석 | 파일 전송 | 21 |
| SMTP 규격으로 해석 | 이메일 전송 | 25 / 587 |

### TCP가 실제로 하는 일

TCP 소켓을 열면 결국 이런 일이 벌어진다:

```
[클라이언트]                          [서버]
    |                                   |
    |  ---- SYN (연결 요청) ---->       |   ← 3-way handshake
    |  <--- SYN+ACK (수락) -----       |
    |  ---- ACK (확인) -------->       |
    |                                   |
    |  ---- "GET / HTTP/1.1\r\n" -->   |   ← 이게 HTTP 요청. TCP 입장에선 그냥 문자열
    |  <--- "HTTP/1.1 200 OK\r\n" --   |   ← 이게 HTTP 응답. 역시 그냥 문자열
    |                                   |
    |  ---- FIN (종료) -------->       |
    |  <--- FIN+ACK -----------        |
```

**핵심**: TCP는 `"GET / HTTP/1.1\r\n"`이라는 문자열이 HTTP인지 아닌지 모른다. 그냥 바이트를 안전하게 전달할 뿐이다.

### 직접 확인하는 법 — telnet으로 HTTP 요청 보내기

TCP 소켓에 텍스트를 직접 타이핑해서 HTTP 통신이 가능하다:

```bash
$ telnet example.com 80
GET / HTTP/1.1
Host: example.com

```

이렇게 입력하면 실제로 HTML 응답이 돌아온다. 이것이 **"HTTP는 그냥 TCP 위의 텍스트"**라는 증거다. 브라우저도 내부적으로 이 짓을 하고 있을 뿐이다.

### HTTP — 텍스트 기반 요청/응답 규격

HTTP는 TCP 위에서 **정해진 텍스트 형식**으로 요청/응답을 주고받는 규격이다.

**HTTP 요청 메시지의 실제 모습 (TCP로 전송되는 텍스트 그대로):**

```
GET /api/users HTTP/1.1\r\n          ← 요청 라인 (메서드 + 경로 + 버전)
Host: example.com\r\n                ← 헤더 시작
Content-Type: application/json\r\n
Authorization: Bearer abc123\r\n
\r\n                                  ← 빈 줄 = 헤더 끝, 바디 시작
{"name": "홍길동"}                    ← 바디 (선택)
```

**HTTP 응답 메시지:**

```
HTTP/1.1 200 OK\r\n                  ← 상태 라인 (버전 + 상태코드 + 사유)
Content-Type: application/json\r\n
Content-Length: 27\r\n
\r\n
{"id": 1, "name": "홍길동"}
```

TCP는 이 텍스트를 한 글자도 바꾸지 않고 그대로 전달한다. **해석은 전적으로 애플리케이션(브라우저, 서버)의 몫**이다.

### HTTPS — HTTP + SSL/TLS 암호화

HTTPS는 HTTP와 TCP 사이에 **SSL/TLS 암호화 계층**을 끼워넣은 것이다.

```
HTTP (평문)                    HTTPS (암호화)
┌─────────────┐               ┌─────────────┐
│    HTTP      │               │    HTTP      │
├─────────────┤               ├─────────────┤
│              │               │  SSL / TLS   │  ← 이 한 층이 추가됨
│    TCP       │               ├─────────────┤
│              │               │    TCP       │
└─────────────┘               └─────────────┘
```

**HTTPS 연결 과정 (TLS Handshake):**

```
[클라이언트]                              [서버]
    |                                       |
    |  --- TCP 3-way handshake --->         |  ← 먼저 TCP 연결
    |                                       |
    |  --- ClientHello (지원 암호 목록) --> |  ← TLS 핸드셰이크 시작
    |  <-- ServerHello (선택된 암호) -----  |
    |  <-- 서버 인증서 (공개키 포함) -----  |  ← SSL 인증서 전달
    |  --- 키 교환 데이터 --------------->  |  ← 대칭키 생성을 위한 교환
    |  <-- Finished --------------------   |
    |  --- Finished ------------------->   |  ← TLS 핸드셰이크 완료
    |                                       |
    |  --- 암호화된 HTTP 요청 ---------->   |  ← 이후 모든 HTTP 데이터가 암호화
    |  <-- 암호화된 HTTP 응답 ----------   |
```

**TCP 입장에서 보면**: HTTP든 HTTPS든 결국 바이트 스트림을 전달하는 것. 다만 HTTPS는 그 바이트가 암호화되어 있을 뿐이다.

**SSL 인증서가 하는 일:**
1. **신원 확인** — "이 서버가 진짜 example.com이 맞다"를 인증기관(CA)이 보증
2. **공개키 전달** — 클라이언트가 데이터를 암호화할 수 있게 공개키를 전달
3. **암호화 통신 시작** — 공개키로 대칭키를 안전하게 교환한 후, 대칭키로 실제 데이터 암호화

### WebSocket과 TCP

WebSocket은 HTTP로 시작해서 TCP 직통으로 전환하는 프로토콜이다.

**WebSocket 연결 과정:**

```
[클라이언트]                                    [서버]
    |                                             |
    |  --- HTTP 요청 (Upgrade: websocket) --->    |  ← 일반 HTTP 요청처럼 시작
    |  <-- HTTP 101 Switching Protocols ------    |  ← 서버가 "알겠다, 프로토콜 바꾸자"
    |                                             |
    |  === 이후부터 TCP 직통 양방향 통신 ===      |  ← 더 이상 HTTP 아님
    |  <-> 프레임 단위로 실시간 데이터 교환 <->   |
```

**실제 HTTP 업그레이드 요청:**

```
GET /chat HTTP/1.1
Host: example.com
Upgrade: websocket                    ← "웹소켓으로 바꿔주세요"
Connection: Upgrade
Sec-WebSocket-Key: dGhlIHNhbXBsZQ==  ← 핸드셰이크 검증용 키
Sec-WebSocket-Version: 13
```

**서버 응답:**

```
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=  ← 키 기반 검증 응답
```

이후에는 HTTP 형식을 벗어나서 WebSocket 프레임이라는 자체 형식으로 TCP 위에서 직접 양방향 통신한다.

> 일반 TCP 소켓으로도 WebSocket을 구현할 수 있다. 결국 TCP에서 실시간 양방향 통신을 하는 것이고, 위의 핸드셰이크 규격만 맞추면 된다.

### 전체 계층 구조

```
[애플리케이션 계층]  HTTP / HTTPS / WebSocket / SSH / FTP / SMTP ...
                     ↕ 텍스트를 "어떤 규격으로 해석할지" 결정
[보안 계층]          SSL/TLS (HTTPS일 때만)
                     ↕ 암호화/복호화
[전송 계층]          TCP (신뢰성 보장, 순서 보장, 재전송)
                     또는 UDP (빠르지만 보장 없음)
                     ↕ 바이트를 패킷으로 쪼개서 전송
[네트워크 계층]      IP (목적지 주소 기반 라우팅)
                     ↕
[데이터링크 계층]    이더넷 / Wi-Fi (물리적 전송)
```

**TCP vs UDP 차이:**

| | TCP | UDP |
|---|---|---|
| 연결 | 3-way handshake 필요 | 연결 없이 바로 전송 |
| 신뢰성 | 데이터 도착 보장, 순서 보장 | 보장 안 됨 (유실 가능) |
| 속도 | 상대적으로 느림 | 빠름 |
| 사용처 | HTTP, SSH, FTP 등 | DNS 질의, 동영상 스트리밍, 게임 |

---

## localhost와 DNS

### localhost란?

- `localhost`는 **자기 자신(루프백 주소)**을 가리키는 호스트명
- IP 주소로는 `127.0.0.1` (IPv4) 또는 `::1` (IPv6)
- 네트워크 카드(NIC)를 거치지 않고 **OS 커널 내부에서 바로 처리**됨 → 외부 네트워크와 무관

```
[일반 통신]
앱 → OS → NIC(랜카드) → 라우터 → 인터넷 → 목적지 서버

[localhost 통신]
앱 → OS → (커널 내부 루프백) → 같은 OS의 다른 앱
         NIC를 거치지 않음! 외부 네트워크로 안 나감!
```

### DNS(Domain Name System)란?

DNS는 **도메인 이름을 IP 주소로 변환하는 시스템**이다. 전화번호부와 같은 역할.

```
google.com  →  DNS 질의  →  142.250.207.46
naver.com   →  DNS 질의  →  223.130.195.200
```

브라우저는 IP 주소로만 통신할 수 있다. `google.com`이라고 입력하면 반드시 먼저 IP를 알아내야 TCP 연결을 시작할 수 있다.

### DNS 해석 순서 (상세)

브라우저에 `example.com`을 입력했을 때:

```
① 브라우저 DNS 캐시 확인
   → 최근에 방문한 적 있으면 여기서 바로 반환
   → Chrome: chrome://net-internals/#dns 에서 확인 가능
   ↓ 없으면

② OS DNS 캐시 확인
   → OS가 이전에 조회한 결과를 캐싱
   → Windows: ipconfig /displaydns 로 확인
   → Mac: sudo dscacheutil -flushcache 로 초기화
   ↓ 없으면

③ hosts 파일 확인
   → Linux/Mac: /etc/hosts
   → Windows: C:\Windows\System32\drivers\etc\hosts
   → localhost는 여기서 127.0.0.1로 해석됨 ★
   ↓ 없으면

④ 로컬 DNS 서버(리졸버)에 질의
   → 보통 공유기(192.168.0.1) 또는 ISP의 DNS 서버
   → 또는 직접 설정한 DNS (8.8.8.8, 1.1.1.1 등)
   ↓ 캐시에 없으면

⑤ 루트 DNS 서버 → TLD DNS 서버 → 권한 DNS 서버 (재귀 질의)
   → "." → ".com" → "example.com" 순서로 위임하며 찾아감
```

**⑤번 재귀 질의 상세 과정:**

```
[로컬 DNS 서버]
    |
    |-- "example.com의 IP가 뭐야?" --> [루트 DNS 서버 (.)]
    |<- ".com은 이 서버한테 물어봐"     (전 세계 13개)
    |
    |-- "example.com의 IP가 뭐야?" --> [TLD DNS 서버 (.com)]
    |<- "example.com은 이 서버가 관리"
    |
    |-- "example.com의 IP가 뭐야?" --> [권한 DNS 서버 (example.com)]
    |<- "93.184.216.34 이야!"          (실제 IP 반환)
    |
    → 결과를 캐싱하고 브라우저에 반환
```

### localhost는 DNS를 거치지 않는다

`localhost`는 위 순서의 **③번(hosts 파일)**에서 바로 `127.0.0.1`로 해석된다. 외부 DNS 서버에 질의할 필요가 없다.

```
# /etc/hosts (Linux/Mac)
127.0.0.1   localhost
::1         localhost

# Windows: C:\Windows\System32\drivers\etc\hosts
# 같은 형식
```

### hosts 파일 활용

hosts 파일에 직접 도메인 → IP 매핑을 추가할 수 있다:

```
# 로컬 개발용 커스텀 도메인
127.0.0.1   my-local-api.dev
127.0.0.1   test.example.com
127.0.0.1   local.myapp.com

# 특정 사이트 차단 (IP를 0.0.0.0으로 보내면 접속 불가)
0.0.0.0     ads.example.com
0.0.0.0     tracker.example.com
```

**활용 사례:**
- **로컬 개발**: `my-local-api.dev`로 접속해도 로컬 서버로 연결
- **사이트 차단**: 광고/추적 도메인을 `0.0.0.0`으로 보내서 차단
- **테스트**: 실제 도메인을 로컬 서버로 우회시켜 테스트

### DNS 레코드 종류

DNS 서버에는 단순히 IP만 저장하는 게 아니라 여러 종류의 레코드가 있다:

| 레코드 | 역할 | 예시 |
|--------|------|------|
| **A** | 도메인 → IPv4 주소 | `example.com → 93.184.216.34` |
| **AAAA** | 도메인 → IPv6 주소 | `example.com → 2606:2800:220:1:...` |
| **CNAME** | 도메인 → 다른 도메인 (별명) | `www.example.com → example.com` |
| **MX** | 메일 서버 지정 | `example.com → mail.example.com` |
| **NS** | 네임서버 지정 | `example.com → ns1.example.com` |
| **TXT** | 텍스트 정보 (인증 등) | SPF, DKIM 메일 인증 등에 사용 |

**nslookup으로 직접 확인:**

```bash
$ nslookup google.com
Server:    8.8.8.8
Address:   8.8.8.8#53

Non-authoritative answer:
Name:    google.com
Address: 142.250.207.46

$ nslookup -type=MX google.com    # 메일 서버 조회
$ nslookup -type=NS google.com    # 네임서버 조회
```

---

## 헷갈렸던 포인트

### Q: HTTP와 TCP는 어떤 관계인가?

TCP는 **전송 계층** 프로토콜이고, HTTP는 **애플리케이션 계층** 프로토콜이다. HTTP는 TCP 위에서 동작하며, TCP 입장에서 `GET / HTTP/1.1\r\n`은 그냥 텍스트 데이터일 뿐이다. telnet으로 TCP 소켓에 직접 HTTP 텍스트를 타이핑해도 동작하는 게 그 증거다.

### Q: HTTPS는 HTTP와 완전히 다른 프로토콜인가?

아니다. HTTPS = HTTP + SSL/TLS. HTTP와 TCP 사이에 암호화 계층(SSL/TLS)이 끼어드는 것뿐이다. HTTP 메시지 형식 자체는 완전히 동일하고, 전송 구간이 암호화된다는 차이만 있다. 포트도 80에서 443으로 다르다.

### Q: WebSocket은 HTTP와 관계없는 별개 기술인가?

아니다. WebSocket은 처음에 **HTTP 핸드셰이크**(101 Switching Protocols)로 시작한 뒤, 프로토콜을 업그레이드해서 TCP 직통 양방향 통신으로 전환한다. 일반 TCP 소켓으로도 이 핸드셰이크 규격만 맞추면 WebSocket을 구현할 수 있다.

### Q: HTTP에 무작정 TCP를 꽂으면?

된다. HTTP는 결국 TCP 위에서 정해진 형식의 텍스트를 주고받는 것이다. TCP 소켓을 열어서 `"GET / HTTP/1.1\r\nHost: example.com\r\n\r\n"`이라는 문자열을 보내면 실제로 HTTP 응답이 온다. 브라우저는 이걸 예쁘게 해주는 프로그램일 뿐이다.

### Q: localhost는 DNS를 통해 해석되나?

아니다. `localhost`는 OS의 **hosts 파일**(`/etc/hosts`)에서 직접 `127.0.0.1`로 매핑된다. DNS 해석 순서에서 hosts 파일은 외부 DNS 서버 질의보다 먼저 확인되므로, 외부 네트워크를 전혀 타지 않는다.

### Q: DNS 질의는 TCP인가 UDP인가?

기본적으로 **UDP 53번 포트**를 사용한다. DNS 질의/응답은 보통 짧은 데이터라 빠른 UDP가 적합하다. 단, 응답이 512바이트를 초과하거나 영역 전송(zone transfer) 같은 경우에는 TCP를 사용한다.

## 참고 자료

- [MDN - HTTP 개요](https://developer.mozilla.org/ko/docs/Web/HTTP/Overview)
- [MDN - WebSocket API](https://developer.mozilla.org/ko/docs/Web/API/WebSockets_API)
