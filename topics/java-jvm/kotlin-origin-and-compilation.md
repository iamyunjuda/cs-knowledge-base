# 코틀린은 왜 등장했나, 그리고 자바를 거쳐 컴파일되는가?

## 핵심 정리

### 1. 코틀린 등장 배경 (Why Kotlin?)

#### JetBrains의 자가 발화
- **만든 곳**: JetBrains (IntelliJ IDEA, PyCharm, WebStorm 등을 만드는 IDE 회사)
- **시기**: 2010년 사내 프로젝트 시작 → 2011년 공개 → 2016년 1.0 → 2017년 Google이 Android 공식 언어로 채택 → 2019년 Google이 "Kotlin-first" 선언
- **이름**: 러시아 상트페테르부르크 인근 코틀린(Kotlin) 섬에서 따옴 (자바 섬에서 따온 Java처럼)

JetBrains는 자사 IDE를 **수백만 라인 자바 코드**로 개발하고 있었다. 그러다 보니 자바의 한계가 매일 체감되었다:

| 자바의 문제 | 매일 마주치는 고통 |
|------------|-----------------|
| Verbosity (장황함) | `getter/setter`, `equals/hashCode/toString` 보일러플레이트 |
| NullPointerException | 운영 환경에서 가장 자주 터지는 예외 (Tony Hoare가 "10억 달러짜리 실수"라 부른 것) |
| Checked Exception | `try-catch` 강제, Stream API에서 람다와 충돌 |
| 함수형 빈약함 | Java 8 이전엔 람다도 없음, 이후도 컬렉션 API가 빈약 |
| 타입 추론 부재 | `Map<String, List<UserDto>> users = new HashMap<>();` 같은 반복 |
| 변경 가능성 디폴트 | `final` 키워드를 일일이 붙여야 불변 |

#### 왜 Scala나 Groovy가 아니었나?
- **Scala**: 강력하지만 너무 복잡(고급 타입 시스템, implicit), 컴파일 속도가 매우 느림 → 대규모 코드베이스에 부적합
- **Groovy**: 동적 타입 기반이라 런타임 안정성 부족, 정적 컴파일 모드도 한계
- **Clojure**: Lisp 계열로 패러다임 자체가 다름

JetBrains는 "**자바와 100% 호환되면서, 자바보다 명확히 더 좋은 정적 타입 언어**"를 원했다. 그 결과가 코틀린이다.

#### 코틀린의 주요 개선점
```kotlin
// Null 안전성 (컴파일 타임에 NPE 방지)
val name: String = null      // 컴파일 에러
val name: String? = null     // OK, ?로 명시

// 데이터 클래스 (한 줄로 equals/hashCode/toString/copy 자동 생성)
data class User(val id: Long, val name: String)

// 확장 함수 (기존 클래스에 메서드 추가)
fun String.lastChar(): Char = this[length - 1]

// 스마트 캐스트 (타입 체크 후 자동 캐스트)
if (obj is String) {
    println(obj.length)  // 캐스팅 없이 String 메서드 사용
}

// 코루틴 (suspend 함수, 구조적 동시성)
suspend fun fetch(): Data = withContext(Dispatchers.IO) { ... }
```

---

### 2. 컴파일 과정 — 가장 흔한 오해 정정

#### ❌ 흔한 오해
```
Kotlin (.kt) → Java (.java) → 바이트코드 (.class) → JVM 실행
                ↑ 이 단계가 있다고 착각
```

#### ✅ 실제 동작
```
Kotlin (.kt) → kotlinc (코틀린 컴파일러) → 바이트코드 (.class) → JVM 실행
Java   (.java) → javac (자바 컴파일러)   → 바이트코드 (.class) → JVM 실행
```

**코틀린은 자바 소스 코드를 거치지 않는다.** `kotlinc`라는 별도의 컴파일러가 `.kt` 파일을 직접 JVM 바이트코드(`.class`)로 변환한다. 자바와 코틀린은 같은 출력물(바이트코드)을 만드는, **서로 다른 입구**일 뿐이다.

#### 왜 이런 오해가 생기나?
1. **IntelliJ의 "Show Kotlin Bytecode → Decompile"** 기능: 코틀린이 생성한 바이트코드를 사람이 읽기 쉽게 자바로 "역컴파일"해서 보여준다. 이건 **디버깅 도구**일 뿐, 실제 컴파일 경로가 아니다.
2. **Kotlin/JS, Kotlin/Native**: 코틀린은 멀티플랫폼이라 JS(자바스크립트)나 네이티브 바이너리로 컴파일되는 백엔드도 있다. 하지만 JVM 백엔드는 자바를 거치지 않는다.
3. **자바와의 100% 상호운용성**: 같은 프로젝트에서 .kt와 .java를 섞어 쓸 수 있어 "자바로 변환되나?"라고 추측하기 쉽다.

#### 컴파일 흐름 상세
```
┌─────────────┐
│  Main.kt    │
└──────┬──────┘
       │ kotlinc
       ▼
┌─────────────────────────────────────────┐
│ 1. Lexer/Parser  → AST                  │
│ 2. Resolver      → 심볼/타입 해석        │
│ 3. Type Checker  → null 안전성, 추론     │
│ 4. IR (Intermediate Representation)     │
│ 5. Backend       → JVM 바이트코드 생성   │
└──────┬──────────────────────────────────┘
       ▼
┌─────────────┐
│  Main.class │  ← javac 출력물과 같은 포맷
└──────┬──────┘
       │ 클래스 로더
       ▼
┌──────────────────────┐
│  JVM (HotSpot)       │
│  - Interpreter       │
│  - JIT (C1/C2)       │
│  - GC                │
└──────────────────────┘
```

---

### 3. 성능 비교 — 코틀린이 자바보다 느린가?

#### 런타임 성능: 거의 동일
- 같은 JVM에서, 같은 바이트코드 명령어를, 같은 JIT 컴파일러(HotSpot C1/C2)가 실행한다.
- 똑같은 알고리즘을 짜면 **벤치마크상 측정 가능한 차이가 거의 없다** (보통 ±2~3% 노이즈 수준).

#### 코틀린이 추가하는 작은 오버헤드
```kotlin
fun greet(name: String) { println("Hello $name") }
```
바이트코드에는 다음이 추가된다:
```
INVOKESTATIC kotlin/jvm/internal/Intrinsics.checkNotNullParameter
```
→ null이 들어오면 즉시 `IllegalArgumentException`을 던지는 **null 안전성 가드**. 함수 호출 한 번에 nanosecond 단위라 실무 성능엔 영향 없음.

#### 코틀린이 오히려 더 빠를 수 있는 경우
- **`inline` 함수**: 자바 람다는 `Function` 객체를 생성하지만, 코틀린 `inline fun`은 호출부에 코드를 펼쳐 넣어 객체 할당이 없다.
  ```kotlin
  inline fun measure(block: () -> Unit) { ... }  // 람다 객체 생성 X
  ```
- **데이터 클래스**: 자바 record와 비슷하게 컴파일러가 최적화된 `equals/hashCode`를 생성.
- **`when` 표현식**: tableswitch/lookupswitch 바이트코드로 최적 컴파일.

#### 컴파일 속도: 코틀린이 더 느림
- `kotlinc`는 `javac`보다 **2~3배 느린 게 일반적**. 타입 추론과 null 분석 때문.
- 해결책: **Incremental Compilation** (변경된 파일만 재컴파일), **Kotlin K2 컴파일러** (2.0부터 기본, 기존 대비 최대 2배 빠름).

#### 스타트업/메모리: 거의 동일
- 같은 JVM 위에서 도는 같은 `.class` 파일이라 JVM 워밍업, GC 패턴, Metaspace 사용량이 자바와 거의 같다.
- 다만 `kotlin-stdlib.jar`(약 1.6MB)이 클래스패스에 추가되어 초기 클래스 로딩이 미세하게 더 있다.

---

### 4. 바이트코드 레벨에서 본 코틀린의 트릭

#### Null 안전성
```kotlin
fun foo(s: String) { println(s.length) }
```
↓ 바이트코드 (역컴파일하면 자바로 이렇게 보임)
```java
public static void foo(String s) {
    Intrinsics.checkNotNullParameter(s, "s");  // 컴파일러가 자동 삽입
    System.out.println(s.length());
}
```

#### 데이터 클래스
```kotlin
data class User(val id: Long, val name: String)
```
↓ JVM은 이런 클래스를 생성 (개념적으로)
```java
public final class User {
    private final long id;
    private final String name;
    public long getId() { ... }
    public String getName() { ... }
    public boolean equals(Object o) { ... }   // 자동 생성
    public int hashCode() { ... }             // 자동 생성
    public String toString() { ... }          // 자동 생성
    public User copy(long id, String name) { ... }  // 자동 생성
    public User component1() { ... }          // 구조 분해용
    public User component2() { ... }
}
```

#### 코루틴 (suspend 함수)
```kotlin
suspend fun fetch(): String = withContext(Dispatchers.IO) { ... }
```
↓ 바이트코드 레벨에서는 **CPS(Continuation-Passing Style) 변환**으로 상태 머신이 된다
```java
public static Object fetch(Continuation<? super String> $cont) {
    // label로 분기되는 거대한 switch 문 (상태 머신)
    // 호출자에게 Continuation을 통해 결과를 비동기 전달
}
```
→ 스레드를 점유하지 않고 함수 호출 한 번에 일시정지/재개 가능. 자바의 `CompletableFuture`보다 가볍다.

#### 확장 함수
```kotlin
fun String.lastChar(): Char = this[length - 1]
```
↓ 정적 메서드로 컴파일됨
```java
public static char lastChar(String $this) {
    return $this.charAt($this.length() - 1);
}
```
→ 클래스를 진짜로 수정하는 게 아니라 **첫 인자로 receiver를 받는 static 메서드**일 뿐.

---

## 헷갈렸던 포인트

### Q1. 코틀린은 자바로 변환된 다음 컴파일되는 거 아니야? 그럼 단계가 늘어나서 느린 거 아닌가?
**A. 아니다.** 코틀린은 `kotlinc` 컴파일러가 `.kt` → `.class` (JVM 바이트코드)로 **직접** 변환한다. 자바를 거치는 단계는 **없다**. 그래서 런타임 성능은 자바와 사실상 동일하다.

오해의 출처는 IntelliJ의 "Decompile to Java" 기능인데, 이건 **생성된 바이트코드를 사람이 읽기 쉽게** 자바 코드로 역변환해서 보여주는 디버깅 도구일 뿐이다. 실제 빌드 파이프라인에는 자바 단계가 없다.

### Q2. 그럼 어떤 점은 진짜로 자바보다 느릴 수 있나?
**A. 컴파일 속도가 느리다.** 런타임이 아니라 빌드 타임이다.
- 코틀린은 타입 추론, null flow 분석, 스마트 캐스트 등 컴파일러가 할 일이 많아 `javac`보다 2~3배 느리다.
- 다만 incremental compilation과 K2 컴파일러(2.0+)로 많이 개선됐다.
- 런타임/메모리/스타트업은 자바와 사실상 차이 없다.

### Q3. 코틀린은 무조건 JVM 위에서만 도는 건가?
**A. 아니다.** 코틀린은 멀티플랫폼 언어다:
- **Kotlin/JVM**: 가장 일반적, JVM 바이트코드 생성 (Android, Spring 등)
- **Kotlin/JS**: 자바스크립트로 컴파일 (웹 프론트)
- **Kotlin/Native**: LLVM 기반 네이티브 바이너리로 컴파일 (iOS, 임베디드)
- **Kotlin/Wasm**: WebAssembly로 컴파일 (실험적)

같은 `.kt` 소스를 여러 백엔드로 빌드할 수 있는 게 Kotlin Multiplatform(KMP)의 핵심이다.

### Q4. 코틀린은 자바 라이브러리를 그대로 쓸 수 있나? 반대도 되나?
**A. 양방향 모두 거의 100% 호환된다.**
- **코틀린에서 자바 사용**: 그냥 import해서 쓰면 된다. Spring, Hibernate, Apache Commons 다 그대로 사용 가능.
- **자바에서 코틀린 사용**: 가능. 다만 코틀린의 일부 기능(`suspend`, 확장 함수, default parameter 등)은 자바에서 호출할 때 다르게 보인다.
  - `suspend fun foo()` → 자바에선 `foo(Continuation cont)`로 보임
  - 확장 함수 → static 메서드로 호출
  - default parameter → `@JvmOverloads` 안 붙이면 풀 시그니처만 보임

### Q5. 그러면 코틀린이 자바보다 무조건 좋은 거 아닌가?
**A. 트레이드오프가 있다.**
- **장점**: null 안전성, 간결함, 코루틴, 함수형 지원, 확장 함수, 데이터 클래스
- **단점**:
  - 컴파일 속도가 느림 (대규모 모듈에서 체감)
  - 학습 곡선 (특히 코루틴, scope function, generic variance)
  - 자바 신버전이 따라잡고 있음 (record, sealed, pattern matching, virtual thread)
  - 일부 자바 라이브러리는 코틀린 친화적이지 않음 (Lombok과는 충돌)
  - 디버깅 시 코루틴 스택 트레이스가 끊김
- 대규모 자바 코드베이스가 있다면 점진적 마이그레이션이 현실적. 신규 프로젝트는 코틀린이 우세.

### Q6. 그럼 자바와 코틀린의 .class 파일은 똑같은가? 구분이 가능한가?
**A. 거의 같지만 구분은 가능하다.**
- 둘 다 같은 JVM 바이트코드 명세를 따른다.
- 다만 코틀린이 생성한 클래스에는 `@kotlin.Metadata` 어노테이션이 붙어 있어, Kotlin 리플렉션이 원본 시그니처(null 정보, generic variance 등)를 복원할 수 있다.
- `kotlin-stdlib.jar`의 클래스를 참조하면 코틀린 코드라는 강한 신호다.

---

## 참고 자료
- [Kotlin 공식 문서 — Compiler reference](https://kotlinlang.org/docs/compiler-reference.html)
- [Kotlin K2 Compiler 소개](https://blog.jetbrains.com/kotlin/2024/04/k2-compiler-performance-benchmarks-and-how-to-measure-them-on-your-projects/)
- [Why JetBrains needs Kotlin (2011 announcement)](https://blog.jetbrains.com/kotlin/2011/07/hello-world/)
- [Kotlin Bytecode and Decompilation — IntelliJ Guide](https://kotlinlang.org/docs/tools-bytecode-and-decompilation.html)
- [Tony Hoare — Null References: The Billion Dollar Mistake](https://www.infoq.com/presentations/Null-References-The-Billion-Dollar-Mistake-Tony-Hoare/)
- 관련 문서: [JVM 동작 원리](jvm-internals.md), [JVM 아키텍처 심화](jvm-architecture-deep-dive.md), [Thread vs CompletableFuture vs Coroutine 비교](thread-future-coroutine-comparison.md)
