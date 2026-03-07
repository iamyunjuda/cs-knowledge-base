# Traffic Mirroring, Blue-Green, Canary 배포 — 검증과 무중단 배포 전략 총정리

## 핵심 정리

### 왜 이 전략이 필요한가?

대규모 시스템을 리팩토링할 때, 단위 테스트와 통합 테스트만으로는 운영 환경의 모든 케이스를 커버할 수 없다. 실제 트래픽 패턴, 데이터 분포, 타이밍 이슈 등은 테스트 환경에서 재현이 어렵기 때문이다.

이를 해결하기 위해 검증 → 배포 전략을 조합한다:

| 단계 | 전략 | 목적 |
|------|------|------|
| **검증** | Traffic Mirroring (Shadow Traffic) | 실제 트래픽으로 리팩토링 시스템을 "읽기 전용"으로 검증 |
| **배포** | Blue-Green 배포 | 두 환경을 준비해두고 한 번에 전환 |
| **배포** | Canary 배포 | 검증 완료 후 실제 트래픽을 점진적으로 전환 |

---

### Traffic Mirroring (Shadow Traffic) 상세

#### 동작 원리

```
사용자 요청
    │
    ▼
┌──────────┐
│  Proxy   │──── 원본 요청 ────▶ [기존 시스템] ──▶ 응답을 사용자에게 반환
│ (Envoy/  │
│  Nginx/  │──── 복제 요청 ────▶ [새 시스템]   ──▶ 응답 폐기 (비교 분석용)
│  Istio)  │
└──────────┘
```

- 프록시 계층에서 요청을 **복제(mirror/shadow)** 하여 새 시스템으로 전송
- **사용자에게는 항상 기존 시스템의 응답**만 반환 → 서비스 영향 zero
- 새 시스템의 응답은 수집·비교 목적으로만 사용

#### 구현 방식 (Istio 예시)

```yaml
apiVersion: networking.istio.io/v1alpha3
kind: VirtualService
metadata:
  name: my-service
spec:
  hosts:
    - my-service
  http:
    - route:
        - destination:
            host: my-service-v1  # 기존 시스템 (실제 응답)
      mirror:
        host: my-service-v2      # 새 시스템 (미러링 대상)
      mirrorPercentage:
        value: 100.0             # 100% 미러링
```

#### Nginx 기반 미러링

```nginx
location / {
    # 기존 시스템으로 프록시
    proxy_pass http://legacy-backend;

    # 미러링 설정
    mirror /mirror;
    mirror_request_body on;
}

location = /mirror {
    internal;
    proxy_pass http://new-backend$request_uri;
    proxy_set_header X-Mirrored "true";
}
```

#### 비교 분석 시스템 설계

미러링만 하면 의미가 없다. **응답을 비교하는 시스템**이 반드시 필요하다.

```
[기존 시스템 응답] ──┐
                     ├──▶ [Diff Comparator] ──▶ [대시보드/알림]
[새 시스템 응답]  ──┘

비교 항목:
├── 응답 Body (JSON diff)
├── HTTP Status Code
├── 응답 시간 (Latency P50/P95/P99)
├── 에러율
└── 특정 필드 값 일치율
```

실무에서는 Kafka 등의 메시지 큐로 양쪽 응답을 모아 비동기로 비교하는 구조가 일반적이다.

---

### Traffic Mirroring의 한계점

#### 1. 부작용(Side Effect)이 있는 요청은 미러링하면 위험하다

이것이 Traffic Mirroring의 **가장 치명적인 한계**다.

```
[문제 시나리오]

사용자: "결제 요청" (POST /payment)
    │
    ├──▶ [기존 시스템] → 실제 결제 처리 ✅
    │
    └──▶ [새 시스템]   → 결제가 또 처리됨 ❌ (이중 결제!)
```

**영향받는 요청 유형:**
- **결제/송금**: 이중 과금
- **알림 발송**: 이메일/SMS 중복 발송
- **외부 API 호출**: 제3자 시스템에 중복 요청
- **DB 쓰기**: 데이터 중복 생성, 재고 이중 차감
- **상태 변경**: 주문 상태, 사용자 상태 등의 비정상 전이

**대응 방안:**

```
방법 1: 읽기 요청만 미러링
━━━━━━━━━━━━━━━━━━━━━━━━
- GET 요청만 미러링, POST/PUT/DELETE는 제외
- 단점: 쓰기 로직의 검증이 불가능

방법 2: 새 시스템을 Dry-run 모드로 동작
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 새 시스템의 외부 연동(DB, 결제 API 등)을 Mock/Stub으로 대체
- 로직은 실행하되 실제 부작용은 발생시키지 않음
- 단점: Mock과 실제 환경의 차이로 검증 정확도 하락

방법 3: 별도 DB + 격리된 환경
━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 새 시스템이 별도의 격리된 DB를 사용
- 외부 API는 Sandbox 환경으로 연결
- 단점: 데이터 동기화 비용, 환경 구축 복잡도
```

#### 2. 미러링 트래픽으로 인한 리소스 부하

```
평소 트래픽:  1,000 RPS
미러링 시:    1,000 RPS (기존) + 1,000 RPS (미러) = 총 2,000 RPS

영향:
├── 네트워크 대역폭 2배
├── 새 시스템의 인프라 비용 추가
├── 프록시 계층의 부하 증가
└── 공유 자원(DB, 캐시 등) 경합 가능
```

미러링 비율을 조절하거나(`mirrorPercentage`), 새 시스템이 공유 자원을 사용하지 않도록 격리하는 것이 중요하다.

#### 3. 타이밍 차이로 인한 비교 불일치

```
[시간에 따라 결과가 달라지는 경우]

기존 시스템: 10:00:00.001에 처리 → 재고 5개
새 시스템:   10:00:00.050에 처리 → 재고 4개 (그 사이 다른 주문 발생)

→ 응답이 다르지만 버그가 아님 (False Positive)
```

이런 false positive가 쌓이면 실제 문제를 놓칠 수 있다. 비교 로직에서 시간 의존적 필드를 제외하거나, 허용 오차를 설정해야 한다.

#### 4. 비동기 처리의 검증 한계

```
요청 → [API 응답] → [비동기 이벤트 발행] → [다운스트림 처리]
         ↑                                       ↑
      비교 가능                             비교 어려움
```

API의 즉각 응답은 비교할 수 있지만, 이후 발생하는 비동기 이벤트(Kafka 메시지, 배치 처리 등)의 정합성 검증은 별도 체계가 필요하다.

---

### Traffic Mirroring 시 주의사항

#### 1. 멱등성(Idempotency) 보장 없이 미러링하면 안 된다

미러링 대상 시스템이 **멱등하지 않은 연산**을 수행한다면, 미러링 자체가 시스템을 오염시킨다.

```
[체크리스트]
□ 미러링 대상 요청이 순수한 읽기(Query)인가?
□ 쓰기 요청을 미러링한다면, 새 시스템이 Dry-run 모드인가?
□ 외부 시스템(결제, 알림)으로의 호출이 차단되어 있는가?
□ 미러링으로 인한 DB 쓰기가 격리된 환경에서 이루어지는가?
```

#### 2. 미러링 실패가 원본 요청에 영향을 주면 안 된다

```
[잘못된 구현]
요청 → 기존 시스템 호출 → 미러링 호출 → 응답 반환
                              ↑
                     미러 대상이 타임아웃나면
                     전체 응답이 지연됨 ❌

[올바른 구현]
요청 → 기존 시스템 호출 → 응답 반환 (즉시)
           │
           └──▶ (비동기) 미러링 호출 (fire-and-forget)
```

미러링은 반드시 **비동기(fire-and-forget)** 로 처리해야 한다. 미러 대상의 장애나 지연이 원본 서비스에 전파되어서는 안 된다.

#### 3. 미러링 트래픽 식별 헤더

새 시스템이 자신이 받는 요청이 미러링인지 구분할 수 있어야 한다.

```
X-Mirrored: true
X-Shadow-Request: true
X-Request-Source: mirror
```

이를 통해 새 시스템이 의도적으로 부작용을 억제하는 로직을 태울 수 있다.

---

### Blue-Green 배포 상세

#### 동작 원리

두 개의 동일한 운영 환경(Blue, Green)을 유지하면서 트래픽을 한 번에 전환하는 방식이다.

```
[배포 전]
                  ┌─────────────┐
사용자 ──────────▶│  Blue (v1)  │  ← 현재 운영 중
                  └─────────────┘
                  ┌─────────────┐
                  │ Green (v2)  │  ← 대기 (새 버전 배포 완료)
                  └─────────────┘

[전환]
                  ┌─────────────┐
                  │  Blue (v1)  │  ← 대기 (롤백용으로 유지)
                  └─────────────┘
                  ┌─────────────┐
사용자 ──────────▶│ Green (v2)  │  ← 트래픽 전환 완료
                  └─────────────┘

전환 방식: DNS 변경, 로드밸런서 타겟 그룹 교체, 라우터 설정 변경
```

핵심은 **새 버전을 완전히 배포하고 검증한 뒤에** 트래픽을 한 번에 전환하는 것이다. 이전 환경은 롤백용으로 유지한다.

#### Blue-Green 검증 방법

Blue-Green에서는 전환 **전에** Green 환경을 검증해야 한다. 실제 사용자에게 노출되기 전이므로 검증 방법이 다르다.

```
[Blue-Green 검증 파이프라인]

Step 1: Green 환경에 새 버전 배포
         │
         ▼
Step 2: 내부 Smoke Test
         │  - 헬스체크 API 호출
         │  - 주요 API 엔드포인트 호출
         │  - DB 연결, 캐시 연결 확인
         │
         ▼
Step 3: 내부 사용자 접근 (Internal Preview)
         │  - 내부 직원만 Green으로 라우팅
         │  - VPN/IP 화이트리스트로 접근 제한
         │  - QA 팀의 수동 테스트
         │
         ▼
Step 4: 합성 트래픽 테스트 (Synthetic Traffic)
         │  - 실제 사용자 시나리오를 자동화한 테스트 스크립트
         │  - 부하 테스트 (k6, Locust, Artillery 등)
         │  - 성능 벤치마크 비교
         │
         ▼
Step 5: Traffic Mirroring (선택)
         │  - Blue로 들어오는 실제 트래픽을 Green에도 미러링
         │  - 응답 비교 분석
         │
         ▼
Step 6: 트래픽 전환 (Go/No-Go 결정)
```

#### AWS 기반 Blue-Green 구현

```
[Route 53 가중치 기반 전환]

Route 53 (DNS)
    │
    ├── my-service.example.com → ALB-Blue  (weight: 100)
    │                            └── Target Group: v1 인스턴스
    │
    └── my-service.example.com → ALB-Green (weight: 0)
                                 └── Target Group: v2 인스턴스

전환 시: Blue weight → 0, Green weight → 100
```

```yaml
# K8s Service 기반 Blue-Green
apiVersion: v1
kind: Service
metadata:
  name: my-service
spec:
  selector:
    app: my-service
    version: v1        # 전환 시 v2로 변경
  ports:
    - port: 80
      targetPort: 8080
```

#### Argo Rollouts Blue-Green 설정

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: my-service
spec:
  strategy:
    blueGreen:
      activeService: my-service-active       # 현재 운영 트래픽
      previewService: my-service-preview     # 새 버전 미리보기
      autoPromotionEnabled: false            # 수동 승인 후 전환
      prePromotionAnalysis:                  # 전환 전 자동 검증
        templates:
          - templateName: smoke-test
        args:
          - name: service-name
            value: my-service-preview
      scaleDownDelaySeconds: 600             # 롤백 대비 10분간 이전 버전 유지
```

#### Blue-Green 배포의 문제 상황과 대응

##### 1. 리소스 비용 2배

```
[근본적 문제]

Blue 환경:  EC2 10대 + RDS + ElastiCache = 월 $5,000
Green 환경: EC2 10대 + RDS + ElastiCache = 월 $5,000
──────────────────────────────────────────────
총 비용:    $10,000 (배포 중이 아닐 때도 유지)

vs Canary: 기존 인프라 + Pod 1~2개 추가 ≈ $5,100
```

**대응 방안:**
- 배포 시에만 Green 환경을 프로비저닝하고, 전환 완료 후 이전 환경 축소
- Auto Scaling Group의 min capacity를 0으로 설정해 비사용 시 비용 절감
- Spot Instance 활용으로 Green 환경 비용 절감

##### 2. 전환 순간의 "빅뱅" 위험

```
[문제 시나리오]

전환 직후 5분 이내에 발생하는 문제:
├── 검증에서 잡지 못한 엣지 케이스
├── 실제 트래픽 규모에서만 드러나는 성능 문제
├── 특정 사용자 데이터에서만 발생하는 버그
└── 100% 사용자가 동시에 영향 받음 ← 이것이 핵심 위험
```

Blue-Green은 전환이 all-or-nothing이기 때문에, 문제가 생기면 **전체 사용자**에게 영향이 간다. Canary는 5% 사용자만 영향받는 것과 대조적이다.

**대응 방안:**
- 전환 전 Traffic Mirroring으로 충분히 검증
- 전환 직후 집중 모니터링 (War Room)
- 이전 환경을 즉시 롤백 가능한 상태로 유지
- DNS TTL을 짧게 설정 (30초~1분)하여 롤백 시 빠른 전파

##### 3. DB 마이그레이션과의 충돌

```
[문제 시나리오]

Blue (v1): DB 스키마 A 사용 중
Green (v2): DB 스키마 B 필요

전환 시:
├── DB를 스키마 B로 먼저 변경 → Blue(v1)가 깨짐 ❌
├── 전환 후 DB 변경 → Green(v2)이 스키마 A에서 동작해야 함 ❌
└── 별도 DB를 사용 → 데이터 동기화 문제 ❌
```

**대응 방안:**
- Canary와 동일하게 **Expand-Contract 패턴** 적용
- 또는 **Shared-nothing 구조**: Blue/Green이 각각 독립된 DB를 가지고, 전환 시 데이터 동기화
- 스키마 변경이 크면 Blue-Green보다 **Canary가 더 적합**

##### 4. 장시간 세션/커넥션 끊김

```
[문제 시나리오]

사용자가 Blue에 WebSocket 연결 중
    │
    ▼
트래픽 전환 → Green으로 변경
    │
    ▼
기존 WebSocket 연결 끊김 → 사용자 경험 저하
(긴 폼 작성 중, 파일 업로드 중, 실시간 채팅 중...)
```

**대응 방안:**
- Connection Draining: 기존 연결은 완료될 때까지 유지, 새 연결만 Green으로
- Graceful Shutdown: Blue에서 진행 중인 요청이 완료된 후 종료
- 클라이언트 재연결 로직: WebSocket 끊김 시 자동 재연결

---

### Canary 배포 상세

#### 동작 원리

```
[단계적 트래픽 전환]

Phase 1:  ██░░░░░░░░░░░░░░░░░░  5%  → 새 시스템 (모니터링 24h)
Phase 2:  ██████░░░░░░░░░░░░░░  25% → 새 시스템 (모니터링 12h)
Phase 3:  ██████████░░░░░░░░░░  50% → 새 시스템 (모니터링 6h)
Phase 4:  ████████████████████  100% → 새 시스템 (완전 전환)

각 단계에서 이상 감지 시 → 즉시 0%로 롤백
```

#### Istio 기반 Canary 설정

```yaml
apiVersion: networking.istio.io/v1alpha3
kind: VirtualService
metadata:
  name: my-service
spec:
  hosts:
    - my-service
  http:
    - route:
        - destination:
            host: my-service
            subset: stable    # 기존 버전
          weight: 95
        - destination:
            host: my-service
            subset: canary    # 새 버전
          weight: 5
---
apiVersion: networking.istio.io/v1alpha3
kind: DestinationRule
metadata:
  name: my-service
spec:
  host: my-service
  subsets:
    - name: stable
      labels:
        version: v1
    - name: canary
      labels:
        version: v2
```

#### 자동화된 Canary (Argo Rollouts)

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: my-service
spec:
  strategy:
    canary:
      steps:
        - setWeight: 5
        - pause: { duration: 1h }
        - analysis:
            templates:
              - templateName: success-rate
            args:
              - name: service-name
                value: my-service
        - setWeight: 25
        - pause: { duration: 1h }
        - setWeight: 50
        - pause: { duration: 30m }
        - setWeight: 100
      rollbackWindow:
        revisions: 1
```

---

### Canary 배포의 문제 상황과 대응

#### 1. 버전 간 데이터 스키마 불일치

이것이 Canary 배포에서 **가장 까다로운 문제**다.

```
[문제 시나리오: DB 스키마 변경]

기존 시스템 (v1): users 테이블에 "name" 컬럼 사용
새 시스템 (v2):  users 테이블에 "first_name" + "last_name" 컬럼 사용

Canary 배포 중:
├── v1 Pod → "name" 컬럼 읽기/쓰기 → 정상
├── v2 Pod → "first_name" 컬럼 읽기 → 컬럼 없음 → 에러! ❌
└── 두 버전이 동시에 같은 DB를 공유하므로 충돌 발생
```

**대응 방안: Expand-Contract 패턴**

```
Phase 1 (Expand):
  - "first_name", "last_name" 컬럼 추가 (기존 "name"은 유지)
  - v1은 "name"에 쓰면서 동시에 새 컬럼에도 쓰도록 수정
  - 배포

Phase 2 (Migrate):
  - 기존 데이터 마이그레이션 (name → first_name + last_name)
  - v2 Canary 배포 시작 (새 컬럼 사용)

Phase 3 (Contract):
  - v2가 100% 전환 완료된 후
  - "name" 컬럼 제거
```

#### 2. 세션/상태 불일치 (Sticky Session 문제)

```
[문제 시나리오]

사용자 A: 장바구니에 상품 추가 (v1 처리 → v1 세션에 저장)
          ↓
          결제 요청 (이번엔 v2로 라우팅됨)
          ↓
          v2: "장바구니가 비어있습니다" ❌
```

**대응 방안:**

```
방법 1: Sticky Session (세션 고정)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 같은 사용자는 항상 같은 버전으로 라우팅
- 쿠키 또는 헤더 기반으로 버전 고정
- 단점: 트래픽 비율이 정확하지 않을 수 있음

방법 2: 외부 세션 저장소 (Redis)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 세션을 v1/v2 모두 접근 가능한 외부 저장소에 보관
- 세션 데이터 형식의 하위 호환성 보장 필요

방법 3: Stateless 설계
━━━━━━━━━━━━━━━━━━━━
- JWT 등 토큰 기반으로 상태를 클라이언트에 위임
- 서버 간 세션 공유 불필요
```

#### 3. 캐시 불일치

```
[문제 시나리오]

v1: 상품 가격을 캐시에 저장 (key: "product:123", format: {price: 10000})
v2: 캐시 형식 변경 (key: "product:123", format: {price: 10000, currency: "KRW"})

Canary 중:
- v1이 캐시에 쓴 데이터를 v2가 읽으면 → 파싱 에러
- v2가 캐시에 쓴 데이터를 v1이 읽으면 → 예상치 못한 필드 무시 또는 에러
```

**대응 방안:**
- 캐시 키에 버전을 포함: `product:v1:123`, `product:v2:123`
- 캐시 데이터 형식의 하위 호환성 보장 (새 필드는 optional)
- Canary 전환 완료 후 이전 버전 캐시 무효화

#### 4. 분산 트랜잭션 일관성

```
[문제 시나리오: MSA 환경]

주문 서비스(v2, Canary) → 재고 서비스(v1) → 결제 서비스(v1)

v2의 주문 서비스가 새로운 메시지 포맷으로 이벤트 발행
→ v1 재고 서비스가 새 포맷을 이해하지 못함
→ 트랜잭션 실패, 데이터 불일치
```

**대응 방안:**
- API/이벤트의 하위 호환성을 반드시 유지 (Backward Compatible)
- Consumer-Driven Contract Testing으로 호환성 사전 검증
- 새 필드는 추가만 하고, 기존 필드는 제거하지 않음

#### 5. 모니터링 지표 오염

```
[문제 시나리오]

전체 에러율: 0.5% (정상 범위)

그런데 실제로는:
- v1 (95% 트래픽): 에러율 0.1%
- v2 (5% 트래픽):  에러율 8.0% ← 심각한 문제!

전체 평균에 묻혀서 감지 못함 ❌
```

**대응 방안:**
- 버전별로 지표를 분리해서 모니터링 (필수!)
- Canary 전용 대시보드 구성
- 자동 롤백 조건 설정 (에러율 > N%, 레이턴시 > Nms)

```yaml
# Argo Rollouts AnalysisTemplate 예시
apiVersion: argoproj.io/v1alpha1
kind: AnalysisTemplate
metadata:
  name: success-rate
spec:
  metrics:
    - name: success-rate
      interval: 1m
      successCondition: result[0] >= 0.99  # 99% 이상 성공률
      provider:
        prometheus:
          query: |
            sum(rate(http_requests_total{status=~"2.*", version="canary"}[5m]))
            /
            sum(rate(http_requests_total{version="canary"}[5m]))
    - name: latency-p99
      interval: 1m
      successCondition: result[0] <= 500   # P99 500ms 이하
      provider:
        prometheus:
          query: |
            histogram_quantile(0.99,
              sum(rate(http_request_duration_seconds_bucket{version="canary"}[5m]))
              by (le)
            ) * 1000
```

---

### Traffic Mirroring → Canary 전체 플로우

```
[Phase 0] 준비
   │  - 비교 분석 시스템 구축
   │  - 모니터링/알림 설정
   │  - 롤백 절차 문서화 및 훈련
   │
   ▼
[Phase 1] Traffic Mirroring (1~2주)
   │  - 읽기 요청 100% 미러링
   │  - 응답 비교 분석
   │  - 성능 지표(Latency, Error Rate) 수집
   │  - 불일치 원인 분석 및 수정
   │
   ▼
[Phase 2] Canary 5% (1~2일)
   │  - 실제 트래픽 5% 전환
   │  - 버전별 지표 분리 모니터링
   │  - 에러/지연 이상 시 즉시 롤백
   │
   ▼
[Phase 3] Canary 25% → 50% (단계별 확대)
   │  - 각 단계에서 충분한 관찰 시간 확보
   │  - 트래픽 패턴별 검증 (피크 타임 포함)
   │
   ▼
[Phase 4] 100% 전환 완료
      - 기존 시스템 제거
      - 미러링 인프라 정리
```

---

## 헷갈렸던 포인트

### Q1: Traffic Mirroring과 Canary 배포의 근본적 차이는?

**Traffic Mirroring**은 **검증 도구**이고, **Canary 배포**는 **배포 전략**이다.

| 구분 | Traffic Mirroring | Canary 배포 |
|------|-------------------|-------------|
| 사용자 영향 | 없음 (응답 폐기) | 있음 (실제 응답 제공) |
| 목적 | 정확성 검증 | 안정성 확인 후 점진적 전환 |
| 실패 시 영향 | 없음 | 일부 사용자에게 영향 |
| 롤백 | 불필요 (미러링 중단) | 트래픽 비율을 0%로 변경 |
| 순서 | 먼저 수행 | 미러링 검증 후 수행 |

### Q2: Blue-Green 배포와 Canary 배포의 차이는?

```
Blue-Green: 전체 트래픽을 한 번에 전환
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[Blue  100%] ──── 스위칭 ────▶ [Green 100%]
- 장점: 간단, 빠른 롤백 (다시 Blue로 전환)
- 단점: 문제가 있으면 전체 사용자에게 영향

Canary: 트래픽을 점진적으로 전환
━━━━━━━━━━━━━━━━━━━━━━━━━━━
[기존 95%] + [새 5%] → [기존 75%] + [새 25%] → ... → [새 100%]
- 장점: 소수 사용자로 먼저 검증, 위험 최소화
- 단점: 두 버전이 동시에 존재하는 복잡도
```

| 비교 항목 | Blue-Green | Canary |
|-----------|-----------|--------|
| 전환 방식 | All-or-nothing (100% 한 번에) | 점진적 (5% → 25% → 50% → 100%) |
| 위험 범위 | 전체 사용자 | 일부 사용자 (비율 조절 가능) |
| 롤백 속도 | 매우 빠름 (트래픽 스위칭) | 빠름 (weight를 0으로) |
| 인프라 비용 | 높음 (2배 환경 유지) | 낮음 (기존 + 소수 Pod) |
| 두 버전 공존 | 짧음 (전환 순간만) | 김 (단계별 관찰 기간) |
| DB 스키마 변경 | 상대적으로 단순 (한 시점에 하나만 활성) | 복잡 (두 버전이 오래 공존) |
| 검증 시점 | 전환 **전** (내부 테스트) | 전환 **중** (실제 트래픽) |

### Q3: 실무에서 어떤 소프트웨어/상황에 Blue-Green vs Canary를 쓰는가?

#### Blue-Green이 적합한 경우

```
1. 모바일 앱 백엔드 (API 서버)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 앱 버전과 서버 API 버전의 호환성이 중요
- 새 API 버전을 완전히 준비한 후 한 번에 전환
- 예: 카카오톡, 라인, 토스 등의 주요 릴리즈

2. DB 마이그레이션이 없는 Stateless 서비스
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 정적 웹사이트, CDN 컨텐츠 서버
- 연산 중심 서비스 (이미지 변환, 인코딩 등)
- 예: Netflix CDN, Cloudflare Workers

3. 규제가 엄격한 금융/의료 시스템
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 두 버전이 공존하면 감사(audit) 추적이 복잡
- 전환 전 사전 검증을 철저히 하고 한 번에 전환
- 예: 은행 코어뱅킹, 보험 청구 시스템

4. 배포 빈도가 낮고 변경이 큰 경우
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 월 1~2회 배포, 메이저 버전 업그레이드
- 레거시 시스템 마이그레이션
- 예: ERP 시스템, 사내 관리 도구

5. AWS Elastic Beanstalk, Cloud Foundry
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 플랫폼 자체가 Blue-Green을 기본 지원
- URL Swap, CNAME Swap으로 간단히 전환
```

#### Canary가 적합한 경우

```
1. 대규모 트래픽 웹 서비스
━━━━━━━━━━━━━━━━━━━━━━━━
- 트래픽이 많아 작은 비율로도 충분한 샘플 확보
- 문제 발생 시 영향 범위를 최소화해야 함
- 예: Google, Facebook, Netflix 스트리밍

2. MSA (Microservice Architecture) 환경
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 서비스 간 의존성이 복잡하여 점진적 검증 필요
- 각 서비스를 독립적으로 Canary 배포
- 예: 쿠팡, 배달의민족, Uber

3. Kubernetes + Service Mesh 환경
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Istio/Linkerd가 트래픽 비율 조절을 네이티브 지원
- Argo Rollouts/Flagger로 자동화 용이
- 예: Lyft (Envoy), Airbnb (K8s)

4. 배포 빈도가 높은 CI/CD 환경
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 하루 수십~수백 회 배포
- 각 배포마다 전체 환경을 2벌씩 준비하면 비용 폭발
- 예: Amazon (11.7초에 1회 배포), Etsy

5. Feature Flag와 결합하는 경우
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 특정 사용자 그룹에게만 새 기능 노출
- A/B 테스트와 병행
- 예: LaunchDarkly, Unleash 사용 기업들
```

#### 둘 다 사용하는 경우 (하이브리드)

```
[실무에서 자주 보이는 조합]

인프라 레벨: Blue-Green
━━━━━━━━━━━━━━━━━━━━━━
- K8s 클러스터 자체를 Blue-Green으로 운영
- 클러스터 업그레이드, 인프라 변경 시 사용
- 예: EKS 클러스터를 새로 만들고 DNS 전환

애플리케이션 레벨: Canary
━━━━━━━━━━━━━━━━━━━━━━
- 각 서비스의 코드 변경은 Canary로 배포
- Pod 단위의 점진적 전환
- 예: 일반적인 피처 배포, 버그 수정

Netflix 사례:
├── 리전 단위: Blue-Green (us-east-1 → us-west-2)
├── 서비스 단위: Canary (Spinnaker 자동화)
└── 검증: Traffic Mirroring (Replay Traffic)
```

### Q4: Blue-Green 배포는 어떻게 검증하는가?

Blue-Green은 Canary와 달리 전환 **전에** 검증해야 한다. 실제 사용자 트래픽으로 검증할 수 없으므로 다른 접근이 필요하다.

```
[검증 수단 비교]

             Blue-Green                    Canary
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
검증 시점    전환 전 (사전 검증)           전환 중 (실시간 검증)
트래픽       합성/내부 트래픽              실제 사용자 트래픽
검증 깊이    테스트 시나리오에 의존         실제 패턴으로 검증
한계         엣지 케이스 누락 가능         소수 사용자 영향 가능
```

**Blue-Green의 검증 전략:**
1. **Smoke Test**: 배포 직후 핵심 기능 자동 점검
2. **Internal Preview**: 내부 직원만 Green으로 라우팅하여 사전 검증
3. **Synthetic Monitoring**: 실사용자 시나리오를 모방한 자동화 테스트
4. **Traffic Mirroring**: Blue의 실제 트래픽을 Green에 미러링하여 응답 비교
5. **부하 테스트**: Green에 예상 트래픽 규모를 인위적으로 주입

이 중 **Traffic Mirroring과 결합하는 것이 가장 효과적**이다. Blue-Green 전환 전에 미러링으로 실제 트래픽 패턴을 검증할 수 있기 때문이다.

### Q5: A/B Testing과 Canary 배포의 차이는?

둘 다 트래픽을 분할하지만 **목적이 다르다.**

- **A/B Testing**: 어떤 버전이 **비즈니스 지표(전환율, 클릭률)** 에서 더 나은지 비교
- **Canary 배포**: 새 버전이 **기술적으로 안정적인지** 확인 후 전환

### Q6: 미러링 시 POST 요청도 복제해야 할까?

원칙적으로 **부작용이 있는 요청은 미러링하지 않는 것이 안전**하다. 하지만 쓰기 로직도 검증해야 한다면:

1. 새 시스템을 **Dry-run 모드**로 구성 (실제 DB 쓰기/외부 API 호출 차단)
2. 또는 **격리된 환경**(별도 DB, Sandbox API)에서 처리
3. 요청 헤더에 `X-Mirrored: true`를 붙여 새 시스템이 부작용을 억제하도록 분기

어떤 방법이든 **운영 데이터에 영향을 주지 않는 것이 절대 원칙**이다.

### Q7: Canary에서 자동 롤백은 어떻게 구현하는가?

```
[자동 롤백 파이프라인]

Prometheus/Grafana
       │
       ▼
  지표 수집 (에러율, 레이턴시, CPU, 메모리)
       │
       ▼
  임계값 비교 (에러율 > 1%? P99 > 500ms?)
       │
       ├── 정상 → 다음 단계로 weight 증가
       │
       └── 이상 → 즉시 Canary weight를 0%로
                  + Slack/PagerDuty 알림 발송
                  + 롤백 사유 로깅
```

Argo Rollouts, Flagger, Spinnaker 같은 도구가 이를 자동화해준다.

## 면접 답변 전략

### "Traffic Mirroring의 한계점 1가지"

> Traffic Mirroring은 **부작용(Side Effect)이 있는 쓰기 요청을 안전하게 미러링하기 어렵다**는 근본적 한계가 있습니다. 결제, 알림 발송, DB 쓰기 등의 요청이 복제되면 이중 처리가 발생할 수 있어, 읽기 요청만 미러링하거나 새 시스템을 Dry-run 모드로 구성해야 합니다. 이 경우 쓰기 로직의 검증이 불완전해지는 트레이드오프가 존재합니다.

### "Traffic Mirroring 시 주의사항 1가지"

> 미러링 트래픽의 실패나 지연이 **원본 서비스에 절대 영향을 주어서는 안 됩니다.** 미러링은 반드시 비동기(fire-and-forget) 방식으로 처리하고, 새 시스템의 장애가 프록시 계층을 통해 기존 시스템으로 전파되지 않도록 격리해야 합니다. 이를 위해 별도의 커넥션 풀과 타임아웃을 설정하고, 미러링 실패 시에도 원본 응답에는 영향이 없도록 구현해야 합니다.

### "Blue-Green 배포의 한계와 검증 방법"

> Blue-Green 배포는 트래픽을 한 번에 100% 전환하므로, 사전 검증에서 놓친 문제가 있으면 **전체 사용자에게 즉시 영향**이 갑니다. 또한 두 환경을 동시에 유지해야 하므로 **인프라 비용이 2배**입니다. 이를 보완하기 위해 전환 전에 Traffic Mirroring으로 Blue의 실제 트래픽을 Green에 복제하여 응답을 비교하고, 내부 직원 대상 Preview 라우팅으로 사전 검증합니다. 인프라 비용은 배포 시에만 Green을 프로비저닝하고 전환 완료 후 이전 환경을 축소하는 방식으로 절감할 수 있습니다.

### "Blue-Green vs Canary 선택 기준"

> **Blue-Green**은 배포 빈도가 낮고, Stateless하며, DB 스키마 변경이 없는 서비스에 적합합니다. 금융/의료처럼 규제가 엄격하여 두 버전 공존이 감사 추적을 복잡하게 만드는 경우에도 유리합니다. **Canary**는 대규모 트래픽의 MSA 환경에서, 배포 빈도가 높고, 실제 사용자 트래픽으로 점진적 검증이 필요한 경우에 적합합니다. 실무에서는 인프라 레벨(K8s 클러스터 교체)에서는 Blue-Green, 애플리케이션 레벨(서비스 코드 배포)에서는 Canary를 사용하는 하이브리드 방식도 많이 사용합니다.

### "Canary 배포로 인한 문제 상황과 대응 방안"

> Canary 배포 시 **두 버전이 동시에 같은 DB를 사용하면서 스키마 불일치로 장애가 발생**할 수 있습니다. 예를 들어 v2에서 컬럼 이름을 변경하면 v1이 해당 컬럼을 찾지 못해 에러가 발생합니다. 이를 예방하기 위해 **Expand-Contract 패턴**을 적용합니다. 먼저 새 컬럼을 추가하고(Expand), 양쪽 버전 모두 호환되는 상태에서 Canary를 진행한 뒤, 완전 전환 후 이전 컬럼을 제거(Contract)합니다. 이렇게 하면 배포 중 어느 시점에서든 두 버전이 안전하게 공존할 수 있습니다.

## 참고 자료

- [Istio Traffic Mirroring 공식 문서](https://istio.io/latest/docs/tasks/traffic-management/mirroring/)
- [Argo Rollouts - Canary 배포 가이드](https://argoproj.github.io/argo-rollouts/features/canary/)
- [Martin Fowler - Canary Release](https://martinfowler.com/bliki/CanaryRelease.html)
- [Nginx Mirror Module](https://nginx.org/en/docs/http/ngx_http_mirror_module.html)
