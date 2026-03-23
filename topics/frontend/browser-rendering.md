# 브라우저 동작 원리 — Chrome 기준, URL 입력부터 화면 렌더링까지

## 핵심 정리

### 브라우저의 전체 구조 (Chrome 기준)

```
┌──────────────────────────────────────────────────┐
│                   Browser Process                 │
│  (UI, 북마크, 네트워크, 스토리지 관리)              │
├──────────────────────────────────────────────────┤
│  Renderer Process    │  Renderer Process   │ ... │
│  (탭 1)              │  (탭 2)             │     │
│  ┌─────────────┐    │                      │     │
│  │ Main Thread  │    │                      │     │
│  │ (JS + 레이아웃)│   │                      │     │
│  ├─────────────┤    │                      │     │
│  │ Compositor   │    │                      │     │
│  │ Thread       │    │                      │     │
│  └─────────────┘    │                      │     │
├──────────────────────────────────────────────────┤
│                    GPU Process                    │
│              (실제 픽셀 그리기)                     │
├──────────────────────────────────────────────────┤
│               Network Service                     │
│          (HTTP 요청, DNS, 캐시)                    │
└──────────────────────────────────────────────────┘
```

Chrome은 **멀티 프로세스 아키텍처**:
- **Browser Process**: 주소창, 탭 관리, 네트워크 요청 총괄
- **Renderer Process**: 탭마다 별도 프로세스 (보안 + 안정성). 한 탭이 죽어도 다른 탭에 영향 없음
- **GPU Process**: 모든 탭의 렌더링을 GPU로 합성
- **Plugin Process**: 확장 프로그램 격리 실행

### URL 입력부터 화면까지 — 전체 흐름

```
URL 입력 → DNS 조회 → TCP/TLS 연결 → HTTP 요청 → HTML 응답
→ HTML 파싱 → DOM 트리 → CSSOM 트리 → Render Tree
→ Layout → Paint → Composite → 화면 출력
```

#### 1단계: 네비게이션 (Navigation)

```
사용자가 URL 입력
    ↓
[Browser Process]
    ↓
DNS 조회: 도메인 → IP (캐시 → OS → 라우터 → ISP → Root DNS)
    ↓
TCP 3-Way Handshake (SYN → SYN-ACK → ACK)
    ↓
TLS Handshake (HTTPS인 경우, 인증서 검증 + 대칭키 교환)
    ↓
HTTP 요청 전송 (GET / HTTP/2)
    ↓
서버가 HTML 응답 (Content-Type: text/html)
    ↓
Browser Process → Renderer Process에 HTML 전달 ("이 탭에서 렌더링해라")
```

#### 2단계: 파싱 (Parsing) — HTML → DOM + CSSOM

```
HTML 문서
    ↓
[HTML Parser] → DOM Tree (Document Object Model)
    ↓
<link rel="stylesheet"> 만나면 → CSS 파싱 → CSSOM Tree
<script> 만나면 → JS 실행 (파싱 중단!)
<img> 만나면 → 비동기 리소스 요청 (파싱 계속)
```

**파싱 중단(Parser Blocking)이 중요한 이유:**
- `<script>` 태그를 만나면 HTML 파싱이 **멈춘다**
- JS가 DOM을 조작할 수 있으므로, 파서는 JS 실행이 끝날 때까지 대기
- 해결: `<script defer>` 또는 `<script async>`

```html
<!-- 파싱 블로킹 -->
<script src="app.js"></script>

<!-- defer: HTML 파싱 완료 후 실행 (순서 보장) -->
<script defer src="app.js"></script>

<!-- async: 다운로드 완료 즉시 실행 (순서 미보장) -->
<script async src="analytics.js"></script>
```

**DOM Tree 예시:**
```
Document
├── html
│   ├── head
│   │   ├── title: "My Page"
│   │   └── link (stylesheet)
│   └── body
│       ├── div#app
│       │   ├── h1: "Hello"
│       │   └── p: "World"
│       └── script (app.js)
```

**CSSOM Tree:**
```
StyleSheet
├── body { font-size: 16px; }
│   ├── div#app { display: flex; }
│   │   ├── h1 { color: blue; font-size: 2em; }  ← 상속 + 자체 스타일
│   │   └── p { margin: 10px; }
```

#### 3단계: 스타일 계산 + Render Tree

```
DOM Tree + CSSOM Tree
        ↓
    Render Tree (= DOM 노드 + 계산된 스타일)
        ↓
    display: none인 요소는 제외
    visibility: hidden인 요소는 포함 (공간 차지)
    ::before, ::after 같은 pseudo-element는 추가
```

#### 4단계: Layout (= Reflow)

각 요소의 **정확한 위치와 크기**를 계산한다.

```
Render Tree의 각 노드에 대해:
- 부모 요소의 크기 → 자식의 % 크기 계산
- width, height, margin, padding, border → 정확한 박스 크기
- float, flexbox, grid → 레이아웃 알고리즘 적용
- 결과: 각 요소의 (x, y, width, height) 좌표
```

**Layout이 다시 발생하는 경우 (= Reflow, 비용 큼):**
- DOM 요소 추가/삭제
- 요소의 크기/위치 변경 (width, height, margin, padding)
- 폰트 크기 변경
- 윈도우 리사이즈
- `offsetWidth`, `scrollTop` 등 읽기 → 브라우저가 최신 값을 보장하기 위해 강제 Layout

#### 5단계: Paint

Layout 결과를 바탕으로 **무엇을 그릴지** 명령 목록을 생성한다.

```
Paint Records:
1. #app 배경색 흰색으로 채워라
2. h1 텍스트 "Hello"를 (20, 50) 위치에 파란색으로 그려라
3. p 텍스트 "World"를 (20, 100) 위치에 그려라
4. 테두리를 (10, 40, 300, 80) 좌표에 그려라
```

**Repaint가 발생하는 경우 (Reflow보다는 가벼움):**
- `color`, `background-color`, `visibility` 변경
- `box-shadow`, `border-radius` 변경

#### 6단계: Compositing (합성)

현대 브라우저의 성능 비밀. 페이지를 **여러 레이어로 분리**하여 독립적으로 처리한다.

```
Main Thread                  Compositor Thread         GPU Process
    │                              │                       │
    ├── Layer Tree 생성             │                       │
    ├── 각 레이어 Paint             │                       │
    │       ↓                      │                       │
    │   Paint 결과를 타일로 분할 ──→ 타일을 GPU에 래스터화 ──→ │
    │                              │                       │
    │                     레이어를 합성하여 ──→ 최종 프레임 출력
    │                     최종 프레임 생성                    │
```

**별도 레이어로 승격(promote)되는 조건:**
- `transform: translateZ(0)` 또는 `will-change: transform`
- `position: fixed`
- `<video>`, `<canvas>`
- CSS 애니메이션 사용 시

**Compositing만으로 처리되는 속성 (= 매우 빠름):**
- `transform` (이동, 회전, 크기 조절)
- `opacity`
→ Layout, Paint 건너뛰고 GPU에서 바로 합성

### V8 엔진 — Chrome의 JavaScript 엔진

```
JS 소스코드
    ↓
[Parser] → AST (Abstract Syntax Tree)
    ↓
[Ignition] → 바이트코드 (인터프리터, 빠른 시작)
    ↓
[TurboFan] → 최적화된 머신코드 (핫 코드 감지 시 JIT 컴파일)
    ↓
(타입이 바뀌면 → Deoptimization → 바이트코드로 돌아감)
```

**JIT(Just-In-Time) 컴파일 핵심:**
- 처음엔 인터프리터(Ignition)로 빠르게 실행
- 자주 실행되는 "핫" 함수를 감지
- TurboFan이 해당 함수를 머신코드로 컴파일 (타입 추정 기반 최적화)
- 타입이 예상과 다르면 **Deoptimization** → 인터프리터로 폴백

```javascript
// TurboFan이 최적화하기 좋은 코드
function add(a, b) { return a + b; }
add(1, 2);    // 숫자 + 숫자 → 최적화
add(3, 4);    // 계속 숫자 → 최적화 유지

// TurboFan이 Deoptimization하는 코드
add("hello", "world");  // 갑자기 문자열! → 최적화 해제
```

### 이벤트 루프와 렌더링의 관계

```
┌─────────────────────────────────────────────┐
│              Main Thread 이벤트 루프            │
│                                              │
│  [Task Queue]  →  Task 실행  →  Microtask 전부 실행  │
│       ↓                                      │
│  (16.67ms마다 = 60fps)                        │
│  requestAnimationFrame 콜백                    │
│       ↓                                      │
│  Style → Layout → Paint → Composite          │
│       ↓                                      │
│  다음 Task Queue로                             │
└─────────────────────────────────────────────┘
```

**중요:** JS 실행이 오래 걸리면 렌더링이 블로킹된다!
- JS 실행 → Style/Layout/Paint가 **같은 Main Thread**에서 동작
- 무거운 연산은 `Web Worker`로 분리하거나 `requestIdleCallback` 사용

### React와 브라우저 렌더링의 관계

```
React 컴포넌트 상태 변경 (setState)
    ↓
Virtual DOM 재생성 (React 내부)
    ↓
이전 Virtual DOM과 Diffing (Reconciliation)
    ↓
변경된 부분만 실제 DOM에 반영 (= Commit Phase)
    ↓
브라우저가 Style → Layout → Paint → Composite
```

React 18의 **Concurrent Rendering**:
- 렌더링을 중단/재개할 수 있음
- 긴급한 업데이트(입력)와 비긴급 업데이트(목록 필터링)를 분리
- `useTransition`, `useDeferredValue`로 제어
- Main Thread를 오래 점유하지 않아 **브라우저 렌더링이 블로킹되지 않음**

### Chrome DevTools 성능 분석

**Performance 탭 핵심 지표:**
- **FCP (First Contentful Paint)**: 첫 콘텐츠가 화면에 나타난 시점
- **LCP (Largest Contentful Paint)**: 가장 큰 콘텐츠 렌더링 시점
- **CLS (Cumulative Layout Shift)**: 레이아웃 이동 누적 점수
- **TBT (Total Blocking Time)**: Main Thread 블로킹 총 시간
- **INP (Interaction to Next Paint)**: 사용자 인터랙션 → 다음 Paint까지 지연

**Lighthouse 점수 올리기 실전:**
- JS 번들 크기 줄이기 (Code Splitting, Tree Shaking)
- 이미지 최적화 (WebP, lazy loading)
- CSS 인라인화 (Critical CSS)
- 서버 응답 시간 줄이기 (CDN, 캐싱)
- `<script defer>` 사용

## 헷갈렸던 포인트

### Q: DOM 조작이 느리다고 하는데, 정확히 뭐가 느린 거야?
**A:** DOM 조작 자체는 빠르다. 느린 건 그 **이후에 발생하는 Layout과 Paint**다.
- `element.style.width = '200px'` → Layout 재계산 (Reflow) 트리거
- 여러 DOM 변경을 한 번에 묶으면(batch) Reflow를 한 번만 발생시킬 수 있다
- React의 Virtual DOM이 이걸 자동으로 해준다 (변경사항을 모아서 한 번에 실제 DOM에 반영)

### Q: `transform`이 왜 `top/left`보다 애니메이션이 부드러운 거야?
**A:**
- `top/left` 변경 → **Layout(Reflow) + Paint + Composite** (매 프레임마다 전부 재계산)
- `transform` 변경 → **Composite만** (GPU에서 레이어만 이동, Layout/Paint 생략)
- 60fps(16.67ms/프레임)를 유지하려면 Composite만으로 끝나는 속성을 사용해야 한다

### Q: `<script>` 태그 위치가 왜 중요한데? 그냥 `<head>`에 넣으면 안 되나?
**A:**
- `<head>`에 넣으면: HTML 파싱 중에 JS 다운로드 + 실행 → 화면이 늦게 뜸
- `<body>` 끝에 넣으면: HTML 파싱 완료 후 JS 실행 → 화면은 빨리 뜨지만 인터랙션은 나중에
- **`<script defer>`가 가장 좋음**: HTML 파싱과 병렬 다운로드 + 파싱 완료 후 실행

### Q: 크롬 탭마다 프로세스가 있으면 메모리 엄청 잡아먹는 거 아닌가?
**A:** 맞다. Chrome이 메모리를 많이 쓰는 주된 이유다. 하지만 이 구조의 장점:
- **보안**: 탭 간 메모리 격리 (사이트 격리, Spectre 공격 방어)
- **안정성**: 한 탭의 크래시가 다른 탭에 영향 없음
- Chrome은 메모리가 부족하면 백그라운드 탭 프로세스를 자동 해제(Tab Discarding)

### Q: React가 Virtual DOM을 쓰는 이유가 성능 때문이라는데, 그럼 Vue도 같은 건가?
**A:** Virtual DOM은 "성능을 위해"가 아니라 **"선언적 UI를 가능하게 하면서 충분히 빠르게"** 하기 위한 것이다.
- Virtual DOM 없이도 직접 DOM 조작이 더 빠를 수 있다 (Svelte가 이 방식)
- Vue도 Virtual DOM을 사용하지만, 컴파일 타임에 정적 분석으로 최적화 (Static Hoisting)
- Svelte는 컴파일러가 직접 DOM 조작 코드를 생성 → Virtual DOM 없음 → 더 작은 번들

## 참고 자료
- [How Browsers Work — web.dev](https://web.dev/howbrowserswork/)
- [Inside look at modern web browser (4 parts) — Chrome Developers](https://developer.chrome.com/blog/inside-browser-part1/)
- [V8 JavaScript Engine](https://v8.dev/)
- [Rendering Performance — web.dev](https://web.dev/rendering-performance/)
