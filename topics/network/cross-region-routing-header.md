# Cross-Region 라우팅 헤더 설계 — X-Region-Info 기반 지역 간 서버 통신

## 핵심 정리

### 문제 상황
- 유저마다 **소속 지역(Region) 정보**가 있고, 해당 지역의 서버를 타도록 구성
- 백오피스 등 **단일 지역에서만 운영 중인 서버**가 존재
- 타 지역 유저가 이 단일 지역 서버에 접근하여 데이터를 CRUD하면 **Cross-Region 문제** 발생
- **구체적 증상:** 타 지역 유저가 로그인 후 Redis Session 값을 업데이트하면 **세션이 무효화(캐시 eviction)되지 않음**
- 같은 지역의 유저는 세션 캐시가 정상적으로 날아감 → **지역 간 Redis 동기화 문제로 추정**
- 게이트웨이에서 `X-Region-Info` 헤더를 기반으로 적절한 지역으로 요청을 라우팅하려는 설계

### 아키텍처 개요 — 현재 문제 구조

```
[유저 A (서울, region=kr)]          [유저 B (싱가포르, region=sg)]
     │                                    │
     ▼                                    ▼
┌──────────┐                        ┌──────────┐
│ Seoul GW │                        │ SG GW    │
└────┬─────┘                        └────┬─────┘
     │                                   │
     ▼                                   │  ※ 단일 지역 서버 접근
┌──────────┐    ┌──────────┐             │
│ Seoul    │    │ Seoul    │◄────────────┘
│ Services │    │ Redis    │
└──────────┘    └──────────┘
                     │
                     ├─ 유저 A 세션 업데이트 → eviction 정상 ✅
                     └─ 유저 B 세션 업데이트 → eviction 안 됨 ❌
                         (유저 B의 세션은 SG Redis에 있을 수 있음)
```

### Cross-Region 세션 무효화 실패 — 추정 원인 분석

타 지역 유저만 세션 무효화가 안 되는 이유는 여러 가지가 있을 수 있다:

```
원인 1: Redis가 지역별로 분리되어 있음 (가장 유력)
─────────────────────────────────────────────────
[SG 유저] → [KR 단일서버] → KR Redis에 세션 업데이트
                              하지만 SG 유저의 원래 세션은 SG Redis에 있음
                              → KR Redis의 eviction이 SG Redis에 전파되지 않음
                              → 유저의 다음 요청이 SG Gateway로 가면 SG Redis의 stale 세션을 읽음

원인 2: Redis Pub/Sub 기반 캐시 무효화가 지역을 넘지 못함
─────────────────────────────────────────────────────────
Spring Session이 Redis Pub/Sub으로 세션 변경을 알리는데,
Pub/Sub은 같은 Redis 클러스터 내에서만 전파됨
→ 다른 지역 Redis에는 이벤트가 도달하지 않음

원인 3: 세션 쿠키/토큰의 지역 바인딩 문제
────────────────────────────────────────
유저 세션 ID가 원래 지역 Redis에서 생성됨
단일 지역 서버에서 같은 세션 ID로 업데이트해도
원래 지역에서는 변경을 인식하지 못함

원인 4: Gateway가 유저 지역 기반으로 Redis를 선택
──────────────────────────────────────────────
요청 처리 시 유저의 region 정보로 Redis 엔드포인트를 결정하는 로직이 있다면,
단일 지역 서버에서는 항상 로컬(KR) Redis만 바라보므로
SG 유저의 세션은 SG Redis에서 관리되어 불일치 발생
```

### 원인 확인을 위한 디버깅 체크리스트

```
□ 1. Redis 토폴로지 확인
     - 지역별 독립 Redis인지, Global Datastore(복제)인지
     - Redis Cluster 구성인지, Standalone인지

□ 2. 세션 저장 위치 확인
     - 타 지역 유저의 세션이 어느 Redis에 저장되는지
     - 단일 지역 서버가 어느 Redis에 쓰는지
     → redis-cli KEYS "spring:session:*" 로 양쪽 Redis에서 확인

□ 3. 캐시 무효화 메커니즘 확인
     - Spring Session의 Redis 이벤트 설정 (notify-keyspace-events)
     - Pub/Sub 채널이 지역 간 연결되어 있는지
     - @CacheEvict 또는 수동 eviction의 대상 Redis

□ 4. 요청 흐름 추적
     - 타 지역 유저 요청이 단일 지역 서버에 도달할 때 어떤 Redis를 사용하는지
     - 세션 업데이트 후 다음 요청이 어느 지역 Gateway를 통해 가는지
```

### X-Region-Info 헤더 설계

```
X-Region-Info: <target-region>
```

**헤더 값 구성 요소:**
| 필드 | 설명 | 예시 |
|------|------|------|
| `X-Region-Info` | 요청을 처리할 대상 지역 | `kr-1`, `sg-1`, `us-west-1` |
| `X-Region-Origin` | 요청이 발생한 원본 지역 | `sg-1` |
| `X-Region-Hop-Count` | 라우팅 홉 수 (무한 루프 방지) | `1`, `2` (최대 3) |
| `X-Region-Request-Id` | 지역 간 요청 추적 ID | `uuid-v4` |
| `X-Region-Timestamp` | 요청 발생 시각 (TTL 검증용) | ISO 8601 |

### 게이트웨이 라우팅 로직

```
1. 유저 요청 → 가장 가까운 지역의 Gateway 도달
2. Gateway가 요청 분석:
   a. 이미 X-Region-Info가 있으면 → 해당 지역으로 포워딩
   b. 없으면 → 요청 경로/파라미터/유저 정보 기반으로 대상 지역 결정
3. 대상 지역이 현재 지역이면 → 로컬 서비스로 전달
4. 대상 지역이 다른 지역이면 → X-Region-Info 헤더 추가 후 대상 지역 Gateway로 포워딩
5. 대상 지역 Gateway → 로컬 서비스로 전달
```

**라우팅 결정 기준:**
```yaml
# 라우팅 테이블 예시
routing_rules:
  - path_prefix: "/api/backoffice/**"
    target_region: "kr-1"          # 백오피스는 항상 한국
  - path_prefix: "/api/settlement/**"
    target_region: "kr-1"          # 정산도 한국에서만 운영
  - path_prefix: "/api/users/**"
    target_region: "from_user_metadata"  # 유저의 소속 지역
  - path_prefix: "/api/orders/**"
    target_region: "from_request_body"   # 주문 대상 지역
```

## 효율적인 개발 전략

### 1. Gateway 레벨 구현 (Spring Cloud Gateway / Envoy / Nginx)

**Spring Cloud Gateway 필터 예시:**
```java
@Component
public class CrossRegionRoutingFilter implements GlobalFilter, Ordered {

    private final RegionRoutingResolver routingResolver;
    private final RegionRegistry regionRegistry;

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        ServerHttpRequest request = exchange.getRequest();

        // 1. 이미 Cross-Region 헤더가 있으면 (다른 지역에서 포워딩된 요청)
        String regionInfo = request.getHeaders().getFirst("X-Region-Info");
        if (regionInfo != null && regionInfo.equals(regionRegistry.getCurrentRegion())) {
            // 현재 지역 대상이면 로컬로 전달
            return chain.filter(exchange);
        }

        // 2. 대상 지역 결정
        String targetRegion = routingResolver.resolve(request);

        // 3. 현재 지역이면 그냥 통과
        if (targetRegion.equals(regionRegistry.getCurrentRegion())) {
            return chain.filter(exchange);
        }

        // 4. 다른 지역이면 포워딩
        String hopCount = request.getHeaders().getFirst("X-Region-Hop-Count");
        int hops = hopCount != null ? Integer.parseInt(hopCount) : 0;
        if (hops >= 3) {
            return Mono.error(new TooManyHopsException("Cross-region hop limit exceeded"));
        }

        ServerHttpRequest mutatedRequest = request.mutate()
            .header("X-Region-Info", targetRegion)
            .header("X-Region-Origin", regionRegistry.getCurrentRegion())
            .header("X-Region-Hop-Count", String.valueOf(hops + 1))
            .header("X-Region-Request-Id", UUID.randomUUID().toString())
            .header("X-Region-Timestamp", Instant.now().toString())
            .build();

        // 대상 지역 Gateway URL로 리다이렉트
        URI targetUri = regionRegistry.getGatewayUri(targetRegion);
        // ... 포워딩 로직
        return chain.filter(exchange.mutate().request(mutatedRequest).build());
    }

    @Override
    public int getOrder() {
        return -1; // 가장 먼저 실행
    }
}
```

### 2. Region Registry — 지역 정보 중앙 관리

```java
@Component
public class RegionRegistry {

    // 각 지역의 Gateway 엔드포인트 관리
    private final Map<String, RegionInfo> regions;

    @Data
    public static class RegionInfo {
        private String regionId;       // "kr-1"
        private String gatewayUrl;     // "https://gw.kr-1.internal.example.com"
        private String publicUrl;      // "https://api.kr.example.com"
        private boolean healthy;       // 헬스 체크 상태
        private List<String> services; // 해당 지역에서 운영 중인 서비스 목록
    }

    public URI getGatewayUri(String regionId) {
        RegionInfo info = regions.get(regionId);
        if (info == null || !info.isHealthy()) {
            throw new RegionUnavailableException(regionId);
        }
        return URI.create(info.getGatewayUrl());
    }
}
```

### 3. 서비스 간 전파 — 내부 호출 시에도 헤더 유지

```java
// Feign Client Interceptor — 내부 서비스 간 호출 시 Region 헤더 전파
@Component
public class RegionHeaderPropagationInterceptor implements RequestInterceptor {

    @Override
    public void apply(RequestTemplate template) {
        // 현재 요청의 Region 헤더를 내부 호출에도 전파
        ServletRequestAttributes attrs =
            (ServletRequestAttributes) RequestContextHolder.getRequestAttributes();

        if (attrs != null) {
            HttpServletRequest request = attrs.getRequest();
            propagateHeader(request, template, "X-Region-Info");
            propagateHeader(request, template, "X-Region-Origin");
            propagateHeader(request, template, "X-Region-Request-Id");
            propagateHeader(request, template, "X-Region-Hop-Count");
        }
    }

    private void propagateHeader(HttpServletRequest from, RequestTemplate to, String header) {
        String value = from.getHeader(header);
        if (value != null) {
            to.header(header, value);
        }
    }
}
```

### 4. 비동기 메시지에도 Region 정보 포함

```java
// Kafka 메시지에 Region 메타데이터 포함
public class RegionAwareKafkaProducer {

    public <T> void send(String topic, String key, T payload) {
        ProducerRecord<String, T> record = new ProducerRecord<>(topic, key, payload);

        // 메시지 헤더에 Region 정보 추가
        record.headers().add("X-Region-Origin",
            regionRegistry.getCurrentRegion().getBytes(StandardCharsets.UTF_8));
        record.headers().add("X-Region-Request-Id",
            MDC.get("regionRequestId").getBytes(StandardCharsets.UTF_8));

        kafkaTemplate.send(record);
    }
}
```

## 보안에서 신경 써야 할 점

### 1. 헤더 위조 방지 (Header Spoofing)

**가장 중요한 보안 이슈.** 외부 클라이언트가 `X-Region-Info` 헤더를 직접 설정하면 임의의 지역으로 요청을 라우팅할 수 있다.

```java
// Gateway 진입점에서 외부 요청의 Region 헤더를 무조건 제거
@Component
@Order(Ordered.HIGHEST_PRECEDENCE) // 가장 먼저 실행
public class ExternalHeaderStrippingFilter implements GlobalFilter {

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        // 외부 요청인지 판별 (내부 네트워크에서 온 게 아니면)
        if (!isInternalRequest(exchange.getRequest())) {
            ServerHttpRequest sanitized = exchange.getRequest().mutate()
                .headers(headers -> {
                    headers.remove("X-Region-Info");
                    headers.remove("X-Region-Origin");
                    headers.remove("X-Region-Hop-Count");
                    headers.remove("X-Region-Request-Id");
                    headers.remove("X-Region-Timestamp");
                })
                .build();
            return chain.filter(exchange.mutate().request(sanitized).build());
        }
        return chain.filter(exchange);
    }

    private boolean isInternalRequest(ServerHttpRequest request) {
        // 내부 네트워크 CIDR 기반 판별
        InetSocketAddress remoteAddress = request.getRemoteAddress();
        return INTERNAL_CIDRS.stream()
            .anyMatch(cidr -> cidr.contains(remoteAddress.getAddress()));
    }
}
```

### 2. 지역 간 통신 인증 (mTLS + HMAC 서명)

지역 간 Gateway 통신은 반드시 상호 인증이 필요하다.

```yaml
# 지역 간 통신 보안 계층
보안 레이어:
  L1 - 네트워크: VPN / 전용선 / AWS VPC Peering / GCP VPC Network Peering
  L2 - TLS:      mTLS (상호 인증, 각 지역 Gateway에 인증서 발급)
  L3 - 헤더 서명: HMAC-SHA256으로 X-Region 헤더 무결성 검증
  L4 - 토큰:     내부 서비스 간 JWT (짧은 만료 시간)
```

**HMAC 헤더 서명 — 헤더 변조 감지:**
```java
public class RegionHeaderSigner {

    private final SecretKey hmacKey; // 지역 간 공유 비밀키 (KMS에서 관리)

    // 서명 생성 (보내는 쪽)
    public String sign(Map<String, String> regionHeaders) {
        String payload = regionHeaders.entrySet().stream()
            .sorted(Map.Entry.comparingByKey())
            .map(e -> e.getKey() + "=" + e.getValue())
            .collect(Collectors.joining("&"));

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(hmacKey);
        byte[] signature = mac.doFinal(payload.getBytes(StandardCharsets.UTF_8));
        return Base64.getEncoder().encodeToString(signature);
    }

    // 서명 검증 (받는 쪽)
    public boolean verify(Map<String, String> regionHeaders, String receivedSignature) {
        String expectedSignature = sign(regionHeaders);
        return MessageDigest.isEqual(
            expectedSignature.getBytes(),
            receivedSignature.getBytes()
        );
    }
}
```

### 3. Rate Limiting — 지역 간 요청 폭주 방지

```yaml
# 지역별 Rate Limit 설정
cross_region_rate_limits:
  kr-1_to_sg-1:
    requests_per_second: 1000
    burst: 2000
  sg-1_to_kr-1:
    requests_per_second: 500
    burst: 1000
  # 백오피스 지역으로의 요청은 더 제한적으로
  any_to_backoffice:
    requests_per_second: 200
    burst: 500
```

### 4. Replay Attack 방지

```java
// X-Region-Timestamp 기반 요청 만료 검증
public class ReplayAttackGuard {

    private static final Duration MAX_AGE = Duration.ofSeconds(30);

    public void validate(ServerHttpRequest request) {
        String timestamp = request.getHeaders().getFirst("X-Region-Timestamp");
        if (timestamp == null) {
            throw new SecurityException("Missing region timestamp");
        }

        Instant requestTime = Instant.parse(timestamp);
        if (Duration.between(requestTime, Instant.now()).abs().compareTo(MAX_AGE) > 0) {
            throw new SecurityException("Cross-region request expired");
        }

        // Request ID 중복 체크 (Redis)
        String requestId = request.getHeaders().getFirst("X-Region-Request-Id");
        Boolean isNew = redisTemplate.opsForValue()
            .setIfAbsent("region-req:" + requestId, "1", MAX_AGE.multipliedBy(2));
        if (Boolean.FALSE.equals(isNew)) {
            throw new SecurityException("Duplicate cross-region request");
        }
    }
}
```

### 5. 민감 데이터 지역 제한 (Data Residency)

```java
// 특정 데이터는 지역을 벗어나면 안 됨 (GDPR, 개인정보보호법 등)
@Component
public class DataResidencyFilter implements GlobalFilter {

    private static final Map<String, Set<String>> RESTRICTED_PATHS = Map.of(
        "/api/users/personal-info/**", Set.of("kr-1"),  // 개인정보는 한국만
        "/api/payment/card/**", Set.of("kr-1"),          // 결제 정보도 한국만
        "/api/eu-users/**", Set.of("eu-west-1")          // EU 유저 데이터는 EU만
    );

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        String path = exchange.getRequest().getPath().value();
        String targetRegion = exchange.getRequest().getHeaders().getFirst("X-Region-Info");

        for (var entry : RESTRICTED_PATHS.entrySet()) {
            if (pathMatcher.match(entry.getKey(), path)) {
                if (!entry.getValue().contains(targetRegion)) {
                    // 해당 지역으로 이 데이터를 보낼 수 없음
                    log.warn("Data residency violation: {} → {}", path, targetRegion);
                    return Mono.error(new DataResidencyViolationException());
                }
            }
        }
        return chain.filter(exchange);
    }
}
```

### 6. 보안 체크리스트 종합

| 위협 | 대응 | 구현 위치 |
|------|------|-----------|
| **헤더 위조** | 외부 요청의 X-Region-* 헤더 강제 제거 | Gateway 최상위 필터 |
| **중간자 공격** | mTLS + HMAC 헤더 서명 | Gateway 간 통신 |
| **Replay Attack** | Timestamp TTL + Request ID 중복 체크 | Gateway 수신 필터 |
| **무한 루프** | Hop Count 제한 (최대 3) | 라우팅 필터 |
| **데이터 유출** | Data Residency 정책 필터 | Gateway 라우팅 전 |
| **DDoS 증폭** | 지역별 Rate Limiting | Gateway |
| **내부 서비스 노출** | 내부 네트워크 CIDR 검증 | Gateway 진입점 |
| **키 유출** | HMAC 키를 KMS로 관리, 주기적 로테이션 | 인프라/운영 |
| **로깅/감사** | Cross-Region 요청 전용 감사 로그 | 전 구간 |

## 헷갈렸던 포인트

### Q: 타 지역 유저만 Redis 세션 무효화가 안 되는 건 어떻게 해결하나?

**A:** 근본 원인에 따라 해결책이 달라진다.

**해결책 1: X-Region-Info 헤더로 올바른 Redis를 타게 하기 (라우팅 방식)**
```
[SG 유저] → [SG GW] → X-Region-Info: kr-1 추가
                     → [KR GW] → [KR 단일서버] → KR Redis
                                                     │
                     ← 응답 ←────────────────────────┘

유저의 다음 요청도 동일하게 KR로 라우팅
→ 세션 읽기/쓰기가 모두 KR Redis에서 발생 → 정합성 보장
```
이 방식이 `X-Region-Info` 헤더를 도입하려는 핵심 이유. 단일 지역 서버를 쓸 때는 **세션도 해당 지역의 Redis를 일관되게 사용**하도록 라우팅해야 한다.

**해결책 2: Redis Global Datastore (복제 방식)**
```yaml
# AWS ElastiCache Global Datastore
Primary: KR Redis (read/write)
Secondary: SG Redis (read-only, 자동 복제)

# 단점:
# - 복제 지연(보통 < 1초이지만 보장 불가)
# - 비용 증가
# - 쓰기는 항상 Primary로 가야 함
```

**해결책 3: Cross-Region 캐시 무효화 이벤트 전파 (이벤트 방식)**
```
[KR 단일서버] → KR Redis 세션 업데이트
              → Kafka/SNS로 "session:유저B:invalidate" 이벤트 발행
              → SG 리전 Consumer가 SG Redis에서 해당 세션 삭제

# 단점: 이벤트 전파 지연 동안 stale 세션이 남음
```

**추천:** 단일 지역 서버를 위한 요청이라면 **해결책 1(X-Region-Info 라우팅)**이 가장 깔끔. 세션의 읽기/쓰기 지역을 일치시키는 것이 핵심.

### Q: 왜 DNS 기반 라우팅(GeoDNS)만으로는 부족한가?

**A:** GeoDNS는 유저의 **물리적 위치** 기반으로 가장 가까운 서버를 연결해주지만, 문제의 핵심은 **데이터가 어디에 있느냐**다.

- 서울 유저가 싱가포르에만 있는 백오피스 데이터를 조회해야 하는 상황
- GeoDNS는 서울 유저를 서울 서버로 보내지만, 서울 서버에는 그 데이터가 없음
- **데이터의 위치를 아는 것은 애플리케이션 레벨** → 헤더 기반 라우팅이 필요

### Q: X-Region-Info를 유저(클라이언트)가 설정하면 안 되나?

**A:** 절대 안 된다. 보안 위험이 크다.

1. 클라이언트가 헤더를 임의로 조작하면 권한 없는 지역의 데이터에 접근 가능
2. 내부 네트워크 토폴로지가 클라이언트에 노출됨
3. 반드시 **Gateway가 서버 사이드에서 결정**해야 함
4. 외부에서 들어온 X-Region-* 헤더는 무조건 Strip

### Q: 지역 간 통신 지연(Latency)은 어떻게 최소화하나?

**A:**
- **전용선/VPC Peering**: 공용 인터넷 대신 전용 네트워크 사용 (AWS Direct Connect, GCP Interconnect)
- **Connection Pool 유지**: 지역 간 Gateway 연결을 미리 열어두고 재사용
- **비동기 처리**: 실시간 응답이 필요 없는 작업은 Kafka/SQS로 비동기 전달
- **읽기 복제본**: 자주 조회되는 데이터는 각 지역에 Read Replica 배치
- **캐싱**: Redis Global Datastore로 지역별 캐시 동기화

### Q: 장애 상황에서 특정 지역이 죽으면?

**A:** Circuit Breaker + Fallback 전략이 필수.

```
1. 대상 지역 Gateway 헬스 체크 실패 감지
2. Circuit Breaker OPEN → 해당 지역으로의 라우팅 차단
3. Fallback 전략 실행:
   - 읽기 요청 → 캐시 또는 Read Replica에서 응답 (stale 허용)
   - 쓰기 요청 → 큐에 적재 후 나중에 재시도 (eventual consistency)
   - 백오피스 → "해당 지역 서비스 일시 중단" 안내
4. 지역 복구 시 → 큐의 적재된 요청 순차 처리
```

### Q: 여러 지역의 데이터를 조합해야 하는 요청은?

**A:** Aggregation 패턴 사용.

- **Gateway Aggregation**: Gateway에서 여러 지역에 병렬 요청 후 결과 조합
- **BFF (Backend For Frontend)**: 전용 서비스가 여러 지역 API를 호출하여 결과 조합
- 주의: 한 지역이 느리면 전체 응답이 느려지므로 **타임아웃 + partial response** 전략 필요

## 참고 자료

- [AWS Cross-Region Architecture Best Practices](https://docs.aws.amazon.com/whitepapers/latest/aws-multi-region-fundamentals/cross-region-data.html)
- [Envoy Proxy — External Authorization](https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/ext_authz_filter)
- [Netflix Zuul — Cross-Region Routing](https://netflixtechblog.com/)
- [Spring Cloud Gateway Documentation](https://docs.spring.io/spring-cloud-gateway/reference/)
