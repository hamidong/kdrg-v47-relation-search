# -*- coding: utf-8 -*-
"""v2 원천자료(sources) 무결성 검증.

- sources 배열에 선언된 source_id만 전체 JSON에서 사용되는지 확인
- evidence_type 허용 값 준수 여부 확인
- abc_classification의 source_id가 V47_ABC_PDF인지 확인 (파일럿 9개 ADRG 규칙)
- CORRECTION evidence_type이 있는 source_id가 CORRECTION 타입 원천자료인지 확인

실행
    python tests/test_schema_v2_source_integrity.py

종료코드
    0 = PASS, 1 = FAIL
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Set

for _s in ("stdout", "stderr"):
    _st = getattr(sys, _s, None)
    if _st is not None and hasattr(_st, "reconfigure"):
        try:
            _st.reconfigure(encoding="utf-8")
        except Exception:
            pass

ROOT = Path(__file__).resolve().parent.parent
V2_JSON = ROOT / "data" / "kdrg_v47_pilot_schema_v2.json"
REGISTRY_JSON = ROOT / "data" / "special_case_registry_v47_v2.json"
REPORT_PATH = ROOT / "reports" / "schema_v2_migration_report.txt"

ERRORS: list[str] = []
WARNINGS: list[str] = []
PASS_LIST: list[str] = []

ALLOWED_EVIDENCE_TYPES = {
    "RULE_TEXT", "TABLE_MEMBERSHIP", "CODE_NAME",
    "CORRECTION", "ABC_CLASSIFICATION", "CROSS_VALIDATION"
}

CORRECTION_SOURCE_TYPES = {"CORRECTION_HWPX"}


def fail(msg: str) -> None:
    ERRORS.append(f"[FAIL] {msg}")
    print(f"[FAIL] {msg}")


def warn(msg: str) -> None:
    WARNINGS.append(f"[WARN] {msg}")
    print(f"[WARN] {msg}")


def ok(msg: str) -> None:
    PASS_LIST.append(f"[PASS] {msg}")
    print(f"[PASS] {msg}")


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def iter_source_refs(obj):
    """obj 내 모든 source_ref dict를 재귀적으로 순회한다."""
    if isinstance(obj, dict):
        if "source_id" in obj and "evidence_type" in obj:
            yield obj
        else:
            for v in obj.values():
                yield from iter_source_refs(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from iter_source_refs(item)


# ---------------------------------------------------------------------------
# 검증 함수들
# ---------------------------------------------------------------------------
def check_declared_source_ids(v2):
    declared = {s["source_id"]: s for s in v2.get("sources", [])}
    ok(f"선언된 source_id {len(declared)}개: {sorted(declared)}")

    used: Set[str] = set()
    for ref in iter_source_refs({"tables": v2.get("tables", []), "rules": v2.get("rules", [])}):
        used.add(ref["source_id"])

    bad = used - set(declared)
    if bad:
        for b in sorted(bad):
            fail(f"미선언 source_id 사용: '{b}'")
    else:
        ok(f"모든 source_id 선언 확인 (사용={len(used)}개)")

    unused = set(declared) - used
    if unused:
        for u in sorted(unused):
            warn(f"선언되었으나 사용되지 않은 source_id: '{u}'")

    return declared


def check_evidence_types(v2):
    errors = 0
    for ref in iter_source_refs({"tables": v2.get("tables", []), "rules": v2.get("rules", [])}):
        et = ref.get("evidence_type", "")
        if et not in ALLOWED_EVIDENCE_TYPES:
            fail(f"허용되지 않은 evidence_type: '{et}' (source_id='{ref.get('source_id')}')")
            errors += 1
    if errors == 0:
        ok(f"모든 evidence_type 값 유효")


def check_correction_source_types(v2, declared: dict):
    """CORRECTION evidence_type을 사용하는 source_id가 실제 교정 원천자료인지 확인."""
    for ref in iter_source_refs({"tables": v2.get("tables", []), "rules": v2.get("rules", [])}):
        if ref.get("evidence_type") == "CORRECTION":
            sid = ref.get("source_id", "")
            src_type = declared.get(sid, {}).get("source_type", "")
            if src_type not in CORRECTION_SOURCE_TYPES:
                fail(f"CORRECTION evidence_type이지만 source_type={src_type}: '{sid}'")
    else:
        ok("CORRECTION evidence_type source_type 검증 통과")


def check_abc_classification_source(v2):
    """모든 abc_classification.source_id가 V47_ABC_PDF인지 확인."""
    errors = 0
    for r in v2.get("rules", []):
        adrg = r["adrg"]
        for am in r.get("aadrg_mappings", []):
            abc = am.get("abc_classification", {})
            sid = abc.get("source_id", "")
            if sid != "V47_ABC_PDF":
                fail(f"[{adrg} → {am['aadrg']}] abc_classification.source_id='{sid}' (기대: V47_ABC_PDF)")
                errors += 1
    if errors == 0:
        ok("모든 abc_classification.source_id = V47_ABC_PDF")


def check_main_pdf_rule_refs(v2):
    """각 rule의 source_refs에 V47_MAIN_PDF 항목이 있는지 확인."""
    for r in v2.get("rules", []):
        adrg = r["adrg"]
        src_ids = {ref.get("source_id") for ref in r.get("source_refs", [])}
        # F022는 교정 건이므로 CORR_HWPX 허용
        if "V47_MAIN_PDF" not in src_ids:
            warn(f"[{adrg}] rule.source_refs에 V47_MAIN_PDF 없음 (있는 것: {sorted(src_ids)})")
        else:
            ok(f"[{adrg}] rule.source_refs V47_MAIN_PDF 확인")


def check_sources_fields(v2):
    """sources 배열의 필수 필드 존재 확인."""
    required = {"source_id", "source_type", "file_name", "title", "effective_date", "authority", "usage_scope", "included_in_runtime"}
    errors = 0
    for s in v2.get("sources", []):
        missing = required - set(s.keys())
        if missing:
            fail(f"[sources/{s.get('source_id','?')}] 필수 필드 없음: {sorted(missing)}")
            errors += 1
    if errors == 0:
        ok(f"sources 배열 필수 필드 모두 존재 ({len(v2.get('sources', []))}개)")


def check_registry_adrg_coverage(v2):
    """special_case_registry의 ADRG가 v2 rules에 모두 존재하는지 확인."""
    if not REGISTRY_JSON.exists():
        warn(f"special_case_registry 파일 없음: {REGISTRY_JSON}")
        return
    registry = json.loads(REGISTRY_JSON.read_text(encoding="utf-8"))
    v2_adrgs = {r["adrg"] for r in v2.get("rules", [])}
    for sc in registry.get("special_cases", []):
        adrg = sc.get("adrg", "")
        if adrg not in v2_adrgs:
            fail(f"[registry/{adrg}] v2 rules에 해당 ADRG 없음")
        else:
            ok(f"[registry/{adrg}] v2 rules 존재 확인")
    for st in registry.get("shared_tables", []):
        tid = st.get("table_id", "")
        v2_tids = {t["table_id"] for t in v2.get("tables", [])}
        if tid not in v2_tids:
            fail(f"[registry/shared_tables/{tid}] v2 tables에 없음")
        else:
            ok(f"[registry/shared_tables/{tid}] v2 tables 존재 확인")


# ---------------------------------------------------------------------------
# 보고서
# ---------------------------------------------------------------------------
def write_report():
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "=== KDRG V4.7 Schema v2 원천자료 무결성 + 마이그레이션 보고서 ===",
        f"검증 파일: {V2_JSON.name}",
        f"레지스트리: {REGISTRY_JSON.name}",
        "",
        f"PASS: {len(PASS_LIST)}건",
        f"WARN: {len(WARNINGS)}건",
        f"FAIL: {len(ERRORS)}건",
        "",
    ]
    if ERRORS:
        lines += ["--- FAIL 목록 ---"] + ERRORS + [""]
    if WARNINGS:
        lines += ["--- WARN 목록 ---"] + WARNINGS + [""]
    lines += ["--- PASS 목록 ---"] + PASS_LIST
    overall = "PASS" if not ERRORS else "FAIL"
    lines += ["", f"최종 결과: {overall}"]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n보고서 저장: {REPORT_PATH}")
    return overall


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    print("=== Schema v2 원천자료 무결성 검증 시작 ===\n")
    if not V2_JSON.exists():
        fail(f"v2 JSON 파일 없음: {V2_JSON}")
        write_report()
        sys.exit(1)
    v2 = json.loads(V2_JSON.read_text(encoding="utf-8"))

    check_sources_fields(v2)
    declared = check_declared_source_ids(v2)
    check_evidence_types(v2)
    check_correction_source_types(v2, declared)
    check_abc_classification_source(v2)
    check_main_pdf_rule_refs(v2)
    check_registry_adrg_coverage(v2)

    overall = write_report()
    print(f"\n결과: PASS {len(PASS_LIST)}건 / WARN {len(WARNINGS)}건 / FAIL {len(ERRORS)}건")
    sys.exit(0 if overall == "PASS" else 1)


if __name__ == "__main__":
    main()
