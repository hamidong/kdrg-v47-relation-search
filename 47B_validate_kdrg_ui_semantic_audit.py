from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_VERSION = "2026-07-27_KDRG_V47_UI_SEMANTIC_AUDIT_VALIDATOR_V1"
ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data" / "kdrg_v47_search_integrated.json"
PROFILE_PATH = ROOT / "data" / "kdrg_v47_ui_semantic_profile.json"
REPORT_JSON_PATH = ROOT / "reports" / "ui_semantic_audit_validation_report.json"
REPORT_TXT_PATH = ROOT / "reports" / "ui_semantic_audit_validation_report.txt"

EXPECTED_DATA_SHA256 = "3de5d6d95cd9cbd16e674f5a4cffcd8bf89da2ee70627501f56d81b05bbe8af1"
EXPECTED_PROFILE_SCHEMA = "kdrg-v47-ui-semantic-profile-v1"
EXPECTED_COUNTS = {
    "adrg_records": 1132,
    "logical_table_records": 1308,
    "condition_ast_records": 390,
    "code_records": 16571,
    "ast_node_count": 1727,
    "source_tables_without_ast": 706,
    "no_ast_no_source_table": 36,
    "ast_with_source_and_condition_tables": 172,
    "ast_with_condition_tables_only": 213,
    "ast_without_table_reference": 5,
    "exclusion_node_count": 64,
    "binary_exclusion_node_count": 64,
    "base_table_ref_occurrence_count": 28,
    "base_table_relation_count": 27,
    "excluded_table_ref_occurrence_count": 65,
    "unique_base_table_count": 21,
    "unique_excluded_table_count": 46,
    "exclusion_nodes_with_base_table": 20,
    "code_names_none": 16571,
    "code_roles_none": 16571,
    "table_scope_missing": 1308,
    "tables_all_names_missing": 1308,
    "tables_with_ast_role_evidence": 662,
    "tables_without_ast_role_evidence": 646,
    "diagnosis_evidence_tables": 186,
    "add_on_evidence_tables": 99,
    "procedure_evidence_tables": 369,
    "optional_semantic_tables": 4,
    "other_semantic_tables": 4,
}


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


def unique(values: list[Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return output


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
        stack.extend(str(value) for value in node.get("child_node_ids") or [])
    return output


def collect_table_ids(rows: list[dict[str, Any]]) -> list[str]:
    output: list[str] = []
    for row in rows:
        output.extend(unique(row.get("logical_table_ids") or []))
    return output


def role_category(role_set: set[str]) -> str:
    if role_set & {
        "principal_diagnosis",
        "diagnosis",
        "secondary_diagnosis",
        "principal_or_secondary_diagnosis",
    }:
        return "diagnosis"
    if "add_on_code" in role_set:
        return "add_on_code"
    if role_set & {"procedure", "text:procedure_count"}:
        return "procedure"
    if "text:optional_table_presence" in role_set:
        return "optional_semantic"
    if role_set:
        return "other_semantic"
    return "unknown"


class Checks:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def add(self, name: str, actual: Any, expected: Any) -> None:
        passed = actual == expected
        self.rows.append(
            {
                "name": name,
                "status": "PASS" if passed else "FAIL",
                "actual": actual,
                "expected": expected,
            }
        )

    @property
    def pass_count(self) -> int:
        return sum(row["status"] == "PASS" for row in self.rows)

    @property
    def fail_count(self) -> int:
        return sum(row["status"] == "FAIL" for row in self.rows)


def main() -> int:
    checks = Checks()
    try:
        checks.add("입력 JSON 존재", DATA_PATH.is_file(), True)
        checks.add("UI semantic profile 존재", PROFILE_PATH.is_file(), True)
        if not DATA_PATH.is_file() or not PROFILE_PATH.is_file():
            raise RuntimeError("필수 파일이 없습니다")

        data_hash = sha256_file(DATA_PATH)
        checks.add("입력 JSON SHA256", data_hash, EXPECTED_DATA_SHA256)
        data = load_json(DATA_PATH)
        profile = load_json(PROFILE_PATH)

        checks.add(
            "profile schema",
            str((profile.get("meta") or {}).get("schema_version") or ""),
            EXPECTED_PROFILE_SCHEMA,
        )
        checks.add(
            "profile source SHA256",
            str((profile.get("meta") or {}).get("source_sha256") or ""),
            EXPECTED_DATA_SHA256,
        )
        checks.add(
            "read only audit",
            bool((profile.get("meta") or {}).get("read_only_audit")),
            True,
        )

        adrgs = list(data.get("adrg_records") or [])
        tables = list(data.get("logical_table_records") or [])
        asts = list(data.get("condition_ast_records") or [])
        codes = list(data.get("code_records") or [])
        ast_by_adrg = {str(row.get("adrg") or ""): row for row in asts}
        adrg_by_code = {str(row.get("adrg") or ""): row for row in adrgs}

        actual_basic = {
            "adrg_records": len(adrgs),
            "logical_table_records": len(tables),
            "condition_ast_records": len(asts),
            "code_records": len(codes),
            "ast_node_count": sum(len(row.get("nodes") or []) for row in asts),
        }
        for key, actual in actual_basic.items():
            checks.add(key, actual, EXPECTED_COUNTS[key])
            checks.add(
                f"profile {key}",
                (profile.get("source_counts") or {}).get(key),
                EXPECTED_COUNTS[key],
            )

        coverage = Counter()
        for row in adrgs:
            adrg = str(row.get("adrg") or "")
            has_ast = adrg in ast_by_adrg
            has_source = bool(row.get("source_logical_table_ids") or [])
            has_condition = bool(row.get("condition_logical_table_ids") or [])
            if has_ast and has_source and has_condition:
                key = "ast_with_source_and_condition_tables"
            elif has_ast and (not has_source) and has_condition:
                key = "ast_with_condition_tables_only"
            elif has_ast and (not has_source) and (not has_condition):
                key = "ast_without_table_reference"
            elif (not has_ast) and has_source:
                key = "source_tables_without_ast"
            else:
                key = "no_ast_no_source_table"
            coverage[key] += 1

        profile_coverage = (profile.get("condition_coverage") or {}).get("counts") or {}
        for key in (
            "source_tables_without_ast",
            "no_ast_no_source_table",
            "ast_with_source_and_condition_tables",
            "ast_with_condition_tables_only",
            "ast_without_table_reference",
        ):
            checks.add(key, coverage[key], EXPECTED_COUNTS[key])
            checks.add(f"profile {key}", profile_coverage.get(key), EXPECTED_COUNTS[key])

        exclusion_nodes = 0
        binary_nodes = 0
        nodes_with_base = 0
        base_occurrences: list[str] = []
        base_relation_count = 0
        excluded_occurrences: list[str] = []
        exclusion_map: dict[str, list[tuple[list[str], list[str]]]] = defaultdict(list)
        role_evidence: dict[str, set[str]] = defaultdict(set)

        for ast in asts:
            adrg = str(ast.get("adrg") or "")
            nodes = {
                str(node.get("node_id") or ""): node
                for node in ast.get("nodes") or []
                if str(node.get("node_id") or "")
            }
            for node in ast.get("nodes") or []:
                table_ids = unique(node.get("logical_table_ids") or [])
                if table_ids:
                    node_type = str(node.get("node_type") or "")
                    if node_type == "TABLE_REF":
                        role = str(node.get("table_role") or "unknown")
                    elif node_type == "TEXT_CONDITION":
                        role = f"text:{node.get('semantic_type') or 'unknown'}"
                    else:
                        role = node_type.casefold() or "unknown"
                    for table_id in table_ids:
                        role_evidence[table_id].add(role)

                if str(node.get("node_type") or "") != "EXCLUSION":
                    continue
                exclusion_nodes += 1
                child_ids = [str(value) for value in node.get("child_node_ids") or []]
                if len(child_ids) == 2:
                    binary_nodes += 1
                base_ids = (
                    collect_table_ids(descendants(child_ids[0], nodes)) if child_ids else []
                )
                excluded_ids = (
                    collect_table_ids(descendants(child_ids[1], nodes))
                    if len(child_ids) >= 2
                    else []
                )
                if base_ids:
                    nodes_with_base += 1
                base_occurrences.extend(base_ids)
                base_relation_count += len(set(base_ids))
                excluded_occurrences.extend(excluded_ids)
                exclusion_map[adrg].append((base_ids, excluded_ids))

        role_categories = Counter(role_category(values) for values in role_evidence.values())
        profile_exclusion = (profile.get("exclusion_semantics") or {}).get("counts") or {}
        recomputed_exclusion = {
            "exclusion_node_count": exclusion_nodes,
            "binary_exclusion_node_count": binary_nodes,
            "base_table_ref_occurrence_count": len(base_occurrences),
            "base_table_relation_count": base_relation_count,
            "excluded_table_ref_occurrence_count": len(excluded_occurrences),
            "unique_base_table_count": len(set(base_occurrences)),
            "unique_excluded_table_count": len(set(excluded_occurrences)),
            "exclusion_nodes_with_base_table": nodes_with_base,
        }
        profile_key_map = {
            "exclusion_node_count": "node_count",
            "binary_exclusion_node_count": "binary_node_count",
            "base_table_ref_occurrence_count": "base_table_ref_occurrence_count",
            "base_table_relation_count": "base_table_relation_count",
            "excluded_table_ref_occurrence_count": "excluded_table_ref_occurrence_count",
            "unique_base_table_count": "unique_base_table_count",
            "unique_excluded_table_count": "unique_excluded_table_count",
            "exclusion_nodes_with_base_table": "nodes_with_base_table",
        }
        for key, actual in recomputed_exclusion.items():
            checks.add(key, actual, EXPECTED_COUNTS[key])
            checks.add(
                f"profile {key}",
                profile_exclusion.get(profile_key_map[key]),
                EXPECTED_COUNTS[key],
            )

        code_names_none = sum(not unique(row.get("names") or []) for row in codes)
        code_roles_none = sum(not unique(row.get("roles") or []) for row in codes)
        table_scope_missing = sum(not str(row.get("logical_table_scope") or "").strip() for row in tables)
        code_by_code = {str(row.get("code") or ""): row for row in codes}
        tables_all_names_missing = sum(
            all(not unique((code_by_code.get(code) or {}).get("names") or []) for code in unique(row.get("codes") or []))
            for row in tables
        )

        checks.add("code names none", code_names_none, EXPECTED_COUNTS["code_names_none"])
        checks.add("code roles none", code_roles_none, EXPECTED_COUNTS["code_roles_none"])
        checks.add("table scope missing", table_scope_missing, EXPECTED_COUNTS["table_scope_missing"])
        checks.add(
            "tables all names missing",
            tables_all_names_missing,
            EXPECTED_COUNTS["tables_all_names_missing"],
        )
        checks.add(
            "tables with AST role evidence",
            len(role_evidence),
            EXPECTED_COUNTS["tables_with_ast_role_evidence"],
        )
        checks.add(
            "tables without AST role evidence",
            len(tables) - len(role_evidence),
            EXPECTED_COUNTS["tables_without_ast_role_evidence"],
        )
        checks.add(
            "diagnosis evidence tables",
            role_categories["diagnosis"],
            EXPECTED_COUNTS["diagnosis_evidence_tables"],
        )
        checks.add(
            "add on evidence tables",
            role_categories["add_on_code"],
            EXPECTED_COUNTS["add_on_evidence_tables"],
        )
        checks.add(
            "procedure evidence tables",
            role_categories["procedure"],
            EXPECTED_COUNTS["procedure_evidence_tables"],
        )
        checks.add(
            "optional semantic tables",
            role_categories["optional_semantic"],
            EXPECTED_COUNTS["optional_semantic_tables"],
        )
        checks.add(
            "other semantic tables",
            role_categories["other_semantic"],
            EXPECTED_COUNTS["other_semantic_tables"],
        )

        table_profile = profile.get("table_display_schema") or {}
        profile_role = table_profile.get("ast_role_evidence") or {}
        checks.add(
            "profile code names none",
            (table_profile.get("code_name_counts") or {}).get("none"),
            EXPECTED_COUNTS["code_names_none"],
        )
        checks.add(
            "profile code roles none",
            (table_profile.get("code_role_counts") or {}).get("without_roles"),
            EXPECTED_COUNTS["code_roles_none"],
        )
        checks.add(
            "profile table scope missing",
            (table_profile.get("scope_counts") or {}).get("missing_scope"),
            EXPECTED_COUNTS["table_scope_missing"],
        )
        checks.add(
            "profile tables all names missing",
            (table_profile.get("table_name_coverage_counts") or {}).get("all_names_missing"),
            EXPECTED_COUNTS["tables_all_names_missing"],
        )
        checks.add(
            "profile role evidence table count",
            profile_role.get("table_with_evidence_count"),
            EXPECTED_COUNTS["tables_with_ast_role_evidence"],
        )
        checks.add(
            "profile role unknown table count",
            profile_role.get("table_without_evidence_count"),
            EXPECTED_COUNTS["tables_without_ast_role_evidence"],
        )

        checks.add(
            "E011 base TABLE",
            exclusion_map.get("E011", [([], [])])[0][0],
            ["LT_E011_002"],
        )
        checks.add(
            "E011 excluded TABLE",
            exclusion_map.get("E011", [([], [])])[0][1],
            ["LT_E011_003"],
        )
        checks.add(
            "9620 base TABLE",
            exclusion_map.get("9620", [([], [])])[0][0],
            ["LT_9620_001"],
        )
        checks.add(
            "9620 excluded TABLE",
            exclusion_map.get("9620", [([], [])])[0][1],
            ["LT_9620_002"],
        )
        checks.add(
            "9610 source TABLE",
            list((adrg_by_code.get("9610") or {}).get("source_logical_table_ids") or []),
            ["LT_9610_001"],
        )
        checks.add(
            "9610 AST 없음",
            (adrg_by_code.get("9610") or {}).get("condition_ast_id"),
            None,
        )

        issue_ids = [str(row.get("issue_id") or "") for row in profile.get("issue_register") or []]
        checks.add(
            "필수 issue register",
            issue_ids,
            ["UI-SEM-001", "UI-SEM-002", "UI-SEM-003", "UI-SEM-004", "UI-SEM-005"],
        )
        source_patterns = profile.get("current_ui_source_patterns") or {}
        for key in (
            "search_service_exclusion_ancestor_collapse",
            "runtime_unknown_type_defaults_to_procedure",
            "runtime_no_ast_technical_copy",
            "ui_hardcoded_three_columns",
            "ui_hardcoded_three_column_note",
        ):
            checks.add(f"source pattern {key}", source_patterns.get(key), True)

    except Exception as exc:
        checks.rows.append(
            {
                "name": "validator exception",
                "status": "FAIL",
                "actual": f"{type(exc).__name__}: {exc}",
                "expected": "no exception",
            }
        )

    report = {
        "meta": {
            "script_version": SCRIPT_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "checks": checks.rows,
        "summary": {
            "pass_count": checks.pass_count,
            "fail_count": checks.fail_count,
            "total_count": len(checks.rows),
            "status": "PASS" if checks.fail_count == 0 else "FAIL",
        },
    }
    write_json(REPORT_JSON_PATH, report)

    lines = [
        "KDRG V4.7 UI 의미·TABLE 스키마 전수감사 독립검증",
        "=" * 78,
        f"스크립트 버전: {SCRIPT_VERSION}",
        "",
        "[검증 항목]",
    ]
    for row in checks.rows:
        lines.append(
            f"- [{row['status']}] {row['name']} | actual={row['actual']} | expected={row['expected']}"
        )
    lines.extend(
        [
            "",
            "[최종 결과]",
            f"PASS: {checks.pass_count}",
            f"FAIL: {checks.fail_count}",
            f"TOTAL: {len(checks.rows)}",
            f"전체 결과: {'PASS' if checks.fail_count == 0 else 'FAIL'}",
        ]
    )
    REPORT_TXT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_TXT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if checks.fail_count:
        print(
            f"[FAIL] KDRG UI 의미·TABLE 스키마 전수감사 독립검증: "
            f"{checks.pass_count} PASS / {checks.fail_count} FAIL"
        )
        print(f"report={REPORT_TXT_PATH}")
        return 1

    print(
        f"[PASS] KDRG UI 의미·TABLE 스키마 전수감사 독립검증: "
        f"{checks.pass_count} PASS / 0 FAIL"
    )
    print(f"report={REPORT_TXT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
