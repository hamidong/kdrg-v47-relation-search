from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCRIPT_VERSION = "2026-07-23_KDRG_V47_RUNTIME_SEARCH_SERVICE_VALIDATOR_V1"
ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data" / "kdrg_v47_search_integrated.json"
SERVICE_PATH = ROOT / "app" / "kdrg_search_service.py"
BUILD_REPORT_PATH = ROOT / "reports" / "runtime_search_service_build_report.json"
REPORT_TXT_PATH = ROOT / "reports" / "runtime_search_service_validation_report.txt"
REPORT_JSON_PATH = ROOT / "reports" / "runtime_search_service_validation_report.json"

SERVICE_SCHEMA_VERSION = "kdrg-runtime-search-service-v1"
RESPONSE_SCHEMA_VERSION = "kdrg-runtime-search-response-v1"
SUPPORTED_DATA_SCHEMA = "kdrg-v47-search-integrated-v2"
ENTITY_TYPES = ("CODE", "ADRG", "AADRG", "RDRG", "TABLE")
ENTITY_ORDER = {name: index for index, name in enumerate(ENTITY_TYPES)}
TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣_]+")


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
        passed = sum(row["status"] == "PASS" for row in self.checks)
        failed = len(self.checks) - passed
        return {
            "status": "PASS" if failed == 0 else "FAIL",
            "pass_count": passed,
            "fail_count": failed,
            "total_count": len(self.checks),
            "checks": self.checks,
        }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_hash(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON 최상위 구조가 dict가 아닙니다: {path}")
    return payload


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    temp.replace(path)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"모듈 spec 생성 실패: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def normalize_space(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_entity_id(value: Any, entity_type: str | None = None) -> str:
    text = normalize_space(value).upper()
    if entity_type == "TABLE" or text.startswith("LT_"):
        return re.sub(r"[^A-Z0-9_]", "", text)
    return re.sub(r"[^A-Z0-9]", "", text)


def normalize_query(value: Any) -> str:
    return normalize_space(value).casefold()


def query_tokens(value: Any) -> list[str]:
    tokens = [token.casefold() for token in TOKEN_RE.findall(normalize_space(value))]
    output: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token and token not in seen:
            seen.add(token)
            output.append(token)
    return output


def unique_strings(values: Iterable[Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "")
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return output


class IndependentRuntimeModel:
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        self.records = {
            "ADRG": data["adrg_records"],
            "AADRG": data["aadrg_records"],
            "RDRG": data["rdrg_records"],
            "TABLE": data["logical_table_records"],
            "CODE": data["code_records"],
        }
        self.id_fields = {
            "ADRG": "adrg",
            "AADRG": "aadrg",
            "RDRG": "code",
            "TABLE": "logical_table_id",
            "CODE": "code",
        }
        self.maps = {
            entity_type: {
                normalize_entity_id(row.get(self.id_fields[entity_type]), entity_type): row
                for row in rows
            }
            for entity_type, rows in self.records.items()
        }
        self.ast_map = {
            str(row.get("condition_ast_id") or ""): row
            for row in data.get("condition_ast_records") or []
            if str(row.get("condition_ast_id") or "")
        }
        self.semantic_index, self.semantic_summary = self.build_semantic_index()
        self.documents = self.build_documents()

    def title_subtitle(self, entity_type: str, row: dict[str, Any]) -> tuple[str, str]:
        if entity_type == "CODE":
            names = [str(x) for x in row.get("names") or [] if str(x)]
            return str(row.get("code") or ""), " / ".join(names[:2]) if names else "코드명 원천 미수록"
        if entity_type == "ADRG":
            title = f"{row.get('adrg', '')} · {row.get('adrg_name', '')}".strip(" ·")
            return title, f"MDC {row.get('mdc', '-')} · AADRG {row.get('aadrg_count', 0)}개"
        if entity_type == "AADRG":
            title = f"{row.get('aadrg', '')} · {row.get('group_name', '')}".strip(" ·")
            label = str(row.get("classification_display_label") or "분류 미부여")
            return title, f"ADRG {row.get('adrg', '-')} · {label}"
        if entity_type == "RDRG":
            title = f"{row.get('code', '')} · {row.get('group_name', '')}".strip(" ·")
            return title, f"AADRG {row.get('aadrg', '-')} · {row.get('severity_name') or '중증도 명칭 없음'}"
        return (
            str(row.get("display_name") or row.get("logical_table_id") or ""),
            f"코드 {row.get('code_count', 0)}개 · 관련 ADRG {len(row.get('related_adrgs') or [])}개",
        )

    def summary_payload(self, entity_type: str, row: dict[str, Any]) -> dict[str, Any]:
        if entity_type == "CODE":
            return {
                "names": deepcopy(row.get("names") or []),
                "roles": deepcopy(row.get("roles") or []),
                "logical_table_count": len(row.get("logical_table_ids") or []),
                "source_adrgs": deepcopy(row.get("source_adrgs") or []),
                "condition_adrgs": deepcopy(row.get("condition_adrgs") or []),
                "related_adrgs": deepcopy(row.get("related_adrgs") or []),
                "source_adrg_families": deepcopy(row.get("source_adrg_families") or []),
                "related_aadrg_count": len(row.get("related_aadrgs") or []),
            }
        if entity_type == "ADRG":
            return {
                "mdc": row.get("mdc"),
                "aadrg_count": row.get("aadrg_count"),
                "abc_status": row.get("abc_status"),
                "abc_display_labels": deepcopy(row.get("abc_display_labels") or []),
                "source_table_count": len(row.get("source_logical_table_ids") or []),
                "condition_table_count": len(row.get("condition_logical_table_ids") or []),
                "related_table_count": len(row.get("logical_table_ids") or []),
                "condition_ast_id": row.get("condition_ast_id"),
            }
        if entity_type == "AADRG":
            return {
                "adrg": row.get("adrg"),
                "mdc": row.get("mdc"),
                "classification_code": row.get("classification_code"),
                "classification_display_label": row.get("classification_display_label") or "분류 미부여",
                "abc_status": row.get("abc_status"),
                "rdrg_count": len(row.get("rdrg_codes") or []),
            }
        if entity_type == "RDRG":
            return {
                "adrg": row.get("adrg"),
                "aadrg": row.get("aadrg"),
                "severity_name": row.get("severity_name"),
            }
        return {
            "logical_table_type": row.get("logical_table_type"),
            "logical_table_scope": row.get("logical_table_scope"),
            "code_count": row.get("code_count"),
            "source_adrgs": deepcopy(row.get("source_adrgs") or []),
            "condition_adrgs": deepcopy(row.get("condition_adrgs") or []),
            "related_adrgs": deepcopy(row.get("related_adrgs") or []),
            "source_adrg_families": deepcopy(row.get("source_adrg_families") or []),
            "condition_ast_count": len(row.get("condition_ast_ids") or []),
        }

    def summary_entity(self, entity_type: str, entity_id: str) -> dict[str, Any]:
        row = self.maps[entity_type].get(normalize_entity_id(entity_id, entity_type))
        if row is None:
            return {"entity_type": entity_type, "entity_id": entity_id, "missing": True}
        title, subtitle = self.title_subtitle(entity_type, row)
        return {
            "entity_type": entity_type,
            "entity_id": str(row.get(self.id_fields[entity_type]) or ""),
            "title": title,
            "subtitle": subtitle,
            "summary": self.summary_payload(entity_type, row),
        }

    def build_semantic_index(self) -> tuple[dict[tuple[str, str], list[dict[str, Any]]], dict[str, int]]:
        output: defaultdict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        summary: Counter[str] = Counter()
        for ast in self.data.get("condition_ast_records") or []:
            adrg = str(ast.get("adrg") or "")
            ast_id = str(ast.get("condition_ast_id") or "")
            nodes = {
                str(node.get("node_id") or ""): node
                for node in ast.get("nodes") or []
                if str(node.get("node_id") or "")
            }
            parent_by_child: dict[str, str] = {}
            for node_id, node in nodes.items():
                parent_id = str(node.get("parent_node_id") or "")
                if parent_id:
                    parent_by_child[node_id] = parent_id
                for child_id in node.get("child_node_ids") or []:
                    child = str(child_id or "")
                    if child and child not in parent_by_child:
                        parent_by_child[child] = node_id

            def ancestor_types(node_id: str) -> list[str]:
                result: list[str] = []
                seen: set[str] = set()
                current = node_id
                while current in parent_by_child:
                    parent_id = parent_by_child[current]
                    if not parent_id or parent_id in seen:
                        break
                    seen.add(parent_id)
                    parent = nodes.get(parent_id)
                    if parent is None:
                        break
                    result.append(str(parent.get("node_type") or ""))
                    current = parent_id
                return result

            for node_id, node in nodes.items():
                table_ids = unique_strings(node.get("logical_table_ids") or [])
                if not table_ids:
                    continue
                node_type = str(node.get("node_type") or "")
                semantic_type = str(node.get("semantic_type") or "")
                evaluation_mode = str(node.get("evaluation_mode") or "")
                fragment = str(node.get("source_fragment") or node.get("display_text") or "")
                ancestors = ancestor_types(node_id)

                if node_type == "TEXT_CONDITION" and semantic_type == "optional_table_presence":
                    for index, table_id in enumerate(table_ids):
                        context = "required_table_with_optional_companion" if index == 0 else "optional_companion_table"
                        output[(adrg, table_id)].append({
                            "context": context,
                            "display_label": "필수 TABLE" if index == 0 else "시행 여부 무관",
                            "condition_ast_id": ast_id,
                            "node_id": node_id,
                            "source_fragment": fragment,
                            "semantic_type": semantic_type,
                            "evaluation_mode": evaluation_mode,
                        })
                        summary[context] += 1
                    continue

                allowed = False
                if node_type == "TABLE_REF":
                    parent_id = parent_by_child.get(node_id, "")
                    parent = nodes.get(parent_id)
                    if parent and str(parent.get("node_type") or "") == "EXCLUSION":
                        children = [str(x) for x in parent.get("child_node_ids") or []]
                        if len(children) >= 2 and children[1] == node_id:
                            base = nodes.get(children[0])
                            base_is_or = bool(
                                base
                                and str(base.get("node_type") or "") == "TEXT_CONDITION"
                                and str(base.get("semantic_type") or "") == "or_procedure"
                            )
                            allowed = base_is_or and "NOT" in ancestor_types(parent_id)

                if allowed:
                    context, label = "allowed_exception_under_negated_or_procedure", "OR procedure 허용 예외"
                elif "NOT" in ancestors or "EXCLUSION" in ancestors:
                    context, label = "negative_or_exclusion_reference", "제외 조건"
                elif node_type == "TEXT_CONDITION":
                    context, label = "semantic_text_condition", "의미 조건 TABLE"
                else:
                    context, label = "positive_required_table", "필수 TABLE"

                for table_id in table_ids:
                    output[(adrg, table_id)].append({
                        "context": context,
                        "display_label": label,
                        "condition_ast_id": ast_id,
                        "node_id": node_id,
                        "source_fragment": fragment,
                        "semantic_type": semantic_type or None,
                        "evaluation_mode": evaluation_mode or None,
                    })
                    summary[context] += 1

        cleaned = {
            key: sorted(values, key=lambda row: (
                str(row.get("context") or ""),
                str(row.get("condition_ast_id") or ""),
                str(row.get("node_id") or ""),
            ))
            for key, values in output.items()
        }
        summary["relationship_key_count"] = len(cleaned)
        summary["relationship_occurrence_count"] = sum(len(values) for values in cleaned.values())
        return cleaned, dict(sorted(summary.items()))

    def build_documents(self) -> dict[str, dict[str, Any]]:
        documents: dict[str, dict[str, Any]] = {}
        for entity_type, rows in self.records.items():
            id_field = self.id_fields[entity_type]
            for row in rows:
                entity_id = str(row.get(id_field) or "")
                title, subtitle = self.title_subtitle(entity_type, row)
                fields: dict[str, list[str]] = {
                    "entity_id": [entity_id],
                    "title": [title],
                    "subtitle": [subtitle],
                }
                if entity_type == "CODE":
                    fields.update({
                        "name": [str(x) for x in row.get("names") or []],
                        "role": [str(x) for x in row.get("roles") or []],
                        "table": [str(x) for x in row.get("logical_table_ids") or []],
                        "adrg": [str(x) for x in row.get("related_adrgs") or []],
                    })
                elif entity_type == "ADRG":
                    fields.update({
                        "name": [str(row.get("adrg_name") or "")],
                        "aadrg": [str(x) for x in row.get("aadrg_codes") or []],
                        "classification": [str(x) for x in row.get("abc_display_labels") or []],
                    })
                elif entity_type == "AADRG":
                    fields.update({
                        "name": [str(row.get("group_name") or "")],
                        "adrg": [str(row.get("adrg") or "")],
                        "rdrg": [str(x) for x in row.get("rdrg_codes") or []],
                        "classification": [str(row.get("classification_display_label") or "")],
                    })
                elif entity_type == "RDRG":
                    fields.update({
                        "name": [str(row.get("group_name") or ""), str(row.get("severity_name") or "")],
                        "aadrg": [str(row.get("aadrg") or "")],
                        "adrg": [str(row.get("adrg") or "")],
                    })
                else:
                    fields.update({
                        "name": [str(row.get("display_name") or "")],
                        "type": [str(row.get("logical_table_type") or ""), str(row.get("logical_table_scope") or "")],
                        "code": [str(x) for x in row.get("codes") or []],
                        "adrg": [str(x) for x in row.get("related_adrgs") or []],
                    })
                normalized = {
                    key: [normalize_query(value) for value in values if normalize_space(value)]
                    for key, values in fields.items()
                }
                flat = [value for values in normalized.values() for value in values]
                documents[f"{entity_type}:{entity_id}"] = {
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "title": title,
                    "subtitle": subtitle,
                    "fields": normalized,
                    "haystack": " ".join(flat),
                    "tokens": set(query_tokens(" ".join(flat))),
                }
        return documents

    def normalize_types(self, entity_type: str | Iterable[str] | None) -> list[str]:
        if entity_type is None or entity_type == "ALL":
            return list(ENTITY_TYPES)
        values = [entity_type] if isinstance(entity_type, str) else list(entity_type)
        output: list[str] = []
        for value in values:
            name = str(value or "").upper()
            if name == "ALL":
                return list(ENTITY_TYPES)
            if name not in ENTITY_TYPES:
                raise ValueError(name)
            if name not in output:
                output.append(name)
        if not output:
            raise ValueError("EMPTY")
        return output

    def match_document(self, document: dict[str, Any], query: str, tokens: list[str]) -> tuple[int, str, list[str]] | None:
        entity_type = document["entity_type"]
        entity_id = document["entity_id"]
        normalized_id = normalize_entity_id(entity_id, entity_type)
        input_id = normalize_entity_id(query, entity_type)
        q = normalize_query(query)
        fields: list[str] = []
        if input_id and input_id == normalized_id:
            return 1000, "EXACT_ID", ["entity_id"]
        for field, values in document["fields"].items():
            if q and q in values:
                fields.append(field)
        if fields:
            return 920, "EXACT_TEXT", sorted(set(fields))
        if input_id and normalized_id.startswith(input_id):
            return 840, "PREFIX_ID", ["entity_id"]
        if tokens and all(token in document["tokens"] for token in tokens):
            matched_fields = [
                field
                for field, values in document["fields"].items()
                if any(token in set(query_tokens(" ".join(values))) for token in tokens)
            ]
            return 760, "ALL_TOKENS", sorted(set(matched_fields)) or ["text"]
        if q and q in document["haystack"]:
            matched_fields = [field for field, values in document["fields"].items() if any(q in value for value in values)]
            return 680, "CONTAINS", sorted(set(matched_fields)) or ["text"]
        if tokens and any(token in document["tokens"] for token in tokens):
            matched = sum(token in document["tokens"] for token in tokens)
            return 500 + min(matched, 20), "ANY_TOKEN", ["text"]
        return None

    def adrg_mdc(self, adrg: str) -> str:
        row = self.maps["ADRG"].get(normalize_entity_id(adrg, "ADRG"))
        return str(row.get("mdc") or "").upper() if row else ""

    def adrg_aadrgs(self, adrg: str) -> list[str]:
        row = self.maps["ADRG"].get(normalize_entity_id(adrg, "ADRG"))
        return [str(x) for x in row.get("aadrg_codes") or []] if row else []

    def matches_mdc(self, entity_type: str, row: dict[str, Any], mdc: str) -> bool:
        if entity_type in {"ADRG", "AADRG"}:
            return str(row.get("mdc") or "").upper() == mdc
        if entity_type == "RDRG":
            return self.adrg_mdc(str(row.get("adrg") or "")) == mdc
        if entity_type in {"TABLE", "CODE"}:
            return any(self.adrg_mdc(str(adrg)) == mdc for adrg in row.get("related_adrgs") or [])
        return False

    def matches_classification(self, entity_type: str, row: dict[str, Any], classification: str) -> bool:
        accepted = {classification}
        accepted.add({"전문": "A", "일반": "B", "단순": "C"}.get(classification, classification))
        if entity_type == "AADRG":
            return str(row.get("classification_code") or "").upper() in accepted
        if entity_type == "ADRG":
            return bool({str(x).upper() for x in row.get("abc_classification_codes") or []} & accepted)
        if entity_type == "RDRG":
            aadrgs = [str(row.get("aadrg") or "")]
        elif entity_type == "TABLE":
            aadrgs = [aadrg for adrg in row.get("related_adrgs") or [] for aadrg in self.adrg_aadrgs(str(adrg))]
        elif entity_type == "CODE":
            aadrgs = [str(x) for x in row.get("related_aadrgs") or []]
        else:
            aadrgs = []
        return any(
            str((self.maps["AADRG"].get(normalize_entity_id(code, "AADRG")) or {}).get("classification_code") or "").upper() in accepted
            for code in aadrgs
        )

    def make_result(self, entity_type: str, entity_id: str, score: int, match_type: str, fields: list[str]) -> dict[str, Any]:
        row = self.maps[entity_type][normalize_entity_id(entity_id, entity_type)]
        title, subtitle = self.title_subtitle(entity_type, row)
        return {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "title": title,
            "subtitle": subtitle,
            "score": score,
            "match_type": match_type,
            "matched_fields": fields,
            "summary": self.summary_payload(entity_type, row),
        }

    def search(self, query: str, entity_type: str | Iterable[str] | None = "ALL", *, limit: int = 50, offset: int = 0, mdc: str | None = None, classification: str | None = None) -> dict[str, Any]:
        query_text = normalize_space(query)
        if not query_text or not 1 <= limit <= 500 or offset < 0:
            raise ValueError("INVALID")
        types = self.normalize_types(entity_type)
        tokens = query_tokens(query_text)
        mdc_filter = str(mdc or "").upper().strip()
        class_filter = str(classification or "").upper().strip()
        scored: list[tuple[int, str, str, list[str], str]] = []
        for document in self.documents.values():
            if document["entity_type"] not in types:
                continue
            row = self.maps[document["entity_type"]][normalize_entity_id(document["entity_id"], document["entity_type"])]
            if mdc_filter and not self.matches_mdc(document["entity_type"], row, mdc_filter):
                continue
            if class_filter and not self.matches_classification(document["entity_type"], row, class_filter):
                continue
            match = self.match_document(document, query_text, tokens)
            if match:
                score, match_type, fields = match
                scored.append((score, document["entity_type"], document["entity_id"], fields, match_type))
        scored.sort(key=lambda row: (-row[0], ENTITY_ORDER[row[1]], normalize_entity_id(row[2], row[1])))
        page = scored[offset: offset + limit]
        type_counts = Counter(row[1] for row in scored)
        results = [self.make_result(entity_type_, entity_id, score, match_type, fields) for score, entity_type_, entity_id, fields, match_type in page]
        return {
            "schema_version": RESPONSE_SCHEMA_VERSION,
            "query": query_text,
            "normalized_query": normalize_query(query_text),
            "filters": {"entity_types": types, "mdc": mdc_filter or None, "classification": class_filter or None},
            "total_count": len(scored),
            "type_counts": dict(sorted(type_counts.items(), key=lambda item: ENTITY_ORDER[item[0]])),
            "offset": offset,
            "limit": limit,
            "has_more": offset + len(results) < len(scored),
            "results": results,
        }

    def detail(self, entity_type: str, entity_id: str) -> dict[str, Any]:
        row = self.maps[entity_type][normalize_entity_id(entity_id, entity_type)]
        if entity_type == "CODE":
            table_details = []
            for table_id in row.get("logical_table_ids") or []:
                table = self.maps["TABLE"].get(normalize_entity_id(table_id, "TABLE"))
                if not table:
                    continue
                contexts = []
                for adrg in table.get("condition_adrgs") or []:
                    contexts.extend({"adrg": adrg, **item} for item in self.semantic_index.get((str(adrg), str(table_id)), []))
                table_details.append({
                    "logical_table_id": table_id,
                    "display_name": table.get("display_name"),
                    "logical_table_type": table.get("logical_table_type"),
                    "source_adrgs": deepcopy(table.get("source_adrgs") or []),
                    "condition_adrgs": deepcopy(table.get("condition_adrgs") or []),
                    "related_adrgs": deepcopy(table.get("related_adrgs") or []),
                    "source_adrg_families": deepcopy(table.get("source_adrg_families") or []),
                    "runtime_contexts": contexts,
                    "source_refs": deepcopy(table.get("source_refs") or []),
                })
            detail = {
                **deepcopy(row),
                "relation_sections": {
                    "physical_source": {
                        "adrgs": deepcopy(row.get("source_adrgs") or []),
                        "aadrgs": deepcopy(row.get("source_aadrgs") or []),
                        "family_refs": deepcopy(row.get("source_adrg_families") or []),
                        "display_label": "원문 TABLE 정의 위치",
                    },
                    "condition_usage": {
                        "adrgs": deepcopy(row.get("condition_adrgs") or []),
                        "aadrgs": deepcopy(row.get("condition_aadrgs") or []),
                        "display_label": "조건 AST 실제 사용 관계",
                    },
                    "runtime_related": {
                        "adrgs": deepcopy(row.get("related_adrgs") or []),
                        "aadrgs": deepcopy(row.get("related_aadrgs") or []),
                        "display_label": "검색용 통합 관계",
                    },
                },
                "logical_tables": table_details,
                "related_adrg_summaries": [self.summary_entity("ADRG", code) for code in row.get("related_adrgs") or []],
                "related_aadrg_summaries": [self.summary_entity("AADRG", code) for code in row.get("related_aadrgs") or []],
            }
        elif entity_type == "ADRG":
            detail = {
                **deepcopy(row),
                "aadrg_records": [self.summary_entity("AADRG", code) for code in row.get("aadrg_codes") or []],
                "logical_tables": [self.summary_entity("TABLE", code) for code in row.get("logical_table_ids") or []],
                "condition_ast": deepcopy(self.ast_map.get(str(row.get("condition_ast_id") or ""))),
            }
        elif entity_type == "AADRG":
            detail = {
                **deepcopy(row),
                "parent_adrg": self.summary_entity("ADRG", str(row.get("adrg") or "")),
                "rdrg_records": [self.summary_entity("RDRG", code) for code in row.get("rdrg_codes") or []],
            }
        elif entity_type == "RDRG":
            detail = {
                **deepcopy(row),
                "parent_aadrg": self.summary_entity("AADRG", str(row.get("aadrg") or "")),
                "parent_adrg": self.summary_entity("ADRG", str(row.get("adrg") or "")),
            }
        else:
            contexts = []
            for adrg in row.get("condition_adrgs") or []:
                contexts.extend({"adrg": adrg, **item} for item in self.semantic_index.get((str(adrg), str(row.get("logical_table_id") or "")), []))
            detail = {
                **deepcopy(row),
                "runtime_contexts": contexts,
                "source_adrg_summaries": [self.summary_entity("ADRG", code) for code in row.get("source_adrgs") or []],
                "condition_adrg_summaries": [self.summary_entity("ADRG", code) for code in row.get("condition_adrgs") or []],
                "related_adrg_summaries": [self.summary_entity("ADRG", code) for code in row.get("related_adrgs") or []],
                "code_records": [self.summary_entity("CODE", code) for code in row.get("codes") or []],
            }
        return {
            "schema_version": RESPONSE_SCHEMA_VERSION,
            "entity_type": entity_type,
            "entity_id": str(row.get(self.id_fields[entity_type]) or ""),
            "detail": detail,
        }


def build_report(payload: dict[str, Any]) -> str:
    validation = payload["validation"]
    corpus = payload["full_corpus_validation"]
    search = payload["search_validation"]
    detail = payload["detail_validation"]
    lines = [
        "KDRG V4.7 runtime adapter·검색 service 독립 전수검증 결과",
        "=" * 72,
        f"검증시각: {payload['generated_at']}",
        f"검증 스크립트 버전: {SCRIPT_VERSION}",
        "",
        "[현재 진행 위치]",
        "최종 통합 JSON V2와 runtime service 구축이 완료된 뒤 UI 연결 전에 검색 동작을 확정하는 단계",
        "service 내부 계산을 기대값으로 사용하지 않고 통합 JSON에서 검색 문서·순위·상세 응답을 별도 재구성함",
        "이번 단계에서는 service·통합 JSON·PySide UI를 수정하지 않음",
        "",
        "[원천자료 SHA256]",
        f"integrated_json: {payload['input_hashes']['integrated_json']}",
        f"runtime_service: {payload['input_hashes']['runtime_service']}",
        f"runtime_build_report: {payload['input_hashes']['runtime_build_report']}",
        "",
        "[전체 corpus runtime 재구성]",
        f"전체 검색 entity: {corpus['entity_count']}",
        f"ADRG/AADRG/RDRG/TABLE/CODE: {corpus['entity_counts']['ADRG']} / {corpus['entity_counts']['AADRG']} / {corpus['entity_counts']['RDRG']} / {corpus['entity_counts']['TABLE']} / {corpus['entity_counts']['CODE']}",
        f"독립 search document: {corpus['document_count']}",
        f"search document 불일치: {corpus['document_mismatch_count']}",
        f"title·subtitle 불일치: {corpus['title_mismatch_count']}",
        f"summary 불일치: {corpus['summary_mismatch_count']}",
        f"record map 불일치: {corpus['record_map_mismatch_count']}",
        "",
        "[runtime 의미 context 독립검증]",
        f"relation key: {corpus['semantic_context_counts'].get('relationship_key_count', 0)}",
        f"relation occurrence: {corpus['semantic_context_counts'].get('relationship_occurrence_count', 0)}",
        f"허용 예외: {corpus['semantic_context_counts'].get('allowed_exception_under_negated_or_procedure', 0)}",
        f"시행 여부 무관: {corpus['semantic_context_counts'].get('optional_companion_table', 0)}",
        f"선택 동반 필수 TABLE: {corpus['semantic_context_counts'].get('required_table_with_optional_companion', 0)}",
        f"semantic index 불일치: {corpus['semantic_index_mismatch_count']}",
        "",
        "[검색 순위·필터 독립검증]",
        f"검증 scenario: {search['scenario_count']}",
        f"전체 응답 불일치: {search['response_mismatch_count']}",
        f"exact/prefix/text/token 검색을 별도 matcher로 재계산함",
        f"MDC·A/B/C·entity type·pagination 조합을 포함함",
        "",
        "[상세 응답 전수검증]",
        f"전체 상세조회: {detail['detail_count']}",
        f"ADRG/AADRG/RDRG/TABLE/CODE: {detail['detail_counts']['ADRG']} / {detail['detail_counts']['AADRG']} / {detail['detail_counts']['RDRG']} / {detail['detail_counts']['TABLE']} / {detail['detail_counts']['CODE']}",
        f"상세 응답 불일치: {detail['detail_mismatch_count']}",
        f"응답 schema 오류: {detail['schema_error_count']}",
        "physical source·condition usage·runtime related 관계를 분리해 전수 대조함",
        "",
        "[오류 처리·불변성]",
        f"오류 처리 검증: {payload['error_validation']['pass_count']} / {payload['error_validation']['case_count']}",
        f"통합 JSON 변경: {payload['source_modified']}",
        f"runtime service 변경: {payload['service_modified']}",
        "",
        "[검증 항목 집계]",
        f"PASS: {validation['pass_count']}",
        f"FAIL: {validation['fail_count']}",
        f"TOTAL: {validation['total_count']}",
        "사용자 판단 필요: 0",
        "사용자 수동 Excel 검토: 없음",
        "",
        "[생성 파일]",
        str(REPORT_TXT_PATH),
        str(REPORT_JSON_PATH),
        "",
        "[다음 단계]",
        "독립검증 PASS 후 현재 PySide UI의 데이터 로더를 KdrgSearchService로 교체함",
        "UI에서는 코드·ADRG·AADRG·TABLE 검색 결과와 physical/condition/runtime 관계를 구분해 표시함",
        "",
        "[최종 결과]",
        f"전체 결과: {validation['status']}",
    ]
    failed = [row for row in validation["checks"] if row["status"] == "FAIL"]
    if failed:
        lines.extend(["", "[FAIL 상세]"])
        lines.extend(f"- {row['check_id']} {row['name']} | {row['detail']}" for row in failed)
    return "\n".join(lines) + "\n"


def main() -> int:
    checker = Checker()
    checker.check("V001", "통합 JSON 존재", DATA_PATH.exists(), str(DATA_PATH))
    checker.check("V002", "runtime service 존재", SERVICE_PATH.exists(), str(SERVICE_PATH))
    checker.check("V003", "39번 build report 존재", BUILD_REPORT_PATH.exists(), str(BUILD_REPORT_PATH))
    if not DATA_PATH.exists() or not SERVICE_PATH.exists() or not BUILD_REPORT_PATH.exists():
        result = checker.summary()
        payload = {
            "script_version": SCRIPT_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "input_hashes": {"integrated_json": "", "runtime_service": "", "runtime_build_report": ""},
            "full_corpus_validation": {"entity_count": 0, "entity_counts": {}, "document_count": 0, "document_mismatch_count": 0, "title_mismatch_count": 0, "summary_mismatch_count": 0, "record_map_mismatch_count": 0, "semantic_context_counts": {}, "semantic_index_mismatch_count": 0},
            "search_validation": {"scenario_count": 0, "response_mismatch_count": 0},
            "detail_validation": {"detail_count": 0, "detail_counts": {}, "detail_mismatch_count": 0, "schema_error_count": 0},
            "error_validation": {"case_count": 0, "pass_count": 0},
            "source_modified": False,
            "service_modified": False,
            "validation": result,
        }
        atomic_write_json(REPORT_JSON_PATH, payload)
        atomic_write_text(REPORT_TXT_PATH, build_report(payload))
        print(f"[FAIL] runtime 검색 service 독립 전수검증 실패: {result['pass_count']} PASS / {result['fail_count']} FAIL")
        return 1

    data_hash_before = sha256_file(DATA_PATH)
    service_hash_before = sha256_file(SERVICE_PATH)
    data = read_json(DATA_PATH)
    build_payload = read_json(BUILD_REPORT_PATH)
    build_validation = build_payload.get("validation") or {}
    build_outputs = build_payload.get("outputs") or {}

    checker.check("V004", "통합 schema V2", (data.get("meta") or {}).get("schema_version") == SUPPORTED_DATA_SCHEMA, str((data.get("meta") or {}).get("schema_version")))
    checker.check("V005", "통합 validation PASS", (data.get("validation") or {}).get("status") == "PASS", str((data.get("validation") or {}).get("status")))
    checker.check("V006", "39번 build PASS", build_validation.get("status") == "PASS", str(build_validation.get("status")))
    checker.check("V007", "39번 65 PASS", build_validation.get("pass_count") == 65, str(build_validation.get("pass_count")))
    checker.check("V008", "39번 0 FAIL", build_validation.get("fail_count") == 0, str(build_validation.get("fail_count")))
    checker.check("V009", "39번 service hash 일치", service_hash_before == str(build_outputs.get("service_sha256") or ""), f"actual={service_hash_before} expected={build_outputs.get('service_sha256')}")
    checker.check("V010", "39번 integrated hash 일치", data_hash_before == str((build_payload.get("input") or {}).get("integrated_json_sha256") or ""), f"actual={data_hash_before} expected={(build_payload.get('input') or {}).get('integrated_json_sha256')}")

    module = load_module("kdrg_runtime_service_independent_validation", SERVICE_PATH)
    checker.check("V011", "service schema constant", getattr(module, "SERVICE_SCHEMA_VERSION", None) == SERVICE_SCHEMA_VERSION, str(getattr(module, "SERVICE_SCHEMA_VERSION", None)))
    checker.check("V012", "response schema constant", getattr(module, "RESPONSE_SCHEMA_VERSION", None) == RESPONSE_SCHEMA_VERSION, str(getattr(module, "RESPONSE_SCHEMA_VERSION", None)))
    checker.check("V013", "supported data schema constant", getattr(module, "SUPPORTED_DATA_SCHEMA", None) == SUPPORTED_DATA_SCHEMA, str(getattr(module, "SUPPORTED_DATA_SCHEMA", None)))

    independent = IndependentRuntimeModel(data)
    service = module.KdrgSearchService(DATA_PATH)
    status = service.status()
    checker.check("V014", "service ready", status.get("ready") is True, str(status.get("ready")))
    checker.check("V015", "status service schema", status.get("service_schema_version") == SERVICE_SCHEMA_VERSION, str(status.get("service_schema_version")))
    checker.check("V016", "status response schema", status.get("response_schema_version") == RESPONSE_SCHEMA_VERSION, str(status.get("response_schema_version")))
    checker.check("V017", "status data schema", status.get("data_schema_version") == SUPPORTED_DATA_SCHEMA, str(status.get("data_schema_version")))
    checker.check("V018", "status counts exact", status.get("counts") == (data.get("meta") or {}).get("counts"), stable_hash(status.get("counts")))
    checker.check("V019", "status policies exact", status.get("policies") == (data.get("meta") or {}).get("policies"), stable_hash(status.get("policies")))

    entity_counts = {entity_type: len(rows) for entity_type, rows in independent.records.items()}
    expected_counts = {"ADRG": 1132, "AADRG": 1233, "RDRG": 2699, "TABLE": 1308, "CODE": 16571}
    for index, entity_type in enumerate(("ADRG", "AADRG", "RDRG", "TABLE", "CODE"), start=20):
        checker.check(f"V{index:03d}", f"{entity_type} count", entity_counts[entity_type] == expected_counts[entity_type], str(entity_counts[entity_type]))
    entity_count = sum(entity_counts.values())
    checker.check("V025", "전체 entity count", entity_count == 22943, str(entity_count))
    checker.check("V026", "독립 document count", len(independent.documents) == entity_count, str(len(independent.documents)))
    checker.check("V027", "service document count", len(service._search_documents) == entity_count, str(len(service._search_documents)))

    map_mismatches = 0
    title_mismatches = 0
    summary_mismatches = 0
    document_mismatches = 0
    per_type_mismatch: dict[str, dict[str, int]] = {}
    for entity_type, rows in independent.records.items():
        id_field = independent.id_fields[entity_type]
        counters = Counter()
        service_map = service._record_maps[entity_type]
        for row in rows:
            entity_id = str(row.get(id_field) or "")
            normalized = normalize_entity_id(entity_id, entity_type)
            if service_map.get(normalized) != row:
                map_mismatches += 1
                counters["record_map"] += 1
            if service._title_subtitle(entity_type, row) != independent.title_subtitle(entity_type, row):
                title_mismatches += 1
                counters["title"] += 1
            if service._summary_payload(entity_type, row) != independent.summary_payload(entity_type, row):
                summary_mismatches += 1
                counters["summary"] += 1
            key = f"{entity_type}:{entity_id}"
            actual_document = service._search_documents.get(key)
            expected_document = independent.documents.get(key)
            if actual_document != expected_document:
                document_mismatches += 1
                counters["document"] += 1
        per_type_mismatch[entity_type] = dict(counters)

    checker.check("V028", "record map 전수 일치", map_mismatches == 0, str(map_mismatches))
    checker.check("V029", "title·subtitle 전수 일치", title_mismatches == 0, str(title_mismatches))
    checker.check("V030", "summary 전수 일치", summary_mismatches == 0, str(summary_mismatches))
    checker.check("V031", "search document 전수 일치", document_mismatches == 0, str(document_mismatches))
    checker.check("V032", "search document key 집합 일치", set(service._search_documents) == set(independent.documents), f"actual={len(service._search_documents)} expected={len(independent.documents)}")
    checker.check("V033", "search document canonical hash", stable_hash({k: {**v, 'tokens': sorted(v['tokens'])} for k, v in service._search_documents.items()}) == stable_hash({k: {**v, 'tokens': sorted(v['tokens'])} for k, v in independent.documents.items()}), "full corpus")

    semantic_actual = service._semantic_context_index
    semantic_expected = independent.semantic_index
    semantic_keys = set(semantic_actual) | set(semantic_expected)
    semantic_mismatch = sum(semantic_actual.get(key) != semantic_expected.get(key) for key in semantic_keys)
    checker.check("V034", "semantic relation key count 906", len(semantic_expected) == 906, str(len(semantic_expected)))
    checker.check("V035", "semantic index 전수 일치", semantic_mismatch == 0, str(semantic_mismatch))
    checker.check("V036", "semantic summary 전수 일치", service._semantic_context_summary == independent.semantic_summary, f"actual={service._semantic_context_summary} expected={independent.semantic_summary}")
    checker.check("V037", "허용 예외 context 19", independent.semantic_summary.get("allowed_exception_under_negated_or_procedure") == 19, str(independent.semantic_summary))
    checker.check("V038", "시행 여부 무관 context 7", independent.semantic_summary.get("optional_companion_table") == 7, str(independent.semantic_summary))
    checker.check("V039", "선택 동반 필수 context 7", independent.semantic_summary.get("required_table_with_optional_companion") == 7, str(independent.semantic_summary))
    checker.check("V040", "semantic status counts 일치", status.get("semantic_context_counts") == independent.semantic_summary, stable_hash(status.get("semantic_context_counts")))

    # Search scenarios are independently reconstructed from the integrated JSON.
    scenarios = [
        {"name": "ADRG exact", "query": "9600", "entity_type": "ADRG"},
        {"name": "AADRG exact", "query": "96000", "entity_type": "AADRG"},
        {"name": "RDRG exact", "query": "960000", "entity_type": "RDRG"},
        {"name": "TABLE exact", "query": "LT_9610_001", "entity_type": "TABLE"},
        {"name": "CODE exact", "query": "A000", "entity_type": "CODE"},
        {"name": "CODE punctuation", "query": "A00.0", "entity_type": "CODE"},
        {"name": "ALL Korean", "query": "조기 사망", "entity_type": "ALL", "limit": 20},
        {"name": "ALL token", "query": "주요 문제", "entity_type": "ALL", "limit": 30},
        {"name": "prefix ADRG", "query": "I76", "entity_type": "ADRG", "limit": 30},
        {"name": "entity list", "query": "9600", "entity_type": ["ADRG", "AADRG"], "limit": 30},
        {"name": "MDC PRE", "query": "사망", "entity_type": "ALL", "mdc": "PRE", "limit": 50},
        {"name": "classification B", "query": "9600", "entity_type": "ADRG", "classification": "B"},
        {"name": "classification Korean", "query": "9600", "entity_type": "ADRG", "classification": "일반"},
        {"name": "classification excluded", "query": "9600", "entity_type": "ADRG", "classification": "A"},
        {"name": "pagination first", "query": "사망", "entity_type": "ALL", "limit": 3, "offset": 0},
        {"name": "pagination second", "query": "사망", "entity_type": "ALL", "limit": 3, "offset": 3},
        {"name": "X04 relation code", "query": "S710", "entity_type": "CODE"},
        {"name": "mixed classification", "query": "I760", "entity_type": "ADRG"},
        {"name": "optional table", "query": "LT_C064_003", "entity_type": "TABLE"},
        {"name": "allowed table", "query": "LT_P602_002", "entity_type": "TABLE"},
    ]
    search_mismatches: list[dict[str, Any]] = []
    for scenario in scenarios:
        kwargs = {key: value for key, value in scenario.items() if key not in {"name", "query", "entity_type"}}
        actual = service.search(scenario["query"], scenario["entity_type"], **kwargs)
        expected = independent.search(scenario["query"], scenario["entity_type"], **kwargs)
        if actual != expected:
            search_mismatches.append({
                "name": scenario["name"],
                "actual_hash": stable_hash(actual),
                "expected_hash": stable_hash(expected),
                "actual_top": [(row.get("entity_type"), row.get("entity_id"), row.get("score"), row.get("match_type")) for row in actual.get("results") or []][:10],
                "expected_top": [(row.get("entity_type"), row.get("entity_id"), row.get("score"), row.get("match_type")) for row in expected.get("results") or []][:10],
            })
    checker.check("V041", "검색 scenario 수 20", len(scenarios) == 20, str(len(scenarios)))
    checker.check("V042", "검색 응답 전수 일치", not search_mismatches, json.dumps(search_mismatches[:3], ensure_ascii=False))

    # Explicit ranking and response checks.
    exact = service.search("A00.0", "CODE")
    checker.check("V043", "코드 정규화 exact ID", bool(exact["results"]) and exact["results"][0]["entity_id"] == "A000", str(exact["results"][:1]))
    checker.check("V044", "exact score 1000", bool(exact["results"]) and exact["results"][0]["score"] == 1000, str(exact["results"][:1]))
    checker.check("V045", "exact match type", bool(exact["results"]) and exact["results"][0]["match_type"] == "EXACT_ID", str(exact["results"][:1]))
    prefix = service.search("I76", "ADRG", limit=30)
    checker.check("V046", "prefix 결과 존재", prefix["total_count"] > 0, str(prefix["total_count"]))
    checker.check("V047", "prefix 정렬 결정성", [row["entity_id"] for row in prefix["results"]] == sorted([row["entity_id"] for row in prefix["results"]], key=lambda x: normalize_entity_id(x, "ADRG")), str([row["entity_id"] for row in prefix["results"]]))
    korean = service.search("조기 사망", "ALL", limit=20)
    checker.check("V048", "한글 token 검색 ADRG 9600", any(row["entity_type"] == "ADRG" and row["entity_id"] == "9600" for row in korean["results"]), str([(r['entity_type'], r['entity_id']) for r in korean['results']]))
    checker.check("V049", "type_counts 합계", sum(korean["type_counts"].values()) == korean["total_count"], str(korean["type_counts"]))
    page1 = service.search("사망", "ALL", limit=3, offset=0)
    page2 = service.search("사망", "ALL", limit=3, offset=3)
    checker.check("V050", "pagination 중복 없음", not ({(r['entity_type'], r['entity_id']) for r in page1['results']} & {(r['entity_type'], r['entity_id']) for r in page2['results']}), "first/second")
    checker.check("V051", "pagination total 유지", page1["total_count"] == page2["total_count"], f"{page1['total_count']} / {page2['total_count']}")
    checker.check("V052", "pagination offset 반영", page2["offset"] == 3, str(page2["offset"]))
    checker.check("V053", "MDC 필터 응답 일치", service.search("사망", "ALL", mdc="PRE", limit=50) == independent.search("사망", "ALL", mdc="PRE", limit=50), "PRE")
    checker.check("V054", "A/B/C 영문 필터 일치", service.search("9600", "ADRG", classification="B") == independent.search("9600", "ADRG", classification="B"), "B")
    checker.check("V055", "A/B/C 한글 필터 일치", service.search("9600", "ADRG", classification="일반") == independent.search("9600", "ADRG", classification="일반"), "일반")

    detail_mismatches: list[dict[str, Any]] = []
    schema_errors = 0
    detail_counts: Counter[str] = Counter()
    for entity_type in ("ADRG", "AADRG", "RDRG", "TABLE", "CODE"):
        id_field = independent.id_fields[entity_type]
        for row in independent.records[entity_type]:
            entity_id = str(row.get(id_field) or "")
            actual = service.get_detail(entity_type, entity_id)
            expected = independent.detail(entity_type, entity_id)
            detail_counts[entity_type] += 1
            if actual.get("schema_version") != RESPONSE_SCHEMA_VERSION or actual.get("entity_type") != entity_type or actual.get("entity_id") != entity_id:
                schema_errors += 1
            if actual != expected:
                if len(detail_mismatches) < 20:
                    detail_mismatches.append({
                        "entity_type": entity_type,
                        "entity_id": entity_id,
                        "actual_hash": stable_hash(actual),
                        "expected_hash": stable_hash(expected),
                    })
    detail_count = sum(detail_counts.values())
    checker.check("V056", "상세조회 전수 22943", detail_count == 22943, str(detail_count))
    checker.check("V057", "상세 응답 schema 오류 0", schema_errors == 0, str(schema_errors))
    checker.check("V058", "상세 응답 전수 일치", not detail_mismatches, json.dumps(detail_mismatches[:5], ensure_ascii=False))
    for offset, entity_type in enumerate(("ADRG", "AADRG", "RDRG", "TABLE", "CODE"), start=59):
        checker.check(f"V{offset:03d}", f"{entity_type} 상세 전수", detail_counts[entity_type] == expected_counts[entity_type], str(detail_counts[entity_type]))

    # Cross-reference separation and policy checks.
    s710 = service.get_detail("CODE", "S710")["detail"]["relation_sections"]
    checker.check("V064", "S710 physical source", s710["physical_source"]["adrgs"] == ["X012", "X030", "X600"], str(s710["physical_source"]))
    checker.check("V065", "S710 condition usage", s710["condition_usage"]["adrgs"] == ["X011", "X012", "X041", "X042"], str(s710["condition_usage"]))
    checker.check("V066", "S710 runtime related", s710["runtime_related"]["adrgs"] == ["X011", "X012", "X030", "X041", "X042", "X600"], str(s710["runtime_related"]))
    checker.check("V067", "X04 family provenance", s710["physical_source"]["family_refs"] == ["X04"], str(s710["physical_source"]))
    checker.check("V068", "X04 ADRG 노출 금지", "X04" not in s710["runtime_related"]["adrgs"], str(s710["runtime_related"]))
    optional = service.get_detail("TABLE", "LT_C064_003")["detail"].get("runtime_contexts") or []
    allowed = service.get_detail("TABLE", "LT_P602_002")["detail"].get("runtime_contexts") or []
    checker.check("V069", "선택 동반 context", any(row.get("context") == "optional_companion_table" for row in optional), str(optional[:4]))
    checker.check("V070", "허용 예외 context", any(row.get("context") == "allowed_exception_under_negated_or_procedure" for row in allowed), str(allowed[:4]))
    unclassified = service.get_detail("AADRG", "99000")["detail"]
    checker.check("V071", "미분류 AADRG 보존", unclassified.get("classification_code") is None and bool(unclassified.get("abc_unclassified_provenance")), str(unclassified.get("abc_unclassified_provenance")))
    mixed = service.get_detail("ADRG", "I760")["detail"]
    checker.check("V072", "혼합 분류 ADRG 보존", len(set(mixed.get("abc_classification_codes") or [])) >= 2, str(mixed.get("abc_classification_codes")))

    # Full relation integrity as consumed by the service.
    adrg_ids = {str(row.get("adrg") or "") for row in data.get("adrg_records") or []}
    aadrg_ids = {str(row.get("aadrg") or "") for row in data.get("aadrg_records") or []}
    table_ids = {str(row.get("logical_table_id") or "") for row in data.get("logical_table_records") or []}
    missing_code_tables = sum(table_id not in table_ids for row in data.get("code_records") or [] for table_id in row.get("logical_table_ids") or [])
    missing_code_adrgs = sum(adrg not in adrg_ids for row in data.get("code_records") or [] for adrg in row.get("related_adrgs") or [])
    missing_code_aadrgs = sum(aadrg not in aadrg_ids for row in data.get("code_records") or [] for aadrg in row.get("related_aadrgs") or [])
    missing_table_adrgs = sum(adrg not in adrg_ids for row in data.get("logical_table_records") or [] for adrg in row.get("related_adrgs") or [])
    checker.check("V073", "CODE→TABLE 미등록 0", missing_code_tables == 0, str(missing_code_tables))
    checker.check("V074", "CODE→ADRG 미등록 0", missing_code_adrgs == 0, str(missing_code_adrgs))
    checker.check("V075", "CODE→AADRG 미등록 0", missing_code_aadrgs == 0, str(missing_code_aadrgs))
    checker.check("V076", "TABLE→ADRG 미등록 0", missing_table_adrgs == 0, str(missing_table_adrgs))

    error_cases = [
        ("빈 검색어", lambda: service.search("   ")),
        ("limit 0", lambda: service.search("A000", limit=0)),
        ("limit 501", lambda: service.search("A000", limit=501)),
        ("offset 음수", lambda: service.search("A000", offset=-1)),
        ("잘못된 검색 유형", lambda: service.search("A000", "INVALID")),
        ("빈 검색 유형 배열", lambda: service.search("A000", [])),
        ("잘못된 상세 유형", lambda: service.get_detail("INVALID", "A000")),
        ("없는 상세 ID", lambda: service.get_detail("CODE", "NOT_A_REAL_CODE")),
    ]
    error_pass = 0
    for name, function in error_cases:
        try:
            function()
        except module.KdrgSearchError:
            error_pass += 1
        except Exception:
            pass
    checker.check("V077", "오류 처리 8/8", error_pass == len(error_cases), f"{error_pass}/{len(error_cases)}")
    checker.check("V078", "검색 응답 JSON 직렬화", bool(json.dumps(service.search("조기 사망", "ALL", limit=20), ensure_ascii=False)), "PASS")
    checker.check("V079", "상세 응답 JSON 직렬화", bool(json.dumps(service.get_detail("CODE", "S710"), ensure_ascii=False)), "PASS")

    data_hash_after = sha256_file(DATA_PATH)
    service_hash_after = sha256_file(SERVICE_PATH)
    checker.check("V080", "통합 JSON 미수정", data_hash_after == data_hash_before, f"before={data_hash_before} after={data_hash_after}")
    checker.check("V081", "runtime service 미수정", service_hash_after == service_hash_before, f"before={service_hash_before} after={service_hash_after}")

    # Fixed policy counts and response schema checks.
    checker.check("V082", "runtime expanded TABLE 417", (data.get("meta") or {}).get("counts", {}).get("tables_with_runtime_relation_expansion") == 417, str((data.get("meta") or {}).get("counts", {}).get("tables_with_runtime_relation_expansion")))
    checker.check("V083", "runtime expanded CODE 9122", (data.get("meta") or {}).get("counts", {}).get("codes_with_runtime_relation_expansion") == 9122, str((data.get("meta") or {}).get("counts", {}).get("codes_with_runtime_relation_expansion")))
    checker.check("V084", "TABLE→ADRG relation 1856", (data.get("meta") or {}).get("counts", {}).get("table_related_adrg_relation_count") == 1856, str((data.get("meta") or {}).get("counts", {}).get("table_related_adrg_relation_count")))
    checker.check("V085", "CODE→ADRG relation 90191", (data.get("meta") or {}).get("counts", {}).get("code_related_adrg_relation_count") == 90191, str((data.get("meta") or {}).get("counts", {}).get("code_related_adrg_relation_count")))
    checker.check("V086", "CODE→AADRG relation 100321", (data.get("meta") or {}).get("counts", {}).get("code_related_aadrg_relation_count") == 100321, str((data.get("meta") or {}).get("counts", {}).get("code_related_aadrg_relation_count")))
    checker.check("V087", "검색 token 19478", (data.get("meta") or {}).get("counts", {}).get("search_token_count") == 19478, str((data.get("meta") or {}).get("counts", {}).get("search_token_count")))
    checker.check("V088", "AST node 1727", (data.get("meta") or {}).get("counts", {}).get("ast_node_count") == 1727, str((data.get("meta") or {}).get("counts", {}).get("ast_node_count")))

    # Add deterministic per-type canonical hash checks.
    for offset, entity_type in enumerate(("ADRG", "AADRG", "RDRG", "TABLE", "CODE"), start=89):
        actual_map = {
            key: value for key, value in service._record_maps[entity_type].items()
        }
        expected_map = independent.maps[entity_type]
        checker.check(f"V{offset:03d}", f"{entity_type} record map hash", stable_hash(actual_map) == stable_hash(expected_map), f"actual={stable_hash(actual_map)} expected={stable_hash(expected_map)}")

    # Independent match category coverage from selected scenarios.
    observed_match_types: set[str] = set()
    for scenario in scenarios:
        kwargs = {key: value for key, value in scenario.items() if key not in {"name", "query", "entity_type"}}
        response = independent.search(scenario["query"], scenario["entity_type"], **kwargs)
        observed_match_types.update(str(row.get("match_type") or "") for row in response.get("results") or [])
    checker.check("V094", "EXACT_ID matcher 검증", "EXACT_ID" in observed_match_types, str(sorted(observed_match_types)))
    checker.check("V095", "PREFIX_ID matcher 검증", "PREFIX_ID" in observed_match_types, str(sorted(observed_match_types)))
    checker.check("V096", "token matcher 검증", bool({"ALL_TOKENS", "ANY_TOKEN"} & observed_match_types), str(sorted(observed_match_types)))
    checker.check("V097", "검색 response schema 전수", all(service.search(s["query"], s["entity_type"], **{k:v for k,v in s.items() if k not in {"name","query","entity_type"}}).get("schema_version") == RESPONSE_SCHEMA_VERSION for s in scenarios), RESPONSE_SCHEMA_VERSION)
    checker.check("V098", "검색 결과 score 내림차순", all(all(response["results"][i]["score"] >= response["results"][i+1]["score"] for i in range(len(response["results"])-1)) for response in [service.search(s["query"], s["entity_type"], **{k:v for k,v in s.items() if k not in {"name","query","entity_type"}}) for s in scenarios]), "20 scenarios")

    result = checker.summary()
    payload = {
        "script_version": SCRIPT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "input_hashes": {
            "integrated_json": data_hash_before,
            "runtime_service": service_hash_before,
            "runtime_build_report": sha256_file(BUILD_REPORT_PATH),
        },
        "full_corpus_validation": {
            "entity_count": entity_count,
            "entity_counts": entity_counts,
            "document_count": len(independent.documents),
            "document_mismatch_count": document_mismatches,
            "title_mismatch_count": title_mismatches,
            "summary_mismatch_count": summary_mismatches,
            "record_map_mismatch_count": map_mismatches,
            "per_type_mismatch": per_type_mismatch,
            "semantic_context_counts": independent.semantic_summary,
            "semantic_index_mismatch_count": semantic_mismatch,
        },
        "search_validation": {
            "scenario_count": len(scenarios),
            "response_mismatch_count": len(search_mismatches),
            "mismatches": search_mismatches,
            "scenarios": scenarios,
        },
        "detail_validation": {
            "detail_count": detail_count,
            "detail_counts": dict(detail_counts),
            "detail_mismatch_count": len(detail_mismatches),
            "schema_error_count": schema_errors,
            "mismatches": detail_mismatches,
        },
        "error_validation": {"case_count": len(error_cases), "pass_count": error_pass},
        "source_modified": data_hash_after != data_hash_before,
        "service_modified": service_hash_after != service_hash_before,
        "validation": result,
        "user_judgment_required": 0,
        "manual_excel_review": False,
    }
    atomic_write_json(REPORT_JSON_PATH, payload)
    atomic_write_text(REPORT_TXT_PATH, build_report(payload))

    if result["status"] == "PASS":
        print(
            "[PASS] runtime adapter·검색 service 독립 전수검증 완료: "
            f"22943 details / 20 search scenarios / {result['pass_count']} PASS / 0 FAIL / 사용자 판단 0건"
        )
        print(f"report={REPORT_TXT_PATH}")
        return 0
    print(f"[FAIL] runtime adapter·검색 service 독립 전수검증 실패: {result['pass_count']} PASS / {result['fail_count']} FAIL")
    print(f"report={REPORT_TXT_PATH}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
