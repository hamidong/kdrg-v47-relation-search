from __future__ import annotations

import json
import re
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

SERVICE_SCHEMA_VERSION = "kdrg-runtime-search-service-v1"
RESPONSE_SCHEMA_VERSION = "kdrg-runtime-search-response-v1"
SUPPORTED_DATA_SCHEMA = "kdrg-v47-search-integrated-v2"
ENTITY_TYPES = ("CODE", "ADRG", "AADRG", "RDRG", "TABLE")
ENTITY_ORDER = {name: index for index, name in enumerate(ENTITY_TYPES)}
TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣_]+")
CODE_LIKE_RE = re.compile(r"^[A-Za-z0-9.\-\s]+$")


class KdrgSearchError(RuntimeError):
    pass


def _read_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except FileNotFoundError as exc:
        raise KdrgSearchError(f"통합 검색 데이터가 없습니다: {path}") from exc
    except json.JSONDecodeError as exc:
        raise KdrgSearchError(f"통합 검색 JSON을 읽을 수 없습니다: {path} | {exc}") from exc
    if not isinstance(payload, dict):
        raise KdrgSearchError(f"통합 검색 JSON 최상위 구조가 dict가 아닙니다: {path}")
    return payload


def _normalize_space(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_entity_id(value: Any, entity_type: str | None = None) -> str:
    text = _normalize_space(value).upper()
    if entity_type == "TABLE" or text.startswith("LT_"):
        return re.sub(r"[^A-Z0-9_]", "", text)
    return re.sub(r"[^A-Z0-9]", "", text)


def normalize_query(value: Any) -> str:
    return _normalize_space(value).casefold()


def query_tokens(value: Any) -> list[str]:
    tokens = [token.casefold() for token in TOKEN_RE.findall(_normalize_space(value))]
    output: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token and token not in seen:
            seen.add(token)
            output.append(token)
    return output


def _unique_strings(values: Iterable[Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "")
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return output


class KdrgSearchService:
    def __init__(self, data_path: str | Path | None = None) -> None:
        if data_path is None:
            data_path = Path(__file__).resolve().parents[1] / "data" / "kdrg_v47_search_integrated.json"
        self.data_path = Path(data_path).expanduser().resolve()
        self.data = _read_json(self.data_path)
        self._validate_data()
        self.meta = self.data["meta"]
        self.indexes = self.data["indexes"]
        self.runtime_semantic_rules = deepcopy(self.data.get("runtime_semantic_rules") or {})
        self._records = {
            "ADRG": self.data["adrg_records"],
            "AADRG": self.data["aadrg_records"],
            "RDRG": self.data["rdrg_records"],
            "TABLE": self.data["logical_table_records"],
            "CODE": self.data["code_records"],
        }
        self._id_fields = {
            "ADRG": "adrg",
            "AADRG": "aadrg",
            "RDRG": "code",
            "TABLE": "logical_table_id",
            "CODE": "code",
        }
        self._record_maps = {
            entity_type: {
                normalize_entity_id(row.get(self._id_fields[entity_type]), entity_type): row
                for row in rows
            }
            for entity_type, rows in self._records.items()
        }
        self._semantic_context_index, self._semantic_context_summary = self._build_semantic_context_index()
        self._search_documents = self._build_search_documents()

    def _validate_data(self) -> None:
        meta = self.data.get("meta") or {}
        schema = str(meta.get("schema_version") or "")
        if schema != SUPPORTED_DATA_SCHEMA:
            raise KdrgSearchError(
                f"지원하지 않는 통합 데이터 schema입니다: {schema or '<EMPTY>'} | expected={SUPPORTED_DATA_SCHEMA}"
            )
        required_lists = {
            "adrg_records",
            "aadrg_records",
            "rdrg_records",
            "logical_table_records",
            "condition_ast_records",
            "code_records",
        }
        missing = [key for key in sorted(required_lists) if not isinstance(self.data.get(key), list)]
        if missing:
            raise KdrgSearchError(f"통합 검색 JSON 필수 배열이 없습니다: {', '.join(missing)}")
        if not isinstance(self.data.get("indexes"), dict):
            raise KdrgSearchError("통합 검색 JSON indexes가 없습니다")
        validation = self.data.get("validation") or {}
        if str(validation.get("status") or "") != "PASS":
            raise KdrgSearchError("통합 검색 JSON 자체 validation 상태가 PASS가 아닙니다")

    def status(self) -> dict[str, Any]:
        return {
            "service_schema_version": SERVICE_SCHEMA_VERSION,
            "response_schema_version": RESPONSE_SCHEMA_VERSION,
            "data_schema_version": self.meta.get("schema_version"),
            "data_version": self.meta.get("data_version"),
            "data_state": self.meta.get("state"),
            "data_path": str(self.data_path),
            "counts": deepcopy(self.meta.get("counts") or {}),
            "policies": deepcopy(self.meta.get("policies") or {}),
            "semantic_context_counts": deepcopy(self._semantic_context_summary),
            "ready": True,
        }

    def _build_search_documents(self) -> dict[str, dict[str, Any]]:
        documents: dict[str, dict[str, Any]] = {}
        for entity_type, rows in self._records.items():
            id_field = self._id_fields[entity_type]
            for row in rows:
                entity_id = str(row.get(id_field) or "")
                title, subtitle = self._title_subtitle(entity_type, row)
                fields: dict[str, list[str]] = {
                    "entity_id": [entity_id],
                    "title": [title],
                    "subtitle": [subtitle],
                }
                if entity_type == "CODE":
                    fields["name"] = [str(x) for x in row.get("names") or []]
                    fields["role"] = [str(x) for x in row.get("roles") or []]
                    fields["table"] = [str(x) for x in row.get("logical_table_ids") or []]
                    fields["adrg"] = [str(x) for x in row.get("related_adrgs") or []]
                elif entity_type == "ADRG":
                    fields["name"] = [str(row.get("adrg_name") or "")]
                    fields["aadrg"] = [str(x) for x in row.get("aadrg_codes") or []]
                    fields["classification"] = [str(x) for x in row.get("abc_display_labels") or []]
                elif entity_type == "AADRG":
                    fields["name"] = [str(row.get("group_name") or "")]
                    fields["adrg"] = [str(row.get("adrg") or "")]
                    fields["rdrg"] = [str(x) for x in row.get("rdrg_codes") or []]
                    fields["classification"] = [str(row.get("classification_display_label") or "")]
                elif entity_type == "RDRG":
                    fields["name"] = [str(row.get("group_name") or ""), str(row.get("severity_name") or "")]
                    fields["aadrg"] = [str(row.get("aadrg") or "")]
                    fields["adrg"] = [str(row.get("adrg") or "")]
                elif entity_type == "TABLE":
                    fields["name"] = [str(row.get("display_name") or "")]
                    fields["type"] = [str(row.get("logical_table_type") or ""), str(row.get("logical_table_scope") or "")]
                    fields["code"] = [str(x) for x in row.get("codes") or []]
                    fields["adrg"] = [str(x) for x in row.get("related_adrgs") or []]
                normalized_fields = {
                    key: [normalize_query(value) for value in values if _normalize_space(value)]
                    for key, values in fields.items()
                }
                flat_values = [value for values in normalized_fields.values() for value in values]
                documents[f"{entity_type}:{entity_id}"] = {
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "title": title,
                    "subtitle": subtitle,
                    "fields": normalized_fields,
                    "haystack": " ".join(flat_values),
                    "tokens": set(query_tokens(" ".join(flat_values))),
                }
        return documents

    def _build_semantic_context_index(self) -> tuple[dict[tuple[str, str], list[dict[str, Any]]], dict[str, int]]:
        output: defaultdict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        summary = defaultdict(int)
        for ast in self.data.get("condition_ast_records") or []:
            adrg = str(ast.get("adrg") or "")
            ast_id = str(ast.get("condition_ast_id") or "")
            nodes = {
                str(node.get("node_id") or ""): node
                for node in ast.get("nodes") or []
                if str(node.get("node_id") or "")
            }

            def ancestors(node_id: str) -> list[dict[str, Any]]:
                found: list[dict[str, Any]] = []
                seen: set[str] = set()
                current = nodes.get(node_id)
                while current:
                    parent_id = str(current.get("parent_node_id") or "")
                    if not parent_id or parent_id in seen:
                        break
                    seen.add(parent_id)
                    parent = nodes.get(parent_id)
                    if parent is None:
                        break
                    found.append(parent)
                    current = parent
                return found

            for node in ast.get("nodes") or []:
                node_id = str(node.get("node_id") or "")
                node_type = str(node.get("node_type") or "")
                table_ids = _unique_strings(node.get("logical_table_ids") or [])
                if not table_ids:
                    continue
                fragment = str(node.get("source_fragment") or node.get("display_text") or "")
                semantic_type = str(node.get("semantic_type") or "")
                evaluation_mode = str(node.get("evaluation_mode") or "")
                ancestor_types = [str(item.get("node_type") or "") for item in ancestors(node_id)]

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

                allowed_exception = False
                if node_type == "TABLE_REF":
                    parent = nodes.get(str(node.get("parent_node_id") or ""))
                    if parent and str(parent.get("node_type") or "") == "EXCLUSION":
                        children = [str(x) for x in parent.get("child_node_ids") or []]
                        if len(children) >= 2 and children[1] == node_id:
                            base = nodes.get(children[0])
                            base_is_or = bool(
                                base
                                and str(base.get("node_type") or "") == "TEXT_CONDITION"
                                and str(base.get("semantic_type") or "") == "or_procedure"
                            )
                            parent_ancestor_types = [
                                str(item.get("node_type") or "")
                                for item in ancestors(str(parent.get("node_id") or ""))
                            ]
                            allowed_exception = base_is_or and "NOT" in parent_ancestor_types

                if allowed_exception:
                    context = "allowed_exception_under_negated_or_procedure"
                    display_label = "OR procedure 허용 예외"
                elif "NOT" in ancestor_types or "EXCLUSION" in ancestor_types:
                    context = "negative_or_exclusion_reference"
                    display_label = "제외 조건"
                elif node_type == "TEXT_CONDITION":
                    context = "semantic_text_condition"
                    display_label = "의미 조건 TABLE"
                else:
                    context = "positive_required_table"
                    display_label = "필수 TABLE"

                for table_id in table_ids:
                    output[(adrg, table_id)].append({
                        "context": context,
                        "display_label": display_label,
                        "condition_ast_id": ast_id,
                        "node_id": node_id,
                        "source_fragment": fragment,
                        "semantic_type": semantic_type or None,
                        "evaluation_mode": evaluation_mode or None,
                    })
                    summary[context] += 1

        cleaned = {
            key: sorted(
                values,
                key=lambda item: (
                    str(item.get("context") or ""),
                    str(item.get("condition_ast_id") or ""),
                    str(item.get("node_id") or ""),
                ),
            )
            for key, values in output.items()
        }
        summary["relationship_key_count"] = len(cleaned)
        summary["relationship_occurrence_count"] = sum(len(values) for values in cleaned.values())
        return cleaned, dict(sorted(summary.items()))

    def _title_subtitle(self, entity_type: str, row: dict[str, Any]) -> tuple[str, str]:
        if entity_type == "CODE":
            names = [str(x) for x in row.get("names") or [] if str(x)]
            title = str(row.get("code") or "")
            subtitle = " / ".join(names[:2]) if names else "코드명 원천 미수록"
        elif entity_type == "ADRG":
            title = f"{row.get('adrg', '')} · {row.get('adrg_name', '')}".strip(" ·")
            subtitle = f"MDC {row.get('mdc', '-')} · AADRG {row.get('aadrg_count', 0)}개"
        elif entity_type == "AADRG":
            title = f"{row.get('aadrg', '')} · {row.get('group_name', '')}".strip(" ·")
            label = str(row.get("classification_display_label") or "분류 미부여")
            subtitle = f"ADRG {row.get('adrg', '-')} · {label}"
        elif entity_type == "RDRG":
            title = f"{row.get('code', '')} · {row.get('group_name', '')}".strip(" ·")
            subtitle = f"AADRG {row.get('aadrg', '-')} · {row.get('severity_name') or '중증도 명칭 없음'}"
        else:
            title = str(row.get("display_name") or row.get("logical_table_id") or "")
            subtitle = f"코드 {row.get('code_count', 0)}개 · 관련 ADRG {len(row.get('related_adrgs') or [])}개"
        return title, subtitle

    def _normalize_entity_types(self, entity_type: str | Iterable[str] | None) -> list[str]:
        if entity_type is None or entity_type == "ALL":
            return list(ENTITY_TYPES)
        values = [entity_type] if isinstance(entity_type, str) else list(entity_type)
        output: list[str] = []
        for value in values:
            name = str(value or "").upper()
            if name == "ALL":
                return list(ENTITY_TYPES)
            if name not in ENTITY_TYPES:
                raise KdrgSearchError(f"지원하지 않는 검색 유형입니다: {value}")
            if name not in output:
                output.append(name)
        if not output:
            raise KdrgSearchError("검색 유형이 비어 있습니다")
        return output

    def _match_document(self, document: dict[str, Any], query: str, tokens: list[str]) -> tuple[int, str, list[str]] | None:
        entity_type = document["entity_type"]
        entity_id = document["entity_id"]
        normalized_id = normalize_entity_id(entity_id, entity_type)
        normalized_input_id = normalize_entity_id(query, entity_type)
        q = normalize_query(query)
        matched_fields: list[str] = []

        if normalized_input_id and normalized_input_id == normalized_id:
            return 1000, "EXACT_ID", ["entity_id"]

        for field, values in document["fields"].items():
            if q and q in values:
                matched_fields.append(field)
        if matched_fields:
            return 920, "EXACT_TEXT", sorted(set(matched_fields))

        if normalized_input_id and normalized_id.startswith(normalized_input_id):
            return 840, "PREFIX_ID", ["entity_id"]

        if tokens and all(token in document["tokens"] for token in tokens):
            fields = [
                field
                for field, values in document["fields"].items()
                if any(token in set(query_tokens(" ".join(values))) for token in tokens)
            ]
            return 760, "ALL_TOKENS", sorted(set(fields)) or ["text"]

        if q and q in document["haystack"]:
            fields = [field for field, values in document["fields"].items() if any(q in value for value in values)]
            return 680, "CONTAINS", sorted(set(fields)) or ["text"]

        if tokens and any(token in document["tokens"] for token in tokens):
            matched = sum(1 for token in tokens if token in document["tokens"])
            score = 500 + min(matched, 20)
            return score, "ANY_TOKEN", ["text"]
        return None

    def search(
        self,
        query: str,
        entity_type: str | Iterable[str] | None = "ALL",
        *,
        limit: int = 50,
        offset: int = 0,
        mdc: str | None = None,
        classification: str | None = None,
    ) -> dict[str, Any]:
        query_text = _normalize_space(query)
        if not query_text:
            raise KdrgSearchError("검색어를 입력해야 합니다")
        if limit < 1 or limit > 500:
            raise KdrgSearchError("limit은 1~500 범위여야 합니다")
        if offset < 0:
            raise KdrgSearchError("offset은 0 이상이어야 합니다")
        entity_types = self._normalize_entity_types(entity_type)
        tokens = query_tokens(query_text)
        mdc_filter = str(mdc or "").upper().strip()
        class_filter = str(classification or "").upper().strip()

        scored: list[tuple[int, str, str, list[str], str]] = []
        for key, document in self._search_documents.items():
            if document["entity_type"] not in entity_types:
                continue
            record = self._record_maps[document["entity_type"]][
                normalize_entity_id(document["entity_id"], document["entity_type"])
            ]
            if mdc_filter and not self._record_matches_mdc(document["entity_type"], record, mdc_filter):
                continue
            if class_filter and not self._record_matches_classification(document["entity_type"], record, class_filter):
                continue
            match = self._match_document(document, query_text, tokens)
            if match is None:
                continue
            score, match_type, fields = match
            scored.append((score, document["entity_type"], document["entity_id"], fields, match_type))

        scored.sort(
            key=lambda row: (
                -row[0],
                ENTITY_ORDER[row[1]],
                normalize_entity_id(row[2], row[1]),
            )
        )
        total_count = len(scored)
        page = scored[offset : offset + limit]
        results = [
            self._make_search_result(entity_type_, entity_id, score, match_type, fields)
            for score, entity_type_, entity_id, fields, match_type in page
        ]
        type_counts = defaultdict(int)
        for _, type_name, _, _, _ in scored:
            type_counts[type_name] += 1
        return {
            "schema_version": RESPONSE_SCHEMA_VERSION,
            "query": query_text,
            "normalized_query": normalize_query(query_text),
            "filters": {
                "entity_types": entity_types,
                "mdc": mdc_filter or None,
                "classification": class_filter or None,
            },
            "total_count": total_count,
            "type_counts": dict(sorted(type_counts.items(), key=lambda item: ENTITY_ORDER[item[0]])),
            "offset": offset,
            "limit": limit,
            "has_more": offset + len(results) < total_count,
            "results": results,
        }

    def _record_matches_mdc(self, entity_type: str, record: dict[str, Any], mdc: str) -> bool:
        if entity_type in {"ADRG", "AADRG"}:
            return str(record.get("mdc") or "").upper() == mdc
        if entity_type == "RDRG":
            parent = self._record_maps["ADRG"].get(normalize_entity_id(record.get("adrg"), "ADRG"))
            return bool(parent and str(parent.get("mdc") or "").upper() == mdc)
        if entity_type == "TABLE":
            return any(self._adrg_mdc(code) == mdc for code in record.get("related_adrgs") or [])
        if entity_type == "CODE":
            return any(self._adrg_mdc(code) == mdc for code in record.get("related_adrgs") or [])
        return False

    def _record_matches_classification(self, entity_type: str, record: dict[str, Any], classification: str) -> bool:
        accepted = {classification}
        mapping = {"전문": "A", "일반": "B", "단순": "C"}
        accepted.add(mapping.get(classification, classification))
        if entity_type == "AADRG":
            return str(record.get("classification_code") or "").upper() in accepted
        if entity_type == "ADRG":
            return bool(set(str(x).upper() for x in record.get("abc_classification_codes") or []) & accepted)
        aadrgs: list[str] = []
        if entity_type == "RDRG":
            aadrgs = [str(record.get("aadrg") or "")]
        elif entity_type == "TABLE":
            aadrgs = [a for adrg in record.get("related_adrgs") or [] for a in self._adrg_aadrgs(str(adrg))]
        elif entity_type == "CODE":
            aadrgs = [str(x) for x in record.get("related_aadrgs") or []]
        return any(
            str((self._record_maps["AADRG"].get(normalize_entity_id(code, "AADRG")) or {}).get("classification_code") or "").upper()
            in accepted
            for code in aadrgs
        )

    def _adrg_mdc(self, adrg: str) -> str:
        record = self._record_maps["ADRG"].get(normalize_entity_id(adrg, "ADRG"))
        return str(record.get("mdc") or "").upper() if record else ""

    def _adrg_aadrgs(self, adrg: str) -> list[str]:
        record = self._record_maps["ADRG"].get(normalize_entity_id(adrg, "ADRG"))
        return [str(x) for x in record.get("aadrg_codes") or []] if record else []

    def _make_search_result(
        self,
        entity_type: str,
        entity_id: str,
        score: int,
        match_type: str,
        matched_fields: list[str],
    ) -> dict[str, Any]:
        record = self._record_maps[entity_type][normalize_entity_id(entity_id, entity_type)]
        title, subtitle = self._title_subtitle(entity_type, record)
        result = {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "title": title,
            "subtitle": subtitle,
            "score": score,
            "match_type": match_type,
            "matched_fields": matched_fields,
            "summary": self._summary_payload(entity_type, record),
        }
        return result

    def _summary_payload(self, entity_type: str, row: dict[str, Any]) -> dict[str, Any]:
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

    def get_detail(self, entity_type: str, entity_id: str) -> dict[str, Any]:
        type_name = str(entity_type or "").upper()
        if type_name not in ENTITY_TYPES:
            raise KdrgSearchError(f"지원하지 않는 상세조회 유형입니다: {entity_type}")
        normalized_id = normalize_entity_id(entity_id, type_name)
        row = self._record_maps[type_name].get(normalized_id)
        if row is None:
            raise KdrgSearchError(f"상세조회 대상을 찾지 못했습니다: {type_name}:{entity_id}")
        if type_name == "CODE":
            detail = self._code_detail(row)
        elif type_name == "ADRG":
            detail = self._adrg_detail(row)
        elif type_name == "AADRG":
            detail = self._aadrg_detail(row)
        elif type_name == "RDRG":
            detail = self._rdrg_detail(row)
        else:
            detail = self._table_detail(row)
        return {
            "schema_version": RESPONSE_SCHEMA_VERSION,
            "entity_type": type_name,
            "entity_id": str(row.get(self._id_fields[type_name]) or ""),
            "detail": detail,
        }

    def _code_detail(self, row: dict[str, Any]) -> dict[str, Any]:
        table_details = []
        for table_id in row.get("logical_table_ids") or []:
            table = self._record_maps["TABLE"].get(normalize_entity_id(table_id, "TABLE"))
            if not table:
                continue
            contexts = []
            for adrg in table.get("condition_adrgs") or []:
                contexts.extend(
                    {"adrg": adrg, **item}
                    for item in self._semantic_context_index.get((str(adrg), str(table_id)), [])
                )
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
        adrg_summaries = [
            self._summary_entity("ADRG", adrg)
            for adrg in row.get("related_adrgs") or []
            if self._record_maps["ADRG"].get(normalize_entity_id(adrg, "ADRG"))
        ]
        aadrg_summaries = [
            self._summary_entity("AADRG", aadrg)
            for aadrg in row.get("related_aadrgs") or []
            if self._record_maps["AADRG"].get(normalize_entity_id(aadrg, "AADRG"))
        ]
        return {
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
            "related_adrg_summaries": adrg_summaries,
            "related_aadrg_summaries": aadrg_summaries,
        }

    def _adrg_detail(self, row: dict[str, Any]) -> dict[str, Any]:
        aadrgs = [self._summary_entity("AADRG", code) for code in row.get("aadrg_codes") or []]
        tables = [self._summary_entity("TABLE", table_id) for table_id in row.get("logical_table_ids") or []]
        ast = None
        ast_id = str(row.get("condition_ast_id") or "")
        if ast_id:
            ast = next(
                (deepcopy(item) for item in self.data.get("condition_ast_records") or [] if str(item.get("condition_ast_id") or "") == ast_id),
                None,
            )
        return {**deepcopy(row), "aadrg_records": aadrgs, "logical_tables": tables, "condition_ast": ast}

    def _aadrg_detail(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            **deepcopy(row),
            "parent_adrg": self._summary_entity("ADRG", str(row.get("adrg") or "")),
            "rdrg_records": [self._summary_entity("RDRG", code) for code in row.get("rdrg_codes") or []],
        }

    def _rdrg_detail(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            **deepcopy(row),
            "parent_aadrg": self._summary_entity("AADRG", str(row.get("aadrg") or "")),
            "parent_adrg": self._summary_entity("ADRG", str(row.get("adrg") or "")),
        }

    def _table_detail(self, row: dict[str, Any]) -> dict[str, Any]:
        contexts = []
        for adrg in row.get("condition_adrgs") or []:
            contexts.extend(
                {"adrg": adrg, **item}
                for item in self._semantic_context_index.get((str(adrg), str(row.get("logical_table_id") or "")), [])
            )
        return {
            **deepcopy(row),
            "runtime_contexts": contexts,
            "source_adrg_summaries": [self._summary_entity("ADRG", code) for code in row.get("source_adrgs") or []],
            "condition_adrg_summaries": [self._summary_entity("ADRG", code) for code in row.get("condition_adrgs") or []],
            "related_adrg_summaries": [self._summary_entity("ADRG", code) for code in row.get("related_adrgs") or []],
            "code_records": [self._summary_entity("CODE", code) for code in row.get("codes") or []],
        }

    def _summary_entity(self, entity_type: str, entity_id: str) -> dict[str, Any]:
        row = self._record_maps[entity_type].get(normalize_entity_id(entity_id, entity_type))
        if row is None:
            return {"entity_type": entity_type, "entity_id": entity_id, "missing": True}
        title, subtitle = self._title_subtitle(entity_type, row)
        return {
            "entity_type": entity_type,
            "entity_id": str(row.get(self._id_fields[entity_type]) or ""),
            "title": title,
            "subtitle": subtitle,
            "summary": self._summary_payload(entity_type, row),
        }


__all__ = [
    "KdrgSearchError",
    "KdrgSearchService",
    "SERVICE_SCHEMA_VERSION",
    "RESPONSE_SCHEMA_VERSION",
    "SUPPORTED_DATA_SCHEMA",
    "normalize_entity_id",
    "normalize_query",
    "query_tokens",
]
