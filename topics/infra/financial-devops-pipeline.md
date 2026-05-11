---
title: 금융 규제 환경의 DevOps 파이프라인 — 카카오뱅크 사례로 보는 결재·접근제어·망분리
parent: Infra
nav_order: 4
tags: [DevOps, GitOps, 금융규제, 카카오뱅크, CI/CD, GitLab, Terraform, Kaniko, Buildkit, OIDC, 망분리, 망연계]
description: "전자금융감독규정 환경에서 결재/증적, 접근제어, 망분리 규제를 개발자 친화적인 데브옵스 파이프라인으로 풀어낸 카카오뱅크 사례를 정리합니다."
---


# 금융 규제 환경의 DevOps 파이프라인 — 카카오뱅크 사례로 보는 결재·접근제어·망분리

## 핵심 정리

금융 규제는 흔히 개발자 생산성과 충돌하는 것으로 여겨지지만, **규제가 추구하는 가치**(투명성, 통제, 격리)를 잘 들여다보면 이미 개발 워크플로우(코드 리뷰, 버전 관리, 권한 분리)와 지향점이 닮아 있다. 카카오뱅크는 이 점을 활용해 GitOps 기반 파이프라인을 구축, 규제 준수와 개발 생산성을 동시에 잡았다.

3가지 축:

| 규제 영역 | 핵심 도전 | 해결 방식 |
|---|---|---|
| **결재 / 증적** | 변경 권한 분리 + 모든 변경 기록 | GitOps(Terraform + GitLab MR Approval + Codeowners) |
| **접근제어** | 컨테이너 빌드/배포 시 과도한 권한 | Daemonless 빌드(Kaniko → Buildkit), GitLab CI/CD ↔ AWS OIDC ID Token |
| **망분리** | 외부망 개발 / 내부망 운영 분리 | 망별 GitLab Enterprise + 망연계 파이프라인 |

---

## 1. 결재 / 증적 — GitOps로 풀어낸 변경 통제

### 문제
- 금융 규제: 개인에게 과도한 권한 부여 금지(결재), 모든 변경 기록 의무(증적)
- 과거 카카오뱅크: 형상관리시스템(GitLab) 변경을 **ITSM 결재 시스템**을 통해 요청 → DevOps 엔지니어가 수작업으로 GitLab에 반영
- 결과: 개발자가 ITSM 결재 대기 동안 작업 흐름 단절, 데브옵스 엔지니어가 병목

### 해결: GitOps로 변경 자체를 결재 프로세스에 동기화

**Terraform(IaC) + GitLab CI/CD** 조합:

1. 인프라/시스템 변경을 Terraform 코드로 작성
2. Git에 푸시 → **Merge Request 생성** (= 결재 상신)
3. **Merge Request Approval** 기능으로 승인 (= 결재)
4. 머지되면 CI/CD가 Terraform apply 수행 (= 변경 반영)
5. Git 히스토리에 모든 변경이 자동 기록 (= 증적)

```
[Developer] ─push─→ [GitLab MR] ─approve─→ [CI/CD: terraform apply]
                       │                          │
                       └── 결재 기록              └── 변경 증적
```

### Codeowners로 결재선 분기
변경 대상 파일에 따라 승인자를 다르게 지정해야 하는 경우, GitLab의 **`CODEOWNERS`** 기능 활용:

```
# CODEOWNERS 예시
/infra/prod/      @sre-team @security-team
/infra/dev/       @platform-team
/services/billing/ @billing-owners
```
파일이 변경되면 해당 소유자의 승인이 필수 → 결재선 자동 분기.

### 인사이트
> "코드 리뷰 ≈ 결재, 버전 관리 ≈ 증적"
> 규제의 목적과 개발 워크플로우의 지향점이 이미 맞닿아 있다.

---

## 2. 접근제어 — Daemonless 빌드 + OIDC 페더레이션

### 2-1. 컨테이너 빌드 권한 문제

**문제**: Docker Daemon 기반 빌드는 호스트 권한 노출
- 컨테이너에서 이미지를 빌드하려면 호스트의 `docker.sock`에 마운트 필요
- 컨테이너 ↔ 호스트 격리가 깨지고 **특수 권한**(privileged) 발생
- 클라우드 노드 보안 규정이 명확하지 않던 시점에도 잠재 위협으로 인식

**해결 과정**:
1. Daemonless 빌드 도구 탐색 — Kaniko, Jib, Buildkit
2. **Kaniko** 우선 도입 (Google Container Tools, GitLab 공식 가이드)
3. Java/Kotlin은 **Jib** 병행 (Dockerfile 없이 플러그인만으로 빌드)
4. Kaniko 2년 운영 중 빌드 실패/중단 이슈 → **Buildkit 데몬리스 스크립트**로 전환

**Buildkit 데몬리스의 강점**:
- 내부에서 데몬을 실행하되 외부엔 데몬이 없는 것처럼 추상화
- Docker 공식 빌드 모듈이라 **검증된 안정성**
- 부수 효과: 쿠버네티스 1.24의 dockershim 제거 이슈도 자동 해결

### Daemonless 빌드 도구 비교

| 도구 | 특징 | 한계 |
|---|---|---|
| **Kaniko** | 커뮤니티 인지도 높음, GitLab 공식 가이드 | 빌드 실패/중단이 가끔 발생 |
| **Jib** | Java/Kotlin 전용, Dockerfile 불필요 | 자바 생태계로 제한 |
| **Buildkit (daemonless)** | Docker 공식, 안정성 검증 | 스크립트 추상화 이해 필요 |

---

### 2-2. AWS 리소스 접근 — OIDC ID Token 방식

**문제**: CI/CD 파이프라인이 AWS 인프라를 프로비저닝하려면 광범위한 권한 필요. 어떻게 안전하게 부여할 것인가?

**시도된 방안 변천사**:

1. **IAM Access Key** → 키를 주기적으로 회전해야 하고, 노출되면 치명적. 탈락.
2. **GitLab Runner 분리 + IRSA(IAM Roles for Service Accounts)** → 파이프라인별로 Runner를 만들어 EKS 서비스 어카운트에 IAM Role 부여. 그러나 Runner가 계속 늘어나 유지보수 비용 폭증.
3. **GitLab CI/CD ↔ AWS OIDC (ID Token 방식)** → 최종 채택.

### OIDC ID Token 흐름

```
[GitLab CI/CD Job] ─(short-lived JWT)─→ [AWS STS AssumeRoleWithWebIdentity]
                                              │
                                              └─→ 임시 자격증명 발급 (15분~)
```

- GitLab이 발급한 **단명 JWT**를 AWS IAM이 신뢰
- AWS는 ID Token을 검증 후 **단명 자격증명** 발급 (장기 키 불필요)
- 외부 인터넷 접근은 **GitLab 퍼블릭 엔드포인트에 WAF**를 두어 AWS IAM IP 대역과 함께 통제

**개선 효과**:
- 장기 액세스 키 0개
- Runner 다수 운영 부담 해소
- 파이프라인별 권한을 IAM Role 기반으로 세밀하게 분리

---

## 3. 망분리 / 망연계 — 외부망 개발 ↔ 내부망 운영

### 카카오뱅크의 망 구조

- **경영망(외부망)**: 개발자가 개발 작업 수행
- **금융망(내부망, FIN)**: 실제 서비스 운영
- 두 망 사이는 물리적/논리적으로 분리되어 직접 통신 불가
- 외부망에서 만든 소스/이미지를 내부망으로 **망연계**(transfer) 필요

### 과거 방식의 한계

자체 구현 GitLab 동기화 시스템:
- 제3자 검증을 위해 **MR 생성자 ≠ 머지 수행자**일 때만 동기화 이벤트 발생
- 동기화 시 **전체 리포지터리 복제** → 대용량 레포에서 망간 네트워크 통제 시스템에 지연

### 개선: GitLab Enterprise 망별 설치 + 클라우드 구축

1. AWS에 **망별 GitLab Enterprise**를 각각 구축 (경영망용 / 금융망용)
2. GitLab Enterprise의 망간 동기화 기능으로 PoC → 성능/통제 이슈 해결
3. 클라우드에 GitLab을 둠으로써 **자체 데이터센터 장애 시 빠른 복원** 부가 효과
4. 컨테이너 레지스트리 인증 리다이렉션 문제 해결로 망간 이미지 전달 안정화

### 결과
망분리 규정을 준수하면서도 개발자가 외부망에서 자유롭게 작업하고, 검증된 산출물이 내부망으로 자동 흘러가는 파이프라인 완성.

---

## 헷갈렸던 포인트

### Q1. GitOps와 단순 "CI/CD에서 Terraform 돌리기"는 뭐가 다른가?

**A.** GitOps는 **Git을 단일 진실 공급원(Single Source of Truth)**으로 삼는다는 점에서 다르다.

- 일반 CI/CD: Git은 빌드 트리거 중 하나일 뿐
- GitOps: 실제 시스템 상태가 Git에 선언된 상태와 **항상 일치**해야 함 (drift 감지/교정 포함)

카카오뱅크 사례는 결재/증적 요구사항을 GitOps 패턴으로 자연스럽게 해결한 사례. **모든 변경이 Git에 기록되고 승인을 거친다는 점**이 곧 규제 충족.

### Q2. Codeowners와 일반 리뷰어 지정의 차이는?

**A.** Codeowners는 **파일 경로별 강제 승인자**다.

| 항목 | Reviewer | Codeowner |
|---|---|---|
| 지정 방식 | PR마다 수동 | 파일 경로 패턴으로 사전 정의 |
| 강제력 | 권고 | (설정 시) 머지 차단까지 가능 |
| 용도 | 일반 리뷰 | 보안/규제 영역 변경 통제 |

`/infra/prod/`처럼 민감한 경로에 Codeowner를 지정하면, 누가 PR을 올리든 해당 팀의 승인 없이는 변경 불가 → 결재선 자동화.

### Q3. Daemonless 빌드가 정확히 무엇을 격리하는가?

**A.** 호스트의 Docker Daemon에 대한 의존을 끊는다.

```
[전통적]                          [Daemonless]
Container Job                    Container Job
   │ mount docker.sock              │ (no host socket)
   ▼                                ▼
Host Docker Daemon              내부 빌드 로직 자체 실행
   │ (호스트 권한 노출)             │
   ▼                                ▼
이미지 빌드                       이미지 빌드
```

격리 포인트:
- **호스트 권한 차단**: privileged 컨테이너 / docker.sock 마운트 불필요
- **공급망 보안 향상**: 빌드 환경이 호스트와 분리
- **CI 환경 표준화**: K8s 1.24 이후 dockershim 제거 환경에서도 동작

### Q4. AWS IAM Access Key, IRSA, OIDC ID Token 중 무엇을 써야 하나?

**A.** 최신 모범 사례는 **OIDC ID Token(=Web Identity Federation)**.

| 방식 | 자격 형태 | 회전 부담 | 보안 | 권장도 |
|---|---|---|---|---|
| **Access Key** | 장기 키 | 수동/주기 회전 필요 | 낮음(노출 시 치명적) | 비권장 |
| **IRSA** (EKS) | K8s SA → IAM Role | 자동 단명 | 높음 | EKS 안쪽 워크로드에 적합 |
| **OIDC ID Token** | 단명 JWT → STS AssumeRole | 자동 단명 | 높음 | CI/CD 등 외부 시스템에 최적 |

GitHub Actions, GitLab CI/CD, CircleCI 모두 OIDC 페더레이션을 지원 → **장기 액세스 키를 코드/시크릿에 박지 마라**.

### Q5. 망분리 환경에서 GitLab을 망별로 두는 게 왜 효과적인가?

**A.** "망연계는 게이트로, 작업은 로컬로" 원칙이다.

만약 GitLab 하나만 외부망에 두고 내부망 운영자가 매번 접근하려 하면:
- 망간 트래픽 폭증
- 망연계 시스템이 병목
- 내부망 운영자도 외부망 인증을 거쳐야 하는 보안 이슈

망별 GitLab을 두면:
- 각 망 내부에서 빠른 read/write
- 망간엔 **검증된 산출물만** 단방향으로 흘러감
- 망연계 트래픽 최소화 + 제3자 검증 포인트 명확

### Q6. "규제 준수 + 개발 친화"가 정말 양립 가능한가?

**A.** 카카오뱅크 사례의 가장 큰 시사점이 바로 이 지점이다.

발표자(서신혁 팀장)의 표현:
> "규제의 추구 가치가 무엇인지를 이해하면 그 가치에 부합하는 기술이 어딘가에는 있다."

| 규제 요구 | 개발 워크플로우 대응 |
|---|---|
| 결재(권한 분리) | MR Approval, Codeowners |
| 증적(변경 기록) | Git 히스토리, 커밋 메시지 |
| 접근제어 | OIDC 페더레이션, RBAC |
| 망분리 | 망별 시스템 + 자동 망연계 |

→ 규제를 "추가 작업"이 아니라 **워크플로우 자체에 녹여 넣으면** 개발자는 평소처럼 일하면서 자연히 규제를 준수하게 된다.

---

## 정리: 규제 친화적 DevOps 파이프라인 설계 원칙

1. **수동 결재를 자동 결재로**: ITSM 티켓 대신 MR Approval. 결재 = 머지.
2. **변경의 단일 진실 공급원은 Git**: 모든 변경이 Git을 거치면 증적은 자동.
3. **권한은 단명 토큰으로**: 장기 자격증명을 시스템에 박지 말 것.
4. **빌드 환경은 격리**: Daemonless 빌드로 호스트 권한 노출 차단.
5. **망 경계는 시스템 분리 + 자동 연계**: 사람이 두 망을 오가지 않도록.
6. **규제의 목적부터 이해**: "왜"를 알면 기존 개발 패턴 안에 답이 있다.

---

## 참고 자료

- [원문 — 바이라인네트워크: 금융회사 개발자가 규제 걱정없이 행복 코딩하려면(feat.카뱅)](https://byline.network/2024/10/31-219/)
- [GitLab — Merge Request Approvals](https://docs.gitlab.com/ee/user/project/merge_requests/approvals/)
- [GitLab — CODEOWNERS](https://docs.gitlab.com/ee/user/project/codeowners/)
- [GitLab — OIDC with AWS](https://docs.gitlab.com/ee/ci/cloud_services/aws/)
- [Kaniko — Build Container Images In Kubernetes](https://github.com/GoogleContainerTools/kaniko)
- [BuildKit — Daemonless Build](https://github.com/moby/buildkit#expose-buildkit-as-a-tcp-service)
- [Jib — Build container images for Java](https://github.com/GoogleContainerTools/jib)
- [전자금융감독규정 (금융감독원)](https://www.law.go.kr/행정규칙/전자금융감독규정)
