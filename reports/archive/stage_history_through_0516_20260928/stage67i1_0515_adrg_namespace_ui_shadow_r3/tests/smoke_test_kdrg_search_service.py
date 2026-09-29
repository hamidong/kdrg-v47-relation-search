from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
DATA_PATH = ROOT / "data" / "kdrg_v47_search_integrated.json"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from kdrg_search_service import (  # noqa: E402
    KdrgSearchError,
    KdrgSearchService,
    RESPONSE_SCHEMA_VERSION,
    SERVICE_SCHEMA_VERSION,
    SUPPORTED_DATA_SCHEMA,
)


class Checker:
    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []

    def check(self, check_id: str, name: str, condition: bool, detail: str = "") -> None:
        self.checks.append({
            "check_id": check_id,
            "name": name,
            "status": "PASS" if condition else "FAIL",
            "detail": detail,
        })

    def summary(self) -> dict[str, Any]:
        passed = sum(1 for row in self.checks if row["status"] == "PASS")
        failed = len(self.checks) - passed
        return {
            "status": "PASS" if failed == 0 else "FAIL",
            "pass_count": passed,
            "fail_count": failed,
            "total_count": len(self.checks),
            "checks": self.checks,
        }


def ids(response: dict[str, Any], entity_type: str | None = None) -> list[str]:
    rows = response.get("results") or []
    if entity_type:
        rows = [row for row in rows if row.get("entity_type") == entity_type]
    return [str(row.get("entity_id") or "") for row in rows]


def run_smoke(data_path: str | Path = DATA_PATH) -> dict[str, Any]:
    checker = Checker()
    service = KdrgSearchService(data_path)
    status = service.status()
    counts = status["counts"]

    checker.check("S01", "service ready", status.get("ready") is True, str(status.get("ready")))
    checker.check("S02", "service schema", status.get("service_schema_version") == SERVICE_SCHEMA_VERSION, str(status.get("service_schema_version")))
    checker.check("S03", "response schema", status.get("response_schema_version") == RESPONSE_SCHEMA_VERSION, str(status.get("response_schema_version")))
    checker.check("S04", "data schema V2", status.get("data_schema_version") == SUPPORTED_DATA_SCHEMA, str(status.get("data_schema_version")))
    checker.check("S05", "ADRG 1132", counts.get("adrg_records") == 1132, str(counts.get("adrg_records")))
    checker.check("S06", "AADRG 1233", counts.get("aadrg_records") == 1233, str(counts.get("aadrg_records")))
    checker.check("S07", "RDRG 2699", counts.get("rdrg_records") == 2699, str(counts.get("rdrg_records")))
    checker.check("S08", "TABLE 1308", counts.get("logical_table_records") == 1308, str(counts.get("logical_table_records")))
    checker.check("S09", "CODE 16571", counts.get("unique_search_codes") == 16571, str(counts.get("unique_search_codes")))
    checker.check("S10", "AST node 1727", counts.get("ast_node_count") == 1727, str(counts.get("ast_node_count")))

    adrg = service.search("9600", "ADRG")
    checker.check("S11", "ADRG exact search", ids(adrg) == ["9600"], str(ids(adrg)))
    checker.check("S12", "ADRG exact match type", adrg["results"][0]["match_type"] == "EXACT_ID", str(adrg["results"][0]["match_type"]))

    aadrg = service.search("96000", "AADRG")
    checker.check("S13", "AADRG exact search", ids(aadrg) == ["96000"], str(ids(aadrg)))
    checker.check("S14", "AADRG B classification", aadrg["results"][0]["summary"]["classification_code"] == "B", str(aadrg["results"][0]["summary"]))

    rdrg = service.search("960000", "RDRG")
    checker.check("S15", "RDRG exact search", ids(rdrg) == ["960000"], str(ids(rdrg)))

    table = service.search("LT_9610_001", "TABLE")
    checker.check("S16", "TABLE exact search", ids(table) == ["LT_9610_001"], str(ids(table)))

    code = service.search("A000", "CODE")
    checker.check("S17", "CODE exact search", ids(code) == ["A000"], str(ids(code)))
    dotted = service.search("A00.0", "CODE")
    checker.check("S18", "CODE punctuation normalization", ids(dotted) == ["A000"], str(ids(dotted)))

    name_search = service.search("조기 사망", "ALL", limit=20)
    checker.check("S19", "Korean name token search", "9600" in ids(name_search, "ADRG"), str(ids(name_search, "ADRG")))
    checker.check("S20", "ALL type response", len(name_search.get("type_counts") or {}) >= 3, str(name_search.get("type_counts")))

    only_code = service.search("A000", ["CODE"], limit=20)
    checker.check("S21", "entity type filter", all(row["entity_type"] == "CODE" for row in only_code["results"]), str(only_code["results"]))
    mdc_filter = service.search("사망", "ALL", mdc="PRE", limit=50)
    checker.check("S22", "MDC filter", all((row["summary"].get("mdc") == "PRE") for row in mdc_filter["results"] if row["entity_type"] in {"ADRG", "AADRG"}), str(mdc_filter["results"][:5]))
    class_filter = service.search("9600", "ADRG", classification="B")
    checker.check("S23", "classification filter", ids(class_filter) == ["9600"], str(ids(class_filter)))
    class_filter_empty = service.search("9600", "ADRG", classification="A")
    checker.check("S24", "classification exclusion", class_filter_empty["total_count"] == 0, str(class_filter_empty["total_count"]))

    paged = service.search("사망", "ALL", limit=2, offset=0)
    checker.check("S25", "pagination limit", len(paged["results"]) <= 2, str(len(paged["results"])))
    checker.check("S26", "pagination has_more", paged["has_more"] is (paged["total_count"] > len(paged["results"])), str(paged["has_more"]))

    code_detail = service.get_detail("CODE", "S710")
    relations = code_detail["detail"]["relation_sections"]
    checker.check("S27", "CODE detail response schema", code_detail["schema_version"] == RESPONSE_SCHEMA_VERSION, str(code_detail["schema_version"]))
    checker.check("S28", "physical source relation separated", relations["physical_source"]["adrgs"] == ["X012", "X030", "X600"], str(relations["physical_source"]))
    checker.check("S29", "condition usage relation separated", relations["condition_usage"]["adrgs"] == ["X011", "X012", "X041", "X042"], str(relations["condition_usage"]))
    checker.check("S30", "runtime related relation separated", relations["runtime_related"]["adrgs"] == ["X011", "X012", "X030", "X041", "X042", "X600"], str(relations["runtime_related"]))
    checker.check("S31", "X04 family not exposed as ADRG", "X04" not in relations["runtime_related"]["adrgs"], str(relations["runtime_related"]))
    checker.check("S32", "X04 family provenance preserved", relations["physical_source"]["family_refs"] == ["X04"], str(relations["physical_source"]))

    semantic_counts = status["semantic_context_counts"]
    checker.check("S33", "allowed exception nodes 19", semantic_counts.get("allowed_exception_under_negated_or_procedure") == 19, str(semantic_counts))
    checker.check("S34", "optional companion nodes 7", semantic_counts.get("optional_companion_table") == 7, str(semantic_counts))
    checker.check("S35", "required optional pair nodes 7", semantic_counts.get("required_table_with_optional_companion") == 7, str(semantic_counts))

    optional_table = service.get_detail("TABLE", "LT_C064_003")["detail"]
    optional_contexts = optional_table.get("runtime_contexts") or []
    checker.check("S36", "optional companion table context", any(row.get("context") == "optional_companion_table" for row in optional_contexts), str(optional_contexts[:5]))
    allowed_table = service.get_detail("TABLE", "LT_P602_002")["detail"]
    allowed_contexts = allowed_table.get("runtime_contexts") or []
    checker.check("S37", "allowed exception table context", any(row.get("context") == "allowed_exception_under_negated_or_procedure" for row in allowed_contexts), str(allowed_contexts[:5]))

    unclassified = service.get_detail("AADRG", "99000")["detail"]
    checker.check("S38", "A/B/C unclassified preserved", unclassified.get("classification_code") is None and unclassified.get("abc_unclassified_provenance") is not None, str(unclassified.get("abc_unclassified_provenance")))
    mixed = service.get_detail("ADRG", "I760")["detail"]
    checker.check("S39", "mixed ADRG classification preserved", len(set(mixed.get("abc_classification_codes") or [])) >= 2, str(mixed.get("abc_classification_codes")))

    checker.check("S40", "JSON serialization search", bool(json.dumps(name_search, ensure_ascii=False)), "search serialized")
    checker.check("S41", "JSON serialization detail", bool(json.dumps(code_detail, ensure_ascii=False)), "detail serialized")

    invalid_type_raised = False
    try:
        service.search("A000", "INVALID")
    except KdrgSearchError:
        invalid_type_raised = True
    checker.check("S42", "invalid entity type error", invalid_type_raised, str(invalid_type_raised))

    empty_query_raised = False
    try:
        service.search("   ")
    except KdrgSearchError:
        empty_query_raised = True
    checker.check("S43", "empty query error", empty_query_raised, str(empty_query_raised))

    invalid_limit_raised = False
    try:
        service.search("A000", limit=0)
    except KdrgSearchError:
        invalid_limit_raised = True
    checker.check("S44", "invalid limit error", invalid_limit_raised, str(invalid_limit_raised))

    missing_detail_raised = False
    try:
        service.get_detail("CODE", "NOT_A_REAL_CODE")
    except KdrgSearchError:
        missing_detail_raised = True
    checker.check("S45", "missing detail error", missing_detail_raised, str(missing_detail_raised))

    table_detail = service.get_detail("TABLE", "LT_9610_001")["detail"]
    checker.check("S46", "TABLE code records", len(table_detail.get("code_records") or []) == 7, str(len(table_detail.get("code_records") or [])))
    adrg_detail = service.get_detail("ADRG", "9600")["detail"]
    checker.check("S47", "ADRG condition AST connected", (adrg_detail.get("condition_ast") or {}).get("condition_ast_id") == "AST_9600", str((adrg_detail.get("condition_ast") or {}).get("condition_ast_id")))
    aadrg_detail = service.get_detail("AADRG", "96000")["detail"]
    checker.check("S48", "AADRG parent ADRG connected", (aadrg_detail.get("parent_adrg") or {}).get("entity_id") == "9600", str(aadrg_detail.get("parent_adrg")))
    rdrg_detail = service.get_detail("RDRG", "960000")["detail"]
    checker.check("S49", "RDRG parent AADRG connected", (rdrg_detail.get("parent_aadrg") or {}).get("entity_id") == "96000", str(rdrg_detail.get("parent_aadrg")))

    return checker.summary()


if __name__ == "__main__":
    result = run_smoke()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"] == "PASS" else 1)
