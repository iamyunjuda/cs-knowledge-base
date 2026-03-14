---
title: "공간 인덱싱과 지도 시스템 기초 — POI, 타일링, Geocoding"
parent: Map System / 지도 시스템
nav_order: 1
tags: [R-Tree, Geohash, S2, H3, POI, 타일링, Geocoding, PostGIS]
description: "R-Tree/Geohash/S2/H3 공간 인덱싱, POI 데이터 모델, 지도 타일링, Geocoding, 경로 탐색 알고리즘, PostGIS vs OpenSearch를 정리합니다."
---

# 공간 인덱싱과 지도 시스템 기초 — POI, 타일링, Geocoding

## 핵심 정리

### 지도 서비스의 핵심 구성 요소

```
[지도 서비스 아키텍처]

┌──────────────────────────────────────────────────┐
│                   클라이언트                        │
│   지도 렌더링 (Tile) + POI 검색 + 경로 탐색           │
└──────────────┬───────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────┐
│                   API Gateway                     │
│   인증, Rate Limiting, 라우팅                       │
└──────────────┬───────────────────────────────────┘
               │
  ┌────────────┼────────────┬──────────────┐
  ▼            ▼            ▼              ▼
[Tile]     [Search]    [Routing]     [Place/POI]
타일 서버    검색 서버     경로 서버      장소 서버

  │            │            │              │
  ▼            ▼            ▼              ▼
[Tile DB]  [OpenSearch]  [Graph DB]   [PostgreSQL]
타일 캐시    역인덱스      도로 그래프    + PostGIS
(CDN)      공간 인덱스    가중치 그래프   공간 인덱스
```

### 1. 공간 데이터의 본질

일반 DB는 1차원 데이터(숫자, 문자열)를 정렬하여 B-Tree로 인덱싱한다.
하지만 위도/경도 좌표는 **2차원** → B-Tree 하나로는 "근처" 검색이 불가능하다.

```
[문제: "내 주변 500m 식당 찾기"]

  B-Tree(위도) 인덱스: 위도 37.5000 ~ 37.5050 범위 검색 가능
  B-Tree(경도) 인덱스: 경도 126.9900 ~ 126.9950 범위 검색 가능

  → 두 인덱스를 각각 타고 교집합? 비효율적
  → 공간 인덱스가 필요한 이유
```

### 2. 공간 인덱싱 기법

#### R-Tree (Rectangle Tree)

```
[R-Tree 구조 — PostGIS, MySQL Spatial의 기본]

  공간을 겹치는 사각형(MBR: Minimum Bounding Rectangle)으로 분할

  Level 0 (Root):  [────────────────────────]
                   전체 영역

  Level 1:        [──────]    [──────────]
                   서울          경기

  Level 2:      [──] [──]   [───] [───]
                강남  송파    수원   성남

  Leaf:         P1 P2 P3    P4 P5 P6 P7
                (실제 POI 좌표들)

  "근처 검색" → 루트에서 내려가며 겹치는 사각형만 탐색
  시간복잡도: O(log N) ~ O(√N)
```

**장점**: 범위 검색, KNN(K-Nearest Neighbor) 쿼리에 효율적
**단점**: 삽입/갱신 시 트리 재균형 비용, 겹치는 영역이 많으면 성능 저하

#### Geohash

```
[Geohash — 2차원 좌표를 1차원 문자열로 인코딩]

  위도 37.5665, 경도 126.9780
    → Geohash: "wydm9q"  (precision 6, ~1.2km x 0.6km)

  인코딩 원리:
  1. 위도 범위 [-90, 90]을 반복 이등분하여 0/1 비트 생성
  2. 경도 범위 [-180, 180]을 반복 이등분하여 0/1 비트 생성
  3. 경도/위도 비트를 번갈아 합침
  4. Base32로 인코딩

  핵심 성질:
  - 같은 접두사(prefix) = 같은 지역
    "wydm9q..." ← 서울시청 부근
    "wydm9r..." ← 서울시청 인접
  - 문자열이 길수록 더 좁은 영역
    "w"          → 대한민국 전체 포함
    "wydm"       → 서울 일부
    "wydm9q"     → 약 1km² 영역
    "wydm9qhj3"  → 약 1m² 영역

  [장점]
  - B-Tree 인덱스로 공간 검색 가능 (WHERE geohash LIKE 'wydm9%')
  - Redis Sorted Set으로 근접 검색 가능
  - 분산 시스템에서 파티션 키로 활용

  [단점 — Edge Problem]
  ┌────┬────┐
  │ A  │ B  │  ← A와 B는 인접하지만 Geohash 접두사가 완전히 다를 수 있음
  │  * │ *  │     (예: "wydm" vs "wydp")
  └────┴────┘
  해결: 검색 시 주변 8개 셀도 함께 조회
```

#### S2 Geometry (Google)

```
[S2 — 구(Sphere)를 기반으로 한 셀 시스템]

  Geohash의 평면 투영 왜곡 문제를 해결
  지구를 정육면체에 투영 → 각 면을 Hilbert Curve로 분할

  Cell Level별 크기:
  Level 0  : 지구의 1/6 (정육면체 한 면)
  Level 12 : ~3.3km²
  Level 15 : ~0.05km² (≈50m x 50m)
  Level 20 : ~0.5m²
  Level 30 : ~1cm²

  핵심 장점:
  1. 구면 기반 → Geohash보다 면적 균일
  2. Hilbert Curve → 공간적으로 가까운 점은 ID도 가까움
  3. Cell Covering → 임의 도형을 최소 셀 집합으로 커버 가능
     "서울시 강남구 영역" → S2 셀 집합으로 표현

  [사용처]
  - Google Maps, Google BigQuery GIS
  - Uber H3의 영감 원천
  - DynamoDB 공간 인덱싱 (amazon-dynamodb-geo 라이브러리)
```

#### H3 (Uber)

```
[H3 — 정육각형 격자 시스템]

  S2의 사각형 격자 대신 정육각형(Hexagon) 사용

  왜 육각형?
  ┌───┐         ╱╲    ╱╲
  │   │        ╱  ╲──╱  ╲
  │   │  vs   │    ││    │  ← 인접 셀까지 거리가 균일
  │   │        ╲  ╱──╲  ╱     (사각형은 대각선 √2배)
  └───┘         ╲╱    ╲╱

  Resolution별 크기:
  Res 0  : ~4,357km²
  Res 7  : ~5.16km²
  Res 9  : ~0.105km² (≈105m x 105m)
  Res 12 : ~0.003km²
  Res 15 : ~0.0001km²

  [사용처]
  - Uber: 동적 가격 책정(Surge Pricing) 지역 분할
  - 배달 서비스: 배달 구역 관리
  - 통신사: 기지국 커버리지 분석
  - 역학 조사: 감염 밀도 분석
```

#### 비교 정리

```
┌──────────┬──────────┬──────────────┬─────────────┬───────────┐
│  기법     │ 차원     │ 면적 균일성    │ 구현 난이도   │ 대표 사용처 │
├──────────┼──────────┼──────────────┼─────────────┼───────────┤
│ R-Tree   │ 다차원    │ N/A(동적)     │ 중간        │ PostGIS   │
│ Geohash  │ 2D→1D   │ 극지방 왜곡    │ 쉬움        │ Redis     │
│ S2       │ 구면     │ 균일         │ 복잡        │ Google    │
│ H3       │ 구면     │ 매우 균일     │ 중간        │ Uber      │
│ Quadtree │ 2D      │ 균일(평면)    │ 쉬움        │ 게임/충돌   │
└──────────┴──────────┴──────────────┴─────────────┴───────────┘
```

### 3. POI (Point of Interest) 시스템

```
[POI = 지도 위의 의미 있는 장소]
  식당, 카페, 주유소, 관광지, 호텔, ATM 등

[POI 데이터 모델 — 네이버 지도 같은 서비스]

  poi {
    id: BIGINT (PK)
    name: VARCHAR            -- "스타벅스 강남역점"
    name_local: JSONB        -- {"ko": "스타벅스", "en": "Starbucks", "ar": "ستاربكس"}
    category_id: INT         -- FK → categories (음식점 > 카페)
    location: GEOGRAPHY      -- PostGIS POINT(126.978, 37.566)
    geohash: VARCHAR(12)     -- 인덱스용
    h3_index: BIGINT         -- H3 셀 인덱스
    address: JSONB           -- {"country":"KR", "city":"서울", "street":"..."}
    phone: VARCHAR
    opening_hours: JSONB     -- 영업시간 규칙
    rating: DECIMAL(2,1)     -- 평균 평점
    review_count: INT
    source: VARCHAR          -- "naver", "google", "osm", "local_partner"
    quality_score: DECIMAL   -- 데이터 신뢰도 점수
    created_at: TIMESTAMP
    updated_at: TIMESTAMP
  }

  인덱스:
  - GIST(location)           -- PostGIS 공간 인덱스 (R-Tree 기반)
  - B-Tree(geohash)          -- Geohash prefix 검색
  - B-Tree(category_id)      -- 카테고리별 필터
  - GIN(name_local)          -- 다국어 이름 검색
```

#### POI 검색 아키텍처

```
[검색 요청: "강남역 근처 카페"]
                │
                ▼
  ┌─────────────────────────┐
  │      Query Parser       │
  │  "강남역" → 위치 해석     │
  │  "카페" → 카테고리 필터    │
  └───────────┬─────────────┘
              │
    ┌─────────┼──────────┐
    ▼         ▼          ▼
[Geocoding] [POI검색]  [자동완성]
 주소→좌표   공간+텍스트   Prefix
             복합 쿼리    매칭

[OpenSearch/Elasticsearch 공간 쿼리]

  POST /poi/_search
  {
    "query": {
      "bool": {
        "must": [
          { "match": { "name": "카페" } }
        ],
        "filter": [
          {
            "geo_distance": {
              "distance": "500m",
              "location": { "lat": 37.498, "lon": 127.027 }
            }
          },
          { "term": { "category": "cafe" } }
        ]
      }
    },
    "sort": [
      {
        "_geo_distance": {
          "location": { "lat": 37.498, "lon": 127.027 },
          "order": "asc"
        }
      }
    ]
  }
```

### 4. 지도 타일링 (Map Tiling)

```
[타일이란?]
  지도를 256x256 또는 512x512 픽셀 이미지 조각으로 분할한 것
  클라이언트가 화면에 보이는 영역의 타일만 요청 → 효율적

[Zoom Level과 타일 수]

  Zoom 0:  전 세계 = 1 타일           (1x1)
  Zoom 1:  전 세계 = 4 타일           (2x2)
  Zoom 2:  전 세계 = 16 타일          (4x4)
  ...
  Zoom 10: 전 세계 = 1,048,576 타일   (도시 수준)
  Zoom 15: 전 세계 = ~10억 타일        (건물 수준)
  Zoom 18: 전 세계 = ~690억 타일       (상세 도로)

  총 타일 수 = 4^zoom

[타일 좌표 체계 — Slippy Map / TMS]

  URL 패턴: /{z}/{x}/{y}.png
  예: /15/27741/12661.png  ← 서울시청 부근 zoom 15 타일

[벡터 타일 vs 래스터 타일]

  ┌──────────────┬──────────────────┬──────────────────┐
  │              │ 래스터 타일 (PNG)  │ 벡터 타일 (PBF)   │
  ├──────────────┼──────────────────┼──────────────────┤
  │ 형태         │ 이미지 파일        │ 구조화된 데이터    │
  │ 렌더링       │ 서버에서 렌더링    │ 클라이언트 렌더링  │
  │ 스타일 변경   │ 서버 재렌더링 필요 │ 클라이언트에서 즉시 │
  │ 회전/기울기   │ 깨짐             │ 자유자재           │
  │ 용량         │ 큼 (~20KB/타일)  │ 작음 (~5KB/타일)  │
  │ 다크 모드     │ 별도 타일 세트    │ 스타일만 변경      │
  │ 대표 사용     │ 네이버 지도(일부) │ Mapbox, Google   │
  └──────────────┴──────────────────┴──────────────────┘

  현재 트렌드: 벡터 타일 (Mapbox Vector Tile, MVT 규격)
  - Mapbox GL JS, MapLibre GL JS가 표준
  - 프로토콜 버퍼(Protobuf) 기반 인코딩
```

#### 타일 서빙 아키텍처

```
[타일 요청 흐름]

  Client → CDN(CloudFront/Akamai)
              │
              ├─ Cache HIT → 즉시 반환 (대부분의 요청)
              │
              └─ Cache MISS → Tile Server
                                 │
                    ┌────────────┼───────────────┐
                    ▼            ▼               ▼
               [Redis Cache]  [Pre-rendered]  [Dynamic Render]
               핫 타일 캐시    사전 생성 타일   실시간 렌더링
                                              (저 zoom만)

  캐시 전략:
  - Zoom 0~12: 사전 생성 + CDN 장기 캐시 (변경 드묾)
  - Zoom 13~15: 사전 생성 + 짧은 TTL (POI 변경 반영)
  - Zoom 16~18: 온디맨드 렌더링 + 캐시 (요청 적음)

  CDN 히트율: 보통 95%+ (지도 특성상 인기 지역 집중)
```

### 5. Geocoding / Reverse Geocoding

```
[Geocoding]
  주소 → 좌표
  "서울시 강남구 역삼동 123" → (37.5012, 127.0396)

[Reverse Geocoding]
  좌표 → 주소
  (37.5012, 127.0396) → "서울시 강남구 역삼동 123"

[구현 핵심]

  1. 주소 파싱 (Address Parsing)
     "서울시 강남구 역삼동 123-45"
     → {country: "KR", city: "서울", district: "강남구",
        neighborhood: "역삼동", number: "123-45"}

     글로벌 난이도: 각 나라마다 주소 체계가 다름
     - 한국: 도로명 + 지번 이중 체계
     - 일본: 블록 기반 (정·목 체계)
     - 사우디: 도로명 체계 도입 중 (기존에는 랜드마크 기반)
     - 중국: 성/시/구/가/호 계층 구조

  2. 매칭 알고리즘
     - Prefix 매칭 + Fuzzy 매칭 (오타 허용)
     - 동의어 사전: "강남역" = "강남역 사거리" = "Gangnam Station"
     - N-gram 인덱싱으로 부분 문자열 검색

  3. Reverse Geocoding — Point-in-Polygon 문제
     좌표가 어떤 행정구역(다각형)에 속하는지 판단
     → Ray Casting 알고리즘
     → 또는 S2/H3 셀 매핑으로 전처리
```

### 6. 경로 탐색 (Routing)

```
[핵심 알고리즘]

  1. Dijkstra — 기본
     - 모든 간선 가중치 ≥ 0일 때 최단 경로
     - 지도에서는 너무 느림 (수백만 노드)

  2. A* — Dijkstra + 휴리스틱
     - 목적지 방향으로 우선 탐색
     - 직선 거리를 휴리스틱으로 사용
     - 도시 내 경로에는 충분

  3. Contraction Hierarchies (CH) — 실무 표준
     - 전처리로 "중요한 노드(고속도로 IC 등)"를 미리 계산
     - 쿼리 시 양방향 탐색 → 밀리초 단위 응답
     - Google Maps, OSRM, Valhalla 등이 사용

  4. ALT (A* + Landmarks + Triangle inequality)
     - 랜드마크 기반 하한 추정
     - CH보다 전처리 가벼움, 동적 가중치 변경 가능

[도로 네트워크 그래프]

  Node = 교차로 (lat, lon)
  Edge = 도로 구간
  Weight = 거리, 시간, 교통량

  전 세계 도로: ~5억 노드, ~10억 엣지 (OSM 기준)
  대한민국: ~3000만 노드

  저장: 인접 리스트 (Adjacency List)
  메모리: 압축 표현 (CSR: Compressed Sparse Row)
```

---

## 헷갈렸던 포인트

### Q1: PostGIS vs OpenSearch(Elasticsearch) — 공간 검색은 뭘 써야 하나?

```
[PostGIS (PostgreSQL 확장)]
  - 정확한 공간 연산 (교집합, 버퍼, 면적 계산)
  - 트랜잭션 보장 (POI 생성/수정/삭제)
  - ST_DWithin, ST_Distance 등 표준 SQL 공간 함수
  - 데이터 정합성이 중요한 CRUD에 적합

[OpenSearch/Elasticsearch]
  - 텍스트 검색 + 공간 검색 복합 쿼리
  - geo_distance, geo_bounding_box, geo_shape 필터
  - 대규모 읽기/검색에 최적화
  - 자동완성, 형태소 분석 등 텍스트 기능

[실무 패턴: 둘 다 쓴다]
  PostgreSQL/PostGIS
    ↓ (변경 이벤트)
  CDC / 배치 동기화
    ↓
  OpenSearch (검색 인덱스)

  쓰기/정합성 → PostGIS
  읽기/검색 → OpenSearch
```

### Q2: Redis GEO vs PostGIS — 실시간 근접 검색은?

```
[Redis GEO]
  내부적으로 Geohash + Sorted Set 사용

  GEOADD stores 126.978 37.566 "store:1"
  GEOADD stores 127.027 37.498 "store:2"
  GEORADIUS stores 127.0 37.5 5 km COUNT 10 ASC

  장점: 밀리초 이내 응답, 인메모리
  단점: 정교한 공간 연산 불가, 데이터 영속성 제한
  용도: 실시간 위치 기반 ("근처 택시", "근처 배달원")

[PostGIS]
  장점: 복잡한 공간 연산, 폴리곤 교집합, 정확한 거리
  단점: 수~수십 ms 응답
  용도: POI 관리, 행정구역 판단, 정밀 지오코딩
```

### Q3: 사우디 지도 서비스의 특수 과제는?

```
[사우디/중동 지역 특수성]

  1. 주소 체계 미성숙
     - 최근까지 공식 도로명 없이 랜드마크 기반 안내
     - National Address System (عنوان) 도입 중
     - 건물 번호, 우편번호 체계 정비 진행 중
     → Geocoding 정확도가 낮음, 대체 검색 전략 필요

  2. 아랍어 처리
     - RTL(Right-to-Left) 텍스트 렌더링
     - 아랍어 형태소 분석 (어근 + 접두사/접미사 분리)
     - 로마자 음역 (Transliteration): "الرياض" ↔ "Riyadh"
     - 구어체 vs 표준 아랍어 동의어 처리

  3. 지도 데이터 품질
     - OSM 데이터 밀도가 한국/일본 대비 낮음
     - 현지 파트너 데이터, 위성 이미지 AI 보정 필요
     - 사막 지역: 도로가 모래에 묻히거나 경로 변경

  4. 기후/환경
     - 극한 더위(50°C+)로 야외 POI 영업시간 변동
     - 라마단 기간 영업시간 대폭 변경
     → 영업시간 규칙 엔진 복잡도 증가

  5. 규제
     - 특정 시설 위치 공개 제한 (군사/왕실)
     - 데이터 현지화(Data Localization) 규제
     → 사우디 내 데이터센터 필수
```

### Q4: "네이버 서비스 연동"이란 — 지도에서 어떤 서비스를 연동하나?

```
[네이버 지도/플레이스 서비스 연동 구조]

  ┌──────────┐    ┌──────────┐    ┌──────────┐
  │ 네이버 지도 │←→│ 네이버 검색 │←→│ 네이버 페이 │
  │ (지도/POI) │    │ (텍스트/AI)│    │ (결제/예약) │
  └─────┬────┘    └──────────┘    └──────────┘
        │
  ┌─────┼────────┬──────────────┐
  ▼     ▼        ▼              ▼
[예약]  [주문]   [리뷰]         [쿠폰]
네이버   배달/    네이버 플레이스   멤버십
예약    포장 주문  리뷰 시스템     적립

  글로벌화 = 이 서비스들을 현지 시스템과 연동
  - 현지 결제 시스템 (STC Pay, mada 등)
  - 현지 배달 서비스 연동
  - 현지 리뷰/평점 데이터 통합
```

---

## 참고 자료

### 핵심 오픈소스 프로젝트

| 프로젝트 | 설명 |
|---------|------|
| [PostGIS](https://postgis.net/) | PostgreSQL 공간 확장. R-Tree(GiST) 인덱스 기반 공간 쿼리 |
| [H3 (Uber)](https://github.com/uber/h3) | 정육각형 계층적 공간 인덱싱 시스템 |
| [S2 Geometry](https://github.com/google/s2geometry) | Google의 구면 기하학 라이브러리 |
| [OpenStreetMap](https://www.openstreetmap.org/) | 세계 최대 오픈 지도 데이터 |
| [OSRM](https://github.com/Project-OSRM/osrm-backend) | 오픈소스 경로 탐색 엔진. Contraction Hierarchies 사용 |
| [Valhalla](https://github.com/valhalla/valhalla) | Mapbox 경로 탐색 엔진. 다중 모달(도보/차량/대중교통) |
| [Mapbox GL JS](https://github.com/mapbox/mapbox-gl-js) | 벡터 타일 기반 WebGL 지도 렌더링 |
| [MapLibre GL JS](https://github.com/maplibre/maplibre-gl-js) | Mapbox GL JS의 오픈소스 포크. 무료 사용 가능 |
| [Nominatim](https://github.com/osm-search/Nominatim) | OSM 기반 Geocoding/Reverse Geocoding 엔진 |
| [Pelias](https://github.com/pelias/pelias) | 오픈소스 Geocoding 엔진. Elasticsearch 기반 |
| [Tippecanoe](https://github.com/felt/tippecanoe) | 대규모 GeoJSON → 벡터 타일 변환 도구 |
| [Martin](https://github.com/maplibre/martin) | PostGIS → 벡터 타일 서빙 서버 (Rust) |
