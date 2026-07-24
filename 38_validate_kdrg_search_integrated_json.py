#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KDRG V4.7 최종 검색용 통합 JSON V2 독립 전수검증.

통합 JSON을 신뢰하지 않고 원천 6종에서 TABLE 물리 source 관계와
조건 AST 사용 관계를 별도 구현으로 다시 구성하여 전체 레코드·index·참조를 검증한다.
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

SCRIPT_VERSION = "2026-07-23_KDRG_V47_SEARCH_INTEGRATED_JSON_VALIDATOR_V2"
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
REPORT_DIR = ROOT / "reports"

GROUP_PATH = DATA_DIR / "kdrg_v47_group_name_base.json"
MAIN_PATH = DATA_DIR / "kdrg_v47_main_page_blocks.json"
LOGICAL_PATH = DATA_DIR / "kdrg_v47_logical_tables_repaired_current.json"
AST_PATH = DATA_DIR / "kdrg_v47_condition_ast_repaired_current.json"
ABC_PATH = DATA_DIR / "kdrg_v47_abc_classification_base.json"
TECH_PATH = DATA_DIR / "kdrg_v47_remaining_technical_review_pattern_analysis.json"
INTEGRATED_PATH = DATA_DIR / "kdrg_v47_search_integrated.json"
BUILD_REPORT_PATH = REPORT_DIR / "search_integrated_build_report.json"
REPORT_TXT_PATH = REPORT_DIR / "search_integrated_validation_report.txt"
REPORT_JSON_PATH = REPORT_DIR / "search_integrated_validation_report.json"

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
EXPECTED_ABC = {"A": 506, "B": 563, "C": 143}
EXPECTED_FAMILY_REFS = {"X04"}
EXPECTED_POLICIES = {
    "abc_exact_match_only": True,
    "abc_inference_mapping": False,
    "repaired_current_only": True,
    "source_provenance_preserved": True,
    "runtime_semantics_preserved": True,
    "physical_source_and_condition_usage_separated": True,
    "family_source_ref_never_exposed_as_adrg": True,
}
EXPECTED_RUNTIME_RULES = {
    "allowed_exception_under_negated_or_procedure": "필수 시술이 아니라 OR procedure 판정의 허용 예외",
    "optional_companion_table": "시행 여부 무관이며 필수조건에서 제외",
    "main_pdf_source_only_diagnosis_code": "본문 TABLE 코드를 유지하고 부록 관계 미수록 provenance 표시",
}


class ValidationError(RuntimeError):
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
        raise ValidationError(f"필수 파일 없음: {path}")
    with path.open("r", encoding="utf-8") as f:
        value = json.load(f)
    if not isinstance(value, dict):
        raise ValidationError(f"최상위 JSON 객체 아님: {path}")
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


def normalize(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().upper())


def pick(row: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return default


def identifier(row: dict[str, Any], *keys: str) -> str:
    return str(pick(row, *keys, default="") or "")


def actual_ast_nodes(ast: dict[str, Any]) -> list[dict[str, Any]]:
    rows = ast.get("nodes")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def collect_owner_refs(table: dict[str, Any]) -> set[str]:
    refs: set[str] = set()
    for key in ("source_adrg", "adrg", "owner_adrg"):
        value = table.get(key)
        if isinstance(value, str) and value:
            refs.add(value)
    for key in ("source_adrgs", "adrgs", "linked_adrgs", "condition_adrgs"):
        values = table.get(key)
        if isinstance(values, list):
            refs.update(str(value) for value in values if value)
    return refs


def extract_code_rows(table: dict[str, Any]) -> list[dict[str, Any]]:
    values = table.get("codes")
    return [row for row in values if isinstance(row, dict)] if isinstance(values, list) else []


def extract_code(row: dict[str, Any]) -> str:
    return normalize(pick(row, "code", "value", "code_value", "normalized_code", default=""))


def compare_by_id(actual: list[dict[str, Any]], expected: list[dict[str, Any]], key: str) -> dict[str, Any]:
    a = {str(row.get(key) or ""): row for row in actual}
    e = {str(row.get(key) or ""): row for row in expected}
    missing = sorted(set(e) - set(a))
    extra = sorted(set(a) - set(e))
    different = sorted(item for item in set(a) & set(e) if a[item] != e[item])
    return {
        "missing_count": len(missing),
        "extra_count": len(extra),
        "different_count": len(different),
        "missing_sample": missing[:10],
        "extra_sample": extra[:10],
        "different_sample": different[:10],
    }


def reconstruct() -> dict[str, Any]:
    group = load_json(GROUP_PATH)
    main = load_json(MAIN_PATH)
    logical = load_json(LOGICAL_PATH)
    ast_payload = load_json(AST_PATH)
    abc = load_json(ABC_PATH)
    tech = load_json(TECH_PATH)
    integrated = load_json(INTEGRATED_PATH)
    build_report = load_json(BUILD_REPORT_PATH)

    source_paths = [GROUP_PATH, MAIN_PATH, LOGICAL_PATH, AST_PATH, ABC_PATH, TECH_PATH]
    source_hashes = {path.stem: sha256_file(path) for path in source_paths}

    adrg_rows = group.get("adrgs") or []
    aadrg_rows = group.get("aadrgs") or []
    rdrg_rows = group.get("rdrgs") or []
    catalog_rows = main.get("adrg_catalog") or []
    block_rows = main.get("adrg_blocks") or []
    table_rows = logical.get("logical_tables") or []
    ast_rows = ast_payload.get("condition_asts") or []

    adrg_map = {identifier(row, "code", "adrg"): row for row in adrg_rows}
    aadrg_map = {identifier(row, "code", "aadrg"): row for row in aadrg_rows}
    rdrg_map = {identifier(row, "code", "rdrg"): row for row in rdrg_rows}
    table_map = {identifier(row, "logical_table_id"): row for row in table_rows}
    valid_adrgs = set(adrg_map)
    catalog_map = {identifier(row, "adrg"): row for row in catalog_rows}
    block_map = {identifier(row, "adrg"): row for row in block_rows}
    abc_map = dict((abc.get("indexes") or {}).get("aadrg_to_mapping") or {})
    unclassified_map = {identifier(row, "aadrg"): row for row in abc.get("current_unclassified_aadrgs") or []}

    # 조건 AST 관계: top-level nodes 배열만 순회한다.
    ast_to_tables: dict[str, set[str]] = defaultdict(set)
    table_to_ast_ids: dict[str, set[str]] = defaultdict(set)
    table_to_condition_adrgs: dict[str, set[str]] = defaultdict(set)
    adrg_to_ast: dict[str, str] = {}
    semantic_counts: Counter[str] = Counter()
    node_count = 0
    for ast in ast_rows:
        ast_id = identifier(ast, "condition_ast_id")
        adrg = identifier(ast, "adrg", "source_adrg")
        if adrg:
            adrg_to_ast[adrg] = ast_id
        nodes = actual_ast_nodes(ast)
        node_count += len(nodes)
        for node in nodes:
            tids = node.get("logical_table_ids")
            if isinstance(tids, list):
                for raw_tid in tids:
                    tid = str(raw_tid or "")
                    if not tid:
                        continue
                    ast_to_tables[ast_id].add(tid)
                    table_to_ast_ids[tid].add(ast_id)
                    if adrg in valid_adrgs:
                        table_to_condition_adrgs[tid].add(adrg)
            semantic = str(node.get("text_semantic_type") or node.get("semantic_type") or "")
            if semantic:
                semantic_counts[semantic] += 1

    # TABLE source ref를 independent branch logic으로 분류한다.
    table_relation: dict[str, dict[str, Any]] = {}
    adrg_source_tables: dict[str, set[str]] = defaultdict(set)
    adrg_condition_tables: dict[str, set[str]] = defaultdict(set)
    adrg_all_tables: dict[str, set[str]] = defaultdict(set)
    all_family_refs: set[str] = set()
    all_unresolved_refs: set[str] = set()

    for table in table_rows:
        tid = identifier(table, "logical_table_id")
        raw_refs = sorted(collect_owner_refs(table))
        condition_adrgs = set(table_to_condition_adrgs.get(tid, set()))
        exact: set[str] = set()
        families: set[str] = set()
        unresolved: set[str] = set()
        resolutions: list[dict[str, Any]] = []

        for ref in raw_refs:
            if ref in valid_adrgs:
                exact.add(ref)
                resolutions.append({
                    "source_ref": ref,
                    "status": "EXACT_ADRG",
                    "resolved_adrgs": [ref],
                    "evidence": "group_name_base_exact_code",
                })
                continue
            prefix_matches = sorted(code for code in valid_adrgs if code[: len(ref)] == ref)
            ast_matches = sorted(code for code in condition_adrgs if code in prefix_matches)
            if prefix_matches and ast_matches and not (condition_adrgs - set(prefix_matches)):
                families.add(ref)
                resolutions.append({
                    "source_ref": ref,
                    "status": "FAMILY_PREFIX_RESOLVED_BY_AST",
                    "candidate_adrgs": prefix_matches,
                    "resolved_adrgs": ast_matches,
                    "evidence": "condition_ast_reference",
                })
            else:
                unresolved.add(ref)
                resolutions.append({
                    "source_ref": ref,
                    "status": "UNRESOLVED_SOURCE_REF",
                    "candidate_adrgs": prefix_matches,
                    "condition_adrgs": sorted(condition_adrgs),
                    "resolved_adrgs": [],
                })

        related = exact | condition_adrgs
        relation = {
            "source_adrg_refs": raw_refs,
            "source_adrgs": sorted(exact),
            "source_adrg_families": sorted(families),
            "condition_adrgs": sorted(condition_adrgs),
            "related_adrgs": sorted(related),
            "source_adrg_resolution": resolutions,
            "unresolved_source_adrg_refs": sorted(unresolved),
        }
        table_relation[tid] = relation
        all_family_refs.update(families)
        all_unresolved_refs.update(unresolved)
        for adrg in exact:
            adrg_source_tables[adrg].add(tid)
        for adrg in condition_adrgs:
            adrg_condition_tables[adrg].add(tid)
        for adrg in related:
            adrg_all_tables[adrg].add(tid)

    # 코드 index
    code_to_tables: dict[str, set[str]] = defaultdict(set)
    table_codes: dict[str, list[str]] = {}
    code_names: dict[str, set[str]] = defaultdict(set)
    code_roles: dict[str, set[str]] = defaultdict(set)
    for table in table_rows:
        tid = identifier(table, "logical_table_id")
        codes: set[str] = set()
        for row in extract_code_rows(table):
            code = extract_code(row)
            if not code:
                continue
            codes.add(code)
            code_to_tables[code].add(tid)
            name = pick(row, "name", "code_name", "description", "label", default="")
            if name:
                code_names[code].add(str(name).strip())
            role = pick(row, "code_type", "role", "namespace", default=table.get("logical_table_scope") or "")
            if role:
                code_roles[code].add(str(role))
        table_codes[tid] = sorted(codes)

    # AADRG parent index
    adrg_children: dict[str, list[str]] = defaultdict(list)
    expected_aadrgs: list[dict[str, Any]] = []
    for aadrg in sorted(aadrg_map):
        source = aadrg_map[aadrg]
        adrg = str(source.get("adrg") or aadrg[:4])
        adrg_children[adrg].append(aadrg)
        mapping = abc_map.get(aadrg)
        expected_aadrgs.append({
            "aadrg": aadrg,
            "adrg": adrg,
            "mdc": (catalog_map.get(adrg) or {}).get("mdc"),
            "group_name": source.get("group_name"),
            "rdrg_codes": sorted(set(source.get("rdrg_codes") or [])),
            "abc_status": "EXACT_OFFICIAL" if mapping else "UNCLASSIFIED_EXACT_NOT_IN_OFFICIAL_PDF",
            "classification_code": mapping.get("classification_code") if mapping else None,
            "classification_name": mapping.get("classification_name") if mapping else None,
            "classification_display_label": mapping.get("display_label") if mapping else None,
            "abc_source_ref": mapping.get("source_ref") if mapping else None,
            "abc_unclassified_provenance": unclassified_map.get(aadrg),
        })

    expected_adrgs: list[dict[str, Any]] = []
    for adrg in sorted(adrg_map):
        source = adrg_map[adrg]
        catalog = catalog_map.get(adrg) or {}
        block = block_map.get(adrg) or {}
        children = sorted(adrg_children.get(adrg) or source.get("aadrg_codes") or [])
        classes = [abc_map[code]["classification_code"] for code in children if code in abc_map]
        labels = sorted({abc_map[code]["display_label"] for code in children if code in abc_map})
        expected_adrgs.append({
            "adrg": adrg,
            "mdc": catalog.get("mdc"),
            "adrg_name": pick(catalog, "adrg_name", "group_name", "name", default=source.get("display_name")),
            "aadrg_codes": children,
            "aadrg_count": len(children),
            "abc_classification_codes": sorted(set(classes)),
            "abc_display_labels": labels,
            "abc_status": "MIXED_BY_AADRG" if len(set(classes)) > 1 else ("SINGLE" if classes else "UNCLASSIFIED"),
            "source_logical_table_ids": sorted(adrg_source_tables.get(adrg, set())),
            "condition_logical_table_ids": sorted(adrg_condition_tables.get(adrg, set())),
            "logical_table_ids": sorted(adrg_all_tables.get(adrg, set())),
            "condition_ast_id": adrg_to_ast.get(adrg),
            "source_block": {
                "pdf_page_start": pick(block, "pdf_page_start", "start_pdf_page"),
                "pdf_page_end": pick(block, "pdf_page_end", "end_pdf_page"),
                "printed_page_start": pick(block, "printed_page_start", "start_printed_page"),
                "printed_page_end": pick(block, "printed_page_end", "end_printed_page"),
            },
        })

    expected_tables: list[dict[str, Any]] = []
    for tid in sorted(table_map):
        table = table_map[tid]
        expected_tables.append({
            "logical_table_id": tid,
            "display_name": pick(table, "display_name", "table_name", "name", "canonical_label", default=tid),
            "logical_table_type": table.get("logical_table_type"),
            "logical_table_scope": table.get("logical_table_scope"),
            **table_relation[tid],
            "code_count": len(table_codes.get(tid, [])),
            "codes": table_codes.get(tid, []),
            "condition_ast_ids": sorted(table_to_ast_ids.get(tid, set())),
            "source_refs": table.get("source_refs") or table.get("source_ref") or [],
            "parser_repair_history": table.get("parser_repair_history") or [],
        })

    expected_codes: list[dict[str, Any]] = []
    expanded_code_count = 0
    for code in sorted(code_to_tables):
        tids = sorted(code_to_tables[code])
        source_adrgs = sorted({adrg for tid in tids for adrg in table_relation[tid]["source_adrgs"]})
        condition_adrgs = sorted({adrg for tid in tids for adrg in table_relation[tid]["condition_adrgs"]})
        related_adrgs = sorted(set(source_adrgs) | set(condition_adrgs))
        families = sorted({ref for tid in tids for ref in table_relation[tid]["source_adrg_families"]})
        source_aadrgs = sorted({child for adrg in source_adrgs for child in adrg_children.get(adrg, [])})
        condition_aadrgs = sorted({child for adrg in condition_adrgs for child in adrg_children.get(adrg, [])})
        related_aadrgs = sorted(set(source_aadrgs) | set(condition_aadrgs))
        if set(condition_adrgs) - set(source_adrgs):
            expanded_code_count += 1
        expected_codes.append({
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

    expected_rdrgs = [rdrg_map[code] for code in sorted(rdrg_map)]

    token_index: dict[str, set[str]] = defaultdict(set)

    def register(entity_id: str, values: Iterable[Any]) -> None:
        for value in values:
            text = normalize(value)
            for token in re.findall(r"[0-9A-Z가-힣]+", text):
                if len(token) >= 2:
                    token_index[token].add(entity_id)

    for row in expected_adrgs:
        register(f"ADRG:{row['adrg']}", [row["adrg"], row.get("adrg_name")])
    for row in expected_aadrgs:
        register(f"AADRG:{row['aadrg']}", [row["aadrg"], row.get("group_name"), row.get("classification_display_label")])
    for row in expected_tables:
        register(f"TABLE:{row['logical_table_id']}", [row["logical_table_id"], row.get("display_name")])
    for row in expected_codes:
        register(f"CODE:{row['code']}", [row["code"], *row.get("names", [])])

    expected_indexes = {
        "adrg_to_record_index": {row["adrg"]: index for index, row in enumerate(expected_adrgs)},
        "aadrg_to_record_index": {row["aadrg"]: index for index, row in enumerate(expected_aadrgs)},
        "rdrg_to_record_index": {identifier(row, "rdrg", "code"): index for index, row in enumerate(expected_rdrgs)},
        "logical_table_id_to_record_index": {row["logical_table_id"]: index for index, row in enumerate(expected_tables)},
        "code_to_record_index": {row["code"]: index for index, row in enumerate(expected_codes)},
        "adrg_to_aadrgs": {key: sorted(value) for key, value in sorted(adrg_children.items())},
        "adrg_to_source_logical_table_ids": {key: sorted(value) for key, value in sorted(adrg_source_tables.items())},
        "adrg_to_condition_logical_table_ids": {key: sorted(value) for key, value in sorted(adrg_condition_tables.items())},
        "adrg_to_logical_table_ids": {key: sorted(value) for key, value in sorted(adrg_all_tables.items())},
        "adrg_to_condition_ast_id": dict(sorted(adrg_to_ast.items())),
        "code_to_logical_table_ids": {key: sorted(value) for key, value in sorted(code_to_tables.items())},
        "token_to_entity_ids": {key: sorted(value) for key, value in sorted(token_index.items())},
    }

    expected_counts = {
        "adrg_records": len(expected_adrgs),
        "aadrg_records": len(expected_aadrgs),
        "rdrg_records": len(expected_rdrgs),
        "logical_table_records": len(expected_tables),
        "condition_ast_records": len(ast_rows),
        "ast_node_count": node_count,
        "table_code_rows": sum(len(extract_code_rows(table)) for table in table_rows),
        "unique_search_codes": len(expected_codes),
        "abc_exact_mappings": len(abc_map),
        "abc_unclassified_aadrgs": len(unclassified_map),
        "search_token_count": len(token_index),
        "raw_table_owner_ref_count": sum(len(row["source_adrg_refs"]) for row in table_relation.values()),
        "exact_source_adrg_ref_count": sum(len(row["source_adrgs"]) for row in table_relation.values()),
        "family_source_adrg_ref_count": sum(len(row["source_adrg_families"]) for row in table_relation.values()),
        "unresolved_source_adrg_ref_count": sum(len(row["unresolved_source_adrg_refs"]) for row in table_relation.values()),
        "tables_with_condition_adrgs": sum(bool(row["condition_adrgs"]) for row in table_relation.values()),
        "tables_with_runtime_relation_expansion": sum(bool(set(row["condition_adrgs"]) - set(row["source_adrgs"])) for row in table_relation.values()),
        "table_related_adrg_relation_count": sum(len(row["related_adrgs"]) for row in table_relation.values()),
        "codes_with_runtime_relation_expansion": expanded_code_count,
        "code_related_adrg_relation_count": sum(len(row["related_adrgs"]) for row in expected_codes),
        "code_related_aadrg_relation_count": sum(len(row["related_aadrgs"]) for row in expected_codes),
    }

    actual_sections = {
        "adrg_records": integrated.get("adrg_records") or [],
        "aadrg_records": integrated.get("aadrg_records") or [],
        "rdrg_records": integrated.get("rdrg_records") or [],
        "logical_table_records": integrated.get("logical_table_records") or [],
        "condition_ast_records": integrated.get("condition_ast_records") or [],
        "code_records": integrated.get("code_records") or [],
    }
    expected_sections = {
        "adrg_records": expected_adrgs,
        "aadrg_records": expected_aadrgs,
        "rdrg_records": expected_rdrgs,
        "logical_table_records": expected_tables,
        "condition_ast_records": ast_rows,
        "code_records": expected_codes,
    }

    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, actual: Any, expected: Any) -> None:
        checks.append({"name": name, "status": "PASS" if ok else "FAIL", "actual": actual, "expected": expected})

    # 파일·schema·hash
    check("통합 JSON 존재", INTEGRATED_PATH.exists(), INTEGRATED_PATH.exists(), True)
    check("37번 build report 존재", BUILD_REPORT_PATH.exists(), BUILD_REPORT_PATH.exists(), True)
    meta = integrated.get("meta") or {}
    check("schema version V2", meta.get("schema_version") == "kdrg-v47-search-integrated-v2", meta.get("schema_version"), "kdrg-v47-search-integrated-v2")
    check("state V2", meta.get("state") == "search_ready_integrated_base_v2", meta.get("state"), "search_ready_integrated_base_v2")
    check("data version", meta.get("data_version") == "KDRG V4.7", meta.get("data_version"), "KDRG V4.7")
    check("통합 source hash", meta.get("source_hashes") == source_hashes, meta.get("source_hashes"), source_hashes)
    check("build report source hash", build_report.get("source_hashes") == source_hashes, build_report.get("source_hashes"), source_hashes)
    for stem, digest in sorted(source_hashes.items()):
        check(f"원천 SHA {stem}", (meta.get("source_hashes") or {}).get(stem) == digest, (meta.get("source_hashes") or {}).get(stem), digest)

    # counts
    check("통합 counts 독립 일치", meta.get("counts") == expected_counts, meta.get("counts"), expected_counts)
    check("build report counts 독립 일치", build_report.get("counts") == expected_counts, build_report.get("counts"), expected_counts)
    for key, expected in EXPECTED.items():
        check(f"고정 집계 {key}", expected_counts.get(key) == expected, expected_counts.get(key), expected)

    # 기본키·A/B/C
    check("ADRG ID 고유", len(adrg_map) == len(adrg_rows), len(adrg_map), len(adrg_rows))
    check("AADRG ID 고유", len(aadrg_map) == len(aadrg_rows), len(aadrg_map), len(aadrg_rows))
    check("RDRG ID 고유", len(rdrg_map) == len(rdrg_rows), len(rdrg_map), len(rdrg_rows))
    check("TABLE ID 고유", len(table_map) == len(table_rows), len(table_map), len(table_rows))
    check("AADRG parent 존재", all(row["adrg"] in valid_adrgs for row in expected_aadrgs), sum(row["adrg"] not in valid_adrgs for row in expected_aadrgs), 0)
    check("ABC exact·미분류 분할", set(abc_map).isdisjoint(unclassified_map) and set(abc_map) | set(unclassified_map) == set(aadrg_map), len(set(abc_map) | set(unclassified_map)), len(aadrg_map))
    abc_counts = Counter(str(value.get("classification_code") or "") for value in abc_map.values())
    for code, expected in EXPECTED_ABC.items():
        check(f"ABC exact {code}", abc_counts.get(code, 0) == expected, abc_counts.get(code, 0), expected)

    # AST 실제 node와 깊은 dict 오집계 방지
    deep_dict_count = 0
    for ast in ast_rows:
        stack: list[Any] = [ast]
        while stack:
            value = stack.pop()
            if isinstance(value, dict):
                deep_dict_count += 1
                stack.extend(value.values())
            elif isinstance(value, list):
                stack.extend(value)
    check("실제 AST node 1727", node_count == 1727, node_count, 1727)
    check("깊은 dict는 node가 아님", deep_dict_count == 5178 and deep_dict_count != node_count, deep_dict_count, 5178)

    # source/condition 관계 전수감사
    check("family source ref 집합", all_family_refs == EXPECTED_FAMILY_REFS, sorted(all_family_refs), sorted(EXPECTED_FAMILY_REFS))
    check("미해석 source ref 없음", not all_unresolved_refs, sorted(all_unresolved_refs), [])
    x04 = table_relation.get("LT_X04_PRINCIPAL_DIAGNOSIS_TABLE01") or {}
    check("X04 raw family 보존", x04.get("source_adrg_families") == ["X04"], x04.get("source_adrg_families"), ["X04"])
    check("X04 runtime ADRG 해결", x04.get("condition_adrgs") == ["X041", "X042"], x04.get("condition_adrgs"), ["X041", "X042"])
    check("X04 관련 ADRG 유효", x04.get("related_adrgs") == ["X041", "X042"], x04.get("related_adrgs"), ["X041", "X042"])
    check("전체 TABLE runtime ADRG 등록", all(adrg in valid_adrgs for row in table_relation.values() for adrg in row["related_adrgs"]), 0, 0)
    check("AST TABLE 참조 등록", all(tid in table_map for tids in ast_to_tables.values() for tid in tids), sum(tid not in table_map for tids in ast_to_tables.values() for tid in tids), 0)

    # 전체 section 비교
    key_map = {
        "adrg_records": "adrg",
        "aadrg_records": "aadrg",
        "rdrg_records": "rdrg",
        "logical_table_records": "logical_table_id",
        "code_records": "code",
    }
    mismatches: dict[str, Any] = {}
    for section, expected_rows in expected_sections.items():
        actual_rows = actual_sections[section]
        check(f"{section} count", len(actual_rows) == len(expected_rows), len(actual_rows), len(expected_rows))
        check(f"{section} hash", json_hash(actual_rows) == json_hash(expected_rows), json_hash(actual_rows), json_hash(expected_rows))
        if section in key_map:
            detail = compare_by_id(actual_rows, expected_rows, key_map[section])
            mismatches[section] = detail
            check(f"{section} missing", detail["missing_count"] == 0, detail["missing_count"], 0)
            check(f"{section} extra", detail["extra_count"] == 0, detail["extra_count"], 0)
            check(f"{section} different", detail["different_count"] == 0, detail["different_count"], 0)

    # index·policy·runtime rules
    actual_indexes = integrated.get("indexes") or {}
    check("전체 index hash", json_hash(actual_indexes) == json_hash(expected_indexes), json_hash(actual_indexes), json_hash(expected_indexes))
    for key, expected_value in expected_indexes.items():
        check(f"index {key}", actual_indexes.get(key) == expected_value, json_hash(actual_indexes.get(key)), json_hash(expected_value))
    policies = meta.get("policies") or {}
    check("policy 전체", policies == EXPECTED_POLICIES, policies, EXPECTED_POLICIES)
    for key, value in EXPECTED_POLICIES.items():
        check(f"policy {key}", policies.get(key) is value, policies.get(key), value)
    rules = integrated.get("runtime_semantic_rules") or {}
    check("runtime rules 전체", rules == EXPECTED_RUNTIME_RULES, rules, EXPECTED_RUNTIME_RULES)
    for key, value in EXPECTED_RUNTIME_RULES.items():
        check(f"runtime rule {key}", rules.get(key) == value, rules.get(key), value)

    # 교차 참조
    actual_table_ids = {row.get("logical_table_id") for row in actual_sections["logical_table_records"]}
    actual_adrg_ids = {row.get("adrg") for row in actual_sections["adrg_records"]}
    actual_aadrg_ids = {row.get("aadrg") for row in actual_sections["aadrg_records"]}
    actual_ast_ids = {row.get("condition_ast_id") for row in actual_sections["condition_ast_records"]}
    actual_code_ids = {row.get("code") for row in actual_sections["code_records"]}

    ref_errors = {
        "code_to_table": sorted({tid for row in actual_sections["code_records"] for tid in row.get("logical_table_ids") or [] if tid not in actual_table_ids}),
        "table_to_ast": sorted({aid for row in actual_sections["logical_table_records"] for aid in row.get("condition_ast_ids") or [] if aid not in actual_ast_ids}),
        "adrg_to_table": sorted({tid for row in actual_sections["adrg_records"] for tid in row.get("logical_table_ids") or [] if tid not in actual_table_ids}),
        "aadrg_to_adrg": sorted({row.get("adrg") for row in actual_sections["aadrg_records"] if row.get("adrg") not in actual_adrg_ids}),
        "code_to_adrg": sorted({adrg for row in actual_sections["code_records"] for adrg in row.get("related_adrgs") or [] if adrg not in actual_adrg_ids}),
        "code_to_aadrg": sorted({aadrg for row in actual_sections["code_records"] for aadrg in row.get("related_aadrgs") or [] if aadrg not in actual_aadrg_ids}),
        "table_to_adrg": sorted({adrg for row in actual_sections["logical_table_records"] for adrg in row.get("related_adrgs") or [] if adrg not in actual_adrg_ids}),
    }
    for key, values in ref_errors.items():
        check(f"참조 오류 {key}", not values, values[:20], [])

    # index actual location
    record_index_errors = 0
    index_specs = [
        ("adrg_to_record_index", "adrg_records", "adrg"),
        ("aadrg_to_record_index", "aadrg_records", "aadrg"),
        ("logical_table_id_to_record_index", "logical_table_records", "logical_table_id"),
        ("code_to_record_index", "code_records", "code"),
    ]
    for index_key, section, id_key in index_specs:
        rows = actual_sections[section]
        for value, position in (actual_indexes.get(index_key) or {}).items():
            if not isinstance(position, int) or position < 0 or position >= len(rows) or rows[position].get(id_key) != value:
                record_index_errors += 1
    check("record index 위치 오류", record_index_errors == 0, record_index_errors, 0)

    valid_entities = (
        {f"ADRG:{value}" for value in actual_adrg_ids}
        | {f"AADRG:{value}" for value in actual_aadrg_ids}
        | {f"TABLE:{value}" for value in actual_table_ids}
        | {f"CODE:{value}" for value in actual_code_ids}
    )
    invalid_entities = sorted({entity for values in (actual_indexes.get("token_to_entity_ids") or {}).values() for entity in values if entity not in valid_entities})
    check("token entity 미등록", not invalid_entities, invalid_entities[:20], [])

    # builder validation/hash
    validation = integrated.get("validation") or {}
    check("37 V2 validation PASS", validation.get("status") == "PASS", validation.get("status"), "PASS")
    check("37 V2 fail 0", validation.get("fail_count") == 0, validation.get("fail_count"), 0)
    check("37 V2 pass count 일치", validation.get("pass_count") == len(validation.get("checks") or []), validation.get("pass_count"), len(validation.get("checks") or []))
    check("37 사용자 판단 0", validation.get("user_judgment_required") == 0, validation.get("user_judgment_required"), 0)
    check("37 수동 Excel 없음", validation.get("manual_excel_review") is False, validation.get("manual_excel_review"), False)
    content_hash = json_hash({key: value for key, value in integrated.items() if key != "validation"})
    check("통합 content hash", content_hash == build_report.get("output_content_sha256"), content_hash, build_report.get("output_content_sha256"))

    unresolved = int((tech.get("summary") or (tech.get("meta") or {}).get("counts") or {}).get("unresolved", 0) or 0)
    check("기술검토 unresolved 0", unresolved == 0, unresolved, 0)

    # 실제 수정 영향 집계가 V1 오류 범위를 모두 포함하는지
    old_invalid_source_refs = sorted({ref for table in table_rows for ref in collect_owner_refs(table) if ref not in valid_adrgs})
    check("V1 미등록 source ref 전수 집합", old_invalid_source_refs == ["X04"], old_invalid_source_refs, ["X04"])
    actual_codes_x04_family = [row for row in actual_sections["code_records"] if "X04" in (row.get("source_adrg_families") or [])]
    check("X04 family 영향 코드 79", len(actual_codes_x04_family) == 79, len(actual_codes_x04_family), 79)
    check("X04가 related_adrgs에 노출되지 않음", all("X04" not in (row.get("related_adrgs") or []) for row in actual_sections["code_records"]), 0, 0)
    check("X04 코드가 X041·X042 연결", all({"X041", "X042"}.issubset(set(row.get("condition_adrgs") or [])) for row in actual_codes_x04_family), sum(not {"X041", "X042"}.issubset(set(row.get("condition_adrgs") or [])) for row in actual_codes_x04_family), 0)

    fail_count = sum(item["status"] == "FAIL" for item in checks)
    pass_count = len(checks) - fail_count
    generated_at = now_iso()
    return {
        "script_version": SCRIPT_VERSION,
        "validated_at": generated_at,
        "input_hashes": {
            **source_hashes,
            INTEGRATED_PATH.stem: sha256_file(INTEGRATED_PATH),
            BUILD_REPORT_PATH.stem: sha256_file(BUILD_REPORT_PATH),
        },
        "independent_counts": expected_counts,
        "abc_exact_counts": dict(sorted(abc_counts.items())),
        "runtime_semantic_counts": dict(sorted(semantic_counts.items())),
        "owner_relation_audit": {
            "family_source_refs": sorted(all_family_refs),
            "unresolved_source_refs": sorted(all_unresolved_refs),
            "x04_relation": x04,
            "runtime_expansion_table_count": expected_counts["tables_with_runtime_relation_expansion"],
            "runtime_expansion_code_count": expected_counts["codes_with_runtime_relation_expansion"],
        },
        "section_mismatches": mismatches,
        "cross_reference_errors": ref_errors,
        "validation": {
            "status": "PASS" if fail_count == 0 else "FAIL",
            "pass_count": pass_count,
            "fail_count": fail_count,
            "total_count": len(checks),
            "checks": checks,
            "user_judgment_required": 0,
            "manual_excel_review": False,
        },
    }


def render(report: dict[str, Any]) -> str:
    counts = report["independent_counts"]
    validation = report["validation"]
    x04 = (report.get("owner_relation_audit") or {}).get("x04_relation") or {}
    lines = [
        "KDRG V4.7 최종 검색용 통합 JSON V2 독립 전수검증 결과",
        "=" * 72,
        f"검증시각: {report['validated_at']}",
        f"검증 스크립트 버전: {SCRIPT_VERSION}",
        "",
        "[현재 진행 위치]",
        "37번 V1 검증에서 발견한 AST node 집계 오류와 TABLE source/runtime 관계 혼합을 전체 corpus 기준으로 수정함",
        "37번 V2 통합 JSON을 원천 6종에서 독립 재구성해 확정하는 단계",
        "이번 단계에서는 원천과 통합 JSON을 수정하지 않음",
        "",
        "[원인 전수감사]",
        "V1 AST 집계는 실제 nodes 배열 외 reference occurrence·provenance dict까지 포함하여 5,178개로 오집계함",
        f"V2 실제 AST node: {counts['ast_node_count']}",
        "V1은 TABLE 물리 source ADRG만 코드 관련 ADRG로 사용하여 공유 TABLE의 조건 사용 관계를 누락함",
        f"runtime 관계 확장 TABLE: {counts['tables_with_runtime_relation_expansion']}",
        f"runtime 관계 확장 코드: {counts['codes_with_runtime_relation_expansion']}",
        "",
        "[source ADRG ref 독립 재계산]",
        f"raw owner ref: {counts['raw_table_owner_ref_count']}",
        f"exact ADRG ref: {counts['exact_source_adrg_ref_count']}",
        f"family source ref: {counts['family_source_adrg_ref_count']}",
        f"미해석 source ref: {counts['unresolved_source_adrg_ref_count']}",
        f"X04 condition ADRG: {x04.get('condition_adrgs')}",
        "X04를 ADRG ID로 노출하지 않고 X041·X042 AST 사용 관계로 해결함",
        "",
        "[독립 재구성 결과]",
        f"ADRG/AADRG/RDRG: {counts['adrg_records']} / {counts['aadrg_records']} / {counts['rdrg_records']}",
        f"TABLE/AST/node: {counts['logical_table_records']} / {counts['condition_ast_records']} / {counts['ast_node_count']}",
        f"TABLE code row/고유 code: {counts['table_code_rows']} / {counts['unique_search_codes']}",
        f"TABLE→ADRG runtime 관계: {counts['table_related_adrg_relation_count']}",
        f"CODE→ADRG runtime 관계: {counts['code_related_adrg_relation_count']}",
        f"CODE→AADRG runtime 관계: {counts['code_related_aadrg_relation_count']}",
        f"검색 token: {counts['search_token_count']}",
        "",
        "[통합 레코드 전수 대조]",
        f"ADRG 불일치: {report['section_mismatches'].get('adrg_records', {}).get('different_count', 0)}",
        f"AADRG 불일치: {report['section_mismatches'].get('aadrg_records', {}).get('different_count', 0)}",
        f"TABLE 불일치: {report['section_mismatches'].get('logical_table_records', {}).get('different_count', 0)}",
        f"CODE 불일치: {report['section_mismatches'].get('code_records', {}).get('different_count', 0)}",
        f"미등록 CODE→ADRG: {len(report['cross_reference_errors'].get('code_to_adrg', []))}",
        f"미등록 TABLE→ADRG: {len(report['cross_reference_errors'].get('table_to_adrg', []))}",
        "",
        "[검증 항목 집계]",
        f"PASS: {validation['pass_count']}",
        f"FAIL: {validation['fail_count']}",
        f"TOTAL: {validation['total_count']}",
        "사용자 판단 필요: 0",
        "사용자 수동 Excel 검토: 없음",
        "",
    ]
    failed = [item for item in validation["checks"] if item["status"] == "FAIL"]
    if failed:
        lines.append("[FAIL 상세]")
        for item in failed[:30]:
            lines.append(f"- {item['name']} | actual={item['actual']} | expected={item['expected']}")
        lines.append("")
    lines.extend([
        "[생성 파일]",
        str(REPORT_TXT_PATH),
        str(REPORT_JSON_PATH),
        "",
        "[다음 단계]",
        "V2 검증 PASS 후에만 PySide runtime adapter와 검색 service 구축으로 진행함",
        "코드 검색 응답에서는 physical source·condition usage·runtime 관련 ADRG를 구분해 제공함",
        "",
        "[최종 결과]",
        f"전체 결과: {validation['status']}",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    try:
        report = reconstruct()
        atomic_json(REPORT_JSON_PATH, report)
        atomic_text(REPORT_TXT_PATH, render(report))
        validation = report["validation"]
        counts = report["independent_counts"]
        if validation["fail_count"]:
            print(f"[FAIL] 최종 검색용 통합 JSON V2 독립 전수검증 실패: {validation['pass_count']} PASS / {validation['fail_count']} FAIL")
            print(f"report={REPORT_TXT_PATH}")
            return 1
        print(
            "[PASS] 최종 검색용 통합 JSON V2 독립 전수검증 완료: "
            f"{counts['adrg_records']} ADRG / {counts['aadrg_records']} AADRG / "
            f"{counts['logical_table_records']} tables / {counts['unique_search_codes']} codes / "
            f"runtime-expanded {counts['tables_with_runtime_relation_expansion']} tables / "
            f"{validation['pass_count']} PASS / 0 FAIL / 사용자 판단 0건"
        )
        print(f"report={REPORT_TXT_PATH}")
        return 0
    except Exception as exc:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        text = "\n".join([
            "KDRG V4.7 최종 검색용 통합 JSON V2 독립 전수검증 실패",
            "=" * 72,
            f"오류 유형: {type(exc).__name__}",
            f"오류 내용: {exc}",
            "",
            traceback.format_exc(),
        ])
        atomic_text(REPORT_TXT_PATH, text)
        print(f"[FAIL] 최종 검색용 통합 JSON V2 독립 전수검증 중단: {type(exc).__name__}: {exc}")
        print(f"report={REPORT_TXT_PATH}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
