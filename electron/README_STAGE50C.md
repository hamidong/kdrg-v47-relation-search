# Stage 50C · Electron renderer 검색 UI

## 목적

Stage 50B에서 검증한 JavaScript 검색 service를 Electron renderer에 연결한다.

## 화면 구조

- 통합 검색창
- CODE·ADRG·AADRG·RDRG·TABLE 유형 필터
- MDC 필터
- 질병군 분류(전문/일반/단순) 필터
- 검색 결과 목록과 유형별 건수
- 상세 관계 패널
- ADRG 기본 분류 TABLE
- ADRG 추가 분기조건
- 포함조건과 제외조건 분리
- 기술식·원문 근거 접기

## 의미 보존 원칙

- 기본 분류 TABLE은 원문 정의 목록이며 포함·제외 논리를 뜻하지 않는다.
- 추가 분기조건은 AST 논리를 따라 AND·OR·NOT·EXCLUSION을 재귀 처리한다.
- 제외 조건은 `단, 다음 대상은 제외`로 별도 표시한다.
- 조건 AST가 없는 ADRG는 `별도의 추가 분기조건 없음`으로 표시한다.
- 원천에 없는 코드명과 TABLE 유형은 임의로 생성하지 않는다.

## 보안 원칙

- renderer는 `window.KDRG`의 제한된 bridge만 사용한다.
- renderer에서 `require`, `innerHTML`, `eval`을 사용하지 않는다.
- 원본 통합 corpus는 renderer에 직접 노출하지 않는다.
- 모든 동적 문자는 `textContent`로 화면에 추가한다.

## 검증

```bash
node tests/validate-renderer-ui.js
```

Stage 50C에서는 Electron package 설치와 exe 빌드를 수행하지 않는다.
