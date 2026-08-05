# Stage 51D — Dual-data parity + Windows packaged UI

## 확정한 구조

- Python/PySide 검색 서비스: `kdrg-v47-search-integrated-v2`
- Electron 검색 서비스: `kdrg-v47-search-integrated-v3`
- 운영 Electron 데이터: `data/kdrg_v47_search_integrated_v3.json`

두 서비스는 의도적으로 서로 다른 schema를 사용한다. Python 서비스를 v3로 억지로 전환하거나 v3를 v2로 변환한 더미 fixture를 만들지 않는다.

## 50B dual-data parity

- Python 검색 결과는 기존 v2 데이터에서 생성
- JavaScript/Electron 검색 결과는 운영 v3 데이터에서 생성
- ADRG·TABLE·CODE 등 공통 검색 projection만 비교
- v3 전용 `user_condition_projection_validation`은 Stage 51C 검증에서 별도 확인

## 현재 UI 계약

사용자 화면은 다음 섹션을 사용한다.

- 분류 조건
- 조건 상세
- 원문 근거

다음 구형 섹션은 표시하지 않는다.

- 기본 분류 TABLE
- 추가 분기조건

## Windows packaged UI

Windows portable exe에서 다음을 실제 실행한다.

- B013, B014, B018, B022, L033, 9610 검색
- 인라인 TABLE 펼치기 및 코드 행 로드
- PNG 6장 생성 및 SHA256 고유성 확인
- console error, renderer gone, main-frame load failure 0건 확인

실제 UI 검증 실패 시 SHA256 생성과 Release 업로드 단계로 진행하지 않는다.

## 데이터 정책

새 JSON, compatibility fixture, 더미 데이터는 만들지 않는다. 운영 v2·v3 파일의 내용과 SHA256은 변경하지 않는다.

## 현재 상태

커밋·버전 증가·태그 생성은 아직 금지한다.
