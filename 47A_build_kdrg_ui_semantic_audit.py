from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCRIPT_VERSION = "2026-07-27_KDRG_V47_UI_SEMANTIC_AUDIT_BUILDER_V1"
PROFILE_SCHEMA = "kdrg-v47-ui-semantic-profile-v1"
EXPECTED_DATA_SCHEMA = "kdrg-v47-search-integrated-v2"

ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data" / "kdrg_v47_search_integrated.json"
SEARCH_SERVICE_PATH = ROOT / "app" / "kdrg_search_service.py"
RUNTIME_STORE_PATH = ROOT / "app" / "runtime_data_store.py"
MAIN_WINDOW_PATH = ROOT / "app" / "main_window.py"

PROFILE_PATH = ROOT / "data" / "kdrg_v47_ui_semantic_profile.json"
REPORT_JSON_PATH = ROOT / "reports" / "ui_semantic_audit_report.json"
REPORT_TXT_PATH = ROOT / "reports" / "ui_semantic_audit_report.txt"

EXPECTED_HASHES = {
    "data/kdrg_v47_search_integrated.json": "3de5d6d95cd9cbd16e674f5a4cffcd8bf89da2ee70627501f56d81b05bbe8af1",
    "app/kdrg_search_service.py": "c9b09140ca0f2c0e498ccae3eb35e8b5f0f773d04cd93156faff21e6e5e79be4",
    "app/runtime_data_store.py": "dc42dcad29ebfaec6a0ad6359c5257d7849c268c9b6fb4982f29533ac13ef8ae",
    "app/main_window.py": "76ccc2578bae28b5cc5d21f18ae761cb605222d1bf50d381c35e202166acca17",
}

DIAGNOSIS_ROLES = {
    "principal_diagnosis",
    "diagnosis",
    "secondary_diagnosis",
    "principal_or_secondary_diagnosis",
}
ADD_ON_ROLES = {"add_on_code"}
PROCEDURE_ROLES = {"procedure", "text:procedure_count"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON root must be object: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def unique(values: Iterable[Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return output


def contains_hangul(value: str) -> bool:
    return bool(re.search(r"[가-힣]", str(value or "")))


def descendants(root_id: str, nodes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    stack = [root_id]
    while stack:
        node_id = stack.pop()
        if not node_id or node_id in seen:
            continue
        seen.add(node_id)
        node = nodes.get(node_id)
        if not node:
            continue
        output.append(node)
        stack.extend(str(value) for value in reversed(node.get("child_node_ids") or []))
    return output


def table_refs(node_rows: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for node in node_rows:
        node_id = str(node.get("node_id") or "")
        for table_id in unique(node.get("logical_table_ids") or []):
            output.append(
                {
                    "table_id": table_id,
                    "node_id": node_id,
                    "node_type": str(node.get("node_type") or ""),
                    "source_fragment": str(node.get("source_fragment") or node.get("display_text") or ""),
                }
            )
    return output


def classify_role_evidence(role_set: set[str]) -> str:
    if role_set & DIAGNOSIS_ROLES:
        return "diagnosis"
    if role_set & ADD_ON_ROLES:
        return "add_on_code"
    if role_set & PROCEDURE_ROLES:
        return "procedure"
    if "text:optional_table_presence" in role_set:
        return "optional_semantic"
    if role_set:
        return "other_semantic"
    return "unknown"


def require_files() -> dict[str, str]:
    paths = {
        "data/kdrg_v47_search_integrated.json": DATA_PATH,
        "app/kdrg_search_service.py": SEARCH_SERVICE_PATH,
        "app/runtime_data_store.py": RUNTIME_STORE_PATH,
        "app/main_window.py": MAIN_WINDOW_PATH,
    }
    actual_hashes: dict[str, str] = {}
    failures: list[str] = []
    for relative, path in paths.items():
        if not path.is_file():
            failures.append(f"missing: {relative}")
            continue
        actual = sha256_file(path)
        actual_hashes[relative] = actual
        expected = EXPECTED_HASHES[relative]
        if actual != expected:
            failures.append(f"hash mismatch: {relative} actual={actual} expected={expected}")
    if failures:
        raise RuntimeError("\n".join(failures))
    return actual_hashes


def build_profile(data: dict[str, Any], input_hashes: dict[str, str]) -> dict[str, Any]:
    meta = data.get("meta") or {}
    if str(meta.get("schema_version") or "") != EXPECTED_DATA_SCHEMA:
        raise RuntimeError(
            f"schema mismatch: actual={meta.get('schema_version')} expected={EXPECTED_DATA_SCHEMA}"
        )

    adrg_records = list(data.get("adrg_records") or [])
    table_records = list(data.get("logical_table_records") or [])
    ast_records = list(data.get("condition_ast_records") or [])
    code_records = list(data.get("code_records") or [])

    adrg_by_code = {str(row.get("adrg") or ""): row for row in adrg_records}
    ast_by_adrg = {str(row.get("adrg") or ""): row for row in ast_records}
    table_by_id = {str(row.get("logical_table_id") or ""): row for row in table_records}
    code_by_code = {str(row.get("code") or ""): row for row in code_records}

    coverage_counter: Counter[str] = Counter()
    coverage_examples: dict[str, list[str]] = defaultdict(list)
    for adrg, row in adrg_by_code.items():
        has_ast = adrg in ast_by_adrg
        has_source_tables = bool(row.get("source_logical_table_ids") or [])
        has_condition_tables = bool(row.get("condition_logical_table_ids") or [])
        if has_ast and has_source_tables and has_condition_tables:
            key = "ast_with_source_and_condition_tables"
        elif has_ast and (not has_source_tables) and has_condition_tables:
            key = "ast_with_condition_tables_only"
        elif has_ast and (not has_source_tables) and (not has_condition_tables):
            key = "ast_without_table_reference"
        elif (not has_ast) and has_source_tables:
            key = "source_tables_without_ast"
        else:
            key = "no_ast_no_source_table"
        coverage_counter[key] += 1
        if len(coverage_examples[key]) < 20:
            coverage_examples[key].append(adrg)

    role_evidence: dict[str, set[str]] = defaultdict(set)
    role_evidence_occurrences: list[dict[str, Any]] = []
    exclusion_cases: list[dict[str, Any]] = []
    exclusion_counter: Counter[str] = Counter()
    base_table_occurrence_ids: list[str] = []
    excluded_table_occurrence_ids: list[str] = []

    for ast in ast_records:
        adrg = str(ast.get("adrg") or "")
        nodes = {
            str(node.get("node_id") or ""): node
            for node in ast.get("nodes") or []
            if str(node.get("node_id") or "")
        }

        for node in ast.get("nodes") or []:
            table_ids = unique(node.get("logical_table_ids") or [])
            if not table_ids:
                continue
            node_type = str(node.get("node_type") or "")
            if node_type == "TABLE_REF":
                role = str(node.get("table_role") or "unknown")
            elif node_type == "TEXT_CONDITION":
                role = f"text:{node.get('semantic_type') or 'unknown'}"
            else:
                role = node_type.casefold() or "unknown"
            for table_id in table_ids:
                role_evidence[table_id].add(role)
                role_evidence_occurrences.append(
                    {
                        "adrg": adrg,
                        "condition_ast_id": str(ast.get("condition_ast_id") or ""),
                        "node_id": str(node.get("node_id") or ""),
                        "table_id": table_id,
                        "role": role,
                        "source_fragment": str(node.get("source_fragment") or node.get("display_text") or ""),
                    }
                )

        for node in ast.get("nodes") or []:
            if str(node.get("node_type") or "") != "EXCLUSION":
                continue
            exclusion_counter["node_count"] += 1
            child_ids = [str(value) for value in node.get("child_node_ids") or []]
            if len(child_ids) == 2:
                exclusion_counter["binary_node_count"] += 1
            else:
                exclusion_counter["non_binary_node_count"] += 1

            base_nodes = descendants(child_ids[0], nodes) if child_ids else []
            excluded_nodes = descendants(child_ids[1], nodes) if len(child_ids) >= 2 else []
            base_refs = table_refs(base_nodes)
            excluded_refs = table_refs(excluded_nodes)
            base_table_ids = [row["table_id"] for row in base_refs]
            excluded_table_ids = [row["table_id"] for row in excluded_refs]
            base_table_occurrence_ids.extend(base_table_ids)
            excluded_table_occurrence_ids.extend(excluded_table_ids)

            if base_refs:
                exclusion_counter["nodes_with_base_table"] += 1
            if excluded_refs:
                exclusion_counter["nodes_with_excluded_table"] += 1
            if base_refs and excluded_refs:
                exclusion_counter["nodes_with_both_table_roles"] += 1

            overlap = sorted(set(base_table_ids) & set(excluded_table_ids))
            if overlap:
                exclusion_counter["nodes_with_role_overlap"] += 1

            case = {
                "adrg": adrg,
                "condition_ast_id": str(ast.get("condition_ast_id") or ""),
                "exclusion_node_id": str(node.get("node_id") or ""),
                "source_fragment": str(node.get("source_fragment") or ""),
                "operand_roles": list(node.get("operand_roles") or []),
                "child_node_ids": child_ids,
                "base_table_refs": base_refs,
                "excluded_table_refs": excluded_refs,
                "base_table_ids": unique(base_table_ids),
                "excluded_table_ids": unique(excluded_table_ids),
                "role_overlap_table_ids": overlap,
                "legacy_runtime_risk": {
                    "base_refs_misclassified_as_negative": len(base_refs),
                    "reason": (
                        "현재 semantic context 분류가 EXCLUSION 조상 아래의 모든 TABLE_REF를 negative로 처리하여 "
                        "첫 번째 자식(base)도 제외조건으로 표시함"
                    ),
                },
                "recommended_display": {
                    "base_label": "기본 포함조건",
                    "excluded_label": "단, 다음 대상은 제외",
                },
            }
            exclusion_cases.append(case)

    role_set_distribution = Counter(tuple(sorted(values)) for values in role_evidence.values())
    role_category_counter = Counter(classify_role_evidence(values) for values in role_evidence.values())

    code_name_counter: Counter[str] = Counter()
    code_role_counter: Counter[str] = Counter()
    for row in code_records:
        names = unique(row.get("names") or [])
        roles = unique(row.get("roles") or [])
        has_ko = any(contains_hangul(value) for value in names)
        has_non_ko = any(not contains_hangul(value) for value in names)
        if not names:
            code_name_counter["none"] += 1
        elif has_ko and has_non_ko:
            code_name_counter["korean_and_non_korean"] += 1
        elif has_ko:
            code_name_counter["korean_only"] += 1
        else:
            code_name_counter["non_korean_only"] += 1
        if roles:
            code_role_counter["with_roles"] += 1
        else:
            code_role_counter["without_roles"] += 1

    table_name_counter: Counter[str] = Counter()
    table_scope_counter: Counter[str] = Counter()
    table_examples: dict[str, list[str]] = defaultdict(list)
    table_profiles: list[dict[str, Any]] = []
    for row in table_records:
        table_id = str(row.get("logical_table_id") or "")
        scope = str(row.get("logical_table_scope") or "").strip()
        if scope:
            table_scope_counter["with_scope"] += 1
        else:
            table_scope_counter["missing_scope"] += 1

        codes = unique(row.get("codes") or [])
        named_count = 0
        ko_count = 0
        non_ko_count = 0
        role_count = 0
        for code in codes:
            code_row = code_by_code.get(code) or {}
            names = unique(code_row.get("names") or [])
            roles = unique(code_row.get("roles") or [])
            if names:
                named_count += 1
            if any(contains_hangul(value) for value in names):
                ko_count += 1
            if any(not contains_hangul(value) for value in names):
                non_ko_count += 1
            if roles:
                role_count += 1

        if named_count == 0:
            name_state = "all_names_missing"
        elif named_count < len(codes):
            name_state = "partial_names"
        else:
            name_state = "all_named"
        table_name_counter[name_state] += 1
        if len(table_examples[name_state]) < 20:
            table_examples[name_state].append(table_id)

        evidence = sorted(role_evidence.get(table_id, set()))
        table_profiles.append(
            {
                "logical_table_id": table_id,
                "logical_table_type": str(row.get("logical_table_type") or ""),
                "logical_table_scope": scope or None,
                "code_count": len(codes),
                "named_code_count": named_count,
                "korean_name_code_count": ko_count,
                "non_korean_name_code_count": non_ko_count,
                "code_with_role_count": role_count,
                "ast_role_evidence": evidence,
                "recommended_table_category": classify_role_evidence(set(evidence)),
                "display_schema_status": (
                    "role_evidence_available" if evidence else "role_unknown_requires_neutral_columns"
                ),
            }
        )

    search_service_text = SEARCH_SERVICE_PATH.read_text(encoding="utf-8")
    runtime_store_text = RUNTIME_STORE_PATH.read_text(encoding="utf-8")
    main_window_text = MAIN_WINDOW_PATH.read_text(encoding="utf-8")

    source_pattern_checks = {
        "search_service_exclusion_ancestor_collapse": (
            'elif "NOT" in ancestor_types or "EXCLUSION" in ancestor_types:' in search_service_text
        ),
        "runtime_unknown_type_defaults_to_procedure": (
            'return "수술·처치코드"' in runtime_store_text
        ),
        "runtime_no_ast_technical_copy": (
            '"본문 조건 AST 없음"' in runtime_store_text
        ),
        "ui_hardcoded_three_columns": (
            'setHorizontalHeaderLabels(["코드", "한글명", "영문명"])' in main_window_text
        ),
        "ui_hardcoded_three_column_note": (
            "코드·한글명·영문명 상세 코드표" in main_window_text
        ),
    }

    no_ast_example_9610 = adrg_by_code.get("9610") or {}
    e011_case = next((case for case in exclusion_cases if case["adrg"] == "E011"), None)
    p9620_case = next((case for case in exclusion_cases if case["adrg"] == "9620"), None)

    issue_register = [
        {
            "issue_id": "UI-SEM-001",
            "severity": "BLOCKER_BEFORE_ELECTRON",
            "title": "EXCLUSION base와 excluded 역할 붕괴",
            "evidence": {
                "exclusion_node_count": exclusion_counter["node_count"],
                "base_table_ref_occurrence_count": len(base_table_occurrence_ids),
                "base_table_relation_count": sum(len(set(case["base_table_ids"])) for case in exclusion_cases),
                "unique_base_table_count": len(set(base_table_occurrence_ids)),
                "affected_exclusion_node_count": exclusion_counter["nodes_with_base_table"],
                "current_source_pattern_present": source_pattern_checks[
                    "search_service_exclusion_ancestor_collapse"
                ],
            },
            "impact": (
                "기본 포함조건 TABLE이 제외조건으로 표시되어 E011, 9620 등에서 분류 의미가 반대로 보일 수 있음"
            ),
            "generalized_fix": (
                "EXCLUSION의 첫 번째 자식 subtree는 include/base, 두 번째 자식 subtree는 exclude로 역할을 전파하고 "
                "NOT 조상 판정과 분리"
            ),
            "implementation_stage": "48 표현 계약 확정 후 49 PySide 최소 수정",
        },
        {
            "issue_id": "UI-SEM-002",
            "severity": "BLOCKER_BEFORE_ELECTRON",
            "title": "TABLE 유형 미수록 값을 전부 수술·처치로 기본 분류",
            "evidence": {
                "table_count": len(table_records),
                "missing_scope_count": table_scope_counter["missing_scope"],
                "tables_with_ast_role_evidence": len(role_evidence),
                "tables_without_ast_role_evidence": len(table_records) - len(role_evidence),
                "diagnosis_evidence_table_count": role_category_counter["diagnosis"],
                "add_on_evidence_table_count": role_category_counter["add_on_code"],
                "current_source_pattern_present": source_pattern_checks[
                    "runtime_unknown_type_defaults_to_procedure"
                ],
            },
            "impact": (
                "주진단·기타진단·부가코드 TABLE도 수술·처치로 표시될 수 있어 TABLE 역할과 필터가 왜곡됨"
            ),
            "generalized_fix": (
                "AST table_role 근거를 우선 사용하고, 근거가 없는 TABLE은 '코드 TABLE(유형 미확정)' 중립값으로 표시"
            ),
            "implementation_stage": "48 표현 계약 확정 후 49 PySide 최소 수정",
        },
        {
            "issue_id": "UI-SEM-003",
            "severity": "DATA_GAP_TO_RESOLVE_BEFORE_FINAL_UI",
            "title": "통합 JSON에 코드 한글명·영문명 미수록",
            "evidence": {
                "code_record_count": len(code_records),
                "codes_with_name_count": len(code_records) - code_name_counter["none"],
                "codes_without_name_count": code_name_counter["none"],
                "tables_with_all_names_missing": table_name_counter["all_names_missing"],
                "ui_hardcoded_three_columns": source_pattern_checks["ui_hardcoded_three_columns"],
            },
            "impact": (
                "현재 세 열 표시는 테스트 placeholder이며, 실제 한글명·영문명 상세를 제공할 데이터가 없음"
            ),
            "generalized_fix": (
                "명칭 원천을 별도 기준축으로 통합하기 전에는 '코드' 단일 열을 기본으로 하고, 존재하는 필드만 동적으로 표시"
            ),
            "implementation_stage": "48 표시 규격에서 결측 정책 확정, 명칭 데이터 보강은 별도 후속 데이터 단계",
        },
        {
            "issue_id": "UI-SEM-004",
            "severity": "MUST_FIX_COPY_BEFORE_ELECTRON",
            "title": "기본 TABLE과 추가 AST 부재를 혼동시키는 문구",
            "evidence": {
                "source_tables_without_ast_adrg_count": coverage_counter[
                    "source_tables_without_ast"
                ],
                "no_ast_no_source_table_adrg_count": coverage_counter[
                    "no_ast_no_source_table"
                ],
                "current_source_pattern_present": source_pattern_checks[
                    "runtime_no_ast_technical_copy"
                ],
                "representative_9610": {
                    "source_logical_table_ids": list(
                        no_ast_example_9610.get("source_logical_table_ids") or []
                    ),
                    "condition_ast_id": no_ast_example_9610.get("condition_ast_id"),
                },
            },
            "impact": (
                "'본문 조건 AST 없음'이 기본 분류 TABLE도 없다는 뜻으로 오해될 수 있음"
            ),
            "generalized_fix": (
                "기본 분류 TABLE과 추가 분기조건을 분리하여 '기본 분류 TABLE 있음 / 별도의 추가 분기조건 없음'으로 표시"
            ),
            "implementation_stage": "48 표현 계약 확정 후 49 PySide 최소 수정",
        },
        {
            "issue_id": "UI-SEM-005",
            "severity": "MUST_FIX_SCHEMA_BEFORE_ELECTRON",
            "title": "모든 TABLE에 코드·한글명·영문명 3열을 고정",
            "evidence": {
                "table_count": len(table_records),
                "all_names_missing_table_count": table_name_counter["all_names_missing"],
                "hardcoded_header_present": source_pattern_checks["ui_hardcoded_three_columns"],
                "hardcoded_note_present": source_pattern_checks[
                    "ui_hardcoded_three_column_note"
                ],
            },
            "impact": "TABLE 종류와 실제 데이터 보유 여부가 다른데 동일 열을 강제하여 빈 열과 잘못된 의미를 노출",
            "generalized_fix": (
                "TABLE 표시 계약을 유형·보유필드 기반 동적 열로 정의하고, 미확정 TABLE은 코드 단일 열과 중립 유형으로 표시"
            ),
            "implementation_stage": "48 공통 UI 표현 계약",
        },
    ]

    profile = {
        "meta": {
            "schema_version": PROFILE_SCHEMA,
            "script_version": SCRIPT_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_schema_version": str(meta.get("schema_version") or ""),
            "source_sha256": input_hashes["data/kdrg_v47_search_integrated.json"],
            "state": "ui_semantic_audit_complete",
            "read_only_audit": True,
        },
        "input_hashes": input_hashes,
        "source_counts": {
            "adrg_records": len(adrg_records),
            "logical_table_records": len(table_records),
            "condition_ast_records": len(ast_records),
            "code_records": len(code_records),
            "ast_node_count": sum(len(row.get("nodes") or []) for row in ast_records),
        },
        "condition_coverage": {
            "counts": dict(sorted(coverage_counter.items())),
            "examples": dict(sorted(coverage_examples.items())),
            "display_policy_candidates": {
                "source_tables_without_ast": "기본 분류 TABLE 있음 · 별도의 추가 분기조건 없음",
                "no_ast_no_source_table": "본문 TABLE 및 별도의 추가 분기조건 없음",
                "ast_without_table_reference": "추가 임상·상태 조건 있음 · TABLE 참조 없음",
                "ast_with_tables": "추가 분기조건 있음",
            },
        },
        "exclusion_semantics": {
            "counts": {
                **dict(sorted(exclusion_counter.items())),
                "base_table_ref_occurrence_count": len(base_table_occurrence_ids),
                "base_table_relation_count": sum(len(set(case["base_table_ids"])) for case in exclusion_cases),
                "excluded_table_ref_occurrence_count": len(excluded_table_occurrence_ids),
                "unique_base_table_count": len(set(base_table_occurrence_ids)),
                "unique_excluded_table_count": len(set(excluded_table_occurrence_ids)),
                "legacy_base_ref_misclassification_occurrence_count": len(
                    base_table_occurrence_ids
                ),
            },
            "cases": exclusion_cases,
            "representative_cases": {
                "E011": e011_case,
                "9620": p9620_case,
            },
        },
        "table_display_schema": {
            "scope_counts": dict(sorted(table_scope_counter.items())),
            "code_name_counts": dict(sorted(code_name_counter.items())),
            "code_role_counts": dict(sorted(code_role_counter.items())),
            "table_name_coverage_counts": dict(sorted(table_name_counter.items())),
            "table_name_examples": dict(sorted(table_examples.items())),
            "ast_role_evidence": {
                "table_with_evidence_count": len(role_evidence),
                "table_without_evidence_count": len(table_records) - len(role_evidence),
                "category_counts": dict(sorted(role_category_counter.items())),
                "role_set_distribution": [
                    {"roles": list(role_set), "table_count": count}
                    for role_set, count in sorted(
                        role_set_distribution.items(),
                        key=lambda item: (-item[1], item[0]),
                    )
                ],
                "occurrences": role_evidence_occurrences,
            },
            "table_profiles": table_profiles,
            "recommended_column_policy": {
                "names_unavailable": ["코드"],
                "diagnosis_with_names": ["상병코드", "한글 진단명", "영문 진단명(원천 보유 시)"],
                "procedure_with_names": ["처치코드", "한글 처치명", "영문 처치명(원천 보유 시)"],
                "add_on_with_names": ["부가코드", "코드명(원천 보유 시)"],
                "unknown_type": ["코드"],
            },
        },
        "current_ui_source_patterns": source_pattern_checks,
        "issue_register": issue_register,
        "representative_findings": {
            "E011": {
                "expected_expression": (
                    "LT_E011_001 또는 (LT_E011_002에 해당하면서 LT_E011_003은 제외)"
                ),
                "base_table_id": "LT_E011_002",
                "excluded_table_id": "LT_E011_003",
            },
            "9610": {
                "source_table_ids": list(
                    no_ast_example_9610.get("source_logical_table_ids") or []
                ),
                "condition_ast_id": no_ast_example_9610.get("condition_ast_id"),
                "recommended_copy": "기본 분류 TABLE 있음 · 별도의 추가 분기조건 없음",
            },
            "9620": {
                "expected_expression": (
                    "LT_9620_001 주진단에 해당하면서 LT_9620_002 시술에 해당하는 경우는 제외"
                ),
                "base_table_id": "LT_9620_001",
                "excluded_table_id": "LT_9620_002",
            },
        },
        "next_stage": {
            "stage": "48_build_kdrg_ui_display_contract",
            "purpose": (
                "감사 결과를 바탕으로 EXCLUSION 역할 전파, AST 부재 문구, TABLE 유형 및 동적 열 규칙을 "
                "기계 판독 가능한 공통 UI 표현 계약으로 확정"
            ),
            "protected_files_to_keep_unchanged": list(EXPECTED_HASHES),
        },
    }
    return profile


def report_lines(profile: dict[str, Any]) -> list[str]:
    source = profile["source_counts"]
    coverage = profile["condition_coverage"]["counts"]
    exclusion = profile["exclusion_semantics"]["counts"]
    table_schema = profile["table_display_schema"]
    role = table_schema["ast_role_evidence"]

    lines = [
        "KDRG V4.7 UI 의미·TABLE 스키마 전수감사 결과",
        "=" * 78,
        f"스크립트 버전: {SCRIPT_VERSION}",
        f"입력 JSON SHA256: {profile['meta']['source_sha256']}",
        "",
        "[전수 범위]",
        f"- ADRG: {source['adrg_records']:,}",
        f"- TABLE: {source['logical_table_records']:,}",
        f"- 조건 AST: {source['condition_ast_records']:,}",
        f"- AST node: {source['ast_node_count']:,}",
        f"- 검색 코드: {source['code_records']:,}",
        "",
        "[핵심 판정]",
        "- [BLOCKER] EXCLUSION의 base와 excluded가 현재 UI 변환에서 모두 제외조건으로 합쳐짐",
        f"  · EXCLUSION node: {exclusion['node_count']:,}",
        f"  · base TABLE ref 발생: {exclusion['base_table_ref_occurrence_count']:,}",
        f"  · 영향 EXCLUSION node: {exclusion['nodes_with_base_table']:,}",
        f"  · 영향 고유 TABLE: {exclusion['unique_base_table_count']:,}",
        "- [BLOCKER] TABLE scope가 전부 비어 있는데 현재 adapter는 미확정값을 수술·처치로 기본 분류",
        f"  · scope 미수록 TABLE: {table_schema['scope_counts'].get('missing_scope', 0):,}",
        f"  · AST상 진단 TABLE 근거: {role['category_counts'].get('diagnosis', 0):,}",
        f"  · AST상 부가코드 TABLE 근거: {role['category_counts'].get('add_on_code', 0):,}",
        "- [DATA GAP] 통합 JSON의 모든 code_records.names와 roles가 비어 있음",
        f"  · 명칭 없는 코드: {table_schema['code_name_counts'].get('none', 0):,}",
        f"  · 전체 코드명이 비어 있는 TABLE: {table_schema['table_name_coverage_counts'].get('all_names_missing', 0):,}",
        "- [COPY] 기본 TABLE은 있으나 AST가 없는 ADRG를 '본문 조건 AST 없음'으로만 표시",
        f"  · 해당 ADRG: {coverage.get('source_tables_without_ast', 0):,}",
        "",
        "[대표 사례]",
        "- E011: LT_E011_002는 기본 포함조건, LT_E011_003만 제외조건",
        "- 9610: LT_9610_001 기본 분류 TABLE 있음, 별도 추가 분기조건 없음",
        "- 9620: LT_9620_001 주진단 기본조건, LT_9620_002 시술은 제외조건",
        "",
        "[TABLE 역할 근거]",
        f"- AST 역할 근거가 있는 TABLE: {role['table_with_evidence_count']:,}",
        f"- 역할 근거가 없는 TABLE: {role['table_without_evidence_count']:,}",
    ]
    for category, count in sorted(role["category_counts"].items()):
        lines.append(f"- {category}: {count:,}")

    lines.extend(
        [
            "",
            "[현재 단계 결론]",
            "- PySide 전체 디자인 개편은 하지 않음",
            "- Electron 전환 전에 의미 오류와 표시 계약을 먼저 확정해야 함",
            "- 다음 단계: 48번 공통 UI 표현 계약 생성",
            "",
            "[생성 파일]",
            f"- {PROFILE_PATH.relative_to(ROOT)}",
            f"- {REPORT_JSON_PATH.relative_to(ROOT)}",
            f"- {REPORT_TXT_PATH.relative_to(ROOT)}",
            "",
            "전체 결과: PASS",
        ]
    )
    return lines


def main() -> int:
    try:
        input_hashes = require_files()
        data = load_json(DATA_PATH)
        profile = build_profile(data, input_hashes)
        write_json(PROFILE_PATH, profile)
        write_json(REPORT_JSON_PATH, profile)
        REPORT_TXT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_TXT_PATH.write_text("\n".join(report_lines(profile)) + "\n", encoding="utf-8")
        print("[PASS] KDRG UI 의미·TABLE 스키마 전수감사 완료")
        print(f"profile={PROFILE_PATH}")
        print(f"report={REPORT_TXT_PATH}")
        return 0
    except Exception as exc:
        print(f"[FAIL] KDRG UI 의미·TABLE 스키마 전수감사: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
