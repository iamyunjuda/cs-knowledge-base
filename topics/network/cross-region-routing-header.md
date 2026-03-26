# Cross-Region 라우팅 헤더 설계 — X-Region-Info 기반 지역 간 서버 통신

## 핵심 정리

### 문제 상황
- 한 지역(Region)에 서버들이 클러스터로 구성되어 있음
- 백오피스 또는 특정 지역에서만 운영 중인 서버가 존재
- 다른 지역의 유저가 해당 서버의 데이터를 CRUD할 때 **Cross-Region 지연/장애** 발생
- 게이트웨이에서 `X-Region-Info` 헤더를 기반으로 적절한 지역으로 요청을 라우팅하려는 설계

### 아키텍처 개요

```
[유저 (서울)]                    [유저 (싱가포르)]
     │                                │
     ▼                                ▼
┌─────────────┐               ┌─────────────┐
│ Seoul GW    │               │ Singapore GW│
│ (Gateway)   │               │ (Gateway)   │
└──────┬──────┘               └──────┬──────┘
       │                             │
       │  X-Region-Info: sg-1       │  X-Region-Info: kr-1
       │  ─────────────────────►    │  ─────────────────────►
       │                             │
       ▼                             ▼
┌─────────────┐               ┌─────────────┐
│ Seoul       │               │ Singapore   │
│ Services    │◄─────────────►│ Services    │
└─────────────┘  Cross-Region └─────────────┘
                  Backbone
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
