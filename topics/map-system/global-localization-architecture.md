---
title: "글로벌 로컬라이징 아키텍처 — i18n, L10n, 다국어/다지역 서비스 설계"
parent: Map System / 지도 시스템
nav_order: 2
---

# 글로벌 로컬라이징 아키텍처 — i18n, L10n, 다국어/다지역 서비스 설계

## 핵심 정리

### i18n vs L10n — 용어 정리

```
[i18n = Internationalization (국제화)]
  "i" + 18글자 + "n"
  소프트웨어가 여러 언어/지역을 지원할 수 있도록 설계하는 것
  = 코드에서 하드코딩된 문자열/날짜/통화를 분리하는 구조적 작업
  → 개발자가 한다

[L10n = Localization (현지화)]
  "L" + 10글자 + "n"
  특정 지역에 맞게 번역, 날짜 형식, 통화, 문화적 요소를 적용하는 것
  → 번역가 + PM + 현지 팀이 한다

[g11n = Globalization (세계화)]
  i18n + L10n = g11n
  전체 프로세스를 아우르는 용어
```

### 1. 백엔드 다국어 아키텍처

#### Locale 체계

```
[Locale = 언어 + 지역 + (선택) 문자 체계]

  형식: {language}-{region}
  예시:
  - ko-KR: 한국어 (대한민국)
  - en-US: 영어 (미국)
  - ar-SA: 아랍어 (사우디아라비아)
  - zh-CN: 중국어 간체 (중국)
  - vi-VN: 베트남어 (베트남)

  BCP 47 표준 (RFC 5646):
  - 언어: ISO 639-1 (2글자) — ko, en, ar, zh, vi
  - 지역: ISO 3166-1 alpha-2 — KR, US, SA, CN, VN
  - 문자: ISO 15924 — Latn, Arab, Hans, Hant

  같은 언어, 다른 지역:
  - en-US: "color", "apartment", "01/15/2026"
  - en-GB: "colour", "flat", "15/01/2026"
  - zh-CN: 简体中文 (간체)
  - zh-TW: 繁體中文 (번체)
```

#### API Locale 전달 방식

```
[방법 1: Accept-Language 헤더 (표준)]

  GET /api/places/12345
  Accept-Language: ko-KR, ko;q=0.9, en;q=0.5

  → 서버가 우선순위(q값) 따라 매칭
  → 지원하는 Locale 없으면 Fallback(기본 en)

[방법 2: URL Path]

  /ko/api/places/12345
  /en/api/places/12345
  /ar/api/places/12345

  → CDN 캐싱에 유리 (URL별 캐시)
  → SEO에 유리

[방법 3: Query Parameter]

  /api/places/12345?locale=ko-KR

  → 간단하지만 모든 API에 파라미터 필요

[실무 조합]
  - 웹 프론트: URL Path (/ko/...) + Accept-Language Fallback
  - 모바일 앱: Accept-Language 헤더
  - 내부 API: X-Locale 커스텀 헤더
```

#### 다국어 데이터 저장 패턴

```
[패턴 1: JSONB 컬럼 — 단순하고 유연]

  CREATE TABLE places (
    id BIGINT PRIMARY KEY,
    name JSONB,        -- {"ko": "경복궁", "en": "Gyeongbokgung", "ar": "قصر كيونغبوك"}
    description JSONB, -- {"ko": "조선의 법궁...", "en": "Main royal palace..."}
    address JSONB      -- {"ko": {...}, "en": {...}}
  );

  장점: 스키마 유연, 새 언어 추가 쉬움
  단점: 언어별 인덱싱 복잡, 번역 누락 감지 어려움

[패턴 2: 번역 테이블 분리 — 정규화]

  CREATE TABLE places (
    id BIGINT PRIMARY KEY,
    category_id INT,
    location GEOGRAPHY
  );

  CREATE TABLE place_translations (
    place_id BIGINT REFERENCES places(id),
    locale VARCHAR(10),   -- "ko-KR", "en-US", "ar-SA"
    name VARCHAR(200),
    description TEXT,
    address TEXT,
    PRIMARY KEY (place_id, locale)
  );

  장점: 정규화, 번역 상태 관리 용이, 언어별 인덱싱 가능
  단점: JOIN 필요, 쿼리 복잡도 증가

[패턴 3: 하이브리드 — 실무에서 가장 많이 사용]

  places 테이블: 기본 Locale 데이터 직접 저장 (빠른 조회)
  place_translations: 추가 Locale 번역 저장

  SELECT
    p.id,
    COALESCE(t.name, p.name_default) as name,
    COALESCE(t.description, p.description_default) as description
  FROM places p
  LEFT JOIN place_translations t
    ON t.place_id = p.id AND t.locale = 'ar-SA';

  → 기본 언어는 JOIN 없이 조회
  → 번역된 언어는 번역 테이블에서 가져옴
  → 번역 없으면 기본 언어로 Fallback
```

### 2. 검색에서의 다국어 처리

```
[핵심 과제: "같은 장소"를 여러 언어로 검색]

  "경복궁" (한국어)
  "Gyeongbokgung" (영어)
  "قصر كيونغبوك" (아랍어)
  → 모두 같은 POI를 반환해야 함

[OpenSearch/Elasticsearch 다국어 인덱싱]

  {
    "mappings": {
      "properties": {
        "name_ko": {
          "type": "text",
          "analyzer": "nori"          // 한국어 형태소 분석
        },
        "name_en": {
          "type": "text",
          "analyzer": "english"       // 영어 스테밍
        },
        "name_ar": {
          "type": "text",
          "analyzer": "arabic"        // 아랍어 어근 분석
        },
        "name_vi": {
          "type": "text",
          "analyzer": "vietnamese"    // 베트남어 (ICU)
        },
        "name_all": {
          "type": "text",             // 모든 언어 통합 필드
          "analyzer": "icu_analyzer"  // ICU 유니코드 분석
        }
      }
    }
  }

[언어별 분석기(Analyzer) 특성]

  한국어 (nori):
    "서울특별시" → "서울", "특별", "시"
    복합어 분해, 조사 제거

  아랍어 (arabic):
    "المطاعم" (식당들) → "مطعم" (식당, 어근)
    관사(ال) 제거, 어근 추출

  중국어 (ik/smartcn):
    "北京大学" → "北京", "大学"
    띄어쓰기 없는 언어, 사전 기반 분절

  베트남어:
    "Thành phố Hồ Chí Minh" → "Thành phố", "Hồ Chí Minh"
    음절 기반 + 복합어 인식 필요
```

### 3. 날짜/시간/통화 로컬라이징

```
[날짜 형식 — 같은 날짜, 다른 표현]

  2026-03-06:
  - ko-KR: 2026년 3월 6일 (금)
  - en-US: March 6, 2026
  - ar-SA: 6 مارس 2026 (히즈라력: 1447/9/6)
  - zh-CN: 2026年3月6日
  - vi-VN: 06/03/2026 (일/월/년 — 유럽식)

  주의: 사우디는 히즈라력(이슬람력) 병행 사용!
  → 양력 + 히즈라력 변환 로직 필요

[시간대 — 글로벌 서비스 필수]

  서버: UTC로 저장 (절대 로컬 시간 저장 금지!)
  클라이언트: 사용자 타임존으로 변환

  한국:    UTC+9  (KST, 서머타임 없음)
  사우디:  UTC+3  (AST, 서머타임 없음)
  중국:    UTC+8  (CST, 단일 타임존)
  베트남:  UTC+7  (ICT)

  영업시간 저장 주의:
  "09:00~22:00 Asia/Seoul" ← IANA 타임존 + 로컬 시간
  금요일 영업: 사우디에서는 금요일이 주말(과거, 현재는 토·일)

[통화]

  한국:    KRW (₩) — 소수점 없음 (1원 단위)
  사우디:  SAR (ر.س) — 소수점 2자리 (1.00 리얄)
  중국:    CNY (¥) — 소수점 2자리
  베트남:  VND (₫) — 소수점 없음 (큰 단위 사용)

  서버에서 금액 저장:
  - 최소 단위 정수로 저장 (1원, 1할랄라, 1펜)
  - KRW 10000 → 10000
  - SAR 10.50 → 1050 (할랄라 단위)
  - 절대 float/double 금지 → BigDecimal 또는 Long
```

### 4. RTL (Right-to-Left) 지원

```
[아랍어/히브리어 = 오른쪽에서 왼쪽으로 읽는 언어]

  LTR: Hello World  →→→
  RTL: مرحبا بالعالم  ←←←

[백엔드에서 신경 쓸 것]

  1. API 응답에 텍스트 방향 메타데이터 포함
     {
       "locale": "ar-SA",
       "direction": "rtl",
       "name": "مطعم الشرق"
     }

  2. 주소 표시 순서
     LTR: 서울시 강남구 역삼동 123
     RTL: 123 ,حي العليا ,الرياض  (번지→동→시)

  3. 지도 위 텍스트 렌더링
     - 아랍어 POI 이름이 지도 위에 올바른 방향으로 표시되어야 함
     - 숫자는 LTR 유지 (아라비아 숫자 → 아이러니하게 좌→우)
     - 양방향 텍스트(BiDi): "Starbucks الرياض" → 혼합 방향

  4. 검색 결과 정렬
     - 아랍어 자모 순서: ا ب ت ث ج ح خ د ذ ر ز ...
     - 한국어: 가나다 순서
     - Collation 설정이 Locale마다 다름
```

### 5. 글로벌 로컬라이징 Layer 아키텍처 (네이버 지도 기준)

```
[기존 네이버 지도 = 한국 전용 모놀리식]

  → 글로벌 전환 아키텍처

  ┌──────────────────────────────────────────────────┐
  │              Global API Gateway                   │
  │   Locale 감지, 라우팅, Rate Limiting               │
  └──────────────┬───────────────────────────────────┘
                 │
  ┌──────────────▼───────────────────────────────────┐
  │           Localization Layer (L10n Layer)          │
  │                                                   │
  │  ┌─────────────┐  ┌──────────┐  ┌─────────────┐ │
  │  │ Translation  │  │ Format   │  │ Region      │ │
  │  │ Service      │  │ Service  │  │ Config      │ │
  │  │ 번역 관리     │  │ 날짜/통화 │  │ 지역별 설정  │ │
  │  └─────────────┘  └──────────┘  └─────────────┘ │
  └──────────────┬───────────────────────────────────┘
                 │
  ┌──────────────▼───────────────────────────────────┐
  │           Core Domain Services (공용)              │
  │   POI, 예약, 주문, 리뷰, 검색, 경로                 │
  │   → Locale-agnostic 핵심 로직                     │
  └──────────────┬───────────────────────────────────┘
                 │
  ┌──────────────▼───────────────────────────────────┐
  │           Data Layer                              │
  │   PostgreSQL/PostGIS, OpenSearch, Redis, Kafka     │
  │   글로벌 데이터 + 지역 데이터 분리                    │
  └──────────────────────────────────────────────────┘

  핵심 원칙:
  1. Core 서비스는 Locale을 모름 (비즈니스 로직 공용)
  2. L10n Layer가 입출력을 변환
  3. 지역별 차이(결제, 규제)만 Region Config로 분기
```

---

## 헷갈렸던 포인트

### Q1: 번역 관리 — 개발자가 직접 JSON 파일 관리하면 안 되나?

```
[소규모]
  messages_ko.json, messages_en.json 파일 관리 → 가능

[글로벌 서비스 현실]
  - 5개 언어 × 10,000개 문자열 = 50,000개 번역 항목
  - 번역가가 직접 JSON 편집? → 실수, 포맷 깨짐
  - 번역 진행률 추적? → 파일로는 불가능
  - 컨텍스트(스크린샷, 설명) 전달? → 별도 문서 필요

[실무: TMS(Translation Management System) 사용]
  - Crowdin, Phrase(Memsource), Transifex, Lokalise
  - 번역가 웹 UI에서 작업
  - 개발자는 키만 추가, 번역은 TMS에서 관리
  - CI/CD 연동: 번역 완료 → 자동 빌드/배포

  개발자 워크플로우:
  1. 코드에 키 추가: t("place.review_count", count=42)
  2. 키가 TMS에 자동 등록
  3. 번역가가 TMS에서 번역
  4. 빌드 시 TMS에서 번역 파일 다운로드
```

### Q2: 서버 사이드 렌더링 vs 클라이언트 사이드 — 다국어는 어디서?

```
[지도 서비스에서의 다국어 렌더링]

  서버 사이드 (API 응답 시 변환):
  - POI 이름, 설명, 주소 → 서버에서 Locale별 데이터 반환
  - 검색 결과 → 서버에서 해당 Locale 분석기로 검색

  클라이언트 사이드 (프론트에서 변환):
  - UI 라벨 ("검색", "경로 찾기" 등) → 번들에 포함
  - 날짜/시간 포맷 → Intl API 사용
  - 지도 위 라벨 → 벡터 타일의 다국어 속성에서 선택

  → 데이터는 서버, UI는 클라이언트가 일반적 분업
```

### Q3: Fallback 전략 — 번역이 없으면?

```
[Fallback Chain 예시]

  요청: ar-SA (사우디 아랍어)

  1차: ar-SA 번역 있음? → 반환
  2차: ar 번역 있음? → 반환 (지역 무관 아랍어)
  3차: en 번역 있음? → 반환 (글로벌 기본 언어)
  4차: 원본 데이터 반환 (최후 수단)

  POI 이름 특수 처리:
  - "스타벅스 강남역점" → ar-SA 번역 없음
  - "Starbucks Gangnam Station" → en Fallback
  - 고유명사는 음역(Transliteration) 제공: "ستاربكس كانغنام"
```

---

## 참고 자료

| 자료 | 설명 |
|------|------|
| [ICU (International Components for Unicode)](https://icu.unicode.org/) | 유니코드/로컬라이제이션 표준 라이브러리 |
| [CLDR (Unicode Common Locale Data Repository)](https://cldr.unicode.org/) | 전 세계 Locale 데이터 표준 |
| [BCP 47 (RFC 5646)](https://www.rfc-editor.org/rfc/rfc5646) | 언어 태그 표준 |
| [Spring MessageSource](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-messagesource) | Spring i18n 메시지 처리 |
| [OpenSearch Language Analyzers](https://opensearch.org/docs/latest/analyzers/) | 언어별 텍스트 분석기 |
| [W3C i18n Best Practices](https://www.w3.org/International/) | 웹 국제화 표준 가이드 |
