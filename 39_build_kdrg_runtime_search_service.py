from __future__ import annotations

import hashlib
import importlib.util
import json
import py_compile
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_VERSION = "2026-07-23_KDRG_V47_RUNTIME_SEARCH_SERVICE_BUILDER_V1"
ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data" / "kdrg_v47_search_integrated.json"
VALIDATION_REPORT_PATH = ROOT / "reports" / "search_integrated_validation_report.json"
SERVICE_PATH = ROOT / "app" / "kdrg_search_service.py"
SMOKE_PATH = ROOT / "tests" / "smoke_test_kdrg_search_service.py"
REPORT_TXT_PATH = ROOT / "reports" / "runtime_search_service_build_report.txt"
REPORT_JSON_PATH = ROOT / "reports" / "runtime_search_service_build_report.json"

SERVICE_SOURCE = 'from __future__ import annotations\n\nimport json\nimport re\nfrom collections import defaultdict\nfrom copy import deepcopy\nfrom pathlib import Path\nfrom typing import Any, Iterable\n\nSERVICE_SCHEMA_VERSION = "kdrg-runtime-search-service-v1"\nRESPONSE_SCHEMA_VERSION = "kdrg-runtime-search-response-v1"\nSUPPORTED_DATA_SCHEMA = "kdrg-v47-search-integrated-v2"\nENTITY_TYPES = ("CODE", "ADRG", "AADRG", "RDRG", "TABLE")\nENTITY_ORDER = {name: index for index, name in enumerate(ENTITY_TYPES)}\nTOKEN_RE = re.compile(r"[0-9A-Za-z가-힣_]+")\nCODE_LIKE_RE = re.compile(r"^[A-Za-z0-9.\\-\\s]+$")\n\n\nclass KdrgSearchError(RuntimeError):\n    pass\n\n\ndef _read_json(path: Path) -> dict[str, Any]:\n    try:\n        with path.open("r", encoding="utf-8") as handle:\n            payload = json.load(handle)\n    except FileNotFoundError as exc:\n        raise KdrgSearchError(f"통합 검색 데이터가 없습니다: {path}") from exc\n    except json.JSONDecodeError as exc:\n        raise KdrgSearchError(f"통합 검색 JSON을 읽을 수 없습니다: {path} | {exc}") from exc\n    if not isinstance(payload, dict):\n        raise KdrgSearchError(f"통합 검색 JSON 최상위 구조가 dict가 아닙니다: {path}")\n    return payload\n\n\ndef _normalize_space(value: Any) -> str:\n    return re.sub(r"\\s+", " ", str(value or "")).strip()\n\n\ndef normalize_entity_id(value: Any, entity_type: str | None = None) -> str:\n    text = _normalize_space(value).upper()\n    if entity_type == "TABLE" or text.startswith("LT_"):\n        return re.sub(r"[^A-Z0-9_]", "", text)\n    return re.sub(r"[^A-Z0-9]", "", text)\n\n\ndef normalize_query(value: Any) -> str:\n    return _normalize_space(value).casefold()\n\n\ndef query_tokens(value: Any) -> list[str]:\n    tokens = [token.casefold() for token in TOKEN_RE.findall(_normalize_space(value))]\n    output: list[str] = []\n    seen: set[str] = set()\n    for token in tokens:\n        if token and token not in seen:\n            seen.add(token)\n            output.append(token)\n    return output\n\n\ndef _unique_strings(values: Iterable[Any]) -> list[str]:\n    output: list[str] = []\n    seen: set[str] = set()\n    for value in values:\n        text = str(value or "")\n        if text and text not in seen:\n            seen.add(text)\n            output.append(text)\n    return output\n\n\nclass KdrgSearchService:\n    def __init__(self, data_path: str | Path | None = None) -> None:\n        if data_path is None:\n            data_path = Path(__file__).resolve().parents[1] / "data" / "kdrg_v47_search_integrated.json"\n        self.data_path = Path(data_path).expanduser().resolve()\n        self.data = _read_json(self.data_path)\n        self._validate_data()\n        self.meta = self.data["meta"]\n        self.indexes = self.data["indexes"]\n        self.runtime_semantic_rules = deepcopy(self.data.get("runtime_semantic_rules") or {})\n        self._records = {\n            "ADRG": self.data["adrg_records"],\n            "AADRG": self.data["aadrg_records"],\n            "RDRG": self.data["rdrg_records"],\n            "TABLE": self.data["logical_table_records"],\n            "CODE": self.data["code_records"],\n        }\n        self._id_fields = {\n            "ADRG": "adrg",\n            "AADRG": "aadrg",\n            "RDRG": "code",\n            "TABLE": "logical_table_id",\n            "CODE": "code",\n        }\n        self._record_maps = {\n            entity_type: {\n                normalize_entity_id(row.get(self._id_fields[entity_type]), entity_type): row\n                for row in rows\n            }\n            for entity_type, rows in self._records.items()\n        }\n        self._semantic_context_index, self._semantic_context_summary = self._build_semantic_context_index()\n        self._search_documents = self._build_search_documents()\n\n    def _validate_data(self) -> None:\n        meta = self.data.get("meta") or {}\n        schema = str(meta.get("schema_version") or "")\n        if schema != SUPPORTED_DATA_SCHEMA:\n            raise KdrgSearchError(\n                f"지원하지 않는 통합 데이터 schema입니다: {schema or \'<EMPTY>\'} | expected={SUPPORTED_DATA_SCHEMA}"\n            )\n        required_lists = {\n            "adrg_records",\n            "aadrg_records",\n            "rdrg_records",\n            "logical_table_records",\n            "condition_ast_records",\n            "code_records",\n        }\n        missing = [key for key in sorted(required_lists) if not isinstance(self.data.get(key), list)]\n        if missing:\n            raise KdrgSearchError(f"통합 검색 JSON 필수 배열이 없습니다: {\', \'.join(missing)}")\n        if not isinstance(self.data.get("indexes"), dict):\n            raise KdrgSearchError("통합 검색 JSON indexes가 없습니다")\n        validation = self.data.get("validation") or {}\n        if str(validation.get("status") or "") != "PASS":\n            raise KdrgSearchError("통합 검색 JSON 자체 validation 상태가 PASS가 아닙니다")\n\n    def status(self) -> dict[str, Any]:\n        return {\n            "service_schema_version": SERVICE_SCHEMA_VERSION,\n            "response_schema_version": RESPONSE_SCHEMA_VERSION,\n            "data_schema_version": self.meta.get("schema_version"),\n            "data_version": self.meta.get("data_version"),\n            "data_state": self.meta.get("state"),\n            "data_path": str(self.data_path),\n            "counts": deepcopy(self.meta.get("counts") or {}),\n            "policies": deepcopy(self.meta.get("policies") or {}),\n            "semantic_context_counts": deepcopy(self._semantic_context_summary),\n            "ready": True,\n        }\n\n    def _build_search_documents(self) -> dict[str, dict[str, Any]]:\n        documents: dict[str, dict[str, Any]] = {}\n        for entity_type, rows in self._records.items():\n            id_field = self._id_fields[entity_type]\n            for row in rows:\n                entity_id = str(row.get(id_field) or "")\n                title, subtitle = self._title_subtitle(entity_type, row)\n                fields: dict[str, list[str]] = {\n                    "entity_id": [entity_id],\n                    "title": [title],\n                    "subtitle": [subtitle],\n                }\n                if entity_type == "CODE":\n                    fields["name"] = [str(x) for x in row.get("names") or []]\n                    fields["role"] = [str(x) for x in row.get("roles") or []]\n                    fields["table"] = [str(x) for x in row.get("logical_table_ids") or []]\n                    fields["adrg"] = [str(x) for x in row.get("related_adrgs") or []]\n                elif entity_type == "ADRG":\n                    fields["name"] = [str(row.get("adrg_name") or "")]\n                    fields["aadrg"] = [str(x) for x in row.get("aadrg_codes") or []]\n                    fields["classification"] = [str(x) for x in row.get("abc_display_labels") or []]\n                elif entity_type == "AADRG":\n                    fields["name"] = [str(row.get("group_name") or "")]\n                    fields["adrg"] = [str(row.get("adrg") or "")]\n                    fields["rdrg"] = [str(x) for x in row.get("rdrg_codes") or []]\n                    fields["classification"] = [str(row.get("classification_display_label") or "")]\n                elif entity_type == "RDRG":\n                    fields["name"] = [str(row.get("group_name") or ""), str(row.get("severity_name") or "")]\n                    fields["aadrg"] = [str(row.get("aadrg") or "")]\n                    fields["adrg"] = [str(row.get("adrg") or "")]\n                elif entity_type == "TABLE":\n                    fields["name"] = [str(row.get("display_name") or "")]\n                    fields["type"] = [str(row.get("logical_table_type") or ""), str(row.get("logical_table_scope") or "")]\n                    fields["code"] = [str(x) for x in row.get("codes") or []]\n                    fields["adrg"] = [str(x) for x in row.get("related_adrgs") or []]\n                normalized_fields = {\n                    key: [normalize_query(value) for value in values if _normalize_space(value)]\n                    for key, values in fields.items()\n                }\n                flat_values = [value for values in normalized_fields.values() for value in values]\n                documents[f"{entity_type}:{entity_id}"] = {\n                    "entity_type": entity_type,\n                    "entity_id": entity_id,\n                    "title": title,\n                    "subtitle": subtitle,\n                    "fields": normalized_fields,\n                    "haystack": " ".join(flat_values),\n                    "tokens": set(query_tokens(" ".join(flat_values))),\n                }\n        return documents\n\n    def _build_semantic_context_index(self) -> tuple[dict[tuple[str, str], list[dict[str, Any]]], dict[str, int]]:\n        output: defaultdict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)\n        summary = defaultdict(int)\n        for ast in self.data.get("condition_ast_records") or []:\n            adrg = str(ast.get("adrg") or "")\n            ast_id = str(ast.get("condition_ast_id") or "")\n            nodes = {\n                str(node.get("node_id") or ""): node\n                for node in ast.get("nodes") or []\n                if str(node.get("node_id") or "")\n            }\n\n            def ancestors(node_id: str) -> list[dict[str, Any]]:\n                found: list[dict[str, Any]] = []\n                seen: set[str] = set()\n                current = nodes.get(node_id)\n                while current:\n                    parent_id = str(current.get("parent_node_id") or "")\n                    if not parent_id or parent_id in seen:\n                        break\n                    seen.add(parent_id)\n                    parent = nodes.get(parent_id)\n                    if parent is None:\n                        break\n                    found.append(parent)\n                    current = parent\n                return found\n\n            for node in ast.get("nodes") or []:\n                node_id = str(node.get("node_id") or "")\n                node_type = str(node.get("node_type") or "")\n                table_ids = _unique_strings(node.get("logical_table_ids") or [])\n                if not table_ids:\n                    continue\n                fragment = str(node.get("source_fragment") or node.get("display_text") or "")\n                semantic_type = str(node.get("semantic_type") or "")\n                evaluation_mode = str(node.get("evaluation_mode") or "")\n                ancestor_types = [str(item.get("node_type") or "") for item in ancestors(node_id)]\n\n                if node_type == "TEXT_CONDITION" and semantic_type == "optional_table_presence":\n                    for index, table_id in enumerate(table_ids):\n                        context = "required_table_with_optional_companion" if index == 0 else "optional_companion_table"\n                        output[(adrg, table_id)].append({\n                            "context": context,\n                            "display_label": "필수 TABLE" if index == 0 else "시행 여부 무관",\n                            "condition_ast_id": ast_id,\n                            "node_id": node_id,\n                            "source_fragment": fragment,\n                            "semantic_type": semantic_type,\n                            "evaluation_mode": evaluation_mode,\n                        })\n                        summary[context] += 1\n                    continue\n\n                allowed_exception = False\n                if node_type == "TABLE_REF":\n                    parent = nodes.get(str(node.get("parent_node_id") or ""))\n                    if parent and str(parent.get("node_type") or "") == "EXCLUSION":\n                        children = [str(x) for x in parent.get("child_node_ids") or []]\n                        if len(children) >= 2 and children[1] == node_id:\n                            base = nodes.get(children[0])\n                            base_is_or = bool(\n                                base\n                                and str(base.get("node_type") or "") == "TEXT_CONDITION"\n                                and str(base.get("semantic_type") or "") == "or_procedure"\n                            )\n                            parent_ancestor_types = [\n                                str(item.get("node_type") or "")\n                                for item in ancestors(str(parent.get("node_id") or ""))\n                            ]\n                            allowed_exception = base_is_or and "NOT" in parent_ancestor_types\n\n                if allowed_exception:\n                    context = "allowed_exception_under_negated_or_procedure"\n                    display_label = "OR procedure 허용 예외"\n                elif "NOT" in ancestor_types or "EXCLUSION" in ancestor_types:\n                    context = "negative_or_exclusion_reference"\n                    display_label = "제외 조건"\n                elif node_type == "TEXT_CONDITION":\n                    context = "semantic_text_condition"\n                    display_label = "의미 조건 TABLE"\n                else:\n                    context = "positive_required_table"\n                    display_label = "필수 TABLE"\n\n                for table_id in table_ids:\n                    output[(adrg, table_id)].append({\n                        "context": context,\n                        "display_label": display_label,\n                        "condition_ast_id": ast_id,\n                        "node_id": node_id,\n                        "source_fragment": fragment,\n                        "semantic_type": semantic_type or None,\n                        "evaluation_mode": evaluation_mode or None,\n                    })\n                    summary[context] += 1\n\n        cleaned = {\n            key: sorted(\n                values,\n                key=lambda item: (\n                    str(item.get("context") or ""),\n                    str(item.get("condition_ast_id") or ""),\n                    str(item.get("node_id") or ""),\n                ),\n            )\n            for key, values in output.items()\n        }\n        summary["relationship_key_count"] = len(cleaned)\n        summary["relationship_occurrence_count"] = sum(len(values) for values in cleaned.values())\n        return cleaned, dict(sorted(summary.items()))\n\n    def _title_subtitle(self, entity_type: str, row: dict[str, Any]) -> tuple[str, str]:\n        if entity_type == "CODE":\n            names = [str(x) for x in row.get("names") or [] if str(x)]\n            title = str(row.get("code") or "")\n            subtitle = " / ".join(names[:2]) if names else "코드명 원천 미수록"\n        elif entity_type == "ADRG":\n            title = f"{row.get(\'adrg\', \'\')} · {row.get(\'adrg_name\', \'\')}".strip(" ·")\n            subtitle = f"MDC {row.get(\'mdc\', \'-\')} · AADRG {row.get(\'aadrg_count\', 0)}개"\n        elif entity_type == "AADRG":\n            title = f"{row.get(\'aadrg\', \'\')} · {row.get(\'group_name\', \'\')}".strip(" ·")\n            label = str(row.get("classification_display_label") or "분류 미부여")\n            subtitle = f"ADRG {row.get(\'adrg\', \'-\')} · {label}"\n        elif entity_type == "RDRG":\n            title = f"{row.get(\'code\', \'\')} · {row.get(\'group_name\', \'\')}".strip(" ·")\n            subtitle = f"AADRG {row.get(\'aadrg\', \'-\')} · {row.get(\'severity_name\') or \'중증도 명칭 없음\'}"\n        else:\n            title = str(row.get("display_name") or row.get("logical_table_id") or "")\n            subtitle = f"코드 {row.get(\'code_count\', 0)}개 · 관련 ADRG {len(row.get(\'related_adrgs\') or [])}개"\n        return title, subtitle\n\n    def _normalize_entity_types(self, entity_type: str | Iterable[str] | None) -> list[str]:\n        if entity_type is None or entity_type == "ALL":\n            return list(ENTITY_TYPES)\n        values = [entity_type] if isinstance(entity_type, str) else list(entity_type)\n        output: list[str] = []\n        for value in values:\n            name = str(value or "").upper()\n            if name == "ALL":\n                return list(ENTITY_TYPES)\n            if name not in ENTITY_TYPES:\n                raise KdrgSearchError(f"지원하지 않는 검색 유형입니다: {value}")\n            if name not in output:\n                output.append(name)\n        if not output:\n            raise KdrgSearchError("검색 유형이 비어 있습니다")\n        return output\n\n    def _match_document(self, document: dict[str, Any], query: str, tokens: list[str]) -> tuple[int, str, list[str]] | None:\n        entity_type = document["entity_type"]\n        entity_id = document["entity_id"]\n        normalized_id = normalize_entity_id(entity_id, entity_type)\n        normalized_input_id = normalize_entity_id(query, entity_type)\n        q = normalize_query(query)\n        matched_fields: list[str] = []\n\n        if normalized_input_id and normalized_input_id == normalized_id:\n            return 1000, "EXACT_ID", ["entity_id"]\n\n        for field, values in document["fields"].items():\n            if q and q in values:\n                matched_fields.append(field)\n        if matched_fields:\n            return 920, "EXACT_TEXT", sorted(set(matched_fields))\n\n        if normalized_input_id and normalized_id.startswith(normalized_input_id):\n            return 840, "PREFIX_ID", ["entity_id"]\n\n        if tokens and all(token in document["tokens"] for token in tokens):\n            fields = [\n                field\n                for field, values in document["fields"].items()\n                if any(token in set(query_tokens(" ".join(values))) for token in tokens)\n            ]\n            return 760, "ALL_TOKENS", sorted(set(fields)) or ["text"]\n\n        if q and q in document["haystack"]:\n            fields = [field for field, values in document["fields"].items() if any(q in value for value in values)]\n            return 680, "CONTAINS", sorted(set(fields)) or ["text"]\n\n        if tokens and any(token in document["tokens"] for token in tokens):\n            matched = sum(1 for token in tokens if token in document["tokens"])\n            score = 500 + min(matched, 20)\n            return score, "ANY_TOKEN", ["text"]\n        return None\n\n    def search(\n        self,\n        query: str,\n        entity_type: str | Iterable[str] | None = "ALL",\n        *,\n        limit: int = 50,\n        offset: int = 0,\n        mdc: str | None = None,\n        classification: str | None = None,\n    ) -> dict[str, Any]:\n        query_text = _normalize_space(query)\n        if not query_text:\n            raise KdrgSearchError("검색어를 입력해야 합니다")\n        if limit < 1 or limit > 500:\n            raise KdrgSearchError("limit은 1~500 범위여야 합니다")\n        if offset < 0:\n            raise KdrgSearchError("offset은 0 이상이어야 합니다")\n        entity_types = self._normalize_entity_types(entity_type)\n        tokens = query_tokens(query_text)\n        mdc_filter = str(mdc or "").upper().strip()\n        class_filter = str(classification or "").upper().strip()\n\n        scored: list[tuple[int, str, str, list[str], str]] = []\n        for key, document in self._search_documents.items():\n            if document["entity_type"] not in entity_types:\n                continue\n            record = self._record_maps[document["entity_type"]][\n                normalize_entity_id(document["entity_id"], document["entity_type"])\n            ]\n            if mdc_filter and not self._record_matches_mdc(document["entity_type"], record, mdc_filter):\n                continue\n            if class_filter and not self._record_matches_classification(document["entity_type"], record, class_filter):\n                continue\n            match = self._match_document(document, query_text, tokens)\n            if match is None:\n                continue\n            score, match_type, fields = match\n            scored.append((score, document["entity_type"], document["entity_id"], fields, match_type))\n\n        scored.sort(\n            key=lambda row: (\n                -row[0],\n                ENTITY_ORDER[row[1]],\n                normalize_entity_id(row[2], row[1]),\n            )\n        )\n        total_count = len(scored)\n        page = scored[offset : offset + limit]\n        results = [\n            self._make_search_result(entity_type_, entity_id, score, match_type, fields)\n            for score, entity_type_, entity_id, fields, match_type in page\n        ]\n        type_counts = defaultdict(int)\n        for _, type_name, _, _, _ in scored:\n            type_counts[type_name] += 1\n        return {\n            "schema_version": RESPONSE_SCHEMA_VERSION,\n            "query": query_text,\n            "normalized_query": normalize_query(query_text),\n            "filters": {\n                "entity_types": entity_types,\n                "mdc": mdc_filter or None,\n                "classification": class_filter or None,\n            },\n            "total_count": total_count,\n            "type_counts": dict(sorted(type_counts.items(), key=lambda item: ENTITY_ORDER[item[0]])),\n            "offset": offset,\n            "limit": limit,\n            "has_more": offset + len(results) < total_count,\n            "results": results,\n        }\n\n    def _record_matches_mdc(self, entity_type: str, record: dict[str, Any], mdc: str) -> bool:\n        if entity_type in {"ADRG", "AADRG"}:\n            return str(record.get("mdc") or "").upper() == mdc\n        if entity_type == "RDRG":\n            parent = self._record_maps["ADRG"].get(normalize_entity_id(record.get("adrg"), "ADRG"))\n            return bool(parent and str(parent.get("mdc") or "").upper() == mdc)\n        if entity_type == "TABLE":\n            return any(self._adrg_mdc(code) == mdc for code in record.get("related_adrgs") or [])\n        if entity_type == "CODE":\n            return any(self._adrg_mdc(code) == mdc for code in record.get("related_adrgs") or [])\n        return False\n\n    def _record_matches_classification(self, entity_type: str, record: dict[str, Any], classification: str) -> bool:\n        accepted = {classification}\n        mapping = {"전문": "A", "일반": "B", "단순": "C"}\n        accepted.add(mapping.get(classification, classification))\n        if entity_type == "AADRG":\n            return str(record.get("classification_code") or "").upper() in accepted\n        if entity_type == "ADRG":\n            return bool(set(str(x).upper() for x in record.get("abc_classification_codes") or []) & accepted)\n        aadrgs: list[str] = []\n        if entity_type == "RDRG":\n            aadrgs = [str(record.get("aadrg") or "")]\n        elif entity_type == "TABLE":\n            aadrgs = [a for adrg in record.get("related_adrgs") or [] for a in self._adrg_aadrgs(str(adrg))]\n        elif entity_type == "CODE":\n            aadrgs = [str(x) for x in record.get("related_aadrgs") or []]\n        return any(\n            str((self._record_maps["AADRG"].get(normalize_entity_id(code, "AADRG")) or {}).get("classification_code") or "").upper()\n            in accepted\n            for code in aadrgs\n        )\n\n    def _adrg_mdc(self, adrg: str) -> str:\n        record = self._record_maps["ADRG"].get(normalize_entity_id(adrg, "ADRG"))\n        return str(record.get("mdc") or "").upper() if record else ""\n\n    def _adrg_aadrgs(self, adrg: str) -> list[str]:\n        record = self._record_maps["ADRG"].get(normalize_entity_id(adrg, "ADRG"))\n        return [str(x) for x in record.get("aadrg_codes") or []] if record else []\n\n    def _make_search_result(\n        self,\n        entity_type: str,\n        entity_id: str,\n        score: int,\n        match_type: str,\n        matched_fields: list[str],\n    ) -> dict[str, Any]:\n        record = self._record_maps[entity_type][normalize_entity_id(entity_id, entity_type)]\n        title, subtitle = self._title_subtitle(entity_type, record)\n        result = {\n            "entity_type": entity_type,\n            "entity_id": entity_id,\n            "title": title,\n            "subtitle": subtitle,\n            "score": score,\n            "match_type": match_type,\n            "matched_fields": matched_fields,\n            "summary": self._summary_payload(entity_type, record),\n        }\n        return result\n\n    def _summary_payload(self, entity_type: str, row: dict[str, Any]) -> dict[str, Any]:\n        if entity_type == "CODE":\n            return {\n                "names": deepcopy(row.get("names") or []),\n                "roles": deepcopy(row.get("roles") or []),\n                "logical_table_count": len(row.get("logical_table_ids") or []),\n                "source_adrgs": deepcopy(row.get("source_adrgs") or []),\n                "condition_adrgs": deepcopy(row.get("condition_adrgs") or []),\n                "related_adrgs": deepcopy(row.get("related_adrgs") or []),\n                "source_adrg_families": deepcopy(row.get("source_adrg_families") or []),\n                "related_aadrg_count": len(row.get("related_aadrgs") or []),\n            }\n        if entity_type == "ADRG":\n            return {\n                "mdc": row.get("mdc"),\n                "aadrg_count": row.get("aadrg_count"),\n                "abc_status": row.get("abc_status"),\n                "abc_display_labels": deepcopy(row.get("abc_display_labels") or []),\n                "source_table_count": len(row.get("source_logical_table_ids") or []),\n                "condition_table_count": len(row.get("condition_logical_table_ids") or []),\n                "related_table_count": len(row.get("logical_table_ids") or []),\n                "condition_ast_id": row.get("condition_ast_id"),\n            }\n        if entity_type == "AADRG":\n            return {\n                "adrg": row.get("adrg"),\n                "mdc": row.get("mdc"),\n                "classification_code": row.get("classification_code"),\n                "classification_display_label": row.get("classification_display_label") or "분류 미부여",\n                "abc_status": row.get("abc_status"),\n                "rdrg_count": len(row.get("rdrg_codes") or []),\n            }\n        if entity_type == "RDRG":\n            return {\n                "adrg": row.get("adrg"),\n                "aadrg": row.get("aadrg"),\n                "severity_name": row.get("severity_name"),\n            }\n        return {\n            "logical_table_type": row.get("logical_table_type"),\n            "logical_table_scope": row.get("logical_table_scope"),\n            "code_count": row.get("code_count"),\n            "source_adrgs": deepcopy(row.get("source_adrgs") or []),\n            "condition_adrgs": deepcopy(row.get("condition_adrgs") or []),\n            "related_adrgs": deepcopy(row.get("related_adrgs") or []),\n            "source_adrg_families": deepcopy(row.get("source_adrg_families") or []),\n            "condition_ast_count": len(row.get("condition_ast_ids") or []),\n        }\n\n    def get_detail(self, entity_type: str, entity_id: str) -> dict[str, Any]:\n        type_name = str(entity_type or "").upper()\n        if type_name not in ENTITY_TYPES:\n            raise KdrgSearchError(f"지원하지 않는 상세조회 유형입니다: {entity_type}")\n        normalized_id = normalize_entity_id(entity_id, type_name)\n        row = self._record_maps[type_name].get(normalized_id)\n        if row is None:\n            raise KdrgSearchError(f"상세조회 대상을 찾지 못했습니다: {type_name}:{entity_id}")\n        if type_name == "CODE":\n            detail = self._code_detail(row)\n        elif type_name == "ADRG":\n            detail = self._adrg_detail(row)\n        elif type_name == "AADRG":\n            detail = self._aadrg_detail(row)\n        elif type_name == "RDRG":\n            detail = self._rdrg_detail(row)\n        else:\n            detail = self._table_detail(row)\n        return {\n            "schema_version": RESPONSE_SCHEMA_VERSION,\n            "entity_type": type_name,\n            "entity_id": str(row.get(self._id_fields[type_name]) or ""),\n            "detail": detail,\n        }\n\n    def _code_detail(self, row: dict[str, Any]) -> dict[str, Any]:\n        table_details = []\n        for table_id in row.get("logical_table_ids") or []:\n            table = self._record_maps["TABLE"].get(normalize_entity_id(table_id, "TABLE"))\n            if not table:\n                continue\n            contexts = []\n            for adrg in table.get("condition_adrgs") or []:\n                contexts.extend(\n                    {"adrg": adrg, **item}\n                    for item in self._semantic_context_index.get((str(adrg), str(table_id)), [])\n                )\n            table_details.append({\n                "logical_table_id": table_id,\n                "display_name": table.get("display_name"),\n                "logical_table_type": table.get("logical_table_type"),\n                "source_adrgs": deepcopy(table.get("source_adrgs") or []),\n                "condition_adrgs": deepcopy(table.get("condition_adrgs") or []),\n                "related_adrgs": deepcopy(table.get("related_adrgs") or []),\n                "source_adrg_families": deepcopy(table.get("source_adrg_families") or []),\n                "runtime_contexts": contexts,\n                "source_refs": deepcopy(table.get("source_refs") or []),\n            })\n        adrg_summaries = [\n            self._summary_entity("ADRG", adrg)\n            for adrg in row.get("related_adrgs") or []\n            if self._record_maps["ADRG"].get(normalize_entity_id(adrg, "ADRG"))\n        ]\n        aadrg_summaries = [\n            self._summary_entity("AADRG", aadrg)\n            for aadrg in row.get("related_aadrgs") or []\n            if self._record_maps["AADRG"].get(normalize_entity_id(aadrg, "AADRG"))\n        ]\n        return {\n            **deepcopy(row),\n            "relation_sections": {\n                "physical_source": {\n                    "adrgs": deepcopy(row.get("source_adrgs") or []),\n                    "aadrgs": deepcopy(row.get("source_aadrgs") or []),\n                    "family_refs": deepcopy(row.get("source_adrg_families") or []),\n                    "display_label": "원문 TABLE 정의 위치",\n                },\n                "condition_usage": {\n                    "adrgs": deepcopy(row.get("condition_adrgs") or []),\n                    "aadrgs": deepcopy(row.get("condition_aadrgs") or []),\n                    "display_label": "조건 AST 실제 사용 관계",\n                },\n                "runtime_related": {\n                    "adrgs": deepcopy(row.get("related_adrgs") or []),\n                    "aadrgs": deepcopy(row.get("related_aadrgs") or []),\n                    "display_label": "검색용 통합 관계",\n                },\n            },\n            "logical_tables": table_details,\n            "related_adrg_summaries": adrg_summaries,\n            "related_aadrg_summaries": aadrg_summaries,\n        }\n\n    def _adrg_detail(self, row: dict[str, Any]) -> dict[str, Any]:\n        aadrgs = [self._summary_entity("AADRG", code) for code in row.get("aadrg_codes") or []]\n        tables = [self._summary_entity("TABLE", table_id) for table_id in row.get("logical_table_ids") or []]\n        ast = None\n        ast_id = str(row.get("condition_ast_id") or "")\n        if ast_id:\n            ast = next(\n                (deepcopy(item) for item in self.data.get("condition_ast_records") or [] if str(item.get("condition_ast_id") or "") == ast_id),\n                None,\n            )\n        return {**deepcopy(row), "aadrg_records": aadrgs, "logical_tables": tables, "condition_ast": ast}\n\n    def _aadrg_detail(self, row: dict[str, Any]) -> dict[str, Any]:\n        return {\n            **deepcopy(row),\n            "parent_adrg": self._summary_entity("ADRG", str(row.get("adrg") or "")),\n            "rdrg_records": [self._summary_entity("RDRG", code) for code in row.get("rdrg_codes") or []],\n        }\n\n    def _rdrg_detail(self, row: dict[str, Any]) -> dict[str, Any]:\n        return {\n            **deepcopy(row),\n            "parent_aadrg": self._summary_entity("AADRG", str(row.get("aadrg") or "")),\n            "parent_adrg": self._summary_entity("ADRG", str(row.get("adrg") or "")),\n        }\n\n    def _table_detail(self, row: dict[str, Any]) -> dict[str, Any]:\n        contexts = []\n        for adrg in row.get("condition_adrgs") or []:\n            contexts.extend(\n                {"adrg": adrg, **item}\n                for item in self._semantic_context_index.get((str(adrg), str(row.get("logical_table_id") or "")), [])\n            )\n        return {\n            **deepcopy(row),\n            "runtime_contexts": contexts,\n            "source_adrg_summaries": [self._summary_entity("ADRG", code) for code in row.get("source_adrgs") or []],\n            "condition_adrg_summaries": [self._summary_entity("ADRG", code) for code in row.get("condition_adrgs") or []],\n            "related_adrg_summaries": [self._summary_entity("ADRG", code) for code in row.get("related_adrgs") or []],\n            "code_records": [self._summary_entity("CODE", code) for code in row.get("codes") or []],\n        }\n\n    def _summary_entity(self, entity_type: str, entity_id: str) -> dict[str, Any]:\n        row = self._record_maps[entity_type].get(normalize_entity_id(entity_id, entity_type))\n        if row is None:\n            return {"entity_type": entity_type, "entity_id": entity_id, "missing": True}\n        title, subtitle = self._title_subtitle(entity_type, row)\n        return {\n            "entity_type": entity_type,\n            "entity_id": str(row.get(self._id_fields[entity_type]) or ""),\n            "title": title,\n            "subtitle": subtitle,\n            "summary": self._summary_payload(entity_type, row),\n        }\n\n\n__all__ = [\n    "KdrgSearchError",\n    "KdrgSearchService",\n    "SERVICE_SCHEMA_VERSION",\n    "RESPONSE_SCHEMA_VERSION",\n    "SUPPORTED_DATA_SCHEMA",\n    "normalize_entity_id",\n    "normalize_query",\n    "query_tokens",\n]\n'
SMOKE_SOURCE = 'from __future__ import annotations\n\nimport json\nimport sys\nfrom pathlib import Path\nfrom typing import Any\n\nROOT = Path(__file__).resolve().parents[1]\nAPP_DIR = ROOT / "app"\nDATA_PATH = ROOT / "data" / "kdrg_v47_search_integrated.json"\nif str(APP_DIR) not in sys.path:\n    sys.path.insert(0, str(APP_DIR))\n\nfrom kdrg_search_service import (  # noqa: E402\n    KdrgSearchError,\n    KdrgSearchService,\n    RESPONSE_SCHEMA_VERSION,\n    SERVICE_SCHEMA_VERSION,\n    SUPPORTED_DATA_SCHEMA,\n)\n\n\nclass Checker:\n    def __init__(self) -> None:\n        self.checks: list[dict[str, Any]] = []\n\n    def check(self, check_id: str, name: str, condition: bool, detail: str = "") -> None:\n        self.checks.append({\n            "check_id": check_id,\n            "name": name,\n            "status": "PASS" if condition else "FAIL",\n            "detail": detail,\n        })\n\n    def summary(self) -> dict[str, Any]:\n        passed = sum(1 for row in self.checks if row["status"] == "PASS")\n        failed = len(self.checks) - passed\n        return {\n            "status": "PASS" if failed == 0 else "FAIL",\n            "pass_count": passed,\n            "fail_count": failed,\n            "total_count": len(self.checks),\n            "checks": self.checks,\n        }\n\n\ndef ids(response: dict[str, Any], entity_type: str | None = None) -> list[str]:\n    rows = response.get("results") or []\n    if entity_type:\n        rows = [row for row in rows if row.get("entity_type") == entity_type]\n    return [str(row.get("entity_id") or "") for row in rows]\n\n\ndef run_smoke(data_path: str | Path = DATA_PATH) -> dict[str, Any]:\n    checker = Checker()\n    service = KdrgSearchService(data_path)\n    status = service.status()\n    counts = status["counts"]\n\n    checker.check("S01", "service ready", status.get("ready") is True, str(status.get("ready")))\n    checker.check("S02", "service schema", status.get("service_schema_version") == SERVICE_SCHEMA_VERSION, str(status.get("service_schema_version")))\n    checker.check("S03", "response schema", status.get("response_schema_version") == RESPONSE_SCHEMA_VERSION, str(status.get("response_schema_version")))\n    checker.check("S04", "data schema V2", status.get("data_schema_version") == SUPPORTED_DATA_SCHEMA, str(status.get("data_schema_version")))\n    checker.check("S05", "ADRG 1132", counts.get("adrg_records") == 1132, str(counts.get("adrg_records")))\n    checker.check("S06", "AADRG 1233", counts.get("aadrg_records") == 1233, str(counts.get("aadrg_records")))\n    checker.check("S07", "RDRG 2699", counts.get("rdrg_records") == 2699, str(counts.get("rdrg_records")))\n    checker.check("S08", "TABLE 1308", counts.get("logical_table_records") == 1308, str(counts.get("logical_table_records")))\n    checker.check("S09", "CODE 16571", counts.get("unique_search_codes") == 16571, str(counts.get("unique_search_codes")))\n    checker.check("S10", "AST node 1727", counts.get("ast_node_count") == 1727, str(counts.get("ast_node_count")))\n\n    adrg = service.search("9600", "ADRG")\n    checker.check("S11", "ADRG exact search", ids(adrg) == ["9600"], str(ids(adrg)))\n    checker.check("S12", "ADRG exact match type", adrg["results"][0]["match_type"] == "EXACT_ID", str(adrg["results"][0]["match_type"]))\n\n    aadrg = service.search("96000", "AADRG")\n    checker.check("S13", "AADRG exact search", ids(aadrg) == ["96000"], str(ids(aadrg)))\n    checker.check("S14", "AADRG B classification", aadrg["results"][0]["summary"]["classification_code"] == "B", str(aadrg["results"][0]["summary"]))\n\n    rdrg = service.search("960000", "RDRG")\n    checker.check("S15", "RDRG exact search", ids(rdrg) == ["960000"], str(ids(rdrg)))\n\n    table = service.search("LT_9610_001", "TABLE")\n    checker.check("S16", "TABLE exact search", ids(table) == ["LT_9610_001"], str(ids(table)))\n\n    code = service.search("A000", "CODE")\n    checker.check("S17", "CODE exact search", ids(code) == ["A000"], str(ids(code)))\n    dotted = service.search("A00.0", "CODE")\n    checker.check("S18", "CODE punctuation normalization", ids(dotted) == ["A000"], str(ids(dotted)))\n\n    name_search = service.search("조기 사망", "ALL", limit=20)\n    checker.check("S19", "Korean name token search", "9600" in ids(name_search, "ADRG"), str(ids(name_search, "ADRG")))\n    checker.check("S20", "ALL type response", len(name_search.get("type_counts") or {}) >= 3, str(name_search.get("type_counts")))\n\n    only_code = service.search("A000", ["CODE"], limit=20)\n    checker.check("S21", "entity type filter", all(row["entity_type"] == "CODE" for row in only_code["results"]), str(only_code["results"]))\n    mdc_filter = service.search("사망", "ALL", mdc="PRE", limit=50)\n    checker.check("S22", "MDC filter", all((row["summary"].get("mdc") == "PRE") for row in mdc_filter["results"] if row["entity_type"] in {"ADRG", "AADRG"}), str(mdc_filter["results"][:5]))\n    class_filter = service.search("9600", "ADRG", classification="B")\n    checker.check("S23", "classification filter", ids(class_filter) == ["9600"], str(ids(class_filter)))\n    class_filter_empty = service.search("9600", "ADRG", classification="A")\n    checker.check("S24", "classification exclusion", class_filter_empty["total_count"] == 0, str(class_filter_empty["total_count"]))\n\n    paged = service.search("사망", "ALL", limit=2, offset=0)\n    checker.check("S25", "pagination limit", len(paged["results"]) <= 2, str(len(paged["results"])))\n    checker.check("S26", "pagination has_more", paged["has_more"] is (paged["total_count"] > len(paged["results"])), str(paged["has_more"]))\n\n    code_detail = service.get_detail("CODE", "S710")\n    relations = code_detail["detail"]["relation_sections"]\n    checker.check("S27", "CODE detail response schema", code_detail["schema_version"] == RESPONSE_SCHEMA_VERSION, str(code_detail["schema_version"]))\n    checker.check("S28", "physical source relation separated", relations["physical_source"]["adrgs"] == ["X012", "X030", "X600"], str(relations["physical_source"]))\n    checker.check("S29", "condition usage relation separated", relations["condition_usage"]["adrgs"] == ["X011", "X012", "X041", "X042"], str(relations["condition_usage"]))\n    checker.check("S30", "runtime related relation separated", relations["runtime_related"]["adrgs"] == ["X011", "X012", "X030", "X041", "X042", "X600"], str(relations["runtime_related"]))\n    checker.check("S31", "X04 family not exposed as ADRG", "X04" not in relations["runtime_related"]["adrgs"], str(relations["runtime_related"]))\n    checker.check("S32", "X04 family provenance preserved", relations["physical_source"]["family_refs"] == ["X04"], str(relations["physical_source"]))\n\n    semantic_counts = status["semantic_context_counts"]\n    checker.check("S33", "allowed exception nodes 19", semantic_counts.get("allowed_exception_under_negated_or_procedure") == 19, str(semantic_counts))\n    checker.check("S34", "optional companion nodes 7", semantic_counts.get("optional_companion_table") == 7, str(semantic_counts))\n    checker.check("S35", "required optional pair nodes 7", semantic_counts.get("required_table_with_optional_companion") == 7, str(semantic_counts))\n\n    optional_table = service.get_detail("TABLE", "LT_C064_003")["detail"]\n    optional_contexts = optional_table.get("runtime_contexts") or []\n    checker.check("S36", "optional companion table context", any(row.get("context") == "optional_companion_table" for row in optional_contexts), str(optional_contexts[:5]))\n    allowed_table = service.get_detail("TABLE", "LT_P602_002")["detail"]\n    allowed_contexts = allowed_table.get("runtime_contexts") or []\n    checker.check("S37", "allowed exception table context", any(row.get("context") == "allowed_exception_under_negated_or_procedure" for row in allowed_contexts), str(allowed_contexts[:5]))\n\n    unclassified = service.get_detail("AADRG", "99000")["detail"]\n    checker.check("S38", "A/B/C unclassified preserved", unclassified.get("classification_code") is None and unclassified.get("abc_unclassified_provenance") is not None, str(unclassified.get("abc_unclassified_provenance")))\n    mixed = service.get_detail("ADRG", "I760")["detail"]\n    checker.check("S39", "mixed ADRG classification preserved", len(set(mixed.get("abc_classification_codes") or [])) >= 2, str(mixed.get("abc_classification_codes")))\n\n    checker.check("S40", "JSON serialization search", bool(json.dumps(name_search, ensure_ascii=False)), "search serialized")\n    checker.check("S41", "JSON serialization detail", bool(json.dumps(code_detail, ensure_ascii=False)), "detail serialized")\n\n    invalid_type_raised = False\n    try:\n        service.search("A000", "INVALID")\n    except KdrgSearchError:\n        invalid_type_raised = True\n    checker.check("S42", "invalid entity type error", invalid_type_raised, str(invalid_type_raised))\n\n    empty_query_raised = False\n    try:\n        service.search("   ")\n    except KdrgSearchError:\n        empty_query_raised = True\n    checker.check("S43", "empty query error", empty_query_raised, str(empty_query_raised))\n\n    invalid_limit_raised = False\n    try:\n        service.search("A000", limit=0)\n    except KdrgSearchError:\n        invalid_limit_raised = True\n    checker.check("S44", "invalid limit error", invalid_limit_raised, str(invalid_limit_raised))\n\n    missing_detail_raised = False\n    try:\n        service.get_detail("CODE", "NOT_A_REAL_CODE")\n    except KdrgSearchError:\n        missing_detail_raised = True\n    checker.check("S45", "missing detail error", missing_detail_raised, str(missing_detail_raised))\n\n    table_detail = service.get_detail("TABLE", "LT_9610_001")["detail"]\n    checker.check("S46", "TABLE code records", len(table_detail.get("code_records") or []) == 7, str(len(table_detail.get("code_records") or [])))\n    adrg_detail = service.get_detail("ADRG", "9600")["detail"]\n    checker.check("S47", "ADRG condition AST connected", (adrg_detail.get("condition_ast") or {}).get("condition_ast_id") == "AST_9600", str((adrg_detail.get("condition_ast") or {}).get("condition_ast_id")))\n    aadrg_detail = service.get_detail("AADRG", "96000")["detail"]\n    checker.check("S48", "AADRG parent ADRG connected", (aadrg_detail.get("parent_adrg") or {}).get("entity_id") == "9600", str(aadrg_detail.get("parent_adrg")))\n    rdrg_detail = service.get_detail("RDRG", "960000")["detail"]\n    checker.check("S49", "RDRG parent AADRG connected", (rdrg_detail.get("parent_aadrg") or {}).get("entity_id") == "96000", str(rdrg_detail.get("parent_aadrg")))\n\n    return checker.summary()\n\n\nif __name__ == "__main__":\n    result = run_smoke()\n    print(json.dumps(result, ensure_ascii=False, indent=2))\n    raise SystemExit(0 if result["status"] == "PASS" else 1)\n'


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

    def extend(self, rows: list[dict[str, Any]]) -> None:
        self.checks.extend(rows)

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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
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


def build_report(payload: dict[str, Any]) -> str:
    summary = payload["validation"]
    smoke = payload["smoke_test"]
    lines = [
        "KDRG V4.7 PySide runtime adapter·검색 service 구축 결과",
        "=" * 72,
        f"생성시각: {payload['generated_at']}",
        f"스크립트 버전: {SCRIPT_VERSION}",
        "",
        "[현재 진행 위치]",
        "최종 검색 통합 JSON V2와 126개 독립검증을 완료한 뒤 UI 연결용 runtime 계층을 구축함",
        "이번 단계에서는 PySide 화면을 수정하지 않고 데이터 접근·검색·상세조회 API만 고정함",
        "통합 JSON과 원천 데이터는 수정하지 않음",
        "",
        "[입력 데이터]",
        f"통합 JSON schema: {payload['input']['data_schema_version']}",
        f"통합 JSON SHA256: {payload['input']['integrated_json_sha256']}",
        f"38번 검증: {payload['input']['validator_version']} / {payload['input']['validator_pass_count']} PASS / {payload['input']['validator_fail_count']} FAIL",
        "",
        "[생성 runtime 파일]",
        f"service: {payload['outputs']['service_path']}",
        f"service SHA256: {payload['outputs']['service_sha256']}",
        f"smoke test: {payload['outputs']['smoke_test_path']}",
        f"smoke test SHA256: {payload['outputs']['smoke_test_sha256']}",
        "",
        "[검색 service API]",
        "KdrgSearchService.status(): 데이터 버전·집계·정책·semantic context 상태",
        "KdrgSearchService.search(): CODE·ADRG·AADRG·RDRG·TABLE 통합검색, 유형·MDC·A/B/C 필터, 페이지 처리",
        "KdrgSearchService.get_detail(): 엔터티별 원문 위치·조건 사용·runtime 관계 상세조회",
        "",
        "[코드 관계 표시 정책]",
        "physical_source: 원문 TABLE이 물리적으로 정의된 ADRG·family provenance",
        "condition_usage: 조건 AST에서 TABLE을 실제 사용하는 ADRG",
        "runtime_related: 검색 화면에서 노출할 source+condition 통합 관계",
        "X04 family ref는 ADRG로 노출하지 않고 X041·X042 조건 사용 관계로 표시함",
        "",
        "[runtime 의미 context]",
        f"허용 예외 context: {smoke['semantic_context_counts'].get('allowed_exception_under_negated_or_procedure', 0)}",
        f"시행 여부 무관 context: {smoke['semantic_context_counts'].get('optional_companion_table', 0)}",
        f"선택 동반의 필수 TABLE context: {smoke['semantic_context_counts'].get('required_table_with_optional_companion', 0)}",
        f"전체 TABLE·ADRG semantic relation key: {smoke['semantic_context_counts'].get('relationship_key_count', 0)}",
        "",
        "[smoke test]",
        f"PASS: {smoke['pass_count']}",
        f"FAIL: {smoke['fail_count']}",
        "CODE·ADRG·AADRG·RDRG·TABLE exact 검색, 코드 점 제거, 한글명 검색, 필터, pagination, 상세조회, X04 관계 분리를 검사함",
        "",
        "[전체 검증 항목 집계]",
        f"PASS: {summary['pass_count']}",
        f"FAIL: {summary['fail_count']}",
        f"TOTAL: {summary['total_count']}",
        "사용자 판단 필요: 0",
        "사용자 수동 Excel 검토: 없음",
        "",
        "[생성 파일]",
        str(SERVICE_PATH),
        str(SMOKE_PATH),
        str(REPORT_TXT_PATH),
        str(REPORT_JSON_PATH),
        "",
        "[다음 단계]",
        "40번에서 생성된 service를 사용하지 않고 통합 JSON에서 검색 결과를 독립 재계산하여 응답 schema·순위·관계 분리를 검증함",
        "독립검증 PASS 후 현재 PySide UI의 데이터 로더와 검색 이벤트를 runtime service에 연결함",
        "",
        "[최종 결과]",
        f"전체 결과: {summary['status']}",
    ]
    failed = [row for row in summary["checks"] if row["status"] == "FAIL"]
    if failed:
        lines.extend(["", "[FAIL 상세]"])
        lines.extend(f"- {row['check_id']} {row['name']} | {row['detail']}" for row in failed)
    return "\n".join(lines) + "\n"


def main() -> int:
    checker = Checker()
    checker.check("B01", "통합 JSON 존재", DATA_PATH.exists(), str(DATA_PATH))
    checker.check("B02", "38번 검증 보고서 존재", VALIDATION_REPORT_PATH.exists(), str(VALIDATION_REPORT_PATH))
    if not DATA_PATH.exists() or not VALIDATION_REPORT_PATH.exists():
        result = checker.summary()
        payload = {
            "script_version": SCRIPT_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "input": {},
            "outputs": {},
            "smoke_test": {"pass_count": 0, "fail_count": 1, "semantic_context_counts": {}},
            "validation": result,
        }
        atomic_write_json(REPORT_JSON_PATH, payload)
        atomic_write_text(REPORT_TXT_PATH, build_report(payload))
        print(f"[FAIL] runtime search service 구축 실패: {result['pass_count']} PASS / {result['fail_count']} FAIL")
        return 1

    integrated_hash_before = sha256_file(DATA_PATH)
    integrated = read_json(DATA_PATH)
    validator = read_json(VALIDATION_REPORT_PATH)
    meta = integrated.get("meta") or {}
    validator_validation = validator.get("validation") or {}

    checker.check("B03", "통합 JSON V2 schema", meta.get("schema_version") == "kdrg-v47-search-integrated-v2", str(meta.get("schema_version")))
    checker.check("B04", "통합 JSON 자체 PASS", (integrated.get("validation") or {}).get("status") == "PASS", str((integrated.get("validation") or {}).get("status")))
    checker.check("B05", "38번 V2 validator", str(validator.get("script_version") or "").endswith("_V2"), str(validator.get("script_version")))
    checker.check("B06", "38번 검증 PASS", validator_validation.get("status") == "PASS", str(validator_validation.get("status")))
    checker.check("B07", "38번 126 PASS", validator_validation.get("pass_count") == 126, str(validator_validation.get("pass_count")))
    checker.check("B08", "38번 0 FAIL", validator_validation.get("fail_count") == 0, str(validator_validation.get("fail_count")))
    expected_integrated_hash = str((validator.get("input_hashes") or {}).get("kdrg_v47_search_integrated") or "")
    checker.check("B09", "38번 검증 대상 hash 일치", integrated_hash_before == expected_integrated_hash, f"actual={integrated_hash_before} expected={expected_integrated_hash}")

    atomic_write_text(SERVICE_PATH, SERVICE_SOURCE)
    atomic_write_text(SMOKE_PATH, SMOKE_SOURCE)

    service_compile_ok = True
    smoke_compile_ok = True
    try:
        py_compile.compile(str(SERVICE_PATH), cfile=str(ROOT / "reports" / ".kdrg_search_service.pyc"), doraise=True)
    except Exception as exc:
        service_compile_ok = False
        service_compile_detail = repr(exc)
    else:
        service_compile_detail = "py_compile PASS"
    try:
        py_compile.compile(str(SMOKE_PATH), cfile=str(ROOT / "reports" / ".smoke_test_kdrg_search_service.pyc"), doraise=True)
    except Exception as exc:
        smoke_compile_ok = False
        smoke_compile_detail = repr(exc)
    else:
        smoke_compile_detail = "py_compile PASS"
    checker.check("B10", "service 문법검사", service_compile_ok, service_compile_detail)
    checker.check("B11", "smoke test 문법검사", smoke_compile_ok, smoke_compile_detail)
    checker.check("B12", "service 전면교체 내용 일치", sha256_file(SERVICE_PATH) == sha256_text(SERVICE_SOURCE), sha256_file(SERVICE_PATH))
    checker.check("B13", "smoke test 전면교체 내용 일치", sha256_file(SMOKE_PATH) == sha256_text(SMOKE_SOURCE), sha256_file(SMOKE_PATH))

    smoke_module = load_module("kdrg_runtime_smoke_generated", SMOKE_PATH)
    smoke_result = smoke_module.run_smoke(DATA_PATH)
    checker.extend(smoke_result.get("checks") or [])
    checker.check("B14", "smoke test 전체 PASS", smoke_result.get("status") == "PASS", f"{smoke_result.get('pass_count')} PASS / {smoke_result.get('fail_count')} FAIL")
    integrated_hash_after = sha256_file(DATA_PATH)
    checker.check("B15", "통합 JSON 미수정", integrated_hash_after == integrated_hash_before, f"before={integrated_hash_before} after={integrated_hash_after}")

    service_module = load_module("kdrg_search_service_generated_validation", SERVICE_PATH)
    service = service_module.KdrgSearchService(DATA_PATH)
    service_status = service.status()
    checker.check("B16", "생성 service 직접 import", service_status.get("ready") is True, str(service_status.get("ready")))

    result = checker.summary()
    payload = {
        "script_version": SCRIPT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "input": {
            "integrated_json_path": str(DATA_PATH),
            "integrated_json_sha256": integrated_hash_before,
            "data_schema_version": meta.get("schema_version"),
            "validator_report_path": str(VALIDATION_REPORT_PATH),
            "validator_report_sha256": sha256_file(VALIDATION_REPORT_PATH),
            "validator_version": validator.get("script_version"),
            "validator_pass_count": validator_validation.get("pass_count"),
            "validator_fail_count": validator_validation.get("fail_count"),
        },
        "outputs": {
            "service_path": str(SERVICE_PATH),
            "service_sha256": sha256_file(SERVICE_PATH),
            "smoke_test_path": str(SMOKE_PATH),
            "smoke_test_sha256": sha256_file(SMOKE_PATH),
        },
        "service_status": service_status,
        "smoke_test": {
            "status": smoke_result.get("status"),
            "pass_count": smoke_result.get("pass_count"),
            "fail_count": smoke_result.get("fail_count"),
            "total_count": smoke_result.get("total_count"),
            "semantic_context_counts": service_status.get("semantic_context_counts") or {},
        },
        "validation": result,
        "user_judgment_required": 0,
        "manual_excel_review": False,
        "source_data_modified": False,
    }
    atomic_write_json(REPORT_JSON_PATH, payload)
    atomic_write_text(REPORT_TXT_PATH, build_report(payload))

    if result["status"] == "PASS":
        print(
            "[PASS] PySide runtime adapter·검색 service 구축 완료: "
            f"49 smoke / {result['pass_count']} PASS / 0 FAIL"
        )
        print(f"service={SERVICE_PATH}")
        print(f"smoke={SMOKE_PATH}")
        print(f"report={REPORT_TXT_PATH}")
        return 0
    print(f"[FAIL] PySide runtime adapter·검색 service 구축 실패: {result['pass_count']} PASS / {result['fail_count']} FAIL")
    print(f"report={REPORT_TXT_PATH}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
