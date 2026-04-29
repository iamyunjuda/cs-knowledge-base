---
title: JVM 아키텍처 심화 — ClassLoader·Class 파일 구조·Execution Engine
parent: Java / JVM
nav_order: 3
tags: [JVM, ClassLoader, ParentDelegation, Linking, Verification, Preparation, Resolution, Initialization, Bytecode, javap, ExecutionEngine, JIT, JNI]
description: "클래스 파일 생성부터 JVM이 바이트코드를 기계어로 실행하는 과정까지, ClassLoader 3단계(Loading/Linking/Initialization), Class 파일 구조, Execution Engine 내부, JNI를 정리합니다."
---

# JVM 아키텍처 심화 — ClassLoader·Class 파일 구조·Execution Engine

> 이 문서는 [gngsn.tistory.com/252](https://gngsn.tistory.com/252) 글을 기반으로 정리했다. JVM 전체 동작 흐름이나 버전별 변화는 [jvm-internals.md](jvm-internals.md), 메모리 세부 구조는 [jvm-memory-structure.md](jvm-memory-structure.md)를 참고.

## 핵심 정리

### JVM을 구성하는 세 축

JVM은 크게 세 개의 서브시스템으로 나뉜다.

```
┌────────────────────────────────────────────────────────────┐
│                          JVM                                │
├────────────────────────────────────────────────────────────┤
│  1. ClassLoader Subsystem                                   │
│     ├─ Loading                                              │
│     ├─ Linking (Verification → Preparation → Resolution)    │
│     └─ Initialization                                       │
├────────────────────────────────────────────────────────────┤
│  2. Runtime Data Area                                       │
│     Method Area / Heap / Stack / PC Register / Native Stack │
├────────────────────────────────────────────────────────────┤
│  3. Execution Engine                                        │
│     Interpreter + JIT Compiler + Garbage Collector          │
│                        ↕                                    │
│                     JNI → Native Method Libraries           │
└────────────────────────────────────────────────────────────┘
```

전체 흐름: `.java → javac → .class → ClassLoader가 로딩·링킹·초기화 → Runtime Data Area에 배치 → Execution Engine이 실행`.

---

### JDK / JRE / JVM 관계

| 용어 | 포함 범위 | 용도 |
|------|----------|------|
| **JDK** | JRE + 개발 도구(javac, jar, javadoc 등) | 개발용 |
| **JRE** | JVM + 핵심 라이브러리 패키지 | 실행용 |
| **JVM** | 바이트코드 해석·실행 엔진 | 런타임 |

JVM은 "추상 규격(스펙)"이면서 동시에 "구체적 구현(HotSpot, OpenJ9 등)"이자 "프로세스로 돌아가는 런타임 인스턴스"라는 세 가지 얼굴을 갖는다.

---

### JDK 8 → JDK 9: 모듈 시스템 도입

```
JDK 8:  rt.jar (약 60MB, monolithic)
         └─ 모든 핵심 클래스가 한 덩어리
JDK 9+: 73개 .jmod 모듈로 분할
         └─ module-info.java 로 공개 범위 제어
```

| 항목 | JDK 8 | JDK 9 |
|------|-------|-------|
| 구조 | Monolithic | 73개 모듈 |
| 핵심 라이브러리 | rt.jar | .jmod |
| 내부 API 접근 | 가능 | 강한 캡슐화 |
| ClassLoader 계층 | Bootstrap / Extension / Application | Bootstrap / **Platform** / Application |

---

### Class 파일 — 바이트코드의 실체

`.class` 파일은 JVM 바이트코드와 메타데이터로 이루어진 바이너리다. 구조는 대략:

```
ClassFile {
    u4 magic;              // 0xCAFEBABE
    u2 minor_version;
    u2 major_version;
    u2 constant_pool_count;
    cp_info constant_pool[];
    u2 access_flags;
    u2 this_class;
    u2 super_class;
    u2 interfaces_count;
    u2 interfaces[];
    fields_info fields[];
    method_info methods[];
    attribute_info attributes[];
}
```

`javap -c` 로 디스어셈블하면 "virtual machine assembly language" 형태로 볼 수 있다.

형식: `<index> <opcode> [<operand>] [<comment>]`

```
public static void main(java.lang.String[]);
  0: iconst_0       // int 상수 0을 operand stack에 push
  1: istore_1       // 지역 변수 1번 슬롯에 저장 (int i = 0)
  2: iload_1        // 지역 변수 1번을 다시 스택에 로드
  ...
```

- **iconst_0**: 스택에 상수 0 push (i-prefix = int)
- **istore_1**: 로컬 변수 테이블 1번에 저장
- **iload_1**: 로컬 변수 1번을 스택에 로드
- **if_icmpgt**: 두 int 비교 후 분기
- **iinc**: 로컬 변수 증가 (i++)

---

### ClassLoader Subsystem — 3단계

#### 1단계 Loading — 바이너리를 메모리로

FQCN(Fully Qualified Class Name)으로 `.class` 파일을 찾아 Method Area에 적재한다.

**Parent Delegation Model (부모 위임 모델)**

```
클래스 로드 요청
      ↓
Application ClassLoader  ──→ 부모에게 먼저 위임
      ↓
Platform ClassLoader    ──→ 부모에게 먼저 위임
      ↓
Bootstrap ClassLoader   ──→ 못 찾으면 자식에게 "네가 찾아봐"
      ↓
(자식이 자기 범위에서 탐색)
```

**왜 부모부터?** 핵심 클래스(`java.lang.Object` 같은)를 애플리케이션이 임의로 가로채지 못하게 하는 보안 장치다.

| 계층 | JDK 8 | JDK 9+ | 담당 |
|------|-------|--------|------|
| Bootstrap | rt.jar | java.base 등 핵심 모듈 | 가장 루트, 네이티브 구현 |
| Extension / Platform | JRE/lib/ext | Java SE 플랫폼 모듈 | 확장/플랫폼 클래스 |
| Application | classpath | classpath | 개발자 코드 |

#### 2단계 Linking — 검증·준비·해석

**(1) Verification**
- `.class` 파일 포맷이 스펙에 맞는지, 바이트코드가 유효한지 검증
- 조작된/손상된 클래스 파일을 막는 **보안 게이트**
- 실패 시 `VerifyError`

**(2) Preparation**
- static 변수 슬롯을 **기본값**으로 초기화
  - `int → 0`, `long → 0L`, `boolean → false`, 참조 타입 → `null`
- **아직 개발자가 지정한 값은 할당되지 않는다**

```java
private static final boolean enabled = true;
// Preparation 단계에서는 enabled == false (기본값)
// Initialization 단계에서 비로소 true로 바뀜
```

**(3) Resolution**
- 상수 풀의 **심볼릭 레퍼런스**(이름 기반) → **다이렉트 레퍼런스**(메모리 주소/오프셋)로 변환
- 예: `Math.random()` 문자열 심볼 → 실제 메소드 포인터

#### 3단계 Initialization — 진짜 값 할당

- static 변수에 개발자가 작성한 초기값 할당
- static 블록 실행
- 내부적으로 컴파일러가 합성한 `<clinit>()` 메소드가 돌아감

**초기화가 트리거되는 6가지 상황:**
1. `new`로 인스턴스 생성
2. static 메소드 호출
3. static 필드에 값 할당 (또는 non-final static 필드 읽기)
4. 서브클래스 초기화 (부모 초기화도 연쇄 트리거)
5. Reflection API 사용
6. JVM 시작 시 지정된 main 클래스 로드

---

### Execution Engine — 바이트코드를 실행한다

#### Interpreter

- 바이트코드를 **한 줄씩** 기계어로 번역·실행
- 시작은 빠르지만, 같은 코드를 반복 실행할 때도 매번 다시 번역해서 누적 비용이 크다

#### JIT Compiler

- **반복되는 핫스팟 코드**를 감지해 한 번에 네이티브 코드로 컴파일·캐싱
- 이후 호출부터는 컴파일된 네이티브 코드를 직접 실행

**JIT 내부 구성:**
1. **Intermediate Code Generator**: 바이트코드 → 내부 IR
2. **Code Optimizer**: IR 최적화 (인라이닝, dead code 제거 등)
3. **Target Code Generator**: IR → 네이티브 기계어
4. **Profiler**: 실행 통계로 "핫한 메소드"를 식별

**예시 — 인터프리터 vs JIT**

```java
int sum = 10;
for (int i = 0; i <= 10; i++) {
    sum += i;
}
```

- **Interpreter**: 매 반복마다 `sum`을 메모리에서 읽고 쓰기 → 반복 비용 큼
- **JIT**: `sum`을 레지스터(또는 PC 주변)에 로컬 복사 → 루프 끝난 뒤 한 번에 메모리 기록

#### Garbage Collector

- 사용되지 않는 힙 객체를 자동 회수하는 데몬 스레드
- 기본 동작: **Mark** (도달 가능성 표시) → **Sweep** (미표시 객체 제거) (+ Compact)

| GC | 플래그 | 특징 |
|----|--------|------|
| Serial GC | `-XX:+UseSerialGC` | 단일 스레드, 작은 앱 |
| Parallel GC | `-XX:+UseParallelGC` | 멀티 스레드, throughput 지향 |
| G1 GC | `-XX:+UseG1GC` | Region 기반, 4GB+ 힙 기본값 |
| ZGC | `-XX:+UseZGC` | 사실상 sub-ms pause, 대용량 힙 |

**주의:** `System.gc()` 명시 호출은 Full GC + STW를 유도해 전체 트랜잭션이 멈춘다. 피해야 한다.

---

### JNI — Java Native Interface

C/C++ 같은 네이티브 코드를 호출하기 위한 브릿지.

```java
public class NativeExample {
    static { System.loadLibrary("nativeLib"); }
    public native void someMethod();
}
```

- Native Method Stack이 네이티브 호출 프레임을 관리
- 라이브러리는 `.dll` (Windows) / `.so` (Linux) / `.dylib` (macOS) 형태
- 대표 예: JDK 내부의 `java.io`, `java.net`, `sun.misc.Unsafe` 상당수

---

### 주요 JVM 에러

| 에러 | 시점 | 원인 |
|------|------|------|
| `ClassNotFoundException` | 런타임 (checked) | `Class.forName`·`loadClass` 시 클래스 정의를 못 찾음 |
| `NoClassDefFoundError` | 런타임 (unchecked) | 컴파일 시 존재했지만 런타임에 사라짐 |
| `OutOfMemoryError` | 런타임 | Heap·Metaspace·Direct Memory 고갈 |
| `StackOverflowError` | 런타임 | Stack Frame 계속 쌓임 (무한 재귀 등) |
| `VerifyError` | 링킹 Verification | 바이트코드가 스펙 위반 |

---

## 헷갈렸던 포인트

### Q1. `ClassNotFoundException`과 `NoClassDefFoundError`는 같은 거 아니야?

비슷해 보이지만 **발생 주체와 시점이 다르다**.

- **ClassNotFoundException**: `Class.forName()`, `ClassLoader.loadClass()`, `Class.forName("...")`를 **직접 호출**했을 때 해당 클래스를 찾을 수 없으면 발생. checked exception이라 `catch`로 처리.
- **NoClassDefFoundError**: **컴파일은 성공**했는데 JVM이 런타임에 `new`나 static 참조로 클래스를 로드하려다 찾지 못할 때. Error 계열이라 보통 복구 불가.

전형적 시나리오:
- 빌드엔 있었는데 배포에서 jar가 빠짐 → `NoClassDefFoundError`
- 플러그인 식으로 리플렉션 로드하는데 클래스 없음 → `ClassNotFoundException`

---

### Q2. `private static final boolean enabled = true;` 는 언제 `true`가 되나?

컴파일 타임 상수(constant expression)로 보이지만 **실행 시점 분리**가 있다.

1. **Preparation**: `enabled = false` (boolean 기본값)
2. **Initialization**: `<clinit>`에서 `enabled = true`로 대입

다만 `static final` + **컴파일 타임 상수**라면 컴파일러가 호출부에 값 자체를 인라인해 넣기도 한다 (상수 풀 `ConstantValue` 어트리뷰트). 이 경우 호출부에서는 초기화 순서와 무관하게 `true`로 보이지만, 정의 클래스 자체의 static 필드 슬롯은 여전히 위 순서를 따른다.

---

### Q3. Parent Delegation이면 부모가 먼저 클래스를 "로드"하는 거 아니야?

정확히는 **"탐색 우선권"이 부모에게 있다**는 뜻. 순서는:

1. 자식 로더가 요청 받음
2. **부모에게 먼저 "너가 로드해 봐" 위임**
3. 부모가 못 찾으면 자식이 자기 범위에서 탐색

결과적으로 `java.lang.String` 같은 클래스는 항상 Bootstrap이 로드하게 된다 — 애플리케이션이 같은 FQCN을 들고 와도 Bootstrap이 먼저 로드한 버전이 이기기 때문.

---

### Q4. Interpreter와 JIT는 둘 중 하나만 쓰는 거야?

아니다. HotSpot JVM은 **둘 다 항상 함께** 쓴다.

- 기동 직후: 모든 메소드는 인터프리터로 실행 (빠른 시작)
- 실행하면서 프로파일러가 호출 횟수·루프 횟수를 기록
- 임계치(기본 10,000) 넘으면 C1/C2 JIT로 컴파일해 네이티브 코드로 교체
- 이후 해당 메소드는 네이티브 코드로 실행

이걸 체계화한 게 Tiered Compilation (Java 7+). 자세히는 [jvm-internals.md](jvm-internals.md) 참고.

---

### Q5. `<clinit>()` 과 `<init>()` 은 뭐가 다른가?

- **`<init>()`**: 인스턴스 생성자. `new`마다 호출. 각 생성자별로 만들어짐.
- **`<clinit>()`**: **클래스 초기화자**. 클래스당 단 한 번, 최초 사용 시점에 호출. static 블록과 static 필드 초기화식을 모아서 컴파일러가 합성.

```java
public class Foo {
    static int x = 1;             // <clinit>의 일부
    static { System.out.println(x); } // <clinit>의 일부
    int y = 2;                    // <init>의 일부
    public Foo() { System.out.println(y); } // <init>의 일부
}
```

JVM은 `<clinit>` 실행을 암묵적으로 **동기화**한다 — 멀티스레드 환경에서 클래스 초기화가 두 번 돌지 않음. (하지만 `<clinit>` 안에서 다른 스레드 기다리면 초기화 데드락 가능 — 유명 함정)

---

### Q6. 클래스 로더를 커스텀으로 만드는 건 언제 필요할까?

일반적인 애플리케이션 코드에서는 거의 필요 없다. 하지만 다음 경우엔 필수:

- **WAS/플러그인 아키텍처** (Tomcat, OSGi): 웹앱/번들마다 격리된 클래스 네임스페이스
- **핫 리로딩** (Spring DevTools): 코드 바뀌면 새 클래스로더로 재로드
- **암호화된 jar / 원격 로딩**: 정의 바이트를 복호화/다운로드 후 `defineClass`
- **바이트코드 주입**: APM, AOP (바이트코드 생성 후 로드)

이때 **Parent Delegation을 지킬지 깰지**가 핵심 설계 포인트. Tomcat은 일부러 WebappClassLoader에서 우선순위를 뒤집어 `/WEB-INF/classes`를 먼저 본다 (웹앱이 자체 라이브러리 버전을 쓸 수 있도록).

---

## 참고 자료

- [JVM Architecture — gngsn.tistory.com](https://gngsn.tistory.com/252) (이 문서의 원출처)
- [JVM Specification (Oracle)](https://docs.oracle.com/javase/specs/jvms/se17/html/)
- [The Java® Virtual Machine Specification — Chapter 5. Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html)
- [jvm-internals.md](jvm-internals.md) — JVM 실행 모델 언어별 비교, Tiered Compilation, 버전별 변화
- [jvm-memory-structure.md](jvm-memory-structure.md) — Heap 세대별 구조, Metaspace, String Pool, GC 상세
