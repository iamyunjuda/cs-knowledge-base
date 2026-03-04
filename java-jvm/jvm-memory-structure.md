# JVM 메모리 구조

## 핵심 정리

### JVM Runtime Data Areas 전체 구조

JVM 스펙에서 정의하는 런타임 데이터 영역은 **스레드 공유 영역**과 **스레드 전용 영역**으로 나뉜다:

```
┌─────────────────────────────────────────────────────────────┐
│                    JVM Runtime Data Areas                    │
├──────────────── 스레드 공유 (JVM 당 1개) ────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                    Heap                              │    │
│  │  ┌──────────────────┐  ┌──────────────────────┐     │    │
│  │  │  Young Generation │  │   Old Generation     │     │    │
│  │  │  ┌─────┐┌──────┐ │  │                      │     │    │
│  │  │  │Eden ││Survi-│ │  │  (오래 살아남은 객체) │     │    │
│  │  │  │     ││vor   │ │  │                      │     │    │
│  │  │  │     ││S0/S1 │ │  │                      │     │    │
│  │  │  └─────┘└──────┘ │  └──────────────────────┘     │    │
│  │  └──────────────────┘                                │    │
│  │  ┌──────────────────────────────────────────────┐    │    │
│  │  │              String Pool (Java 7+)            │    │    │
│  │  └──────────────────────────────────────────────┘    │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │           Method Area (Metaspace, Java 8+)           │    │
│  │     클래스 메타데이터, 상수 풀, 메서드 코드 등         │    │
│  │          (네이티브 메모리에 저장)                      │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
├──────────────── 스레드 전용 (스레드 당 1개) ────────────────┤
│                                                             │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────┐         │
│  │ JVM Stack│  │PC Register│  │Native Method Stack│         │
│  │ (프레임) │  │          │  │                   │         │
│  └──────────┘  └──────────┘  └───────────────────┘         │
└─────────────────────────────────────────────────────────────┘
```

---

### 1. Heap (힙)

모든 **객체 인스턴스와 배열**이 할당되는 영역. GC의 주요 대상이다.

#### 전통적 세대별 구조 (Serial GC, Parallel GC, CMS)

| 영역 | 설명 | GC 종류 |
|------|------|---------|
| **Eden** | 새 객체가 최초 할당되는 공간 | Minor GC |
| **Survivor (S0, S1)** | Minor GC에서 살아남은 객체가 이동. 두 영역을 번갈아 사용 | Minor GC |
| **Old Generation** | Survivor에서 임계값(age) 이상 살아남은 객체가 승격(promotion) | Major/Full GC |

- **Minor GC**: Young 영역만 수집. 빈도 높고 빠름
- **Major GC**: Old 영역 수집. 빈도 낮고 느림
- **Full GC**: 전체 힙 수집. Stop-the-World 시간이 가장 김

#### G1GC의 Region 기반 구조 (Java 9+ 기본 GC)

G1은 힙을 **고정 크기의 Region**(기본 1~32MB)으로 나누어 관리한다:

```
┌────┬────┬────┬────┬────┬────┬────┬────┐
│ E  │ S  │ O  │ E  │ H  │ O  │ E  │ S  │
├────┼────┼────┼────┼────┼────┼────┼────┤
│ O  │Free│ E  │ O  │ H  │Free│ O  │ E  │
└────┴────┴────┴────┴────┴────┴────┴────┘
E=Eden, S=Survivor, O=Old, H=Humongous, Free=미할당
```

- 각 Region은 역할(Eden/Survivor/Old/Humongous)이 동적으로 변경
- **Humongous Region**: Region 크기의 50% 이상인 대형 객체 전용
- GC 시 가비지가 가장 많은 Region부터 수집 → "Garbage-First" 이름의 유래
- **목표 중단 시간** 설정 가능 (`-XX:MaxGCPauseMillis`, 기본 200ms)

#### ZGC의 구조 (Java 15+ 프로덕션)

- **Colored Pointers**: 객체 참조 포인터에 메타데이터 비트를 삽입하여 GC 상태 추적
- **Load Barriers**: 객체 참조 로드 시 GC 관련 작업을 동시 수행
- GC 중단 시간: **힙 크기와 무관하게 10ms 이하** (수 TB 힙에서도)
- Java 21의 **Generational ZGC** (JEP 439): 세대별 구분을 추가하여 Young 객체를 더 빈번하게 수집, 처리량 약 10% 개선

#### Shenandoah GC

- Red Hat이 개발, Java 12에서 실험적 도입, Java 15에서 정식화
- ZGC와 유사한 저지연 목표지만 다른 구현: Brooks Pointer를 사용한 동시 이동(compaction)
- **Java 8 백포트 지원**: ZGC와 달리 Java 8에서도 사용 가능 (Red Hat 빌드)

---

### 2. Method Area (메서드 영역) — PermGen에서 Metaspace로

JVM 스펙상 "Method Area"는 **논리적 개념**이고, 그 물리적 구현이 시대에 따라 변했다:

#### PermGen (Java 7 이하)

```
JVM Heap
├── Young Generation
├── Old Generation
└── Permanent Generation (PermGen)  ← 클래스 메타데이터 저장
```

- **힙의 일부**로 구현, 고정 크기 (기본 64~96MB, JVM마다 다름)
- 저장 내용: 클래스 메타데이터, 상수 풀, 정적 변수, 메서드 바이트코드
- **문제**: 많은 클래스를 로드하는 애플리케이션(WAS의 핫 리디플로이 등)에서 `java.lang.OutOfMemoryError: PermGen space` 빈번 발생
- 크기 조정: `-XX:MaxPermSize`로 설정하지만, 적정 값 예측이 어려움

#### Metaspace (Java 8+)

```
JVM Heap
├── Young Generation
└── Old Generation

Native Memory (OS가 관리)
└── Metaspace  ← 클래스 메타데이터 저장
```

- **네이티브 메모리**에 저장, 힙과 분리
- **동적 확장**: 기본적으로 사용 가능한 시스템 메모리까지 자동 확장
- PermGen의 고정 크기 문제 해결 → PermGen OOM이 사라짐
- 제어 옵션:
  - `-XX:MetaspaceSize`: 초기 크기 (기본값은 JVM에 따라 다름, 보통 ~20MB)
  - `-XX:MaxMetaspaceSize`: 최대 크기 (설정하지 않으면 시스템 메모리까지)
- **주의**: 무한 확장 가능하므로 클래스 로더 누수 시 네이티브 메모리 고갈 가능 → `MaxMetaspaceSize` 설정 권장

---

### 3. JVM Stack (스택)

각 스레드마다 고유한 스택이 생성되며, 메서드 호출마다 **스택 프레임**이 push된다:

```
┌──────────────────────┐
│   Stack Frame (현재)  │ ← 현재 실행 중인 메서드
│  ┌────────────────┐  │
│  │ Local Variables │  │ ← 지역 변수, 매개변수, this 참조
│  ├────────────────┤  │
│  │ Operand Stack  │  │ ← 연산 중간 결과 저장
│  ├────────────────┤  │
│  │ Frame Data     │  │ ← 상수 풀 참조, 예외 테이블 등
│  └────────────────┘  │
├──────────────────────┤
│   Stack Frame (이전)  │
├──────────────────────┤
│         ...          │
└──────────────────────┘
```

- **스레드 기본 스택 크기**: `-Xss`로 설정 (기본 512KB~1MB, OS/JVM에 따라 다름)
- 스택이 가득 차면 `java.lang.StackOverflowError` 발생 (깊은 재귀 등)
- **원시 타입(int, long 등)은 스택에 직접 저장**, 객체는 힙에 생성 후 스택에 참조(주소)만 저장

---

### 4. PC Register (Program Counter)

- 각 스레드마다 하나씩 존재
- 현재 실행 중인 바이트코드 명령어의 주소를 저장
- Native 메서드 실행 중이면 값이 undefined

### 5. Native Method Stack

- `native` 키워드가 붙은 메서드 (JNI를 통한 C/C++ 코드) 실행 시 사용
- JVM Stack과 분리되어 관리 (HotSpot은 구현상 합쳐서 관리하기도 함)

---

### 6. String Pool

#### Java 6 이하: PermGen에 위치
- String 리터럴과 `intern()` 호출 결과가 PermGen에 저장
- PermGen의 작은 고정 크기(32~96MB) 때문에 대량의 String intern 시 OOM 위험

#### Java 7+: Heap으로 이동
- **JDK 7u40부터** String Pool이 힙으로 이동
- GC의 대상이 되어 참조되지 않는 문자열은 수거됨
- 힙의 큰 용량을 활용할 수 있어 OOM 위험 대폭 감소
- `intern()` 호출 시: Pool에 동일 문자열이 있으면 그 참조 반환, 없으면 힙의 해당 객체 참조를 Pool에 등록 (Java 7+ 방식)

```java
String s1 = "hello";           // 리터럴 → String Pool에 등록
String s2 = new String("hello"); // 힙에 새 객체 생성
String s3 = s2.intern();       // Pool의 "hello" 참조 반환

System.out.println(s1 == s3);  // true (같은 Pool 참조)
System.out.println(s1 == s2);  // false (s2는 힙의 별도 객체)
```

---

### 7. Direct Memory (Off-Heap)

- `ByteBuffer.allocateDirect()`로 할당하는 네이티브 메모리
- 힙 바깥에 위치하므로 GC 대상이 아님 (래퍼 객체의 `Cleaner`/`finalize`로 해제)
- NIO 채널에서 OS 커널 버퍼와 직접 통신할 때 성능 이점 (힙 ↔ 네이티브 메모리 복사 생략)
- `-XX:MaxDirectMemorySize`로 최대 크기 제한
- 과도한 할당 시 `java.lang.OutOfMemoryError: Direct buffer memory` 발생

---

### 주요 OOM 에러 정리

| 에러 메시지 | 발생 영역 | 원인 | 대응 |
|------------|----------|------|------|
| `Java heap space` | Heap | 객체가 너무 많거나 메모리 누수 | `-Xmx` 증가, 힙 덤프 분석 |
| `GC overhead limit exceeded` | Heap | GC에 시간의 98% 이상 사용 | 메모리 누수 확인, 힙 증가 |
| `PermGen space` (Java 7 이하) | PermGen | 클래스 로더 누수, 너무 많은 클래스 로드 | `-XX:MaxPermSize` 증가, 클래스 로더 누수 수정 |
| `Metaspace` (Java 8+) | Metaspace | 클래스 로더 누수 | 클래스 로더 누수 수정, `-XX:MaxMetaspaceSize` 조정 |
| `unable to create native thread` | OS | OS 스레드 제한 초과 | 스레드 수 줄이기, 스택 크기(`-Xss`) 줄이기 |
| `Direct buffer memory` | Direct Memory | Direct ByteBuffer 과다 할당 | `-XX:MaxDirectMemorySize` 조정, 명시적 해제 |

---

## 헷갈렸던 포인트

### Q1: "Method Area = PermGen = Metaspace"인가?

**아니다.** 이 셋은 서로 다른 레벨의 개념이다:
- **Method Area**: JVM 스펙의 **논리적 정의**. "클래스 수준 데이터를 저장하는 영역"이라는 추상 개념
- **PermGen**: Java 7 이하에서 Method Area를 **물리적으로 구현**한 방식 (힙의 일부)
- **Metaspace**: Java 8+에서 Method Area를 **물리적으로 구현**한 방식 (네이티브 메모리)

즉, PermGen과 Metaspace는 같은 논리적 영역(Method Area)의 서로 다른 구현체다.

### Q2: "static 변수"는 어디에 저장되나?

**Java 버전에 따라 다르다:**
- **Java 7 이하**: PermGen에 저장 (Method Area의 일부)
- **Java 8+**: 클래스 메타데이터는 Metaspace에 저장되지만, **static 변수 중 객체 참조**는 힙의 Class 객체에 저장됨
- 정확히 말하면, `Class<?>` 객체 자체가 힙에 있고, static 필드의 참조가 이 객체에 연결됨

### Q3: G1GC에서도 "Young/Old" 개념이 있는가?

**있다.** 다만 구현 방식이 다르다:
- **전통 GC**: 물리적으로 연속된 메모리 영역을 Young/Old로 고정 분할
- **G1GC**: 동일 크기 Region을 동적으로 Eden/Survivor/Old 역할로 할당. 물리적으로 연속될 필요 없음. 비율도 런타임에 자동 조정
- G1에서도 Young GC(Eden+Survivor Region 수집)와 Mixed GC(Young+일부 Old Region 수집) 개념이 존재

### Q4: ZGC와 Shenandoah 중 어떤 것을 선택해야 하나?

**워크로드와 환경에 따라 다르다:**
- **ZGC**: Oracle/OpenJDK 공식, 대용량 힙(TB급)에 강점, Java 21+ Generational ZGC가 처리량 우수
- **Shenandoah**: Red Hat 주도, Java 8 백포트 지원, 중소 규모 힙에서도 우수
- **공통점**: 둘 다 10ms 이하 GC 중단 시간 목표, 동시(concurrent) 수집
- **일반 권장**: 먼저 G1GC(기본값)를 사용하고, GC 중단 시간이 SLA 위반 원인일 때만 ZGC/Shenandoah 전환 고려

### Q5: 스택에 객체가 저장될 수 있나? (Escape Analysis)

**가능하다 (JVM 최적화에 의해).** JIT 컴파일러의 **탈출 분석(Escape Analysis, Java 6u23+)** 에 의해:
- 메서드 안에서만 사용되고 외부로 참조가 나가지 않는 객체는 스택에 할당하거나 아예 스칼라로 분해(Scalar Replacement)할 수 있음
- 이는 힙 할당과 GC 부담을 줄이는 중요한 최적화
- 단, 이는 **JVM의 최적화 결정**이지 개발자가 제어하는 것이 아님

---

## 참고 자료

- [Oracle JVM Specification - Runtime Data Areas](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html#jvms-2.5)
- [JEP 122: Remove the Permanent Generation](https://openjdk.org/jeps/122)
- [JEP 248: Make G1 the Default Garbage Collector](https://openjdk.org/jeps/248)
- [JEP 333: ZGC - A Scalable Low-Latency GC](https://openjdk.org/jeps/333)
- [JEP 377: ZGC - A Scalable Low-Latency GC (Production)](https://openjdk.org/jeps/377)
- [JEP 379: Shenandoah - A Low-Pause-Time GC (Production)](https://openjdk.org/jeps/379)
- [JEP 439: Generational ZGC](https://openjdk.org/jeps/439)
- [Baeldung - Java String Pool](https://www.baeldung.com/java-string-pool)
- [DigitalOcean - Java Memory Management](https://www.digitalocean.com/community/tutorials/java-jvm-memory-model-memory-management-in-java)
- [HeapHero - JVM Memory Model Deep Dive](https://blog.heaphero.io/a-deep-dive-into-the-jvm-memory-model-how-heap-stack-and-metaspace-function-and-fail/)
- [Red Hat - Shenandoah GC Guide](https://developers.redhat.com/articles/2024/05/28/beginners-guide-shenandoah-garbage-collector)
- [foojay - 10 Years Java GC Guide](https://foojay.io/today/the-ultimate-10-years-java-garbage-collection-guide-2016-2026-choosing-the-right-gc-for-every-workload/)
