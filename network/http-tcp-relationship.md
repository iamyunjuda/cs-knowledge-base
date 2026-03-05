# HTTP/HTTPS와 TCP의 관계

## 핵심 정리

### TCP는 텍스트를 전송하는 기술이다

TCP는 채팅앱처럼 **텍스트(바이트)를 전송하는 기술**이다. TCP 자체는 전송하는 내용이 뭔지 관심 없다.

그 텍스트를 **해석하는 방식**에 따라 다른 프로토콜이 완성된다:

| 해석 방식 | 결과 |
|-----------|------|
| HTTP 규격으로 해석 | 웹 통신 (HTTP/HTTPS) |
| SSH 규격으로 해석 | 원격 접속 (SSH) |
| 자체 규격으로 해석 | 소켓 채팅 |
| WebSocket 규격으로 해석 | 실시간 양방향 통신 |

### HTTP / HTTPS

- **HTTP**: 통신 프로토콜 중 하나. TCP 위에서 텍스트 기반으로 요청/응답을 주고받는 규격
- **HTTPS**: HTTP + SSL/TLS 인증서를 통한 보안 통신. 전송 데이터를 암호화

둘 다 **TCP 통신을 통해 전송**이 이루어진다. TCP 입장에서 보면 HTTP는 그냥 텍스트 전송일 뿐이다.

### WebSocket과 TCP

WebSocket(WS)도 결국 TCP 위에서 동작한다. 일반 TCP 소켓으로 WebSocket을 구현할 수 있는데, 핵심은 그냥 TCP에서 실시간 양방향 통신을 하는 것이다.

> HTTP에 무작정 TCP를 꽂아도 전송이 된다 — TCP는 그만큼 범용적인 전송 계층이다.

### 계층 구조

```
[애플리케이션 계층]  HTTP / HTTPS / WebSocket / SSH / FTP ...
         ↓
[전송 계층]          TCP (또는 UDP)
         ↓
[네트워크 계층]      IP
```

## localhost와 DNS

### localhost란?

- `localhost`는 **자기 자신(루프백 주소)**을 가리키는 호스트명
- IP 주소로는 `127.0.0.1` (IPv4) 또는 `::1` (IPv6)

### localhost는 DNS를 거치지 않는다

일반 도메인(예: `google.com`)은 DNS 서버에 질의해서 IP를 알아내지만, `localhost`는 **OS의 hosts 파일**에서 직접 해석된다.

```
# /etc/hosts (Linux/Mac) 또는 C:\Windows\System32\drivers\etc\hosts (Windows)
127.0.0.1   localhost
::1         localhost
```

### DNS 해석 순서

브라우저에 도메인을 입력했을 때 IP를 찾는 순서:

1. **브라우저 DNS 캐시** — 브라우저가 이미 알고 있는지 확인
2. **OS DNS 캐시** — 운영체제 캐시 확인
3. **hosts 파일** — `/etc/hosts`에 직접 매핑된 항목 확인 ← `localhost`는 여기서 해석됨
4. **DNS 서버 질의** — 위에서 못 찾으면 외부 DNS 서버(예: `8.8.8.8`)에 질의

> `localhost`는 3단계(hosts 파일)에서 바로 `127.0.0.1`로 해석되므로 외부 DNS 서버까지 갈 필요가 없다.

### hosts 파일 활용

hosts 파일에 직접 도메인을 매핑할 수도 있다:

```
127.0.0.1   my-local-api.dev
127.0.0.1   test.example.com
```

이렇게 하면 `my-local-api.dev`로 접속해도 로컬 서버로 연결된다. 개발 환경에서 자주 사용하는 기법이다.

## 헷갈렸던 포인트

### Q: HTTP와 TCP는 어떤 관계인가?

TCP는 **전송 계층** 프로토콜이고, HTTP는 **애플리케이션 계층** 프로토콜이다. HTTP는 TCP 위에서 동작하며, TCP 입장에서 HTTP 메시지는 그냥 텍스트 데이터일 뿐이다.

### Q: HTTPS는 HTTP와 완전히 다른 프로토콜인가?

아니다. HTTPS는 HTTP에 **SSL/TLS 암호화 계층**을 추가한 것이다. 통신 방식은 동일하고, 전송 구간이 암호화된다는 차이만 있다.

### Q: WebSocket은 HTTP와 관계없는 별개 기술인가?

아니다. WebSocket 연결은 처음에 **HTTP 핸드셰이크**로 시작한 뒤 프로토콜을 업그레이드한다. 이후에는 TCP 위에서 직접 양방향 통신한다.

### Q: localhost는 DNS를 통해 해석되나?

아니다. localhost는 OS의 **hosts 파일**에서 직접 `127.0.0.1`로 매핑되므로 외부 DNS 서버에 질의하지 않는다.

## 참고 자료

- [MDN - HTTP 개요](https://developer.mozilla.org/ko/docs/Web/HTTP/Overview)
- [MDN - WebSocket API](https://developer.mozilla.org/ko/docs/Web/API/WebSockets_API)
