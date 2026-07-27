# Stage 50D · Electron Windows portable packaging

## 목적

Stage 50C에서 검증된 검색 UI를 Windows x64 단일 portable exe로 패키징할 수 있는 기준선을 만든다.

## 고정 도구

- Node.js 22.23.1
- Electron 43.2.0
- electron-builder 26.15.3
- npm package-lock lockfileVersion 3

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
2. package-lock 정확 버전 검증
3. electron-builder 설정 검증
4. Windows portable exe 크기 확인
5. 패키지 내부 데이터 SHA256/schema 확인
6. E011 검색·상세조회
7. 숨김 BrowserWindow renderer 로드
8. smoke JSON 보고서 확인

## 다음 단계

수동 `workflow_dispatch`가 성공하면 package 버전을 preview 태그로 확정하고
`electron-v<version>` 태그를 푸시해 GitHub Release Asset을 생성한다.
