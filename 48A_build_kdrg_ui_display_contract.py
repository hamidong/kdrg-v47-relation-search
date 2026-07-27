#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KDRG V4.7 공통 UI 표현 계약 생성기.

47번 전수감사 결과와 통합 검색 JSON을 읽어 PySide와 Electron이 공통으로
사용할 수 있는 기계 판독형 표현 계약을 생성한다. 원본 데이터와 앱 코드는
변경하지 않는다.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_VERSION = "2026-07-27_KDRG_V47_UI_DISPLAY_CONTRACT_BUILDER_V1"
SOURCE_SCHEMA = "kdrg-v47-search-integrated-v2"
PROFILE_SCHEMA = "kdrg-v47-ui-semantic-profile-v1"
OUTPUT_SCHEMA = "kdrg-v47-ui-display-contract-v1"
EXPECTED_SOURCE_SHA256 = "3de5d6d95cd9cbd16e674f5a4cffcd8bf89da2ee70627501f56d81b05bbe8af1"

ROOT = Path(__file__).resolve().parent
SOURCE_PATH = ROOT / "data" / "kdrg_v47_search_integrated.json"
PROFILE_PATH = ROOT / "data" / "kdrg_v47_ui_semantic_profile.json"
OUTPUT_PATH = ROOT / "data" / "kdrg_v47_ui_display_contract.json"
REPORT_JSON_PATH = ROOT / "reports" / "ui_display_contract_build_report.json"
REPORT_TXT_PATH = ROOT / "reports" / "ui_display_contract_build_report.txt"

PROTECTED_FILES = [
    "data/kdrg_v47_search_integrated.json",
    "app/kdrg_search_service.py",
    "app/runtime_data_store.py",
    "app/main_window.py",
]

CATEGORY_META: dict[str, dict[str, Any]] = {
    "diagnosis": {
        "label": "상병 TABLE",
        "code_label": "상병코드",
        "name_ko_label": "한글 진단명",
        "name_en_label": "영문 진단명",
    },
    "procedure": {
        "label": "수술·처치 TABLE",
        "code_label": "처치코드",
        "name_ko_label": "한글 처치명",
        "name_en_label": "영문 처치명",
    },
    "add_on_code": {
        "label": "부가코드 TABLE",
        "code_label": "부가코드",
        "name_ko_label": "코드명",
        "name_en_label": "영문 코드명",
    },
    "optional_semantic": {
        "label": "선택 조건 TABLE",
        "code_label": "코드",
        "name_ko_label": "한글명",
        "name_en_label": "영문명",
    },
    "other_semantic": {
        "label": "기타 조건 TABLE",
        "code_label": "코드",
        "name_ko_label": "한글명",
        "name_en_label": "영문명",
    },
    "unknown": {
        "label": "코드 TABLE(유형 미확정)",
        "code_label": "코드",
        "name_ko_label": "한글명",
        "name_en_label": "영문명",
    },
}

COVERAGE_META: dict[str, dict[str, str]] = {
    "BASIC_TABLE_NO_EXTRA_CONDITION": {
        "basic_table_label": "기본 분류 TABLE 있음",
        "extra_condition_label": "별도의 추가 분기조건 없음",
        "summary": "기본 분류 TABLE 있음 · 별도의 추가 분기조건 없음",
    },
    "NO_BASIC_TABLE_NO_EXTRA_CONDITION": {
        "basic_table_label": "본문 기본 TABLE 없음",
        "extra_condition_label": "별도의 추가 분기조건 없음",
        "summary": "본문 기본 TABLE 및 별도의 추가 분기조건 없음",
    },
    "EXTRA_CONDITION_NO_TABLE_REF": {
        "basic_table_label": "본문 기본 TABLE 없음",
        "extra_condition_label": "추가 임상·상태 조건 있음",
        "summary": "추가 임상·상태 조건 있음 · TABLE 참조 없음",
    },
    "EXTRA_CONDITION_TABLES_NO_BASIC_TABLE": {
        "basic_table_label": "본문 기본 TABLE 없음",
        "extra_condition_label": "TABLE을 사용하는 추가 분기조건 있음",
        "summary": "TABLE을 사용하는 추가 분기조건 있음",
    },
    "BASIC_TABLE_AND_EXTRA_CONDITION_TABLES": {
        "basic_table_label": "기본 분류 TABLE 있음",
        "extra_condition_label": "TABLE을 사용하는 추가 분기조건 있음",
        "summary": "기본 분류 TABLE 및 추가 분기조건 있음",
    },
}


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
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    temporary.replace(path)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def select_coverage_state(source_ids: list[str], ast: dict[str, Any] | None) -> str:
    if ast is None:
        return "BASIC_TABLE_NO_EXTRA_CONDITION" if source_ids else "NO_BASIC_TABLE_NO_EXTRA_CONDITION"
    ast_table_ids = {
        str(table_id)
        for node in ast.get("nodes") or []
        for table_id in node.get("logical_table_ids") or []
        if str(table_id)
    }
    if not ast_table_ids:
        return "EXTRA_CONDITION_NO_TABLE_REF"
    return "BASIC_TABLE_AND_EXTRA_CONDITION_TABLES" if source_ids else "EXTRA_CONDITION_TABLES_NO_BASIC_TABLE"


def visible_columns(profile: dict[str, Any]) -> list[dict[str, Any]]:
    category = str(profile.get("recommended_table_category") or "unknown")
    if category not in CATEGORY_META:
        category = "unknown"
    meta = CATEGORY_META[category]
    columns: list[dict[str, Any]] = [
        {"key": "code", "label": meta["code_label"], "source_field": "code", "required": True}
    ]
    if int(profile.get("korean_name_code_count") or 0) > 0:
        columns.append({"key": "name_ko", "label": meta["name_ko_label"], "source_field": "names", "required": False})
    if int(profile.get("non_korean_name_code_count") or 0) > 0:
        columns.append({"key": "name_en", "label": meta["name_en_label"], "source_field": "names", "required": False})
    return columns


def build_table_registry(
    integrated: dict[str, Any], profile: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    source_tables = {
        str(row.get("logical_table_id") or ""): row
        for row in integrated.get("logical_table_records") or []
    }
    profile_rows = profile.get("table_display_schema", {}).get("table_profiles") or []
    rows: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for item in sorted(profile_rows, key=lambda x: str(x.get("logical_table_id") or "")):
        table_id = str(item.get("logical_table_id") or "")
        source = source_tables.get(table_id)
        if source is None:
            raise RuntimeError(f"Profile TABLE missing in integrated data: {table_id}")
        category = str(item.get("recommended_table_category") or "unknown")
        if category not in CATEGORY_META:
            category = "unknown"
        columns = visible_columns(item)
        row = {
            "logical_table_id": table_id,
            "category": category,
            "category_label": CATEGORY_META[category]["label"],
            "category_evidence": "AST_ROLE_EVIDENCE" if item.get("ast_role_evidence") else "UNRESOLVED_NEUTRAL",
            "ast_role_evidence": list(item.get("ast_role_evidence") or []),
            "code_count": int(item.get("code_count") or 0),
            "name_data_status": "AVAILABLE" if len(columns) > 1 else "NOT_AVAILABLE_IN_INTEGRATED_JSON",
            "visible_columns": columns,
            "hidden_empty_columns": ["name_ko", "name_en"] if len(columns) == 1 else [],
            "table_note": (
                f"{CATEGORY_META[category]['code_label']} {int(item.get('code_count') or 0):,}건"
                if len(columns) == 1
                else f"원천에 존재하는 필드만 표시 · {int(item.get('code_count') or 0):,}건"
            ),
            "source_adrgs": list(source.get("source_adrgs") or []),
            "condition_adrgs": list(source.get("condition_adrgs") or []),
            "source_refs": list(source.get("source_refs") or []),
            "must_not_infer_names": True,
        }
        rows.append(row)
        by_id[table_id] = row
    return rows, by_id


def build_adrg_registry(integrated: dict[str, Any]) -> list[dict[str, Any]]:
    ast_by_id = {
        str(row.get("condition_ast_id") or ""): row
        for row in integrated.get("condition_ast_records") or []
    }
    rows: list[dict[str, Any]] = []
    for adrg in sorted(integrated.get("adrg_records") or [], key=lambda x: str(x.get("adrg") or "")):
        ast_id = str(adrg.get("condition_ast_id") or "")
        ast = ast_by_id.get(ast_id) if ast_id else None
        source_ids = [str(x) for x in adrg.get("source_logical_table_ids") or []]
        condition_ids = [str(x) for x in adrg.get("condition_logical_table_ids") or []]
        state = select_coverage_state(source_ids, ast)
        meta = COVERAGE_META[state]
        rows.append({
            "adrg": str(adrg.get("adrg") or ""),
            "adrg_name": str(adrg.get("adrg_name") or ""),
            "coverage_state": state,
            "basic_table_label": meta["basic_table_label"],
            "extra_condition_label": meta["extra_condition_label"],
            "summary_copy": meta["summary"],
            "source_logical_table_ids": source_ids,
            "condition_logical_table_ids": condition_ids,
            "condition_ast_id": ast_id or None,
            "technical_expression_available": bool(ast and ast.get("canonical_expression")),
            "technical_expression_default_visibility": "collapsed",
        })
    return rows


def table_occurrence_qualifier(node: dict[str, Any], table_index: int) -> str:
    node_type = str(node.get("node_type") or "")
    semantic_type = str(node.get("semantic_type") or "")
    if node_type == "TABLE_REF":
        return "DIRECT_TABLE_MEMBERSHIP"
    if semantic_type == "optional_table_presence":
        return "REQUIRED_TABLE" if table_index == 0 else "OPTIONAL_COMPANION_TABLE"
    if semantic_type == "procedure_count":
        return "PROCEDURE_COUNT_TABLE"
    if semantic_type == "major_problem":
        return "MAJOR_PROBLEM_TABLE"
    if semantic_type == "qualified_table_exclusion":
        return "QUALIFIED_TABLE_EXCLUSION_TEXT"
    if semantic_type == "qualified_table_condition":
        return "QUALIFIED_TABLE_CONDITION_TEXT"
    return "SEMANTIC_TEXT_TABLE"


def build_condition_occurrences(
    integrated: dict[str, Any], table_by_id: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ast in sorted(integrated.get("condition_ast_records") or [], key=lambda x: str(x.get("adrg") or "")):
        nodes = {str(node.get("node_id") or ""): node for node in ast.get("nodes") or []}
        root_id = str(ast.get("root_node_id") or "")
        if root_id not in nodes:
            raise RuntimeError(f"AST root missing: {ast.get('condition_ast_id')} / {root_id}")
        visited: set[str] = set()

        def walk(node_id: str, polarity: int, path: list[dict[str, Any]]) -> None:
            if node_id in visited:
                raise RuntimeError(f"AST graph cycle or duplicate traversal: {ast.get('condition_ast_id')} / {node_id}")
            visited.add(node_id)
            node = nodes[node_id]
            node_type = str(node.get("node_type") or "")
            table_ids = [str(x) for x in node.get("logical_table_ids") or [] if str(x)]
            for table_index, table_id in enumerate(table_ids):
                table_meta = table_by_id.get(table_id)
                if table_meta is None:
                    raise RuntimeError(f"AST TABLE missing in registry: {ast.get('adrg')} / {node_id} / {table_id}")
                exclusion_base_in_path = any(
                    segment.get("operator") == "EXCLUSION" and segment.get("branch") == "base"
                    for segment in path
                )
                exclusion_excluded_in_path = any(
                    segment.get("operator") == "EXCLUSION" and segment.get("branch") == "excluded"
                    for segment in path
                )
                rows.append({
                    "adrg": str(ast.get("adrg") or ""),
                    "condition_ast_id": str(ast.get("condition_ast_id") or ""),
                    "node_id": node_id,
                    "node_type": node_type,
                    "logical_table_id": table_id,
                    "table_role": node.get("table_role"),
                    "table_category": table_meta["category"],
                    "source_fragment": str(node.get("source_fragment") or ""),
                    "semantic_type": node.get("semantic_type"),
                    "occurrence_qualifier": table_occurrence_qualifier(node, table_index),
                    "polarity_sign": 1 if polarity >= 0 else -1,
                    "display_role": "INCLUDE" if polarity >= 0 else "EXCLUDE",
                    "display_label": "기본 포함조건" if polarity >= 0 else "제외 대상",
                    "operator_path": path,
                    "inside_exclusion_base": exclusion_base_in_path,
                    "inside_exclusion_excluded": exclusion_excluded_in_path,
                    "legacy_exclusion_ancestor_collapse_would_misclassify": bool(
                        polarity >= 0 and (exclusion_base_in_path or exclusion_excluded_in_path)
                    ),
                })

            children = [str(x) for x in node.get("child_node_ids") or []]
            if node_type == "NOT":
                for child_id in children:
                    walk(child_id, -polarity, path + [{
                        "node_id": node_id,
                        "operator": "NOT",
                        "branch": "negated",
                        "polarity_after": -1 if polarity >= 0 else 1,
                    }])
            elif node_type == "EXCLUSION":
                if len(children) != 2:
                    raise RuntimeError(f"EXCLUSION must have exactly 2 children: {ast.get('condition_ast_id')} / {node_id}")
                walk(children[0], polarity, path + [{
                    "node_id": node_id,
                    "operator": "EXCLUSION",
                    "branch": "base",
                    "polarity_after": 1 if polarity >= 0 else -1,
                }])
                walk(children[1], -polarity, path + [{
                    "node_id": node_id,
                    "operator": "EXCLUSION",
                    "branch": "excluded",
                    "polarity_after": -1 if polarity >= 0 else 1,
                }])
            else:
                for child_id in children:
                    walk(child_id, polarity, path + [{
                        "node_id": node_id,
                        "operator": node_type,
                        "branch": "inherit",
                        "polarity_after": 1 if polarity >= 0 else -1,
                    }])

        walk(root_id, 1, [])
        if visited != set(nodes):
            missing = sorted(set(nodes) - visited)
            raise RuntimeError(f"AST unreachable nodes: {ast.get('condition_ast_id')} / {missing[:10]}")
    rows.sort(key=lambda x: (x["adrg"], x["node_id"], x["logical_table_id"]))
    return rows


def build_contract(integrated: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    table_registry, table_by_id = build_table_registry(integrated, profile)
    adrg_registry = build_adrg_registry(integrated)
    occurrences = build_condition_occurrences(integrated, table_by_id)

    table_category_counts = Counter(row["category"] for row in table_registry)
    coverage_counts = Counter(row["coverage_state"] for row in adrg_registry)
    display_role_counts = Counter(row["display_role"] for row in occurrences)
    qualifier_counts = Counter(row["occurrence_qualifier"] for row in occurrences)
    node_type_counts = Counter(row["node_type"] for row in occurrences)
    base_occurrences = [row for row in occurrences if row["inside_exclusion_base"]]
    excluded_occurrences = [row for row in occurrences if row["inside_exclusion_excluded"]]
    legacy_misclassified = [row for row in occurrences if row["legacy_exclusion_ancestor_collapse_would_misclassify"]]

    protected_hashes = {
        rel: sha256_file(ROOT / rel)
        for rel in PROTECTED_FILES
        if (ROOT / rel).exists()
    }

    representatives: dict[str, Any] = {}
    for adrg_code in ("E011", "9610", "9620"):
        representatives[adrg_code] = {
            "adrg_display": next(row for row in adrg_registry if row["adrg"] == adrg_code),
            "condition_table_occurrences": [row for row in occurrences if row["adrg"] == adrg_code],
        }

    return {
        "meta": {
            "schema_version": OUTPUT_SCHEMA,
            "script_version": SCRIPT_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_schema_version": integrated.get("meta", {}).get("schema_version"),
            "source_sha256": sha256_file(SOURCE_PATH),
            "semantic_profile_schema_version": profile.get("meta", {}).get("schema_version"),
            "semantic_profile_sha256": sha256_file(PROFILE_PATH),
            "state": "ui_display_contract_ready",
            "read_only_contract_build": True,
            "target_runtimes": ["PySide6", "Electron"],
        },
        "input_hashes": {
            "data/kdrg_v47_search_integrated.json": sha256_file(SOURCE_PATH),
            "data/kdrg_v47_ui_semantic_profile.json": sha256_file(PROFILE_PATH),
            **protected_hashes,
        },
        "source_counts": dict(profile.get("source_counts") or {}),
        "contract_counts": {
            "adrg_display_registry": len(adrg_registry),
            "table_display_registry": len(table_registry),
            "condition_table_occurrence_registry": len(occurrences),
            "condition_table_include_occurrences": display_role_counts["INCLUDE"],
            "condition_table_exclude_occurrences": display_role_counts["EXCLUDE"],
            "exclusion_base_occurrences": len(base_occurrences),
            "exclusion_excluded_occurrences": len(excluded_occurrences),
            "exclusion_excluded_final_include_occurrences": sum(1 for row in excluded_occurrences if row["display_role"] == "INCLUDE"),
            "legacy_ancestor_collapse_misclassification_occurrences": len(legacy_misclassified),
            "code_only_table_count": sum(1 for row in table_registry if len(row["visible_columns"]) == 1),
            "table_category_counts": dict(sorted(table_category_counts.items())),
            "adrg_coverage_state_counts": dict(sorted(coverage_counts.items())),
            "occurrence_qualifier_counts": dict(sorted(qualifier_counts.items())),
            "occurrence_node_type_counts": dict(sorted(node_type_counts.items())),
        },
        "global_display_principles": {
            "presentation_only": "이 계약은 검색 결과의 표시 규칙이며 최종 DRG 판정을 수행하지 않음",
            "source_order_preserved": True,
            "no_unofficial_inference": True,
            "no_name_translation_or_fabrication": True,
            "technical_ast_secondary": "canonical expression은 기본 접힘 상태의 기술식 보기에서만 노출",
            "basic_and_extra_conditions_separated": True,
            "family_reference_policy": "ADRG family는 ADRG 결과로 승격하지 않고 원문 family 근거로만 표시",
        },
        "condition_display_contract": {
            "operator_rules": {
                "AND": {"headline": "모든 조건을 충족", "connector": "그리고", "child_polarity": "inherit"},
                "OR": {"headline": "다음 조건 중 하나를 충족", "connector": "또는", "child_polarity": "inherit"},
                "NOT": {"headline": "다음 조건에 해당하지 않음", "connector": "제외", "child_polarity": "invert"},
                "EXCLUSION": {
                    "headline": "기본 포함조건에서 제외 대상을 뺌",
                    "base_child_index": 0,
                    "excluded_child_index": 1,
                    "base_label": "기본 포함조건",
                    "excluded_label": "단, 다음 대상은 제외",
                    "base_polarity": "inherit",
                    "excluded_polarity": "invert",
                    "must_not_flatten_descendants_as_negative": True,
                },
            },
            "polarity_algorithm": {
                "initial_polarity": 1,
                "AND_OR_OTHER": "현재 polarity를 모든 자식에게 상속",
                "NOT": "현재 polarity에 -1을 곱함",
                "EXCLUSION_BASE": "현재 polarity를 그대로 상속",
                "EXCLUSION_EXCLUDED": "현재 polarity에 -1을 곱함",
                "final_positive_role": "INCLUDE",
                "final_negative_role": "EXCLUDE",
                "reason": "EXCLUSION base 오분류와 NOT+EXCLUSION 이중부정 특례를 하나의 일반 규칙으로 처리",
            },
            "coverage_states": COVERAGE_META,
            "source_table_section": {
                "title": "기본 분류 TABLE",
                "source_field": "source_logical_table_ids",
                "must_be_separate_from_ast": True,
            },
            "extra_condition_section": {
                "title": "추가 분기조건",
                "source_field": "condition_ast_id",
                "technical_expression_default": "collapsed",
                "technical_expression_label": "기술식 보기",
            },
            "text_condition_table_qualifiers": {
                "OPTIONAL_COMPANION_TABLE": "선택적으로 함께 적용될 수 있는 TABLE",
                "REQUIRED_TABLE": "조건식의 기본 TABLE",
                "PROCEDURE_COUNT_TABLE": "해당 TABLE 코드의 건수 조건",
                "MAJOR_PROBLEM_TABLE": "해당 TABLE 내 진단 건수 조건",
                "QUALIFIED_TABLE_CONDITION_TEXT": "원문 한정 조건을 함께 표시",
                "QUALIFIED_TABLE_EXCLUSION_TEXT": "원문 내 부분 제외 문구를 함께 표시",
            },
        },
        "table_display_contract": {
            "category_resolution_precedence": [
                "AST table_role 근거",
                "향후 logical_table_scope 공식값",
                "근거가 없으면 unknown 중립값",
            ],
            "must_not_classify_unknown_as_procedure": True,
            "categories": CATEGORY_META,
            "dynamic_column_rules": {
                "code": "항상 표시",
                "name_ko": "원천 name_ko 데이터가 하나 이상 있을 때만 표시",
                "name_en": "원천 name_en 데이터가 하나 이상 있을 때만 표시",
                "empty_columns": "열 전체가 비면 숨김",
                "current_integrated_json": "모든 names가 비어 있으므로 1,308개 TABLE 모두 코드 단일 열",
            },
            "missing_name_copy": "코드명 데이터 미수록",
            "table_button_copy": "TABLE을 열면 원문 순서를 유지한 코드 목록이 표시됩니다.",
            "must_preserve_code_order": True,
        },
        "adrg_display_registry": adrg_registry,
        "table_display_registry": table_registry,
        "condition_table_occurrence_registry": occurrences,
        "representative_models": representatives,
        "implementation_gate": {
            "stage_49_pyside_minimum_fix": [
                "polarity_algorithm으로 runtime context 재구축",
                "기본 분류 TABLE과 추가 분기조건 구역 분리",
                "unknown TABLE을 수술·처치로 기본 분류하지 않음",
                "visible_columns에 따라 동적 코드표 렌더링",
                "기술식은 기본 접힘 상태",
            ],
            "stage_50_electron_start_condition": "49번 PySide 의미 수정과 독립 회귀검증 PASS / 0 FAIL",
            "protected_data_policy": "48번에서는 통합 JSON과 앱 코드 변경 금지",
        },
    }


def main() -> int:
    checks: list[dict[str, Any]] = []

    def check(name: str, actual: Any, expected: Any) -> None:
        passed = actual == expected
        checks.append({"name": name, "actual": actual, "expected": expected, "passed": passed})
        if not passed:
            raise RuntimeError(f"{name}: actual={actual!r}, expected={expected!r}")

    for required in [SOURCE_PATH, PROFILE_PATH, *(ROOT / rel for rel in PROTECTED_FILES)]:
        check(f"필수 입력 {required.relative_to(ROOT)}", required.exists(), True)

    protected_before = {rel: sha256_file(ROOT / rel) for rel in PROTECTED_FILES}
    integrated = load_json(SOURCE_PATH)
    profile = load_json(PROFILE_PATH)

    check("통합 JSON schema", integrated.get("meta", {}).get("schema_version"), SOURCE_SCHEMA)
    check("통합 JSON SHA256", sha256_file(SOURCE_PATH), EXPECTED_SOURCE_SHA256)
    check("UI semantic profile schema", profile.get("meta", {}).get("schema_version"), PROFILE_SCHEMA)
    check("profile source SHA256", profile.get("meta", {}).get("source_sha256"), EXPECTED_SOURCE_SHA256)
    check("profile read only audit", profile.get("meta", {}).get("read_only_audit"), True)

    for rel, expected_hash in (profile.get("input_hashes") or {}).items():
        path = ROOT / rel
        if path.exists():
            check(f"profile 입력 해시 {rel}", sha256_file(path), expected_hash)

    contract = build_contract(integrated, profile)
    write_json(OUTPUT_PATH, contract)

    counts = contract["contract_counts"]
    source_counts = profile["source_counts"]
    profile_coverage = profile["condition_coverage"]["counts"]
    profile_exclusion = profile["exclusion_semantics"]["counts"]
    profile_roles = profile["table_display_schema"]["ast_role_evidence"]

    check("output schema", contract["meta"]["schema_version"], OUTPUT_SCHEMA)
    check("ADRG registry count", counts["adrg_display_registry"], source_counts["adrg_records"])
    check("TABLE registry count", counts["table_display_registry"], source_counts["logical_table_records"])
    check("condition TABLE occurrence count", counts["condition_table_occurrence_registry"], 939)
    check("include occurrence count", counts["condition_table_include_occurrences"], 874)
    check("exclude occurrence count", counts["condition_table_exclude_occurrences"], 65)
    check("EXCLUSION base occurrence count", counts["exclusion_base_occurrences"], profile_exclusion["base_table_ref_occurrence_count"])
    check("EXCLUSION excluded occurrence count", counts["exclusion_excluded_occurrences"], profile_exclusion["excluded_table_ref_occurrence_count"])
    check("EXCLUSION excluded double-negative include", counts["exclusion_excluded_final_include_occurrences"], 19)
    check("legacy misclassification occurrence", counts["legacy_ancestor_collapse_misclassification_occurrences"], 47)
    check("code only TABLE count", counts["code_only_table_count"], source_counts["logical_table_records"])
    check("diagnosis category", counts["table_category_counts"].get("diagnosis"), profile_roles["category_counts"]["diagnosis"])
    check("procedure category", counts["table_category_counts"].get("procedure"), profile_roles["category_counts"]["procedure"])
    check("add on category", counts["table_category_counts"].get("add_on_code"), profile_roles["category_counts"]["add_on_code"])
    check("unknown category", counts["table_category_counts"].get("unknown"), profile_roles["table_without_evidence_count"])
    check("coverage source no AST", counts["adrg_coverage_state_counts"].get("BASIC_TABLE_NO_EXTRA_CONDITION"), profile_coverage["source_tables_without_ast"])
    check("coverage no source no AST", counts["adrg_coverage_state_counts"].get("NO_BASIC_TABLE_NO_EXTRA_CONDITION"), profile_coverage["no_ast_no_source_table"])
    check("coverage AST no TABLE", counts["adrg_coverage_state_counts"].get("EXTRA_CONDITION_NO_TABLE_REF"), profile_coverage["ast_without_table_reference"])
    check("coverage AST condition only", counts["adrg_coverage_state_counts"].get("EXTRA_CONDITION_TABLES_NO_BASIC_TABLE"), profile_coverage["ast_with_condition_tables_only"])
    check("coverage source and AST", counts["adrg_coverage_state_counts"].get("BASIC_TABLE_AND_EXTRA_CONDITION_TABLES"), profile_coverage["ast_with_source_and_condition_tables"])

    reps = contract["representative_models"]
    e011 = reps["E011"]["condition_table_occurrences"]
    check("E011 base include", [(r["logical_table_id"], r["display_role"]) for r in e011 if r["logical_table_id"] == "LT_E011_002"], [("LT_E011_002", "INCLUDE")])
    check("E011 excluded", [(r["logical_table_id"], r["display_role"]) for r in e011 if r["logical_table_id"] == "LT_E011_003"], [("LT_E011_003", "EXCLUDE")])
    check("9610 coverage copy", reps["9610"]["adrg_display"]["summary_copy"], "기본 분류 TABLE 있음 · 별도의 추가 분기조건 없음")
    check("9620 base include", [(r["logical_table_id"], r["display_role"]) for r in reps["9620"]["condition_table_occurrences"] if r["logical_table_id"] == "LT_9620_001"], [("LT_9620_001", "INCLUDE")])
    check("9620 excluded", [(r["logical_table_id"], r["display_role"]) for r in reps["9620"]["condition_table_occurrences"] if r["logical_table_id"] == "LT_9620_002"], [("LT_9620_002", "EXCLUDE")])

    protected_after = {rel: sha256_file(ROOT / rel) for rel in PROTECTED_FILES}
    for rel in PROTECTED_FILES:
        check(f"보호 파일 불변 {rel}", protected_after[rel], protected_before[rel])

    passed = sum(1 for item in checks if item["passed"])
    failed = len(checks) - passed
    report = {
        "meta": {"script_version": SCRIPT_VERSION, "generated_at": datetime.now(timezone.utc).isoformat()},
        "input_hashes": contract["input_hashes"],
        "output": str(OUTPUT_PATH.relative_to(ROOT)),
        "output_sha256": sha256_file(OUTPUT_PATH),
        "contract_counts": counts,
        "checks": checks,
        "result": {"pass": passed, "fail": failed, "total": len(checks), "status": "PASS" if failed == 0 else "FAIL"},
    }
    write_json(REPORT_JSON_PATH, report)

    lines = [
        "KDRG V4.7 공통 UI 표현 계약 생성 결과",
        "=" * 78,
        f"스크립트 버전: {SCRIPT_VERSION}",
        f"통합 JSON SHA256: {sha256_file(SOURCE_PATH)}",
        f"UI semantic profile SHA256: {sha256_file(PROFILE_PATH)}",
        "",
        "[핵심 계약]",
        f"- ADRG 표시 registry: {counts['adrg_display_registry']:,}",
        f"- TABLE 표시 registry: {counts['table_display_registry']:,}",
        f"- 조건 TABLE occurrence: {counts['condition_table_occurrence_registry']:,}",
        f"- 최종 포함 occurrence: {counts['condition_table_include_occurrences']:,}",
        f"- 최종 제외 occurrence: {counts['condition_table_exclude_occurrences']:,}",
        f"- EXCLUSION base occurrence: {counts['exclusion_base_occurrences']:,}",
        f"- EXCLUSION excluded occurrence: {counts['exclusion_excluded_occurrences']:,}",
        f"- NOT+EXCLUSION 이중부정으로 최종 포함되는 excluded occurrence: {counts['exclusion_excluded_final_include_occurrences']:,}",
        f"- 기존 조상기반 음성 판정 오분류 가능 occurrence: {counts['legacy_ancestor_collapse_misclassification_occurrences']:,}",
        f"- 코드 단일 열 TABLE: {counts['code_only_table_count']:,}",
        "",
        "[확정 규칙]",
        "- EXCLUSION 첫 번째 자식은 base로 현재 polarity를 상속",
        "- EXCLUSION 두 번째 자식은 excluded로 polarity를 반전",
        "- NOT은 polarity를 반전하고 AND/OR는 그대로 상속",
        "- 따라서 EXCLUSION 조상 아래 모든 TABLE을 일괄 제외로 표시하지 않음",
        "- 기본 분류 TABLE과 추가 분기조건은 별도 구역으로 표시",
        "- 근거 없는 TABLE 유형은 '코드 TABLE(유형 미확정)'으로 표시",
        "- 이름 데이터가 없는 현재 1,308개 TABLE은 코드 단일 열로 표시",
        "- canonical AST 식은 기본 접힘 상태의 '기술식 보기'에서만 노출",
        "",
        "[대표 사례]",
        "- E011: LT_E011_002 기본 포함 / LT_E011_003 제외",
        "- 9610: 기본 분류 TABLE 있음 / 별도의 추가 분기조건 없음",
        "- 9620: LT_9620_001 기본 포함 / LT_9620_002 제외",
        "",
        "[생성 파일]",
        "- data/kdrg_v47_ui_display_contract.json",
        "- reports/ui_display_contract_build_report.json",
        "- reports/ui_display_contract_build_report.txt",
        "",
        "[다음 단계]",
        "- 49번: 공통 계약을 적용한 PySide 의미 최소수정",
        "- 통합 JSON은 변경하지 않고 service/adapter/UI만 일반화 규칙으로 수정",
        "",
        "[최종 결과]",
        f"PASS: {passed}",
        f"FAIL: {failed}",
        f"TOTAL: {len(checks)}",
        f"전체 결과: {'PASS' if failed == 0 else 'FAIL'}",
    ]
    write_text(REPORT_TXT_PATH, "\n".join(lines) + "\n")

    print(f"[PASS] KDRG 공통 UI 표현 계약 생성: {passed} PASS / {failed} FAIL")
    print(f"contract={OUTPUT_PATH}")
    print(f"report={REPORT_TXT_PATH}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[FAIL] KDRG 공통 UI 표현 계약 생성 예외: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
