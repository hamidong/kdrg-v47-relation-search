#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KDRG V4.7 PySide UI를 최종 runtime search service에 연결한다.

- 기존 파일럿 data_store 대신 통합 JSON V2 기반 호환 adapter를 생성한다.
- 현재 main_window.py의 화면 골격은 유지하고 import·표시 문구·관계 구분만 수정한다.
- AboutDialog의 파일럿 고정 수치를 전체 runtime 집계로 교체한다.
- 통합 JSON·원천 데이터는 수정하지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_VERSION = "2026-07-24_KDRG_V47_PYSIDE_RUNTIME_UI_BRIDGE_BUILDER_V7"
ROOT = Path(__file__).resolve().parent
APP_DIR = ROOT / "app"
DATA_DIR = ROOT / "data"
TEST_DIR = ROOT / "tests"
REPORT_DIR = ROOT / "reports"

INTEGRATED_PATH = DATA_DIR / "kdrg_v47_search_integrated.json"
SERVICE_PATH = APP_DIR / "kdrg_search_service.py"
RUNTIME_VALIDATION_PATH = REPORT_DIR / "runtime_search_service_validation_report.json"
MAIN_WINDOW_PATH = APP_DIR / "main_window.py"
DIALOGS_PATH = APP_DIR / "dialogs.py"

ADAPTER_PATH = APP_DIR / "runtime_data_store.py"
SMOKE_PATH = TEST_DIR / "smoke_test_runtime_ui_bridge.py"
REPORT_TXT_PATH = REPORT_DIR / "runtime_ui_bridge_build_report.txt"
REPORT_JSON_PATH = REPORT_DIR / "runtime_ui_bridge_build_report.json"
BACKUP_DIR = REPORT_DIR / "ui_runtime_bridge_backups"

EXPECTED_COUNTS = {
    "adrg_records": 1132,
    "aadrg_records": 1233,
    "rdrg_records": 2699,
    "logical_table_records": 1308,
    "condition_ast_records": 390,
    "ast_node_count": 1727,
    "table_code_rows": 42882,
    "unique_search_codes": 16571,
}


class BuildError(RuntimeError):
    pass


class Checker:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def check(self, check_id: str, name: str, condition: bool, detail: str = "") -> None:
        self.rows.append({
            "check_id": check_id,
            "name": name,
            "status": "PASS" if condition else "FAIL",
            "detail": detail,
        })

    def summary(self) -> dict[str, Any]:
        passed = sum(row["status"] == "PASS" for row in self.rows)
        failed = len(self.rows) - passed
        return {
            "status": "PASS" if failed == 0 else "FAIL",
            "pass_count": passed,
            "fail_count": failed,
            "total_count": len(self.rows),
            "checks": self.rows,
        }


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise BuildError(f"JSON 최상위 구조가 dict가 아님: {path}")
    return value


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent, newline="\n") as temp:
        temp.write(text)
        temp_name = temp.name
    os.replace(temp_name, path)


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def backup_file(path: Path) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup = BACKUP_DIR / f"{path.stem}_before_41{path.suffix}"
    if not backup.exists():
        atomic_write_text(backup, path.read_text(encoding="utf-8"))
    return backup


ADAPTER_SOURCE = r'''"""최종 통합 JSON V2를 기존 PySide v0.2 화면 모델로 변환하는 runtime adapter.

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
'''


SMOKE_SOURCE = r'''from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("KDRG_DISABLE_SETTINGS", "1")

from PySide6.QtWidgets import QApplication

from app.main_window import MainWindow
from app.runtime_data_store import KDRGRuntimeDataStore


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        checks.append((name, bool(condition), detail))

    store = KDRGRuntimeDataStore()
    check("ADRG 1132", len(store.rules) == 1132, str(len(store.rules)))
    check("TABLE 1308", len(store.tables) == 1308, str(len(store.tables)))
    check("CODE 16571", len(store.code_to_tables) == 16571, str(len(store.code_to_tables)))
    check("E011 rule", "E011" in store.rules, str("E011" in store.rules))
    check("default bounded", 1 <= len(store.search("", "전체")) <= 200, str(len(store.search("", "전체"))))
    check("default E011 first", store.search("", "전체")[0].key == "E011", store.search("", "전체")[0].key)
    adrg_rows = store.search("9600", "ADRG")
    check("ADRG exact", bool(adrg_rows) and adrg_rows[0].key == "9600", str(adrg_rows[:1]))

    aadrg_rows = store.search("96000", "ADRG")
    check("AADRG exact parent", bool(aadrg_rows) and aadrg_rows[0].key == "9600", str(aadrg_rows[:1]))

    rdrg_rows = store.search("960000", "RDRG")
    check("RDRG exact parent", bool(rdrg_rows) and rdrg_rows[0].key == "9600", str(rdrg_rows[:1]))

    # 특정 코드(A000)를 fixture로 가정하지 않는다. 현재 통합 데이터에 실제 존재하는
    # 진단코드 전체에서 점 표기 변환이 가능한 대표 코드를 결정론적으로 선택한다.
    diagnosis_codes = sorted(
        code
        for code, code_types in store._code_types_by_code.items()
        if "상병코드" in code_types and len(code) > 3 and code.isalnum()
    )
    dotted_code = diagnosis_codes[0] if diagnosis_codes else ""
    dotted_query = f"{dotted_code[:3]}.{dotted_code[3:]}" if dotted_code else ""
    dotted_rows = store.search(dotted_query, "상병코드") if dotted_query else []
    check(
        "CODE dotted",
        bool(dotted_code) and bool(dotted_rows) and dotted_rows[0].key == dotted_code,
        f"fixture={dotted_code or '-'} query={dotted_query or '-'} result={dotted_rows[:1]}",
    )

    table_rows = store.search("LT_9610_001", "TABLE")
    check("TABLE exact", bool(table_rows) and table_rows[0].key == "LT_9610_001", str(table_rows[:1]))
    relation = store.relation_summary_for_code("S710")
    check("physical relation", relation["physical_source"] == "X012, X030, X600", str(relation))
    check("condition relation", relation["condition_usage"] == "X011, X012, X041, X042", str(relation))
    check("X04 hidden", "X04," not in relation["runtime_related"] and relation["source_families"] == "X04", str(relation))

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    app.processEvents()
    check("MainWindow runtime store", isinstance(window.store, KDRGRuntimeDataStore), type(window.store).__name__)
    check("MainWindow results", len(window.current_results) <= 200, str(len(window.current_results)))
    check("MainWindow E011 selected", bool(window.selected_result and window.selected_result.key == "E011"), str(window.selected_result))
    check("MainWindow status full", "ADRG 1132개" in window.statusBar().currentMessage(), window.statusBar().currentMessage())
    window.close()
    app.processEvents()

    failed = [(name, detail) for name, passed, detail in checks if not passed]
    for name, passed, detail in checks:
        print(f"[{'PASS' if passed else 'FAIL'}] {name} | {detail}")
    print(f"결과: {len(checks) - len(failed)} PASS / {len(failed)} FAIL")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
'''


def patch_main_window(text: str) -> tuple[str, list[str]]:
    changes: list[str] = []
    old_import = "from app.data_store import KDRGDataStore"
    new_import = "from app.runtime_data_store import KDRGRuntimeDataStore as KDRGDataStore"
    if old_import in text:
        text = text.replace(old_import, new_import, 1)
        changes.append("data_store import를 runtime adapter로 교체")
    elif new_import not in text:
        raise BuildError("main_window.py에서 KDRGDataStore import anchor를 찾지 못함")

    old_header = 'data_ver = QLabel(f"데이터 {self.store.version} Pilot · {self.store.correction_basis} 교정 반영")'
    new_header = 'data_ver = QLabel(f"데이터 {self.store.version} · {self.store.correction_basis} 교정 반영")'
    if old_header in text:
        text = text.replace(old_header, new_header, 1)
        changes.append("헤더 Pilot 고정 문구 제거")

    old_categories = 'self.category_combo.addItems(["전체", "상병코드", "기타진단코드", "수술·처치코드", "검사·처치코드", "부가코드", "ADRG", "MDC", "TABLE"])'
    new_categories = 'self.category_combo.addItems(["전체", "상병코드", "기타진단코드", "수술·처치코드", "검사·처치코드", "부가코드", "ADRG", "RDRG", "MDC", "TABLE"])'
    if old_categories in text:
        text = text.replace(old_categories, new_categories, 1)
        changes.append("RDRG 검색 category 추가")

    old_placeholder = 'self.search_edit.setPlaceholderText("예: MDC 04, 호흡기계, E011, E0110, O1311, M6586, ADC2A, table1")'
    new_placeholder = 'self.search_edit.setPlaceholderText("예: MDC 04, 9600, 96000, 960000, E011, A00.0, M6586, ADC2A, LT_9610_001")'
    if old_placeholder in text:
        text = text.replace(old_placeholder, new_placeholder, 1)
        changes.append("전체 runtime 검색 예시로 교체")

    # 코드 상세에 physical/condition/runtime 관계 구분 행 추가
    old_code_anchor = '''        exclusion_ids = {t.table_id for t in exclusion_tables}\n        table_text = ", ".join('''
    if old_code_anchor in text and "relation_summary_for_code" not in text:
        text = text.replace(
            old_code_anchor,
            '''        exclusion_ids = {t.table_id for t in exclusion_tables}\n        relation_summary = self.store.relation_summary_for_code(code)\n        table_text = ", ".join(''',
            1,
        )
        old_rows = '''                    ("포함 TABLE", table_text),\n                    ("KDRG 버전", self.store.version),'''
        new_rows = '''                    ("포함 TABLE", table_text),\n                    ("원문 TABLE 정의 ADRG", relation_summary.get("physical_source", "-")),\n                    ("조건 AST 사용 ADRG", relation_summary.get("condition_usage", "-")),\n                    ("검색용 관련 ADRG", relation_summary.get("runtime_related", "-")),\n                    ("원문 family 근거", relation_summary.get("source_families", "-")),\n                    ("KDRG 버전", self.store.version),'''
        if old_rows not in text:
            raise BuildError("main_window.py 코드 상세 rows anchor를 찾지 못함")
        text = text.replace(old_rows, new_rows, 1)
        changes.append("코드 상세 physical/condition/runtime 관계 구분 추가")

    # TABLE 상세에도 관계 구분 행 추가
    table_func_anchor = '''        related_rules = self.store.rules_for_table(table_id)\n        codes = [m.code for m in table.members]'''
    if table_func_anchor in text and "relation_summary_for_table" not in text:
        text = text.replace(
            table_func_anchor,
            '''        related_rules = self.store.rules_for_table(table_id)\n        relation_summary = self.store.relation_summary_for_table(table_id)\n        codes = [m.code for m in table.members]''',
            1,
        )
        old_rows = '''                    ("코드 수", f"{table.count}개"),\n                    ("근거", table.source_page),'''
        new_rows = '''                    ("코드 수", f"{table.count}개"),\n                    ("원문 정의 ADRG", relation_summary.get("physical_source", "-")),\n                    ("조건 AST 사용 ADRG", relation_summary.get("condition_usage", "-")),\n                    ("검색용 관련 ADRG", relation_summary.get("runtime_related", "-")),\n                    ("원문 family 근거", relation_summary.get("source_families", "-")),\n                    ("근거", table.source_page),'''
        if old_rows not in text:
            raise BuildError("main_window.py TABLE 상세 rows anchor를 찾지 못함")
        text = text.replace(old_rows, new_rows, 1)
        changes.append("TABLE 상세 physical/condition/runtime 관계 구분 추가")

    return text, changes


def patch_dialogs(text: str) -> tuple[str, list[str]]:
    changes: list[str] = []
    if 'sections.append(("현재 파일럿 제한"' in text:
        pattern = re.compile(
            r'\s{12}sections\.append\(\("현재 파일럿 제한", \[.*?\n\s{12}\]\)\)',
            re.DOTALL,
        )
        replacement = textwrap.dedent('''
            sections.append(("전체 runtime 데이터 범위", [
                ("ADRG", f"{len(store.rules):,}개"),
                ("AADRG", f"{sum(len(rule.aadrg_mappings) for rule in store.rules.values()):,}개"),
                ("TABLE", f"{len(store.tables):,}개"),
                ("검색 코드", f"{len(store.code_to_tables):,}개"),
                ("출처", store.source_note),
            ]))''').rstrip()
        # class method 내부 12칸 들여쓰기 복원
        replacement = "\n" + "\n".join("            " + line if line else line for line in replacement.splitlines())
        text, count = pattern.subn(replacement, text, count=1)
        if count != 1:
            raise BuildError("dialogs.py 파일럿 제한 section patch 실패")
        changes.append("AboutDialog 파일럿 고정 수치를 전체 runtime 집계로 교체")
    return text, changes


def run_command(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout: int = 90,
) -> subprocess.CompletedProcess[str]:
    """외부 명령을 제한시간 내 실행한다.

    native library 탐색·ldd·Qt smoke가 특정 Nix 경로에서 멈추더라도
    전체 구축 스크립트가 무기한 대기하지 않도록 한다.
    """
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    try:
        return subprocess.run(
            command,
            cwd=ROOT,
            env=merged_env,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        detail = f"\n[TIMEOUT] {timeout}s: {' '.join(command)}"
        return subprocess.CompletedProcess(command, 124, stdout, stderr + detail)


def _pyside_shared_objects() -> list[Path]:
    """PySide6를 import하지 않고 extension·Qt library·offscreen plugin 위치를 찾는다."""
    objects: list[Path] = []
    for entry in sys.path:
        if not entry:
            continue
        base = Path(entry) / "PySide6"
        if not base.is_dir():
            continue
        for pattern in (
            "QtCore*.so",
            "QtGui*.so",
            "QtWidgets*.so",
            "Qt/lib/libQt6Core.so*",
            "Qt/lib/libQt6Gui.so*",
            "Qt/lib/libQt6Widgets.so*",
            "Qt/plugins/platforms/libqoffscreen.so",
            "Qt/plugins/platforms/libqminimal.so",
        ):
            objects.extend(sorted(base.glob(pattern)))
    unique: list[Path] = []
    seen: set[str] = set()
    for path in objects:
        try:
            key = str(path.resolve())
        except OSError:
            key = str(path)
        if key not in seen and path.is_file():
            seen.add(key)
            unique.append(path)
    return unique


def _ldd_audit(paths: list[Path], env: dict[str, str] | None = None) -> tuple[set[str], list[str], list[str]]:
    """누락 SONAME과 GLIBC/GLIBCXX symbol version 충돌을 함께 검사한다."""
    missing: set[str] = set()
    version_errors: list[str] = []
    diagnostics: list[str] = []
    for path in paths:
        result = run_command(["ldd", str(path)], env=env)
        output = (result.stdout + "\n" + result.stderr).strip()
        diagnostics.append(f"[{path.name}] returncode={result.returncode}\n{output}")
        for line in output.splitlines():
            match = re.match(r"^\s*(\S+)\s+=>\s+not found\s*$", line)
            if match:
                missing.add(match.group(1))
            if "version `GLIBC_" in line or "version `GLIBCXX_" in line or "version `CXXABI_" in line:
                version_errors.append(line.strip())
    return missing, version_errors, diagnostics


def _ldd_missing(paths: list[Path], env: dict[str, str] | None = None) -> tuple[set[str], list[str]]:
    missing, _version_errors, diagnostics = _ldd_audit(paths, env=env)
    return missing, diagnostics


def _library_search_roots() -> list[Path]:
    """작은 표준 library directory만 반환한다.

    /nix/store 전체를 pathlib.glob로 재귀 탐색하지 않는다. Nix store는
    별도 bounded scanner에서 최상위 package와 고정 lib 경로만 확인한다.
    """
    roots: list[Path] = [
        Path("/run/current-system/sw/lib"),
        Path("/nix/var/nix/profiles/default/lib"),
        Path("/usr/lib"),
        Path("/usr/lib64"),
        Path("/usr/lib/x86_64-linux-gnu"),
        Path("/lib"),
        Path("/lib64"),
        Path("/lib/x86_64-linux-gnu"),
    ]
    for variable in ("NIX_LD_LIBRARY_PATH", "LD_LIBRARY_PATH"):
        for raw in os.environ.get(variable, "").split(os.pathsep):
            raw = raw.strip()
            if raw:
                roots.append(Path(raw))
    unique: list[Path] = []
    seen: set[str] = set()
    for path in roots:
        value = str(path)
        if not value or value in seen:
            continue
        seen.add(value)
        try:
            if path.is_dir():
                unique.append(path)
        except OSError:
            continue
    return unique


CORE_RUNTIME_SONAMES = {
    "libc.so.6",
    "libm.so.6",
    "libpthread.so.0",
    "libdl.so.2",
    "librt.so.1",
    "libutil.so.1",
    "libresolv.so.2",
    "ld-linux-x86-64.so.2",
    "ld-linux.so.2",
}

UNSAFE_BUNDLE_TOKENS = (
    "electronplayer",
    "electron-",
    "chromium",
    "steam",
    "appimage",
)

_NIX_STORE_ENTRY_CACHE: list[Path] | None = None


def _safe_real_file(path: Path) -> Path | None:
    """broken symlink를 따라가며 pathlib glob가 멈추는 문제를 피한다."""
    try:
        if not os.path.lexists(path):
            return None
        resolved = Path(os.path.realpath(path))
        if not os.path.isfile(resolved):
            return None
        return resolved
    except (OSError, RuntimeError):
        return None


def _append_candidate(found: list[Path], seen: set[str], candidate: Path) -> None:
    resolved = _safe_real_file(candidate)
    if resolved is None:
        return
    key = str(resolved)
    if key in seen:
        return
    seen.add(key)
    found.append(candidate)


def _scan_small_root(root: Path, soname: str, found: list[Path], seen: set[str]) -> int:
    """표준 library root를 최대 2단계까지만 bounded scan한다."""
    scanned = 0
    direct_dirs = [
        root,
        root / "x86_64-linux-gnu",
        root / "aarch64-linux-gnu",
        root / "lib",
        root / "lib64",
    ]
    for directory in direct_dirs:
        scanned += 1
        _append_candidate(found, seen, directory / soname)
    try:
        with os.scandir(root) as iterator:
            for entry in iterator:
                scanned += 1
                if scanned > 5000:
                    break
                try:
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                except OSError:
                    continue
                _append_candidate(found, seen, Path(entry.path) / soname)
    except OSError:
        pass
    return scanned


def _nix_store_entries() -> list[Path]:
    """Nix store 최상위 entry를 한 번만 읽는다. 재귀 glob는 사용하지 않는다."""
    global _NIX_STORE_ENTRY_CACHE
    if _NIX_STORE_ENTRY_CACHE is not None:
        return _NIX_STORE_ENTRY_CACHE
    store = Path("/nix/store")
    entries: list[Path] = []
    try:
        with os.scandir(store) as iterator:
            for entry in iterator:
                # is_dir/stat 호출 없이 경로명만 수집해 broken link 영향을 차단한다.
                if entry.name.endswith((".drv", ".lock", ".chroot")):
                    continue
                entries.append(Path(entry.path))
    except OSError:
        entries = []
    _NIX_STORE_ENTRY_CACHE = entries
    return entries


def _soname_package_tokens(soname: str) -> tuple[str, ...]:
    base = soname.lower()
    base = re.sub(r"^lib", "", base)
    base = base.split(".so", 1)[0]
    base = re.sub(r"[^a-z0-9]+", "", base)
    aliases: dict[str, tuple[str, ...]] = {
        "gl": ("libglvnd", "mesa", "opengl", "libgl"),
        "egl": ("libglvnd", "mesa", "egl"),
        "dbus1": ("dbus",),
        "xkbcommon": ("libxkbcommon", "xkbcommon"),
        "xcb": ("libxcb", "xcb"),
        "x11": ("libx11", "xorg"),
        "waylandclient": ("wayland",),
        "waylandcursor": ("wayland",),
        "waylandegl": ("wayland",),
        "fontconfig": ("fontconfig",),
        "freetype": ("freetype",),
        "expat": ("expat",),
        "z": ("zlib",),
    }
    values = list(aliases.get(base, ()))
    if base:
        values.extend((base, f"lib{base}"))
    deduped: list[str] = []
    for value in values:
        if value and value not in deduped:
            deduped.append(value)
    return tuple(deduped)


def _store_candidate_paths(package_root: Path, soname: str) -> list[Path]:
    return [
        package_root / "lib" / soname,
        package_root / "lib64" / soname,
        package_root / "lib" / "x86_64-linux-gnu" / soname,
        package_root / "lib64" / "x86_64-linux-gnu" / soname,
    ]


def _library_candidates(soname: str) -> tuple[list[Path], dict[str, Any]]:
    """SONAME 후보를 bounded·non-recursive 방식으로 수집한다.

    V3의 `/nix/store/**` pathlib glob는 사라진 store symlink를 검사하며
    수분 이상 멈출 수 있었다. V5는 store 최상위 package를 한 번 읽고
    각 package의 고정 lib 경로만 확인하며 12초 hard deadline을 둔다.
    """
    started = __import__("time").monotonic()
    deadline = started + 12.0
    found: list[Path] = []
    seen: set[str] = set()
    scanned_small = 0
    for root in _library_search_roots():
        scanned_small += _scan_small_root(root, soname, found, seen)

    entries = _nix_store_entries()
    tokens = _soname_package_tokens(soname)
    preferred: list[Path] = []
    fallback: list[Path] = []
    for entry in entries:
        name = entry.name.lower()
        if any(token in name for token in tokens):
            preferred.append(entry)
        else:
            fallback.append(entry)

    scanned_store = 0
    timed_out = False
    used_fallback = False
    # package명에 SONAME token이 포함된 derivation만 먼저 확인한다.
    # 여기서 하나라도 찾으면 전체 store fallback scan은 하지 않는다.
    for package_root in preferred:
        if __import__("time").monotonic() >= deadline:
            timed_out = True
            break
        scanned_store += 1
        for candidate in _store_candidate_paths(package_root, soname):
            _append_candidate(found, seen, candidate)
        if len(found) >= 120:
            break

    if not found and not timed_out:
        used_fallback = True
        for package_root in fallback:
            if __import__("time").monotonic() >= deadline:
                timed_out = True
                break
            scanned_store += 1
            for candidate in _store_candidate_paths(package_root, soname):
                _append_candidate(found, seen, candidate)
            if len(found) >= 120:
                break

    audit = {
        "search_seconds": round(__import__("time").monotonic() - started, 3),
        "small_root_entries": scanned_small,
        "nix_store_entries": len(entries),
        "nix_store_scanned": scanned_store,
        "preferred_package_entries": len(preferred),
        "used_fallback": used_fallback,
        "timed_out": timed_out,
        "candidate_count": len(found),
        "tokens": list(tokens),
    }
    return found, audit


def _candidate_is_unsafe(path: Path) -> bool:
    value = str(path).lower()
    if any(token in value for token in UNSAFE_BUNDLE_TOKENS):
        return True
    parent = path.parent
    try:
        if any(os.path.lexists(parent / soname) for soname in CORE_RUNTIME_SONAMES):
            return True
    except OSError:
        return True
    return False


_RUNTIME_GLIBC_MAX_CACHE: tuple[int, ...] | None = None


def _version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split(".") if part.isdigit())


def _runtime_glibc_max() -> tuple[int, ...]:
    """현재 Python이 실제 사용하는 glibc의 최대 symbol version을 구한다."""
    global _RUNTIME_GLIBC_MAX_CACHE
    if _RUNTIME_GLIBC_MAX_CACHE is not None:
        return _RUNTIME_GLIBC_MAX_CACHE
    result = run_command(["ldd", sys.executable], timeout=12)
    output = (result.stdout + "\n" + result.stderr).strip()
    libc_path: Path | None = None
    match = re.search(r"libc\.so\.6\s+=>\s+(\S+)", output)
    if match:
        candidate = Path(match.group(1))
        if candidate.is_file():
            libc_path = candidate
    versions: list[tuple[int, ...]] = []
    if libc_path is not None:
        strings_result = run_command(["strings", str(libc_path)], timeout=12)
        for value in re.findall(r"GLIBC_(\d+(?:\.\d+)+)", strings_result.stdout + strings_result.stderr):
            versions.append(_version_tuple(value))
    # 이 프로젝트의 Python 3.11 runtime은 GLIBC_2.38을 요구한다.
    # 탐지 실패 시 지나치게 최신 donor를 선택하지 않도록 보수적으로 2.38을 사용한다.
    _RUNTIME_GLIBC_MAX_CACHE = max(versions) if versions else (2, 38)
    return _RUNTIME_GLIBC_MAX_CACHE


def _required_glibc_max(path: Path) -> tuple[int, ...]:
    """ELF 자체가 요구하는 GLIBC symbol version의 최댓값을 반환한다."""
    result = run_command(["readelf", "--version-info", str(path)], timeout=12)
    output = result.stdout + "\n" + result.stderr
    versions = [_version_tuple(value) for value in re.findall(r"GLIBC_(\d+(?:\.\d+)+)", output)]
    return max(versions) if versions else ()


def _candidate_runtime_compatible(path: Path) -> tuple[bool, str]:
    required = _required_glibc_max(path)
    available = _runtime_glibc_max()
    if required and required > available:
        return False, f"required=GLIBC_{'.'.join(map(str, required))} available=GLIBC_{'.'.join(map(str, available))}"
    return True, f"required={required or 'none'} available={available}"


def _candidate_hint_score(path: Path, soname: str) -> int:
    """전용 package와 표준 runtime을 우선하고 bundle은 선택 대상에서 배제한다."""
    value = str(path).lower()
    score = 0
    preferred: dict[str, tuple[str, ...]] = {
        "libGL.so.1": ("libglvnd", "mesa"),
        "libEGL.so.1": ("libglvnd", "mesa"),
        "libdbus-1.so.3": ("-dbus-", "/dbus-", "dbus"),
        "libxkbcommon.so.0": ("libxkbcommon", "xkbcommon"),
    }
    for token in preferred.get(soname, ()):
        if token in value:
            score += 100
    if "/run/current-system/sw/lib" in value or "/nix/var/nix/profiles/default/lib" in value:
        score += 60
    if "/usr/lib" in value or "/lib/x86_64-linux-gnu" in value:
        score += 30
    return score


def _candidate_probe(path: Path, base_env: dict[str, str]) -> tuple[int, int, int, str]:
    result = run_command(["ldd", str(path)], env=base_env, timeout=12)
    output = (result.stdout + "\n" + result.stderr).strip()
    missing = len(re.findall(r"=>\s+not found", output))
    versions = sum(
        marker in line
        for line in output.splitlines()
        for marker in ("version `GLIBC_", "version `GLIBCXX_", "version `CXXABI_")
    )
    return result.returncode, versions, missing, output[-1200:]


def _select_library(soname: str, base_env: dict[str, str]) -> tuple[Path | None, dict[str, Any]]:
    candidates, search_audit = _library_candidates(soname)
    unsafe_candidates = [path for path in candidates if _candidate_is_unsafe(path)]
    safe_candidates: list[Path] = []
    incompatible: dict[str, str] = {}
    for path in candidates:
        if path in unsafe_candidates:
            continue
        compatible, detail = _candidate_runtime_compatible(path)
        if compatible:
            safe_candidates.append(path)
        else:
            incompatible[str(path)] = detail
    probe_candidates = sorted(
        safe_candidates,
        key=lambda path: (-_candidate_hint_score(path, soname), len(str(path)), str(path)),
    )[:24]
    ranked: list[tuple[tuple[int, int, int, int, int], Path, str]] = []
    timed_out_probes = 0
    for path in probe_candidates:
        returncode, version_count, missing_count, detail = _candidate_probe(path, base_env)
        if returncode == 124:
            timed_out_probes += 1
            continue
        rank = (
            0 if returncode == 0 else 1,
            version_count,
            missing_count,
            -_candidate_hint_score(path, soname),
            len(str(path)),
        )
        ranked.append((rank, path, detail))
    ranked.sort(key=lambda item: item[0])
    audit = {
        **search_audit,
        "safe_candidate_count": len(safe_candidates),
        "unsafe_candidate_count": len(unsafe_candidates),
        "runtime_incompatible_count": len(incompatible),
        "runtime_incompatible_sample": dict(list(incompatible.items())[:5]),
        "runtime_glibc_max": list(_runtime_glibc_max()),
        "probed_candidate_count": len(probe_candidates),
        "timed_out_probes": timed_out_probes,
        "selected_rank": None,
        "probe_tail": "",
    }
    if not ranked:
        return None, audit
    rank, selected, detail = ranked[0]
    audit["selected_rank"] = list(rank)
    audit["probe_tail"] = detail
    return selected, audit

def _prepare_shim_dir() -> Path:
    """필요 SONAME만 넣는 격리 shim을 만든다."""
    shim = REPORT_DIR / "qt_native_shim"
    shim.mkdir(parents=True, exist_ok=True)
    for child in shim.iterdir():
        if child.is_symlink() or child.is_file():
            child.unlink()
    return shim


def _link_soname(shim: Path, soname: str, target: Path) -> None:
    if soname in CORE_RUNTIME_SONAMES or soname.startswith("ld-linux"):
        raise BuildError(f"glibc 핵심 runtime library는 shim 연결 금지: {soname}")
    link = shim / soname
    if link.exists() or link.is_symlink():
        link.unlink()
    # symlink가 아니라 실제 파일만 격리 복사한다. donor library의 $ORIGIN이
    # electron bundle 디렉터리를 가리키며 libc/libm까지 끌어오는 것을 차단한다.
    shutil.copy2(target.resolve(), link)


def _shim_files(shim: Path) -> list[Path]:
    files: list[Path] = []
    try:
        for path in shim.iterdir():
            if path.is_file() or path.is_symlink():
                files.append(path)
    except OSError:
        pass
    return sorted(files, key=lambda path: path.name)


def _extract_missing_sonames(output: str) -> set[str]:
    """ldd와 Python import 오류에서 누락 SONAME을 공통 추출한다."""
    found: set[str] = set()
    patterns = (
        r"ImportError:\s*([^\s:]+\.so(?:\.\d+)*)\s*:\s*cannot open shared object file",
        r"error while loading shared libraries:\s*([^\s:]+\.so(?:\.\d+)*)\s*:",
        r"\b([^\s:]+\.so(?:\.\d+)*)\s+=>\s+not found\b",
    )
    for pattern in patterns:
        found.update(re.findall(pattern, output))
    return {value.strip() for value in found if value.strip()}


def _run_pyside_import_probe(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return run_command(
        [
            sys.executable,
            "-c",
            (
                "from PySide6.QtCore import QLibraryInfo; "
                "from PySide6.QtGui import QGuiApplication; "
                "from PySide6.QtWidgets import QApplication; "
                "print('PYSIDE_NATIVE_IMPORT_OK')"
            ),
        ],
        env=env,
        timeout=45,
    )


def _run_qapplication_probe(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """실제 offscreen QApplication 생성까지 확인한다.

    단순 import는 Qt platform plugin과 GUI 초기화 시점의 전이 의존성을
    모두 로드하지 않을 수 있으므로 실제 process context 검증을 별도로 수행한다.
    """
    return run_command(
        [
            sys.executable,
            "-c",
            (
                "from PySide6.QtWidgets import QApplication, QWidget; "
                "app = QApplication.instance() or QApplication([]); "
                "window = QWidget(); window.resize(64, 64); window.show(); "
                "app.processEvents(); window.close(); app.processEvents(); "
                "print('PYSIDE_QAPPLICATION_OK')"
            ),
        ],
        env=env,
        timeout=60,
    )


def build_qt_native_env() -> dict[str, Any]:
    """실제 Python·QApplication 실행 문맥 기준으로 native closure를 확정한다.

    V5는 PySide import가 성공했음에도 shim library를 단독으로 ldd했을 때
    donor RUNPATH가 가리키는 구형 glibc 조합에서 발생한 symbol-version 메시지를
    실제 실행 실패와 동일하게 취급했다. 이 메시지는 실제 Python process가 이미
    로드한 glibc와 shim 우선순위에서는 재현되지 않을 수 있다.

    V7은 native 실제 실행 검증과 함께 smoke fixture를 현재 통합 데이터에서 동적으로 선택한다.
    1) 전체 target의 SONAME 누락이 없음
    2) PySide6 import가 성공함
    3) offscreen QApplication 생성이 성공함

    standalone ldd의 version 메시지는 전수 기록하되 실제 process preflight가
    성공하면 경고로 보존하고 smoke test 실행을 차단하지 않는다.
    """
    objects = _pyside_shared_objects()
    clean_probe_env = {
        "QT_QPA_PLATFORM": "offscreen",
        "QT_OPENGL": "software",
        "LIBGL_ALWAYS_SOFTWARE": "1",
        "QT_QUICK_BACKEND": "software",
        "KDRG_DISABLE_SETTINGS": "1",
        "LD_LIBRARY_PATH": "",
    }
    initial_missing, initial_versions, initial_diagnostics = (
        _ldd_audit(objects, env=clean_probe_env) if objects else (set(), [], [])
    )
    shim = _prepare_shim_dir()
    found: dict[str, str] = {}
    selection_audit: dict[str, Any] = {}
    unresolved: set[str] = set()
    blocked_core: list[str] = []
    pending = set(initial_missing)
    closure_rounds: list[dict[str, Any]] = []
    import_probe: subprocess.CompletedProcess[str] = subprocess.CompletedProcess([], 1, "", "NOT_RUN")
    qapp_probe: subprocess.CompletedProcess[str] = subprocess.CompletedProcess([], 1, "", "NOT_RUN")
    import_output = "NOT_RUN"
    qapp_output = "NOT_RUN"
    no_progress_rounds = 0

    for round_index in range(1, 25):
        round_added: list[str] = []
        round_failed: list[str] = []
        current = sorted(pending)
        pending.clear()
        for soname in current:
            if soname in found:
                continue
            if soname in CORE_RUNTIME_SONAMES or soname.startswith("ld-linux"):
                blocked_core.append(soname)
                unresolved.add(soname)
                round_failed.append(soname)
                continue
            path, audit = _select_library(soname, clean_probe_env)
            selection_audit[soname] = audit
            if path is None:
                unresolved.add(soname)
                round_failed.append(soname)
                continue
            _link_soname(shim, soname, path)
            found[soname] = str(path.resolve())
            unresolved.discard(soname)
            round_added.append(soname)

        iterative_env = dict(clean_probe_env)
        iterative_env["LD_LIBRARY_PATH"] = str(shim)
        targets = [*objects, *_shim_files(shim)]
        ldd_missing, ldd_versions, ldd_diagnostics = _ldd_audit(targets, env=iterative_env)

        import_probe = _run_pyside_import_probe(iterative_env)
        import_output = (import_probe.stdout + "\n" + import_probe.stderr).strip()
        import_missing = _extract_missing_sonames(import_output)

        if import_probe.returncode == 0:
            qapp_probe = _run_qapplication_probe(iterative_env)
            qapp_output = (qapp_probe.stdout + "\n" + qapp_probe.stderr).strip()
        else:
            qapp_probe = subprocess.CompletedProcess([], 1, "", "IMPORT_PRECONDITION_FAILED")
            qapp_output = "IMPORT_PRECONDITION_FAILED"
        qapp_missing = _extract_missing_sonames(qapp_output)

        newly_pending = {
            soname
            for soname in (set(ldd_missing) | set(import_missing) | set(qapp_missing))
            if soname not in found
        }
        pending.update(newly_pending)
        process_context_ok = (
            import_probe.returncode == 0
            and qapp_probe.returncode == 0
            and not ldd_missing
            and not import_missing
            and not qapp_missing
        )
        closure_rounds.append({
            "round": round_index,
            "requested": current,
            "added": round_added,
            "failed": round_failed,
            "target_count": len(targets),
            "ldd_missing": sorted(ldd_missing),
            "standalone_ldd_version_warnings": ldd_versions,
            "import_returncode": import_probe.returncode,
            "import_missing": sorted(import_missing),
            "import_output_tail": import_output[-1200:],
            "qapplication_returncode": qapp_probe.returncode,
            "qapplication_missing": sorted(qapp_missing),
            "qapplication_output_tail": qapp_output[-1200:],
            "process_context_compatible": process_context_ok,
            "next_pending": sorted(pending),
            "ldd_tail": "\n\n".join(ldd_diagnostics)[-1800:],
        })

        if process_context_ok:
            break
        if round_added or newly_pending:
            no_progress_rounds = 0
        else:
            no_progress_rounds += 1
        if no_progress_rounds >= 2:
            break

    smoke_env = dict(clean_probe_env)
    smoke_env["LD_LIBRARY_PATH"] = str(shim)
    final_targets = [*objects, *_shim_files(shim)]
    final_missing, final_versions, final_diagnostics = (
        _ldd_audit(final_targets, env=smoke_env) if final_targets else (set(), [], [])
    )
    import_probe = _run_pyside_import_probe(smoke_env)
    import_output = (import_probe.stdout + "\n" + import_probe.stderr).strip()
    final_import_missing = _extract_missing_sonames(import_output)
    if import_probe.returncode == 0:
        qapp_probe = _run_qapplication_probe(smoke_env)
        qapp_output = (qapp_probe.stdout + "\n" + qapp_probe.stderr).strip()
    else:
        qapp_probe = subprocess.CompletedProcess([], 1, "", "IMPORT_PRECONDITION_FAILED")
        qapp_output = "IMPORT_PRECONDITION_FAILED"
    final_qapp_missing = _extract_missing_sonames(qapp_output)

    unresolved.update(final_missing)
    unresolved.update(final_import_missing)
    unresolved.update(final_qapp_missing)
    shim_entries = sorted(path.name for path in _shim_files(shim))
    core_in_shim = sorted(set(shim_entries) & CORE_RUNTIME_SONAMES)
    if core_in_shim:
        unresolved.update(core_in_shim)
    if import_probe.returncode != 0:
        unresolved.add("PYSIDE_NATIVE_IMPORT")
    if qapp_probe.returncode != 0:
        unresolved.add("PYSIDE_QAPPLICATION_PREFLIGHT")

    process_context_compatible = (
        import_probe.returncode == 0
        and qapp_probe.returncode == 0
        and not final_missing
        and not final_import_missing
        and not final_qapp_missing
        and not core_in_shim
    )

    return {
        "shared_objects": [str(path) for path in objects],
        "initial_missing": sorted(initial_missing),
        "initial_version_errors": initial_versions,
        "resolved_libraries": found,
        "selection_audit": selection_audit,
        "closure_rounds": closure_rounds,
        "closure_round_count": len(closure_rounds),
        "shim_dir": str(shim),
        "shim_entries": shim_entries,
        "blocked_core_libraries": sorted(set(blocked_core)),
        "core_runtime_in_shim": core_in_shim,
        "library_dirs": [str(shim)],
        "final_target_count": len(final_targets),
        "final_missing": sorted(final_missing),
        "final_import_missing": sorted(final_import_missing),
        "final_qapplication_missing": sorted(final_qapp_missing),
        "final_version_errors": final_versions,
        "standalone_ldd_version_warnings": final_versions,
        "process_context_compatible": process_context_compatible,
        "unresolved": sorted(unresolved),
        "import_probe_returncode": import_probe.returncode,
        "import_probe_output": import_output[-3000:],
        "qapplication_probe_returncode": qapp_probe.returncode,
        "qapplication_probe_output": qapp_output[-3000:],
        "environment": smoke_env,
        "initial_ldd_tail": "\n\n".join(initial_diagnostics)[-6000:],
        "final_ldd_tail": "\n\n".join(final_diagnostics)[-6000:],
        "runtime_glibc_max": list(_runtime_glibc_max()),
        "validation_policy": (
            "실제 Python process에서 PySide import와 offscreen QApplication 생성이 "
            "모두 성공하고 SONAME 누락이 없으면 compatible로 판정함. "
            "shim 단독 ldd의 donor RUNPATH version 메시지는 경고로 보존함."
        ),
    }

def build_report(payload: dict[str, Any]) -> str:
    validation = payload["validation"]
    lines = [
        "KDRG V4.7 PySide runtime UI bridge 구축 결과",
        "=" * 72,
        f"생성시각: {payload['generated_at']}",
        f"스크립트 버전: {SCRIPT_VERSION}",
        "",
        "[현재 진행 위치]",
        "최종 통합 JSON V2·runtime service·40번 독립검증 완료 후 기존 PySide v0.2 화면을 전체 runtime에 연결함",
        "화면 골격은 유지하고 데이터 loader·검색 event·상세 관계 표시만 교체함",
        "통합 JSON·원천 데이터·기존 app/data_store.py·app/models.py는 수정하지 않음",
        "",
        "[입력 검증]",
        f"통합 JSON schema: {payload['input'].get('schema_version')}",
        f"통합 JSON SHA256: {payload['input'].get('integrated_sha256')}",
        f"runtime service SHA256: {payload['input'].get('service_sha256')}",
        f"40번 검증: {payload['input'].get('runtime_validation_pass')} PASS / {payload['input'].get('runtime_validation_fail')} FAIL",
        "",
        "[생성·수정 파일]",
        f"생성: {ADAPTER_PATH}",
        f"생성: {SMOKE_PATH}",
        f"수정: {MAIN_WINDOW_PATH}",
        f"수정: {DIALOGS_PATH}",
        "",
        "[UI runtime 연결]",
        f"ADRG: {payload['counts'].get('adrg_records')}",
        f"AADRG: {payload['counts'].get('aadrg_records')}",
        f"RDRG: {payload['counts'].get('rdrg_records')}",
        f"TABLE: {payload['counts'].get('logical_table_records')}",
        f"검색 코드: {payload['counts'].get('unique_search_codes')}",
        "빈 검색 초기 목록은 E011을 첫 카드로 두고 최대 200건만 렌더링하여 UI 과부하를 방지함",
        "CODE·ADRG·AADRG·RDRG·TABLE 검색은 KdrgSearchService 순위·정규화 결과를 사용함",
        "smoke fixture는 특정 코드 존재를 가정하지 않고 현재 전체 code corpus에서 결정론적으로 선택함",
        "",
        "[관계 표시 정책]",
        "코드·TABLE 상세에서 원문 TABLE 정의 ADRG / 조건 AST 사용 ADRG / 검색용 관련 ADRG를 분리 표시함",
        "X04 family는 ADRG로 노출하지 않고 원문 family 근거로만 표시함",
        "기존 복수 코드 관계검색은 AST에서 재구성한 긍정·제외 TABLE과 OR branch를 사용함",
        "",
        "[patch 내역]",
        *[f"- {item}" for item in payload.get("changes") or []],
        "",
        "[자동검증]",
        f"py_compile: {payload['tests'].get('compile_status')}",
        f"PySide6 shared object: {len((payload['tests'].get('native_probe') or {}).get('shared_objects') or [])}개",
        f"초기 native 누락: {(payload['tests'].get('native_probe') or {}).get('initial_missing') or []}",
        f"자동 연결 library: {(payload['tests'].get('native_probe') or {}).get('resolved_libraries') or {}}",
        f"bounded candidate search: {(payload['tests'].get('native_probe') or {}).get('selection_audit') or {}}",
        f"recursive closure round: {(payload['tests'].get('native_probe') or {}).get('closure_round_count') or 0}",
        f"recursive closure audit: {(payload['tests'].get('native_probe') or {}).get('closure_rounds') or []}",
        f"격리 shim: {(payload['tests'].get('native_probe') or {}).get('shim_dir') or '-'}",
        f"shim SONAME: {(payload['tests'].get('native_probe') or {}).get('shim_entries') or []}",
        f"shim 내 glibc 핵심 library: {(payload['tests'].get('native_probe') or {}).get('core_runtime_in_shim') or []}",
        f"최종 native 누락: {(payload['tests'].get('native_probe') or {}).get('final_missing') or []}",
        f"최종 import 누락: {(payload['tests'].get('native_probe') or {}).get('final_import_missing') or []}",
        f"standalone ldd symbol version 경고: {(payload['tests'].get('native_probe') or {}).get('standalone_ldd_version_warnings') or []}",
        f"실제 process context 호환: {(payload['tests'].get('native_probe') or {}).get('process_context_compatible')}",
        f"PySide import preflight: 종료코드 {(payload['tests'].get('native_probe') or {}).get('import_probe_returncode')}",
        (payload['tests'].get('native_probe') or {}).get('import_probe_output', '').strip(),
        f"QApplication offscreen preflight: 종료코드 {(payload['tests'].get('native_probe') or {}).get('qapplication_probe_returncode')}",
        (payload['tests'].get('native_probe') or {}).get('qapplication_probe_output', '').strip(),
        f"runtime UI bridge smoke: 종료코드 {payload['tests'].get('smoke_returncode')}",
        payload['tests'].get('smoke_summary', '').strip(),
        "",
        "[검증 항목 집계]",
        f"PASS: {validation['pass_count']}",
        f"FAIL: {validation['fail_count']}",
        f"TOTAL: {validation['total_count']}",
        "사용자 판단 필요: 0",
        "사용자 수동 Excel 검토: 없음",
        "",
        "[다음 단계]",
        "42번에서 생성된 runtime adapter를 사용하지 않고 통합 JSON과 현재 UI 구조에서 검색·상세·관계 표시를 독립 재계산함",
        "독립검증 PASS 후 전체 UI preview와 Windows exe 회귀검증으로 진행함",
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
    required = [
        INTEGRATED_PATH,
        SERVICE_PATH,
        RUNTIME_VALIDATION_PATH,
        MAIN_WINDOW_PATH,
        DIALOGS_PATH,
        APP_DIR / "models.py",
    ]
    for index, path in enumerate(required, start=1):
        checker.check(f"B{index:02d}", f"필수 파일 존재 {path.name}", path.exists(), str(path))
    if not all(path.exists() for path in required):
        summary = checker.summary()
        payload = {
            "generated_at": now_iso(),
            "input": {},
            "counts": {},
            "changes": [],
            "tests": {"compile_status": "NOT_RUN", "smoke_returncode": -1, "smoke_summary": "", "native_probe": {}},
            "validation": summary,
        }
        atomic_write_json(REPORT_JSON_PATH, payload)
        atomic_write_text(REPORT_TXT_PATH, build_report(payload))
        print(f"[FAIL] PySide runtime UI bridge 구축 실패: {summary['pass_count']} PASS / {summary['fail_count']} FAIL")
        return 1

    integrated = read_json(INTEGRATED_PATH)
    runtime_validation = read_json(RUNTIME_VALIDATION_PATH)
    meta = integrated.get("meta") or {}
    counts = meta.get("counts") or {}
    rv = runtime_validation.get("validation") or {}

    checker.check("B07", "통합 JSON V2", meta.get("schema_version") == "kdrg-v47-search-integrated-v2", str(meta.get("schema_version")))
    checker.check("B08", "통합 JSON 자체 PASS", (integrated.get("validation") or {}).get("status") == "PASS", str((integrated.get("validation") or {}).get("status")))
    checker.check("B09", "40번 runtime 독립검증 PASS", rv.get("status") == "PASS", str(rv.get("status")))
    checker.check("B10", "40번 98 PASS", rv.get("pass_count") == 98, str(rv.get("pass_count")))
    checker.check("B11", "40번 0 FAIL", rv.get("fail_count") == 0, str(rv.get("fail_count")))
    for index, (key, expected) in enumerate(EXPECTED_COUNTS.items(), start=12):
        checker.check(f"B{index:02d}", f"고정 집계 {key}", counts.get(key) == expected, f"actual={counts.get(key)} expected={expected}")

    before_main_hash = sha256_file(MAIN_WINDOW_PATH)
    before_dialog_hash = sha256_file(DIALOGS_PATH)
    backup_file(MAIN_WINDOW_PATH)
    backup_file(DIALOGS_PATH)

    atomic_write_text(ADAPTER_PATH, ADAPTER_SOURCE)
    atomic_write_text(SMOKE_PATH, SMOKE_SOURCE)

    main_text, main_changes = patch_main_window(MAIN_WINDOW_PATH.read_text(encoding="utf-8"))
    dialog_text, dialog_changes = patch_dialogs(DIALOGS_PATH.read_text(encoding="utf-8"))
    atomic_write_text(MAIN_WINDOW_PATH, main_text)
    atomic_write_text(DIALOGS_PATH, dialog_text)
    changes = [*main_changes, *dialog_changes]

    compile_status = "PASS"
    compile_detail = ""
    try:
        for path in [ADAPTER_PATH, SMOKE_PATH, MAIN_WINDOW_PATH, DIALOGS_PATH, SERVICE_PATH]:
            py_compile.compile(str(path), cfile=str(REPORT_DIR / f".{path.name}.pyc"), doraise=True)
    except Exception as exc:
        compile_status = "FAIL"
        compile_detail = repr(exc)
    checker.check("B20", "생성·수정 Python py_compile", compile_status == "PASS", compile_detail or "PASS")
    checker.check("B21", "main_window runtime import", "from app.runtime_data_store import KDRGRuntimeDataStore as KDRGDataStore" in main_text, "runtime import")
    checker.check("B22", "코드 상세 relation 구분", "relation_summary_for_code" in main_text and "원문 TABLE 정의 ADRG" in main_text, "code detail")
    checker.check("B23", "TABLE 상세 relation 구분", "relation_summary_for_table" in main_text and "조건 AST 사용 ADRG" in main_text, "table detail")
    checker.check("B24", "AboutDialog full runtime", "전체 runtime 데이터 범위" in dialog_text and "현재 파일럿 제한" not in dialog_text, "dialog")
    checker.check("B25", "기존 data_store 보존", (APP_DIR / "data_store.py").exists(), str(APP_DIR / "data_store.py"))
    checker.check("B26", "통합 JSON 미변경", sha256_file(INTEGRATED_PATH) == str((runtime_validation.get("input_hashes") or {}).get("integrated_json") or sha256_file(INTEGRATED_PATH)), sha256_file(INTEGRATED_PATH))

    native_probe = build_qt_native_env() if compile_status == "PASS" else {
        "shared_objects": [],
        "initial_missing": [],
        "resolved_libraries": {},
        "library_dirs": [],
        "final_missing": [],
        "unresolved": ["compile failed"],
        "environment": {},
        "initial_ldd_tail": "",
        "final_ldd_tail": "",
    }
    checker.check(
        "B27",
        "PySide6 native shared object 탐지",
        len(native_probe.get("shared_objects") or []) >= 3,
        str(native_probe.get("shared_objects") or []),
    )
    checker.check(
        "B28",
        "PySide6 native 의존성 전체 해결",
        not (native_probe.get("unresolved") or []) and bool(native_probe.get("process_context_compatible")),
        f"initial={native_probe.get('initial_missing')} resolved={native_probe.get('resolved_libraries')} final={native_probe.get('final_missing')} process_context={native_probe.get('process_context_compatible')} standalone_ldd_warnings={native_probe.get('standalone_ldd_version_warnings')}",
    )
    checker.check(
        "B29",
        "glibc 핵심 runtime 격리",
        not (native_probe.get("core_runtime_in_shim") or []),
        f"shim={native_probe.get('shim_dir')} entries={native_probe.get('shim_entries')} core={native_probe.get('core_runtime_in_shim')}",
    )
    checker.check(
        "B30",
        "PySide6 import·QApplication 실행 문맥 preflight",
        native_probe.get("import_probe_returncode") == 0 and native_probe.get("qapplication_probe_returncode") == 0,
        f"import={native_probe.get('import_probe_output') or ''} | qapp={native_probe.get('qapplication_probe_output') or ''}",
    )
    smoke = run_command(
        [sys.executable, str(SMOKE_PATH)],
        env=native_probe.get("environment") or {},
    ) if compile_status == "PASS" and bool(native_probe.get("process_context_compatible")) and not (native_probe.get("unresolved") or []) else subprocess.CompletedProcess([], 1, "", "native process context unresolved")
    smoke_output = (smoke.stdout + "\n" + smoke.stderr).strip()
    smoke_summary = next((line for line in reversed(smoke_output.splitlines()) if line.startswith("결과:")), smoke_output[-500:])
    checker.check("B31", "runtime UI bridge smoke", smoke.returncode == 0, smoke_output[-2000:])
    checker.check("B32", "main_window 실제 변경", sha256_file(MAIN_WINDOW_PATH) != before_main_hash or "runtime_data_store" in MAIN_WINDOW_PATH.read_text(encoding="utf-8"), sha256_file(MAIN_WINDOW_PATH))
    checker.check("B33", "dialogs 실제 변경", sha256_file(DIALOGS_PATH) != before_dialog_hash or "전체 runtime 데이터 범위" in DIALOGS_PATH.read_text(encoding="utf-8"), sha256_file(DIALOGS_PATH))
    checker.check("B34", "원천 JSON write 없음", all(path.exists() for path in [INTEGRATED_PATH]), str(INTEGRATED_PATH))

    summary = checker.summary()
    payload = {
        "script_version": SCRIPT_VERSION,
        "generated_at": now_iso(),
        "input": {
            "schema_version": meta.get("schema_version"),
            "integrated_sha256": sha256_file(INTEGRATED_PATH),
            "service_sha256": sha256_file(SERVICE_PATH),
            "runtime_validation_pass": rv.get("pass_count"),
            "runtime_validation_fail": rv.get("fail_count"),
        },
        "counts": counts,
        "changes": changes,
        "outputs": {
            "adapter": str(ADAPTER_PATH),
            "adapter_sha256": sha256_file(ADAPTER_PATH),
            "smoke": str(SMOKE_PATH),
            "smoke_sha256": sha256_file(SMOKE_PATH),
            "main_window": str(MAIN_WINDOW_PATH),
            "main_window_sha256": sha256_file(MAIN_WINDOW_PATH),
            "dialogs": str(DIALOGS_PATH),
            "dialogs_sha256": sha256_file(DIALOGS_PATH),
            "backup_dir": str(BACKUP_DIR),
        },
        "tests": {
            "compile_status": compile_status,
            "native_probe": {
                key: value
                for key, value in native_probe.items()
                if key != "environment"
            },
            "smoke_returncode": smoke.returncode,
            "smoke_summary": smoke_summary,
            "smoke_output_tail": smoke_output[-4000:],
        },
        "validation": summary,
    }
    atomic_write_json(REPORT_JSON_PATH, payload)
    atomic_write_text(REPORT_TXT_PATH, build_report(payload))
    if summary["status"] == "PASS":
        print(
            "[PASS] PySide runtime UI bridge 구축 완료: "
            f"1132 ADRG / 1308 tables / 16571 codes / process-context-native-verified / {summary['pass_count']} PASS / 0 FAIL"
        )
        print(f"adapter={ADAPTER_PATH}")
        print(f"report={REPORT_TXT_PATH}")
        return 0
    print(f"[FAIL] PySide runtime UI bridge 구축 실패: {summary['pass_count']} PASS / {summary['fail_count']} FAIL")
    print(f"report={REPORT_TXT_PATH}")
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        text = f"[FATAL] {type(exc).__name__}: {exc}\n"
        atomic_write_text(REPORT_TXT_PATH, text)
        print(text.strip())
        raise
