# -*- coding: utf-8 -*-
"""v2 스키마 JSON → v1 호환 딕셔너리 어댑터 (의미 동일성 검증 전용).

이 모듈은 현재 runtime 데이터(v1)를 교체하지 않고 v2 JSON을 읽어
KDRGDataStore가 기대하는 v1 dict 구조로 변환한다.
실제 UI 런타임에는 사용하지 않는다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def load_v2_as_v1_dict(v2_path: Path) -> Dict[str, Any]:
    """v2 JSON 파일을 읽어 v1 스키마 dict로 변환한다."""
    raw = json.loads(v2_path.read_text(encoding="utf-8"))
    return {
        "meta": _adapt_meta(raw.get("meta", {})),
        "mdc_master": raw.get("mdc_master", []),
        "tables": [_adapt_table(t) for t in raw.get("tables", [])],
        "rules": [_adapt_rule(r) for r in raw.get("rules", [])],
    }


# ---------------------------------------------------------------------------
# meta
# ---------------------------------------------------------------------------
def _adapt_meta(meta: Dict) -> Dict:
    return {
        "app_data_version": meta.get("dataset_version", ""),
        "kdrg_version": meta.get("kdrg_version", "KDRG V4.7"),
        "data_scope": meta.get("data_scope", ""),
        "ui_badge": "KDRG V4.7 PILOT · SPECIAL CASE",
        "notice": meta.get("notes", "v2 스키마 변환 데이터입니다. 의미 동일성 검증 전용."),
        "source_note": f"스키마 v2 · correction_cutoff: {meta.get('correction_cutoff_date', '-')}",
        "abc_basis": "[별표 1] 입원환자의 질병군별 질병의 종류 최신 고시본",
        "correction_basis": meta.get("correction_cutoff_date", "-"),
        "pilot_cases": [r for r in []],  # will be filled by caller if needed
    }


# ---------------------------------------------------------------------------
# table
# ---------------------------------------------------------------------------
def _adapt_table(t: Dict) -> Dict:
    members_v1 = []
    for m in t.get("members", []):
        members_v1.append({
            "code": m["code"],
            "name_ko": m.get("name_ko_effective", m.get("name_ko_raw", "")),
            "name_en": m.get("name_en_effective", m.get("name_en_raw", "")),
            "original_order": m["original_order"],
        })
    # source_refs → source_page (첫 번째 항목의 printed_page + pdf_page)
    src_refs = t.get("source_refs", [])
    source_page = _source_refs_to_page_str(src_refs)
    return {
        "table_id": t["table_id"],
        "display_label": t.get("display_label", t.get("printed_label", "")),
        "code_type": t.get("code_type", ""),
        "source_page": source_page,
        "members": members_v1,
    }


def _source_refs_to_page_str(refs: List[Dict]) -> str:
    for ref in refs:
        sid = ref.get("source_id", "")
        if "MAIN_PDF" in sid:
            pp = ref.get("printed_page")
            pdf_p = ref.get("pdf_page")
            parts = []
            if pp:
                parts.append(f"본문 {pp}쪽")
            if pdf_p:
                parts.append(f"PDF {pdf_p}페이지")
            return " · ".join(parts)
    return ""


# ---------------------------------------------------------------------------
# rule
# ---------------------------------------------------------------------------
def _adapt_rule(r: Dict) -> Dict:
    mappings = r.get("aadrg_mappings", [])
    first = mappings[0] if mappings else {}
    abc = first.get("abc_classification", {})

    # aadrg_mappings v1 형태
    aadrg_mappings_v1 = []
    for am in mappings:
        am_abc = am.get("abc_classification", {})
        v1_abc_status = _abc_status_v2_to_v1(am_abc.get("status", ""))
        aadrg_mappings_v1.append({
            "aadrg": am["aadrg"],
            "group_code": am_abc.get("group_code", ""),
            "group_name": am_abc.get("group_name", ""),
            "aadrg_name": am.get("aadrg_name_effective", am.get("aadrg_name_raw", "")),
            "abc_status": v1_abc_status,
        })

    # condition_groups_display → condition_groups (이름만 복원)
    cgs = []
    for cg in r.get("condition_groups_display", []):
        excl = cg.get("exclude_components", [])
        cgs.append({
            "group_no": cg["group_no"],
            "group_label": cg["group_label"],
            "join_to_next_group": cg.get("join_to_next_group"),
            "components": cg.get("components", []),
            "requirements": cg.get("requirements", []),
            "exclude_components": excl,
        })

    src_refs = r.get("source_refs", [])
    source_page = _source_refs_to_page_str(src_refs)

    return {
        "adrg": r["adrg"],
        "aadrg": first.get("aadrg", ""),
        "mdc": r["mdc"],
        "group_code": abc.get("group_code", ""),
        "group_name": abc.get("group_name", ""),
        "title": r.get("title", ""),
        "subtitle": r.get("subtitle", ""),
        "condition_text": r.get("condition_text_effective", r.get("condition_text_raw", "")),
        "source_page": source_page,
        "condition_summary": "",
        "condition_groups": cgs,
        "aadrg_mappings": aadrg_mappings_v1,
        "condition_expression": r.get("condition_expression", {}),
        "abc_basis": "[별표 1] 상급종합병원 지정·평가 규정 동일 AADRG 코드 확인",
    }


def _abc_status_v2_to_v1(v2_status: str) -> str:
    return {
        "OFFICIAL_PDF_EXACT_CODE": "V46_OFFICIAL_SAME_CODE_COMPATIBLE",
        "NOT_LISTED_IN_OFFICIAL_PDF": "NOT_LISTED",
        "V47_CLASSIFICATION_UNRESOLVED": "UNRESOLVED",
        "MERGED_FROM_MULTIPLE_PREDECESSORS": "MERGED",
        "PROVISIONAL_INTERNAL_ONLY": "PROVISIONAL",
    }.get(v2_status, v2_status)


# ---------------------------------------------------------------------------
# 편의 함수
# ---------------------------------------------------------------------------
def load_via_data_store(v2_path: Path):
    """v2 → v1 dict → KDRGDataStore 로드 (검증 전용)."""
    import io
    import sys
    import json

    v1_dict = load_v2_as_v1_dict(v2_path)
    sys.path.insert(0, str(v2_path.parent.parent))
    from app.data_store import KDRGDataStore

    tmp = io.BytesIO(json.dumps(v1_dict, ensure_ascii=False).encode("utf-8"))
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w", encoding="utf-8") as f:
        json.dump(v1_dict, f, ensure_ascii=False)
        tmp_path = f.name
    try:
        ds = KDRGDataStore(data_path=tmp_path)
    finally:
        os.unlink(tmp_path)
    return ds
