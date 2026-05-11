---
title: "Spring StateMachine으로 FSM 구현하기 — 카카오뱅크 알림 시스템 사례"
parent: Spring
nav_order: 9
tags: [Spring, StateMachine, FSM, 유한상태머신, 상태관리, Redis, 알림시스템, 카카오뱅크, DIP, 상태전이]
description: "복잡한 상태 전이를 가진 도메인에서 Spring StateMachine을 어떻게 활용하는지, 카카오뱅크 통합 알림 시스템(UMS) 사례를 통해 FSM의 개념·구현·트레이드오프를 정리합니다."
---

# Spring StateMachine으로 FSM 구현하기 — 카카오뱅크 알림 시스템 사례

## 핵심 정리

**FSM(Finite State Machine, 유한 상태 머신)** 은 시스템이 가질 수 있는 상태(State)와 그 상태들 사이의 전이(Transition)를 명시적으로 모델링하는 패턴이다. 메시지 발송, 주문 처리, 결제 승인처럼 **여러 단계를 거치며 각 단계에서 분기·예외 처리가 필요한 도메인**에서 코드가 if-else 지옥이 되기 쉬운데, FSM은 "상태 + 이벤트 + 전이"라는 선언적 구조로 이를 정리한다.

카카오뱅크는 통합 알림 시스템(UMS, Unified Messaging System)에 **Spring StateMachine 프레임워크**를 도입해 메시지 라이프사이클(접수 → 발송 → 성공/실패/취소)을 관리하는 사례를 공유했다. 도입을 통해 얻은 가치와 함께 **TTL 누락으로 인한 Redis 메모리 누수, 학습 곡선, 과도한 기능성** 같은 트레이드오프도 솔직하게 짚는다.

이 문서는 FSM이 왜 필요한지, Spring StateMachine의 구성 요소가 무엇인지, 실제 적용 시 어떤 점을 주의해야 하는지를 정리한다.

---

## 1. FSM은 왜 필요한가

### 상태 전이가 복잡한 도메인의 문제

알림 발송 같은 도메인은 메시지 하나의 라이프사이클이 단순하지 않다.

```
[접수 완료(RECEIVED)]
    │
    ├── 발송 → [발송 성공(SENT_SUCCEEDED)]
    │       └── (종료)
    │
    ├── 발송 → [발송 실패(SENT_FAILED)]
    │       └── 재처리 → [재시도 중]
    │
    └── 취소 → [취소됨(CANCELLED)]
            └── (종료)
```

이런 흐름을 단순 if-else로 구현하면 다음과 같은 문제가 생긴다:

- **상태 전이가 코드 곳곳에 흩어진다** — 새 상태가 추가되면 여러 파일을 수정해야 함
- **불법 전이를 막기 어렵다** — "이미 취소된 메시지를 다시 발송"같은 케이스를 누가 막을지 불명확
- **테스트가 어렵다** — 가능한 상태 조합이 폭발적으로 늘어남
- **가시성이 떨어진다** — 전체 상태 흐름이 코드 어디에 있는지 알기 어려움

### FSM 패턴의 가치

FSM은 위 문제를 다음과 같이 해결한다:

| 가치 | 설명 |
|------|------|
| **명시성** | 가능한 상태와 전이를 한 곳에서 선언적으로 정의 |
| **안전성** | 정의되지 않은 전이는 자동으로 차단 |
| **테스트 용이성** | 각 전이를 독립 단위로 검증 가능 |
| **확장성** | 새 상태/이벤트 추가 시 영향 범위가 명확 |

---

## 2. Spring StateMachine의 구성 요소

Spring StateMachine은 FSM을 구현하기 위한 Spring 공식 프레임워크다. 핵심 개념은 다음 5가지다.

### State (상태)

시스템이 현재 머무는 위치. 알림 시스템 예시:

```kotlin
enum class MessageStatus {
    RECEIVED,          // 접수 완료
    CANCELLED,         // 취소됨
    SENT_SUCCEEDED,    // 발송 성공
    SENT_FAILED        // 발송 실패
}
```

### Event (이벤트)

상태 전이를 유발하는 입력. "이런 일이 일어났다"는 신호.

```kotlin
enum class MessageEvent {
    SEND,    // 발송 요청
    CANCEL   // 취소 요청
}
```

### Transition (전이)

"어떤 상태에서 어떤 이벤트가 발생하면, 어떤 상태로 이동한다"는 규칙.

```
RECEIVED + SEND   → SENT_SUCCEEDED (성공 시)
RECEIVED + SEND   → SENT_FAILED    (실패 시)
RECEIVED + CANCEL → CANCELLED
```

### Guard (전이 조건)

전이가 일어나도 되는지 검증하는 조건. **false를 반환하면 전이가 차단된다**.

예: "이미 발송된 메시지는 취소할 수 없다" → `cancelGuard()`가 현재 상태를 확인하고 false 반환.

### Action (전이 시 실행 동작)

전이가 일어나는 시점에 실행되는 비즈니스 로직.

예: `RECEIVED → SENT_SUCCEEDED` 전이 시 "발송 완료 알림 전송", "통계 업데이트" 등을 Action으로 등록.

### 전체 그림

```
┌─────────────┐    SEND + Guard OK + sendAction()    ┌─────────────────┐
│  RECEIVED   │ ──────────────────────────────────▶ │ SENT_SUCCEEDED  │
│             │                                     └─────────────────┘
│             │    SEND + Guard OK + failAction()    ┌─────────────────┐
│             │ ──────────────────────────────────▶ │  SENT_FAILED    │
│             │                                     └─────────────────┘
│             │    CANCEL + cancelGuard + cancelAction ┌─────────────┐
│             │ ──────────────────────────────────▶ │  CANCELLED  │
└─────────────┘                                     └─────────────┘
```

---

## 3. 카카오뱅크의 적용 도메인 — UMS (Unified Messaging System)

카카오뱅크는 다음 채널을 통합 관리하는 **알림 발송 플랫폼**에 Spring StateMachine을 도입했다.

- 앱 푸시
- 카카오 알림톡
- 이메일
- SMS / LMS
- 팩스

이 시스템은 단순히 메시지를 보내고 끝이 아니라:

1. **접수** — 발송 요청을 받아 큐에 적재
2. **필터링** — 수신 거부 사용자, 휴면 계정 등 제외
3. **예약 발송** — 지정된 시각까지 보관
4. **발송** — 채널별 외부 시스템 호출
5. **결과 수신** — 비동기 콜백으로 성공/실패 확인
6. **재처리** — 실패한 메시지의 재시도

각 단계가 비동기이고 외부 시스템 의존성이 강하기 때문에, 상태 관리가 핵심 과제가 된다. FSM이 잘 맞는 도메인이다.

---

## 4. 구현 — 의존성, 설정, Action/Guard, 영속화

### 의존성 추가

```gradle
dependencyManagement {
    imports {
        mavenBom "org.springframework.statemachine:spring-statemachine-bom:4.0.0"
    }
}

dependencies {
    implementation("org.springframework.statemachine:spring-statemachine-starter")
}
```

### StateMachine 구성

`@EnableStateMachineFactory`를 사용해 팩토리를 노출하고, `StateMachineConfigurerAdapter`를 상속받아 상태/이벤트/전이를 선언한다.

```kotlin
@Configuration
@EnableStateMachineFactory
class MessageStateMachineConfig(
    private val cancelGuard: CancelGuard,
    private val cancelAction: CancelAction,
    private val sendAction: SendAction,
) : StateMachineConfigurerAdapter<MessageStatus, MessageEvent>() {

    override fun configure(states: StateMachineStateConfigurer<MessageStatus, MessageEvent>) {
        states.withStates()
            .initial(MessageStatus.RECEIVED)
            .states(MessageStatus.values().toSet())
            .end(MessageStatus.SENT_SUCCEEDED)
            .end(MessageStatus.SENT_FAILED)
            .end(MessageStatus.CANCELLED)
    }

    override fun configure(transitions: StateMachineTransitionConfigurer<MessageStatus, MessageEvent>) {
        transitions
            .withExternal()
                .source(MessageStatus.RECEIVED).target(MessageStatus.CANCELLED)
                .event(MessageEvent.CANCEL)
                .guard(cancelGuard)
                .action(cancelAction)
            .and()
            .withExternal()
                .source(MessageStatus.RECEIVED).target(MessageStatus.SENT_SUCCEEDED)
                .event(MessageEvent.SEND)
                .action(sendAction)
            // ... 나머지 전이
    }
}
```

핵심 포인트:
- `initial(...)` — 시작 상태 지정
- `end(...)` — 종료 상태(이후 전이 불가)
- `withExternal()` — 상태가 바뀌는 전이(self-transition은 internal)
- `guard()` / `action()` — 조건과 실행 로직 주입

### Action 구현

```kotlin
@Component
class CancelAction : Action<MessageStatus, MessageEvent> {
    override fun execute(context: StateContext<MessageStatus, MessageEvent>) {
        val messageId = context.messageHeaders["messageId"] as String
        // 취소 처리 비즈니스 로직
    }
}
```

이벤트 헤더(`messageHeaders`)를 통해 외부에서 필요한 컨텍스트를 Action으로 전달할 수 있다.

### Guard 구현

```kotlin
@Component
class CancelGuard : Guard<MessageStatus, MessageEvent> {
    override fun evaluate(context: StateContext<MessageStatus, MessageEvent>): Boolean {
        // 취소 가능 여부 검증
        return true
    }
}
```

### 이벤트 발행

```kotlin
val message = MessageBuilder
    .withPayload(MessageEvent.CANCEL)
    .setHeader("messageId", messageId)
    .build()

stateMachine.sendEvent(Mono.just(message)).subscribe()
```

### Redis 영속화 — 분산 환경 대응

기본 StateMachine은 인메모리다. 여러 인스턴스가 동시에 메시지를 처리하거나, 인스턴스 재시작 후에도 상태를 유지해야 하면 외부 저장소가 필요하다.

```kotlin
@Bean
fun stateMachinePersist(
    redisConnectionFactory: RedisConnectionFactory
): RedisStateMachinePersister<MessageStatus, MessageEvent> {
    return RedisStateMachinePersister(
        DefaultStateMachinePersister(
            RedisPersistingStateMachineInterceptor(redisConnectionFactory)
        )
    )
}
```

`RedisPersistingStateMachineInterceptor`는 전이가 일어날 때마다 상태 머신의 현재 상태를 Redis에 저장한다.

### DIP 적용 — 프레임워크 결합도 낮추기

카카오뱅크는 Spring StateMachine의 `StateMachine` 인터페이스를 직접 사용하지 않고, **자체 인터페이스로 감싼 후** 그 구현체가 Spring StateMachine을 사용하도록 했다.

```kotlin
interface MessageStateProcessor {
    fun process(messageId: String, event: MessageEvent)
}

class SpringStateMachineProcessor(
    private val factory: StateMachineFactory<MessageStatus, MessageEvent>,
    private val persister: StateMachinePersister<MessageStatus, MessageEvent, String>
) : MessageStateProcessor {
    override fun process(messageId: String, event: MessageEvent) {
        // Spring StateMachine 구현 세부사항
    }
}
```

**이유**: 프레임워크를 갈아끼우거나 직접 구현으로 회귀할 때 호출하는 쪽 코드를 안 바꿔도 됨. 의존성 역전 원칙(DIP) 적용.

---

## 5. 도입하면서 겪은 문제들

### 5-1. TTL 미설정 → Redis 메모리 누수

가장 뼈아픈 이슈. Spring StateMachine은 Redis에 상태를 저장할 때 **기본 TTL을 설정하지 않는다**. 즉 상태 머신 인스턴스를 명시적으로 제거하지 않으면 Redis에 영구히 남는다.

```
메시지 처리 완료 → 상태 머신 종료 (end state 도달)
    → 하지만 Redis의 상태 데이터는 그대로 남음
    → 시간이 지나면 Redis 메모리 포화
```

**해결책**:
- 종료 상태 도달 시 명시적으로 `stateMachine.stopReactively()` + Redis 키 삭제
- 또는 Redis 키에 TTL을 직접 설정하는 커스텀 Interceptor 작성

### 5-2. 학습 곡선

Spring StateMachine은 기능이 풍부한 만큼 진입 장벽이 있다.
- `withExternal()` vs `withInternal()` vs `withLocal()` 차이
- Reactive API와 동기 API의 혼재 (`sendEvent` 등은 `Mono` 반환)
- Hierarchical State / Region / Pseudo State 같은 고급 기능

**시사점**: 단순한 도메인이면 enum + when 분기로 직접 구현하는 게 더 빠를 수 있다.

### 5-3. 과도한 기능성

UML State Diagram을 거의 다 지원하는 프레임워크라, 정작 필요한 건 단순한 전이뿐인데 의도치 않게 복잡한 API를 마주하게 된다.

### 5-4. 프레임워크 제약

특정 동작(예: 특정 시점에 다른 상태 머신과 통신, 커스텀 영속화 포맷)을 원하는 대로 구현하기 어려운 경우가 있다. 프레임워크가 정한 추상화에 맞춰야 한다.

---

## 6. 직접 구현 vs 프레임워크 — 선택 기준

| 항목 | 직접 구현 (enum + when) | Spring StateMachine |
|------|------------------------|---------------------|
| **개발 시간** | 단순할 땐 짧음, 복잡해질수록 폭증 | 초기엔 길지만 일정 |
| **자유도** | 100% 자유 | 프레임워크 추상화 내 |
| **유지보수** | 상태 늘어나면 부담 큼 | 선언적 구조로 일정 |
| **학습 비용** | 없음 | 있음 |
| **분산 환경 영속화** | 직접 구현 | 내장 (Redis/JPA 등) |
| **이벤트 리스너/AOP** | 직접 구현 | 내장 |
| **테스트** | 단위 테스트 직관적 | 프레임워크 통합 필요 |

**선택 기준**:
- **상태 < 5개, 전이 단순** → 직접 구현
- **상태 ≥ 10개, 복잡한 전이/분기/Guard, 분산 영속화 필요** → Spring StateMachine
- **그 중간** → 팀 역량과 향후 확장성으로 결정

---

## 7. 결론 — "만능 도구는 없다, 적절한 선택은 있다"

원글이 강조하는 핵심 메시지는 **도구 자체에 매몰되지 말라**는 것이다.

- Spring StateMachine은 강력하지만 만능은 아님
- 직접 구현이 더 적합한 경우도 많음
- 선택은 **프로젝트 규모, 팀 역량, 요구사항 복잡도, 확장성**을 종합 판단

개발자의 진짜 역량은 특정 프레임워크 숙련도가 아니라 **상황에 맞는 도구를 선택하는 판단력**이라는 결론. 도입 후 TTL 누락으로 메모리 누수까지 겪었기에 더 설득력 있는 교훈이다.

---

## 헷갈렸던 포인트

### Q1. FSM이랑 워크플로우 엔진(Camunda, Activiti)이랑 뭐가 다른가?

**A**: 추상화 수준이 다르다.
- **FSM**: "상태 + 이벤트 + 전이"라는 단순 모델. 가벼움. 코드로 표현.
- **워크플로우 엔진(BPMN)**: Task, Gateway, Event, Subprocess 등 비즈니스 프로세스 전반을 모델링. 비개발자(기획자)도 다이어그램으로 정의 가능. 무거움.

알림 발송처럼 상태 전이가 메인이면 FSM, 복잡한 사람-시스템 협업 프로세스(여신 심사 워크플로우 등)면 BPMN이 적합.

### Q2. State Pattern(GoF)이랑 Spring StateMachine은 같은 건가?

**A**: 개념적으로 같은 패밀리지만 구현 방식이 다르다.
- **State Pattern**: 객체지향 디자인 패턴. 각 상태를 클래스로 만들고, 컨텍스트가 현재 상태 객체를 참조. 상태 클래스가 다음 상태로의 전이를 직접 알고 있음.
- **Spring StateMachine**: 선언적 설정 기반. 상태는 enum, 전이 규칙은 별도 Config에 모아둠. 상태 자체는 데이터, 전이 로직은 프레임워크가 관리.

State Pattern은 상태가 적고 동작이 다양할 때, Spring StateMachine은 전이 규칙 자체가 복잡할 때 유리.

### Q3. 왜 DB가 아닌 Redis에 상태를 저장하나?

**A**: 두 가지 이유.
1. **속도** — 상태 전이는 빈번하게 일어남. DB에 매번 쓰면 부하 큼.
2. **분산 환경 일관성** — 여러 인스턴스가 동일 메시지를 처리하려 할 때 Redis의 단일 인스턴스로 직렬화 가능.

다만 Redis가 휘발성이므로 **최종 결과는 별도 RDB에 기록**하는 게 일반적. 진행 중인 상태는 Redis, 종결된 상태는 DB 식으로 분리.

### Q4. 종료 상태(end state)에 도달한 상태 머신은 자동으로 정리되나?

**A**: **아니다**. 위의 5-1 문제와 직결. `end()`로 지정해도 메모리/Redis에서 자동 삭제되지 않음. **반드시 명시적으로 stop + 영속화 키 삭제**해야 함. 카카오뱅크의 메모리 누수가 이 함정에서 발생.

### Q5. Guard가 false를 반환하면 어떻게 되나?

**A**: 전이가 **무시된다**. 예외도 안 던진다. 호출자 입장에서는 "이벤트를 보냈는데 상태가 안 바뀌었다"만 알 수 있음. 그래서:
- Guard 실패를 알아야 하는 호출자라면 `StateMachineListener`로 `transitionDeclined()` 이벤트를 수신
- 또는 Guard 검증 자체를 호출 측에서 미리 하고, Guard는 안전망 용도로만 사용

### Q6. Action 안에서 예외가 발생하면 전이가 롤백되나?

**A**: **기본적으로 롤백되지 않는다**. 상태는 이미 전이된 채로 Action만 실패한 상태가 됨. 이게 일관성 문제를 일으킬 수 있어서:
- Action에서 발생할 수 있는 예외는 Action 내부에서 try-catch
- 또는 별도 보상 트랜잭션(Saga 패턴)으로 상태를 원복
- 또는 Action의 비즈니스 로직 자체를 멱등하게 작성

---

## 참고 자료

- [Spring Statemachine 적용기 (카카오뱅크 기술 블로그)](https://tech.kakaobank.com/posts/2511-fsm-using-spring-statemachine/)
- [Spring Statemachine Reference Documentation](https://docs.spring.io/spring-statemachine/docs/current/reference/)
- [State Pattern (Refactoring Guru)](https://refactoring.guru/design-patterns/state)
