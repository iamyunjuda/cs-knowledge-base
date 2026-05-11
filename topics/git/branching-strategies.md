---
title: Git 브랜치 전략 — Git Flow, GitHub Flow, Trunk-Based의 차이와 선택 기준
parent: Git
nav_order: 2
tags: [GitFlow, GitHubFlow, GitLabFlow, TrunkBased, 브랜치전략, 릴리스, CI/CD]
description: "Git Flow, GitHub Flow, GitLab Flow, Trunk-Based Development의 구조와 차이, 팀 규모·배포 주기·릴리스 방식에 따른 선택 기준을 정리합니다."
---


# Git 브랜치 전략 — Git Flow, GitHub Flow, Trunk-Based의 차이와 선택 기준

## 핵심 정리

브랜치 전략은 **릴리스 방식**과 **배포 주기**에 의해 결정된다. "어느 게 정답"이 아니라, 팀이 어떻게 배포하느냐에 맞춰 선택하는 것이 핵심이다.

| 전략 | 영구 브랜치 | 배포 주기 | 적합한 환경 |
|---|---|---|---|
| **Git Flow** | main + develop | 정기 릴리스 (주/월 단위) | 버전 관리되는 패키지, SDK, 모바일 앱 |
| **GitHub Flow** | main 하나 | 수시 배포 (하루 N회) | 단일 환경 SaaS, 웹 서비스 |
| **GitLab Flow** | main + 환경별(staging/production) | 환경별 승급 배포 | 스테이징 검증이 중요한 서비스 |
| **Trunk-Based** | main 하나 (단명 브랜치만) | 지속 배포 (하루 수십 회) | 대규모 팀, CI/CD 성숙 조직 |

---

## 1. Git Flow

2010년 Vincent Driessen이 제안한 가장 유명한 전략. 5종류의 브랜치를 운영한다.

```
main      ───●───────────●─────────●──   (릴리스된 버전만, 태그 부착)
              \         / \       /
release        \    ●──●   \  ●──●
                \  /        \ /
develop  ────●──●──●──●──●───●──●──   (다음 릴리스 통합 브랜치)
              \    /  /
feature/A      ●──●  /
feature/B          ●
                       \
hotfix/X     ───────────●─── (긴급 패치는 main에서 분기)
```

### 브랜치별 역할

| 브랜치 | 수명 | 분기 from | 머지 to |
|---|---|---|---|
| `main` | 영구 | - | - (릴리스 시점만 머지) |
| `develop` | 영구 | main (최초) | - |
| `feature/*` | 단명 | develop | develop |
| `release/*` | 단명 | develop | main + develop |
| `hotfix/*` | 단명 | main | main + develop |

### 흐름
1. **개발**: `feature/login` 브랜치를 develop에서 분기 → 작업 후 develop에 머지
2. **릴리스 준비**: develop이 안정화되면 `release/1.2.0` 브랜치 생성 → 버그 수정만 진행
3. **출시**: release 브랜치를 main과 develop에 머지, main에 `v1.2.0` 태그 부착
4. **긴급 패치**: 운영 중 버그 발생 시 `hotfix/critical-bug`를 main에서 분기 → main과 develop 둘 다에 머지

### 장점
- 어느 버전이 운영 중인지 main만 보면 명확
- 릴리스 직전에 별도 안정화 시간 확보 가능
- 여러 버전을 동시에 유지보수 가능 (v1.x, v2.x)

### 단점
- 브랜치가 5종류로 **복잡**
- 머지 충돌이 잦음 (develop ↔ main, hotfix를 두 곳에 머지 등)
- **CI/CD와 궁합이 나쁨**: 지속 배포 환경에서는 develop이 main과 자주 어긋남
- 작성자 본인도 [2020년에 "웹 서비스에는 더 이상 권장하지 않는다"고 발표](https://nvie.com/posts/a-successful-git-branching-model/)

---

## 2. GitHub Flow

GitHub에서 자사 운영을 위해 만든 단순한 전략. **main 하나만 영구 브랜치**.

```
main  ──●──●────●──●────●──●──   (항상 배포 가능 상태)
         \      \       /
feature   ●──●   ●──●──●
            \         /
PR + Review + CI 통과 후 머지
```

### 규칙
1. main은 **항상 배포 가능한 상태** 유지
2. 새 작업은 main에서 `feature/xxx` 브랜치 분기
3. PR을 열어 코드 리뷰 + CI 통과
4. 머지하면 즉시 또는 짧은 시간 내 배포

### 장점
- 단순 (브랜치 종류 1+1)
- 지속 배포(CD)와 자연스럽게 맞물림
- 충돌이 적음

### 단점
- 버전 개념이 약함 (태그로 보완)
- 릴리스 안정화 기간이 따로 없음 → main에 들어가기 전 충분한 테스트 필요
- 운영 환경이 여러 개면(staging/prod) 어떻게 분리할지 별도 약속 필요

---

## 3. GitLab Flow

GitHub Flow에 **환경별 브랜치**를 추가한 변형. 스테이징 검증이 필요한 팀에 적합.

```
main         ──●──●──●──●──●──   (개발 통합)
                \       \
pre-production   ●       ●       (QA 환경, main → 승급)
                  \       \
production         ●       ●     (운영, pre-prod → 승급)
```

### 흐름
1. feature → main 머지 (GitHub Flow와 동일)
2. main의 일부 커밋을 `pre-production` 브랜치에 머지 → 스테이징 배포
3. 검증 후 `production` 브랜치에 머지 → 운영 배포

### 특징
- "상류 우선(upstream first)" 원칙: 환경별 브랜치는 항상 main의 부분 집합
- 환경별 배포를 브랜치로 시각화
- 운영에 들어간 변경을 git log로 추적 가능

### 단점
- 환경이 늘어나면 브랜치 관리 비용 증가
- 환경 분리는 **태그 또는 CI/CD 파이프라인 변수**로 처리하는 게 더 일반적

---

## 4. Trunk-Based Development (TBD)

Google, Facebook, Netflix 등 빅테크가 쓰는 전략. **단명 브랜치만 허용**.

```
main  ──●─●──●─●──●─●─●──●──●──   (모두가 여기에 자주 머지)
         \    \    \   \
short     ●    ●    ●   ●   (≤ 1~2일 안에 머지)
```

### 핵심 원칙
1. 모든 개발자가 **하루에 한 번 이상** main에 머지
2. feature 브랜치는 **최대 1~2일**만 유지
3. 미완성 기능은 **Feature Flag**로 main에 머지하되 비활성화
4. main은 **항상 그린**(CI 통과 + 배포 가능) 상태

### 왜 효과적인가
- 머지 충돌의 근본 원인은 **분기 수명이 길어서**이다. 매일 머지하면 충돌이 사실상 사라짐
- CI/CD와 완전히 일체화: 머지 = 잠재적 배포
- 코드 리뷰가 **작은 단위**로 자주 일어남 → 리뷰 품질 향상
- DORA 보고서에서 고성과 조직의 공통 특성으로 지목

### 단점
- **Feature Flag 인프라**가 필수 (없으면 미완성 코드가 운영에 노출)
- 강력한 **CI 파이프라인**과 **자동화된 테스트** 없이는 불가능
- 작은 팀이나 신규 프로젝트에는 과한 셋업

---

## 전략 비교 한 줄 요약

| 전략 | 한 줄 요약 |
|---|---|
| Git Flow | "버전 출시"가 명확한 제품용. 복잡하지만 다중 버전 유지 가능 |
| GitHub Flow | 단순함의 정석. main 하나 + 짧은 feature 브랜치 |
| GitLab Flow | GitHub Flow + 환경별 브랜치로 배포 단계 시각화 |
| Trunk-Based | 매일 머지, Feature Flag로 미완성 코드 격리. 빅테크 표준 |

---

## 헷갈렸던 포인트

### Q1. Git Flow와 GitHub Flow를 어떻게 선택해야 하나?

**A.** "한 번에 운영되는 버전이 몇 개인가"로 판단한다.

| 상황 | 선택 |
|---|---|
| 모바일 앱(v1.2.0과 v2.0.0이 동시에 살아있음) | Git Flow |
| SDK/라이브러리(다중 버전 패치 필요) | Git Flow |
| 웹 서비스(항상 최신 1개만 운영) | GitHub Flow / Trunk-Based |
| SaaS B2B(스테이징 검증 필수) | GitLab Flow |

웹 서비스를 GitFlow로 운영하면 develop과 main이 점점 어긋나면서 머지 지옥에 빠진다. 이게 GitFlow 작성자조차 "웹에는 그만 쓰라"고 한 이유.

### Q2. Trunk-Based에서 미완성 기능은 어떻게 main에 머지하나?

**A.** **Feature Flag**(기능 플래그)를 쓴다. 코드는 머지되지만 런타임에 비활성화.

```kotlin
if (featureFlag.isEnabled("new-checkout-ui", userId)) {
    renderNewCheckout()
} else {
    renderOldCheckout()
}
```

장점:
- 미완성 기능을 main에 안전하게 머지 가능
- A/B 테스트, 점진적 롤아웃(1% → 10% → 100%)에 활용
- 장애 시 코드 롤백 없이 **플래그만 끄면** 즉시 복구

도구: LaunchDarkly, Unleash, Flagsmith, Spring Cloud Config, 자체 구현

### Q3. hotfix는 어떻게 처리하나?

**A.** 전략마다 다르다.

| 전략 | hotfix 처리 |
|---|---|
| Git Flow | `hotfix/*` 브랜치 → main + develop 양쪽에 머지 |
| GitHub Flow | 일반 PR과 동일하게 처리 (main 분기 → PR → 머지) |
| GitLab Flow | main에서 fix → pre-prod → prod로 승급 (또는 직접 prod로 cherry-pick) |
| Trunk-Based | 다른 변경과 동일하게 main 머지 + 빠른 배포 |

핵심: hotfix를 **다른 변경과 함께 묶지 마라**. 작은 단위로 분리해야 검증·롤백이 쉽다.

### Q4. 환경별로 브랜치를 두는 게 좋을까, 태그로 관리하는 게 좋을까?

**A.** 대부분의 경우 **태그 + CI/CD 변수**가 더 낫다.

브랜치로 환경을 관리하면:
- 환경 추가 = 브랜치 추가 + 머지 정책 추가
- "어느 커밋이 어느 환경에 있는지" 추적하려면 그래프 분석 필요
- 환경 간 동기화 누락 시 환경끼리 코드가 어긋남

태그/CI 파이프라인 변수로 관리하면:
- `v1.2.0` 태그 = 모든 환경에서 동일한 커밋
- 환경 차이는 **설정값**으로만 표현
- "운영에 있는 버전 = main의 어느 커밋"이 명확

GitLab Flow를 도입하더라도 **장기적으로는 태그/파이프라인 변수 방식으로 수렴**하는 경우가 많다.

### Q5. 모노레포에서는 어떤 전략이 적합한가?

**A.** **Trunk-Based**가 사실상 표준이다.

이유:
- 모노레포는 변경 빈도가 매우 높음 (여러 서비스가 한 레포)
- 브랜치를 오래 유지하면 충돌이 폭발적으로 늘어남
- Bazel/Turborepo 같은 빌드 시스템은 main 기준 캐시 활용을 가정

Google, Meta, Uber 모두 단일 trunk 기반으로 운영한다.

### Q6. 브랜치 보호(Protected Branch)는 어떻게 설정하나?

**A.** 어떤 전략을 쓰든 main은 반드시 보호한다.

권장 설정:
- **직접 push 금지** (PR을 통해서만 머지)
- **PR 머지 전 CI 통과 필수** (status check required)
- **최소 1명 이상 리뷰 승인 필요**
- **stale review 무효화** (새 커밋 시 이전 승인 무효)
- **Code Owners 지정** (특정 경로 변경 시 담당자 리뷰 필수)
- **force push 금지** (히스토리 변조 방지)

GitHub: Settings → Branches → Branch protection rules
GitLab: Settings → Repository → Protected branches

### Q7. 브랜치 명명 규칙은 어떻게 정해야 하나?

**A.** 팀 컨벤션을 정하는 게 핵심. 흔한 패턴:

```
feature/SHOP-123-add-payment-flow   # 작업 종류 / 이슈번호 / 설명
bugfix/login-timeout                # 버그 수정
hotfix/critical-checkout-error      # 긴급 패치
chore/upgrade-spring-boot           # 빌드/설정 변경
refactor/extract-user-service       # 리팩터링
release/1.2.0                       # 릴리스 준비 (Git Flow)
```

명명 규칙을 정해두면:
- 자동화 도구(Jira 연동, 배포 파이프라인 분기)가 쉬워짐
- 리뷰어가 PR 성격을 한눈에 파악

### Q8. 어떤 전략을 쓰든 공통으로 지켜야 할 것은?

**A.** 다음 5가지는 전략과 무관하게 적용된다.

1. **main은 항상 빌드/테스트 통과 상태 유지** (CI 그린)
2. **머지 전 PR 리뷰** (혼자 작업이라도 셀프 리뷰)
3. **커밋 메시지 컨벤션** (Conventional Commits 등)
4. **단명 브랜치 선호** (오래 묵힐수록 충돌 증가)
5. **force push는 본인 브랜치에서만** (공유 브랜치 절대 금지)

---

## 참고 자료

- [A successful Git branching model — Vincent Driessen (Git Flow 원문)](https://nvie.com/posts/a-successful-git-branching-model/)
- [GitHub Flow](https://docs.github.com/en/get-started/using-github/github-flow)
- [GitLab Flow](https://docs.gitlab.com/ee/topics/gitlab_flow.html)
- [Trunk Based Development](https://trunkbaseddevelopment.com/)
- [Google: Why Trunk-Based Development?](https://cloud.google.com/architecture/devops/devops-tech-trunk-based-development)
- [DORA — State of DevOps Reports](https://dora.dev/)
