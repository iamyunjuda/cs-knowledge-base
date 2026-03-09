# Rebase Merge vs Squash Merge — Git 병합 전략의 차이와 선택 기준

## 핵심 정리

Git에서 브랜치를 병합하는 방식은 크게 **Merge Commit**, **Rebase Merge**, **Squash Merge** 세 가지가 있다. 이 문서에서는 특히 헷갈리기 쉬운 **Rebase Merge**와 **Squash Merge**의 차이를 정리한다.

---

### 세 가지 병합 전략 비교

| 구분 | Merge Commit | Rebase Merge | Squash Merge |
|------|-------------|-------------|-------------|
| **커밋 히스토리** | 병합 커밋 생성, 브랜치 분기 이력 보존 | 커밋을 재배치, 일직선 히스토리 | 모든 커밋을 하나로 합쳐서 일직선 히스토리 |
| **개별 커밋 보존** | O | O | X (하나로 합쳐짐) |
| **병합 커밋 생성** | O | X | X |
| **커밋 해시 변경** | X (기존 커밋 유지) | O (새 해시로 재생성) | O (새 커밋 하나 생성) |
| **git log 모양** | 분기+합류 그래프 | 일직선 | 일직선 |

---

### 1. Merge Commit (기본 병합)

```
# 실행 방법
git checkout main
git merge feature
```

```
히스토리:
*   Merge branch 'feature'   ← 병합 커밋
|\
| * feature: commit 3
| * feature: commit 2
| * feature: commit 1
|/
* main: previous commit
```

- 가장 안전한 기본 전략
- 브랜치가 어디서 분기되어 어디서 합쳐졌는지 명확히 보임
- 히스토리가 복잡해질 수 있음 (여러 브랜치가 겹치면 그래프가 난잡)

---

### 2. Rebase Merge

```
# 실행 방법
git checkout feature
git rebase main        # feature의 커밋들을 main 위로 재배치
git checkout main
git merge feature      # fast-forward merge (일직선이므로)
```

```
히스토리 (rebase 전):
* feature: commit 3
* feature: commit 2
* feature: commit 1
| * main: new commit
|/
* 공통 조상

히스토리 (rebase 후 merge):
* feature: commit 3'   ← 해시가 바뀐 새 커밋
* feature: commit 2'
* feature: commit 1'
* main: new commit
* 공통 조상
```

**특징:**
- 개별 커밋이 **모두 보존**됨 (commit 1, 2, 3이 각각 남음)
- 커밋 해시가 변경됨 (원래 커밋을 main 최신 위에 **재생성**하기 때문)
- 병합 커밋 없이 **일직선** 히스토리
- 각 커밋의 변경 내용과 메시지를 개별적으로 추적 가능

**장점:**
- 깔끔한 일직선 히스토리
- 각 커밋 단위로 코드 리뷰/추적 가능
- `git bisect`로 버그 원인 커밋을 정밀하게 찾을 수 있음

**단점:**
- 커밋 해시가 바뀌므로 **이미 push한 브랜치에 rebase하면 위험** (`force push` 필요)
- 충돌 시 커밋 하나하나마다 충돌을 해결해야 할 수 있음
- 다른 사람과 공유 중인 브랜치에서 사용하면 혼란 발생

---

### 3. Squash Merge

```
# 실행 방법
git checkout main
git merge --squash feature
git commit -m "feat: 기능 X 구현"
```

```
히스토리 (squash 전):
| * feature: WIP 수정
| * feature: 오타 수정
| * feature: 기능 구현 중
| * feature: 초기 구현
|/
* main: previous commit

히스토리 (squash 후):
* feat: 기능 X 구현   ← 하나의 깔끔한 커밋
* main: previous commit
```

**특징:**
- feature 브랜치의 모든 커밋을 **하나의 커밋으로 합침**
- 개별 커밋 히스토리는 **사라짐**
- main 브랜치에는 깔끔한 단일 커밋만 남음

**장점:**
- 히스토리가 매우 깔끔 (기능 단위로 커밋 하나)
- "WIP", "오타 수정", "리뷰 반영" 같은 불필요한 커밋이 정리됨
- PR 단위로 변경사항을 한눈에 파악 가능

**단점:**
- 개별 커밋의 세부 변경 이력을 잃음
- 큰 기능의 경우 하나의 거대한 커밋이 됨 → `git bisect` 활용 어려움
- 원래 브랜치의 커밋 이력과 main의 이력이 **완전히 다른 커밋**이 되어 Git이 공통 이력을 인식하지 못함

---

## 헷갈렸던 포인트

### Q1. Rebase와 Squash 둘 다 일직선 히스토리를 만드는데, 핵심 차이는?

**A.** 커밋 보존 여부가 핵심이다.

| | Rebase Merge | Squash Merge |
|---|---|---|
| feature에 5개 커밋이 있으면 | main에 **5개 커밋**이 그대로 올라감 | main에 **1개 커밋**으로 합쳐서 올라감 |

- **Rebase**: 개별 커밋의 맥락(왜 이 변경을 했는지)이 보존
- **Squash**: 결과만 남고 과정은 사라짐

### Q2. "Rebase는 위험하다"고 하는 이유는?

**A.** Rebase는 커밋 해시를 변경하기 때문이다.

```
# 원래 커밋
abc1234 feature: commit 1

# rebase 후 (같은 내용이지만 다른 해시)
def5678 feature: commit 1
```

이미 원격에 push한 커밋을 rebase하면:
1. 로컬과 원격의 히스토리가 달라짐
2. `git push --force`가 필요해짐
3. 같은 브랜치에서 작업 중인 다른 개발자의 히스토리와 충돌

**규칙: 아직 push하지 않은 로컬 커밋에만 rebase를 사용하라.**

### Q3. Squash Merge 후 feature 브랜치를 계속 쓰면 문제가 생기나?

**A.** 그렇다. Squash Merge 후에는 feature 브랜치를 **반드시 삭제**해야 한다.

Squash Merge는 새로운 커밋을 생성하기 때문에, Git은 feature 브랜치의 원래 커밋들이 main에 반영되었다는 것을 알지 못한다. feature 브랜치에서 계속 작업 후 다시 merge하면 **이미 반영된 변경사항이 충돌**로 나타날 수 있다.

### Q4. GitHub/GitLab PR에서 "Squash and merge" 버튼은 뭘 하는 건가?

**A.** PR의 모든 커밋을 하나로 합쳐서 대상 브랜치에 병합한다.

```
PR 커밋들:
- fix: 버그 수정
- fix: 리뷰 반영
- fix: 오타 수정

"Squash and merge" 클릭 후 main에 생기는 커밋:
- feat: 로그인 기능 구현 (#42)   ← PR 제목이 커밋 메시지가 됨
```

대부분의 팀에서 PR 머지 시 가장 많이 사용하는 전략이다.

### Q5. 실무에서 어떤 전략을 써야 하나?

**A.** 팀 규모와 프로젝트 성격에 따라 다르다.

| 상황 | 추천 전략 | 이유 |
|------|----------|------|
| 소규모 팀, 커밋 습관이 좋음 | **Rebase Merge** | 깔끔한 히스토리 + 개별 커밋 추적 가능 |
| 대규모 팀, PR 기반 협업 | **Squash Merge** | PR 단위로 히스토리가 정리되어 관리 용이 |
| 오픈소스, 이력 보존 중요 | **Merge Commit** | 기여자의 모든 커밋 이력 보존, 안전함 |
| 커밋 메시지가 지저분한 팀 | **Squash Merge** | "WIP", "tmp" 같은 커밋이 정리됨 |
| 버그 추적이 중요한 서비스 | **Rebase Merge** | `git bisect` 활용하여 정밀한 버그 추적 가능 |

**실무에서 가장 흔한 조합:**
- **main 브랜치**: Squash Merge (PR 단위로 깔끔하게)
- **개인 작업 중**: Rebase (로컬에서 main 최신과 동기화할 때)
- **릴리스 브랜치**: Merge Commit (이력 보존이 중요하므로)

## 참고 자료

- [Git 공식 문서 — git-merge](https://git-scm.com/docs/git-merge)
- [Git 공식 문서 — git-rebase](https://git-scm.com/docs/git-rebase)
- [Atlassian — Merging vs. Rebasing](https://www.atlassian.com/git/tutorials/merging-vs-rebasing)
