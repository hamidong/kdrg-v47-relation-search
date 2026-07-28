# Stage 50D · Electron Windows portable packaging

## 목적

Stage 50C에서 검증된 검색 UI를 Windows x64 단일 portable exe로 패키징할 수 있는 기준선을 만든다.

## 고정 도구

- Node.js 22.23.1
- Electron 43.2.0
- electron-builder 26.15.3
- npm CLI 11.17.0
- npm package-lock lockfileVersion 3

## npm 재현성·복구 원칙

- Node에 동봉된 npm을 그대로 신뢰하지 않고 npm CLI 11.17.0을 별도로 고정한다.
- npm registry metadata의 `dist.integrity`와 다운로드한 tarball의 SHA512를 비교한다.
- GitHub Actions job 수준 `env`에는 runner context를 사용하지 않고 정적 값만 둔다.
- runner가 시작된 뒤 `$env:RUNNER_TEMP`와 기본 실행 식별자 환경변수로 임시경로를 계산한다.
- 계산된 npm·Electron cache 경로는 `$GITHUB_ENV`로 이후 단계에 전달한다.
- GitHub Actions 실행별로 독립된 npm cache를 사용해 오염된 cache 재사용을 차단한다.
- `npm ci`는 고정 CLI로 실행하며 실패 시 `node_modules`를 정리하고 최대 2회 수행한다.
- 두 번 모두 실패하면 최신 npm debug log 250줄을 Actions 로그에 출력한다.
- 검증과 electron-builder 실행도 동일한 고정 npm CLI를 사용한다.

## 패키징 원칙

- Windows target: `portable`
- 설치 및 관리자 권한 불필요
- `asar: true`
- 통합 JSON 3종은 `resources/data/`에 `extraResources`로 배치
- 원본 JSON은 renderer에 직접 노출하지 않음
- Actions 임시 artifact 업로드는 사용하지 않음
- `electron-v*` 태그에서만 GitHub Release Assets에 exe와 SHA256을 업로드

## 검증

1. JavaScript 문법·검색·UI·보안 회귀검증
2. job-level context 허용범위와 runner 임시경로 초기화 검증
3. 고정 npm CLI tarball SHA512와 package-lock 정확 버전 검증
4. electron-builder 설정 검증
5. Windows portable exe 크기 확인
6. 패키지 내부 데이터 SHA256/schema 확인
7. E011 검색·상세조회
8. 숨김 BrowserWindow renderer 로드
9. smoke JSON 보고서 확인

## 다음 단계

수동 `workflow_dispatch`가 성공하면 package 버전을 preview 태그로 확정하고
`electron-v<version>` 태그를 푸시해 GitHub Release Asset을 생성한다.
