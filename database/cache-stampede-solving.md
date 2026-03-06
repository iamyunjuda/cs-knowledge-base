# Cache Stampede 해결기 — 주기적 DB 부하 급증의 원인을 찾아서

## 핵심 정리

캐시가 동시에 만료되면서 수많은 요청이 한꺼번에 DB로 몰리는 **Cache Stampede(Thundering Herd)** 현상과, 이를 직접 진단하고 해결해 나가는 과정을 정리한다.

---

## 상황 설정

나는 상품 정보 조회 API를 운영하고 있다. 카테고리별 상품 목록, 추천 상품, 프로모션 배너 등 다양한 데이터를 Key 단위로 Redis에 캐싱해서 트래픽을 처리한다. 평소에는 DB 부하도 낮고, 응답도 빠르게 나가고 있었다.

**시스템 구성:**
- 캐시: Redis 클러스터
- DB: Primary-Replica 구조의 PostgreSQL
- 애플리케이션: 6대의 WAS에서 로드밸런싱

---

## 1단계: 이상 징후 발견

어느 날 모니터링 대시보드를 보다가 이상한 그래프 패턴을 발견했다.

```
15:00 — DB 쿼리 수 폭증 → 잠시 후 정상화
15:05 — 또 폭증 → 잠시 후 정상화
15:10 — 또 폭증 → 잠시 후 정상화
```

DB 쿼리가 주기적으로 급증하고, 그때마다 API 응답 시간이 수 초대로 치솟으며, 일부 요청은 타임아웃으로 실패했다. 그러다 20~40초 정도 지나면 자연스럽게 복구됐다.

처음에는 "크론잡이 돌아가나?" 싶었지만, 크론잡 스케줄과는 맞지 않았다. 외부 이벤트나 트래픽 급증도 아니었다. 뭔가 **내부적인 원인**이 있었다.

---

## 2단계: 원인 추적

### 가설 1: 슬로우 쿼리?

DB 슬로우 쿼리 로그를 확인했다.

```sql
-- 문제 시간대에 집중된 쿼리들
SELECT * FROM product_display WHERE display_key = 'home-best-sellers';
SELECT * FROM product_display WHERE display_key = 'category-electronics';
SELECT * FROM product_display WHERE display_key = 'promo-banner-main';
```

쿼리 자체는 단순한 Key 조회였다. 1건이면 1ms도 안 걸리는 쿼리가, 이 시간대에만 **수천 건씩 동시에** 들어오고 있었다.

### 가설 2: 캐시 미스?

Redis 로그를 뒤졌다. 그리고 결정적인 단서를 찾았다.

```
# 캐시 설정 코드를 열어봤다
redis.set(key, value, EX=300)  # TTL 300초 = 5분
```

**TTL이 전부 300초(5분)로 동일했다.** 서버가 배포되거나 재시작되면, 비슷한 시점에 캐시가 세팅되고, 정확히 5분 뒤에 **한꺼번에 만료**된다.

### 원인 확정: Cache Stampede

흐름을 정리하면 이렇다:

```
[시점 0초] 캐시 세팅 (TTL=300s)
    ↓
[시점 300초] 인기 Key 여러 개의 캐시가 동시에 만료
    ↓
[시점 300초 ~ 301초]
  서버 1: "캐시 없네? → DB 조회"
  서버 2: "캐시 없네? → DB 조회"
  서버 3: "캐시 없네? → DB 조회"
  ...
  서버 6 × 수백 동시 요청 = DB에 수천 건 동시 쿼리
    ↓
  DB 과부하 → 응답 지연 → 타임아웃
    ↓
  캐시가 다시 채워지며 자동 복구
```

인기 Key일수록 초당 요청이 많으니, 캐시가 비는 순간 **모든 서버의 모든 요청이 동시에 DB를 때린다.** 이것이 바로 Cache Stampede(Thundering Herd) 현상이다.

---

## 3단계: 해결 전략 수립

원인을 파악했으니, 해결책을 설계했다. 하나의 은탄환은 없었고, **여러 전략을 조합**해야 했다.

### 전략 1: TTL에 랜덤 지터(Jitter) 추가

가장 먼저 적용한 방법. 캐시 만료 시점을 흩뿌려서 동시 만료를 방지한다.

```python
import random

base_ttl = 300
jitter = random.randint(0, 60)  # 0~60초 랜덤
redis.set(key, value, EX=base_ttl + jitter)

# 결과: 캐시 만료가 300초~360초 사이에 분산
```

**효과:** 동시 만료되는 Key 수가 대폭 줄어든다.
**한계:** 인기 Key 하나만 만료돼도 동시 요청이 많으면 여전히 문제될 수 있다.

### 전략 2: 분산 락(Distributed Lock)을 이용한 단일 갱신

캐시 미스가 발생했을 때, **딱 한 스레드만** DB를 조회하고 나머지는 기다리게 한다.

```python
def get_product_display(key):
    value = redis.get(key)
    if value is not None:
        return value

    lock_key = f"lock:{key}"
    if redis.set(lock_key, "1", NX=True, EX=10):  # 락 획득 시도
        try:
            # 락을 잡은 스레드만 DB 조회
            value = db.query("SELECT * FROM product_display WHERE display_key = %s", key)
            redis.set(key, value, EX=300 + random.randint(0, 60))
            return value
        finally:
            redis.delete(lock_key)
    else:
        # 락을 못 잡은 스레드 → 잠깐 대기 후 캐시 재확인
        time.sleep(0.05)
        return redis.get(key) or get_product_display(key)  # 재시도
```

**효과:** Key당 DB 조회가 1번만 발생한다. DB 부하가 극적으로 감소.
**한계:** 락 대기 시간만큼 응답 지연이 생길 수 있다. 락을 잡은 프로세스가 죽으면 EX 시간까지 대기해야 한다.

### 전략 3: 논리적 만료(Logical Expiry) + 백그라운드 갱신

캐시의 물리적 TTL은 넉넉하게 잡고, **논리적 만료 시간**을 데이터에 포함시킨다. 만료되면 백그라운드에서 갱신한다.

```python
import json, time, threading

def set_with_logical_expiry(key, value, logical_ttl=300):
    data = json.dumps({
        "value": value,
        "expires_at": time.time() + logical_ttl
    })
    # 물리적 TTL은 논리적 TTL보다 훨씬 길게
    redis.set(key, data, EX=logical_ttl * 2)

def get_product_display(key):
    raw = redis.get(key)
    if raw is None:
        # 물리적으로도 없으면 동기 조회 (분산 락 병행)
        return fetch_and_cache(key)

    data = json.loads(raw)
    if time.time() < data["expires_at"]:
        return data["value"]  # 아직 유효 → 바로 반환

    # 논리적으로 만료 → 일단 stale 데이터 반환, 백그라운드 갱신
    threading.Thread(target=fetch_and_cache, args=(key,)).start()
    return data["value"]  # 오래된 데이터라도 즉시 반환
```

**효과:** 사용자는 항상 즉시 응답을 받는다. DB 갱신은 백그라운드에서 하나만 일어난다.
**한계:** 갱신 완료 전까지 약간 오래된 데이터가 반환될 수 있다.

### 전략 4: 인기 Key는 사전 워밍(Pre-warming)

만료되기 **전에** 미리 갱신한다.

```python
# 별도 스케줄러가 주기적으로 실행
HOT_KEYS = ["home-best-sellers", "category-electronics", "promo-banner-main"]

def pre_warm_hot_keys():
    for key in HOT_KEYS:
        remaining_ttl = redis.ttl(key)
        if remaining_ttl < 30:  # 만료 30초 전이면
            value = db.query("SELECT * FROM product_display WHERE display_key = %s", key)
            redis.set(key, value, EX=300 + random.randint(0, 60))
```

**효과:** 인기 Key는 캐시가 비는 순간 자체가 없어진다.
**한계:** 인기 Key 목록을 관리해야 한다.

---

## 4단계: 최종 적용 조합

모든 전략을 한꺼번에 넣는 건 과하다. 상황에 맞게 조합했다.

```
[1차 방어] TTL 지터 — 모든 Key에 기본 적용
[2차 방어] 분산 락 — 캐시 미스 시 DB 동시 조회 방지
[3차 방어] 인기 Key 사전 워밍 — 트래픽 많은 Key는 만료 자체를 방지
[선택 적용] 논리적 만료 — 응답 지연에 극도로 민감한 API에 적용
```

적용 후 주기적 DB 부하 급증이 사라졌고, 응답 시간도 안정적으로 유지되었다.

---

## 헷갈렸던 포인트

### Q: 단순히 TTL을 길게 잡으면 해결되지 않나?

TTL을 늘리면 Stampede 발생 빈도는 줄지만, 데이터 신선도(freshness)가 떨어진다. 그리고 TTL이 아무리 길어도 결국 만료되는 순간은 오기 때문에, 근본적인 해결은 아니다. 지터 + 락 조합이 더 효과적이다.

### Q: Cache Stampede와 Cache Avalanche의 차이는?

- **Cache Stampede**: 특정 인기 Key 몇 개가 동시에 만료되어 해당 Key에 대한 요청이 DB로 몰리는 현상.
- **Cache Avalanche**: Redis 서버 장애, 메모리 부족 등으로 **대량의 캐시가 한꺼번에 증발**하는 현상. 규모가 훨씬 크고 복구도 어렵다.

이 문서에서 다룬 문제는 Stampede에 해당한다.

### Q: 분산 락을 쓰면 성능이 오히려 떨어지지 않나?

락 대기 시간(~50ms)은 DB 과부하로 인한 수 초 지연보다 훨씬 짧다. 또한 락은 **캐시 미스가 발생한 순간에만** 작동하므로, 평소에는 아무런 오버헤드가 없다.

### Q: 논리적 만료에서 stale 데이터를 반환하는 게 괜찮은가?

서비스 특성에 따라 다르다. 상품 추천 목록이나 배너 설정 같은 데이터는 수초 정도의 지연이 허용되는 경우가 많다. 결제 금액이나 재고 수량 같은 데이터에는 이 전략을 쓰면 안 된다.

---

## 참고 자료

- [Cache Stampede - Wikipedia](https://en.wikipedia.org/wiki/Cache_stampede)
- [Redis Documentation - Distributed Locks (Redlock)](https://redis.io/docs/manual/patterns/distributed-locks/)
