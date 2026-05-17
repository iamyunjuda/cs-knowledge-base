# MCP (Model Context Protocol) — AI 모델과 외부 세계를 연결하는 표준 프로토콜

## 핵심 정리

### MCP란?

MCP(Model Context Protocol)는 Anthropic이 2024년 11월에 공개한 **오픈 표준 프로토콜**로, AI 애플리케이션이 외부 데이터 소스, 도구, 서비스에 안전하게 접근할 수 있도록 하는 통신 규격이다.

### 왜 필요한가?

LLM은 학습 데이터 시점의 지식만 갖고 있고, 외부 시스템과 직접 상호작용할 수 없다. 이를 해결하기 위해 각 AI 서비스/도구마다 별도의 통합(Integration)을 구현해야 했는데, 이는 **M×N 문제**를 야기한다.

```
MCP 없이:
  AI앱 A ──┬── 커스텀 통합 ──→ 도구 1
           ├── 커스텀 통합 ──→ 도구 2
           └── 커스텀 통합 ──→ 도구 3
  AI앱 B ──┬── 커스텀 통합 ──→ 도구 1  (또 따로 구현)
           ├── 커스텀 통합 ──→ 도구 2
           └── 커스텀 통합 ──→ 도구 3

MCP로:
  AI앱 A ──┐                  ┌── MCP Server ──→ 도구 1
           ├── MCP Protocol ──┼── MCP Server ──→ 도구 2
  AI앱 B ──┘                  └── MCP Server ──→ 도구 3
```

**USB-C 비유**: USB-C가 충전기/디스플레이/데이터 전송을 하나의 포트로 통합한 것처럼, MCP는 AI와 외부 도구의 연결을 하나의 프로토콜로 표준화한다. M개의 AI 앱과 N개의 도구가 있을 때, M×N개의 커스텀 통합 대신 M+N개의 MCP 구현만 있으면 된다.

### 아키텍처

MCP는 **Host - Client - Server** 3계층 구조를 따른다:

```
┌─────────────────────────────────────────────────┐
│  MCP Host (예: Claude Desktop, IDE, AI 챗봇)      │
│                                                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │MCP Client│  │MCP Client│  │MCP Client│       │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘       │
└───────┼──────────────┼──────────────┼────────────┘
        │              │              │
   JSON-RPC       JSON-RPC       JSON-RPC
        │              │              │
  ┌─────┴─────┐  ┌─────┴─────┐  ┌─────┴─────┐
  │MCP Server │  │MCP Server │  │MCP Server │
  │ (GitHub)  │  │ (Slack)   │  │ (DB)      │
  └───────────┘  └───────────┘  └───────────┘
```

**Host**: 사용자가 직접 사용하는 AI 애플리케이션. Claude Desktop, IDE(Cursor, VS Code), 커스텀 AI 챗봇 등. MCP Client 인스턴스를 생성하고 관리한다.

**Client**: Host 내부에서 동작하며, 특정 MCP Server와 1:1 연결을 유지한다. 프로토콜 협상(Capability Negotiation), 메시지 라우팅을 담당한다.

**Server**: 외부 시스템에 대한 인터페이스를 MCP 프로토콜로 노출한다. 경량 프로그램으로, 하나의 서비스(GitHub, Slack, DB 등)를 MCP로 래핑한다.

### 핵심 기능 (Primitives)

MCP Server가 제공할 수 있는 3가지 핵심 기능:

| Primitive | 설명 | 제어 주체 | 비유 |
|-----------|------|----------|------|
| **Resources** | 데이터/컨텍스트 제공 (파일, DB 레코드, API 응답 등) | 애플리케이션 | GET 엔드포인트 |
| **Tools** | 모델이 호출할 수 있는 함수/액션 | 모델 (LLM) | POST 엔드포인트 |
| **Prompts** | 재사용 가능한 프롬프트 템플릿 | 사용자 | 저장된 쿼리 |

**Resources (리소스):**
- 서버가 클라이언트에게 읽기 전용 데이터를 제공
- `file:///path/to/file`, `postgres://db/table` 등 URI로 식별
- 애플리케이션이 사용자 동의하에 컨텍스트로 포함

**Tools (도구):**
- 가장 핵심적인 기능. LLM이 판단하여 호출할 수 있는 실행 가능한 함수
- 예: `create_github_issue`, `query_database`, `send_slack_message`
- JSON Schema로 파라미터 정의, LLM이 자동으로 파라미터를 채워 호출
- 부작용(Side Effect)이 있을 수 있으므로 사용자 승인 메커니즘 필요

**Prompts (프롬프트):**
- 서버가 제공하는 사전 정의된 프롬프트 템플릿
- 사용자가 명시적으로 선택하여 사용 (예: 슬래시 커맨드)

### 통신 방식

MCP는 **JSON-RPC 2.0** 기반으로 통신한다.

**Transport 종류:**

| Transport | 사용 시나리오 | 특징 |
|-----------|-------------|------|
| **stdio** | 로컬 프로세스 간 통신 | Host가 Server를 자식 프로세스로 실행, stdin/stdout으로 통신. 가장 일반적 |
| **Streamable HTTP** | 원격 서버 통신 | HTTP POST로 요청, SSE로 스트리밍 응답. 2025년 3월 스펙(2025-03-26)에서 도입 |
| ~~SSE~~ | ~~원격 서버 통신~~ | 2025-03-26 스펙에서 Deprecated. Streamable HTTP로 대체 |

**연결 수명주기:**

```
Client                          Server
  │                               │
  ├── initialize ────────────────→│  (버전, 기능 협상)
  │←─────────── initialize result─┤
  ├── initialized ───────────────→│  (확인)
  │                               │
  ├── tools/list ────────────────→│  (사용 가능한 도구 조회)
  │←──────────── tools/list result┤
  │                               │
  ├── tools/call ────────────────→│  (도구 실행 요청)
  │←──────────── tools/call result┤
  │                               │
  ├── shutdown ──────────────────→│  (종료)
  │                               │
```

### 기존 Function Calling과의 차이

| 비교 항목 | Function Calling (기존) | MCP |
|----------|------------------------|-----|
| **범위** | 특정 LLM API에 종속 | 모든 LLM/AI 앱에서 사용 가능한 표준 |
| **서버 측 구현** | 개발자가 직접 구현 | 커뮤니티가 만든 MCP Server 재사용 |
| **동적 발견** | 미리 정의된 함수 목록 고정 | 런타임에 사용 가능한 도구를 동적으로 발견 |
| **양방향 통신** | 요청-응답만 | Server→Client 알림(Notification)도 가능 |
| **생태계** | API별 격리 | 표준화된 생태계. 한 번 만든 Server를 여러 Host에서 사용 |

> Function Calling은 "LLM이 함수를 호출하는 인터페이스"이고, MCP는 "AI 앱과 외부 시스템을 연결하는 프로토콜"이다. MCP의 Tools 기능이 Function Calling을 포함하면서, 거기에 Resources, Prompts, 동적 발견, 표준화를 더한 것이다.

### 현재 생태계 (2025년 기준)

- **공식 SDK**: TypeScript, Python, Java, Kotlin, C# 등 주요 언어 지원
- **주요 MCP Server**: GitHub, Slack, Google Drive, PostgreSQL, Filesystem, Brave Search 등 수천 개
- **지원 Host**: Claude Desktop, Claude Code, Cursor, Windsurf, Cline, Continue 등
- **스펙 버전**: 2025-03-26 (Streamable HTTP 도입, SSE 폐기)

### 보안 고려사항

MCP는 강력한 기능을 제공하는 만큼 보안이 중요하다:

1. **최소 권한 원칙**: Server는 필요한 최소한의 권한만 요청해야 함
2. **사용자 동의**: Tool 실행 전 사용자 승인을 요구하는 것이 권장됨 (특히 Side Effect가 있는 작업)
3. **입력 검증**: Server는 모든 입력을 검증해야 함. LLM이 생성한 파라미터가 예상 범위를 벗어날 수 있음
4. **비밀 정보 관리**: API 키 등은 환경변수로 관리, MCP 메시지에 노출되지 않도록 주의
5. **Transport 보안**: 원격 통신 시 TLS 사용 필수

## 헷갈렸던 포인트

### Q: MCP Server는 별도의 서버를 운영해야 하는 건가?

아니다. **stdio 방식**에서는 MCP Host가 Server를 로컬 자식 프로세스로 실행한다. 별도의 서버 인프라가 필요 없다. `npx @modelcontextprotocol/server-github` 같은 명령어 하나로 실행되며, Host 앱이 시작/종료를 관리한다.

**원격 배포(Streamable HTTP)**의 경우에는 HTTP 서버로 운영해야 하지만, 이는 팀 내 공유 도구나 SaaS 통합 시에 사용하는 패턴이다.

### Q: MCP와 API Gateway/Plugin 시스템은 뭐가 다른가?

MCP는 **AI 모델이 동적으로 도구를 발견하고 호출**할 수 있도록 설계된 프로토콜이다.

- **API Gateway**: 사람이 미리 설정한 라우팅 규칙에 따라 요청 전달. 고정적
- **ChatGPT Plugins** (종료됨): OpenAI에 종속된 독자 생태계
- **MCP**: 모델/벤더에 종속되지 않는 오픈 표준. 어떤 AI 앱이든 MCP Client만 구현하면 모든 MCP Server 활용 가능

### Q: 모든 LLM API 호출을 MCP로 바꿔야 하는가?

아니다. MCP는 **AI 앱 ↔ 외부 도구/데이터** 연결에 대한 프로토콜이지, LLM API 자체를 대체하는 것이 아니다.

```
사용자 → AI 앱 → LLM API (Claude API 등)     ← 이건 MCP가 아님
                    ↕
              MCP Server (GitHub, DB 등)      ← 이건 MCP
```

LLM에게 "도구를 사용할 수 있는 능력"을 주는 것이 MCP의 역할이다.

### Q: MCP Server를 직접 만들어야 하는 경우는?

이미 공개된 MCP Server가 있는 서비스라면 그것을 사용하면 된다. 직접 만들어야 하는 경우:

1. **사내 시스템 연동**: 내부 API, 사내 DB 등 공개 MCP Server가 없는 경우
2. **커스텀 비즈니스 로직**: 단순 CRUD가 아닌 도메인 특화 로직이 필요한 경우
3. **기존 API 래핑**: 이미 있는 REST API를 AI가 사용할 수 있도록 MCP로 감싸는 경우

TypeScript/Python SDK를 사용하면 수십 줄로 기본적인 MCP Server를 구현할 수 있다.

## 참고 자료

- [MCP 공식 문서](https://modelcontextprotocol.io/) - 스펙, 가이드, SDK 문서
- [MCP GitHub Organization](https://github.com/modelcontextprotocol) - 공식 구현체, SDK, 예제
- [Introducing the Model Context Protocol (Anthropic 블로그)](https://www.anthropic.com/news/model-context-protocol) - MCP 발표 블로그
- [MCP Specification (2025-03-26)](https://spec.modelcontextprotocol.io/) - 최신 프로토콜 스펙
- [MCP Servers Directory](https://github.com/modelcontextprotocol/servers) - 공식/커뮤니티 MCP Server 목록
