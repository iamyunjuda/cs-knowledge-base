# React 번들링 — Webpack, Vite, 그리고 모듈 시스템의 진화

## 핵심 정리

### 번들링이란?
브라우저는 원래 수백 개의 JS/CSS/이미지 파일을 개별 요청해야 한다. **번들러**는 이 파일들을 하나(또는 소수)의 파일로 합쳐서 네트워크 요청 수를 줄이고, 로딩 속도를 높이는 도구다.

### JavaScript 모듈 시스템의 진화

| 시대 | 방식 | 특징 |
|------|------|------|
| 초기 | `<script>` 태그 나열 | 전역 변수 충돌, 순서 의존 |
| CommonJS (2009) | `require()` / `module.exports` | Node.js 표준, 동기 로딩 |
| AMD (2011) | `define()` / `require()` | 브라우저용, 비동기 로딩 |
| **ES Modules (2015)** | `import` / `export` | 표준 스펙, 정적 분석 가능 |

ES Modules가 표준이 된 이후에도 번들링이 필요한 이유:
- **Tree Shaking**: 사용하지 않는 코드 제거 (ESM의 정적 구조 덕분에 가능)
- **Code Splitting**: 페이지별로 필요한 코드만 로딩
- **Transpiling**: JSX, TypeScript → 브라우저가 이해하는 JS로 변환
- **Polyfill**: 구형 브라우저 호환
- **Asset 처리**: CSS, 이미지, 폰트 등 비-JS 자원도 함께 번들링

### Webpack — 1세대 번들러의 왕

```
Entry → Loaders → Plugins → Output (bundle.js)
```

**핵심 개념:**
- **Entry**: 번들링의 시작점 (보통 `src/index.js`)
- **Loader**: 파일을 변환하는 전처리기
  - `babel-loader`: JSX/ES6+ → ES5
  - `ts-loader`: TypeScript → JS
  - `css-loader` + `style-loader`: CSS → JS 모듈
  - `file-loader` / `asset/resource`: 이미지, 폰트
- **Plugin**: 번들 결과물을 후처리
  - `HtmlWebpackPlugin`: HTML 자동 생성
  - `MiniCssExtractPlugin`: CSS 파일 분리
  - `DefinePlugin`: 환경 변수 주입
- **Output**: 최종 번들 파일 설정

```javascript
// webpack.config.js (간략화)
module.exports = {
  entry: './src/index.js',
  module: {
    rules: [
      { test: /\.jsx?$/, use: 'babel-loader', exclude: /node_modules/ },
      { test: /\.css$/, use: ['style-loader', 'css-loader'] },
    ],
  },
  plugins: [new HtmlWebpackPlugin({ template: './public/index.html' })],
  output: { filename: 'bundle.[contenthash].js', path: path.resolve(__dirname, 'dist') },
};
```

**Webpack의 한계:**
- 설정이 복잡 (config 파일이 수백 줄)
- 개발 시 전체를 번들링하므로 **HMR(Hot Module Replacement)이 느림**
- 프로젝트가 커지면 빌드 시간 수 분 → 개발 생산성 저하

### Vite — 차세대 번들러

Vite의 핵심 혁신: **개발 시에는 번들링하지 않는다.**

```
[개발 모드]
브라우저가 ESM import 요청 → Vite 서버가 해당 모듈만 변환 → 즉시 응답

[프로덕션 빌드]
Rollup 기반 번들링 → 최적화된 정적 파일 생성
```

**개발 모드 동작 원리:**
1. 브라우저가 `<script type="module" src="/src/main.jsx">` 요청
2. Vite 개발 서버가 `main.jsx`를 esbuild로 **즉시 변환** (Go로 작성, 매우 빠름)
3. 브라우저가 `import App from './App.jsx'`를 만나면 추가 요청
4. Vite가 `App.jsx`도 변환해서 응답
5. → **필요한 모듈만 변환**하므로 프로젝트 크기와 무관하게 빠름

**Webpack vs Vite 비교:**

| 항목 | Webpack | Vite |
|------|---------|------|
| 개발 서버 시작 | 전체 번들링 후 시작 (느림) | 즉시 시작 (ESM 기반) |
| HMR 속도 | 프로젝트 크기에 비례 | 항상 빠름 (변경된 모듈만) |
| 프로덕션 빌드 | Webpack 자체 | Rollup 사용 |
| 설정 복잡도 | 높음 | 낮음 (합리적 기본값) |
| 생태계 | 매우 넓음, 레거시 지원 | 빠르게 성장 중 |
| React 사용 시 | CRA(Create React App) 기반 | `npm create vite@latest` |

```javascript
// vite.config.js (React 프로젝트)
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  // 이것만으로 JSX, HMR, CSS 모듈 등 자동 지원
});
```

### Code Splitting과 Lazy Loading

React에서 번들 최적화의 핵심:

```jsx
// 동적 import → 별도 chunk로 분리
const AdminPage = React.lazy(() => import('./pages/AdminPage'));

function App() {
  return (
    <Suspense fallback={<Loading />}>
      <Routes>
        <Route path="/admin" element={<AdminPage />} />
      </Routes>
    </Suspense>
  );
}
```

번들 분석 도구:
- `webpack-bundle-analyzer`: Webpack 번들 시각화
- `rollup-plugin-visualizer`: Vite/Rollup 번들 시각화
- Chrome DevTools → Network 탭 → JS 파일 크기 확인

### Source Map

번들된 코드는 한 줄로 압축(minify)되어 디버깅이 불가능하다. **Source Map**은 번들 코드 ↔ 원본 코드 매핑 파일이다.

```
bundle.js.map → 원본 파일명, 줄 번호, 변수명 매핑
```

- 개발: `devtool: 'eval-source-map'` (빠르고 정확)
- 프로덕션: `devtool: 'source-map'` 또는 생략 (보안상 배포 시 제거하기도 함)

### CRA → Vite 마이그레이션이 대세인 이유

Create React App (CRA)은 2023년부터 사실상 **유지보수 중단** 상태:
- React 공식 문서에서도 CRA 대신 Vite, Next.js 등 권장
- Webpack 4 기반이라 최신 기능 미지원
- `react-scripts eject` 하면 돌아올 수 없음

마이그레이션 핵심 단계:
1. `vite`, `@vitejs/plugin-react` 설치
2. `vite.config.js` 생성
3. `index.html`을 `public/` → 프로젝트 루트로 이동
4. `<script type="module" src="/src/index.jsx">` 추가
5. 환경 변수 `REACT_APP_*` → `VITE_*`로 변경
6. `react-scripts` 제거

## 헷갈렸던 포인트

### Q: 번들링이 필요 없어지는 시대가 오는 거 아닌가? ESM이면 되잖아?
**A:** 개발 모드에서는 맞다 (Vite가 이 방식). 하지만 프로덕션에서는 여전히 필요하다:
- 수백 개의 ESM 요청 → HTTP/2로도 느림 (서버 왕복 비용)
- Tree Shaking으로 사용하지 않는 코드 제거
- Minification (코드 압축)
- CSS/이미지 최적화
- **Import Map**과 **HTTP/3**가 보편화되면 변할 수 있지만, 아직은 번들링이 필수

### Q: Webpack의 Loader와 Plugin의 차이가 뭔데?
**A:**
- **Loader**: 개별 파일을 변환 (1:1). "이 확장자의 파일은 이렇게 처리해라"
- **Plugin**: 번들링 과정 전체에 개입 (N:1). "번들 완성 후 이것도 해라"
- Loader는 `module.rules`에, Plugin은 `plugins`에 설정

### Q: Vite가 개발 서버에서 esbuild를 쓰는데 프로덕션에서는 왜 Rollup?
**A:** esbuild는 변환(transform)은 빠르지만, Code Splitting, CSS 처리, 플러그인 생태계가 Rollup에 비해 아직 부족하다. Vite는 개발 속도(esbuild)와 프로덕션 품질(Rollup)을 모두 잡는 전략이다. (Vite 미래 버전에서 Rolldown으로 통합 예정)

### Q: `contenthash`가 번들 파일명에 붙는 이유는?
**A:** 브라우저 캐시 무효화(Cache Busting)를 위해서다. 파일 내용이 바뀌면 해시가 바뀌어 새 파일로 인식 → CDN/브라우저 캐시를 안전하게 활용. 내용이 안 바뀌면 해시도 동일 → 캐시 히트.

## 참고 자료
- [Webpack 공식 문서 — Concepts](https://webpack.js.org/concepts/)
- [Vite 공식 문서 — Why Vite](https://vitejs.dev/guide/why.html)
- [React 공식 문서 — Start a New React Project](https://react.dev/learn/start-a-new-react-project)
