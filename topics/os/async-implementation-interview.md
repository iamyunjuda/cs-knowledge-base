# 면접에서 "비동기를 구현해보라"고 했을 때 — 접근법과 답변 전략

## 핵심 정리

### 이 질문의 의도

면접관이 보고 싶은 것은 **완벽한 코드가 아니라**:

```
① 비동기의 본질을 이해하는가
   → "결과를 기다리지 않고 다른 일을 먼저 하는 것"

② 동기 코드와의 차이를 설명할 수 있는가
   → 왜 비동기가 필요한지, 어떤 문제를 해결하는지

③ 구현 방식의 선택지를 알고 있는가
   → Thread, Callback, Future/Promise, async/await 등

④ 트레이드오프를 인식하는가
   → 복잡성 증가, 디버깅 어려움, 예외 처리 등
```

---

### 답변 전략: 3단계로 이야기를 시작하라

#### 1단계: 먼저 문제를 정의한다 (30초)

```
"비동기가 왜 필요한지부터 말씀드리겠습니다.

동기 방식은 A 작업이 끝날 때까지 B를 못 합니다.
예를 들어 커피숍에서 커피를 주문하면,

[동기] 주문 → 커피 나올 때까지 계산대 앞에서 대기 → 다음 손님
       → 커피 만드는 3분 동안 계산대가 놀고 있음

[비동기] 주문 → 진동벨 받고 자리로 감 → 다음 손님 바로 주문
         → 커피 완성되면 진동벨 울림 → 커피 수령

핵심은 '결과를 기다리는 동안 다른 일을 할 수 있는 것'입니다."
```

**이렇게 시작하면 면접관은 "아, 개념은 알고 있구나"라고 판단한다.**

#### 2단계: 가장 단순한 구현부터 보여준다 (2~3분)

```
"가장 원시적인 방법부터 시작하겠습니다.
비동기의 핵심은 '별도의 실행 흐름에서 작업을 수행하고,
완료되면 알려주는 것'입니다."
```

##### 방법 1: Thread + Callback (가장 기본)

```java
// "비동기의 가장 기본 형태는 별도 스레드에서 실행하고
//  콜백으로 결과를 전달하는 것입니다"

interface Callback<T> {
    void onComplete(T result);
    void onError(Exception e);
}

void asyncTask(String input, Callback<String> callback) {
    new Thread(() -> {
        try {
            // 오래 걸리는 작업 (DB, 외부 API 등)
            String result = doHeavyWork(input);
            callback.onComplete(result);
        } catch (Exception e) {
            callback.onError(e);
        }
    }).start();
}

// 사용
asyncTask("data", new Callback<>() {
    public void onComplete(String result) {
        System.out.println("완료: " + result);
    }
    public void onError(Exception e) {
        System.out.println("실패: " + e.getMessage());
    }
});
System.out.println("이건 즉시 실행됨 — 기다리지 않음");
```

```
"이게 비동기의 본질입니다.
 ① 별도 스레드에서 작업 실행
 ② 결과가 나오면 콜백으로 전달
 ③ 호출자는 기다리지 않고 다음 코드 실행"
```

##### 방법 2: Future 패턴 (콜백의 진화)

```java
// "콜백의 문제는 중첩되면 읽기 어렵다는 것입니다.
//  그래서 '미래의 결과'를 객체로 표현하는 Future 패턴이 나왔습니다"

class SimpleFuture<T> {
    private T result;
    private Exception error;
    private boolean done = false;

    // 결과 설정 (작업 완료 시)
    synchronized void complete(T value) {
        this.result = value;
        this.done = true;
        notifyAll();  // 대기 중인 스레드 깨움
    }

    // 결과 가져오기 (완료될 때까지 대기)
    synchronized T get() throws Exception {
        while (!done) wait();
        if (error != null) throw error;
        return result;
    }
}

// 사용
SimpleFuture<String> future = new SimpleFuture<>();
new Thread(() -> {
    String result = doHeavyWork("data");
    future.complete(result);
}).start();

// 필요한 시점에 결과를 꺼냄
String result = future.get();  // 아직 안 끝났으면 여기서 대기
```

```
"Future는 '아직 완료되지 않은 결과의 참조'입니다.
 Java의 CompletableFuture, JS의 Promise가 이 패턴입니다."
```

#### 3단계: 발전 방향과 트레이드오프를 말한다 (1~2분)

```
"지금 보여드린 구현에는 몇 가지 문제가 있습니다.

① 스레드를 매번 생성하면 비용이 큽니다
   → 해결: Thread Pool로 스레드를 재사용

② 콜백이 중첩되면 가독성이 떨어집니다 (Callback Hell)
   → 해결: Promise/Future 체이닝, 또는 async/await 문법

③ 예외 처리가 어렵습니다 (다른 스레드에서 발생한 예외)
   → 해결: Future에 예외를 담아서 전달

④ 여러 비동기 작업의 조합이 복잡합니다
   → 해결: CompletableFuture.allOf(), Promise.all()

실무에서는 이런 문제들을 이미 해결한 프레임워크를 사용합니다.
Java면 CompletableFuture, Kotlin이면 Coroutine,
JS면 async/await를 씁니다."
```

---

### 언어별로 물어보면 이렇게 답한다

면접관이 "특정 언어로 해보세요"라고 하면:

#### Java

```java
// "Java에서는 CompletableFuture를 씁니다"
CompletableFuture<String> future = CompletableFuture
    .supplyAsync(() -> callExternalAPI())      // 다른 스레드에서 실행
    .thenApply(response -> parse(response))     // 결과 변환
    .exceptionally(ex -> "fallback");           // 예외 처리

// 또는 Java 21이면 Virtual Thread
Thread.startVirtualThread(() -> {
    String result = callExternalAPI();  // blocking이지만 경량 스레드라 OK
});
```

#### JavaScript

```javascript
// "JS에서는 Promise + async/await를 씁니다"
async function fetchData() {
    try {
        const response = await fetch('/api/data');  // 여기서 중단
        const data = await response.json();         // 여기서 중단
        return data;
    } catch (error) {
        console.error('실패:', error);
    }
}
// 내부적으로 싱글 스레드 Event Loop가 처리
```

#### Kotlin

```kotlin
// "Kotlin에서는 Coroutine을 씁니다"
suspend fun fetchData(): Data {
    val result = withContext(Dispatchers.IO) {
        callExternalAPI()  // IO 스레드에서 실행, 현재 코루틴은 중단
    }
    return parse(result)
}
```

#### Python

```python
# "Python에서는 asyncio를 씁니다"
async def fetch_data():
    async with aiohttp.ClientSession() as session:
        response = await session.get('/api/data')  # 중단점
        return await response.json()
```

---

### 면접관이 더 깊게 물어볼 수 있는 후속 질문 대비

```
Q: "스레드 없이 비동기를 구현할 수 있나요?"
A: "네. Event Loop 모델입니다. Node.js가 대표적입니다.
    싱글 스레드에서 I/O 작업을 OS에 위임하고,
    완료되면 콜백을 실행하는 방식입니다.
    내부적으로 OS의 epoll/kqueue를 사용합니다."

Q: "비동기와 멀티스레딩의 차이는 뭔가요?"
A: "멀티스레딩은 '실행 단위를 여러 개 만드는 것'이고,
    비동기는 '결과를 기다리지 않는 것'입니다.
    비동기를 멀티스레딩으로 구현할 수도 있고 (Java Thread),
    싱글 스레드에서 구현할 수도 있습니다 (Node.js Event Loop)."

Q: "비동기의 단점은 뭔가요?"
A: "① 코드 복잡성 증가 (콜백 지옥, 실행 순서 추적 어려움)
    ② 디버깅이 어려움 (스택트레이스가 끊김)
    ③ 예외 처리가 복잡함 (다른 스레드의 예외를 어떻게 받을지)
    ④ 공유 자원 접근 시 동기화 필요 (Race Condition)"

Q: "Non-blocking과 비동기는 같은 건가요?"
A: "다릅니다.
    Non-blocking: '호출이 즉시 반환된다' (대기하지 않음)
    비동기: '결과를 나중에 받는다' (콜백/Future 등으로)
    Non-blocking I/O + Event Loop = 비동기 처리의 한 구현 방식입니다."
```

---

### 면접 답변 전체 흐름 요약

```
1. 비유로 시작 (30초)
   "커피숍의 진동벨 시스템이 비동기입니다"

2. 본질 정의 (30초)
   "결과를 기다리지 않고 다른 일을 하는 것,
    결과가 나오면 알려주는 것"

3. 가장 단순한 구현 (2분)
   Thread + Callback → Future 패턴
   "별도 실행 흐름 + 결과 전달 메커니즘"

4. 발전 방향 (1분)
   Thread Pool, Promise 체이닝, async/await
   "실무에서는 프레임워크가 해결"

5. 트레이드오프 (30초)
   복잡성, 디버깅, 예외 처리
```

## 헷갈렸던 포인트

### Q1. 면접에서 완벽한 코드를 기대하는 건가?

**아니다.** IDE 없이 완벽한 코드를 치는 것을 기대하는 면접관은 드물다. 기대하는 것은:

```
✅ 면접관이 보고 싶은 것:
  - 비동기의 개념을 정확히 이해하는가
  - 왜 필요한지 설명할 수 있는가
  - 구현의 핵심 아이디어를 알고 있는가 (스레드 + 콜백/Future)
  - 트레이드오프를 인식하는가

❌ 면접관이 기대하지 않는 것:
  - 문법 완벽한 코드
  - 프레임워크 API를 외우고 있는 것
  - 라이브러리 내부 구현을 다 아는 것
```

의사코드(pseudocode)로 핵심 아이디어만 전달해도 충분하다.

### Q2. 어떤 언어로 답해야 가장 유리한가?

**본인이 가장 익숙한 언어.** 언어 제약이 없다고 했으면:

```
Java 개발자 → CompletableFuture
JS 개발자 → async/await + Promise
Kotlin 개발자 → Coroutine
Python 개발자 → asyncio

혹은 언어 무관하게 Thread + Callback으로 원리를 보여주는 것도 좋다.
"어떤 언어든 비동기의 본질은 같다"는 것을 보여줄 수 있으므로.
```

### Q3. "Event Loop로 구현하겠습니다"라고 하면 더 높은 점수를 받나?

상황에 따라 다르다:

```
Thread + Callback:
  → 가장 이해하기 쉬운 답변
  → 비동기의 본질을 직관적으로 보여줌
  → 대부분의 면접에서 이것만으로 충분

Event Loop:
  → 더 고급 답변이지만, 제대로 설명할 수 있어야 함
  → "싱글 스레드에서 I/O 멀티플렉싱으로 비동기 처리"
  → 잘못 설명하면 오히려 감점

★ 확실히 아는 범위에서 답하는 것이 가장 중요하다
```

## 참고 자료

- [Java CompletableFuture 완벽 가이드](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [MDN — Asynchronous JavaScript](https://developer.mozilla.org/en-US/docs/Learn/JavaScript/Asynchronous)
- [Kotlin Coroutines Guide](https://kotlinlang.org/docs/coroutines-guide.html)
