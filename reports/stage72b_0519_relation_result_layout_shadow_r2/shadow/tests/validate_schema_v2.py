# -*- coding: utf-8 -*-
"""v2 JSON 파일의 JSON Schema 구조적 유효성 검증.

실행
    python tests/validate_schema_v2.py

종료코드
    0 = PASS, 1 = FAIL
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

for _s in ("stdout", "stderr"):
    _st = getattr(sys, _s, None)
    if _st is not None and hasattr(_st, "reconfigure"):
        try:
            _st.reconfigure(encoding="utf-8")
        except Exception:
            pass

try:
    import jsonschema
    from jsonschema import Draft202012Validator, ValidationError
except ImportError:
    print("[ERROR] jsonschema 패키지 없음. pip install jsonschema", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
V2_JSON = ROOT / "data" / "kdrg_v47_pilot_schema_v2.json"
V2_SCHEMA = ROOT / "schemas" / "kdrg_relation_schema_v2.json"
COND_SCHEMA = ROOT / "schemas" / "condition_expression_schema_v2.json"
REPORT_PATH = ROOT / "reports" / "schema_v2_validation_report.txt"

ERRORS: list[str] = []
WARNINGS: list[str] = []
PASS_LIST: list[str] = []


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
# 1. 파일 로드
# ---------------------------------------------------------------------------
def load_files():
    for p in (V2_JSON, V2_SCHEMA, COND_SCHEMA):
        if not p.exists():
            fail(f"파일 없음: {p}")
            return None, None, None
    v2 = json.loads(V2_JSON.read_text(encoding="utf-8"))
    schema = json.loads(V2_SCHEMA.read_text(encoding="utf-8"))
    cond_schema = json.loads(COND_SCHEMA.read_text(encoding="utf-8"))
    ok("파일 로드 성공 (v2 JSON + 2개 스키마)")
    return v2, schema, cond_schema


# ---------------------------------------------------------------------------
# 2. 최상위 JSON Schema 검증
# ---------------------------------------------------------------------------
def validate_top_level(v2, schema):
    validator = Draft202012Validator(schema)
    errs = list(validator.iter_errors(v2))
    if errs:
        for e in errs:
            fail(f"최상위 스키마 위반: {e.json_path} → {e.message}")
    else:
        ok("최상위 JSON Schema 검증 통과")


# ---------------------------------------------------------------------------
# 3. condition_expression 각 노드 재귀 검증
# ---------------------------------------------------------------------------
def validate_expr_node(node: dict, cond_schema: dict, adrg: str, path: str) -> int:
    errors = 0
    validator = Draft202012Validator(cond_schema)
    errs = list(validator.iter_errors(node))
    if errs:
        for e in errs:
            fail(f"[{adrg}] condition_expression 스키마 위반 @ {path}: {e.message}")
        errors += len(errs)
    for child in node.get("children", []):
        cid = child.get("node_id", "?")
        errors += validate_expr_node(child, cond_schema, adrg, f"{path}/{cid}")
    return errors


def validate_condition_expressions(v2, cond_schema):
    total_errors = 0
    for r in v2.get("rules", []):
        adrg = r["adrg"]
        expr = r.get("condition_expression", {})
        if not expr:
            fail(f"[{adrg}] condition_expression 빈 객체")
            total_errors += 1
            continue
        if not expr.get("node_type"):
            fail(f"[{adrg}] condition_expression node_type 없음")
            total_errors += 1
            continue
        errs = validate_expr_node(expr, cond_schema, adrg, expr.get("node_id", "root"))
        if errs == 0:
            ok(f"[{adrg}] condition_expression 구조 검증 통과")
        total_errors += errs


# ---------------------------------------------------------------------------
# 4. source_id 일관성 검증
# ---------------------------------------------------------------------------
def validate_source_ids(v2):
    declared = {s["source_id"] for s in v2.get("sources", [])}
    ok(f"선언된 source_id: {len(declared)}개 — {sorted(declared)}")

    def refs_in(obj):
        if isinstance(obj, dict):
            if "source_id" in obj and "evidence_type" in obj:
                yield obj["source_id"]
            for v in obj.values():
                yield from refs_in(v)
        elif isinstance(obj, list):
            for item in obj:
                yield from refs_in(item)

    used = set(refs_in(v2.get("tables", []))) | set(refs_in(v2.get("rules", [])))
    bad = used - declared
    if bad:
        for b in sorted(bad):
            fail(f"미선언 source_id 사용: '{b}'")
    else:
        ok(f"source_id 일관성 검증 통과 (사용된 source_id {len(used)}개 모두 선언됨)")


# ---------------------------------------------------------------------------
# 5. member_count 정합성
# ---------------------------------------------------------------------------
def validate_member_counts(v2):
    errors = 0
    for t in v2.get("tables", []):
        declared = t.get("member_count", -1)
        actual = len(t.get("members", []))
        if declared != actual:
            fail(f"[{t['table_id']}] member_count={declared} ≠ 실제={actual}")
            errors += 1
    if errors == 0:
        ok(f"member_count 정합성 검증 통과 ({len(v2.get('tables', []))}개 테이블)")


# ---------------------------------------------------------------------------
# 6. abc_classification status 검증
# ---------------------------------------------------------------------------
def validate_abc_status(v2):
    allowed = {
        "OFFICIAL_PDF_EXACT_CODE",
        "NOT_LISTED_IN_OFFICIAL_PDF",
        "V47_CLASSIFICATION_UNRESOLVED",
        "MERGED_FROM_MULTIPLE_PREDECESSORS",
        "PROVISIONAL_INTERNAL_ONLY"
    }
    errors = 0
    for r in v2.get("rules", []):
        for am in r.get("aadrg_mappings", []):
            abc = am.get("abc_classification", {})
            status = abc.get("status", "")
            if status not in allowed:
                fail(f"[{r['adrg']} → {am['aadrg']}] 허용되지 않은 abc_classification.status: '{status}'")
                errors += 1
    if errors == 0:
        ok("abc_classification.status 값 검증 통과")


# ---------------------------------------------------------------------------
# 7. derived_indexes 간이 검증
# ---------------------------------------------------------------------------
def validate_derived_indexes(v2):
    idx = v2.get("derived_indexes", {})
    code_to_tid = idx.get("code_to_table_ids", {})
    table_to_adrg = idx.get("table_id_to_adrg_ids", {})
    if not code_to_tid:
        warn("derived_indexes.code_to_table_ids 비어 있음")
    else:
        ok(f"derived_indexes.code_to_table_ids 항목 수: {len(code_to_tid)}")
    if not table_to_adrg:
        warn("derived_indexes.table_id_to_adrg_ids 비어 있음")
    else:
        ok(f"derived_indexes.table_id_to_adrg_ids 항목 수: {len(table_to_adrg)}")


# ---------------------------------------------------------------------------
# 8. schema_version 확인
# ---------------------------------------------------------------------------
def validate_meta(v2):
    meta = v2.get("meta", {})
    if meta.get("schema_version") != "2":
        fail(f"meta.schema_version = '{meta.get('schema_version')}' (기대값: '2')")
    else:
        ok("meta.schema_version == '2'")


# ---------------------------------------------------------------------------
# 보고서 저장
# ---------------------------------------------------------------------------
def write_report():
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "=== KDRG V4.7 Schema v2 구조적 유효성 검증 보고서 ===",
        f"검증 파일: {V2_JSON.name}",
        f"검증 스키마: {V2_SCHEMA.name}, {COND_SCHEMA.name}",
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
    print("=== Schema v2 구조적 유효성 검증 시작 ===\n")
    v2, schema, cond_schema = load_files()
    if v2 is None:
        write_report()
        sys.exit(1)

    validate_meta(v2)
    validate_top_level(v2, schema)
    validate_condition_expressions(v2, cond_schema)
    validate_source_ids(v2)
    validate_member_counts(v2)
    validate_abc_status(v2)
    validate_derived_indexes(v2)

    overall = write_report()
    sys.exit(0 if overall == "PASS" else 1)


if __name__ == "__main__":
    main()
