---
title: "글로벌 트래픽 대응 아키텍처 — 멀티리전, CDN, 대규모 서비스 운영"
parent: Map System / 지도 시스템
nav_order: 4
---

# 글로벌 트래픽 대응 아키텍처 — 멀티리전, CDN, 대규모 서비스 운영

## 핵심 정리

### 글로벌 지도 서비스의 트래픽 특성

```
[지도 서비스 = 읽기 극도로 많고, 쓰기 적은 서비스]

  읽기/쓰기 비율: 약 1000:1 이상
  - 타일 요청: 한 화면에 ~20개 타일 동시 요청
  - 지도 이동/확대마다 추가 타일 요청
  - POI 검색: 텍스트 + 공간 복합 쿼리
  - 경로 탐색: CPU 집약적 그래프 연산

  트래픽 패턴:
  - 출퇴근 시간 피크 (AM 7~9, PM 5~7)
  - 지역별 시차 → 글로벌이면 피크가 분산
  - 이벤트성 폭증 (대규모 행사, 자연재해 시 경로 검색 급증)
  - 시즌 변동 (여행 시즌, 라마단 등)
```

### 1. 멀티리전 아키텍처

```
[왜 멀티리전이 필요한가?]

  서울 ↔ 리야드 네트워크 지연: ~200ms (왕복)
  서울 ↔ 호치민: ~80ms
  서울 ↔ 베이징: ~50ms

  지도 타일 20개 × 200ms = 4초 (체감 로딩 시간)
  → 사용자가 느끼기에 "느린 지도"

  목표: 각 지역에서 50ms 이내 응답

[멀티리전 배포 전략]

  ┌─────────────────────────────────────────────────┐
  │            Global Traffic Manager                │
  │    (DNS 기반 지역 라우팅: Route 53, Cloud DNS)    │
  │    사용자 IP → 가장 가까운 리전으로 라우팅          │
  └─────┬──────────────┬──────────────┬─────────────┘
        │              │              │
        ▼              ▼              ▼
  ┌──────────┐  ┌──────────┐  ┌──────────┐
  │ AP 리전   │  │ ME 리전   │  │ SEA 리전  │
  │ (서울)    │  │ (리야드)   │  │ (싱가포르) │
  │          │  │           │  │          │
  │ API서버   │  │ API서버    │  │ API서버   │
  │ 타일서버  │  │ 타일서버   │  │ 타일서버   │
  │ 검색서버  │  │ 검색서버   │  │ 검색서버   │
  │ DB(읽기)  │  │ DB(읽기)   │  │ DB(읽기)  │
  │ Redis     │  │ Redis     │  │ Redis    │
  └─────┬────┘  └─────┬────┘  └─────┬────┘
        │              │              │
        └──────────────┼──────────────┘
                       ▼
              ┌─────────────────┐
              │  Primary Region  │
              │  (서울 또는 싱가포르)│
              │  쓰기 전용 Master  │
              │  DB, Kafka       │
              └─────────────────┘
```

#### 데이터 복제 전략

```
[읽기 복제 — 가장 일반적]

  Primary DB (서울)
    → Read Replica (리야드)    : 비동기 복제, ~1초 지연
    → Read Replica (싱가포르)   : 비동기 복제, ~0.5초 지연

  쓰기: Primary로 라우팅 (해외에서 쓰기 지연 200ms+)
  읽기: 로컬 Replica에서 처리 (5ms 이내)

  지도 서비스는 읽기 99%+ → 이 모델이 적합

[지역별 데이터 분리 — 데이터 현지화]

  사우디 규제: 사우디 사용자 데이터는 사우디 DC에 저장
  중국 규제: 중국 데이터는 중국 내 저장 필수

  → 지역별 독립 DB + 글로벌 공용 데이터 동기화

  ┌──────────────────┐     ┌──────────────────┐
  │ 사우디 리전 DB     │     │ 한국 리전 DB       │
  │ - 사우디 POI      │     │ - 한국 POI        │
  │ - 사우디 사용자    │     │ - 한국 사용자      │
  │ - 사우디 리뷰     │     │ - 한국 리뷰        │
  └──────┬───────────┘     └──────┬───────────┘
         │                        │
         └────────┬───────────────┘
                  ▼
         ┌──────────────────┐
         │ Global Shared DB  │
         │ - 카테고리 마스터   │
         │ - 환율 정보        │
         │ - 공통 설정        │
         └──────────────────┘
```

### 2. CDN과 타일 캐싱

```
[지도 타일 = CDN의 최적 사용 사례]

  이유:
  - 정적 콘텐츠 (변경 빈도 낮음)
  - 작은 파일 (5~20KB)
  - 지역성 높음 (서울 사용자 → 서울 타일 요청)
  - 동일 타일 반복 요청 (인기 지역)

[CDN 배치 전략]

  ┌──────────────────────────────────────────────┐
  │              CDN Edge Locations               │
  │                                              │
  │  서울(15+) 리야드(2+) 싱가포르(5+) 호치민(2+)  │
  │  도쿄     제다       자카르타    하노이        │
  │  부산               쿠알라룸푸르               │
  └──────────────────┬───────────────────────────┘
                     │ Cache MISS
                     ▼
  ┌──────────────────────────────────────────────┐
  │            CDN Origin Shield                  │
  │     (리전별 1개, 오리진 부하 감소용)             │
  └──────────────────┬───────────────────────────┘
                     │
                     ▼
  ┌──────────────────────────────────────────────┐
  │            Tile Server (Origin)               │
  │     타일 렌더링 + 로컬 캐시 (Redis/NVMe)      │
  └──────────────────────────────────────────────┘

[캐시 계층]

  L1: 브라우저/앱 로컬 캐시     (0ms)
  L2: CDN Edge                 (~5ms)
  L3: CDN Origin Shield        (~20ms)
  L4: Tile Server Redis 캐시   (~2ms)
  L5: Tile Server 디스크 캐시   (~5ms)
  L6: 동적 렌더링              (~50~200ms)

  CDN 히트율 목표: 95%+ (L2에서 해결)
  전체 히트율: 99%+ (L6까지 가는 요청 1% 미만)

[캐시 무효화 전략]

  1. TTL 기반 (기본)
     - Zoom 0~10:  TTL 7일 (거의 변하지 않음)
     - Zoom 11~14: TTL 1일 (도로/건물 변경)
     - Zoom 15~18: TTL 1시간 (POI 변경 반영)

  2. 이벤트 기반 무효화
     POI 업데이트 → 해당 좌표의 타일 키 계산 → CDN Purge API
     → 변경된 타일만 선택적 무효화

  3. 버전닝
     URL: /tiles/v2026030601/{z}/{x}/{y}.pbf
     전체 배치 업데이트 시 버전 변경 → 기존 캐시 자연 만료
```

### 3. API 성능 최적화

```
[지도 API 성능 패턴]

  1. Viewport 기반 데이터 로딩
     클라이언트가 현재 화면 영역(Bounding Box) 전송
     → 서버는 해당 영역의 POI만 반환
     → 줌 레벨에 따라 반환 POI 밀도 조절

     Zoom 10: 주요 랜드마크만 (~50개)
     Zoom 14: 주요 상점/식당 (~200개)
     Zoom 17: 모든 POI (~500개)

  2. 클러스터링
     POI가 밀집된 영역 → 하나의 클러스터로 합산
     "강남역 주변 카페 127개" → 줌 인하면 개별 표시
     → 서버 사이드 클러스터링 (Supercluster 알고리즘)
     → 또는 클라이언트 사이드 (Mapbox GL JS 내장)

  3. 응답 압축
     - gzip/brotli: JSON API 응답 60~80% 압축
     - Protobuf: 벡터 타일 이미 바이너리, 추가 압축 20~30%
     - Delta Encoding: 이전 응답 대비 변경분만 전송

  4. 연결 최적화
     - HTTP/2 멀티플렉싱: 타일 20개를 하나의 연결로
     - HTTP/3 (QUIC): UDP 기반, 모바일 네트워크에서 유리
     - Connection Pooling: 백엔드 DB/Redis 연결 재사용
```

### 4. 대규모 트래픽에서의 안정성

```
[Circuit Breaker 패턴 — 장애 전파 방지]

  지도 서비스 구성:
  타일 서버 ← API서버 → 검색 서버
                     → 경로 서버
                     → 리뷰 서버

  경로 서버 장애 시:
  ❌ 전체 서비스 다운
  ✅ 경로만 "일시적 이용 불가", 지도/검색/리뷰 정상

  Circuit Breaker 상태:
  CLOSED → 정상 (요청 전달)
  OPEN   → 차단 (즉시 Fallback 반환)
  HALF_OPEN → 일부 요청만 시도 (복구 확인)

[Graceful Degradation — 단계적 기능 축소]

  Level 0: 정상 — 모든 기능 동작
  Level 1: 경미 — 실시간 교통 OFF, 캐시된 교통 정보 제공
  Level 2: 보통 — 리뷰/사진 OFF, POI 기본 정보만
  Level 3: 심각 — 검색 OFF, 타일 + 캐시된 POI만
  Level 4: 비상 — 정적 타일만 (CDN에서 서빙)

[Rate Limiting — 지도 API 특화]

  지도 API는 일반 API보다 호출 빈도가 높음:
  - 타일: 화면 이동 시 초당 수십 요청
  - 검색: 타이핑마다 자동완성 요청

  전략:
  - 타일: IP/사용자별 초당 100요청 제한
  - 검색: IP/사용자별 초당 10요청 제한
  - 경로: IP/사용자별 분당 30요청 제한
  - API Key별 일간 쿼터 (무료: 10만/일, 유료: 1000만/일)

  구현:
  - API Gateway 레벨 (Kong, Envoy)
  - Redis 기반 Sliding Window Counter
  - Token Bucket 알고리즘
```

### 5. 모니터링과 관측성 (Observability)

```
[지도 서비스 핵심 메트릭]

  비즈니스 메트릭:
  - 타일 로딩 시간 (P50, P95, P99)
  - 검색 응답 시간
  - 첫 의미 있는 지도 표시 시간 (FMP: First Meaningful Paint)
  - 경로 탐색 성공률

  인프라 메트릭:
  - CDN 히트율 (목표: 95%+)
  - DB 커넥션 풀 사용률
  - Kafka Consumer Lag
  - OpenSearch 쿼리 레이턴시

  데이터 품질 메트릭:
  - POI 업데이트 지연 (배치 완료 시간)
  - 실시간 파이프라인 지연 (Kafka → DB)
  - 데이터 품질 스코어 추이

[분산 추적 — 글로벌 서비스 디버깅]

  사용자 요청 (리야드)
    → API Gateway (리야드)
    → Search Service (리야드)
    → OpenSearch (리야드 Replica)
    → POI Service (리야드)
    → PostgreSQL (리야드 Read Replica)

  OpenTelemetry로 전체 흐름 추적
  Trace ID로 리전 간 요청 연결
  Jaeger/Tempo에서 시각화

[장애 대응 — 글로벌 특수성]

  시차로 인한 대응 체계:
  - 한국 (UTC+9): 주간 → 한국 팀 대응
  - 사우디 (UTC+3): 한국 심야 → 현지/온콜 팀
  - 베트남 (UTC+7): 한국과 2시간 차 → 상호 커버

  Runbook 필수:
  - 각 장애 시나리오별 대응 절차
  - 영어로 작성 (글로벌 팀 공용)
  - PagerDuty/OpsGenie 자동 호출
```

### 6. 해외 개발자 협업 — 기술적 관점

```
[글로벌 팀과의 기술 협업 포인트]

  1. API 계약 우선 (Contract First)
     - OpenAPI(Swagger) 스펙으로 API 정의
     - 스펙 리뷰 후 구현 → 의사소통 비용 감소
     - gRPC + Protobuf: 타입 안전, 언어 무관

  2. 코드 리뷰 비동기화
     - 시차 때문에 실시간 리뷰 어려움
     - PR에 충분한 컨텍스트 작성 (Why, What, How)
     - 자동화된 코드 품질 체크 (Linter, Test, SAST)

  3. 문서 공용어: 영어
     - ADR (Architecture Decision Records) 영어 작성
     - Confluence/Notion Wiki 영어 기준
     - 코드 주석, 커밋 메시지 영어

  4. 타임존 고려 설계
     - 배포 윈도우: 각 리전 비피크 시간대
     - 회의: 겹치는 시간대 활용 (보통 오후 2~5시 KST)
     - 비동기 커뮤니케이션 도구: Slack, Jira, Confluence
```

---

## 헷갈렸던 포인트

### Q1: 멀티리전 DB — 모든 리전에 Write를 허용하면 안 되나?

```
[Single-Writer (단일 쓰기 리전)]
  Primary: 서울 (쓰기)
  Replica: 리야드, 싱가포르 (읽기만)

  장점: 데이터 일관성 보장 (충돌 없음)
  단점: 해외에서 쓰기 지연 (200ms+)

[Multi-Writer (다중 쓰기 리전)]
  서울도 쓰기, 리야드도 쓰기

  문제:
  - 같은 POI를 서울과 리야드에서 동시 수정하면?
  - Conflict Resolution 필요 (Last-Write-Wins, CRDT 등)
  - 복잡도 폭발

[지도 서비스 선택]
  → 대부분 Single-Writer + Read Replica
  → 이유: POI 수정은 관리자/배치 작업이 대부분
  → 사용자 리뷰 같은 경우: 지역별 독립 DB (충돌 가능성 없음)
```

### Q2: CDN에서 사우디 리전 Edge가 부족하면?

```
[중동 CDN 커버리지 현황 (2026)]

  AWS CloudFront: 바레인(1), UAE(1+)
  Cloudflare: 리야드, 제다, 두바이, 바레인 등 10+ PoP
  Akamai: 중동 20+ PoP (가장 넓은 커버리지)

  대안 전략:
  1. 현지 CDN 업체 활용 (GulfCDN, Alibaba Cloud ME)
  2. 자체 캐시 서버 사우디 DC에 배치
  3. Multi-CDN: 주 CDN + 보조 CDN → DNS로 분배

  사우디 데이터 현지화:
  - 사용자 데이터: 사우디 DC 필수
  - 타일/지도 데이터: CDN 캐시 OK (공개 데이터)
  - 개인정보 미포함 API: CDN 캐시 가능
```

### Q3: 지도 서비스에서 Redis를 어디에 쓰나?

```
[Redis 활용 패턴]

  1. 타일 캐시 (Hot Tile Cache)
     인기 지역 타일을 Redis에 캐싱
     Key: tile:{z}:{x}:{y}
     Value: 바이너리 타일 데이터
     TTL: Zoom 레벨별 차등

  2. 실시간 교통 데이터
     Key: traffic:link:{linkId}
     Value: {speed: 45, level: "slow", updatedAt: ...}
     TTL: 5분 (갱신되지 않으면 자동 삭제)

  3. 세션/인증 캐시
     사용자 세션, API Key 검증 결과 캐싱

  4. Rate Limiting
     Sliding Window Counter
     Key: ratelimit:{apiKey}:{window}
     INCR + EXPIRE

  5. 실시간 위치 (GEO)
     GEOADD drivers 127.027 37.498 "driver:123"
     GEORADIUS drivers 127.0 37.5 3 km
     → 근처 택시/배달원 실시간 검색

  6. 검색 자동완성 캐시
     Key: autocomplete:{locale}:{prefix}
     Value: 상위 10개 결과
     TTL: 1시간
```

---

## 참고 자료

| 자료 | 설명 |
|------|------|
| [AWS Global Infrastructure](https://aws.amazon.com/about-aws/global-infrastructure/) | AWS 리전/Edge 위치 맵 |
| [Cloudflare Network Map](https://www.cloudflare.com/network/) | Cloudflare 글로벌 PoP 현황 |
| [OpenTelemetry](https://opentelemetry.io/) | 분산 추적/메트릭/로그 표준 |
| [Envoy Proxy](https://www.envoyproxy.io/) | 클라우드 네이티브 프록시 (Rate Limiting, Circuit Breaking) |
| [CockroachDB Multi-Region](https://www.cockroachlabs.com/docs/stable/multiregion-overview.html) | 분산 SQL DB 멀티리전 설계 참고 |
| [Google SRE Book — Managing Incidents](https://sre.google/sre-book/managing-incidents/) | 글로벌 장애 대응 표준 참고서 |
