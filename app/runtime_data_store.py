"""최종 통합 JSON V2를 기존 PySide v0.2 화면 모델로 변환하는 runtime adapter.

화면은 기존 구조를 유지하지만 검색·상세·관계 데이터는
app.kdrg_search_service.KdrgSearchService를 기준으로 제공한다.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from app.kdrg_search_service import KdrgSearchError, KdrgSearchService
from app.models import (
    AADRGMapping,
    AdvancedCondition,
    CodeMember,
    ConditionGroup,
    MDCDef,
    RelationCandidate,
    RelationCodeMatch,
    RelationGroupMatch,
    RuleComponent,
    RuleDef,
    SearchResult,
    TableDef,
    normalize,
)


POSITIVE_CONTEXTS = {
    "positive_required_table",
    "required_table_with_optional_companion",
    "semantic_text_condition",
}
NEGATIVE_CONTEXTS = {
    "negative_or_exclusion_reference",
    "allowed_exception_under_negated_or_procedure",
    "optional_companion_table",
}
CATEGORY_TO_ENTITY = {
    "전체": "ALL",
    "ADRG": ["ADRG", "AADRG"],
    "AADRG": "AADRG",
    "RDRG": "RDRG",
    "TABLE": "TABLE",
    "상병코드": "CODE",
    "기타진단코드": "CODE",
    "수술·처치코드": "CODE",
    "검사·처치코드": "CODE",
    "부가코드": "CODE",
}
DEFAULT_RESULT_LIMIT = 200
SEARCH_RESULT_LIMIT = 500


def _unique(values: Iterable[Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return output


def _contains_hangul(value: str) -> bool:
    return any("가" <= char <= "힣" for char in value)


def _code_type_from_text(*values: Any) -> str:
    text = " ".join(str(value or "") for value in values).casefold()
    if any(token in text for token in ("secondary", "other diagnosis", "기타진단", "other_diagnosis")):
        return "기타진단코드"
    if any(token in text for token in ("diagnosis", "진단", "principal", "주진단")):
        return "상병코드"
    if any(token in text for token in ("add_on", "addon", "supplement", "부가", "additional")):
        return "부가코드"
    if any(token in text for token in ("test", "검사")):
        return "검사·처치코드"
    if any(token in text for token in ("procedure", "surgery", "operation", "시술", "수술", "처치")):
        return "수술·처치코드"
    return "수술·처치코드"


def _result_kind(code_type: str) -> str:
    return {
        "상병코드": "diagnosis_code",
        "기타진단코드": "secondary_diagnosis_code",
        "수술·처치코드": "procedure_code",
        "검사·처치코드": "test_code",
        "부가코드": "supplement_code",
    }.get(code_type, "procedure_code")


def _short_list(values: Iterable[Any], limit: int = 18) -> str:
    rows = _unique(values)
    if not rows:
        return "-"
    if len(rows) <= limit:
        return ", ".join(rows)
    return f"{', '.join(rows[:limit])} 외 {len(rows) - limit}개"


class KDRGRuntimeDataStore:
    """기존 MainWindow가 기대하는 interface를 최종 runtime service로 제공한다."""

    def __init__(self, data_path: Optional[object] = None) -> None:
        self.service = KdrgSearchService(Path(data_path) if data_path else None)
        self.raw = self.service.data
        self.meta = self.service.meta
        self.runtime_status = self.service.status()
        self.runtime_counts: Dict[str, int] = dict(self.runtime_status.get("counts") or {})

        self.version = str(self.runtime_status.get("data_version") or "KDRG V4.7")
        self.correction_basis = "2026-05-01"
        self.data_scope = (
            f"전체 ADRG {self.runtime_counts.get('adrg_records', 0):,}개 · "
            f"AADRG {self.runtime_counts.get('aadrg_records', 0):,}개 · "
            f"TABLE {self.runtime_counts.get('logical_table_records', 0):,}개 · "
            f"검색코드 {self.runtime_counts.get('unique_search_codes', 0):,}개"
        )
        self.ui_badge = "KDRG V4.7 FULL · RUNTIME V2"
        self.notice = "최종 통합 JSON V2와 독립검증된 runtime search service를 사용합니다."
        self.source_note = "KDRG V4.7 분류집 본문·부록·2026-05-01 교정표·공식 A/B/C 별표"
        self.abc_basis = "공식 별표 PDF의 AADRG exact code match만 적용"

        self._adrg_rows = {str(row.get("adrg") or ""): row for row in self.raw.get("adrg_records") or []}
        self._aadrg_rows = {str(row.get("aadrg") or ""): row for row in self.raw.get("aadrg_records") or []}
        self._rdrg_rows = {str(row.get("code") or ""): row for row in self.raw.get("rdrg_records") or []}
        self._table_rows = {str(row.get("logical_table_id") or ""): row for row in self.raw.get("logical_table_records") or []}
        self._code_rows = {normalize(row.get("code")): row for row in self.raw.get("code_records") or []}
        self._ast_rows = {str(row.get("adrg") or ""): row for row in self.raw.get("condition_ast_records") or []}

        self._code_types_by_code: Dict[str, Set[str]] = self._build_code_type_index()
        self._member_by_code: Dict[str, CodeMember] = self._build_member_index()
        self.tables: Dict[str, TableDef] = self._build_tables()
        self.rules: Dict[str, RuleDef] = self._build_rules()
        self.mdcs: Dict[str, MDCDef] = self._build_mdcs()
        self.code_to_tables: Dict[str, List[str]] = {
            normalize(code): list(row.get("logical_table_ids") or [])
            for code, row in ((str(item.get("code") or ""), item) for item in self.raw.get("code_records") or [])
        }
        self.table_to_rules: Dict[str, List[str]] = self._build_table_to_rules(positive=True)
        self.exclusion_table_to_rules: Dict[str, List[str]] = self._build_table_to_rules(positive=False)

    # ------------------------------------------------------------------
    # 변환 구축
    # ------------------------------------------------------------------

    def _build_code_type_index(self) -> Dict[str, Set[str]]:
        output: Dict[str, Set[str]] = defaultdict(set)
        for row in self.raw.get("code_records") or []:
            code = normalize(row.get("code"))
            for role in row.get("roles") or []:
                output[code].add(_code_type_from_text(role))
            for table_id in row.get("logical_table_ids") or []:
                table = self._table_rows.get(str(table_id)) or {}
                output[code].add(_code_type_from_text(table.get("logical_table_scope"), table.get("logical_table_type")))
            if not output[code]:
                output[code].add("수술·처치코드")
        return output

    def _build_member_index(self) -> Dict[str, CodeMember]:
        output: Dict[str, CodeMember] = {}
        for index, row in enumerate(self.raw.get("code_records") or [], start=1):
            code = str(row.get("code") or "")
            names = _unique(row.get("names") or [])
            ko_names = [name for name in names if _contains_hangul(name)]
            en_names = [name for name in names if not _contains_hangul(name)]
            output[normalize(code)] = CodeMember(
                code=code,
                name_en=" / ".join(en_names[:2]),
                name_ko=" / ".join(ko_names[:2]) or (names[0] if names else "코드명 원천 미수록"),
                original_order=index,
            )
        return output

    def _table_source_label(self, row: dict[str, Any]) -> str:
        parts: list[str] = []
        source_adrgs = row.get("source_adrgs") or []
        families = row.get("source_adrg_families") or []
        if source_adrgs:
            parts.append(f"원문 정의 ADRG {_short_list(source_adrgs, 10)}")
        if families:
            parts.append(f"원문 family {_short_list(families, 10)}")
        refs = row.get("source_refs") or []
        if refs:
            first = refs[0]
            if isinstance(first, dict):
                page = first.get("pdf_page") or first.get("page") or first.get("pdf_page_start")
                if page:
                    parts.append(f"PDF p.{page}")
            elif str(first).strip():
                parts.append(str(first).strip())
        return " · ".join(parts) or "KDRG V4.7 분류집 본문"

    def _build_tables(self) -> Dict[str, TableDef]:
        output: Dict[str, TableDef] = {}
        for row in self.raw.get("logical_table_records") or []:
            table_id = str(row.get("logical_table_id") or "")
            code_type = _code_type_from_text(row.get("logical_table_scope"), row.get("logical_table_type"))
            members: list[CodeMember] = []
            for index, code in enumerate(row.get("codes") or [], start=1):
                base = self._member_by_code.get(normalize(code))
                if base:
                    members.append(CodeMember(base.code, base.name_en, base.name_ko, index))
                else:
                    members.append(CodeMember(str(code), "", "코드명 원천 미수록", index))
            output[table_id] = TableDef(
                table_id=table_id,
                display_label=str(row.get("display_name") or table_id),
                code_type=code_type,
                source_page=self._table_source_label(row),
                members=tuple(members),
            )
        return output

    def _build_mdcs(self) -> Dict[str, MDCDef]:
        codes = sorted({str(row.get("mdc") or "") for row in self.raw.get("adrg_records") or [] if str(row.get("mdc") or "")})
        output: Dict[str, MDCDef] = {}
        for code in codes:
            display_code = code if code == "PRE" else code.zfill(2)
            name = "선행 분류" if code == "PRE" else f"MDC {display_code}"
            aliases = (f"MDC {display_code}", f"MDC{display_code}", name)
            output[display_code] = MDCDef(display_code, name, aliases)
        return output

    def _page_label(self, source_block: dict[str, Any]) -> str:
        start = source_block.get("pdf_page_start")
        end = source_block.get("pdf_page_end")
        if start and end and start != end:
            return f"KDRG V4.7 분류집 PDF p.{start}-{end}"
        if start:
            return f"KDRG V4.7 분류집 PDF p.{start}"
        return "KDRG V4.7 분류집 본문"

    @staticmethod
    def _descendants(node_id: str, nodes: dict[str, dict[str, Any]]) -> set[str]:
        found: set[str] = set()
        stack = [node_id]
        while stack:
            current = stack.pop()
            if not current or current in found:
                continue
            found.add(current)
            node = nodes.get(current) or {}
            stack.extend(str(value) for value in node.get("child_node_ids") or [])
        return found

    def _condition_groups(self, adrg: str, ast: Optional[dict[str, Any]]) -> Tuple[ConditionGroup, ...]:
        if not ast:
            return (ConditionGroup(1, "조건식 1", "", (), ("본문 조건 AST 없음",), ()),)
        node_rows = list(ast.get("nodes") or [])
        nodes = {str(node.get("node_id") or ""): node for node in node_rows if str(node.get("node_id") or "")}
        root_id = str(ast.get("root_node_id") or "")
        root = nodes.get(root_id) or {}
        root_set = self._descendants(root_id, nodes) if root_id else set(nodes)

        branch_ids: list[str] = []
        shared: set[str] = set()
        if str(root.get("node_type") or "") == "OR" and len(root.get("child_node_ids") or []) >= 2:
            branch_ids = [str(value) for value in root.get("child_node_ids") or []]
        else:
            direct_or = next(
                (
                    nodes.get(str(child))
                    for child in root.get("child_node_ids") or []
                    if str((nodes.get(str(child)) or {}).get("node_type") or "") == "OR"
                    and len((nodes.get(str(child)) or {}).get("child_node_ids") or []) >= 2
                ),
                None,
            )
            if direct_or:
                or_id = str(direct_or.get("node_id") or "")
                branch_ids = [str(value) for value in direct_or.get("child_node_ids") or []]
                shared = root_set - self._descendants(or_id, nodes)
        if not branch_ids:
            branch_sets = [root_set or set(nodes)]
        else:
            branch_sets = [self._descendants(branch_id, nodes) | shared for branch_id in branch_ids]

        context_lookup: dict[tuple[str, str], dict[str, Any]] = {}
        for (ctx_adrg, table_id), values in self.service._semantic_context_index.items():
            if str(ctx_adrg) != adrg:
                continue
            for value in values:
                context_lookup[(str(value.get("node_id") or ""), str(table_id))] = value

        groups: list[ConditionGroup] = []
        for group_index, node_set in enumerate(branch_sets, start=1):
            positive: list[RuleComponent] = []
            negative: list[RuleComponent] = []
            requirements: list[str] = []
            seen_positive: set[str] = set()
            seen_negative: set[str] = set()
            seen_requirement: set[str] = set()
            for node in node_rows:
                node_id = str(node.get("node_id") or "")
                if node_id not in node_set:
                    continue
                table_ids = _unique(node.get("logical_table_ids") or [])
                for table_id in table_ids:
                    context = context_lookup.get((node_id, table_id)) or {
                        "context": "positive_required_table",
                        "display_label": "필수 TABLE",
                    }
                    context_name = str(context.get("context") or "")
                    label = str(context.get("display_label") or "")
                    if context_name in NEGATIVE_CONTEXTS:
                        if table_id not in seen_negative:
                            negative.append(RuleComponent(table_id, "AND" if negative else "", "", label))
                            seen_negative.add(table_id)
                    else:
                        if table_id not in seen_positive:
                            positive.append(RuleComponent(table_id, "AND" if positive else "", "", label))
                            seen_positive.add(table_id)
                if not table_ids and str(node.get("node_type") or "") == "TEXT_CONDITION":
                    text = str(node.get("display_text") or node.get("source_fragment") or "").strip()
                    if 2 <= len(text) <= 180 and text not in seen_requirement:
                        requirements.append(text)
                        seen_requirement.add(text)
            groups.append(
                ConditionGroup(
                    group_no=group_index,
                    group_label=f"조건식 {group_index}",
                    join_to_next_group="OR" if group_index < len(branch_sets) else "",
                    components=tuple(positive),
                    requirements=tuple(requirements[:12]),
                    exclude_components=tuple(negative),
                )
            )
        return tuple(groups)

    def _build_rules(self) -> Dict[str, RuleDef]:
        aadrg_by_adrg: Dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in self.raw.get("aadrg_records") or []:
            aadrg_by_adrg[str(row.get("adrg") or "")].append(row)

        output: Dict[str, RuleDef] = {}
        for row in self.raw.get("adrg_records") or []:
            adrg = str(row.get("adrg") or "")
            children = sorted(aadrg_by_adrg.get(adrg, []), key=lambda item: str(item.get("aadrg") or ""))
            mappings = tuple(
                AADRGMapping(
                    aadrg=str(child.get("aadrg") or ""),
                    group_code=str(child.get("classification_code") or ""),
                    group_name=str(child.get("classification_display_label") or "분류 미부여"),
                    aadrg_name=str(child.get("group_name") or ""),
                )
                for child in children
            )
            class_codes = _unique(child.get("classification_code") for child in children if child.get("classification_code"))
            class_labels = _unique(child.get("classification_display_label") for child in children if child.get("classification_display_label"))
            group_code = class_codes[0] if len(class_codes) == 1 else ""
            group_name = class_labels[0] if len(class_labels) == 1 else ("AADRG별 혼합 분류" if class_codes else "분류 미부여")
            ast = self._ast_rows.get(adrg)
            source_raw = str((ast or {}).get("source_raw_text") or "본문 조건 AST 없음")
            canonical = str((ast or {}).get("canonical_expression") or source_raw)
            output[adrg] = RuleDef(
                adrg=adrg,
                aadrg=str(children[0].get("aadrg") or "") if children else "",
                mdc=str(row.get("mdc") or ""),
                group_code=group_code,
                group_name=group_name,
                title=str(row.get("adrg_name") or adrg),
                subtitle="",
                condition_text=source_raw,
                source_page=self._page_label(row.get("source_block") or {}),
                condition_summary=canonical,
                condition_groups=self._condition_groups(adrg, ast),
                aadrg_mappings=mappings,
            )
        return output

    def _build_table_to_rules(self, *, positive: bool) -> Dict[str, List[str]]:
        output: Dict[str, List[str]] = defaultdict(list)
        for adrg, rule in self.rules.items():
            components = rule.components if positive else rule.exclusion_components
            for component in components:
                if adrg not in output[component.table_id]:
                    output[component.table_id].append(adrg)
        return {key: sorted(values) for key, values in output.items()}

    # ------------------------------------------------------------------
    # 기존 MainWindow 호환 API
    # ------------------------------------------------------------------

    def rules_for_mdc(self, mdc: str) -> List[RuleDef]:
        code = str(mdc or "").strip().upper()
        if code != "PRE":
            code = code.zfill(2)
        return [rule for rule in self.rules.values() if str(rule.mdc).upper() == code]

    def exact_table_ids_for_code(self, code: str, selected_type: str = "자동판별") -> List[str]:
        normalized = normalize(code)
        table_ids = list(self.code_to_tables.get(normalized, []))
        if selected_type and selected_type != "자동판별":
            code_types = self._code_types_by_code.get(normalized, set())
            if selected_type not in code_types:
                return []
            table_ids = [
                table_id
                for table_id in table_ids
                if self.tables.get(table_id) and (
                    self.tables[table_id].code_type == selected_type or selected_type in code_types
                )
            ]
        return table_ids

    def rules_for_code(self, code: str) -> List[RuleDef]:
        adrg_ids: set[str] = set()
        for table_id in self.code_to_tables.get(normalize(code), []):
            adrg_ids.update(self.table_to_rules.get(table_id, []))
        return [self.rules[adrg] for adrg in sorted(adrg_ids) if adrg in self.rules]

    def exclusion_rules_for_code(self, code: str) -> List[RuleDef]:
        adrg_ids: set[str] = set()
        for table_id in self.code_to_tables.get(normalize(code), []):
            adrg_ids.update(self.exclusion_table_to_rules.get(table_id, []))
        return [self.rules[adrg] for adrg in sorted(adrg_ids) if adrg in self.rules]

    def exclusion_tables_for_code(self, code: str) -> List[TableDef]:
        ids = set(self.code_to_tables.get(normalize(code), [])) & set(self.exclusion_table_to_rules)
        return [self.tables[table_id] for table_id in sorted(ids)]

    def tables_for_code(self, code: str) -> List[TableDef]:
        return [self.tables[table_id] for table_id in self.code_to_tables.get(normalize(code), []) if table_id in self.tables]

    def member_for_code(self, code: str) -> Optional[CodeMember]:
        return self._member_by_code.get(normalize(code))

    def rules_for_table(self, table_id: str) -> List[RuleDef]:
        return [self.rules[adrg] for adrg in self.table_to_rules.get(table_id, []) if adrg in self.rules]

    def relation_summary_for_code(self, code: str) -> dict[str, str]:
        row = self._code_rows.get(normalize(code)) or {}
        return {
            "physical_source": _short_list(row.get("source_adrgs") or []),
            "condition_usage": _short_list(row.get("condition_adrgs") or []),
            "runtime_related": _short_list(row.get("related_adrgs") or []),
            "source_families": _short_list(row.get("source_adrg_families") or []),
        }

    def relation_summary_for_table(self, table_id: str) -> dict[str, str]:
        row = self._table_rows.get(str(table_id)) or {}
        return {
            "physical_source": _short_list(row.get("source_adrgs") or []),
            "condition_usage": _short_list(row.get("condition_adrgs") or []),
            "runtime_related": _short_list(row.get("related_adrgs") or []),
            "source_families": _short_list(row.get("source_adrg_families") or []),
        }

    def _mdc_search(self, query: str) -> List[SearchResult]:
        q = normalize(query)
        results: list[SearchResult] = []
        for mdc in self.mdcs.values():
            fields = [mdc.mdc, f"MDC {mdc.mdc}", mdc.name, *mdc.aliases]
            if not q or any(q in normalize(value) for value in fields):
                results.append(
                    SearchResult(
                        "mdc",
                        mdc.mdc,
                        f"MDC {mdc.mdc}",
                        f"{mdc.name} · ADRG {len(self.rules_for_mdc(mdc.mdc))}개",
                        0 if q and q in {normalize(value) for value in fields} else 10,
                        mdc=mdc.mdc,
                    )
                )
        return sorted(results, key=lambda row: (row.priority, row.key))

    def _classification_for_adrg(self, adrg: str) -> tuple[str, str]:
        row = self._adrg_rows.get(adrg) or {}
        codes = _unique(row.get("abc_classification_codes") or [])
        labels = _unique(row.get("abc_display_labels") or [])
        if len(codes) == 1:
            return codes[0], labels[0] if labels else ""
        if len(codes) > 1:
            return "", "AADRG별 혼합 분류"
        return "", "분류 미부여"

    def _code_type_for_result(self, code: str, category: str) -> str:
        if category in {"상병코드", "기타진단코드", "수술·처치코드", "검사·처치코드", "부가코드"}:
            return category
        types = sorted(self._code_types_by_code.get(normalize(code), {"수술·처치코드"}))
        priority = ["상병코드", "기타진단코드", "수술·처치코드", "검사·처치코드", "부가코드"]
        return next((name for name in priority if name in types), types[0])

    def search(self, query: str, category: str = "전체") -> List[SearchResult]:
        text = str(query or "").strip()
        if category == "MDC":
            return self._mdc_search(text)
        if not text:
            rows = sorted(self.rules.values(), key=lambda item: item.adrg)
            default = next((rule for rule in rows if rule.adrg == "E011"), None)
            if default:
                rows = [default, *[rule for rule in rows if rule.adrg != "E011"]]
            return [
                SearchResult(
                    "adrg",
                    rule.adrg,
                    rule.adrg,
                    rule.title_full,
                    20,
                    rule.group_code,
                    rule.group_name,
                    rule.mdc,
                )
                for rule in rows[:DEFAULT_RESULT_LIMIT]
            ]

        entity_type = CATEGORY_TO_ENTITY.get(category, "ALL")
        response = self.service.search(text, entity_type, limit=SEARCH_RESULT_LIMIT)
        output: list[SearchResult] = []
        seen: set[tuple[str, str, str]] = set()
        for item in response.get("results") or []:
            type_name = str(item.get("entity_type") or "")
            entity_id = str(item.get("entity_id") or "")
            summary = item.get("summary") or {}
            priority = max(0, 1000 - int(item.get("score") or 0))
            if type_name == "CODE":
                code_type = self._code_type_for_result(entity_id, category)
                if category in {"상병코드", "기타진단코드", "수술·처치코드", "검사·처치코드", "부가코드"}:
                    if category not in self._code_types_by_code.get(normalize(entity_id), set()):
                        continue
                result = SearchResult(
                    _result_kind(code_type),
                    entity_id,
                    entity_id,
                    str(item.get("subtitle") or "코드명 원천 미수록"),
                    priority,
                )
            elif type_name == "ADRG":
                group_code, group_name = self._classification_for_adrg(entity_id)
                row = self._adrg_rows.get(entity_id) or {}
                result = SearchResult("adrg", entity_id, entity_id, str(row.get("adrg_name") or item.get("subtitle") or ""), priority, group_code, group_name, str(row.get("mdc") or ""))
            elif type_name == "AADRG":
                row = self._aadrg_rows.get(entity_id) or {}
                parent = str(row.get("adrg") or entity_id[:4])
                result = SearchResult(
                    "aadrg",
                    parent,
                    entity_id,
                    f"{row.get('group_name') or ''} · ADRG {parent}",
                    priority,
                    str(row.get("classification_code") or ""),
                    str(row.get("classification_display_label") or "분류 미부여"),
                    str(row.get("mdc") or ""),
                )
            elif type_name == "RDRG":
                row = self._rdrg_rows.get(entity_id) or {}
                parent = str(row.get("adrg") or "")
                aadrg = str(row.get("aadrg") or "")
                aadrg_row = self._aadrg_rows.get(aadrg) or {}
                result = SearchResult(
                    "aadrg",
                    parent,
                    entity_id,
                    f"{row.get('group_name') or ''} · AADRG {aadrg} · ADRG {parent}",
                    priority,
                    str(aadrg_row.get("classification_code") or ""),
                    str(aadrg_row.get("classification_display_label") or "분류 미부여"),
                    str((self._adrg_rows.get(parent) or {}).get("mdc") or ""),
                )
            elif type_name == "TABLE":
                row = self._table_rows.get(entity_id) or {}
                result = SearchResult(
                    "table",
                    entity_id,
                    str(row.get("display_name") or entity_id),
                    f"{_code_type_from_text(row.get('logical_table_scope'), row.get('logical_table_type'))} · {row.get('code_count', 0)}개 코드",
                    priority,
                )
            else:
                continue
            signature = (result.kind, result.key, result.label)
            if signature not in seen:
                seen.add(signature)
                output.append(result)
        return sorted(output, key=lambda row: (row.priority, row.kind, row.label))

    def relation_search(self, conditions: List[AdvancedCondition], operator: str) -> List[RelationCandidate]:
        operator = normalize(operator) or "AND"
        total_count = len(conditions)
        condition_tables: List[Tuple[AdvancedCondition, Set[str]]] = [
            (condition, set(self.exact_table_ids_for_code(condition.code, condition.code_type)))
            for condition in conditions
        ]
        candidates: List[RelationCandidate] = []
        for rule in self.rules.values():
            rule_table_ids = {component.table_id for component in rule.components}
            exclusion_ids = {component.table_id for component in rule.exclusion_components}
            if any(global_ids & exclusion_ids for _, global_ids in condition_tables):
                continue
            rule_matches: list[RelationCodeMatch] = []
            matched_count = 0
            for condition, global_ids in condition_tables:
                matched_ids = tuple(sorted(global_ids & rule_table_ids))
                if matched_ids:
                    matched_count += 1
                rule_matches.append(RelationCodeMatch(condition.code, condition.code_type, matched_ids))
            if operator == "AND" and matched_count != total_count:
                continue
            if operator == "OR" and matched_count == 0:
                continue
            group_matches: list[RelationGroupMatch] = []
            strict_group_exists = False
            for group in rule.condition_groups:
                group_ids = {component.table_id for component in group.components}
                matches: list[RelationCodeMatch] = []
                hit_count = 0
                for condition, global_ids in condition_tables:
                    ids = tuple(sorted(global_ids & group_ids))
                    if ids:
                        hit_count += 1
                    matches.append(RelationCodeMatch(condition.code, condition.code_type, ids))
                all_inputs = hit_count == total_count
                if hit_count:
                    group_matches.append(RelationGroupMatch(group.group_no, group.group_label, tuple(matches), all_inputs))
                strict_group_exists = strict_group_exists or all_inputs
            level = "strict" if matched_count == total_count and strict_group_exists else "split" if matched_count == total_count else "partial"
            candidates.append(RelationCandidate(rule.adrg, level, matched_count, total_count, tuple(rule_matches), tuple(group_matches)))
        rank = {"strict": 0, "split": 1, "partial": 2}
        return sorted(candidates, key=lambda item: (rank.get(item.relation_level, 9), -item.matched_count, item.adrg))


KDRGDataStore = KDRGRuntimeDataStore

__all__ = ["KDRGRuntimeDataStore", "KDRGDataStore", "KdrgSearchError"]
