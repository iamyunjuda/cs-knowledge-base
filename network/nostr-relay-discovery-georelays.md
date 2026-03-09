# Nostr 릴레이 탐색과 지오로케이션 — GeoRelays 프로젝트 분석

## 핵심 정리

### GeoRelays가 뭔가?

[permissionlesstech/georelays](https://github.com/permissionlesstech/georelays)는 **Nostr 프로토콜**의 릴레이 서버를 자동으로 발견하고, 동작 여부를 검증한 뒤, **IP 지오로케이션**으로 전 세계 지도에 시각화하는 파이프라인 프로젝트다.

```
┌─────────────────────────────────────────────────────────┐
│                  GeoRelays 파이프라인                      │
│                                                         │
│  Stage 1             Stage 2              Stage 3       │
│  ┌──────────┐       ┌──────────┐        ┌──────────┐   │
│  │ Relay     │──────▶│ BitChat  │───────▶│ Geo      │   │
│  │ Discovery │       │ Filter   │        │ Lookup   │   │
│  │ (BFS 크롤)│       │ (kind    │        │ (IP→좌표) │   │
│  │           │       │  20000)  │        │          │   │
│  └──────────┘       └──────────┘        └──────────┘   │
│       │                   │                   │         │
│       ▼                   ▼                   ▼         │
│  relay_discovery     bitchat_relays      nostr_relays   │
│  _results.json       (stdout)            .csv           │
│                                          (lat, lon)     │
│                           │                             │
│                           ▼                             │
│                  ┌─────────────────┐                    │
│                  │  시각화 (Maps)    │                    │
│                  │  - 정적 지도 PNG  │                    │
│                  │  - 히트맵 PNG    │                    │
│                  │  - 인터랙티브 HTML│                    │
│                  └─────────────────┘                    │
└─────────────────────────────────────────────────────────┘
```

---

### Nostr 프로토콜이란?

Nostr(**N**otes and **O**ther **S**tuff **T**ransmitted by **R**elays)는 **탈중앙화 소셜 프로토콜**이다. Twitter/X 같은 중앙 서버 없이, 여러 개의 **릴레이(Relay)** 서버를 통해 메시지를 주고받는다.

```
┌──────────────────────────────────────────────────────┐
│              Nostr 아키텍처 개요                        │
│                                                      │
│   Client A ──WebSocket──▶ Relay 1 ◀──WebSocket── Client B  │
│      │                      │                        │
│      │                      │  (릴레이끼리는 직접      │
│      │                      │   통신하지 않음)         │
│      └──WebSocket──▶ Relay 2 ◀──WebSocket── Client C  │
│                         │                            │
│                    Relay 3                            │
│                                                      │
│  - 클라이언트가 여러 릴레이에 동시 연결                    │
│  - 릴레이는 독립적인 WebSocket 서버                      │
│  - 중앙 서버 없음 → 검열 저항성                          │
└──────────────────────────────────────────────────────┘
```

#### Nostr의 핵심 개념

| 개념 | 설명 |
|------|------|
| **Event** | Nostr의 기본 데이터 단위. JSON 형태. 서명(Schnorr) 포함 |
| **Kind** | Event의 종류를 나타내는 숫자. kind 1 = 텍스트 노트, kind 3 = 팔로우 리스트 |
| **Relay** | WebSocket 서버. Event를 저장하고 구독자에게 전달 |
| **NIP** | Nostr Implementation Possibilities. 프로토콜 확장 명세 |
| **공개키/비밀키** | Ed25519 키 쌍으로 신원 관리. 계정 = 공개키 |

#### Event 구조 (간략)

```json
{
  "id": "이벤트 해시 (SHA-256)",
  "pubkey": "작성자 공개키 (hex)",
  "created_at": 1234567890,
  "kind": 1,
  "tags": [
    ["r", "wss://relay.example.com"],
    ["p", "상대방_공개키", "wss://hint-relay.com"]
  ],
  "content": "Hello Nostr!",
  "sig": "Schnorr 서명"
}
```

---

### Stage 1: 릴레이 탐색 — BFS로 Nostr 네트워크 크롤링

GeoRelays의 핵심은 **소셜 그래프를 따라가며 릴레이를 발견하는 BFS(너비 우선 탐색)**이다.

#### 동작 원리

```
┌─────────────────────────────────────────────────────────┐
│              BFS 릴레이 탐색 흐름                          │
│                                                         │
│  1. 시드 릴레이에서 시작                                   │
│     wss://relay.damus.io                                │
│         │                                               │
│  2. kind 3 (팔로우 리스트) + kind 10002 (릴레이 리스트) 수집│
│         │                                               │
│         ▼                                               │
│  ┌─────────────────────────────────┐                    │
│  │  Event에서 릴레이 URL 추출        │                    │
│  │  - "r" 태그: ["r", "wss://..."] │                    │
│  │  - "p" 태그 3번째 요소 (릴레이 힌트)│                   │
│  └──────────┬──────────────────────┘                    │
│             │                                           │
│  3. 발견된 릴레이마다 검증                                  │
│         │                                               │
│         ▼                                               │
│  ┌─────────────────────────────────┐                    │
│  │  WebSocket 연결 → REQ 전송       │                    │
│  │  → 응답 확인:                    │                    │
│  │    EVENT/EOSE → 정상 (functioning)│                   │
│  │    NOTICE/에러 → 비정상           │                    │
│  │    타임아웃 → 비정상              │                    │
│  └──────────┬──────────────────────┘                    │
│             │                                           │
│  4. 정상 릴레이에서 다시 2번 반복 (BFS 큐)                  │
│             │                                           │
│  5. 더 이상 새 릴레이가 없을 때까지 반복                     │
│                                                         │
│  결과: ~2,679개 테스트 → ~699개 정상 (약 35% 생존율)       │
└─────────────────────────────────────────────────────────┘
```

#### 왜 kind 3과 kind 10002인가?

| Kind | 이름 | GeoRelays에서의 역할 |
|------|------|---------------------|
| **kind 3** | Contact List (팔로우 리스트) | 사용자가 팔로우하는 사람의 릴레이 정보 포함. `p` 태그에 릴레이 URL 힌트 |
| **kind 10002** | Relay List (NIP-65) | 사용자가 "나는 이 릴레이들을 쓴다"고 명시적으로 선언한 목록 |

웹 크롤러가 하이퍼링크를 따라가듯, GeoRelays는 **소셜 그래프의 릴레이 메타데이터**를 따라간다.

#### 검증 방식의 엄격함

단순 TCP 연결 확인이 아니라, **실제 Nostr 프로토콜 메시지를 주고받아** 정상 동작을 확인한다:

```
클라이언트                        릴레이
    │                              │
    │──── WebSocket 연결 ──────────▶│
    │                              │
    │──── ["REQ", "sub_id",       │
    │      {"kinds": [1],         │
    │       "limit": 1}] ────────▶│
    │                              │
    │◀──── ["EVENT", "sub_id",    │  ← 정상 응답
    │       {...}] ───────────────│
    │                              │
    │◀──── ["EOSE", "sub_id"]     │  ← End of Stored Events
    │       ──────────────────────│
    │                              │
    │  → 이 릴레이는 "functioning"    │
```

#### 구현 디테일

```
설정값:
- 연결 타임아웃: 5초
- 응답 타임아웃: 5초
- 이벤트 수집 타임아웃: 30초
- 릴레이당 최대 이벤트 수: 300개
- 동시 처리 배치: 10개 (asyncio)
- 최대 메시지 크기: 1MB
- 진행 저장 주기: 10개 릴레이마다

증분 실행 (Incremental):
- 이전 결과(relay_discovery_results.json)를 로드
- 기존에 정상이었던 릴레이를 다음 실행의 시드로 사용
- 매일 실행할수록 데이터셋이 단조증가
```

---

### Stage 2: BitChat 필터링

**BitChat**은 Nostr 위에서 동작하는 채팅 프로토콜로, **kind 20000** 이벤트를 사용한다. 모든 릴레이가 이를 지원하지는 않으므로 별도 필터링이 필요하다.

```bash
# 각 릴레이에 대해 Read + Write 테스트
# Read: kind 20000 이벤트 조회 가능한지
nak req -k 20000 wss://relay.example.com  # 10초 타임아웃

# Write: kind 20000 이벤트 발행 가능한지
nak event -k 20000 -t n=test -t g=test wss://relay.example.com

# 두 테스트 모두 통과한 릴레이만 출력
# xargs -P 10으로 병렬 처리
```

- `nak`: fiatjaf가 만든 Nostr CLI 도구
- Read/Write **모두** 성공해야 BitChat 호환으로 판정

---

### Stage 3: IP 지오로케이션

릴레이 URL의 호스트명을 **IP 주소 → 위도/경도**로 변환한다.

```
┌─────────────────────────────────────────────────────┐
│              지오로케이션 파이프라인                      │
│                                                     │
│  wss://relay.example.com                            │
│         │                                           │
│  1. DNS 해석 (getaddrinfo, IPv4만)                   │
│         │                                           │
│         ▼                                           │
│  93.184.216.34                                      │
│         │                                           │
│  2. DB-IP 데이터베이스에서 IP 범위 검색                  │
│     (Binary Search - bisect_right)                  │
│         │                                           │
│         ▼                                           │
│  ┌─────────────────────────────────┐                │
│  │  IP 범위 테이블 (CSV → 메모리)    │                │
│  │                                 │                │
│  │  시작 IP    | 끝 IP     | 위치   │                │
│  │  93.184.0.0 | 93.184.255.255    │                │
│  │  → lat: 41.84, lon: -72.68     │                │
│  └─────────────────────────────────┘                │
│         │                                           │
│         ▼                                           │
│  출력: relay.example.com, 41.84, -72.68             │
│                                                     │
│  한계:                                               │
│  - IPv4만 지원 (IPv6 릴레이는 건너뜀)                  │
│  - 호스트당 첫 번째 A 레코드만 사용                     │
│  - CDN/Anycast IP는 실제 위치와 다를 수 있음            │
└─────────────────────────────────────────────────────┘
```

#### Binary Search가 여기서 쓰이는 이유

IP 주소를 정수로 변환하면, DB-IP의 수십만 개 IP 범위를 **정렬된 배열**로 만들 수 있다. `bisect_right`로 O(log n) 검색이 가능해 별도의 GeoIP 라이브러리 없이도 빠르게 동작한다.

```python
# 개념적 구현
start_ips = [ip_to_int("1.0.0.0"), ip_to_int("1.0.1.0"), ...]  # 정렬됨
end_ips   = [ip_to_int("1.0.0.255"), ip_to_int("1.0.1.255"), ...]
locations = [(lat1, lon1), (lat2, lon2), ...]

idx = bisect.bisect_right(start_ips, target_ip) - 1
if start_ips[idx] <= target_ip <= end_ips[idx]:
    return locations[idx]  # (latitude, longitude)
```

---

### CI/CD: 3단계 워크플로우 체인

GitHub Actions로 매일 자동 실행되며, **workflow_run** 트리거로 의존성 체인을 구성한다.

```
┌─────────────────────────────────────────────────────┐
│           GitHub Actions 워크플로우 체인                │
│                                                     │
│  ① update-relay-data.yml                            │
│     (매일 06:00 UTC / 수동)                           │
│     - 릴레이 탐색 (BFS)                               │
│     - BitChat 필터링                                  │
│     - 지오로케이션                                     │
│     - 결과 커밋: relay_discovery_results.json          │
│                  nostr_relays.csv                    │
│         │                                           │
│         │ workflow_run (완료 시 트리거)                 │
│         ▼                                           │
│  ② relay-count-tracker.yml                          │
│     - git 히스토리에서 릴레이 수 추이 추출               │
│     - 최근 70개 커밋 분석                              │
│     - 트렌드 차트 생성                                 │
│         │                                           │
│         │ workflow_run                               │
│         ▼                                           │
│  ③ relay-maps.yml                                   │
│     - 정적 지도 (Cartopy → PNG)                       │
│     - 히트맵 (scipy Gaussian → PNG)                   │
│     - 인터랙티브 지도 (Folium → HTML)                  │
│                                                     │
│  핵심: 데이터 갱신 → 통계 → 시각화 순서 보장             │
└─────────────────────────────────────────────────────┘
```

---

### 시각화 결과

| 유형 | 도구 | 특징 |
|------|------|------|
| **정적 지도 PNG** | Cartopy | 해안선, 국경, 하천, 격자선 포함. 정확한 지도 투영 |
| **히트맵 PNG** | scipy (Gaussian filter) | 360x180 그리드에 밀도 스무딩. 릴레이 집중 지역 시각화 |
| **인터랙티브 HTML** | Folium + MarkerCluster | 클릭으로 탐색. 줌 레벨에 따라 클러스터링 |

현재 데이터: **289개** BitChat 호환 릴레이가 전 세계에 분포. 토론토(캐나다) 호스팅 인프라에 집중 경향.

---

### 기술 스택 요약

| 영역 | 기술 |
|------|------|
| 릴레이 크롤링 | Python asyncio + websockets |
| BitChat 필터 | Bash + nak (Nostr CLI) |
| 지오로케이션 | DB-IP CSV + bisect (Binary Search) |
| 시각화 | matplotlib, Cartopy, Folium, scipy |
| CI/CD | GitHub Actions (workflow_run 체인) |
| 데이터 | pandas, numpy |

---

## 헷갈렸던 포인트

### Q1. Nostr 릴레이끼리는 통신하나?

**아니다.** Nostr 릴레이는 서로 직접 통신하지 않는다. 각 릴레이는 독립적인 WebSocket 서버이고, **클라이언트가 여러 릴레이에 동시 접속**하여 메시지를 전파하는 구조다. 그래서 릴레이 목록을 알려면 릴레이 자체가 아니라 **사용자들의 Event(kind 3, kind 10002)**를 통해 간접적으로 발견해야 한다.

### Q2. 왜 BFS인가? 다른 방법은?

Nostr에는 "릴레이 디렉토리"가 공식적으로 없다. 각 사용자가 자신이 사용하는 릴레이를 Event로 공개하므로, 소셜 그래프를 따라가는 BFS가 가장 자연스럽다. 웹 크롤러가 하이퍼링크를 따라가는 것과 같은 원리.

### Q3. 릴레이 검증을 왜 프로토콜 수준으로 하나?

TCP 포트가 열려 있어도 **Nostr 프로토콜을 지원하지 않는 서버**일 수 있다. 또한 WebSocket은 연결되지만 Nostr `REQ`에 제대로 응답하지 않는 릴레이도 있다. 실제 `EVENT`/`EOSE` 응답까지 확인해야 진짜 동작하는 릴레이인지 알 수 있다.

### Q4. IP 지오로케이션은 정확한가?

대략적이다. **CDN이나 Anycast를 사용하는 릴레이**는 실제 서버 위치와 IP 기반 추정 위치가 다를 수 있다. 또한 IPv6 전용 릴레이는 아예 처리되지 않는다. 그래도 전 세계 릴레이 분포의 **전체적인 경향**을 파악하기에는 충분하다.

### Q5. 증분 실행(Incremental)이 왜 중요한가?

한 번의 BFS로는 네트워크 전체를 탐색할 수 없다. 시드 릴레이에서 도달 가능한 범위만 탐색되기 때문이다. 매일 실행하면서 **이전에 발견한 정상 릴레이를 다음 실행의 시드로 추가**하면, 탐색 범위가 점점 넓어져 더 많은 릴레이를 발견할 수 있다.

---

## 참고 자료

- [GeoRelays GitHub](https://github.com/permissionlesstech/georelays)
- [Nostr 프로토콜 (nostr-protocol/nostr)](https://github.com/nostr-protocol/nostr)
- [NIP-01: Basic Protocol](https://github.com/nostr-protocol/nips/blob/master/01.md)
- [NIP-65: Relay List Metadata (kind 10002)](https://github.com/nostr-protocol/nips/blob/master/65.md)
- [nak - Nostr CLI Tool](https://github.com/fiatjaf/nak)
- [DB-IP Geolocation Database](https://db-ip.com/)
