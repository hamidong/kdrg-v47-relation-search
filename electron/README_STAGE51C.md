# Stage 51C · Electron 사용자 분류조건 검색 UI

## 목적

KDRG V4.7 통합 검색 데이터 v3의 `user_condition_*` 필드를 Electron ADRG 상세 화면에 연결한다.
분류집에서 실제로 확인된 사용자용 조건과 TABLE만 보여주고, 기술용 전체 관계를 사용자 조건으로 오인하지 않도록 분리한다.

## 공개 검색 범위

- 검색 유형은 `전체·코드·ADRG`만 제공한다.
- AADRG와 RDRG는 ADRG 상세의 파생정보로 표시한다.
- TABLE은 별도 검색 결과가 아니라 ADRG·코드 상세 안에서 인라인으로 펼친다.
- TABLE 카드를 열어도 현재 화면을 유지한다.

## ADRG 상세 구조

- 기본정보
- 파생 AADRG와 질병군 분류
- `분류 조건`: `user_condition_text`에 저장된 공식 조건 문구
- `조건 상세`: `user_condition_table_refs`로 연결된 실제 조건 TABLE
- `원문 근거`: 조건 출처·상태·AST·기술식

## 의미 보존 원칙

- 사용자 TABLE 카드는 `user_condition_table_refs`만 사용한다.
- `logical_table_ids`, source TABLE, AST 전체 관계는 관계검색·기술 상세용으로 유지한다.
- 가족 TABLE이나 원문 정의 TABLE 전체를 실제 사용자 조건으로 확대 표시하지 않는다.
- B018은 `LT_B018_001·LT_B018_004·LT_B018_005`만 조건 상세에 표시한다.
- B022와 L033은 조건 문구를 표시하되 연결 근거가 유일하지 않으므로 TABLE을 추정하지 않는다.
- 9610은 명시적 분류 조건이 확인되지 않았으므로 사용자 조건 TABLE을 생성하지 않는다.
- 원천에 없는 코드명·TABLE명·조건을 임의로 생성하지 않는다.

## 보안 원칙

- renderer는 `window.KDRG`의 제한된 bridge만 사용한다.
- renderer에서 `require`, `innerHTML`, `insertAdjacentHTML`, `eval`을 사용하지 않는다.
- 원본 통합 corpus는 renderer에 직접 노출하지 않는다.
- 모든 동적 문자는 `textContent`로 화면에 추가한다.

## 운영 데이터

- 파일: `data/kdrg_v47_search_integrated_v3.json`
- schema: `kdrg-v47-search-integrated-v3`
- SHA256: `3cc370dfb7e3d3c9480e66fc6cdb2b83c9f05f39fa82c0ce4d9403c0812d7f0b`

## 검증

```bash
cd ~/workspace/electron
npm run validate:stage51c
npm run validate:search
npm run validate:ui
npm run check

cd ~/workspace
python -X utf8 electron/scripts/validate-checkout-byte-integrity.py
git diff --check
```

`README_STAGE50C.md`는 당시 구현을 기록한 역사 문서로 보존한다.
현재 Windows 패키징과 실제 화면 검토는 Stage 51D에서 진행한다.
