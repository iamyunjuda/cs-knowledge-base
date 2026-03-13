---
title: "컨테이너 vs 가상머신 — Docker, Kubernetes, 그리고 왜 컨테이너인가"
parent: OS / 운영체제
nav_order: 9
---

# 컨테이너 vs 가상머신 — Docker, Kubernetes, 그리고 왜 컨테이너인가

## 핵심 정리

### 가상머신(VM)의 구조

```
┌───────────┐ ┌───────────┐ ┌───────────┐
│   App A   │ │   App B   │ │   App C   │
├───────────┤ ├───────────┤ ├───────────┤
│ Guest OS  │ │ Guest OS  │ │ Guest OS  │  ← 각각 완전한 OS
│ (Ubuntu)  │ │ (CentOS)  │ │ (Debian)  │
└─────┬─────┘ └─────┬─────┘ └─────┬─────┘
      └──────────────┼──────────────┘
              ┌──────┴──────┐
              │ Hypervisor  │  ← 하드웨어 가상화
              │(KVM/VMware) │
              ├─────────────┤
              │  Host OS    │
              ├─────────────┤
              │  Hardware   │
              └─────────────┘
```

- 각 VM마다 **완전한 OS 커널**을 포함 (수백 MB ~ 수 GB)
- Hypervisor가 하드웨어를 에뮬레이션
- 부팅 시간: **수십 초 ~ 분 단위**
- 강한 격리: 별도의 커널이므로 보안 경계가 명확

### 컨테이너(Container)의 구조

```
┌───────────┐ ┌───────────┐ ┌───────────┐
│   App A   │ │   App B   │ │   App C   │
├───────────┤ ├───────────┤ ├───────────┤
│  Libs/Bins│ │  Libs/Bins│ │  Libs/Bins│  ← 라이브러리만 포함
└─────┬─────┘ └─────┬─────┘ └─────┬─────┘
      └──────────────┼──────────────┘
              ┌──────┴──────┐
              │Container    │
              │Runtime      │  ← Docker/containerd
              │(runc)       │
              ├─────────────┤
              │ Host OS     │
              │ (커널 공유)  │  ← 단 하나의 Linux 커널
              ├─────────────┤
              │  Hardware   │
              └─────────────┘
```

- 모든 컨테이너가 **호스트의 커널을 공유**
- OS 없이 애플리케이션 + 의존성만 패키징 (수 MB ~ 수백 MB)
- 시작 시간: **밀리초 ~ 수 초**
- 커널의 Namespace + cgroups로 격리

### 핵심 비교

| 구분 | 가상머신 (VM) | 컨테이너 (Container) |
|------|-------------|---------------------|
| **격리 수준** | 하드웨어 레벨 (강함) | 프로세스 레벨 (상대적으로 약함) |
| **커널** | 각각 독립 커널 | 호스트 커널 공유 |
| **이미지 크기** | GB 단위 | MB 단위 |
| **시작 시간** | 분 단위 | 초 ~ 밀리초 |
| **리소스 오버헤드** | 크다 (Guest OS 메모리) | 작다 (프로세스 수준) |
| **밀도** | 1대 서버에 수십 개 | 1대 서버에 수백 ~ 수천 개 |
| **이식성** | 하이퍼바이저 의존 | OCI 표준으로 어디서든 실행 |

### 커널이 컨테이너를 만드는 방법

#### 1. Namespace — "뭘 볼 수 있는가"를 격리

```
호스트 PID 목록:  PID 1(systemd), PID 100(dockerd), PID 200(nginx), PID 201(worker)

컨테이너 A가 보는 세상:  PID 1(nginx), PID 2(worker)  ← PID Namespace
컨테이너 B가 보는 세상:  PID 1(java), PID 2(thread)   ← 별도의 PID Namespace
```

| Namespace 종류 | 격리 대상 |
|---------------|----------|
| **PID** | 프로세스 ID (컨테이너 내부에서 PID 1부터 시작) |
| **Network** | 네트워크 인터페이스, IP, 포트, 라우팅 테이블 |
| **Mount** | 파일 시스템 마운트 포인트 |
| **UTS** | 호스트명 |
| **IPC** | System V IPC, POSIX 메시지 큐 |
| **User** | UID/GID (컨테이너 내 root ≠ 호스트 root) |
| **Cgroup** | cgroup 루트 디렉토리 |

#### 2. cgroups — "얼마나 쓸 수 있는가"를 제한

```yaml
# Docker에서의 리소스 제한
docker run --cpus="2.0" --memory="512m" --memory-swap="1g" nginx
```

- **CPU**: 사용 가능한 CPU 코어 수, CPU 시간 비율
- **Memory**: 최대 메모리, swap 제한 → 초과 시 OOM Kill
- **Block I/O**: 디스크 읽기/쓰기 속도 제한
- **Network**: 대역폭 제한 (tc와 결합)

#### 3. OverlayFS — 이미지 레이어 시스템

```
┌─────────────────────┐
│  Container Layer    │  ← 쓰기 가능 (변경사항만 저장)
├─────────────────────┤
│  App Layer          │  ← 읽기 전용 (COPY app.jar)
├─────────────────────┤
│  JDK Layer          │  ← 읽기 전용 (RUN apt install openjdk)
├─────────────────────┤
│  Base Image Layer   │  ← 읽기 전용 (FROM ubuntu:22.04)
└─────────────────────┘
```

- 여러 읽기 전용 레이어 위에 하나의 쓰기 가능 레이어를 올림
- 같은 베이스 이미지를 쓰는 컨테이너들은 레이어를 **공유** → 디스크 절약

### 왜 컨테이너를 선호하는가? — 실무 관점

#### 1. 개발-배포 일관성
```
"내 로컬에서는 되는데요?" → 컨테이너로 해결
```
Dockerfile로 환경을 코드화하면 개발/스테이징/프로덕션 환경이 동일하다.

#### 2. 마이크로서비스에 최적
- VM: 서비스 하나에 OS 하나 → 리소스 낭비
- 컨테이너: 서비스 하나에 프로세스 하나 → 경량, 독립 배포 가능

#### 3. 빠른 스케일링
```
VM 스케일 아웃: OS 부팅 → 설정 → 앱 시작 (수 분)
컨테이너 스케일 아웃: 컨테이너 시작 (수 초)
```
K8s HPA(Horizontal Pod Autoscaler)가 트래픽에 따라 자동으로 Pod를 늘리고 줄인다.

#### 4. 효율적인 리소스 사용
- 동일 서버에서 VM 10개 vs 컨테이너 100개 실행 가능
- Guest OS의 메모리/CPU 오버헤드가 없다

#### 5. 불변 인프라 (Immutable Infrastructure)
- 서버를 "수정"하지 않고 새 이미지를 빌드해서 교체
- 롤백이 이전 이미지 태그로 배포하는 것만큼 간단

### Docker와 Kubernetes의 관계

```
Docker: 컨테이너를 "만들고 실행"하는 도구
Kubernetes: 컨테이너를 "운영하고 관리"하는 오케스트레이터

[Kubernetes]
├── Node 1
│   ├── Pod (Container A + Sidecar)
│   ├── Pod (Container B)
│   └── kubelet + containerd  ← 실제 컨테이너 런타임
├── Node 2
│   ├── Pod (Container A replica)
│   └── Pod (Container C)
└── Control Plane
    ├── API Server
    ├── Scheduler       ← 어떤 Node에 Pod를 배치할지
    ├── Controller Manager
    └── etcd            ← 클러스터 상태 저장
```

K8s가 컨테이너 환경에서 하는 일:
- **자동 배포/롤백**: 새 버전 배포 시 Rolling Update, 문제 시 자동 롤백
- **자동 복구**: Pod가 죽으면 자동 재시작/재배치
- **오토스케일링**: HPA/VPA/Cluster Autoscaler
- **서비스 디스커버리**: DNS 기반 서비스 이름 해석
- **설정 관리**: ConfigMap, Secret

## 헷갈렸던 포인트

### Q1: 컨테이너가 커널을 공유하면 보안이 취약하지 않나?

**맞다. VM보다 격리가 약하다.** 그래서 보완책이 존재한다:

| 보완 기술 | 설명 |
|----------|------|
| **seccomp** | 사용 가능한 시스템 콜 제한 (Docker 기본 적용) |
| **AppArmor/SELinux** | 강제 접근 제어 |
| **Rootless Container** | 컨테이너를 비-root 유저로 실행 |
| **gVisor** | 유저 스페이스 커널로 시스템 콜 가로채기 |
| **Kata Containers** | 경량 VM 안에서 컨테이너 실행 (VM급 격리 + 컨테이너 편의성) |

금융/의료처럼 강한 격리가 필요한 환경에서는 **Kata Containers**나 **Firecracker**(AWS Lambda가 사용)처럼 microVM을 사용하기도 한다.

### Q2: Docker는 Linux에서만 되나? macOS/Windows에서는?

Docker는 **Linux 커널 기능(Namespace, cgroups)** 에 의존한다.

- **macOS**: 내부적으로 경량 Linux VM(LinuxKit)을 실행하고 그 위에서 컨테이너 구동
- **Windows**: WSL2(Windows Subsystem for Linux 2)의 Linux 커널 위에서 컨테이너 구동
- 즉, macOS/Windows에서도 결국 **Linux 커널 위에서** 컨테이너가 돌아간다

### Q3: "컨테이너 = Docker"인가?

**아니다.** Docker는 컨테이너 기술의 대중화를 이끌었지만, 컨테이너 런타임은 여러 가지다:

| 런타임 | 설명 |
|-------|------|
| **containerd** | Docker에서 분리된 산업 표준 런타임 (K8s 기본) |
| **CRI-O** | K8s 전용 경량 런타임 (Red Hat 주도) |
| **runc** | OCI 표준 구현체, 실제 컨테이너 생성 담당 |
| **Podman** | Docker 호환, 데몬리스, Rootless 기본 지원 |

K8s 1.24부터 **dockershim이 제거**되어 containerd/CRI-O를 직접 사용한다.

## 참고 자료

- [Docker 공식 문서 — Container Overview](https://docs.docker.com/get-started/overview/)
- [Kubernetes 공식 문서 — Concepts](https://kubernetes.io/docs/concepts/)
- [Linux Namespaces — man7.org](https://man7.org/linux/man-pages/man7/namespaces.7.html)
