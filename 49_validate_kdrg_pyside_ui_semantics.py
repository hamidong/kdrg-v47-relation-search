#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KDRG V4.7 Stage 49 PySide UI 의미 최소수정 독립검증."""
from __future__ import annotations

import hashlib
import json
import py_compile
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

SCRIPT_VERSION = "2026-07-27_KDRG_V47_PYSIDE_UI_SEMANTICS_VALIDATOR_V1"
ROOT = Path(__file__).resolve().parent
REPORT_DIR = ROOT / "reports"
REPORT_TXT = REPORT_DIR / "pyside_ui_semantics_validation_report.txt"
REPORT_JSON = REPORT_DIR / "pyside_ui_semantics_validation_report.json"

EXPECTED_HASHES = {
    "data/kdrg_v47_search_integrated.json": "3de5d6d95cd9cbd16e674f5a4cffcd8bf89da2ee70627501f56d81b05bbe8af1",
    "app/kdrg_search_service.py": "35766cfd10b887c9852536a2165d6719e20c5ad2791a5d1a0d0166d7b94cb6cd",
    "app/runtime_data_store.py": "e2d5bf1de4c9697f84e30f9e8ec9664abf9cda0acddb392620c3a7b71f28d48d",
    "app/main_window.py": "291b4f76d389b24695ebe2b180b1cd4a729a8978af758dd279656c67ac5df242",
    "tests/windows_runtime_source_smoke.py": "5fc535d44956e4e5efef3e4356c5f8629954b5a9e60bf6d912987257629fc907",
}


def configure_utf8_stdio() -> None:
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="backslashreplace")
            except Exception:
                pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON root must be object: {path}")
    return value


def add(results: list[dict[str, Any]], name: str, passed: bool, actual: Any, expected: Any) -> None:
    results.append({"name": name, "passed": bool(passed), "actual": actual, "expected": expected})


def flatten_service_context(service: Any) -> dict[tuple[str, str, str], dict[str, Any]]:
    output: dict[tuple[str, str, str], dict[str, Any]] = {}
    for (adrg, table_id), values in service._semantic_context_index.items():
        for item in values:
            key = (str(adrg), str(table_id), str(item.get("node_id") or ""))
            if key in output:
                raise RuntimeError(f"duplicate service context key: {key}")
            output[key] = item
    return output


def main() -> int:
    configure_utf8_stdio()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []

    required = [
        *EXPECTED_HASHES,
        "data/kdrg_v47_ui_semantic_profile.json",
        "data/kdrg_v47_ui_display_contract.json",
        "app/models.py",
        "app/styles.py",
        "version.py",
    ]
    for rel in required:
        add(results, f"필수 파일 {rel}", (ROOT / rel).is_file(), str(ROOT / rel), "exists")
    if any(not row["passed"] for row in results):
        return finish(results)

    for rel, expected in EXPECTED_HASHES.items():
        actual = sha256(ROOT / rel)
        add(results, f"SHA256 {rel}", actual == expected, actual, expected)

    for rel in [
        "app/kdrg_search_service.py",
        "app/runtime_data_store.py",
        "app/main_window.py",
        "tests/windows_runtime_source_smoke.py",
    ]:
        try:
            py_compile.compile(str(ROOT / rel), doraise=True)
            add(results, f"py_compile {rel}", True, "PASS", "PASS")
        except Exception as exc:
            add(results, f"py_compile {rel}", False, f"{type(exc).__name__}: {exc}", "PASS")

    integrated = load_json(ROOT / "data/kdrg_v47_search_integrated.json")
    profile = load_json(ROOT / "data/kdrg_v47_ui_semantic_profile.json")
    contract = load_json(ROOT / "data/kdrg_v47_ui_display_contract.json")
    add(results, "통합 JSON schema", integrated.get("meta", {}).get("schema_version") == "kdrg-v47-search-integrated-v2", integrated.get("meta", {}).get("schema_version"), "kdrg-v47-search-integrated-v2")
    add(results, "semantic profile schema", profile.get("meta", {}).get("schema_version") == "kdrg-v47-ui-semantic-profile-v1", profile.get("meta", {}).get("schema_version"), "kdrg-v47-ui-semantic-profile-v1")
    add(results, "display contract schema", contract.get("meta", {}).get("schema_version") == "kdrg-v47-ui-display-contract-v1", contract.get("meta", {}).get("schema_version"), "kdrg-v47-ui-display-contract-v1")
    add(results, "contract source hash", contract.get("meta", {}).get("source_sha256") == EXPECTED_HASHES["data/kdrg_v47_search_integrated.json"], contract.get("meta", {}).get("source_sha256"), EXPECTED_HASHES["data/kdrg_v47_search_integrated.json"])

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from app.kdrg_search_service import KdrgSearchService
    from app.runtime_data_store import KDRGRuntimeDataStore

    service = KdrgSearchService()
    store = KDRGRuntimeDataStore()
    counts = dict(service.status().get("counts") or {})
    expected_counts = {
        "adrg_records": 1132,
        "aadrg_records": 1233,
        "rdrg_records": 2699,
        "logical_table_records": 1308,
        "unique_search_codes": 16571,
    }
    for key, expected in expected_counts.items():
        actual = int(counts.get(key, -1))
        add(results, f"runtime count {key}", actual == expected, actual, expected)
    add(results, "runtime rules", len(store.rules) == 1132, len(store.rules), 1132)
    add(results, "runtime tables", len(store.tables) == 1308, len(store.tables), 1308)
    add(results, "runtime codes", len(store.code_to_tables) == 16571, len(store.code_to_tables), 16571)

    semantic_counts = dict(service.status().get("semantic_context_counts") or {})
    expected_semantic = {
        "relationship_occurrence_count": 939,
        "include_occurrence": 874,
        "exclude_occurrence": 65,
        "exclusion_base_occurrence": 28,
        "exclusion_excluded_occurrence": 65,
        "exclusion_excluded_final_include": 19,
        "legacy_misclassification_occurrence": 47,
    }
    for key, expected in expected_semantic.items():
        actual = int(semantic_counts.get(key, -1))
        add(results, f"polarity count {key}", actual == expected, actual, expected)

    service_context = flatten_service_context(service)
    contract_rows = contract.get("condition_table_occurrence_registry") or []
    add(results, "contract occurrence count", len(contract_rows) == 939, len(contract_rows), 939)
    mismatches: list[dict[str, Any]] = []
    for row in contract_rows:
        key = (str(row.get("adrg") or ""), str(row.get("logical_table_id") or ""), str(row.get("node_id") or ""))
        actual = service_context.get(key)
        expected_role = str(row.get("display_role") or "")
        expected_sign = int(row.get("polarity_sign") or 0)
        if actual is None or actual.get("display_role") != expected_role or int(actual.get("polarity_sign") or 0) != expected_sign:
            mismatches.append({"key": key, "actual": actual, "expected_role": expected_role, "expected_sign": expected_sign})
    add(results, "939건 service-contract polarity 일치", not mismatches, mismatches[:10], [])
    add(results, "service context key count", len(service_context) == 939, len(service_context), 939)

    contract_table = {str(row.get("logical_table_id") or ""): row for row in contract.get("table_display_registry") or []}
    category_mismatches = []
    code_type_map = {
        "diagnosis": "상병코드",
        "procedure": "수술·처치코드",
        "add_on_code": "부가코드",
        "optional_semantic": "선택 조건 코드",
        "other_semantic": "기타 조건 코드",
        "unknown": "코드(유형 미확정)",
    }
    for table_id, table_def in store.tables.items():
        expected_category = str((contract_table.get(table_id) or {}).get("category") or "")
        actual_category = store.table_category(table_id)
        expected_type = code_type_map.get(expected_category, "코드(유형 미확정)")
        if actual_category != expected_category or table_def.code_type != expected_type:
            category_mismatches.append({"table_id": table_id, "actual_category": actual_category, "expected_category": expected_category, "actual_type": table_def.code_type, "expected_type": expected_type})
    add(results, "1,308 TABLE category 계약 일치", not category_mismatches, category_mismatches[:10], [])
    category_counts = Counter(store.table_category(table_id) for table_id in store.tables)
    add(results, "TABLE category counts", dict(sorted(category_counts.items())) == contract.get("contract_counts", {}).get("table_category_counts"), dict(sorted(category_counts.items())), contract.get("contract_counts", {}).get("table_category_counts"))
    unknown_as_procedure = [table_id for table_id in store.tables if store.table_category(table_id) == "unknown" and store.tables[table_id].code_type == "수술·처치코드"]
    add(results, "unknown TABLE procedure 기본분류 제거", not unknown_as_procedure, unknown_as_procedure[:10], [])

    all_name_empty = all(not member.name_ko and not member.name_en for table in store.tables.values() for member in table.members)
    add(results, "코드명 미수록 상태 보존", all_name_empty, all_name_empty, True)

    adrg_contract = {str(row.get("adrg") or ""): row for row in contract.get("adrg_display_registry") or []}
    coverage_mismatches = []
    for adrg in store.rules:
        actual = store.condition_coverage_for_adrg(adrg)
        expected = adrg_contract.get(adrg) or {}
        keys = ("coverage_state", "summary_copy")
        if any(actual.get(key) != expected.get(key) for key in keys) or actual.get("basic_table_ids") != expected.get("source_logical_table_ids"):
            coverage_mismatches.append({"adrg": adrg, "actual": actual, "expected": expected})
    add(results, "1,132 ADRG coverage 계약 일치", not coverage_mismatches, coverage_mismatches[:10], [])

    e011 = store.rules["E011"]
    e011_positive = [component.table_id for group in e011.condition_groups for component in group.components]
    e011_negative = [component.table_id for group in e011.condition_groups for component in group.exclude_components]
    add(results, "E011 base include", "LT_E011_002" in e011_positive and "LT_E011_002" not in e011_negative, {"positive": e011_positive, "negative": e011_negative}, "LT_E011_002 include only")
    add(results, "E011 excluded", e011_negative == ["LT_E011_003"], e011_negative, ["LT_E011_003"])

    coverage_9610 = store.condition_coverage_for_adrg("9610")
    add(results, "9610 basic TABLE", coverage_9610.get("basic_table_ids") == ["LT_9610_001"], coverage_9610.get("basic_table_ids"), ["LT_9610_001"])
    add(results, "9610 no extra condition", not coverage_9610.get("has_condition_ast") and not store.rules["9610"].condition_groups, {"coverage": coverage_9610, "groups": store.rules["9610"].condition_groups}, "no AST / no fake group")
    add(results, "9610 neutral TABLE", store.table_category("LT_9610_001") == "unknown" and store.tables["LT_9610_001"].code_type == "코드(유형 미확정)", (store.table_category("LT_9610_001"), store.tables["LT_9610_001"].code_type), ("unknown", "코드(유형 미확정)"))

    rule_9620 = store.rules["9620"]
    positive_9620 = [component.table_id for group in rule_9620.condition_groups for component in group.components]
    negative_9620 = [component.table_id for group in rule_9620.condition_groups for component in group.exclude_components]
    add(results, "9620 base/excluded", positive_9620 == ["LT_9620_001"] and negative_9620 == ["LT_9620_002"], {"positive": positive_9620, "negative": negative_9620}, {"positive": ["LT_9620_001"], "negative": ["LT_9620_002"]})
    add(results, "9620 type labels", (store.tables["LT_9620_001"].code_type, store.tables["LT_9620_002"].code_type) == ("상병코드", "수술·처치코드"), (store.tables["LT_9620_001"].code_type, store.tables["LT_9620_002"].code_type), ("상병코드", "수술·처치코드"))

    for query, category, expected_key in [
        ("E011", "ADRG", "E011"),
        ("A01.0", "상병코드", "A010"),
        ("LT_9610_001", "TABLE", "LT_9610_001"),
        ("9610", "ADRG", "9610"),
        ("9620", "ADRG", "9620"),
    ]:
        rows = store.search(query, category)
        keys = [str(row.key) for row in rows[:20]]
        add(results, f"검색 fixture {query}", expected_key in keys, keys, f"contains {expected_key}")

    search_text = (ROOT / "app/kdrg_search_service.py").read_text(encoding="utf-8")
    store_text = (ROOT / "app/runtime_data_store.py").read_text(encoding="utf-8")
    ui_text = (ROOT / "app/main_window.py").read_text(encoding="utf-8")
    smoke_text = (ROOT / "tests/windows_runtime_source_smoke.py").read_text(encoding="utf-8")
    source_rules = {
        "polarity traversal": 'elif node_type == "EXCLUSION"' in search_text and 'walk(children[0], polarity' in search_text and 'walk(children[1], -polarity' in search_text,
        "ancestor collapse removed": 'elif "NOT" in ancestor_types or "EXCLUSION" in ancestor_types' not in search_text,
        "unknown neutral": 'return "코드(유형 미확정)"' in store_text,
        "fake AST copy removed": '본문 조건 AST 없음' not in store_text,
        "dynamic columns": 'self._columns: List[Tuple[str, str]]' in ui_text and 'self.table.setColumnCount(len(self._columns))' in ui_text,
        "single-column copy": '현재 통합 데이터에는 코드명이 수록되지 않아 코드 열만 표시합니다.' in ui_text,
        "basic/extra sections": 'QLabel("기본 분류 TABLE")' in ui_text and 'QLabel("추가 분기조건")' in ui_text,
        "exclusion copy": 'QLabel("단, 다음 대상은 제외")' in ui_text,
        "technical collapsed": 'technical_frame.setVisible(False)' in ui_text and 'technical_button.setText("기술식 보기")' in ui_text,
        "old three-column note removed": '코드·한글명·영문명 상세 코드표' not in ui_text,
        "Windows smoke V4": 'WINDOWS_RUNTIME_SOURCE_SMOKE_V4' in smoke_text,
        "Windows semantic checks": 'UI 의미 polarity' in smoke_text and 'UI 코드명 없는 TABLE 단일 열' in smoke_text,
    }
    for name, passed in source_rules.items():
        add(results, f"source rule {name}", passed, passed, True)

    return finish(results)


def finish(results: list[dict[str, Any]]) -> int:
    pass_count = sum(1 for row in results if row["passed"])
    failures = [row for row in results if not row["passed"]]
    payload = {"script_version": SCRIPT_VERSION, "pass": pass_count, "fail": len(failures), "total": len(results), "results": results}
    REPORT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "KDRG V4.7 Stage 49 PySide UI 의미 최소수정 독립검증",
        "=" * 78,
        f"스크립트 버전: {SCRIPT_VERSION}",
        "",
        "[검증 항목]",
    ]
    for row in results:
        status = "PASS" if row["passed"] else "FAIL"
        lines.append(f"- [{status}] {row['name']} | actual={row['actual']} | expected={row['expected']}")
    lines.extend(["", "[최종 결과]", f"PASS: {pass_count}", f"FAIL: {len(failures)}", f"TOTAL: {len(results)}", f"전체 결과: {'PASS' if not failures else 'FAIL'}"])
    REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if failures:
        print(f"[FAIL] KDRG Stage 49 PySide UI 의미검증: {pass_count} PASS / {len(failures)} FAIL")
        print("[FAIL 상세]")
        for row in failures:
            print(f"- {row['name']} | actual={row['actual']} | expected={row['expected']}")
        print(f"report={REPORT_TXT}")
        return 1
    print(f"[PASS] KDRG Stage 49 PySide UI 의미검증: {pass_count} PASS / 0 FAIL")
    print(f"report={REPORT_TXT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
