---
title: JVM 동작 원리 — 다른 언어와의 비교 및 버전별 변화
parent: Java / JVM
nav_order: 1
---

# JVM 동작 원리 — 다른 언어와의 비교 및 버전별 변화

## 핵심 정리

### JVM의 코드 실행 과정

Java 소스코드가 실행되기까지의 과정은 크게 3단계로 나뉜다:

```
Java 소스코드(.java)
    ↓ javac (컴파일러)
바이트코드(.class)
    ↓ Class Loader → Bytecode Verifier
JVM Runtime Data Areas에 로드
    ↓ Interpreter + JIT Compiler
기계어(Machine Code) 실행
```

1. **컴파일 단계**: `javac`가 `.java` 소스를 플랫폼 독립적인 바이트코드(`.class`)로 컴파일
2. **로딩 단계**: Class Loader가 바이트코드를 찾아 로드하고, Bytecode Verifier가 안전성 검증
3. **실행 단계**: 인터프리터가 바이트코드를 한 줄씩 실행하다가, 자주 호출되는 "핫스팟(hot spot)" 코드를 JIT 컴파일러가 기계어로 변환하여 최적화

### HotSpot JVM의 Tiered Compilation (Java 7+)

Java 7부터 기본 적용된 **Tiered Compilation**은 시작 속도와 장기 성능을 모두 잡기 위한 전략이다:

| 레벨 | 컴파일러 | 설명 |
|------|---------|------|
| 0 | 인터프리터 | 모든 메서드가 처음에는 인터프리터로 실행 |
| 1~3 | C1 (Client) | 빠르게 컴파일, 기본 최적화 적용 |
| 4 | C2 (Server) | 느리지만 고도의 최적화 적용 (인라이닝, 루프 최적화 등) |

메서드 호출 횟수와 루프 실행 횟수를 프로파일링하여, 충분히 "뜨거운" 코드만 C2로 승격시킨다.

---

## 다른 언어 실행 모델과의 비교

### C/C++ — AOT(Ahead-of-Time) 컴파일

```
소스코드(.c/.cpp) → 컴파일러(gcc/clang) → 기계어(바이너리)
```

- **직접 기계어로 컴파일**: VM 없이 OS 위에서 바로 실행
- **장점**: 시작 속도 빠름, 런타임 오버헤드 없음
- **단점**: 플랫폼마다 다시 컴파일 필요, 런타임 최적화 불가
- **JVM과의 핵심 차이**: JVM의 JIT는 런타임 프로파일 정보를 기반으로 최적화하므로, 실행 중에 C/C++ AOT보다 더 나은 최적화를 적용할 수 있는 경우가 있다 (예: 가상 메서드 인라이닝, 분기 예측 최적화)

### Python (CPython) — 인터프리터 + PVM

```
소스코드(.py) → 컴파일러 → 바이트코드(.pyc) → PVM(인터프리터) 실행
```

- **스택 기반 VM**으로 바이트코드를 한 줄씩 실행 (JVM과 유사한 구조)
- **GIL(Global Interpreter Lock)**: 멀티스레드에서도 한 번에 하나의 스레드만 바이트코드 실행 가능 → CPU 바운드 병렬 처리에 큰 제약
- **JIT 없음** (전통적으로): CPython 3.13(2024)에서 실험적 JIT 도입
- **JVM과의 핵심 차이**: JVM은 초기부터 JIT 컴파일을 통해 네이티브 수준 성능을 달성하지만, CPython은 순수 인터프리터로 동작하여 실행 속도가 느림. PyPy(대안 구현체)는 JIT를 사용

### C# / .NET (CLR) — JVM과 가장 유사

```
소스코드(.cs) → 컴파일러(Roslyn) → IL(Intermediate Language) → CLR의 JIT → 기계어
```

- **JVM과의 공통점**: 중간 언어(IL ↔ 바이트코드), JIT 컴파일, GC 관리, 값/참조 타입 구분
- **JVM과의 차이점**:
  - CLR은 메서드 **최초 호출 시 바로 JIT 컴파일** (JVM은 인터프리터로 시작 후 핫스팟만 JIT)
  - CLR의 JIT 워밍업은 JVM보다 짧음
  - .NET은 **AOT 컴파일(NativeAOT)** 도 공식 지원하여 네이티브 바이너리 생성 가능
  - CLR은 `struct`(값 타입)를 직접 지원하여 힙 할당을 줄일 수 있음 (JVM은 Project Valhalla에서 준비 중)

### Go — 네이티브 컴파일 + 경량 런타임

```
소스코드(.go) → Go 컴파일러 → 네이티브 바이너리 (런타임 내장)
```

- **AOT 컴파일**로 단일 바이너리 생성, VM 불필요
- **고루틴(goroutine)**: 스택 크기 약 2KB로 시작 (JVM 스레드는 기본 1MB) → 수십만 개 동시 생성 가능
- Go 스케줄러가 고루틴을 소수의 OS 스레드에 매핑 (M:N 스케줄링)
- **JVM과의 핵심 차이**:
  - 시작 속도: Go가 압도적으로 빠름 (JIT 워밍업 없음)
  - 장기 실행 성능: JVM의 JIT가 런타임 최적화를 적용하여 Go보다 나은 경우가 있음
  - 컨테이너 크기: Go 바이너리가 훨씬 작음 (JVM 런타임 불필요)
  - Java 21의 Virtual Thread가 Go의 고루틴과 유사한 경량 스레드 모델을 제공

### JavaScript (V8) — 다단계 JIT

```
소스코드(.js) → V8 파싱 → Ignition(인터프리터/바이트코드) → Sparkplug → Maglev → TurboFan
```

- **4단계 컴파일 파이프라인**: 코드가 "뜨거워질수록" 더 높은 수준의 최적화 적용
  - Ignition: 바이트코드 인터프리터 (빠른 시작)
  - Sparkplug: 빠른 베이스라인 컴파일
  - Maglev: 중간 수준 최적화 (2023년 도입)
  - TurboFan: 최고 수준 최적화
- **JVM과의 핵심 차이**: V8도 JVM과 유사한 티어드 컴파일을 사용하지만, 동적 타입 언어 특성상 "hidden class"와 "inline caching" 같은 추가 최적화 기법이 필요. JVM은 정적 타입 정보를 활용하여 더 공격적인 최적화 가능

### 비교 요약표

| 특성 | JVM (Java) | CLR (.NET) | CPython | Go | V8 (JS) | C/C++ |
|------|-----------|-----------|---------|-----|---------|-------|
| 컴파일 방식 | JIT (Tiered) | JIT (즉시) | 인터프리터 | AOT | JIT (4-tier) | AOT |
| 중간 표현 | 바이트코드 | IL/MSIL | 바이트코드 | 없음 | 바이트코드 | 없음 |
| VM/런타임 | JVM | CLR | PVM | 경량 런타임 | V8 엔진 | 없음 |
| GC | 다양한 선택지 | 세대별 GC | 참조 카운팅+GC | 동시 Mark&Sweep | 세대별 GC | 수동 관리 |
| 시작 속도 | 느림 (워밍업) | 보통 | 빠름 | 매우 빠름 | 빠름 | 매우 빠름 |
| 최대 실행 성능 | 매우 높음 | 높음 | 낮음 | 높음 | 높음 | 매우 높음 |
| 경량 동시성 | Virtual Thread (21+) | async/await | asyncio | goroutine | 이벤트 루프 | OS 스레드 |

---

## Java 버전별 JVM 주요 변화

### Java 1.0 ~ 1.4 — 초기 인터프리터 시대
- 순수 인터프리터 기반 실행으로 시작
- Java 1.3에서 HotSpot VM이 기본 VM으로 채택
- 초기 JIT 컴파일러 도입 (Client/Server 분리)

### Java 5 ~ 6 — HotSpot 성숙기
- Class Data Sharing(CDS) 도입으로 시작 시간 개선
- GC 개선: Parallel GC가 서버 환경 기본값
- JMX, JConsole 등 모니터링 도구 강화

### Java 7 — invokedynamic과 G1GC
- **invokedynamic** 바이트코드 명령어 추가 (JEP 없음, JSR 292): 동적 언어 지원의 기반. 이후 Java 8 람다의 핵심 구현 메커니즘이 됨
- **G1GC** 도입 (실험적): 대용량 힙에서 예측 가능한 GC 중단 시간 목표
- **Tiered Compilation** 기본 활성화
- **String Pool이 PermGen에서 Heap으로 이동**: PermGen의 고정 크기 제한으로 인한 OOM 문제 해결

### Java 8 — PermGen 제거, Metaspace 도입 (LTS)
- **PermGen → Metaspace** (JEP 122): 클래스 메타데이터를 네이티브 메모리에 저장. 고정 크기 제한 제거, 동적 확장 가능
- 람다 표현식: invokedynamic을 활용한 구현
- Nashorn JavaScript 엔진 도입 (이후 Java 15에서 제거)
- 이 시점의 GC 기본값: Parallel GC (서버), Serial GC (클라이언트)

### Java 9 — 모듈 시스템과 새로운 컴파일러 (JEP 261)
- **JPMS(Java Platform Module System, Project Jigsaw)**: 모놀리식 rt.jar를 모듈로 분리. JVM 자체의 내부 API 캡슐화
- **G1GC가 기본 GC로 변경** (JEP 248)
- **AOT 컴파일** 실험적 도입 (jaotc, JEP 295 — 이후 Java 17에서 제거)
- **Graal JIT 컴파일러** 실험적 추가 (JEP 317, Java 10): C2 대체를 목표로 한 Java로 작성된 JIT 컴파일러
- 6개월 릴리스 주기 시작

### Java 11 — ZGC 등장 (LTS)
- **ZGC** 실험적 도입 (JEP 333): 대용량 힙(TB 단위)에서도 10ms 이하 GC 중단 시간 목표
- **Epsilon GC** (JEP 318): GC를 하지 않는 실험적 수집기 (벤치마킹, 짧은 생명 프로세스용)
- Nashorn 사용 중단 예고

### Java 14 ~ 15 — 저지연 GC 정식화
- **ZGC 정식화** (JEP 377, Java 15): 프로덕션 사용 가능
- **Shenandoah GC 정식화** (JEP 379, Java 15): Red Hat이 개발한 또 다른 저지연 GC
- Nashorn 제거, AOT 컴파일(jaotc) 제거

### Java 16 ~ 17 — 안정화 (LTS)
- **ZGC 동시 스레드 스택 처리** (JEP 376, Java 16): GC 루트 스캐닝까지 동시 처리
- AOT/Graal JIT 실험 코드 JDK에서 제거 (GraalVM으로 분리)
- Sealed Classes 정식화 (JVM의 타입 체크 최적화에 활용)

### Java 21 — Virtual Thread와 Generational ZGC (LTS)
- **Virtual Threads 정식화** (JEP 444, Project Loom): JVM이 관리하는 경량 스레드. OS 스레드와 1:1이 아닌, 소수의 캐리어 스레드에 M:N 매핑. 블로킹 시 OS 스레드를 점유하지 않고 메모리에 suspend
- **Generational ZGC** (JEP 439): "대부분의 객체는 일찍 죽는다"는 약한 세대 가설 활용. 이전 단일 세대 ZGC 대비 약 10% 처리량 개선
- Structured Concurrency, Scoped Values (프리뷰)

### GraalVM과 Native Image — AOT의 부활
- **GraalVM**: Oracle이 개발한 고성능 JDK 배포판
- **Native Image**: Java 코드를 AOT 컴파일하여 네이티브 바이너리 생성
  - 시작 시간: 수십 ms (JVM의 수 초 대비)
  - 메모리 사용: JVM 대비 크게 감소
  - 제약: 리플렉션, 동적 프록시 등에 제한 (빌드 시 정적 분석 필요)
- Spring Boot 3.x, Quarkus, Micronaut 등 프레임워크가 Native Image 공식 지원

---

## 헷갈렸던 포인트

### Q1: "Java는 인터프리터 언어다" vs "Java는 컴파일 언어다" — 어느 쪽이 맞나?

**둘 다 맞고 둘 다 틀리다.** Java는 **하이브리드 실행 모델**을 사용한다.

- `javac`가 소스를 바이트코드로 **컴파일**하고 (컴파일 언어의 특성)
- JVM이 바이트코드를 **인터프리팅**하다가 (인터프리터 언어의 특성)
- 핫스팟 코드를 JIT가 **기계어로 컴파일**한다 (컴파일 언어의 특성)

이런 분류 자체가 의미가 크지 않다. "Java는 바이트코드로 컴파일 후, JVM에서 인터프리터+JIT로 실행된다"가 정확하다.

### Q2: JIT 컴파일러가 있으면 항상 C/C++보다 느린가?

**아니다.** JIT가 AOT보다 나은 최적화를 적용할 수 있는 경우가 있다:
- **프로파일 기반 최적화**: 실행 중 수집한 정보(어떤 분기가 자주 타는지, 어떤 타입이 실제로 들어오는지)로 최적화
- **추측적 인라이닝**: 가상 메서드 호출을 실제 실행 패턴 기반으로 인라이닝
- **탈최적화(Deoptimization)**: 추측이 틀리면 인터프리터로 되돌아갔다가 다시 최적화

단, JVM은 워밍업 시간이 필요하고, GC 오버헤드가 있으므로 **짧은 실행이나 실시간 시스템**에서는 C/C++가 유리하다.

### Q3: Go의 goroutine과 Java 21의 Virtual Thread는 같은 건가?

**비슷한 목표를 가지지만 구현이 다르다:**
- **goroutine**: Go 런타임 스케줄러가 관리, 스택 크기 ~2KB로 시작하며 동적 확장, M:N 스케줄링
- **Virtual Thread**: JVM이 관리, 소수의 캐리어(플랫폼) 스레드에 매핑, 블로킹 I/O 시 자동 suspend/resume
- 핵심 차이: goroutine은 Go 언어에 내장된 1급 기능이고, Virtual Thread는 기존 `java.lang.Thread` API와 호환되도록 설계되어 기존 코드 마이그레이션이 쉬움

### Q4: GraalVM Native Image를 쓰면 JVM의 장점이 사라지는 것 아닌가?

**트레이드오프가 있다:**
- **얻는 것**: 빠른 시작, 낮은 메모리, 단일 바이너리 배포
- **잃는 것**: 런타임 JIT 최적화(장기 실행 시 최대 성능), 리플렉션/동적 프록시 자유로운 사용, 런타임 클래스 로딩
- **적합한 사용처**: 서버리스, CLI 도구, 마이크로서비스 (빠른 시작이 중요한 환경)
- **부적합한 사용처**: 장기 실행 서버 (JIT 최적화 효과가 큰 환경)

---

## 참고 자료

- [Oracle JVM Specification](https://docs.oracle.com/javase/specs/jvms/se21/html/index.html)
- [OpenJDK HotSpot JIT - InfoQ](https://www.infoq.com/articles/OpenJDK-HotSpot-What-the-JIT/)
- [JEP 248: G1 Default GC](https://openjdk.org/jeps/248)
- [JEP 333: ZGC](https://openjdk.org/jeps/333)
- [JEP 444: Virtual Threads](https://openjdk.org/jeps/444)
- [JEP 439: Generational ZGC](https://openjdk.org/jeps/439)
- [JEP 122: Remove PermGen](https://openjdk.org/jeps/122)
- [Red Hat - HotSpot JIT Compiler](https://developers.redhat.com/articles/2021/06/23/how-jit-compiler-boosts-java-performance-openjdk)
- [Graal JIT Compiler - Baeldung](https://www.baeldung.com/graal-java-jit-compiler)
- [Java Version History - Wikipedia](https://en.wikipedia.org/wiki/Java_version_history)
- [Advanced Web Machinery - JVM Features Since JDK 8](https://advancedweb.hu/a-categorized-list-of-all-java-and-jvm-features-since-jdk-8-to-21/)
- [V8 Blog - Maglev](https://v8.dev/blog/maglev)
- [CPython Interpreter Internals](https://devguide.python.org/internals/interpreter/)
