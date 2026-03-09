# 언어별 비동기 구현 방식 — 내부 동작 원리부터 프레임워크 주의점까지

## 핵심 정리

비동기(Asynchronous) 프로그래밍은 **I/O 대기 시간 동안 다른 작업을 수행**하여 처리량을 높이는 기법이다. 그런데 각 언어마다 비동기를 구현하는 **철학과 메커니즘이 완전히 다르다.** 이 문서는 주요 언어별로 비동기가 어떻게 작동하는지 내부 구조부터 분석하고, 프레임워크에서 사용할 때 반드시 주의해야 할 포인트를 정리한다.

```
비동기의 본질적 목표:
  "CPU가 I/O를 기다리며 놀지 않게 하자"

방법은 언어마다 다르다:
  JavaScript → 싱글 스레드 + Event Loop + Callback/Promise
  Python     → 싱글 스레드 + Event Loop + Coroutine (asyncio)
  Java       → 멀티 스레드 + CompletableFuture / Virtual Thread
  Kotlin     → Coroutine + Structured Concurrency
  Go         → Goroutine + Channel (CSP 모델)
  C#         → async/await + Task + SynchronizationContext
  Rust       → async/await + Future + Runtime (tokio)
```

## 헷갈렸던 포인트

---

### Q1: JavaScript/Node.js — 싱글 스레드인데 어떻게 비동기가 되나?

JavaScript는 **싱글 스레드 + Event Loop** 모델이다. 비동기 I/O는 OS(epoll/kqueue)나 libuv의 스레드풀에 위임한다.

```
[JavaScript 비동기 구조]

 ┌──────────────────────────────────────────────────┐
 │              V8 Engine (싱글 스레드)                │
 │  Call Stack: main() → fetchData() → ...           │
 │                                                    │
 │  Microtask Queue: [Promise.then(), queueMicrotask] │
 │  Macrotask Queue: [setTimeout, setInterval, I/O]   │
 └──────────────┬─────────────────────────────────────┘
                │ Event Loop
                ▼
 ┌──────────────────────────────┐
 │         libuv (C 라이브러리)   │
 │  ┌─────────────────────────┐ │
 │  │ Thread Pool (기본 4개)   │ │  ← DNS, 파일 I/O 등 blocking 작업
 │  └─────────────────────────┘ │
 │  ┌─────────────────────────┐ │
 │  │ OS 비동기 I/O            │ │  ← 네트워크 I/O (epoll/kqueue)
 │  │ (epoll/kqueue/IOCP)     │ │
 │  └─────────────────────────┘ │
 └──────────────────────────────┘
```

**Event Loop 동작 순서:**

```
while (true) {
    1. Call Stack이 비었는지 확인
    2. Microtask Queue 전부 처리 (Promise.then, async/await 후속)
    3. Macrotask Queue에서 하나 꺼내 실행 (setTimeout, I/O callback)
    4. 필요하면 렌더링 (브라우저 환경)
    5. 반복
}
```

**async/await의 내부 변환:**

```javascript
// 개발자가 작성한 코드
async function getUser(id) {
    const response = await fetch(`/api/user/${id}`);  // 여기서 중단
    const data = await response.json();                // 여기서 중단
    return data;
}

// 엔진이 내부적으로 처리하는 방식 (개념적)
function getUser(id) {
    return fetch(`/api/user/${id}`)
        .then(response => response.json())
        .then(data => data);
}
```

**핵심:** `await`는 함수 실행을 **일시 중단**하고 **Event Loop에 제어권을 반환**한다. Promise가 resolve되면 Microtask Queue를 통해 재개된다.

**Node.js에서의 비동기 I/O 경로:**

```
네트워크 I/O (HTTP, TCP, DNS lookup 결과):
  → OS의 epoll/kqueue으로 직접 non-blocking 처리 (스레드풀 안 거침)

파일 I/O, DNS lookup, crypto:
  → libuv의 스레드풀(기본 4개)에서 처리
  → UV_THREADPOOL_SIZE 환경변수로 확장 가능 (최대 1024)

네트워크 I/O는 진짜 non-blocking이지만,
파일 I/O는 내부적으로 멀티스레드다! (겉으로는 비동기 API)
```

---

### Q2: Python — asyncio는 어떻게 작동하나?

Python도 **GIL(Global Interpreter Lock)** 때문에 사실상 싱글 스레드다. `asyncio`는 **Coroutine + Event Loop** 기반이다.

```
[Python asyncio 구조]

 ┌────────────────────────────────────────┐
 │          asyncio Event Loop             │
 │                                         │
 │  ┌─ Coroutine: fetch_data()            │
 │  │   → await aiohttp.get() (I/O 대기)  │
 │  │   → Event Loop에 제어권 반환         │
 │  │                                      │
 │  ├─ Coroutine: process_data()          │
 │  │   → 실행 중...                       │
 │  │                                      │
 │  └─ Coroutine: save_result()           │
 │      → await로 중단 중                  │
 └────────────────────────────────────────┘
          │
          ▼ I/O 멀티플렉싱
    OS selector (epoll/kqueue)
```

**Python Coroutine의 내부 동작:**

```python
import asyncio

# async def로 Coroutine 정의
async def fetch_user(user_id: int) -> dict:
    print(f"Fetching user {user_id}")
    # await: 여기서 Event Loop에 제어권 반환
    await asyncio.sleep(1)  # 네트워크 대기 시뮬레이션
    return {"id": user_id, "name": "Alice"}

# 동시 실행
async def main():
    # gather: 여러 Coroutine을 동시에 실행
    users = await asyncio.gather(
        fetch_user(1),
        fetch_user(2),
        fetch_user(3),
    )
    # 3초가 아니라 1초만에 완료! (동시에 대기했으므로)
    print(users)

asyncio.run(main())
```

**Python 비동기의 내부 메커니즘 — Generator 기반:**

```python
# Python의 async/await는 실제로 Generator의 확장이다
# 내부적으로 이런 식으로 동작한다:

# 1. async def → Coroutine 객체 생성
# 2. await → yield와 유사 (제어권 반환)
# 3. Event Loop가 I/O 완료 시 .send()로 재개

# Generator 기반 Coroutine (구 방식, 이해를 위해)
@asyncio.coroutine
def old_style():
    result = yield from some_future  # yield로 제어권 반환
    return result

# 현대 방식 (동일한 동작)
async def new_style():
    result = await some_future       # 내부적으로 yield
    return result
```

**GIL과 asyncio의 관계:**

```
Q: GIL이 있는데 asyncio가 의미가 있나?
A: 있다! GIL은 "CPU 연산"의 병렬 실행을 막을 뿐이다.

  CPU-bound 작업: GIL 때문에 asyncio로 이득 없음
                  → multiprocessing 또는 ProcessPoolExecutor 사용

  I/O-bound 작업: I/O 대기 중에는 GIL이 해제됨
                  → asyncio가 효과적!
                  → 수천 개의 네트워크 요청을 동시에 대기 가능

  실제 동작:
  Coroutine A: HTTP 요청 → await → GIL 해제 → OS가 I/O 처리
  Coroutine B: GIL 획득 → 실행 → HTTP 요청 → await → GIL 해제
  Coroutine C: GIL 획득 → 실행 → ...
```

---

### Q3: Go — Goroutine은 어떻게 수백만 개가 가능한가?

Go는 **CSP(Communicating Sequential Processes)** 모델을 채택했다. Goroutine + Channel이 핵심이다.

```
[Go 런타임 스케줄러 — GMP 모델]

  G = Goroutine (경량 스레드, 초기 스택 2KB → 동적 확장)
  M = Machine (OS 스레드)
  P = Processor (논리적 프로세서, GOMAXPROCS 개수)

  ┌───────────────────────────────────────────────┐
  │  P0                    P1                      │
  │  ┌──────────┐          ┌──────────┐            │
  │  │ Local Q  │          │ Local Q  │            │
  │  │ [G1][G2] │          │ [G4][G5] │            │
  │  └────┬─────┘          └────┬─────┘            │
  │       │                     │                   │
  │       ▼                     ▼                   │
  │    M0 (OS Thread)       M1 (OS Thread)         │
  │    현재 실행: G3         현재 실행: G6           │
  │                                                 │
  │  Global Queue: [G7, G8, G9, ...]               │
  └───────────────────────────────────────────────┘
```

**Goroutine이 I/O를 만나면:**

```go
func fetchData(url string) ([]byte, error) {
    // 이 코드는 동기처럼 보이지만, Go 런타임이 알아서 비동기로 처리한다!
    resp, err := http.Get(url)  // ← blocking처럼 보이지만...
    if err != nil {
        return nil, err
    }
    defer resp.Body.Close()
    return io.ReadAll(resp.Body)
}

func main() {
    // Goroutine 10만 개 생성 — 문제없다!
    for i := 0; i < 100_000; i++ {
        go fetchData("https://api.example.com/data")
    }
}
```

**내부 동작:**

```
Goroutine G1: http.Get() 호출
  → Go 런타임: "I/O 작업이네? G1을 파킹(park)하고 OS에 등록"
  → netpoller (epoll 기반): 소켓 이벤트 감시
  → M0은 G1을 빼고 다음 Goroutine(G2) 실행
  → ... 응답 도착 → netpoller가 감지 → G1을 다시 실행 큐에 넣음

개발자는 그냥 "동기 코드"를 쓰면 된다.
Go 런타임이 내부적으로 non-blocking I/O + 스케줄링을 처리한다.
```

**Go의 비동기 철학 — "동시성을 숨기지 않되, 복잡성을 숨긴다":**

```
JavaScript: callback → Promise → async/await (패턴이 진화)
Python:     threading → asyncio → async/await (별도 생태계)
Go:         처음부터 goroutine + channel (언어에 내장)

Go의 접근법:
  - async/await 키워드가 없다 (필요 없다)
  - 모든 I/O가 내부적으로 non-blocking
  - 개발자는 그냥 동기 코드를 쓴다
  - "함수 색칠(function coloring)" 문제가 없다

함수 색칠 문제란?
  Python/JS: async 함수는 async 함수에서만 호출 가능
             → 코드가 "async"와 "sync"로 나뉨
  Go:        그런 구분이 없다. 모든 함수가 동일하게 동작
```

**Channel을 통한 Goroutine 간 통신:**

```go
// "메모리를 공유하여 통신하지 말고, 통신하여 메모리를 공유하라"
// — Go 격언

func producer(ch chan<- int) {
    for i := 0; i < 10; i++ {
        ch <- i  // Channel에 데이터 전송 (꽉 차면 대기)
    }
    close(ch)
}

func consumer(ch <-chan int) {
    for val := range ch {  // Channel에서 데이터 수신
        fmt.Println(val)
    }
}

func main() {
    ch := make(chan int, 5)  // 버퍼 크기 5인 Channel
    go producer(ch)
    consumer(ch)
}
```

---

### Q4: C# — async/await의 원조, SynchronizationContext란?

C#은 **async/await 패턴의 원조**이며 (2012, C# 5.0), JavaScript/Python/Rust 등에 영향을 줬다.

```
[C# async/await 구조]

  ┌─────────────────────────────────────────────┐
  │  Task: .NET의 비동기 작업 단위               │
  │  - Task<T>: 결과가 있는 비동기 작업          │
  │  - ValueTask<T>: 할당 최적화 버전            │
  │                                              │
  │  async/await:                                │
  │  - 컴파일러가 State Machine으로 변환          │
  │  - Kotlin Coroutine과 동일한 원리!           │
  └─────────────────────────────────────────────┘
```

```csharp
// C# async/await
public async Task<User> GetUserAsync(int id)
{
    // await: 여기서 State Machine의 state 전환
    var response = await httpClient.GetAsync($"/api/user/{id}");
    var json = await response.Content.ReadAsStringAsync();
    return JsonSerializer.Deserialize<User>(json);
}

// 컴파일러가 생성하는 State Machine (개념적)
struct GetUserAsync_StateMachine : IAsyncStateMachine
{
    public int state;
    public AsyncTaskMethodBuilder<User> builder;
    private HttpResponseMessage response;

    void MoveNext()
    {
        switch (state)
        {
            case 0:
                state = 1;
                var awaiter = httpClient.GetAsync(url).GetAwaiter();
                if (!awaiter.IsCompleted)
                {
                    builder.AwaitUnsafeOnCompleted(ref awaiter, ref this);
                    return;  // 여기서 반환! 스레드 해방
                }
                goto case 1;
            case 1:
                response = awaiter.GetResult();
                state = 2;
                // ... 다음 await
        }
    }
}
```

**SynchronizationContext — C# 특유의 개념:**

```
SynchronizationContext란?
  "await 이후의 코드를 어떤 스레드에서 실행할지 결정하는 메커니즘"

┌────────────────────────────────────────────────────────┐
│ 환경별 SynchronizationContext                           │
│                                                         │
│ WPF/WinForms:                                           │
│   await 전: UI 스레드에서 실행                            │
│   await 후: 다시 UI 스레드로 복귀! (SyncContext가 보장)    │
│   → UI 업데이트가 자연스럽게 동작                          │
│                                                         │
│ ASP.NET Core:                                           │
│   SynchronizationContext 없음                            │
│   await 후: ThreadPool의 아무 스레드에서 재개              │
│   → 성능이 더 좋음 (스레드 고정이 없으므로)                 │
│                                                         │
│ Console App:                                            │
│   SynchronizationContext 없음                            │
│   await 후: ThreadPool의 아무 스레드에서 재개              │
└────────────────────────────────────────────────────────┘
```

---

### Q5: Rust — Zero-cost async는 어떻게 가능한가?

Rust의 async는 **런타임 비용이 0**에 가깝다. 컴파일 타임에 State Machine으로 변환되고, 런타임은 사용자가 선택한다.

```
[Rust async 구조]

  ┌─────────────────────────────────────────────┐
  │  Future trait: Rust의 비동기 기본 단위        │
  │                                              │
  │  trait Future {                              │
  │      type Output;                            │
  │      fn poll(self, cx: &mut Context)         │
  │          -> Poll<Self::Output>;              │
  │  }                                           │
  │                                              │
  │  Poll::Ready(value) → 완료                   │
  │  Poll::Pending      → 아직 미완료             │
  └─────────────────────────────────────────────┘
          │
          ▼ 런타임이 poll을 호출
  ┌─────────────────────────────────────────────┐
  │  Runtime (사용자 선택):                       │
  │  - tokio: 가장 널리 사용, 멀티스레드           │
  │  - async-std: std 라이브러리 미러링            │
  │  - smol: 경량                                │
  └─────────────────────────────────────────────┘
```

```rust
// Rust async/await
async fn fetch_user(id: u32) -> Result<User, Error> {
    // await: Future를 poll하여 완료될 때까지 대기
    let response = reqwest::get(format!("/api/user/{}", id)).await?;
    let user: User = response.json().await?;
    Ok(user)
}

// 컴파일러가 생성하는 State Machine (개념적)
enum FetchUser {
    State0 { id: u32 },
    State1 { response_future: ResponseFuture },
    State2 { json_future: JsonFuture },
    Complete,
}

impl Future for FetchUser {
    type Output = Result<User, Error>;

    fn poll(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<Self::Output> {
        loop {
            match self.state {
                State0 => {
                    // HTTP 요청 시작, State1으로 전환
                    let fut = reqwest::get(...);
                    self.state = State1 { response_future: fut };
                }
                State1 => {
                    // response_future를 poll
                    match self.response_future.poll(cx) {
                        Poll::Pending => return Poll::Pending,  // 아직 안 됨
                        Poll::Ready(resp) => {
                            self.state = State2 { ... };
                        }
                    }
                }
                // ...
            }
        }
    }
}
```

**Rust async가 "Zero-cost"인 이유:**

```
Java/C#: 비동기 작업 → 힙에 객체 할당 (Task, CompletableFuture)
         → GC가 수거해야 함

Go:      Goroutine → 런타임이 스택 관리 → 런타임 오버헤드

Rust:    async fn → 컴파일 타임에 enum(State Machine)으로 변환
         → 크기가 컴파일 타임에 결정됨
         → 힙 할당 없이 스택에 배치 가능
         → GC 없음, 런타임 오버헤드 최소

단, 런타임(tokio 등)은 별도로 존재. "Zero-cost"는
"추상화 자체의 비용이 0"이라는 뜻이지 "모든 비용이 0"은 아니다.
```

---

### Q6: Java — CompletableFuture부터 Virtual Thread까지의 진화

> Java의 비동기 진화는 기존 문서 [비동기 처리 방식 비교](async-processing-comparison.md)에서 Spring 생태계 중심으로 다루었다. 여기서는 **언어 레벨의 비동기 메커니즘**에 집중한다.

```
[Java 비동기 진화 타임라인]

Java 1.0 (1996): Thread, Runnable
Java 5   (2004): ExecutorService, Future, Callable
Java 7   (2011): ForkJoinPool (work-stealing)
Java 8   (2014): CompletableFuture (콜백 체이닝)
Java 9   (2017): Flow API (Reactive Streams)
Java 19  (2022): Virtual Thread (Preview)
Java 21  (2023): Virtual Thread (정식, JEP 444)
```

**CompletableFuture — Java의 Promise:**

```java
// CompletableFuture 체이닝 (JavaScript Promise.then과 유사)
CompletableFuture<OrderDetail> result =
    CompletableFuture.supplyAsync(() -> orderRepo.findById(id))       // 비동기 실행
        .thenCompose(order ->
            CompletableFuture.supplyAsync(() -> userRepo.findById(order.getUserId()))
                .thenApply(user -> new OrderDetail(order, user))      // 결합
        );

// 여러 작업 병렬 실행
CompletableFuture<Void> all = CompletableFuture.allOf(
    fetchInventory(itemId),
    fetchPricing(itemId),
    fetchReviews(itemId)
);
```

**Virtual Thread 내부 동작 — Continuation:**

```
[Virtual Thread의 핵심: Continuation]

Continuation = "실행 상태를 저장/복원할 수 있는 코드 블록"

VThread-1 실행 중:
  → JDBC query 호출 (blocking I/O)
  → JVM이 감지: "이건 blocking이네"
  → Continuation 저장: 스택 프레임을 힙에 복사
  → Carrier Thread(Platform Thread)에서 VThread-1 분리 (unmount)
  → Carrier Thread가 VThread-2 실행 시작

  ... DB 응답 도착 ...

  → VThread-1의 Continuation 복원: 힙에서 스택으로 복사
  → Carrier Thread에 VThread-1 다시 올림 (mount)
  → 이어서 실행

핵심: 개발자가 작성한 코드는 "blocking"이지만,
     JVM이 내부적으로 non-blocking으로 전환한다.
```

---

### Q7: Kotlin Coroutine — 구조화된 동시성(Structured Concurrency)

> Kotlin Coroutine의 suspend 메커니즘은 기존 문서 [비동기 처리 방식 비교](async-processing-comparison.md)에서 다루었다. 여기서는 **Structured Concurrency**에 집중한다.

```kotlin
// Structured Concurrency: 부모-자식 관계로 Coroutine 관리
suspend fun loadDashboard(): Dashboard = coroutineScope {
    // 두 작업이 동시에 실행된다
    val userDeferred = async { userService.getUser(userId) }
    val ordersDeferred = async { orderService.getOrders(userId) }

    // 둘 다 완료될 때까지 대기
    Dashboard(
        user = userDeferred.await(),
        orders = ordersDeferred.await()
    )
    // ★ 만약 ordersDeferred에서 예외 발생 → userDeferred도 자동 취소!
}
```

```
[Structured Concurrency가 해결하는 문제]

❌ 구조화되지 않은 동시성 (Go, Java Thread):
  func handle() {
      go fetchA()   // fire and forget!
      go fetchB()   // 에러나도 누가 처리?
  }
  // fetchA가 실패해도 fetchB는 계속 실행...
  // handle()이 끝나도 fetchA, fetchB는 어딘가에서 실행 중...

✅ Structured Concurrency (Kotlin Coroutine):
  suspend fun handle() = coroutineScope {
      val a = async { fetchA() }   // 이 scope에 바인딩
      val b = async { fetchB() }   // 이 scope에 바인딩
  }
  // a가 실패하면 b도 자동 취소
  // scope가 끝나면 모든 자식 Coroutine 완료 보장
  // → "Coroutine 누수"가 구조적으로 불가능
```

---

### Q8: 전체 언어별 비교표

| 구분 | JavaScript | Python | Go | Java (21+) | Kotlin | C# | Rust |
|------|-----------|--------|-----|-----------|--------|-----|------|
| **비동기 단위** | Promise | Coroutine | Goroutine | Virtual Thread | Coroutine | Task | Future |
| **키워드** | async/await | async/await | 없음 (go 키워드) | 없음 | suspend | async/await | async/await |
| **스레드 모델** | 싱글 스레드 | 싱글 스레드 (GIL) | M:N (GMP) | M:N (VThread:Carrier) | M:N (Coroutine:Thread) | M:N (Task:ThreadPool) | M:N (Future:Runtime) |
| **런타임** | V8/libuv | asyncio Event Loop | Go Runtime | JVM | kotlinx.coroutines | CLR | tokio/async-std |
| **I/O 처리** | libuv 위임 | OS selector | netpoller (epoll) | Carrier Thread 전환 | suspend + Dispatcher | I/O Completion Port | mio (epoll 추상화) |
| **함수 색칠** | 있음 | 있음 | **없음** | **없음** | 있음 (suspend) | 있음 | 있음 |
| **취소 메커니즘** | AbortController | Task.cancel() | context.Context | Thread.interrupt() | Job.cancel() | CancellationToken | Drop trait |
| **동시성 수** | 수만 (I/O) | 수만 (I/O) | 수백만 | 수백만 | 수백만 | 수만~수십만 | 수백만 |
| **GC** | 있음 | 있음 | 있음 | 있음 | 있음 | 있음 | **없음** |

---

### Q9: 프레임워크에서 비동기 사용 시 반드시 주의할 포인트

#### 1. JavaScript — Node.js / Express / NestJS

```javascript
// ❌ Event Loop 블로킹 — 절대 하면 안 되는 패턴
app.get('/hash', (req, res) => {
    // CPU-intensive 작업이 Event Loop를 막는다!
    const hash = crypto.pbkdf2Sync(password, salt, 100000, 64, 'sha512');
    res.json({ hash });
    // 이 작업이 끝날 때까지 모든 요청이 대기!
});

// ✅ Worker Thread 또는 비동기 버전 사용
app.get('/hash', async (req, res) => {
    const hash = await crypto.pbkdf2(password, salt, 100000, 64, 'sha512');
    res.json({ hash });
});
```

```
Node.js 주의 포인트 정리:
├─ CPU-intensive 작업을 메인 스레드에서 하지 말 것
│  → Worker Threads, child_process, 또는 별도 서비스로 분리
├─ 파일 I/O는 내부적으로 스레드풀(기본 4개) 사용
│  → 동시 파일 작업이 많으면 UV_THREADPOOL_SIZE 증가
├─ unhandledRejection을 반드시 처리할 것
│  → 안 하면 Node.js 프로세스 크래시 (v15+)
├─ async 함수에서 try/catch를 빠뜨리지 말 것
│  → Express에서는 에러 미들웨어로 안 잡힘 (express-async-errors 필요)
└─ Promise.all vs Promise.allSettled 구분
   → all: 하나라도 실패하면 전체 reject
   → allSettled: 모두 완료 후 각각의 결과 반환
```

#### 2. Python — Django / FastAPI / Flask

```python
# ❌ FastAPI에서 동기 ORM 사용
@app.get("/users/{user_id}")
async def get_user(user_id: int):
    # SQLAlchemy 동기 쿼리가 Event Loop를 블로킹!
    user = db.query(User).filter(User.id == user_id).first()
    return user

# ✅ 방법 1: async ORM 사용 (SQLAlchemy 2.0+)
@app.get("/users/{user_id}")
async def get_user(user_id: int):
    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        return result.scalar_one()

# ✅ 방법 2: 동기 함수는 def로 선언 (FastAPI가 자동으로 스레드풀에서 실행)
@app.get("/users/{user_id}")
def get_user(user_id: int):  # async 없이 def만 사용!
    user = db.query(User).filter(User.id == user_id).first()
    return user  # FastAPI가 threadpool에서 실행해줌
```

```
Python 프레임워크 주의 포인트 정리:
├─ Django: 기본적으로 동기. async view는 Django 4.1+
│  ├─ Django ORM은 여전히 동기 → sync_to_async() 래퍼 필요
│  └─ ASGI 서버(uvicorn/daphne) 사용 필수 (WSGI로는 비동기 불가)
├─ FastAPI:
│  ├─ async def → Event Loop에서 직접 실행 (blocking 금지!)
│  ├─ def (sync) → 자동으로 외부 스레드풀에서 실행 (blocking OK)
│  ├─ 이 차이를 모르면 성능 재앙 발생
│  └─ Depends()도 async/sync 구분 주의
├─ async와 sync 라이브러리를 섞지 말 것
│  ├─ requests (동기) → httpx (비동기) 또는 aiohttp
│  ├─ psycopg2 (동기) → asyncpg (비동기)
│  └─ 동기 라이브러리를 async 함수에서 쓰면 Event Loop 블로킹!
└─ asyncio.run()은 중첩 불가
   → 이미 Event Loop 안에서 asyncio.run() 호출하면 에러
   → nest_asyncio 패키지로 우회 가능하지만 권장하지 않음
```

#### 3. Go — Gin / Echo / Fiber

```go
// Go는 비동기가 언어에 내장되어 있어서 "실수"가 적지만, 다른 함정이 있다

// ❌ Goroutine 누수
func handler(c *gin.Context) {
    ch := make(chan string)
    go func() {
        result := callExternalAPI()  // 10초 걸림
        ch <- result
    }()

    select {
    case result := <-ch:
        c.JSON(200, result)
    case <-time.After(3 * time.Second):
        c.JSON(504, "timeout")
        // Goroutine은 아직 살아있다! 10초 후에 ch에 쓰려고 시도 → 영원히 블록!
    }
}

// ✅ context로 취소 전파
func handler(c *gin.Context) {
    ctx, cancel := context.WithTimeout(c.Request.Context(), 3*time.Second)
    defer cancel()

    result, err := callExternalAPIWithContext(ctx)
    if err != nil {
        c.JSON(504, "timeout")
        return
    }
    c.JSON(200, result)
}
```

```
Go 프레임워크 주의 포인트 정리:
├─ Goroutine 누수 (가장 흔한 실수)
│  ├─ unbuffered channel에 아무도 수신하지 않으면 영원히 블록
│  ├─ context.Context를 반드시 전파하여 취소 가능하게
│  └─ runtime.NumGoroutine()으로 모니터링
├─ 공유 자원 접근 시 Race Condition
│  ├─ go test -race 플래그로 반드시 테스트
│  ├─ sync.Mutex 또는 channel로 보호
│  └─ sync.Map은 read-heavy 패턴에서만 유리
├─ HTTP Handler에서 Goroutine 주의
│  ├─ Handler가 반환되면 ResponseWriter 사용 불가
│  └─ 백그라운드 작업은 별도 channel/worker로 분리
└─ panic은 해당 Goroutine만 죽인다
   ├─ 다른 Goroutine에 에러 전파가 자동으로 안 됨
   └─ recover()로 명시적 처리 필요
```

#### 4. Java — Spring Boot (MVC / WebFlux)

```java
// ❌ Virtual Thread에서의 synchronized 블록 (Pinning 문제)
public class BadService {
    private final Object lock = new Object();

    public void process() {
        synchronized (lock) {    // ← Virtual Thread가 Carrier Thread에 고정됨!
            db.query("...");     //    이 동안 Carrier Thread를 다른 VThread가 못 씀
        }
    }
}

// ✅ ReentrantLock 사용
public class GoodService {
    private final ReentrantLock lock = new ReentrantLock();

    public void process() {
        lock.lock();
        try {
            db.query("...");     // Virtual Thread가 자유롭게 unmount 가능
        } finally {
            lock.unlock();
        }
    }
}
```

```
Java/Spring 프레임워크 주의 포인트 정리:
├─ Spring MVC + Virtual Thread (Java 21+):
│  ├─ spring.threads.virtual.enabled=true 한 줄이면 적용
│  ├─ synchronized 대신 ReentrantLock 사용 (Pinning 방지)
│  ├─ ThreadLocal 남용 주의 (VThread가 수백만 개면 메모리 문제)
│  └─ 기존 blocking 코드 그대로 사용 가능 (최대 장점)
├─ Spring WebFlux:
│  ├─ Event Loop 스레드에서 절대 blocking 금지
│  ├─ JDBC/JPA 사용 불가 → R2DBC 필요
│  ├─ Schedulers.boundedElastic()으로 blocking 격리 가능
│  ├─ publishOn/subscribeOn 차이 이해 필수
│  └─ 디버깅이 어려움 → Hooks.onOperatorDebug() 활성화
├─ CompletableFuture 주의:
│  ├─ 기본 스레드풀은 ForkJoinPool.commonPool()
│  │  → CPU 코어 수 - 1개뿐. I/O 작업에 부적합!
│  ├─ 반드시 별도 Executor 지정: supplyAsync(() -> ..., myExecutor)
│  └─ 예외 처리: exceptionally() 또는 handle()로 반드시 처리
└─ @Async 주의:
   ├─ @EnableAsync + TaskExecutor Bean 설정 필수
   ├─ 같은 클래스 내부 호출은 동작 안 함 (프록시 문제)
   └─ 반환값은 Future/CompletableFuture여야 결과 받을 수 있음
```

#### 5. C# — ASP.NET Core

```csharp
// ❌ async void — 예외를 잡을 수 없다
public async void HandleRequest()  // void! 위험!
{
    await SomethingAsync();  // 여기서 예외 → 프로세스 크래시!
}

// ✅ async Task — 반드시 Task 반환
public async Task HandleRequestAsync()
{
    await SomethingAsync();  // 예외를 호출자가 처리 가능
}

// ❌ .Result 또는 .Wait() — 데드락 위험
public IActionResult Get()
{
    var user = GetUserAsync().Result;  // 데드락!
    return Ok(user);
}

// ✅ async를 끝까지 전파
public async Task<IActionResult> Get()
{
    var user = await GetUserAsync();
    return Ok(user);
}
```

```
C# / ASP.NET Core 주의 포인트 정리:
├─ async void는 이벤트 핸들러 외에 절대 사용 금지
│  → 예외가 SynchronizationContext로 전파되어 프로세스 크래시
├─ .Result / .Wait() 호출 금지 (async all the way)
│  → SynchronizationContext가 있는 환경에서 데드락
│  → ASP.NET Core는 SyncContext가 없어서 데드락은 안 나지만 스레드 낭비
├─ ConfigureAwait(false) — 라이브러리 코드에서 사용 권장
│  → SynchronizationContext 캡처를 건너뜀
│  → ASP.NET Core에서는 SyncContext가 없어서 효과 없지만, 습관적으로 사용
├─ CancellationToken을 항상 전파할 것
│  → Controller: async Task<IActionResult> Get(CancellationToken ct)
│  → 클라이언트가 연결 끊으면 자동 취소
└─ IAsyncDisposable 구현 시 DisposeAsync() 사용
   → await using var conn = new SqlConnection(...);
```

#### 6. Rust — Actix-web / Axum

```rust
// ❌ async 함수 안에서 blocking 작업
async fn handler() -> impl IntoResponse {
    // 이러면 tokio의 worker thread가 블로킹된다!
    let data = std::fs::read_to_string("large_file.txt").unwrap();
    Json(data)
}

// ✅ spawn_blocking으로 분리
async fn handler() -> impl IntoResponse {
    let data = tokio::task::spawn_blocking(|| {
        std::fs::read_to_string("large_file.txt").unwrap()
    }).await.unwrap();
    Json(data)
}
```

```
Rust 프레임워크 주의 포인트 정리:
├─ tokio 런타임 스레드에서 blocking 작업 금지
│  ├─ std::fs → tokio::fs 사용
│  ├─ 불가피하면 tokio::task::spawn_blocking() 사용
│  └─ blocking 스레드풀과 async 스레드풀은 별도로 관리됨
├─ Send + 'static 제약
│  ├─ 멀티스레드 런타임에서 Future는 스레드간 이동 가능해야 함
│  ├─ Rc, RefCell 사용 불가 → Arc, Mutex 사용
│  └─ 이 제약 때문에 컴파일 에러가 자주 발생 (학습 곡선)
├─ async trait 제약 (Rust 1.75+ 안정화)
│  └─ 이전에는 #[async_trait] 매크로 필요 → Box<dyn Future> 할당
├─ 런타임 중첩 금지
│  ├─ tokio::runtime::Runtime 안에서 또 Runtime 생성 불가
│  └─ #[tokio::main]이 이미 런타임을 생성함
└─ select! 매크로 사용 시 취소 안전성(cancel safety) 확인
   └─ select!에서 탈락한 Future는 즉시 drop됨 → 부분 완료 상태 주의
```

---

### Q10: 리액티브 프로그래밍(Reactive Programming)이란? — 비동기와 뭐가 다른가?

**리액티브는 비동기의 상위 개념이다.** 비동기는 "기다리지 않고 다른 일을 한다"에 초점이 있고, 리액티브는 **"데이터 흐름에 반응한다"**에 초점이 있다.

```
[비동기 vs 리액티브]

비동기(Async):
  "작업을 요청하고 나중에 결과를 받는다"
  → 단일 값: Future, Promise, Task
  → 요청-응답 패턴

리액티브(Reactive):
  "데이터 스트림을 구독하고, 데이터가 올 때마다 반응한다"
  → 0~N개의 값이 시간에 따라 흘러온다
  → 데이터 흐름(Stream) 패턴
  → Backpressure: 소비자가 처리 속도를 제어

비유:
  비동기 = 택배를 주문하고 알림 올 때까지 다른 일 하기
  리액티브 = 유튜브 채널 구독 → 새 영상이 올라올 때마다 알림 → 반응
```

#### Reactive Streams 표준 (Java 9 Flow API)

```java
// Reactive Streams의 4가지 핵심 인터페이스
public interface Publisher<T> {
    void subscribe(Subscriber<? super T> s);
}

public interface Subscriber<T> {
    void onSubscribe(Subscription s);   // 구독 시작
    void onNext(T t);                   // 데이터 수신
    void onError(Throwable t);          // 에러 발생
    void onComplete();                  // 스트림 완료
}

public interface Subscription {
    void request(long n);    // n개의 데이터를 요청 (Backpressure!)
    void cancel();           // 구독 취소
}

public interface Processor<T, R> extends Subscriber<T>, Publisher<R> {
    // 중간 처리자: 데이터를 받아서 변환 후 내보냄
}
```

```
[Backpressure가 왜 중요한가?]

Producer: 초당 10,000개 이벤트 생성
Consumer: 초당 1,000개만 처리 가능

Backpressure 없으면:
  → Consumer 버퍼 무한 증가 → OutOfMemoryError!

Backpressure 있으면:
  Consumer: "나 1,000개만 보내줘" (request(1000))
  Producer: "알겠어, 1,000개만 보냄" (나머지는 대기/폐기)

전략:
  ├─ Buffer: 일정량까지 버퍼에 저장
  ├─ Drop: 처리 못하면 폐기
  ├─ Latest: 가장 최신 값만 유지
  └─ Error: 처리 못하면 에러 발생
```

#### 언어별 리액티브 구현체

```
[리액티브 생태계]

Java:
  ├─ RxJava (ReactiveX): Observable/Flowable
  ├─ Project Reactor: Mono/Flux (Spring WebFlux의 기반)
  └─ Java 9 Flow API: 표준 인터페이스 (구현체가 아님)

JavaScript/TypeScript:
  ├─ RxJS: Observable 기반 (Angular의 핵심)
  └─ Node.js Streams: Readable/Writable/Transform

Python:
  ├─ RxPY: ReactiveX의 Python 구현
  └─ asyncio Streams: StreamReader/StreamWriter

C#:
  ├─ Rx.NET: ReactiveX의 원조 (.NET 출신)
  ├─ System.Reactive: 공식 라이브러리
  └─ IAsyncEnumerable (C# 8+): async 스트림

Go:
  └─ Channel이 사실상 리액티브 스트림 역할
     → 별도 라이브러리 거의 안 씀

Rust:
  ├─ tokio-stream: Stream trait 기반
  └─ futures::Stream: 비동기 Iterator와 유사

Kotlin:
  └─ Flow: Kotlin Coroutine 기반 Cold Stream
     → SharedFlow/StateFlow: Hot Stream
```

#### Project Reactor (Spring WebFlux) — Mono와 Flux

```java
// Mono: 0~1개 값 (비동기 단일 결과)
Mono<User> user = userRepository.findById(id);

// Flux: 0~N개 값 (비동기 스트림)
Flux<Order> orders = orderRepository.findByUserId(userId);

// 실전 예시: 사용자와 주문을 동시에 조회 후 조합
Mono<Dashboard> dashboard = Mono.zip(
    userRepo.findById(userId),                    // 비동기 조회 1
    orderRepo.findByUserId(userId).collectList(), // 비동기 조회 2 (리스트로 수집)
    (user, orders) -> new Dashboard(user, orders) // 결과 조합
);

// 스트림 처리 예시: 실시간 이벤트 처리
Flux<Event> events = eventSource.stream()
    .filter(e -> e.getType() == EventType.ORDER)  // 주문 이벤트만
    .buffer(Duration.ofSeconds(5))                 // 5초 단위로 묶기
    .flatMap(batch -> processBatch(batch))         // 배치 처리
    .onErrorResume(e -> {                          // 에러 시 빈 스트림
        log.error("Error", e);
        return Flux.empty();
    });
```

#### RxJS (Angular/프론트엔드) — Observable

```typescript
// Angular에서 HTTP 요청 (Observable 기반)
@Injectable()
export class UserService {
    getUser(id: number): Observable<User> {
        return this.http.get<User>(`/api/users/${id}`).pipe(
            retry(3),                        // 실패 시 3번 재시도
            catchError(this.handleError)     // 에러 처리
        );
    }
}

// 실시간 검색 (리액티브의 진가가 발휘되는 순간)
this.searchInput.valueChanges.pipe(
    debounceTime(300),           // 300ms 입력 멈추면
    distinctUntilChanged(),       // 같은 값이면 무시
    switchMap(term =>             // 이전 요청 취소 + 새 요청
        this.searchService.search(term)
    )
).subscribe(results => {
    this.results = results;
});
// → debounce + 자동 취소 + 에러 처리가 단 몇 줄로 완성
```

#### Kotlin Flow — Cold Stream과 Hot Stream

```kotlin
// Cold Stream: 구독할 때마다 새로 시작
fun fetchOrders(userId: Long): Flow<Order> = flow {
    val orders = orderRepository.findByUserId(userId)
    orders.forEach { order ->
        emit(order)  // 하나씩 방출
    }
}

// 사용 (collect 시점에 실행됨)
fetchOrders(userId)
    .filter { it.status == Status.PENDING }
    .map { it.toDto() }
    .collect { dto -> println(dto) }

// Hot Stream: 구독 여부와 관계없이 데이터 발행
// SharedFlow: 여러 구독자에게 동시 방출
private val _events = MutableSharedFlow<Event>()
val events: SharedFlow<Event> = _events.asSharedFlow()

// StateFlow: 항상 최신 값을 유지 (LiveData 대체)
private val _uiState = MutableStateFlow(UiState.Loading)
val uiState: StateFlow<UiState> = _uiState.asStateFlow()
```

```
[Cold vs Hot Stream 차이]

Cold Stream (Flow, Flux, Observable):
  ├─ 구독자가 있어야 실행 시작
  ├─ 각 구독자가 독립적인 데이터 스트림을 받음
  └─ 예: DB 쿼리, HTTP 요청

Hot Stream (SharedFlow, Subject, ConnectableObservable):
  ├─ 구독 여부와 관계없이 데이터 발행
  ├─ 모든 구독자가 같은 데이터를 공유
  └─ 예: 주식 시세, 센서 데이터, UI 이벤트
```

#### 리액티브가 빛나는 순간과 그렇지 않은 순간

```
리액티브가 적합한 상황:
  ✅ 실시간 데이터 스트림 (WebSocket, SSE, 주식 시세)
  ✅ 복잡한 이벤트 조합 (검색 자동완성, 폼 유효성 검사)
  ✅ 고동시성 I/O (수만 연결 처리, API Gateway)
  ✅ Backpressure가 필요한 상황 (로그 수집, 메시지 큐)

리액티브가 과한 상황:
  ❌ 단순 CRUD API (Spring MVC + JPA가 더 간단)
  ❌ CPU-bound 작업 (리액티브의 이점이 없음)
  ❌ 팀원 대부분이 리액티브 경험이 없을 때
  ❌ 기존 blocking 라이브러리에 의존적일 때

"리액티브는 은탄환이 아니다.
 복잡성이 증가하는 만큼 확실한 이유가 있어야 한다."
```

---

### Q11: 비동기의 공통 함정 — 언어에 관계없이 조심할 것

```
[모든 언어에 공통되는 비동기 주의 사항]

1. 함수 색칠(Function Coloring) 문제
   ├─ async 함수 → async 함수에서만 호출 가능 (JS, Python, Rust, C#, Kotlin)
   ├─ sync 함수에서 async를 호출하려면 별도 메커니즘 필요
   ├─ Go와 Java Virtual Thread만이 이 문제에서 자유롭다
   └─ 해결: "async all the way" 원칙 — 중간에 sync로 바꾸지 말 것

2. 에러 전파
   ├─ 비동기 에러는 잡기 어렵다 (스택트레이스가 끊김)
   ├─ JS: unhandledRejection 이벤트 리스너 필수
   ├─ Python: asyncio 디버그 모드 활성화
   ├─ Go: errgroup으로 에러 수집
   └─ 모든 언어: 비동기 에러를 명시적으로 처리하는 패턴 확립

3. 리소스 누수
   ├─ 취소되지 않은 비동기 작업이 메모리를 잡아먹음
   ├─ 타임아웃 설정 필수 (외부 API 호출)
   ├─ 취소 메커니즘 전파 (CancellationToken, context.Context, Job.cancel)
   └─ 연결 풀 관리: 비동기 환경에서 동시 연결 수 폭발 주의

4. 동시성 ≠ 병렬성
   ├─ 싱글 스레드 비동기 (JS, Python): 동시성은 있지만 병렬은 아님
   ├─ CPU-bound 작업에는 비동기가 도움 안 됨
   └─ I/O-bound: 비동기 효과적 / CPU-bound: 멀티프로세스 또는 멀티스레드

5. 디버깅의 어려움
   ├─ 비동기 코드의 스택트레이스는 의미가 축소됨
   ├─ 요청 추적: Correlation ID / Trace ID 패턴 적용
   └─ 언어별 디버깅 도구: AsyncLocal(.NET), MDC(Java), contextvars(Python)
```

## 참고 자료

- [Node.js Event Loop 공식 문서](https://nodejs.org/en/learn/asynchronous-work/event-loop-timers-and-nexttick)
- [Python asyncio 공식 문서](https://docs.python.org/3/library/asyncio.html)
- [Go Concurrency Patterns — Rob Pike](https://go.dev/talks/2012/concurrency.slide)
- [JEP 444: Virtual Threads](https://openjdk.org/jeps/444)
- [Kotlin Coroutines 공식 가이드](https://kotlinlang.org/docs/coroutines-guide.html)
- [C# Async/Await Best Practices — Stephen Cleary](https://learn.microsoft.com/en-us/archive/msdn-magazine/2013/march/async-await-best-practices-in-asynchronous-programming)
- [Tokio Tutorial (Rust)](https://tokio.rs/tokio/tutorial)
- [What Color is Your Function? — Bob Nystrom](https://journal.stuffwithstuff.com/2015/02/01/what-color-is-your-function/)
