#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KDRG V4.7 최종 검색용 통합 JSON 구축 V2.

repaired TABLE·조건 AST·질병군·A/B/C 기준축을 검색 전용 데이터로 결합한다.
V2는 TABLE의 물리 정의 위치(source ADRG)와 실제 조건식 사용 ADRG를 분리하며,
3자리 family source ref를 ADRG 코드로 잘못 노출하지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import traceback
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCRIPT_VERSION = "2026-07-23_KDRG_V47_SEARCH_INTEGRATED_JSON_BUILDER_V2"
SCHEMA_VERSION = "kdrg-v47-search-integrated-v2"
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
REPORT_DIR = ROOT / "reports"

GROUP_PATH = DATA_DIR / "kdrg_v47_group_name_base.json"
MAIN_PATH = DATA_DIR / "kdrg_v47_main_page_blocks.json"
LOGICAL_PATH = DATA_DIR / "kdrg_v47_logical_tables_repaired_current.json"
AST_PATH = DATA_DIR / "kdrg_v47_condition_ast_repaired_current.json"
ABC_PATH = DATA_DIR / "kdrg_v47_abc_classification_base.json"
TECH_PATH = DATA_DIR / "kdrg_v47_remaining_technical_review_pattern_analysis.json"
OUTPUT_PATH = DATA_DIR / "kdrg_v47_search_integrated.json"
REPORT_TXT_PATH = REPORT_DIR / "search_integrated_build_report.txt"
REPORT_JSON_PATH = REPORT_DIR / "search_integrated_build_report.json"

EXPECTED = {
    "adrg_records": 1132,
    "aadrg_records": 1233,
    "rdrg_records": 2699,
    "logical_table_records": 1308,
    "condition_ast_records": 390,
    "ast_node_count": 1727,
    "table_code_rows": 42882,
    "unique_search_codes": 16571,
    "abc_exact_mappings": 1212,
    "abc_unclassified_aadrgs": 21,
    "search_token_count": 19478,
    "raw_table_owner_ref_count": 1308,
    "exact_source_adrg_ref_count": 1307,
    "family_source_adrg_ref_count": 1,
    "unresolved_source_adrg_ref_count": 0,
    "tables_with_condition_adrgs": 662,
    "tables_with_runtime_relation_expansion": 417,
    "table_related_adrg_relation_count": 1856,
    "codes_with_runtime_relation_expansion": 9122,
    "code_related_adrg_relation_count": 90191,
    "code_related_aadrg_relation_count": 100321,
}
EXPECTED_FAMILY_REFS = {"X04"}

RUNTIME_RULES = {
    "allowed_exception_under_negated_or_procedure": "필수 시술이 아니라 OR procedure 판정의 허용 예외",
    "optional_companion_table": "시행 여부 무관이며 필수조건에서 제외",
    "main_pdf_source_only_diagnosis_code": "본문 TABLE 코드를 유지하고 부록 관계 미수록 provenance 표시",
}


class BuildError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def json_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise BuildError(f"필수 파일이 없음: {path}")
    with path.open("r", encoding="utf-8") as f:
        value = json.load(f)
    if not isinstance(value, dict):
        raise BuildError(f"최상위 JSON 객체가 아님: {path}")
    return value


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent) as tmp:
        json.dump(value, tmp, ensure_ascii=False, indent=2)
        tmp.write("\n")
        name = tmp.name
    os.replace(name, path)


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent) as tmp:
        tmp.write(text)
        name = tmp.name
    os.replace(name, path)


def norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().upper())


def first(row: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return default


def raw_table_owner_refs(table: dict[str, Any]) -> list[str]:
    values: set[str] = set()
    for key in ("source_adrg", "adrg", "owner_adrg"):
        value = table.get(key)
        if isinstance(value, str) and value:
            values.add(value)
    for key in ("source_adrgs", "adrgs", "linked_adrgs", "condition_adrgs"):
        value = table.get(key)
        if isinstance(value, list):
            values.update(str(x) for x in value if x)
    return sorted(values)


def table_code_rows(table: dict[str, Any]) -> list[dict[str, Any]]:
    rows = table.get("codes") or []
    return [row for row in rows if isinstance(row, dict)]


def row_code(row: dict[str, Any]) -> str:
    return norm(first(row, "code", "value", "code_value", "normalized_code", default=""))


def ast_nodes(ast: dict[str, Any]) -> list[dict[str, Any]]:
    """AST의 실제 node 배열만 반환한다. provenance/reference dict는 node로 세지 않는다."""
    value = ast.get("nodes") or []
    return [node for node in value if isinstance(node, dict)]


def resolve_source_refs(
    raw_refs: list[str],
    valid_adrgs: set[str],
    condition_adrgs: set[str],
) -> tuple[list[str], list[str], list[dict[str, Any]], list[str]]:
    exact: set[str] = set()
    families: set[str] = set()
    unresolved: set[str] = set()
    details: list[dict[str, Any]] = []

    for ref in raw_refs:
        if ref in valid_adrgs:
            exact.add(ref)
            details.append({
                "source_ref": ref,
                "status": "EXACT_ADRG",
                "resolved_adrgs": [ref],
                "evidence": "group_name_base_exact_code",
            })
            continue

        candidates = sorted(code for code in valid_adrgs if code.startswith(ref))
        linked = sorted(code for code in condition_adrgs if code in candidates)
        if candidates and linked and set(condition_adrgs).issubset(candidates):
            families.add(ref)
            details.append({
                "source_ref": ref,
                "status": "FAMILY_PREFIX_RESOLVED_BY_AST",
                "candidate_adrgs": candidates,
                "resolved_adrgs": linked,
                "evidence": "condition_ast_reference",
            })
        else:
            unresolved.add(ref)
            details.append({
                "source_ref": ref,
                "status": "UNRESOLVED_SOURCE_REF",
                "candidate_adrgs": candidates,
                "condition_adrgs": sorted(condition_adrgs),
                "resolved_adrgs": [],
            })

    return sorted(exact), sorted(families), details, sorted(unresolved)


def build() -> tuple[dict[str, Any], dict[str, Any]]:
    group = load_json(GROUP_PATH)
    main = load_json(MAIN_PATH)
    logical = load_json(LOGICAL_PATH)
    ast_payload = load_json(AST_PATH)
    abc = load_json(ABC_PATH)
    tech = load_json(TECH_PATH) if TECH_PATH.exists() else {}

    source_paths = [GROUP_PATH, MAIN_PATH, LOGICAL_PATH, AST_PATH, ABC_PATH]
    if TECH_PATH.exists():
        source_paths.append(TECH_PATH)
    hashes = {path.stem: sha256_file(path) for path in source_paths}

    adrgs = group.get("adrgs") or []
    aadrgs = group.get("aadrgs") or []
    rdrgs = group.get("rdrgs") or []
    catalog = main.get("adrg_catalog") or []
    blocks = main.get("adrg_blocks") or []
    tables = logical.get("logical_tables") or []
    asts = ast_payload.get("condition_asts") or []

    adrg_base = {str(first(x, "code", "adrg")): x for x in adrgs}
    aadrg_base = {str(first(x, "code", "aadrg")): x for x in aadrgs}
    rdrg_base = {str(first(x, "code", "rdrg")): x for x in rdrgs}
    valid_adrgs = set(adrg_base)
    catalog_map = {str(x.get("adrg")): x for x in catalog}
    block_map = {str(x.get("adrg")): x for x in blocks}
    abc_map = dict((abc.get("indexes") or {}).get("aadrg_to_mapping") or {})
    abc_unclassified = {str(x.get("aadrg")): x for x in abc.get("current_unclassified_aadrgs") or []}
    table_map = {str(x.get("logical_table_id") or ""): x for x in tables}

    # 실제 AST node 배열만 사용해 TABLE 사용 관계를 재구성한다.
    ast_to_tables: dict[str, set[str]] = defaultdict(set)
    table_to_ast_ids: dict[str, set[str]] = defaultdict(set)
    table_to_condition_adrgs: dict[str, set[str]] = defaultdict(set)
    adrg_to_ast: dict[str, str] = {}
    runtime_semantics: Counter[str] = Counter()
    ast_node_count = 0
    for ast in asts:
        ast_id = str(ast.get("condition_ast_id") or "")
        adrg = str(first(ast, "adrg", "source_adrg", default=""))
        if adrg:
            adrg_to_ast[adrg] = ast_id
        nodes = ast_nodes(ast)
        ast_node_count += len(nodes)
        for node in nodes:
            tids = node.get("logical_table_ids") or []
            if isinstance(tids, list):
                for tid_value in tids:
                    tid = str(tid_value or "")
                    if not tid:
                        continue
                    ast_to_tables[ast_id].add(tid)
                    table_to_ast_ids[tid].add(ast_id)
                    if adrg in valid_adrgs:
                        table_to_condition_adrgs[tid].add(adrg)
            semantic = str(node.get("text_semantic_type") or node.get("semantic_type") or "")
            if semantic:
                runtime_semantics[semantic] += 1

    # TABLE별 물리 source와 AST 조건 사용 ADRG를 분리한다.
    table_runtime: dict[str, dict[str, Any]] = {}
    adrg_to_source_tables: dict[str, set[str]] = defaultdict(set)
    adrg_to_condition_tables: dict[str, set[str]] = defaultdict(set)
    adrg_to_related_tables: dict[str, set[str]] = defaultdict(set)
    family_refs: set[str] = set()
    unresolved_refs: set[str] = set()

    for table in tables:
        tid = str(table.get("logical_table_id") or "")
        raw_refs = raw_table_owner_refs(table)
        condition_adrgs = set(table_to_condition_adrgs.get(tid, set()))
        source_adrgs, source_families, resolution, unresolved = resolve_source_refs(
            raw_refs, valid_adrgs, condition_adrgs
        )
        related_adrgs = sorted(set(source_adrgs) | condition_adrgs)
        family_refs.update(source_families)
        unresolved_refs.update(unresolved)
        table_runtime[tid] = {
            "source_adrg_refs": raw_refs,
            "source_adrgs": source_adrgs,
            "source_adrg_families": source_families,
            "condition_adrgs": sorted(condition_adrgs),
            "related_adrgs": related_adrgs,
            "source_adrg_resolution": resolution,
            "unresolved_source_adrg_refs": unresolved,
        }
        for adrg in source_adrgs:
            adrg_to_source_tables[adrg].add(tid)
        for adrg in condition_adrgs:
            adrg_to_condition_tables[adrg].add(tid)
        for adrg in related_adrgs:
            adrg_to_related_tables[adrg].add(tid)

    # TABLE 코드 index
    code_to_tables: dict[str, set[str]] = defaultdict(set)
    table_to_codes: dict[str, list[str]] = {}
    code_names: dict[str, set[str]] = defaultdict(set)
    code_roles: dict[str, set[str]] = defaultdict(set)
    for table in tables:
        tid = str(table.get("logical_table_id") or "")
        codes: set[str] = set()
        for row in table_code_rows(table):
            code = row_code(row)
            if not code:
                continue
            codes.add(code)
            code_to_tables[code].add(tid)
            name = first(row, "name", "code_name", "description", "label", default="")
            if name:
                code_names[code].add(str(name).strip())
            role = first(row, "code_type", "role", "namespace", default=table.get("logical_table_scope") or "")
            if role:
                code_roles[code].add(str(role))
        table_to_codes[tid] = sorted(codes)

    # AADRG
    aadrg_records: list[dict[str, Any]] = []
    adrg_to_aadrgs: dict[str, list[str]] = defaultdict(list)
    for code in sorted(aadrg_base):
        row = aadrg_base[code]
        adrg = str(row.get("adrg") or code[:4])
        adrg_to_aadrgs[adrg].append(code)
        mapping = abc_map.get(code)
        aadrg_records.append({
            "aadrg": code,
            "adrg": adrg,
            "mdc": (catalog_map.get(adrg) or {}).get("mdc"),
            "group_name": row.get("group_name"),
            "rdrg_codes": sorted(set(row.get("rdrg_codes") or [])),
            "abc_status": "EXACT_OFFICIAL" if mapping else "UNCLASSIFIED_EXACT_NOT_IN_OFFICIAL_PDF",
            "classification_code": mapping.get("classification_code") if mapping else None,
            "classification_name": mapping.get("classification_name") if mapping else None,
            "classification_display_label": mapping.get("display_label") if mapping else None,
            "abc_source_ref": mapping.get("source_ref") if mapping else None,
            "abc_unclassified_provenance": abc_unclassified.get(code),
        })

    # ADRG
    adrg_records: list[dict[str, Any]] = []
    for adrg in sorted(adrg_base):
        base = adrg_base[adrg]
        cat = catalog_map.get(adrg) or {}
        block = block_map.get(adrg) or {}
        children = sorted(adrg_to_aadrgs.get(adrg) or base.get("aadrg_codes") or [])
        classes = [abc_map[x]["classification_code"] for x in children if x in abc_map]
        labels = sorted({abc_map[x]["display_label"] for x in children if x in abc_map})
        source_tids = sorted(adrg_to_source_tables.get(adrg, set()))
        condition_tids = sorted(adrg_to_condition_tables.get(adrg, set()))
        related_tids = sorted(adrg_to_related_tables.get(adrg, set()))
        adrg_records.append({
            "adrg": adrg,
            "mdc": cat.get("mdc"),
            "adrg_name": first(cat, "adrg_name", "group_name", "name", default=base.get("display_name")),
            "aadrg_codes": children,
            "aadrg_count": len(children),
            "abc_classification_codes": sorted(set(classes)),
            "abc_display_labels": labels,
            "abc_status": "MIXED_BY_AADRG" if len(set(classes)) > 1 else ("SINGLE" if classes else "UNCLASSIFIED"),
            "source_logical_table_ids": source_tids,
            "condition_logical_table_ids": condition_tids,
            "logical_table_ids": related_tids,
            "condition_ast_id": adrg_to_ast.get(adrg),
            "source_block": {
                "pdf_page_start": first(block, "pdf_page_start", "start_pdf_page"),
                "pdf_page_end": first(block, "pdf_page_end", "end_pdf_page"),
                "printed_page_start": first(block, "printed_page_start", "start_printed_page"),
                "printed_page_end": first(block, "printed_page_end", "end_printed_page"),
            },
        })

    # TABLE
    table_records: list[dict[str, Any]] = []
    for table in sorted(tables, key=lambda x: str(x.get("logical_table_id") or "")):
        tid = str(table.get("logical_table_id") or "")
        runtime = table_runtime[tid]
        table_records.append({
            "logical_table_id": tid,
            "display_name": first(table, "display_name", "table_name", "name", "canonical_label", default=tid),
            "logical_table_type": table.get("logical_table_type"),
            "logical_table_scope": table.get("logical_table_scope"),
            **runtime,
            "code_count": len(table_to_codes.get(tid, [])),
            "codes": table_to_codes.get(tid, []),
            "condition_ast_ids": sorted(table_to_ast_ids.get(tid, set())),
            "source_refs": table.get("source_refs") or table.get("source_ref") or [],
            "parser_repair_history": table.get("parser_repair_history") or [],
        })

    # 코드
    code_records: list[dict[str, Any]] = []
    codes_with_expansion = 0
    for code in sorted(code_to_tables):
        tids = sorted(code_to_tables[code])
        source_adrgs = sorted({adrg for tid in tids for adrg in table_runtime[tid]["source_adrgs"]})
        condition_adrgs = sorted({adrg for tid in tids for adrg in table_runtime[tid]["condition_adrgs"]})
        related_adrgs = sorted(set(source_adrgs) | set(condition_adrgs))
        families = sorted({ref for tid in tids for ref in table_runtime[tid]["source_adrg_families"]})
        source_aadrgs = sorted({a for adrg in source_adrgs for a in adrg_to_aadrgs.get(adrg, [])})
        condition_aadrgs = sorted({a for adrg in condition_adrgs for a in adrg_to_aadrgs.get(adrg, [])})
        related_aadrgs = sorted(set(source_aadrgs) | set(condition_aadrgs))
        if set(condition_adrgs) - set(source_adrgs):
            codes_with_expansion += 1
        code_records.append({
            "code": code,
            "names": sorted(code_names.get(code, set())),
            "roles": sorted(code_roles.get(code, set())),
            "logical_table_ids": tids,
            "source_adrgs": source_adrgs,
            "condition_adrgs": condition_adrgs,
            "related_adrgs": related_adrgs,
            "source_adrg_families": families,
            "source_aadrgs": source_aadrgs,
            "condition_aadrgs": condition_aadrgs,
            "related_aadrgs": related_aadrgs,
        })

    # 검색 token
    token_to_entities: dict[str, set[str]] = defaultdict(set)

    def add_tokens(entity_id: str, values: Iterable[Any]) -> None:
        for value in values:
            for token in re.findall(r"[0-9A-Z가-힣]+", norm(value)):
                if len(token) >= 2:
                    token_to_entities[token].add(entity_id)

    for row in adrg_records:
        add_tokens(f"ADRG:{row['adrg']}", [row["adrg"], row.get("adrg_name")])
    for row in aadrg_records:
        add_tokens(f"AADRG:{row['aadrg']}", [row["aadrg"], row.get("group_name"), row.get("classification_display_label")])
    for row in table_records:
        add_tokens(f"TABLE:{row['logical_table_id']}", [row["logical_table_id"], row.get("display_name")])
    for row in code_records:
        add_tokens(f"CODE:{row['code']}", [row["code"], *row.get("names", [])])

    raw_ref_count = sum(len(row["source_adrg_refs"]) for row in table_runtime.values())
    exact_ref_count = sum(len(row["source_adrgs"]) for row in table_runtime.values())
    family_ref_count = sum(len(row["source_adrg_families"]) for row in table_runtime.values())
    unresolved_ref_count = sum(len(row["unresolved_source_adrg_refs"]) for row in table_runtime.values())
    expansion_table_count = sum(
        bool(set(row["condition_adrgs"]) - set(row["source_adrgs"]))
        for row in table_runtime.values()
    )

    counts = {
        "adrg_records": len(adrg_records),
        "aadrg_records": len(aadrg_records),
        "rdrg_records": len(rdrg_base),
        "logical_table_records": len(table_records),
        "condition_ast_records": len(asts),
        "ast_node_count": ast_node_count,
        "table_code_rows": sum(len(table_code_rows(x)) for x in tables),
        "unique_search_codes": len(code_records),
        "abc_exact_mappings": len(abc_map),
        "abc_unclassified_aadrgs": len(abc_unclassified),
        "search_token_count": len(token_to_entities),
        "raw_table_owner_ref_count": raw_ref_count,
        "exact_source_adrg_ref_count": exact_ref_count,
        "family_source_adrg_ref_count": family_ref_count,
        "unresolved_source_adrg_ref_count": unresolved_ref_count,
        "tables_with_condition_adrgs": sum(bool(row["condition_adrgs"]) for row in table_runtime.values()),
        "tables_with_runtime_relation_expansion": expansion_table_count,
        "table_related_adrg_relation_count": sum(len(row["related_adrgs"]) for row in table_runtime.values()),
        "codes_with_runtime_relation_expansion": codes_with_expansion,
        "code_related_adrg_relation_count": sum(len(row["related_adrgs"]) for row in code_records),
        "code_related_aadrg_relation_count": sum(len(row["related_aadrgs"]) for row in code_records),
    }

    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, actual: Any, expected: Any) -> None:
        checks.append({"name": name, "status": "PASS" if ok else "FAIL", "actual": actual, "expected": expected})

    for key, expected in EXPECTED.items():
        check(f"고정 집계 {key}", counts.get(key) == expected, counts.get(key), expected)
    check("ADRG ID 고유", len(adrg_base) == len(adrgs), len(adrg_base), len(adrgs))
    check("AADRG ID 고유", len(aadrg_base) == len(aadrgs), len(aadrg_base), len(aadrgs))
    check("RDRG ID 고유", len(rdrg_base) == len(rdrgs), len(rdrg_base), len(rdrgs))
    check("TABLE ID 고유", len(table_map) == len(tables), len(table_map), len(tables))
    check("AADRG parent ADRG 전부 존재", all(row["adrg"] in valid_adrgs for row in aadrg_records), sum(row["adrg"] not in valid_adrgs for row in aadrg_records), 0)
    check("AST TABLE ref 전부 존재", all(tid in table_map for tids in ast_to_tables.values() for tid in tids), sum(tid not in table_map for tids in ast_to_tables.values() for tid in tids), 0)
    check("runtime 관련 ADRG 전부 등록", all(adrg in valid_adrgs for row in table_runtime.values() for adrg in row["related_adrgs"]), 0, 0)
    check("source family ref 집합", family_refs == EXPECTED_FAMILY_REFS, sorted(family_refs), sorted(EXPECTED_FAMILY_REFS))
    check("source ref 미해석 없음", not unresolved_refs, sorted(unresolved_refs), [])
    check("X04 family AST 근거", table_runtime.get("LT_X04_PRINCIPAL_DIAGNOSIS_TABLE01", {}).get("condition_adrgs") == ["X041", "X042"], table_runtime.get("LT_X04_PRINCIPAL_DIAGNOSIS_TABLE01", {}).get("condition_adrgs"), ["X041", "X042"])
    check("코드 runtime ADRG 미등록 없음", all(adrg in valid_adrgs for row in code_records for adrg in row["related_adrgs"]), 0, 0)
    check("A/B/C exact AADRG 전부 존재", all(code in aadrg_base for code in abc_map), sum(code not in aadrg_base for code in abc_map), 0)
    check("A/B/C exact·미분류 완전 분할", set(abc_map).isdisjoint(abc_unclassified) and set(abc_map) | set(abc_unclassified) == set(aadrg_base), len(set(abc_map) | set(abc_unclassified)), len(aadrg_base))
    check("technical unresolved zero", int((tech.get("summary") or tech.get("meta", {}).get("counts") or {}).get("unresolved", 0)) == 0, int((tech.get("summary") or tech.get("meta", {}).get("counts") or {}).get("unresolved", 0)), 0)
    check("token index nonempty", bool(token_to_entities), len(token_to_entities), ">0")

    fail_count = sum(item["status"] == "FAIL" for item in checks)
    pass_count = len(checks) - fail_count
    generated_at = now_iso()

    output = {
        "meta": {
            "schema_version": SCHEMA_VERSION,
            "script_version": SCRIPT_VERSION,
            "data_version": "KDRG V4.7",
            "generated_at": generated_at,
            "state": "search_ready_integrated_base_v2",
            "source_hashes": hashes,
            "counts": counts,
            "policies": {
                "abc_exact_match_only": True,
                "abc_inference_mapping": False,
                "repaired_current_only": True,
                "source_provenance_preserved": True,
                "runtime_semantics_preserved": True,
                "physical_source_and_condition_usage_separated": True,
                "family_source_ref_never_exposed_as_adrg": True,
            },
        },
        "adrg_records": adrg_records,
        "aadrg_records": aadrg_records,
        "rdrg_records": [rdrg_base[x] for x in sorted(rdrg_base)],
        "logical_table_records": table_records,
        "condition_ast_records": asts,
        "code_records": code_records,
        "runtime_semantic_rules": RUNTIME_RULES,
        "indexes": {
            "adrg_to_record_index": {row["adrg"]: i for i, row in enumerate(adrg_records)},
            "aadrg_to_record_index": {row["aadrg"]: i for i, row in enumerate(aadrg_records)},
            "rdrg_to_record_index": {str(first(row, "rdrg", "code")): i for i, row in enumerate([rdrg_base[x] for x in sorted(rdrg_base)])},
            "logical_table_id_to_record_index": {row["logical_table_id"]: i for i, row in enumerate(table_records)},
            "code_to_record_index": {row["code"]: i for i, row in enumerate(code_records)},
            "adrg_to_aadrgs": {key: sorted(value) for key, value in sorted(adrg_to_aadrgs.items())},
            "adrg_to_source_logical_table_ids": {key: sorted(value) for key, value in sorted(adrg_to_source_tables.items())},
            "adrg_to_condition_logical_table_ids": {key: sorted(value) for key, value in sorted(adrg_to_condition_tables.items())},
            "adrg_to_logical_table_ids": {key: sorted(value) for key, value in sorted(adrg_to_related_tables.items())},
            "adrg_to_condition_ast_id": dict(sorted(adrg_to_ast.items())),
            "code_to_logical_table_ids": {key: sorted(value) for key, value in sorted(code_to_tables.items())},
            "token_to_entity_ids": {key: sorted(value) for key, value in sorted(token_to_entities.items())},
        },
        "validation": {
            "status": "PASS" if fail_count == 0 else "FAIL",
            "pass_count": pass_count,
            "fail_count": fail_count,
            "checks": checks,
            "user_judgment_required": 0,
            "manual_excel_review": False,
        },
    }
    report = {
        "script_version": SCRIPT_VERSION,
        "generated_at": generated_at,
        "source_hashes": hashes,
        "counts": counts,
        "owner_relation_audit": {
            "family_source_refs": sorted(family_refs),
            "unresolved_source_refs": sorted(unresolved_refs),
            "family_resolution_table_ids": sorted(
                tid for tid, row in table_runtime.items() if row["source_adrg_families"]
            ),
            "runtime_expansion_table_ids": sorted(
                tid for tid, row in table_runtime.items()
                if set(row["condition_adrgs"]) - set(row["source_adrgs"])
            ),
        },
        "runtime_semantic_counts": dict(sorted(runtime_semantics.items())),
        "output_content_sha256": json_hash({key: output[key] for key in output if key != "validation"}),
        "validation": output["validation"],
    }
    return output, report


def render(report: dict[str, Any]) -> str:
    c = report["counts"]
    v = report["validation"]
    lines = [
        "KDRG V4.7 최종 검색용 통합 JSON V2 구축 결과",
        "=" * 72,
        f"생성시각: {report['generated_at']}",
        f"스크립트 버전: {SCRIPT_VERSION}",
        "",
        "[현재 진행 위치]",
        "데이터 기준축 구축·검증 완료 후 검색 runtime 관계를 통합하는 단계",
        "TABLE 물리 정의 ADRG와 조건 AST 사용 ADRG를 전체 corpus에서 분리함",
        "기존 원천 JSON은 수정하지 않고 통합 JSON만 전면 재생성함",
        "",
        "[문제 원인과 전체 영향]",
        "기존 V1은 TABLE의 source_adrg를 runtime 관련 ADRG로 그대로 사용함",
        "공유 TABLE은 다른 ADRG AST에서도 참조되므로 물리 위치와 조건 사용 관계를 구분해야 함",
        f"조건 사용 관계 확장 TABLE: {c['tables_with_runtime_relation_expansion']}",
        f"영향 코드: {c['codes_with_runtime_relation_expansion']}",
        f"TABLE→ADRG runtime 관계: {c['table_related_adrg_relation_count']}",
        f"CODE→ADRG runtime 관계: {c['code_related_adrg_relation_count']}",
        "",
        "[AST node 집계 수정]",
        f"조건 AST: {c['condition_ast_records']}",
        f"실제 AST node: {c['ast_node_count']}",
        "reference occurrence·provenance dict는 AST node 집계에서 제외함",
        "",
        "[source ADRG ref 전수감사]",
        f"raw TABLE owner ref: {c['raw_table_owner_ref_count']}",
        f"exact ADRG ref: {c['exact_source_adrg_ref_count']}",
        f"family source ref: {c['family_source_adrg_ref_count']} ({', '.join(report['owner_relation_audit']['family_source_refs'])})",
        f"미해석 source ref: {c['unresolved_source_adrg_ref_count']}",
        "X04는 ADRG로 노출하지 않고 AST 근거에 따라 X041·X042 조건 관계로 연결함",
        "",
        "[통합 결과]",
        f"ADRG: {c['adrg_records']}",
        f"AADRG: {c['aadrg_records']}",
        f"RDRG: {c['rdrg_records']}",
        f"논리 TABLE: {c['logical_table_records']}",
        f"TABLE code row: {c['table_code_rows']}",
        f"고유 검색 코드: {c['unique_search_codes']}",
        f"A/B/C exact: {c['abc_exact_mappings']}",
        f"A/B/C 미분류 보존: {c['abc_unclassified_aadrgs']}",
        f"검색 token: {c['search_token_count']}",
        "",
        "[검증 항목 집계]",
        f"PASS: {v['pass_count']}",
        f"FAIL: {v['fail_count']}",
        f"TOTAL: {v['pass_count'] + v['fail_count']}",
        "사용자 판단 필요: 0",
        "사용자 수동 Excel 검토: 없음",
        "",
        "[생성 파일]",
        str(OUTPUT_PATH),
        str(REPORT_TXT_PATH),
        str(REPORT_JSON_PATH),
        "",
        "[다음 단계]",
        "38번 V2에서 원천 6종으로 물리 source·조건 사용 관계를 독립 재구성하여 전수검증함",
        "검증 완료 전 runtime adapter 단계로 이동하지 않음",
        "",
        "[최종 결과]",
        f"전체 결과: {v['status']}",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    try:
        output, report = build()
        atomic_json(OUTPUT_PATH, output)
        atomic_json(REPORT_JSON_PATH, report)
        atomic_text(REPORT_TXT_PATH, render(report))
        validation = output["validation"]
        if validation["fail_count"]:
            print(f"[FAIL] 최종 검색용 통합 JSON V2 구축 실패: {validation['pass_count']} PASS / {validation['fail_count']} FAIL")
            print(f"report={REPORT_TXT_PATH}")
            return 1
        counts = output["meta"]["counts"]
        print(
            "[PASS] 최종 검색용 통합 JSON V2 구축 완료: "
            f"{counts['adrg_records']} ADRG / {counts['aadrg_records']} AADRG / "
            f"{counts['logical_table_records']} tables / {counts['unique_search_codes']} codes / "
            f"runtime-expanded {counts['tables_with_runtime_relation_expansion']} tables / "
            f"{validation['pass_count']} PASS / 0 FAIL"
        )
        print(f"data={OUTPUT_PATH}")
        print(f"report={REPORT_TXT_PATH}")
        return 0
    except Exception as exc:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        text = "\n".join([
            "KDRG V4.7 최종 검색용 통합 JSON V2 구축 실패",
            "=" * 72,
            f"오류 유형: {type(exc).__name__}",
            f"오류 내용: {exc}",
            "",
            traceback.format_exc(),
        ])
        atomic_text(REPORT_TXT_PATH, text)
        print(f"[FAIL] 최종 검색용 통합 JSON V2 구축 중단: {type(exc).__name__}: {exc}")
        print(f"report={REPORT_TXT_PATH}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
