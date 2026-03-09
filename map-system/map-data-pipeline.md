# 대규모 지도 데이터 파이프라인 — 실시간/배치 처리, ETL, 데이터 모델링

## 핵심 정리

### 지도 데이터의 특수성

```
[일반 웹 서비스 데이터 vs 지도 데이터]

  일반 서비스:
  - 사용자 생성 데이터 (게시글, 댓글)
  - 구조화된 스키마
  - 단일 소스

  지도 데이터:
  - 수십 개 외부 소스 통합 (정부, 파트너, 크롤링, 사용자 제보)
  - 공간 데이터 + 속성 데이터 + 시계열 데이터 혼합
  - 데이터 품질이 소스마다 다름
  - 전 세계 데이터 = 수십 TB ~ PB 규모
  - 실시간 변화 (교통, 영업시간) + 느린 변화 (도로, 건물)
```

### 1. 지도 데이터 소스 유형

```
[글로벌 데이터 소스]

  ┌──────────────────────────────────────────────────┐
  │               External Data Sources               │
  ├──────────────┬──────────────┬────────────────────┤
  │ 공공 데이터    │ 파트너 데이터  │ 자체 수집 데이터    │
  ├──────────────┼──────────────┼────────────────────┤
  │ OpenStreetMap │ 현지 통신사   │ 사용자 제보/리뷰    │
  │ 정부 지적 데이터│ 결제사 POI   │ 크롤링 (웹/앱)     │
  │ 위성 이미지    │ 프랜차이즈 DB │ GPS 궤적 수집      │
  │ 기상 데이터    │ 부동산 DB    │ 스트리트뷰 촬영     │
  │ 교통 실시간    │ 배달 플랫폼   │ AI 객체 인식       │
  └──────────────┴──────────────┴────────────────────┘

  데이터 규모 감각:
  - 전 세계 도로 네트워크: ~5억 노드, ~10억 엣지
  - 전 세계 POI: ~5억 개 (Google Maps 기준)
  - 한국 POI: ~2000만 개
  - OSM 전체 데이터: ~2TB (PBF 압축)
  - 하루 GPS 궤적: 수십억 포인트 (대형 서비스 기준)
```

### 2. 배치 파이프라인

```
[배치 = 대량의 데이터를 주기적으로 처리]

  ┌────────┐    ┌─────────┐    ┌──────────┐    ┌─────────┐
  │ Ingest │ → │ Process │ → │ Validate │ → │ Publish │
  │ 수집    │    │ 변환     │    │ 검증      │    │ 배포     │
  └────────┘    └─────────┘    └──────────┘    └─────────┘

[1단계: 수집 (Ingest)]

  방법:
  - API Polling: 파트너 API를 주기적으로 호출
  - File Drop: SFTP/S3에 파일 업로드 (CSV, GeoJSON, Shapefile)
  - Web Crawling: 현지 업체 정보 수집 (합법적 범위)
  - DB Replication: CDC(Change Data Capture)로 원본 DB 변경 감지

  도구:
  - Apache NiFi / Airbyte: 데이터 수집 오케스트레이션
  - AWS Glue / Spark: 대규모 ETL
  - Debezium: CDC (MySQL/PostgreSQL → Kafka)

[2단계: 변환 (Process/Transform)]

  ┌─────────────────────────────────────────┐
  │           ETL Pipeline (Spark)           │
  │                                         │
  │  1. 좌표 정규화                           │
  │     - 다양한 좌표계 → WGS84 (EPSG:4326)  │
  │     - 한국: KATEC/Bessel → WGS84 변환    │
  │     - 사우디: UTM Zone 37~39 → WGS84     │
  │                                         │
  │  2. 주소 정규화                           │
  │     - "서울 강남구" = "서울특별시 강남구"    │
  │     - 약어 전개, 오타 보정                 │
  │                                         │
  │  3. POI 중복 제거 (Deduplication)         │
  │     - Entity Resolution 문제              │
  │     - "스벅 강남점" = "스타벅스 강남역점"?  │
  │     - 이름 유사도 + 거리(50m 이내) + 카테고리│
  │     → ML 기반 매칭 스코어                  │
  │                                         │
  │  4. 카테고리 매핑                          │
  │     - 소스A: "한식" → 통합: "음식점 > 한식" │
  │     - 소스B: "Korean" → 통합: "음식점 > 한식"│
  │     - 표준 카테고리 택소노미로 통일           │
  │                                         │
  │  5. 품질 스코어링                          │
  │     - 데이터 완성도 (이름, 주소, 전화 등)    │
  │     - 소스 신뢰도 (공공 > 파트너 > 크롤링)   │
  │     - 최근성 (업데이트 시점)                │
  │     → quality_score: 0.0 ~ 1.0           │
  └─────────────────────────────────────────┘

[3단계: 검증 (Validate)]

  자동 검증:
  - 좌표 범위 검증 (한국: 위도 33~38, 경도 124~132)
  - 필수 필드 존재 확인
  - 중복 키 검출
  - 이전 배치와 비교: 급격한 변화 감지 (Anomaly Detection)
    → POI 10% 이상 삭제되면 Alert → 수동 검토

  수동 검증:
  - QA 팀 샘플링 검사
  - 지도 위 시각화 검토 (이상한 위치의 POI 확인)

[4단계: 배포 (Publish)]

  Blue-Green 배포:
  - DB에 새 데이터 적재 → 스냅샷 비교 → 스왑
  - 문제 시 즉시 롤백 (이전 버전으로 스왑)

  인덱스 재구축:
  - OpenSearch 인덱스 재생성 (Alias Swap)
  - 타일 캐시 무효화 (변경된 영역만)
  - CDN Purge (변경된 타일 URL만)
```

### 3. 실시간 파이프라인

```
[실시간 = 초~분 단위로 반영되어야 하는 데이터]

  - 실시간 교통 정보
  - POI 영업 상태 변경 (임시 휴업, 긴급 폐점)
  - 사용자 리뷰/평점 업데이트
  - GPS 궤적 기반 도로 상태

[아키텍처: Kafka 중심 이벤트 스트리밍]

  ┌──────────┐    ┌────────┐    ┌──────────────┐
  │ Producer │ → │ Kafka  │ → │ Stream       │
  │          │    │ Topics │    │ Processor    │
  └──────────┘    └────────┘    └──────┬───────┘
                                       │
                         ┌─────────────┼──────────────┐
                         ▼             ▼              ▼
                   [PostgreSQL]  [OpenSearch]     [Redis]
                   POI 업데이트   검색 인덱스       실시간 캐시
                                업데이트          (교통 상태)

  Kafka Topics 설계:

  poi.updates          — POI 생성/수정/삭제 이벤트
  poi.reviews          — 리뷰/평점 이벤트
  traffic.realtime     — 실시간 교통 데이터
  user.location        — GPS 궤적 (익명화)
  map.tile.invalidate  — 타일 캐시 무효화 신호

[Stream Processing: Kafka Streams / Flink]

  예: 실시간 교통 정보 처리

  GPS 궤적 수신 (초당 수만 건)
    → 도로 링크에 매핑 (Map Matching)
    → 링크별 평균 속도 계산 (Sliding Window: 5분)
    → 속도 기준 혼잡도 분류 (원활/서행/정체)
    → Redis 업데이트 (TTL: 5분)
    → 타일 서버에 실시간 교통 레이어 반영

  Flink Window 예시:
  - Tumbling Window (5분): 5분마다 집계
  - Sliding Window (5분, 1분 슬라이드): 1분마다 최근 5분 집계
  - Session Window: 사용자별 이동 세션 감지
```

### 4. 데이터 모델링

```
[지도 서비스 핵심 도메인 모델]

  ┌─────────────────────────────────────────┐
  │                Places                    │
  │  (POI의 통합 뷰 — Master Record)         │
  │                                         │
  │  id, canonical_name, location,           │
  │  category, quality_score,                │
  │  primary_source, merged_from[]           │
  └───┬──────────┬──────────┬───────────────┘
      │          │          │
      ▼          ▼          ▼
  ┌────────┐ ┌────────┐ ┌──────────────┐
  │ Trans- │ │Reviews │ │ Operating    │
  │ lations│ │        │ │ Hours        │
  │ 번역    │ │ 리뷰    │ │ 영업시간 규칙  │
  └────────┘ └────────┘ └──────────────┘

  ┌─────────────────────────────────────────┐
  │           Raw Sources                    │
  │  (원본 소스별 데이터 — 변환 전)            │
  │                                         │
  │  source_id, source_name, raw_data,       │
  │  fetched_at, matched_place_id            │
  └─────────────────────────────────────────┘

  핵심 원칙:
  1. 원본(Raw)과 가공(Master) 분리
     → Raw는 감사(Audit) 및 재처리용
     → Master는 서빙용
  2. 하나의 Place에 여러 Source가 매핑 (N:1)
  3. 소스 간 충돌 시 quality_score가 높은 쪽 우선
```

#### 영업시간 모델링 — 의외로 복잡한 도메인

```
[왜 복잡한가?]

  "월~금 09:00~18:00, 토 10:00~14:00, 일 휴무"
  → 단순해 보이지만...

  - 공휴일 예외
  - 라마단 기간 특별 시간 (사우디)
  - 부정기 휴무 ("둘째 넷째 화요일 휴무")
  - 계절별 변경 ("여름: ~21:00, 겨울: ~18:00")
  - 브레이크 타임 ("11:30~14:00, 17:00~21:00")
  - 라스트 오더 ("폐점 30분 전")

[데이터 모델: OSM Opening Hours 규격 참고]

  {
    "regular": [
      {"days": ["MON","TUE","WED","THU","FRI"], "open": "09:00", "close": "18:00"},
      {"days": ["SAT"], "open": "10:00", "close": "14:00"}
    ],
    "breaks": [
      {"days": ["MON","TUE","WED","THU","FRI"], "open": "14:30", "close": "17:00"}
    ],
    "special": [
      {"date": "2026-01-01", "closed": true, "reason": "신정"},
      {"date_range": ["2026-03-12", "2026-04-10"], "open": "10:00", "close": "15:00",
       "reason": "Ramadan"}
    ],
    "timezone": "Asia/Riyadh"
  }

  → "지금 영업 중?" 판단 로직:
  1. special에 오늘 날짜 매칭 → 있으면 그 규칙 적용
  2. 없으면 regular에서 요일 매칭
  3. breaks 제외
  4. 타임존 변환하여 현재 시간과 비교
```

### 5. 배치 + 실시간 통합: Lambda / Kappa 아키텍처

```
[Lambda 아키텍처 — 배치 + 실시간 이중 경로]

                    ┌─────────────────────┐
                    │    Data Sources      │
                    └──────┬──────────────┘
                           │
              ┌────────────┼────────────┐
              ▼                         ▼
  ┌───────────────────┐    ┌──────────────────┐
  │  Batch Layer       │    │  Speed Layer      │
  │  (Spark/Hadoop)    │    │  (Flink/KStreams)  │
  │  정확하지만 느림     │    │  빠르지만 근사치    │
  │  T+1 ~ T+24h      │    │  실시간 (~초)       │
  └────────┬──────────┘    └────────┬─────────┘
           │                        │
           ▼                        ▼
  ┌───────────────────┐    ┌──────────────────┐
  │  Batch View        │    │  Realtime View    │
  │  (완전한 데이터)     │    │  (최신 변경분)      │
  └────────┬──────────┘    └────────┬─────────┘
           │                        │
           └──────────┬─────────────┘
                      ▼
              ┌──────────────┐
              │ Serving Layer │
              │ (병합하여 서빙) │
              └──────────────┘

  예: POI 데이터 서빙
  - Batch: 매일 새벽 전체 소스 통합 → 정확한 Master DB 갱신
  - Speed: 실시간 사용자 제보/리뷰 → 즉시 반영
  - Serving: 배치 결과 + 실시간 변경분 병합

[Kappa 아키텍처 — 실시간 단일 경로]

  모든 데이터를 스트리밍으로 처리
  배치 = 과거 데이터를 스트리밍으로 재처리(Replay)

  Kafka 로그 보존 + Flink Stateful Processing
  → 배치 레이어 제거, 운영 복잡도 감소
  → 단, 대규모 과거 데이터 재처리 시 비용 증가
```

### 6. 데이터 품질 관리 (Data Quality)

```
[지도 데이터 품질 = 서비스 신뢰의 핵심]

  품질 지표:
  ┌──────────────┬──────────────────────────────┐
  │ 지표          │ 설명                          │
  ├──────────────┼──────────────────────────────┤
  │ Completeness │ 필수 필드 채워짐 비율           │
  │ Accuracy     │ 실제 위치와 좌표 일치 정도       │
  │ Freshness    │ 마지막 업데이트 이후 경과 시간    │
  │ Consistency  │ 동일 POI의 소스 간 일관성        │
  │ Uniqueness   │ 중복 없음                      │
  │ Reachability │ 연락처(전화/URL) 유효성          │
  └──────────────┴──────────────────────────────┘

  자동 품질 체크:
  - 좌표가 바다/호수 위인 POI 자동 플래그
  - 같은 좌표에 100개+ POI → 데이터 오류 의심
  - 전화번호 형식 검증 (libphonenumber)
  - URL 접속 가능 여부 (배치 Health Check)
  - 폐업 감지: 6개월 이상 업데이트 없음 + 리뷰 없음
```

---

## 헷갈렸던 포인트

### Q1: CDC(Change Data Capture) — DB 동기화에 왜 CDC를 쓰나?

```
[기존 방식: 주기적 전체 덤프]
  매일 새벽 SELECT * FROM pois → ETL → 타겟 DB
  문제: 수천만 건 전체 복사 → 느림, 리소스 낭비

[CDC 방식: 변경분만 캡처]
  MySQL Binlog / PostgreSQL WAL → Debezium → Kafka
  → 변경된 레코드만 실시간 전달

  PostgreSQL → Debezium → Kafka → OpenSearch
  (원본 POI DB)            (이벤트)  (검색 인덱스)

  장점:
  - 실시간 동기화 (초 단위 지연)
  - DB 부하 최소화
  - 이벤트 기반 → 하류 시스템 독립적 확장 가능

  주의:
  - Debezium Connector 장애 시 데이터 유실 가능
    → Kafka offset 기반 재시작으로 복구
  - 스키마 변경 시 호환성 관리 필요
    → Schema Registry (Avro/Protobuf) 사용
```

### Q2: Map Matching이 뭔가? — GPS 궤적을 도로에 맞추기

```
[문제]
  GPS 정확도: ±5~15m (건물 사이, 터널, 고가도로)
  → 실제 도로 위가 아닌 좌표가 들어옴

[Map Matching = GPS 포인트를 가장 가까운 도로 링크에 매핑]

  Raw GPS:    * . . * . . * . . *
  도로:       ━━━━━━━━━━━━━━━━━━
  매칭 결과:   ● . . ● . . ● . . ●  (도로 위로 보정)

  알고리즘:
  - Hidden Markov Model (HMM) 기반
  - 각 GPS 포인트 → 후보 도로 링크들 선택
  - Viterbi 알고리즘으로 최적 경로 선택
  - 거리 + 방향 + 연결성을 종합 고려

  사용처:
  - 실시간 교통 속도 계산
  - 경로 이탈 감지 (네비게이션)
  - 택시 미터기 (정확한 주행 거리)
  - 도로 변경 감지 (새 도로/폐도로)

  오픈소스: Valhalla Meili, OSRM matching service
```

### Q3: 지도 데이터 파이프라인에서 Spark vs Flink 선택 기준은?

```
  ┌──────────────┬────────────────┬────────────────┐
  │              │ Apache Spark   │ Apache Flink   │
  ├──────────────┼────────────────┼────────────────┤
  │ 주 용도      │ 배치 + 마이크로배치│ 진짜 실시간 스트림│
  │ 지연 시간    │ 초~분           │ 밀리초~초        │
  │ 상태 관리    │ 제한적          │ 강력한 Stateful │
  │ 윈도우 처리  │ 기본적           │ 풍부 (Event Time)│
  │ 생태계      │ 광범위 (ML 포함) │ 스트리밍 특화    │
  │ 학습 곡선    │ 상대적 쉬움     │ 높음            │
  └──────────────┴────────────────┴────────────────┘

  지도 서비스 선택:
  - 배치 ETL (일/주간 데이터 통합): Spark
  - 실시간 교통/GPS: Flink
  - 실시간 POI 업데이트: Kafka Streams (가벼운 경우)
```

---

## 참고 자료

| 자료 | 설명 |
|------|------|
| [Debezium](https://debezium.io/) | 오픈소스 CDC 플랫폼 |
| [Apache Flink](https://flink.apache.org/) | 실시간 스트림 처리 엔진 |
| [Apache Spark](https://spark.apache.org/) | 대규모 배치/마이크로배치 처리 |
| [Valhalla Meili](https://github.com/valhalla/valhalla) | 오픈소스 Map Matching |
| [OpenStreetMap Data](https://planet.openstreetmap.org/) | OSM 전체 데이터 다운로드 |
| [Overture Maps Foundation](https://overturemaps.org/) | Linux Foundation의 개방형 지도 데이터 프로젝트 |
| [libphonenumber](https://github.com/google/libphonenumber) | Google의 전화번호 파싱/검증 라이브러리 |
