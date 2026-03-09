# BLE 기반 친구 탐지 앱 — 블루투스 근접 감지, 거리 측정, 방향 표시의 기술 원리

## 핵심 정리

### 앱 컨셉

1:1로 친구를 맺고, 친구가 블루투스를 켜고 근처에 오면 **알림**을 보내고, 이후 **나침반(방향)**과 **거리(미터)**를 홈 화면 위젯에서 실시간으로 보여주는 앱.

```
┌──────────────────────────────────────────────────────┐
│                    앱 동작 흐름                        │
│                                                      │
│  [백그라운드 BLE 스캔]                                 │
│         │                                            │
│         ▼                                            │
│  친구 BLE 신호 감지 ──▶ 푸시 알림: "친구가 근처에!"     │
│         │                                            │
│         ▼                                            │
│  [위젯 활성화]                                        │
│  ┌────────────────┐                                  │
│  │   🧭  ↗ 북동쪽  │                                  │
│  │   약 15m 거리   │                                  │
│  └────────────────┘                                  │
└──────────────────────────────────────────────────────┘
```

---

### 1. BLE (Bluetooth Low Energy) 기초

BLE는 Bluetooth 4.0부터 도입된 저전력 무선 통신 규격이다. Classic Bluetooth와 달리 **페어링 없이도 신호를 감지(스캔)**할 수 있어 근접 탐지에 적합하다.

| 항목 | Classic Bluetooth | BLE |
|------|------------------|-----|
| 전력 소모 | 높음 | 매우 낮음 |
| 연결 필요 여부 | 반드시 페어링 | Advertising만으로 감지 가능 |
| 데이터 전송량 | 대용량 (오디오 등) | 소량 (센서, 비콘) |
| 탐지 범위 | ~10m | ~50m (환경에 따라 다름) |
| 용도 | 이어폰, 파일 전송 | 비콘, 건강 트래커, 근접 감지 |

#### BLE Advertising & Scanning

```
┌──────────┐         Advertising Packet          ┌──────────┐
│  친구 폰  │  ──────────────────────────────▶   │  내 폰    │
│ (Peripheral│   UUID + Minor + Major + TxPower  │ (Central) │
│  /Advertiser)                                  │  Scanner  │
└──────────┘         매 100~1000ms 주기           └──────────┘
```

- **Advertiser (친구 폰)**: 자신의 고유 UUID를 포함한 BLE Advertising 패킷을 주기적으로 브로드캐스트
- **Scanner (내 폰)**: 백그라운드에서 특정 UUID를 가진 BLE 신호를 스캔하다가, 친구의 UUID를 감지하면 알림 발생

---

### 2. 거리 측정 — RSSI 기반 추정

BLE에서 거리를 직접 측정하는 것은 불가능하다. 대신 **RSSI (Received Signal Strength Indicator, 수신 신호 세기)**를 이용해 거리를 **추정**한다.

#### RSSI → 거리 변환 공식 (Log-Distance Path Loss Model)

```
d = 10 ^ ((TxPower - RSSI) / (10 * n))

d       : 추정 거리 (미터)
TxPower : 1m 거리에서의 기준 RSSI 값 (보통 -59 ~ -65 dBm)
RSSI    : 현재 수신된 신호 세기 (dBm)
n       : 환경 계수 (자유 공간: 2, 실내: 2.5~4.0)
```

#### RSSI 값과 대략적 거리 관계

| RSSI (dBm) | 추정 거리 | 신호 강도 |
|-------------|----------|----------|
| -30 ~ -50  | ~1m      | 매우 강함 |
| -50 ~ -70  | 1~5m     | 강함     |
| -70 ~ -85  | 5~15m    | 보통     |
| -85 ~ -100 | 15~30m+  | 약함     |

#### RSSI의 한계와 보정

RSSI는 환경에 따라 변동이 매우 크다:
- 벽, 사람, 가방 안 등 **장애물**에 의한 신호 감쇠
- **다중 경로 반사(Multipath)**로 인한 신호 왜곡
- 기기마다 다른 안테나 특성

**보정 방법:**
```
1. 이동 평균 필터 (Moving Average)
   - 최근 N개의 RSSI 값을 평균 → 노이즈 제거
   - 단점: 반응 지연

2. 칼만 필터 (Kalman Filter)
   - 예측값과 관측값을 가중 결합
   - RSSI 노이즈 제거에 가장 널리 사용
   - 상태: [거리, 거리 변화율]

3. 가중 이동 평균 (Weighted Moving Average)
   - 최근 값에 더 큰 가중치 부여
   - 반응성과 안정성의 균형
```

---

### 3. 방향 표시 — BLE 단독으로는 불가능

BLE RSSI만으로는 **신호 세기(=거리 추정)**만 가능하고, **방향**은 알 수 없다. 방향을 표시하려면 추가 기술이 필요하다.

#### 접근법 비교

| 방식 | 정확도 | 요구 사항 | 실용성 |
|------|-------|----------|-------|
| **BLE + GPS 좌표 공유** | 중 (3~10m 오차) | 인터넷 연결 필요 | 높음 |
| **BLE 5.1 AoA/AoD** | 높 (~1m) | 안테나 배열 필요 | 낮음 (모바일 미지원) |
| **UWB (Ultra-Wideband)** | 매우 높 (~10cm) | UWB 칩 탑재 기기 | 중 (일부 기기만) |

#### 방법 1: BLE + GPS 좌표 공유 (가장 현실적)

```
┌──────────┐    BLE 감지 (근처 확인)    ┌──────────┐
│  내 폰    │◀──────────────────────▶│  친구 폰  │
│           │                        │           │
│  GPS 좌표 │───── 서버/P2P ────────▶│  GPS 좌표  │
│  (37.5, 127.0)   좌표 교환         │(37.5, 127.001)│
└──────────┘                        └──────────┘
      │
      ▼
  내 좌표 + 친구 좌표 + 자이로스코프/자력계
      │
      ▼
  ┌────────────────────┐
  │ 방위각 계산 (Bearing)  │
  │ + 디바이스 방향 (Heading)│
  │ = 나침반 화살표 방향     │
  └────────────────────┘
```

**방위각(Bearing) 계산:**
```
// 두 GPS 좌표 사이의 방위각 (라디안)
bearing = atan2(
    sin(Δlon) * cos(lat2),
    cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(Δlon)
)

// 나침반 화살표 방향 = 방위각 - 디바이스가 바라보는 방향(heading)
arrowAngle = bearing - deviceHeading
```

**GPS 거리 계산 (Haversine 공식):**
```
a = sin²(Δlat/2) + cos(lat1) * cos(lat2) * sin²(Δlon/2)
c = 2 * atan2(√a, √(1-a))
distance = R * c    // R = 6371km (지구 반지름)
```

#### 방법 2: UWB (Ultra-Wideband) — 프리미엄 옵션

UWB는 Apple AirTag, Samsung SmartTag+가 사용하는 기술로, **정밀한 거리 + 방향**을 동시에 측정할 수 있다.

```
UWB 동작 원리:
- ToF (Time of Flight): 초광대역 펄스의 왕복 시간으로 거리 측정 (~10cm 정확도)
- AoA (Angle of Arrival): 다중 안테나로 신호 도달 각도 계산 → 방향 측정

지원 기기:
- iOS: iPhone 11 이상 (U1 칩) → Nearby Interaction 프레임워크
- Android: Pixel 6 Pro, Samsung Galaxy S21+ 이상 → UWB API
```

---

### 4. 백그라운드 BLE 스캔과 알림

앱이 포그라운드가 아닌 **백그라운드/홀드 상태**에서도 친구를 감지해야 하므로, OS별 백그라운드 제한을 이해해야 한다.

#### iOS 백그라운드 BLE

```
┌─────────────────────────────────────────────────┐
│              iOS BLE 백그라운드 동작               │
├─────────────────────────────────────────────────┤
│                                                 │
│  Core Bluetooth 프레임워크:                       │
│  - Background Mode 활성화 필요                    │
│    (Info.plist → bluetooth-central)              │
│  - 백그라운드에서 스캔 가능하지만 제약 있음:          │
│    · 스캔 간격이 길어짐 (~수 분)                    │
│    · UUID 필터링 필수                              │
│    · Advertising 데이터 일부만 수신                 │
│                                                 │
│  iBeacon 프로토콜 활용:                            │
│  - CLLocationManager의 Region Monitoring          │
│  - 앱이 종료되어도 진입/이탈 이벤트 수신             │
│  - didEnterRegion → Local Notification 발생       │
│  - 가장 안정적인 백그라운드 감지 방법               │
│                                                 │
└─────────────────────────────────────────────────┘
```

**iOS 권장 전략: iBeacon Region Monitoring**
```swift
// 친구의 UUID로 Beacon Region 등록
let region = CLBeaconRegion(
    uuid: UUID(uuidString: "친구-고유-UUID")!,
    identifier: "friend-region"
)

// 진입 감지 시 알림
func locationManager(_ manager: CLLocationManager,
                     didEnterRegion region: CLRegion) {
    // "친구가 근처에 있어요!" 알림 발송
    sendLocalNotification()
    // 정밀 거리/방향 측정 시작
    startRanging(for: region as! CLBeaconRegion)
}
```

#### Android 백그라운드 BLE

```
┌─────────────────────────────────────────────────┐
│           Android BLE 백그라운드 동작              │
├─────────────────────────────────────────────────┤
│                                                 │
│  Foreground Service 방식:                        │
│  - 알림 표시 필수 (사용자에게 스캔 중임을 알림)       │
│  - BLE 스캔을 지속적으로 수행 가능                   │
│  - 배터리 소모 주의                                │
│                                                 │
│  WorkManager + BLE 스캔:                         │
│  - 주기적 스캔 (최소 15분 간격)                     │
│  - 배터리 효율적이지만 실시간성 떨어짐               │
│                                                 │
│  Companion Device Manager (Android 8+):          │
│  - 시스템 수준에서 BLE 디바이스 감시                 │
│  - 앱이 종료되어도 감지 가능                        │
│  - 가장 권장되는 방식                              │
│                                                 │
└─────────────────────────────────────────────────┘
```

---

### 5. 홈 화면 위젯 구현

#### iOS — WidgetKit

```
┌─────────────────────────────────────────┐
│          iOS WidgetKit 구조              │
│                                         │
│  WidgetKit 제약:                         │
│  - 직접 BLE 스캔 불가                    │
│  - 메인 앱에서 데이터 → App Group 공유    │
│  - TimelineProvider로 주기적 갱신        │
│  - Live Activity (iOS 16+)로 실시간 표시 │
│                                         │
│  ┌─────────────┐    ┌──────────────┐   │
│  │   메인 앱     │───▶│  App Group   │   │
│  │ (BLE + GPS)  │    │ (UserDefaults│   │
│  │              │    │  /파일 공유)  │   │
│  └─────────────┘    └──────┬───────┘   │
│                            │            │
│                     ┌──────▼───────┐   │
│                     │   Widget     │   │
│                     │  🧭 ↗ 15m   │   │
│                     └──────────────┘   │
│                                         │
│  Live Activity (Dynamic Island):        │
│  - 실시간 업데이트 가능                   │
│  - ActivityKit 프레임워크                │
│  - 잠금 화면에서도 표시                   │
│  - 이 앱에 가장 적합한 방식!             │
│                                         │
└─────────────────────────────────────────┘
```

#### Android — App Widget + Foreground Service

```
┌─────────────────────────────────────────┐
│        Android 위젯 구조                 │
│                                         │
│  ┌─────────────────┐                    │
│  │ Foreground Service│                   │
│  │  (BLE 스캔 유지)  │                   │
│  │  + GPS 좌표 교환  │                   │
│  └────────┬────────┘                    │
│           │ 데이터 업데이트               │
│    ┌──────▼───────┐                     │
│    │ AppWidgetProvider│                  │
│    │   🧭 ↗ 15m     │                   │
│    │  (RemoteViews)  │                   │
│    └───────────────┘                    │
│                                         │
│  Glance (Jetpack Compose 위젯):         │
│  - 최신 방식, Compose UI 사용 가능       │
│  - 업데이트 주기 제어 용이               │
│                                         │
└─────────────────────────────────────────┘
```

#### 잠금 화면 표시

| 플랫폼 | 방법 | 실시간성 |
|--------|------|---------|
| iOS | **Live Activity + Dynamic Island** | 높음 (push 기반 업데이트) |
| iOS | Lock Screen 위젯 | 중간 (Timeline 기반) |
| Android | 위젯 (잠금 화면 위젯 허용 시) | 중간 |
| Android | **Ongoing Notification** (커스텀 레이아웃) | 높음 |

---

### 6. 전체 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│                     전체 시스템 구조                       │
│                                                         │
│  ┌──────────┐                        ┌──────────┐      │
│  │   내 폰   │                        │  친구 폰  │      │
│  │          │◀── BLE Advertising ───▶│          │      │
│  │          │    (근접 감지용)         │          │      │
│  │          │                        │          │      │
│  │          │◀── GPS 좌표 교환 ──────▶│          │      │
│  │          │    (서버 or P2P)        │          │      │
│  └────┬─────┘                        └────┬─────┘      │
│       │                                   │             │
│       ▼                                   ▼             │
│  ┌─────────────────────────────────────────────┐       │
│  │              중계 서버 (선택적)                │       │
│  │                                             │       │
│  │  - 친구 매칭/관리 (1:1 페어링)                │       │
│  │  - GPS 좌표 중계 (위치 공유)                  │       │
│  │  - 푸시 알림 발송 (FCM / APNs)               │       │
│  │  - WebSocket으로 실시간 좌표 스트리밍          │       │
│  └─────────────────────────────────────────────┘       │
│                                                         │
│  ┌─────────────────────────────────────────────┐       │
│  │              동작 시나리오                     │       │
│  │                                             │       │
│  │  Phase 1: 대기 (백그라운드)                   │       │
│  │  - iBeacon Region Monitoring (iOS)           │       │
│  │  - CompanionDeviceManager (Android)          │       │
│  │  - 배터리 소모 최소화                         │       │
│  │                                             │       │
│  │  Phase 2: 감지 → 알림                        │       │
│  │  - BLE 신호 감지 시 Local Notification        │       │
│  │  - 서버 경유 Push Notification도 병행         │       │
│  │                                             │       │
│  │  Phase 3: 추적 (위젯 활성화)                  │       │
│  │  - BLE RSSI → 거리 추정 (칼만 필터 적용)      │       │
│  │  - GPS 좌표 교환 → 방위각 계산               │       │
│  │  - 나침반 UI 업데이트 (1~3초 주기)            │       │
│  │  - Live Activity / Ongoing Notification      │       │
│  │                                             │       │
│  │  Phase 4: 이탈                               │       │
│  │  - BLE 신호 사라짐 → 위젯 "범위 밖" 표시      │       │
│  │  - 다시 Phase 1로 전환                       │       │
│  └─────────────────────────────────────────────┘       │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

### 7. 핵심 기술 스택 요약

| 영역 | iOS | Android |
|------|-----|---------|
| BLE 스캔 | Core Bluetooth | Android BLE API |
| 백그라운드 감지 | iBeacon + CLLocationManager | CompanionDeviceManager |
| 거리 측정 | RSSI + 칼만 필터 | RSSI + 칼만 필터 |
| 방향 측정 | Core Location (heading) + GPS | SensorManager (자력계) + GPS |
| 위젯 | WidgetKit + **Live Activity** | App Widget / **Glance** |
| 잠금 화면 | Dynamic Island / Lock Screen | Ongoing Notification |
| UWB (선택) | Nearby Interaction (U1 칩) | Android UWB API |
| 좌표 교환 | WebSocket / P2P (MPC) | WebSocket / Wi-Fi Direct |

---

## 헷갈렸던 포인트

### Q1. BLE만으로 방향을 알 수 있나?

**아니다.** BLE RSSI는 신호 세기만 알려주므로 "얼마나 가까운지"는 추정할 수 있지만, "어느 방향인지"는 알 수 없다. 방향을 알려면:
- GPS 좌표를 서로 교환하고 방위각을 계산하거나
- UWB의 AoA(Angle of Arrival)를 사용해야 한다

### Q2. 앱이 완전히 종료되어도 감지가 되나?

- **iOS**: iBeacon Region Monitoring은 앱이 **종료(terminated)**되어도 OS가 감지해서 앱을 잠깐 깨워준다. 가장 안정적.
- **Android**: CompanionDeviceManager를 사용하면 시스템 수준에서 감시. Foreground Service는 앱이 종료되면 같이 종료됨.

### Q3. RSSI 기반 거리가 정확한가?

정확하지 않다. 실내에서는 **±5m 이상** 오차가 날 수 있다. 하지만 이 앱의 목적은 "정밀 측위"가 아니라 **"친구가 근처에 있다"는 사실을 아는 것**이므로, 대략적인 거리 표시로 충분하다. 칼만 필터로 노이즈를 줄이면 사용자 경험이 크게 개선된다.

### Q4. 배터리 소모는 어떤가?

- **BLE Advertising**: 매우 낮음 (하루 1~2% 수준)
- **BLE Scanning**: 모드에 따라 다름
  - Low Power 모드: 낮음 (5~10초 간격 스캔)
  - Low Latency 모드: 높음 (지속 스캔)
- **GPS**: 가장 큰 소모원. 친구 감지 후에만 GPS를 활성화하는 것이 핵심

### Q5. GPS 좌표 교환은 서버가 꼭 필요한가?

꼭 필요하지는 않다. BLE 연결(GATT)을 통해 P2P로 좌표를 교환할 수도 있다. 하지만 서버를 두면:
- 친구 매칭/관리가 쉬워짐
- BLE 범위 밖에서도 위치 공유 가능 (GPS 기반 원거리 모드)
- 푸시 알림 발송 가능

---

## 참고 자료

- [Apple Core Bluetooth Programming Guide](https://developer.apple.com/library/archive/documentation/NetworkingInternetWeb/Conceptual/CoreBluetooth_concepts/AboutCoreBluetooth/Introduction.html)
- [Android BLE Overview](https://developer.android.com/develop/connectivity/bluetooth/ble/ble-overview)
- [Apple Nearby Interaction (UWB)](https://developer.apple.com/nearby-interaction/)
- [iBeacon - Apple Developer](https://developer.apple.com/ibeacon/)
- [Android Companion Device Manager](https://developer.android.com/reference/android/companion/CompanionDeviceManager)
- [WidgetKit - Apple Developer](https://developer.apple.com/widgets/)
- [ActivityKit (Live Activity) - Apple Developer](https://developer.apple.com/documentation/activitykit)
- [Kalman Filter for RSSI Smoothing](https://en.wikipedia.org/wiki/Kalman_filter)
