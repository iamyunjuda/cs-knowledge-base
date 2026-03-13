---
title: "운영체제 구조와 커널(Kernel) 심화"
parent: OS / 운영체제
nav_order: 5
tags: [커널, Kernel, 유저모드, 커널모드, Ring, Monolithic, Microkernel, 컨테이너]
description: "유저 모드 vs 커널 모드, CPU Ring 구조, 커널 구성 요소, Monolithic vs Microkernel, Linux 커널과 컨테이너 기술의 관계를 정리합니다."
---

# 운영체제 구조와 커널(Kernel) 심화

## 핵심 정리

### 컴퓨터 구조 전체 그림

```
┌─────────────────────────────────────────────┐
│              Application (User Process)      │
├─────────────────────────────────────────────┤
│              System Call Interface            │  ← 유저 공간과 커널의 경계
├─────────────────────────────────────────────┤
│                  Kernel                      │
│  ┌──────────┬──────────┬──────────────────┐  │
│  │ Process  │ Memory   │ File System      │  │
│  │ Manager  │ Manager  │ Manager          │  │
│  ├──────────┼──────────┼──────────────────┤  │
│  │ Device   │ Network  │ IPC              │  │
│  │ Driver   │ Stack    │ (Inter-Process)  │  │
│  └──────────┴──────────┴──────────────────┘  │
├─────────────────────────────────────────────┤
│              Hardware (CPU, RAM, Disk, NIC)   │
└─────────────────────────────────────────────┘
```

### 유저 모드 vs 커널 모드

CPU는 **Ring 구조**로 권한 수준을 나눈다:

| 구분 | Ring 0 (커널 모드) | Ring 3 (유저 모드) |
|------|-------------------|-------------------|
| **권한** | 모든 하드웨어 접근 가능 | 제한된 메모리/명령만 사용 |
| **실행 주체** | 커널 코드, 디바이스 드라이버 | 일반 애플리케이션 |
| **메모리** | 전체 주소 공간 접근 | 프로세스 가상 주소 공간만 |
| **전환 비용** | — | System Call 시 Context Switch 발생 |

```
[Application]  →  open("/tmp/file")
                     │
                     ▼ (System Call: Trap)
[Kernel Mode]  →  VFS → ext4 → Block I/O → Disk Driver
                     │
                     ▼ (결과 반환)
[Application]  ←  file descriptor (fd=3)
```

### 커널의 핵심 구성 요소

#### 1. 프로세스 관리 (Process Management)
- **프로세스 생성**: `fork()` → 부모 프로세스 복제, `exec()` → 새 프로그램 로드
- **스케줄링**: CFS(Completely Fair Scheduler), 타임 슬라이스 기반
- **프로세스 상태**: Running → Ready → Waiting → Terminated
- **스레드**: 같은 프로세스 내 메모리 공간 공유, 경량 실행 단위

#### 2. 메모리 관리 (Memory Management)
- **가상 메모리**: 프로세스마다 독립된 가상 주소 공간 제공
- **페이징**: 4KB 단위 페이지로 물리 메모리 매핑
- **Page Fault**: 접근한 페이지가 물리 메모리에 없을 때 디스크에서 로드
- **Copy-on-Write (COW)**: fork() 시 실제 쓰기가 발생할 때까지 메모리 복사 지연

```
[Process A의 가상 메모리]          [물리 메모리]
0x0000 - Code    ──────────→  물리 주소 0x1000
0x1000 - Heap    ──────────→  물리 주소 0x5000
0x7000 - Stack   ──────────→  물리 주소 0x3000

[Process B의 가상 메모리]
0x0000 - Code    ──────────→  물리 주소 0x8000  (완전히 독립!)
0x1000 - Heap    ──────────→  물리 주소 0x9000
```

#### 3. 파일 시스템 (File System)
- **VFS (Virtual File System)**: 통일된 파일 인터페이스 제공
- ext4, XFS, Btrfs 등 다양한 파일 시스템을 VFS 위에서 추상화
- **"Everything is a file"**: 디바이스, 소켓, 파이프도 파일 디스크립터로 접근

#### 4. 네트워크 스택
- L2(Ethernet) → L3(IP) → L4(TCP/UDP) → L7(Application) 처리
- **Netfilter/iptables**: 패킷 필터링, NAT (Docker/K8s 네트워킹의 핵심)

#### 5. 디바이스 드라이버
- 하드웨어와 커널 사이의 인터페이스
- Linux는 **모듈(Module)** 형태로 동적 로드/언로드 가능

### 커널 아키텍처 유형

#### Monolithic Kernel (모놀리식 커널)
```
┌─────────────────────────────────┐
│         Kernel (단일 주소 공간)    │
│  Process + Memory + FS + Driver  │
│  + Network ... 전부 커널 내부     │
└─────────────────────────────────┘
```
- **Linux, Unix** 계열
- 모든 커널 기능이 **하나의 주소 공간**에서 실행
- 장점: 성능 우수 (컴포넌트 간 함수 호출)
- 단점: 드라이버 버그가 전체 커널 크래시 유발 가능

#### Microkernel (마이크로커널)
```
┌──────────────────┐
│   Microkernel     │  ← 최소한의 기능만 (IPC, 스케줄링, 메모리)
└──────────────────┘
  ↕ IPC    ↕ IPC    ↕ IPC
┌──────┐ ┌──────┐ ┌──────┐
│ FS   │ │Driver│ │Network│  ← 서버 프로세스로 분리
└──────┘ └──────┘ └──────┘
```
- **Minix, QNX, seL4**
- 커널에 최소 기능만 두고 나머지는 유저 모드 서버로 분리
- 장점: 안정성 (드라이버 크래시가 커널에 영향 없음)
- 단점: IPC 오버헤드로 성능 저하

#### Hybrid Kernel (하이브리드 커널)
- **Windows NT, macOS (XNU)**
- 모놀리식의 성능 + 마이크로커널의 모듈성을 절충

### Linux 커널이 Docker/K8s의 핵심인 이유

Linux 커널은 **컨테이너 기술의 기반이 되는 핵심 기능들**을 제공한다:

| 커널 기능 | 역할 | 컨테이너에서의 사용 |
|----------|------|-------------------|
| **Namespace** | 프로세스 격리 | PID, Network, Mount, UTS, IPC 격리 |
| **cgroups** | 리소스 제한 | CPU, Memory, I/O 제한 |
| **UnionFS/OverlayFS** | 레이어 파일 시스템 | Docker 이미지 레이어 |
| **Netfilter/iptables** | 네트워크 필터링 | Docker 네트워크, K8s Service |
| **seccomp** | 시스템 콜 필터링 | 컨테이너 보안 |

## 헷갈렸던 포인트

### Q1: System Call은 왜 비용이 드나?

유저 모드 → 커널 모드 전환 시:
1. CPU 레지스터 저장 (유저 모드 상태)
2. 커널 스택으로 전환
3. 커널 코드 실행
4. 유저 모드로 복귀 (레지스터 복원)

이 과정이 약 **수백 나노초 ~ 수 마이크로초** 소요된다. 그래서 `io_uring`이나 `vDSO` 같은 기술로 System Call을 줄이려는 시도가 있다.

### Q2: 왜 Linux 커널이 모놀리식인데 모듈도 되나?

Linux는 **모놀리식이지만 Loadable Kernel Module (LKM)** 을 지원한다. 드라이버를 `.ko` 파일로 만들어 런타임에 `insmod`/`modprobe`로 로드할 수 있다. 커널 재컴파일 없이 기능을 추가/제거할 수 있지만, 로드된 모듈은 **커널 주소 공간에서 실행**되므로 본질적으로는 모놀리식이다.

### Q3: 커널 패닉(Kernel Panic)은 왜 발생하나?

커널 코드에서 복구 불가능한 오류가 발생하면 시스템 전체를 중단시킨다:
- NULL 포인터 역참조
- 메모리 접근 위반
- 드라이버 버그
- 하드웨어 오류

유저 모드 프로세스의 버그는 해당 프로세스만 죽지만(Segmentation Fault), 커널 모드 버그는 **전체 시스템**에 영향을 준다. 이것이 마이크로커널 지지자들의 핵심 논거다.

## 참고 자료

- [Linux Kernel Documentation](https://www.kernel.org/doc/html/latest/)
- [Operating Systems: Three Easy Pieces](https://pages.cs.wisc.edu/~remzi/OSTEP/)
