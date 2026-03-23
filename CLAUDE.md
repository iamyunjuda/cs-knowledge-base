# CS Knowledge Base - Claude 지침서

## 이 저장소의 목적
헷갈리기 쉬운 CS 지식을 주제별로 정리하는 저장소입니다.

## 새 문서 추가 워크플로우

사용자가 새로운 CS 주제나 질문/답변을 요청하면 다음 절차를 따르세요:

### 1. 카테고리 판단
내용을 분석하여 아래 카테고리 중 적절한 곳에 배치합니다. 해당하는 카테고리가 없으면 새로 만듭니다.

모든 주제 폴더는 `topics/` 디렉토리 하위에 위치합니다.

현재 카테고리:
- `topics/java-jvm/` - Java 언어, JVM, 메모리, GC 등
- `topics/spring/` - Spring Framework, Spring Boot, Bean, AOP, 커넥션 풀, 트랜잭션 등
- `topics/network/` - HTTP, TCP/UDP, DNS, 네트워크 프로토콜 등
- `topics/os/` - 프로세스, 스레드, 동기/비동기, 운영체제 등
- `topics/database/` - SQL, 인덱스, 트랜잭션, DB 설계 등
- `topics/data-structure/` - 자료구조, 알고리즘 등
- `topics/infra/` - Kafka, Redis, Docker, 인프라 미들웨어 등
- `topics/blockchain/` - Web3, 이더리움, 지갑, 스마트 컨트랙트, DeFi, 합의 메커니즘(PoW/PoS), 키 관리(KMS/HSM/MPC), 모니터링, DB 스키마, VASP/거래소, ERC 토큰 표준, 풀노드 운영, dApp 개발 등
- `topics/frontend/` - React, 브라우저 렌더링, 번들링, 프론트엔드 기술 등
- `topics/design-pattern/` - 디자인 패턴, 아키텍처 등
- `topics/git/` - Git 명령어, 브랜치 전략, 병합 방식 등
- `topics/map-system/` - 공간 인덱싱, 지도 타일링, POI, 글로벌 로컬라이징, 지도 데이터 파이프라인 등

### 2. 마크다운 파일 생성
- 파일명: 주제를 영문 kebab-case로 (예: `garbage-collection.md`)
- 카테고리 디렉토리가 없으면 새로 생성

### 3. 문서 작성 포맷
```markdown
# 제목

## 핵심 정리
(주제에 대한 핵심 내용을 명확하게 정리)

## 헷갈렸던 포인트
(헷갈렸던 부분과 그 해답을 Q&A 형식으로 기록)

## 참고 자료
(있으면 링크 추가)
```

### 4. SUMMARY.md 목차 업데이트 (필수!)
문서를 추가/삭제/이동할 때마다 반드시 `SUMMARY.md`의 목차를 업데이트합니다.
- 새 카테고리가 생기면 섹션 추가
- 파일 경로와 제목이 정확히 일치하도록 링크 작성
- 카테고리 내에서 알파벳/가나다 순 정렬

### 5. 새 카테고리 추가 시
- 이 CLAUDE.md의 "현재 카테고리" 목록도 함께 업데이트
- SUMMARY.md에 새 섹션 추가
