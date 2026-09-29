KDRG 코드 관계 검색기 v16
MDC 검색 + 복수 코드 관계검색 테스트 버전
============================================================

1. 실행 구조

kdrg_relation_search_v16_mdc_advanced_search.py
data/
  kdrg_relation_data_v16_mdc_advanced_search.json

2. 실행

pip install PySide6
python kdrg_relation_search_v16_mdc_advanced_search.py

3. 이번 버전 신규 기능

[가] MDC 검색
- MDC 04 / MDC04 / 호흡기계
- MDC 05 / MDC05 / 순환기계
- MDC 상세에서 전체 ADRG 및 A/B/C군별 목록 확인
- ADRG 상세 진입 후 뒤로가기로 MDC 목록 복귀

[나] 복수 코드 관계검색
- 기존 단일 검색창은 그대로 유지
- 상단의 '복수 코드 관계검색 펼치기'에서 2~6개 코드 입력
- 코드유형 선택 또는 자동판별
- AND / OR 관계검색
- 같은 ADRG의 같은 조건식 안에 모두 연결되는지 분석
- 서로 다른 OR 조건식에 분산된 경우 별도 경고
- 미입력 TABLE, 시간·연령·미포함 조건 등 추가 확인사항 표시
- 최종 조건충족 또는 DRG 판정은 하지 않음

4. 관계검색 결과 해석

같은 조건식 내 공통 연결
- 입력코드가 적어도 하나의 동일 condition_group 안에 모두 연결됨
- 남아 있는 TABLE이나 추가조건은 별도 확인해야 함

서로 다른 OR 조건식에 분산
- 입력코드 모두가 같은 ADRG에는 연결되지만 서로 다른 OR 대안에 위치함
- 하나의 조합조건으로 해석하면 안 됨

입력코드 일부 연결
- OR 검색에서 일부 코드만 해당 ADRG에 연결됨

5. 자동검증

python validate_kdrg_v16_mdc_advanced_search.py

검증 범위
- MDC master 및 별칭
- ADRG/AADRG/TABLE/코드 구조
- 조건그룹 연결
- E011/F136/F194/F600/E501 대표 관계검색
- PySide 문법 및 주요 UI 토큰

6. 중요 제한

이 기능은 KDRG 공식 조건구조 안의 코드 관계를 확인하는 검색 기능이다.
환자의 최종 DRG, 조건 충족 여부, 상위군 가능성, 가상 재분류를 판정하지 않는다.
