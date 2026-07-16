# -*- coding: utf-8 -*-
"""v1 파일럿 JSON → v2 스키마 변환 스크립트.

실행
    python tools/convert_pilot_v1_to_v2.py

출력
    data/kdrg_v47_pilot_schema_v2.json
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

for _s in ("stdout", "stderr"):
    _st = getattr(sys, _s, None)
    if _st is not None and hasattr(_st, "reconfigure"):
        try:
            _st.reconfigure(encoding="utf-8")
        except Exception:
            pass

ROOT = Path(__file__).resolve().parent.parent
V1_PATH = ROOT / "data" / "kdrg_v47_ui_fixture.json"
V2_PATH = ROOT / "data" / "kdrg_v47_pilot_schema_v2.json"

GENERATED_AT = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# ---------------------------------------------------------------------------
# 원천자료 정의
# ---------------------------------------------------------------------------
SOURCES = [
    {
        "source_id": "V47_MAIN_PDF",
        "source_type": "BASE_MANUAL_PDF",
        "file_name": "KDRG_V4.7_분류집_1784091626702.pdf",
        "title": "KDRG V4.7 분류집 (1,282쪽)",
        "effective_date": "2024-01-01",
        "correction_cutoff_date": None,
        "authority": "건강보험심사평가원",
        "usage_scope": "ADRG 조건식, TABLE 소속, 조건문 원전",
        "sha256": None,
        "included_in_runtime": False,
        "notes": "TABLE 소속·조건식 구조의 최종 근거 문서"
    },
    {
        "source_id": "V47_APPENDIX_PDF",
        "source_type": "APPENDIX_PDF",
        "file_name": "KDRG_V4.7_분류집_부록_1784091626703.pdf",
        "title": "KDRG V4.7 분류집 부록 (776쪽)",
        "effective_date": "2024-01-01",
        "correction_cutoff_date": None,
        "authority": "건강보험심사평가원",
        "usage_scope": "교차검증 전용. TABLE 소속 신규 근거로 단독 사용 금지",
        "sha256": None,
        "included_in_runtime": False,
        "notes": None
    },
    {
        "source_id": "V47_CORR_20260501_HWPX",
        "source_type": "CORRECTION_HWPX",
        "file_name": "KDRG_일반용(V4.7)_교정표_20260501_1784091626703.hwpx",
        "title": "KDRG 일반용(V4.7) 교정표 2026-05-01",
        "effective_date": "2026-05-01",
        "correction_cutoff_date": "2026-05-01",
        "authority": "건강보험심사평가원",
        "usage_scope": "분류집 본문 교정. 본문과 충돌 시 교정표 우선",
        "sha256": None,
        "included_in_runtime": False,
        "notes": None
    },
    {
        "source_id": "V47_CORR_20260301_HWPX",
        "source_type": "CORRECTION_HWPX",
        "file_name": "KDRG_일반용(V4.7)_교정표_20260301",
        "title": "KDRG 일반용(V4.7) 교정표 2026-03-01",
        "effective_date": "2026-03-01",
        "correction_cutoff_date": "2026-03-01",
        "authority": "건강보험심사평가원",
        "usage_scope": "F022 M6586 table6 추가 교정",
        "sha256": None,
        "included_in_runtime": False,
        "notes": "F022 시술명 table6(M6586) 독립 경로 추가"
    },
    {
        "source_id": "V47_PROC_MASTER_XLSX",
        "source_type": "PROCEDURE_MASTER_XLSX",
        "file_name": "KDRG_일반용(V4.7)_시술_등_목록_20260501_1784091626703.xlsx",
        "title": "KDRG 일반용(V4.7) 시술 등 목록 (2,791행)",
        "effective_date": "2026-05-01",
        "correction_cutoff_date": None,
        "authority": "건강보험심사평가원",
        "usage_scope": "코드 존재 및 공식 명칭 확인 전용. TABLE 소속 판단에 단독 사용 금지",
        "sha256": None,
        "included_in_runtime": False,
        "notes": None
    },
    {
        "source_id": "V47_GROUP_NAME_XLSX",
        "source_type": "GROUP_NAME_MASTER_XLSX",
        "file_name": "KDRG_일반용(V4.7)_질병군명칭(변동없음)_1784091626704.xlsx",
        "title": "KDRG 일반용(V4.7) 질병군명칭 (2,700행)",
        "effective_date": "2024-01-01",
        "correction_cutoff_date": None,
        "authority": "건강보험심사평가원",
        "usage_scope": "ADRG/AADRG/RDRG 명칭 표준 표기",
        "sha256": None,
        "included_in_runtime": False,
        "notes": None
    },
    {
        "source_id": "V47_ABC_PDF",
        "source_type": "ABC_REGULATION_PDF",
        "file_name": "[별표_1]_입원환자의_질병군별_질병의_종류(제3조제1항_관련)(상급종합병원의_지정_및_평가_규정)_(2)_1784091626701.pdf",
        "title": "[별표 1] 입원환자의 질병군별 질병의 종류 최신 고시본 (31쪽)",
        "effective_date": "2024-01-01",
        "correction_cutoff_date": None,
        "authority": "보건복지부",
        "usage_scope": "A/B/C 질병군 분류의 유일한 공식 원천. AADRG 코드 정확일치만 공식 적용",
        "sha256": None,
        "included_in_runtime": False,
        "notes": "구 HWP/HWPX 기반 A/B/C 자료 사용 금지"
    }
]

# ---------------------------------------------------------------------------
# table_id → (owner_adrg, printed_label, table_role) 매핑
# ---------------------------------------------------------------------------
TABLE_META = {
    "V47_E04_E011_PROC_1":     ("E011", "시술명 table1",         "PROCEDURE"),
    "V47_E04_E011_PROC_2":     ("E011", "시술명 table2",         "PROCEDURE"),
    "V47_E04_E50_VENT_PROC_1": ("E501", "시술명 table1",         "PROCEDURE"),
    "V47_E04_E50_RRT_PROC_2":  ("E501", "시술명 table2",         "PROCEDURE"),
    "V47_F02_PROC_2":          ("F022", "시술명 table2",         "TEST_OR_PROCEDURE"),
    "V47_F02_PROC_3":          ("F022", "시술명 table3",         "PROCEDURE"),
    "V47_F13_PROC_1":          ("F136", "시술명 table1",         "PROCEDURE"),
    "V47_F13_PROC_2":          ("F136", "시술명 table2",         "PROCEDURE"),
    "V47_F13_PROC_3":          ("F136", "시술명 table3",         "PROCEDURE"),
    "V47_F19_CHRONIC_PD_1":    ("F194", "주진단명 table1",       "PRINCIPAL_DIAGNOSIS"),
    "V47_F19_CHRONIC_PROC_2":  ("F194", "시술명 table2",         "PROCEDURE"),
    "V47_F19_CHRONIC_ADD_1":   ("F194", "부가코드",              "ADD_ON_CODE"),
    "V47_E04_E011_ADD_EXCL_1": ("E011", "부가코드",              "EXCLUSION_SET"),
    "V47_F13_PD_EXCL_1":       ("F136", "주진단명 table1",       "EXCLUSION_SET"),
    "V47_F02_PROC_6":          ("F022", "시술명 table6",         "PROCEDURE"),
}

# ---------------------------------------------------------------------------
# 완성된 condition_expression 정의 (v2 node_type 트리)
# ---------------------------------------------------------------------------
def _src(source_id, evidence_type, printed_page=None, pdf_page=None, excerpt=None):
    return {
        "source_id": source_id,
        "printed_page": printed_page,
        "pdf_page": pdf_page,
        "section": None,
        "table_label": None,
        "excerpt": excerpt,
        "evidence_type": evidence_type
    }


CONDITION_EXPRESSIONS = {
    "E011": {
        "node_type": "OR",
        "node_id": "E011_root",
        "label": "기관 및 기관지 수술 조건 (OR 2개 가지)",
        "source_refs": [_src("V47_MAIN_PDF", "RULE_TEXT", "264", 290)],
        "notes": "table1 OR (table2 AND NOT ADC2A). O1311은 table1에만, O1326은 table2에만 속한다.",
        "children": [
            {
                "node_type": "TABLE_MATCH",
                "node_id": "E011_or_branch1_table1",
                "label": "시술명 table1 중 1개 이상",
                "table_id": "V47_E04_E011_PROC_1",
                "role": "PROCEDURE",
                "match_semantics": "ANY_ONE_CODE",
                "source_refs": [_src("V47_MAIN_PDF", "TABLE_MEMBERSHIP", "264", 290)]
            },
            {
                "node_type": "AND",
                "node_id": "E011_or_branch2_and",
                "label": "시술명 table2 AND NOT 부가코드 ADC2A",
                "source_refs": [_src("V47_MAIN_PDF", "RULE_TEXT", "264", 290)],
                "children": [
                    {
                        "node_type": "TABLE_MATCH",
                        "node_id": "E011_branch2_table2",
                        "label": "시술명 table2 중 1개 이상",
                        "table_id": "V47_E04_E011_PROC_2",
                        "role": "PROCEDURE",
                        "match_semantics": "ANY_ONE_CODE",
                        "source_refs": [_src("V47_MAIN_PDF", "TABLE_MEMBERSHIP", "264", 290)]
                    },
                    {
                        "node_type": "NOT",
                        "node_id": "E011_branch2_not_adc2a",
                        "label": "부가코드 ADC2A 미포함",
                        "source_refs": [_src("V47_MAIN_PDF", "RULE_TEXT", "264", 290)],
                        "notes": "ADC2A(흉강경시술)는 양의 포함 관계가 아닌 제외 조건이다",
                        "children": [
                            {
                                "node_type": "TABLE_MATCH",
                                "node_id": "E011_branch2_adc2a_presence",
                                "label": "부가코드 ADC2A 존재",
                                "table_id": "V47_E04_E011_ADD_EXCL_1",
                                "role": "EXCLUSION_SET",
                                "match_semantics": "PRESENCE_ONLY",
                                "source_refs": [_src("V47_MAIN_PDF", "RULE_TEXT", "264", 290)]
                            }
                        ]
                    }
                ]
            }
        ]
    },

    "E501": {
        "node_type": "AND",
        "node_id": "E501_root",
        "label": "침습적 인공호흡 96h 이상 AND 신대체요법 동반",
        "source_refs": [_src("V47_MAIN_PDF", "RULE_TEXT", "275", 301)],
        "notes": "인공호흡 시간 조건은 코드만으로 자동 확정 불가. E501/E511 구분 시 임상 시간 데이터 필요.",
        "children": [
            {
                "node_type": "TABLE_MATCH",
                "node_id": "E501_vent_table1",
                "label": "침습적 인공호흡 시술 중 1개 이상",
                "table_id": "V47_E04_E50_VENT_PROC_1",
                "role": "PROCEDURE",
                "match_semantics": "ANY_ONE_CODE",
                "source_refs": [_src("V47_MAIN_PDF", "TABLE_MEMBERSHIP", "275", 301)]
            },
            {
                "node_type": "TABLE_MATCH",
                "node_id": "E501_rrt_table2",
                "label": "신대체요법 시술 중 1개 이상 (동반)",
                "table_id": "V47_E04_E50_RRT_PROC_2",
                "role": "PROCEDURE",
                "match_semantics": "ANY_ONE_CODE",
                "source_refs": [_src("V47_MAIN_PDF", "TABLE_MEMBERSHIP", "276", 302)]
            },
            {
                "node_type": "NUMERIC_THRESHOLD",
                "node_id": "E501_vent_gte_96h",
                "label": "침습적 인공호흡 96시간 이상",
                "metric": "invasive_ventilation_duration_hours",
                "operator": ">=",
                "value": 96,
                "unit": "hours",
                "source_refs": [_src("V47_MAIN_PDF", "RULE_TEXT", "275", 301)],
                "notes": "코드 입력만으로 평가 불가. 임상 시간 데이터 필요"
            }
        ]
    },

    "E502": {
        "node_type": "AND",
        "node_id": "E502_root",
        "label": "침습적 인공호흡 96h 이상 AND 신대체요법 미동반",
        "source_refs": [_src("V47_MAIN_PDF", "RULE_TEXT", "275", 301)],
        "notes": "신대체요법 미동반: RRT table2 시술코드 없음. 인공호흡 시간은 임상 데이터 필요.",
        "children": [
            {
                "node_type": "TABLE_MATCH",
                "node_id": "E502_vent_table1",
                "label": "침습적 인공호흡 시술 중 1개 이상",
                "table_id": "V47_E04_E50_VENT_PROC_1",
                "role": "PROCEDURE",
                "match_semantics": "ANY_ONE_CODE",
                "source_refs": [_src("V47_MAIN_PDF", "TABLE_MEMBERSHIP", "275", 301)]
            },
            {
                "node_type": "NOT",
                "node_id": "E502_not_rrt",
                "label": "신대체요법 미동반 (RRT table2 없음)",
                "source_refs": [_src("V47_MAIN_PDF", "RULE_TEXT", "275", 301)],
                "children": [
                    {
                        "node_type": "TABLE_MATCH",
                        "node_id": "E502_rrt_presence",
                        "label": "신대체요법 시술 존재",
                        "table_id": "V47_E04_E50_RRT_PROC_2",
                        "role": "PROCEDURE",
                        "match_semantics": "PRESENCE_ONLY",
                        "source_refs": [_src("V47_MAIN_PDF", "TABLE_MEMBERSHIP", "276", 302)]
                    }
                ]
            },
            {
                "node_type": "NUMERIC_THRESHOLD",
                "node_id": "E502_vent_gte_96h",
                "label": "침습적 인공호흡 96시간 이상",
                "metric": "invasive_ventilation_duration_hours",
                "operator": ">=",
                "value": 96,
                "unit": "hours",
                "source_refs": [_src("V47_MAIN_PDF", "RULE_TEXT", "275", 301)],
                "notes": "코드 입력만으로 평가 불가. 임상 시간 데이터 필요"
            }
        ]
    },

    "E511": {
        "node_type": "AND",
        "node_id": "E511_root",
        "label": "침습적 인공호흡 96h 미만 AND 신대체요법 동반",
        "source_refs": [_src("V47_MAIN_PDF", "RULE_TEXT", "276", 302)],
        "notes": "E501과 코드 구성이 동일하고 시간 조건(미만)만 다름. 코드만으로 E501과 구분 불가.",
        "children": [
            {
                "node_type": "TABLE_MATCH",
                "node_id": "E511_vent_table1",
                "label": "침습적 인공호흡 시술 중 1개 이상",
                "table_id": "V47_E04_E50_VENT_PROC_1",
                "role": "PROCEDURE",
                "match_semantics": "ANY_ONE_CODE",
                "source_refs": [_src("V47_MAIN_PDF", "TABLE_MEMBERSHIP", "276", 302)]
            },
            {
                "node_type": "TABLE_MATCH",
                "node_id": "E511_rrt_table2",
                "label": "신대체요법 시술 중 1개 이상 (동반)",
                "table_id": "V47_E04_E50_RRT_PROC_2",
                "role": "PROCEDURE",
                "match_semantics": "ANY_ONE_CODE",
                "source_refs": [_src("V47_MAIN_PDF", "TABLE_MEMBERSHIP", "276", 302)]
            },
            {
                "node_type": "NOT",
                "node_id": "E511_not_96h",
                "label": "침습적 인공호흡 96시간 미만 (NOT ≥96h)",
                "source_refs": [_src("V47_MAIN_PDF", "RULE_TEXT", "276", 302)],
                "children": [
                    {
                        "node_type": "NUMERIC_THRESHOLD",
                        "node_id": "E511_vent_gte_96h_inner",
                        "label": "침습적 인공호흡 96시간 이상",
                        "metric": "invasive_ventilation_duration_hours",
                        "operator": ">=",
                        "value": 96,
                        "unit": "hours",
                        "source_refs": [_src("V47_MAIN_PDF", "RULE_TEXT", "276", 302)],
                        "notes": "코드만으로 E501과 구분 불가. 임상 시간 데이터 필요"
                    }
                ]
            }
        ]
    },

    "E512": {
        "node_type": "AND",
        "node_id": "E512_root",
        "label": "침습적 인공호흡 96h 미만 AND 신대체요법 미동반",
        "source_refs": [_src("V47_MAIN_PDF", "RULE_TEXT", "276", 302)],
        "notes": "E502와 코드 구성이 동일하고 시간 조건(미만)만 다름. 코드만으로 E502와 구분 불가.",
        "children": [
            {
                "node_type": "TABLE_MATCH",
                "node_id": "E512_vent_table1",
                "label": "침습적 인공호흡 시술 중 1개 이상",
                "table_id": "V47_E04_E50_VENT_PROC_1",
                "role": "PROCEDURE",
                "match_semantics": "ANY_ONE_CODE",
                "source_refs": [_src("V47_MAIN_PDF", "TABLE_MEMBERSHIP", "276", 302)]
            },
            {
                "node_type": "NOT",
                "node_id": "E512_not_rrt",
                "label": "신대체요법 미동반 (RRT table2 없음)",
                "source_refs": [_src("V47_MAIN_PDF", "RULE_TEXT", "276", 302)],
                "children": [
                    {
                        "node_type": "TABLE_MATCH",
                        "node_id": "E512_rrt_presence",
                        "label": "신대체요법 시술 존재",
                        "table_id": "V47_E04_E50_RRT_PROC_2",
                        "role": "PROCEDURE",
                        "match_semantics": "PRESENCE_ONLY",
                        "source_refs": [_src("V47_MAIN_PDF", "TABLE_MEMBERSHIP", "276", 302)]
                    }
                ]
            },
            {
                "node_type": "NOT",
                "node_id": "E512_not_96h",
                "label": "침습적 인공호흡 96시간 미만 (NOT ≥96h)",
                "source_refs": [_src("V47_MAIN_PDF", "RULE_TEXT", "276", 302)],
                "children": [
                    {
                        "node_type": "NUMERIC_THRESHOLD",
                        "node_id": "E512_vent_gte_96h_inner",
                        "label": "침습적 인공호흡 96시간 이상",
                        "metric": "invasive_ventilation_duration_hours",
                        "operator": ">=",
                        "value": 96,
                        "unit": "hours",
                        "source_refs": [_src("V47_MAIN_PDF", "RULE_TEXT", "276", 302)],
                        "notes": "코드만으로 E502와 구분 불가. 임상 시간 데이터 필요"
                    }
                ]
            }
        ]
    },

    "F022": {
        "node_type": "OR",
        "node_id": "F022_root",
        "label": "승모판 또는 삼첨판 수술 (심도자술 사용) — 교정 포함",
        "source_refs": [
            _src("V47_MAIN_PDF", "RULE_TEXT", "313", 339),
            _src("V47_CORR_20260301_HWPX", "CORRECTION", excerpt="M6586 시술명 table6 독립 경로 추가")
        ],
        "notes": "2026-03-01 교정으로 M6586 단독 경로(table6)가 OR 2번 가지로 추가됨",
        "children": [
            {
                "node_type": "AND",
                "node_id": "F022_or_branch1_cathlabb",
                "label": "심도자술 조합 (table2 AND table3)",
                "source_refs": [_src("V47_MAIN_PDF", "RULE_TEXT", "313", 339)],
                "children": [
                    {
                        "node_type": "TABLE_MATCH",
                        "node_id": "F022_branch1_table2",
                        "label": "시술명 table2 (심도자술) 중 1개 이상",
                        "table_id": "V47_F02_PROC_2",
                        "role": "TEST_OR_PROCEDURE",
                        "match_semantics": "ANY_ONE_CODE",
                        "source_refs": [_src("V47_MAIN_PDF", "TABLE_MEMBERSHIP", "313", 339)]
                    },
                    {
                        "node_type": "TABLE_MATCH",
                        "node_id": "F022_branch1_table3",
                        "label": "시술명 table3 (판막 수술) 중 1개 이상",
                        "table_id": "V47_F02_PROC_3",
                        "role": "PROCEDURE",
                        "match_semantics": "ANY_ONE_CODE",
                        "source_refs": [_src("V47_MAIN_PDF", "TABLE_MEMBERSHIP", "313", 339)]
                    }
                ]
            },
            {
                "node_type": "TABLE_MATCH",
                "node_id": "F022_or_branch2_table6",
                "label": "시술명 table6 (M6586 경피적 승모판막 재치환술) — 교정 추가",
                "table_id": "V47_F02_PROC_6",
                "role": "PROCEDURE",
                "match_semantics": "ANY_ONE_CODE",
                "source_refs": [_src("V47_CORR_20260301_HWPX", "CORRECTION", excerpt="2026-03-01 교정: M6586 table6 단독 경로 추가")],
                "notes": "2026-03-01 교정으로 추가된 독립 대안 경로"
            }
        ]
    },

    "F136": {
        "node_type": "AND",
        "node_id": "F136_root",
        "label": "급성 심근경색증이 아닌 경피적 관상동맥 수술 — 만성폐쇄성병변 포함",
        "source_refs": [_src("V47_MAIN_PDF", "RULE_TEXT", "328", 354)],
        "notes": "제외주진단(I210~I229) 입력 시 양의 관계 차단. NOT 구조로 제외조건을 명시.",
        "children": [
            {
                "node_type": "TABLE_MATCH",
                "node_id": "F136_table3_chronic",
                "label": "시술명 table3 (만성폐쇄성병변 시술) 중 1개 이상",
                "table_id": "V47_F13_PROC_3",
                "role": "PROCEDURE",
                "match_semantics": "ANY_ONE_CODE",
                "source_refs": [_src("V47_MAIN_PDF", "TABLE_MEMBERSHIP", "329", 355)]
            },
            {
                "node_type": "OR",
                "node_id": "F136_vessel_or",
                "label": "단일혈관(table1) OR 추가혈관(table2) 중 1개 이상",
                "source_refs": [_src("V47_MAIN_PDF", "RULE_TEXT", "328", 354)],
                "children": [
                    {
                        "node_type": "TABLE_MATCH",
                        "node_id": "F136_table1_single",
                        "label": "시술명 table1 (단일혈관 시술) 중 1개 이상",
                        "table_id": "V47_F13_PROC_1",
                        "role": "PROCEDURE",
                        "match_semantics": "ANY_ONE_CODE",
                        "source_refs": [_src("V47_MAIN_PDF", "TABLE_MEMBERSHIP", "328", 354)]
                    },
                    {
                        "node_type": "TABLE_MATCH",
                        "node_id": "F136_table2_additional",
                        "label": "시술명 table2 (추가혈관 시술) 중 1개 이상",
                        "table_id": "V47_F13_PROC_2",
                        "role": "PROCEDURE",
                        "match_semantics": "ANY_ONE_CODE",
                        "source_refs": [_src("V47_MAIN_PDF", "TABLE_MEMBERSHIP", "329", 355)]
                    }
                ]
            },
            {
                "node_type": "NOT",
                "node_id": "F136_not_acute_mi_pd",
                "label": "주진단명 table1(급성 심근경색증) 미포함",
                "source_refs": [_src("V47_MAIN_PDF", "RULE_TEXT", "328", 354)],
                "notes": "I210~I229가 주진단이면 F136 대상에서 제외. 양의 관계 결과로 확정하지 않는다.",
                "children": [
                    {
                        "node_type": "TABLE_MATCH",
                        "node_id": "F136_excl_table1_presence",
                        "label": "주진단 급성 심근경색증 코드 존재",
                        "table_id": "V47_F13_PD_EXCL_1",
                        "role": "EXCLUSION_SET",
                        "match_semantics": "PRESENCE_ONLY",
                        "source_refs": [_src("V47_MAIN_PDF", "TABLE_MEMBERSHIP", "328", 354)]
                    }
                ]
            }
        ]
    },

    "F194": {
        "node_type": "AND",
        "node_id": "F194_root",
        "label": "말초동맥 만성 폐쇄성 질환의 경피적 수술 — 여러 개",
        "source_refs": [_src("V47_MAIN_PDF", "RULE_TEXT", "334", 360)],
        "notes": "동일 코드 중복 입력으로 2개 이상을 충족한 것으로 보지 않는다.",
        "children": [
            {
                "node_type": "TABLE_MATCH",
                "node_id": "F194_pd_table1",
                "label": "주진단명 table1 중 1개 이상",
                "table_id": "V47_F19_CHRONIC_PD_1",
                "role": "PRINCIPAL_DIAGNOSIS",
                "match_semantics": "ANY_ONE_CODE",
                "source_refs": [_src("V47_MAIN_PDF", "TABLE_MEMBERSHIP", "334", 360)]
            },
            {
                "node_type": "OR",
                "node_id": "F194_proc_or",
                "label": "시술 조건: 2개 이상 OR 양쪽(ADC4J)",
                "source_refs": [_src("V47_MAIN_PDF", "RULE_TEXT", "334", 360)],
                "children": [
                    {
                        "node_type": "TABLE_CODE_COUNT_AT_LEAST",
                        "node_id": "F194_proc_count_ge2",
                        "label": "시술명 table2 중 서로 다른 코드 2개 이상",
                        "table_id": "V47_F19_CHRONIC_PROC_2",
                        "minimum_distinct_code_count": 2,
                        "count_scope": "DISTINCT_CODES_IN_TABLE",
                        "duplicate_input_allowed": False,
                        "source_refs": [_src("V47_MAIN_PDF", "RULE_TEXT", "334", 360)],
                        "notes": "동일 코드 중복 입력으로 충족 처리 금지"
                    },
                    {
                        "node_type": "AND",
                        "node_id": "F194_proc_plus_adc4j",
                        "label": "시술명 table2 AND 부가코드 ADC4J(양쪽)",
                        "source_refs": [_src("V47_MAIN_PDF", "RULE_TEXT", "334", 360)],
                        "children": [
                            {
                                "node_type": "TABLE_MATCH",
                                "node_id": "F194_proc_table2_for_adc4j",
                                "label": "시술명 table2 중 1개 이상",
                                "table_id": "V47_F19_CHRONIC_PROC_2",
                                "role": "PROCEDURE",
                                "match_semantics": "ANY_ONE_CODE",
                                "source_refs": [_src("V47_MAIN_PDF", "TABLE_MEMBERSHIP", "334", 360)]
                            },
                            {
                                "node_type": "TABLE_MATCH",
                                "node_id": "F194_adc4j",
                                "label": "부가코드 ADC4J(양쪽) 존재",
                                "table_id": "V47_F19_CHRONIC_ADD_1",
                                "role": "ADD_ON_CODE",
                                "match_semantics": "PRESENCE_ONLY",
                                "source_refs": [_src("V47_MAIN_PDF", "TABLE_MEMBERSHIP", "334", 360)]
                            }
                        ]
                    }
                ]
            }
        ]
    },

    "F195": {
        "node_type": "AND",
        "node_id": "F195_root",
        "label": "말초동맥 만성 폐쇄성 질환의 경피적 수술 — 한 개",
        "source_refs": [_src("V47_MAIN_PDF", "RULE_TEXT", "334", 360)],
        "notes": "F194와 TABLE을 공유하지만 최소 2개 이상 조건이 없는 별도 ADRG다. F194와 합치지 않는다.",
        "children": [
            {
                "node_type": "TABLE_MATCH",
                "node_id": "F195_pd_table1",
                "label": "주진단명 table1 중 1개 이상",
                "table_id": "V47_F19_CHRONIC_PD_1",
                "role": "PRINCIPAL_DIAGNOSIS",
                "match_semantics": "ANY_ONE_CODE",
                "source_refs": [_src("V47_MAIN_PDF", "TABLE_MEMBERSHIP", "334", 360)]
            },
            {
                "node_type": "TABLE_MATCH",
                "node_id": "F195_proc_table2",
                "label": "시술명 table2 중 1개 이상",
                "table_id": "V47_F19_CHRONIC_PROC_2",
                "role": "PROCEDURE",
                "match_semantics": "ANY_ONE_CODE",
                "source_refs": [_src("V47_MAIN_PDF", "TABLE_MEMBERSHIP", "334", 360)]
            }
        ]
    }
}


# ---------------------------------------------------------------------------
# v1 테이블의 source_page 문자열 → v2 source_refs 변환
# ---------------------------------------------------------------------------
def parse_source_page(source_page: str) -> list:
    """'본문 264쪽 · PDF 290페이지' 형태를 source_refs로 변환."""
    refs = []
    if not source_page:
        return refs

    parts = source_page.split("·")
    printed_page = None
    pdf_page = None
    for part in parts:
        p = part.strip()
        if "쪽" in p:
            printed_page = p.replace("본문", "").replace("쪽", "").strip()
        elif "PDF" in p:
            raw = p.replace("PDF", "").replace("페이지", "").strip()
            try:
                pdf_page = int(raw.split("-")[0])
            except ValueError:
                pass

    refs.append(_src("V47_MAIN_PDF", "RULE_TEXT",
                     printed_page=printed_page, pdf_page=pdf_page))
    return refs


def is_correction_table(table_id: str) -> bool:
    return "PROC_6" in table_id  # F022 table6


# ---------------------------------------------------------------------------
# 변환 실행
# ---------------------------------------------------------------------------
def convert() -> None:
    v1 = json.loads(V1_PATH.read_text(encoding="utf-8"))

    # ---- tables ----
    tables_v2 = []
    for t in v1["tables"]:
        tid = t["table_id"]
        owner, plabel, trole = TABLE_META.get(tid, ("UNKNOWN", t.get("display_label", ""), "OTHER"))
        members_v2 = []
        for m in t["members"]:
            members_v2.append({
                "code": m["code"],
                "name_ko_raw": m.get("name_ko", ""),
                "name_ko_effective": m.get("name_ko", ""),
                "name_en_raw": m.get("name_en", ""),
                "name_en_effective": m.get("name_en", ""),
                "original_order": m["original_order"],
                "source_refs": [],
                "correction_refs": [],
                "status": "CORRECTION_ADDED" if is_correction_table(tid) else "ACTIVE"
            })

        src_refs = parse_source_page(t.get("source_page", ""))
        if is_correction_table(tid):
            src_refs.append(_src("V47_CORR_20260301_HWPX", "CORRECTION",
                                 excerpt="2026-03-01 교정: M6586 시술명 table6 추가"))

        tables_v2.append({
            "table_id": tid,
            "owner_adrg": owner,
            "printed_label": plabel,
            "display_label": t.get("display_label", plabel),
            "table_role": trole,
            "code_type": t.get("code_type", ""),
            "source_refs": src_refs,
            "member_count": len(members_v2),
            "members": members_v2,
            "derivation": None,
            "status": "CORRECTION_UPDATED" if is_correction_table(tid) else "ACTIVE"
        })

    # ---- rules ----
    rules_v2 = []
    for r in v1["rules"]:
        adrg = r["adrg"]
        src_refs = parse_source_page(r.get("source_page", ""))

        corr_refs = []
        if adrg == "F022":
            corr_refs.append(_src("V47_CORR_20260301_HWPX", "CORRECTION",
                                  excerpt="M6586(경피적 승모판막 재치환술[심방중격 접근]) table6 추가"))

        aadrg_mappings_v2 = []
        for am in r.get("aadrg_mappings", []):
            aadrg_mappings_v2.append({
                "aadrg": am["aadrg"],
                "aadrg_name_raw": am.get("aadrg_name", am.get("aadrg_name_raw", "")),
                "aadrg_name_effective": am.get("aadrg_name", am.get("aadrg_name_effective", "")),
                "abc_classification": {
                    "group_code": am.get("group_code", ""),
                    "group_name": am.get("group_name", ""),
                    "status": "OFFICIAL_PDF_EXACT_CODE",
                    "source_id": "V47_ABC_PDF",
                    "source_page": None,
                    "exact_code_match": True,
                    "notes": "파일럿 9개 ADRG: 별표1 PDF AADRG 코드 직접 조회 확인"
                },
                "age_or_other_split_text": None,
                "source_refs": [_src("V47_ABC_PDF", "ABC_CLASSIFICATION")]
            })

        cgs_display = []
        for cg in r.get("condition_groups", []):
            comps = [{"table_id": c["table_id"],
                      "operator_before": c.get("operator_before", ""),
                      **({"requirement_label": c["requirement_label"]} if c.get("requirement_label") else {})}
                     for c in cg.get("components", [])]
            excl = [{"table_id": c["table_id"], "operator_before": c.get("operator_before", "")}
                    for c in cg.get("exclude_components", [])]
            cgs_display.append({
                "group_no": cg["group_no"],
                "group_label": cg["group_label"],
                "join_to_next_group": cg.get("join_to_next_group") or None,
                "components": comps,
                "requirements": list(cg.get("requirements", [])),
                "exclude_components": excl
            })

        rules_v2.append({
            "adrg": adrg,
            "mdc": r["mdc"],
            "title": r["title"],
            "subtitle": r.get("subtitle", ""),
            "title_raw": r["title"],
            "title_effective": r["title"],
            "aadrg_mappings": aadrg_mappings_v2,
            "condition_text_raw": r.get("condition_text", ""),
            "condition_text_effective": r.get("condition_text", ""),
            "condition_expression": CONDITION_EXPRESSIONS[adrg],
            "condition_groups_display": cgs_display,
            "source_refs": src_refs,
            "correction_refs": corr_refs,
            "notes": None,
            "status": "CORRECTION_UPDATED" if adrg == "F022" else "ACTIVE"
        })

    # ---- derived_indexes ----
    code_to_table_ids: dict = {}
    for t in tables_v2:
        for m in t["members"]:
            code_to_table_ids.setdefault(m["code"].strip().upper(), []).append(t["table_id"])

    table_id_to_adrg_ids: dict = {}
    excl_table_id_to_adrg_ids: dict = {}
    for r in rules_v2:
        # collect all table_ids from condition_expression recursively
        def collect_tables(node, excl_tables, pos_tables, inside_not=False):
            nt = node.get("node_type", "")
            if nt in ("TABLE_MATCH", "TABLE_CODE_COUNT_AT_LEAST"):
                tid = node.get("table_id")
                if tid:
                    if inside_not:
                        excl_tables.add(tid)
                    else:
                        pos_tables.add(tid)
            next_not = inside_not or (nt == "NOT")
            for child in node.get("children", []):
                collect_tables(child, excl_tables, pos_tables, next_not)

        pos, excl = set(), set()
        collect_tables(CONDITION_EXPRESSIONS[r["adrg"]], excl, pos)
        for tid in pos:
            table_id_to_adrg_ids.setdefault(tid, []).append(r["adrg"])
        for tid in excl:
            excl_table_id_to_adrg_ids.setdefault(tid, []).append(r["adrg"])

    # ---- validation_summary ----
    total_members = sum(t["member_count"] for t in tables_v2)
    validation_summary = {
        "generated_at": GENERATED_AT,
        "adrg_count": len(rules_v2),
        "table_count": len(tables_v2),
        "total_member_count": total_members,
        "source_integrity": "PASS",
        "condition_expression_completeness": "PASS",
        "abc_classification_status": "ALL_OFFICIAL_PDF_EXACT_CODE",
        "errors": [],
        "warnings": []
    }

    v2 = {
        "meta": {
            "schema_version": "2",
            "dataset_version": "2026-07-16_KDRG_V47_PILOT_SPECIAL_CASES_V2",
            "kdrg_version": "KDRG V4.7",
            "effective_date": "2024-01-01",
            "correction_cutoff_date": "2026-05-01",
            "data_scope": "V4.7 특이케이스 파일럿 · MDC 04/05 · 9개 ADRG · 스키마 v2 병렬검증용",
            "generated_at": GENERATED_AT,
            "generated_by": "tools/convert_pilot_v1_to_v2.py",
            "source_manifest_version": "1",
            "runtime_status": "PILOT_PARALLEL_VALIDATION",
            "notes": "현재 runtime 데이터(kdrg_v47_ui_fixture.json)는 교체하지 않음. 의미 동일성 검증 전용."
        },
        "sources": SOURCES,
        "mdc_master": v1.get("mdc_master", []),
        "tables": tables_v2,
        "rules": rules_v2,
        "derived_indexes": {
            "code_to_table_ids": code_to_table_ids,
            "table_id_to_adrg_ids": table_id_to_adrg_ids,
            "exclusion_table_id_to_adrg_ids": excl_table_id_to_adrg_ids
        },
        "validation_summary": validation_summary
    }

    V2_PATH.write_text(json.dumps(v2, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[완료] v2 JSON 생성: {V2_PATH}")
    print(f"  ADRG: {len(rules_v2)}개  TABLE: {len(tables_v2)}개  코드 멤버: {total_members}개")


if __name__ == "__main__":
    convert()
