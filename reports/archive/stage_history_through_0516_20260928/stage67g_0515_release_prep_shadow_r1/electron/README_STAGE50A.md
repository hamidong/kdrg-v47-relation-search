# KDRG V4.7 Electron Stage 50A

## 이번 단계 범위

- Electron main/preload/renderer 기본 골격
- 통합 JSON, UI semantic profile, UI display contract의 안전한 로딩
- SHA256 및 schema 검증
- renderer에는 요약 snapshot만 전달
- 보안 기본값: contextIsolation, sandbox, nodeIntegration 비활성

## 아직 포함하지 않는 범위

- JavaScript 검색 서비스
- 검색 결과 화면
- Electron Windows 패키징 및 Release workflow
- PySide 파일 변경

## 검증

```bash
cd ~/workspace/electron
npm run validate
```

## 로컬 실행 준비

Node.js 22 이상 환경에서 다음 단계에 `npm install` 후 `npm start`를 사용합니다.
Stage 50A에서는 의존성 설치와 GUI 실행을 필수로 하지 않습니다.
