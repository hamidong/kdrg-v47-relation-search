# KDRG V4.7 Electron Stage 50B

Stage 50B는 기존 Python `KdrgSearchService`의 검색·상세조회 의미를 Node.js로 이식한 단계다.

## 포함 범위

- ADRG, AADRG, RDRG, TABLE, CODE 검색
- 점 표기 코드 정규화
- MDC 및 A/B/C 분류 필터
- 조건 AST TABLE polarity 939건
- 상세조회 응답 계약
- main process 내부 검색 service
- 제한된 preload IPC bridge
- Python↔JavaScript 동등성 자동검증

## 보안 경계

통합 JSON은 main process에서만 읽는다. renderer에는 검색 응답과 상세조회 응답만 전달하며,
Node.js 객체나 `ipcRenderer` 자체를 노출하지 않는다.

## 다음 단계

Stage 50C에서 renderer 검색창·결과목록·상세패널을 연결한다. Electron 의존성 설치와
`package-lock.json` 생성도 실제 UI 기동검증과 함께 수행한다.
