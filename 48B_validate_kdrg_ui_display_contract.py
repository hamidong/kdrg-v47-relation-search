#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KDRG V4.7 공통 UI 표현 계약 독립검증기."""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_VERSION = "2026-07-27_KDRG_V47_UI_DISPLAY_CONTRACT_VALIDATOR_V1"
SOURCE_SCHEMA = "kdrg-v47-search-integrated-v2"
PROFILE_SCHEMA = "kdrg-v47-ui-semantic-profile-v1"
CONTRACT_SCHEMA = "kdrg-v47-ui-display-contract-v1"
EXPECTED_SOURCE_SHA256 = "3de5d6d95cd9cbd16e674f5a4cffcd8bf89da2ee70627501f56d81b05bbe8af1"

ROOT = Path(__file__).resolve().parent
SOURCE_PATH = ROOT / "data" / "kdrg_v47_search_integrated.json"
PROFILE_PATH = ROOT / "data" / "kdrg_v47_ui_semantic_profile.json"
CONTRACT_PATH = ROOT / "data" / "kdrg_v47_ui_display_contract.json"
REPORT_JSON_PATH = ROOT / "reports" / "ui_display_contract_validation_report.json"
REPORT_TXT_PATH = ROOT / "reports" / "ui_display_contract_validation_report.txt"
PROTECTED_FILES = [
    "data/kdrg_v47_search_integrated.json",
    "app/kdrg_search_service.py",
    "app/runtime_data_store.py",
    "app/main_window.py",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON root must be object: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def independent_coverage_state(source_ids: list[str], ast: dict[str, Any] | None) -> str:
    if ast is None:
        return "BASIC_TABLE_NO_EXTRA_CONDITION" if source_ids else "NO_BASIC_TABLE_NO_EXTRA_CONDITION"
    has_table = any(node.get("logical_table_ids") for node in ast.get("nodes") or [])
    if not has_table:
        return "EXTRA_CONDITION_NO_TABLE_REF"
    return "BASIC_TABLE_AND_EXTRA_CONDITION_TABLES" if source_ids else "EXTRA_CONDITION_TABLES_NO_BASIC_TABLE"


def recompute_occurrence_roles(integrated: dict[str, Any]) -> list[tuple[str, str, str, str, bool, bool]]:
    output: list[tuple[str, str, str, str, bool, bool]] = []
    for ast in integrated.get("condition_ast_records") or []:
        nodes = {str(node.get("node_id") or ""): node for node in ast.get("nodes") or []}
        visited: set[str] = set()

        def walk(node_id: str, sign: int, path: tuple[tuple[str, str], ...]) -> None:
            if node_id in visited:
                raise RuntimeError(f"duplicate AST traversal: {ast.get('condition_ast_id')} / {node_id}")
            visited.add(node_id)
            node = nodes[node_id]
            for table_id in node.get("logical_table_ids") or []:
                in_base = ("EXCLUSION", "base") in path
                in_excluded = ("EXCLUSION", "excluded") in path
                output.append((
                    str(ast.get("adrg") or ""),
                    node_id,
                    str(table_id),
                    "INCLUDE" if sign > 0 else "EXCLUDE",
                    in_base,
                    in_excluded,
                ))
            node_type = str(node.get("node_type") or "")
            children = [str(x) for x in node.get("child_node_ids") or []]
            if node_type == "NOT":
                for child in children:
                    walk(child, -sign, path + (("NOT", "negated"),))
            elif node_type == "EXCLUSION":
                if len(children) != 2:
                    raise RuntimeError(f"non-binary EXCLUSION: {ast.get('condition_ast_id')} / {node_id}")
                walk(children[0], sign, path + (("EXCLUSION", "base"),))
                walk(children[1], -sign, path + (("EXCLUSION", "excluded"),))
            else:
                for child in children:
                    walk(child, sign, path + ((node_type, "inherit"),))

        root = str(ast.get("root_node_id") or "")
        if root not in nodes:
            raise RuntimeError(f"missing root: {ast.get('condition_ast_id')} / {root}")
        walk(root, 1, tuple())
        if visited != set(nodes):
            raise RuntimeError(f"unreachable AST nodes: {ast.get('condition_ast_id')}")
    output.sort()
    return output


def main() -> int:
    checks: list[dict[str, Any]] = []

    def check(name: str, actual: Any, expected: Any) -> None:
        checks.append({"name": name, "actual": actual, "expected": expected, "passed": actual == expected})

    for path in [SOURCE_PATH, PROFILE_PATH, CONTRACT_PATH, *(ROOT / rel for rel in PROTECTED_FILES)]:
        check(f"필수 파일 {path.relative_to(ROOT)}", path.exists(), True)

    if any(not item["passed"] for item in checks):
        raise RuntimeError("필수 파일 누락")

    integrated = load_json(SOURCE_PATH)
    profile = load_json(PROFILE_PATH)
    contract = load_json(CONTRACT_PATH)

    check("통합 JSON schema", integrated.get("meta", {}).get("schema_version"), SOURCE_SCHEMA)
    check("profile schema", profile.get("meta", {}).get("schema_version"), PROFILE_SCHEMA)
    check("contract schema", contract.get("meta", {}).get("schema_version"), CONTRACT_SCHEMA)
    check("통합 JSON SHA256", sha256_file(SOURCE_PATH), EXPECTED_SOURCE_SHA256)
    check("contract source SHA256", contract.get("meta", {}).get("source_sha256"), sha256_file(SOURCE_PATH))
    check("contract profile SHA256", contract.get("meta", {}).get("semantic_profile_sha256"), sha256_file(PROFILE_PATH))
    check("contract read only", contract.get("meta", {}).get("read_only_contract_build"), True)
    check("target PySide", "PySide6" in (contract.get("meta", {}).get("target_runtimes") or []), True)
    check("target Electron", "Electron" in (contract.get("meta", {}).get("target_runtimes") or []), True)

    source_counts = integrated["meta"]["counts"]
    contract_counts = contract["contract_counts"]
    adrg_registry = contract["adrg_display_registry"]
    table_registry = contract["table_display_registry"]
    occurrence_registry = contract["condition_table_occurrence_registry"]

    check("ADRG registry length", len(adrg_registry), source_counts["adrg_records"])
    check("TABLE registry length", len(table_registry), source_counts["logical_table_records"])
    check("occurrence registry length", len(occurrence_registry), 939)
    check("ADRG registry unique", len({row["adrg"] for row in adrg_registry}), len(adrg_registry))
    check("TABLE registry unique", len({row["logical_table_id"] for row in table_registry}), len(table_registry))
    check("occurrence key unique", len({(row["adrg"], row["node_id"], row["logical_table_id"]) for row in occurrence_registry}), len(occurrence_registry))

    adrg_source = {str(row.get("adrg") or ""): row for row in integrated.get("adrg_records") or []}
    ast_by_id = {str(row.get("condition_ast_id") or ""): row for row in integrated.get("condition_ast_records") or []}
    registry_by_adrg = {row["adrg"]: row for row in adrg_registry}
    independent_coverage = Counter()
    coverage_mismatches: list[str] = []
    for code, source_row in adrg_source.items():
        ast_id = str(source_row.get("condition_ast_id") or "")
        state = independent_coverage_state(list(source_row.get("source_logical_table_ids") or []), ast_by_id.get(ast_id) if ast_id else None)
        independent_coverage[state] += 1
        if registry_by_adrg[code]["coverage_state"] != state:
            coverage_mismatches.append(code)
    check("coverage state mismatches", coverage_mismatches, [])
    check("coverage counts recompute", dict(sorted(independent_coverage.items())), contract_counts["adrg_coverage_state_counts"])

    independent_roles = recompute_occurrence_roles(integrated)
    contract_roles = sorted((
        row["adrg"], row["node_id"], row["logical_table_id"], row["display_role"],
        bool(row["inside_exclusion_base"]), bool(row["inside_exclusion_excluded"])
    ) for row in occurrence_registry)
    check("occurrence polarity independent recompute", contract_roles, independent_roles)

    role_counts = Counter(row["display_role"] for row in occurrence_registry)
    check("include count", role_counts["INCLUDE"], 874)
    check("exclude count", role_counts["EXCLUDE"], 65)
    check("contract include count", contract_counts["condition_table_include_occurrences"], 874)
    check("contract exclude count", contract_counts["condition_table_exclude_occurrences"], 65)

    base_rows = [row for row in occurrence_registry if row["inside_exclusion_base"]]
    excluded_rows = [row for row in occurrence_registry if row["inside_exclusion_excluded"]]
    check("EXCLUSION base count", len(base_rows), 28)
    check("EXCLUSION base all include", Counter(row["display_role"] for row in base_rows), Counter({"INCLUDE": 28}))
    check("EXCLUSION excluded count", len(excluded_rows), 65)
    check("EXCLUSION excluded role distribution", Counter(row["display_role"] for row in excluded_rows), Counter({"EXCLUDE": 46, "INCLUDE": 19}))
    check("double negative count", contract_counts["exclusion_excluded_final_include_occurrences"], 19)
    check("legacy generalized mismatch count", contract_counts["legacy_ancestor_collapse_misclassification_occurrences"], 47)

    category_counts = Counter(row["category"] for row in table_registry)
    check("TABLE category counts", dict(sorted(category_counts.items())), contract_counts["table_category_counts"])
    check("diagnosis count", category_counts["diagnosis"], 186)
    check("procedure count", category_counts["procedure"], 369)
    check("add on count", category_counts["add_on_code"], 99)
    check("optional semantic count", category_counts["optional_semantic"], 4)
    check("other semantic count", category_counts["other_semantic"], 4)
    check("unknown count", category_counts["unknown"], 646)
    check("all current TABLE code-only", sum(len(row["visible_columns"]) == 1 for row in table_registry), 1308)
    check("all current TABLE code first", all(row["visible_columns"][0]["key"] == "code" for row in table_registry), True)
    check("unknown neutral label", all(row["category_label"] == "코드 TABLE(유형 미확정)" for row in table_registry if row["category"] == "unknown"), True)
    check("unknown not procedure", contract["table_display_contract"]["must_not_classify_unknown_as_procedure"], True)
    check("name inference forbidden", all(row["must_not_infer_names"] for row in table_registry), True)

    rules = contract["condition_display_contract"]
    check("EXCLUSION binary base index", rules["operator_rules"]["EXCLUSION"]["base_child_index"], 0)
    check("EXCLUSION binary excluded index", rules["operator_rules"]["EXCLUSION"]["excluded_child_index"], 1)
    check("EXCLUSION no flatten", rules["operator_rules"]["EXCLUSION"]["must_not_flatten_descendants_as_negative"], True)
    check("NOT invert", rules["operator_rules"]["NOT"]["child_polarity"], "invert")
    check("technical expression collapsed", rules["extra_condition_section"]["technical_expression_default"], "collapsed")
    check("basic and AST separate", rules["source_table_section"]["must_be_separate_from_ast"], True)

    reps = contract["representative_models"]
    e011_roles = {(r["logical_table_id"], r["display_role"]) for r in reps["E011"]["condition_table_occurrences"]}
    check("E011 base", ("LT_E011_002", "INCLUDE") in e011_roles, True)
    check("E011 excluded", ("LT_E011_003", "EXCLUDE") in e011_roles, True)
    check("9610 state", reps["9610"]["adrg_display"]["coverage_state"], "BASIC_TABLE_NO_EXTRA_CONDITION")
    check("9610 copy", reps["9610"]["adrg_display"]["summary_copy"], "기본 분류 TABLE 있음 · 별도의 추가 분기조건 없음")
    roles_9620 = {(r["logical_table_id"], r["display_role"], r["table_category"]) for r in reps["9620"]["condition_table_occurrences"]}
    check("9620 diagnosis base", ("LT_9620_001", "INCLUDE", "diagnosis") in roles_9620, True)
    check("9620 procedure excluded", ("LT_9620_002", "EXCLUDE", "procedure") in roles_9620, True)

    qualifier_counts = Counter(row["occurrence_qualifier"] for row in occurrence_registry)
    check("direct TABLE qualifier", qualifier_counts["DIRECT_TABLE_MEMBERSHIP"], 897)
    check("required optional semantic qualifier", qualifier_counts["REQUIRED_TABLE"], 7)
    check("optional companion qualifier", qualifier_counts["OPTIONAL_COMPANION_TABLE"], 7)
    check("procedure count qualifier", qualifier_counts["PROCEDURE_COUNT_TABLE"], 6)
    check("major problem qualifier", qualifier_counts["MAJOR_PROBLEM_TABLE"], 19)
    check("qualified condition qualifier", qualifier_counts["QUALIFIED_TABLE_CONDITION_TEXT"], 2)
    check("qualified exclusion qualifier", qualifier_counts["QUALIFIED_TABLE_EXCLUSION_TEXT"], 1)

    for rel in PROTECTED_FILES:
        check(f"보호 파일 hash 계약 일치 {rel}", contract["input_hashes"].get(rel), sha256_file(ROOT / rel))
    check("통합 JSON 보호 해시", sha256_file(SOURCE_PATH), EXPECTED_SOURCE_SHA256)

    check("implementation stage 49 items", len(contract["implementation_gate"]["stage_49_pyside_minimum_fix"]), 5)
    check("Electron gate", contract["implementation_gate"]["stage_50_electron_start_condition"], "49번 PySide 의미 수정과 독립 회귀검증 PASS / 0 FAIL")

    passed = sum(1 for item in checks if item["passed"])
    failed_items = [item for item in checks if not item["passed"]]
    failed = len(failed_items)
    report = {
        "meta": {"script_version": SCRIPT_VERSION, "generated_at": datetime.now(timezone.utc).isoformat()},
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "checks": checks,
        "result": {"pass": passed, "fail": failed, "total": len(checks), "status": "PASS" if failed == 0 else "FAIL"},
    }
    write_json(REPORT_JSON_PATH, report)

    lines = [
        "KDRG V4.7 공통 UI 표현 계약 독립검증",
        "=" * 78,
        f"스크립트 버전: {SCRIPT_VERSION}",
        f"contract SHA256: {sha256_file(CONTRACT_PATH)}",
        "",
        "[검증 항목]",
    ]
    for item in checks:
        status = "PASS" if item["passed"] else "FAIL"
        actual = item["actual"]
        if isinstance(actual, list) and len(actual) > 20:
            actual = f"list[{len(actual)}]"
        lines.append(f"- [{status}] {item['name']} | actual={actual} | expected={item['expected']}")
    lines += [
        "",
        "[최종 결과]",
        f"PASS: {passed}",
        f"FAIL: {failed}",
        f"TOTAL: {len(checks)}",
        f"전체 결과: {'PASS' if failed == 0 else 'FAIL'}",
    ]
    write_text(REPORT_TXT_PATH, "\n".join(lines) + "\n")

    if failed_items:
        print(f"[FAIL] KDRG 공통 UI 표현 계약 독립검증: {passed} PASS / {failed} FAIL", file=sys.stderr)
        for item in failed_items:
            print(f"- {item['name']}: actual={item['actual']!r}, expected={item['expected']!r}", file=sys.stderr)
        print(f"report={REPORT_TXT_PATH}", file=sys.stderr)
        return 1

    print(f"[PASS] KDRG 공통 UI 표현 계약 독립검증: {passed} PASS / 0 FAIL")
    print(f"report={REPORT_TXT_PATH}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[FAIL] KDRG 공통 UI 표현 계약 독립검증 예외: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
