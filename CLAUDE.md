# CS Knowledge Base - Claude 지침서

## 이 저장소의 목적
헷갈리기 쉬운 CS 지식을 주제별로 정리하는 저장소입니다.

## 새 문서 추가 워크플로우

사용자가 새로운 CS 주제나 질문/답변을 요청하면 다음 절차를 따르세요:

### 1. 카테고리 판단
내용을 분석하여 아래 카테고리 중 적절한 곳에 배치합니다. 해당하는 카테고리가 없으면 새로 만듭니다.

현재 카테고리:
- `java-jvm/` - Java 언어, JVM, 메모리, GC 등
- `spring/` - Spring Framework, Spring Boot, Bean, AOP, 커넥션 풀, 트랜잭션 등
- `network/` - HTTP, TCP/UDP, DNS, 네트워크 프로토콜 등
- `os/` - 프로세스, 스레드, 동기/비동기, 운영체제 등
- `database/` - SQL, 인덱스, 트랜잭션, DB 설계 등
- `data-structure/` - 자료구조, 알고리즘 등
- `infra/` - Kafka, Redis, Docker, 인프라 미들웨어 등
- `blockchain/` - Web3, 이더리움, 지갑, 스마트 컨트랙트, DeFi, 합의 메커니즘(PoW/PoS), 키 관리(KMS/HSM/MPC), 모니터링, DB 스키마, VASP/거래소, ERC 토큰 표준, 풀노드 운영, dApp 개발 등
- `design-pattern/` - 디자인 패턴, 아키텍처 등
- `git/` - Git 명령어, 브랜치 전략, 병합 방식 등
- `map-system/` - 공간 인덱싱, 지도 타일링, POI, 글로벌 로컬라이징, 지도 데이터 파이프라인 등

### 2. 마크다운 파일 생성
- 파일명: 주제를 영문 kebab-case로 (예: `garbage-collection.md`)
- 카테고리 디렉토리가 없으면 새로 생성

### 3. Jekyll front matter 작성 (필수! 빠뜨리면 블로그 메뉴에 안 보임!)

이 저장소는 `just-the-docs` Jekyll 테마로 블로그에 배포됩니다.
**모든 마크다운 파일에 반드시 YAML front matter를 작성해야 합니다.**
front matter가 없으면 블로그 사이드바 메뉴와 검색에 노출되지 않습니다.

#### 카테고리 인덱스 파일 (`<카테고리>/index.md`)
새 카테고리를 만들 때 반드시 해당 디렉토리에 `index.md`를 생성합니다.
```markdown
---
title: <카테고리 표시명>
nav_order: <숫자>
has_children: true
---

# <카테고리 표시명>

<카테고리 설명 한 줄>
```

현재 nav_order 배정:
| nav_order | 카테고리 |
|-----------|---------|
| 1 | Java / JVM |
| 2 | Network |
| 3 | Database |
| 4 | OS / 운영체제 |
| 5 | Infra / 인프라 미들웨어 |
| 6 | Blockchain / Web3 |
| 7 | Spring |
| 8 | Design Pattern / 설계 패턴 |
| 9 | Git |
| 10 | Map System / 지도 시스템 |

#### 개별 문서 파일
```markdown
---
title: "문서 제목"
parent: <카테고리 index.md의 title과 정확히 동일>
nav_order: <카테고리 내 순번>
tags: [키워드1, 키워드2, 키워드3]
description: "구글 검색 스니펫에 노출될 1~2문장 요약 (최대 160자)"
---
```
- `parent` 값은 해당 카테고리 `index.md`의 `title`과 **글자 하나까지 정확히** 일치해야 합니다
- `tags`에는 검색 편의를 위한 한/영 키워드를 넣습니다 (예: `[HikariCP, 커넥션풀, Spring Boot, 슬로우쿼리]`)
- `description`은 `jekyll-seo-tag`가 `<meta name="description">`으로 변환합니다. **구글 검색 결과 스니펫에 직접 노출**되므로 핵심 내용을 160자 이내로 요약합니다

### 4. 문서 본문 작성 포맷
```markdown
# 제목

## 핵심 정리
(주제에 대한 핵심 내용을 명확하게 정리)

## 헷갈렸던 포인트
(헷갈렸던 부분과 그 해답을 Q&A 형식으로 기록)

## 참고 자료
(있으면 링크 추가)
```

### 5. README.md 인덱스 업데이트 (필수!)
문서를 추가/삭제/이동할 때마다 반드시 `README.md`의 목차를 업데이트합니다.
- 새 카테고리가 생기면 섹션 추가
- 파일 경로와 제목이 정확히 일치하도록 링크 작성
- 카테고리 내에서 알파벳/가나다 순 정렬

### 6. 새 카테고리 추가 시
- 해당 디렉토리에 `index.md` 생성 (3번 참고, **빠뜨리면 메뉴에 안 보임!**)
- 이 CLAUDE.md의 "현재 카테고리" 목록 및 nav_order 테이블 업데이트
- README.md에 새 섹션 추가
