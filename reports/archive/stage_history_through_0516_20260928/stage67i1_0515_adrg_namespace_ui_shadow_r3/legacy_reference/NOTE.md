# legacy_reference 안내

이 폴더의 파일은 이전 버전(v16 / KDRG V4.6 세대) UI·데이터·검증 스크립트입니다.
화면 구조와 검증 방식을 참고하기 위해서만 보관하며, 다음 용도로는 사용하지 않습니다.

- **코드 소스로 사용 금지**: 여기 있는 `kdrg_relation_data_v16_*.json`의 코드/TABLE/ADRG
  데이터를 KDRG V4.7 화면의 실제 데이터로 가져다 쓰지 않습니다.
- **A/B/C 질병군 분류 기준으로 사용 금지**: A/B/C는 `sources/raw/`의 새 [별표 1] PDF만
  기준으로 삼습니다.
- **버전 표기 유지**: 이 폴더 밖(README, app/, data/, SOURCE_MANIFEST 등)의 사용자 노출
  텍스트에는 "KDRG V4.6"이라는 문자열이 나타나지 않아야 합니다.

포함 파일: v16 메인 스크립트, v16 데이터 JSON, v16 README/TEST_GUIDE/특이케이스 레지스트리,
v16 validate/smoke_test 스크립트.
