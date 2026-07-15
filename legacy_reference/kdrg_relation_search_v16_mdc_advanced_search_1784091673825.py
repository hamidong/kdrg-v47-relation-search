# -*- coding: utf-8 -*-
"""
KDRG 코드 관계 검색기 - MDC 검색·복수 코드 관계검색 v16

목적
- KDRG 분류집의 ADRG 조건, AADRG, 질병군 A/B/C, table, table 내부 코드를
  코드 중심으로 조회하는 PySide6 프로토타입입니다.
- 현재 버전은 MDC 04 호흡기계와 MDC 05 순환기계 전체 외부 JSON 데이터를 읽고, MDC 검색과 복수 코드 관계검색을 지원합니다.
- ADRG 검색 결과와 상세 화면에서 A/B/C 질병군을 서로 다른 색상으로 표시합니다.
- 부제목이 비어 있으면 빈 괄호를 표시하지 않습니다.
- F194처럼 시술 횟수 또는 부가코드 조건이 있는 경우 조건표에 요구사항을 표시합니다.
- F136처럼 OR 조건이 있는 ADRG는 조건식 1 / 조건식 2 구조로 풀어 표시합니다.
- ADRG 상세로 이동한 뒤 이전 코드/TABLE 상세 화면으로 돌아가는 탐색 이력을 지원합니다.
- 복수 코드 관계검색은 공식 조건구조 안의 연결 관계만 보여주며 최종 조건충족/DRG 판정은 하지 않습니다.
- 추천, EMR 연동, 가상 재분류 기능은 포함하지 않습니다.

실행
    pip install PySide6
    python kdrg_relation_search_v16_mdc_advanced_search.py
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QFormLayout,
    QWidget,
)


# =============================================================================
# 1. 데이터 모델
# =============================================================================


@dataclass(frozen=True)
class CodeMember:
    code: str
    name_en: str
    name_ko: str
    original_order: int

    @property
    def display_name(self) -> str:
        if self.name_en and self.name_ko:
            return f"{self.name_en} / {self.name_ko}"
        return self.name_ko or self.name_en


@dataclass(frozen=True)
class TableDef:
    table_id: str
    display_label: str
    code_type: str
    source_page: str
    members: Tuple[CodeMember, ...]

    @property
    def count(self) -> int:
        return len(self.members)

    def contains_code(self, code: str) -> bool:
        q = normalize(code)
        return any(normalize(m.code) == q for m in self.members)

    def member_by_code(self, code: str) -> Optional[CodeMember]:
        q = normalize(code)
        for member in self.members:
            if normalize(member.code) == q:
                return member
        return None


@dataclass(frozen=True)
class AADRGMapping:
    aadrg: str
    group_code: str
    group_name: str
    aadrg_name: str = ""

    @property
    def group_display(self) -> str:
        return f"{self.group_code}군 · {self.group_name}"


@dataclass(frozen=True)
class RuleComponent:
    table_id: str
    operator_before: str = ""
    operator_after: str = ""
    requirement_label: str = ""


@dataclass(frozen=True)
class ConditionGroup:
    group_no: int
    group_label: str
    join_to_next_group: str
    components: Tuple[RuleComponent, ...]
    requirements: Tuple[str, ...] = ()


@dataclass(frozen=True)
class RuleDef:
    adrg: str
    aadrg: str
    mdc: str
    group_code: str
    group_name: str
    title: str
    subtitle: str
    condition_text: str
    source_page: str
    condition_summary: str
    condition_groups: Tuple[ConditionGroup, ...]
    aadrg_mappings: Tuple[AADRGMapping, ...]

    @property
    def components(self) -> Tuple[RuleComponent, ...]:
        """검색/링크 검증용 평탄화 components. UI는 condition_groups를 우선 사용한다."""
        flattened: List[RuleComponent] = []
        for group in self.condition_groups:
            flattened.extend(group.components)
        return tuple(flattened)

    @property
    def group_display(self) -> str:
        return f"{self.group_code}군 · {self.group_name}"

    @property
    def aadrg_display(self) -> str:
        return " / ".join(m.aadrg for m in self.aadrg_mappings) or self.aadrg

    @property
    def aadrg_detail_display(self) -> str:
        return "\n".join(f"{m.aadrg} · {m.group_display} · {m.aadrg_name}" for m in self.aadrg_mappings)

    @property
    def title_full(self) -> str:
        return f"{self.title}({self.subtitle})" if self.subtitle else self.title


@dataclass(frozen=True)
class SearchResult:
    kind: str
    key: str
    label: str
    sublabel: str
    priority: int
    group_code: str = ""
    group_name: str = ""
    mdc: str = ""


@dataclass(frozen=True)
class MDCDef:
    mdc: str
    name: str
    aliases: Tuple[str, ...]

    @property
    def display(self) -> str:
        return f"MDC {self.mdc} · {self.name}"


@dataclass(frozen=True)
class AdvancedCondition:
    code_type: str
    code: str


@dataclass(frozen=True)
class RelationCodeMatch:
    code: str
    selected_type: str
    table_ids: Tuple[str, ...]


@dataclass(frozen=True)
class RelationGroupMatch:
    group_no: int
    group_label: str
    matches: Tuple[RelationCodeMatch, ...]
    all_inputs_in_group: bool


@dataclass(frozen=True)
class RelationCandidate:
    adrg: str
    relation_level: str
    matched_count: int
    total_count: int
    rule_matches: Tuple[RelationCodeMatch, ...]
    group_matches: Tuple[RelationGroupMatch, ...]

    @property
    def status_label(self) -> str:
        return {
            "strict": "같은 조건식 내 공통 연결",
            "split": "서로 다른 OR 조건식에 분산",
            "partial": "입력코드 일부 연결",
        }.get(self.relation_level, "관계 확인")


# =============================================================================
# 2. 유틸리티
# =============================================================================


def normalize(value: object) -> str:
    return str(value or "").strip().upper().replace(" ", "")


def contains_text(haystack: str, needle: str) -> bool:
    if not needle:
        return True
    return normalize(needle) in normalize(haystack)


def result_kind_for_code_type(code_type: str) -> str:
    return {
        "상병코드": "diagnosis_code",
        "기타진단코드": "secondary_diagnosis_code",
        "수술·처치코드": "procedure_code",
        "검사·처치코드": "test_code",
        "부가코드": "supplement_code",
    }.get(code_type, "procedure_code")


def badge_name_for_code_type(code_type: str) -> str:
    return {
        "상병코드": "BadgeBlue",
        "기타진단코드": "BadgeBlue",
        "수술·처치코드": "BadgeGreen",
        "검사·처치코드": "BadgeTeal",
        "부가코드": "BadgeOrange",
    }.get(code_type, "BadgeGray")


def group_badge_name(group_code: str, size: str) -> str:
    code = normalize(group_code)
    if code not in {"A", "B", "C"}:
        code = "Other"
    prefix = {"result": "ResultGroupBadge", "mini": "MiniGroupBadge", "full": "GroupBadge"}[size]
    return f"{prefix}{code}"


def shorten_codes(codes: List[str], limit: int = 20) -> str:
    if len(codes) <= limit:
        return ", ".join(codes)
    visible = ", ".join(codes[:limit])
    return f"{visible}, ... 외 {len(codes) - limit}개"


def rich_code_summary(codes: List[str], highlight_code: str, limit: int = 20) -> str:
    """코드요약 표시용 HTML. 코드명은 넣지 않고 코드만 간략 표시한다."""
    visible_codes = codes[:limit]
    parts: List[str] = []
    hq = normalize(highlight_code)
    for code in visible_codes:
        safe_code = html.escape(code)
        if hq and normalize(code) == hq:
            parts.append(
                "<span style='font-weight:800; color:#0b5cad; "
                "background:#e7f1ff; padding:2px 5px; border-radius:6px;'>"
                f"{safe_code}</span>"
            )
        else:
            parts.append(safe_code)
    text = ", ".join(parts)
    if len(codes) > limit:
        text += f", ... 외 {len(codes) - limit}개"
    return text


def clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        child = item.widget()
        child_layout = item.layout()
        if child is not None:
            child.setParent(None)
            child.deleteLater()
        elif child_layout is not None:
            clear_layout(child_layout)


# =============================================================================
# 3. 샘플 데이터 저장소
# =============================================================================


class KDRGDataStore:
    """외부 JSON 기반 KDRG 관계 데이터 저장소."""

    DEFAULT_DATA_PATH = Path(__file__).resolve().parent / "data" / "kdrg_relation_data_v16_mdc_advanced_search.json"

    def __init__(self, data_path: Optional[object] = None) -> None:
        self.data_path = Path(data_path) if data_path else self.DEFAULT_DATA_PATH
        if not self.data_path.exists():
            raise FileNotFoundError(
                "KDRG 데이터 파일을 찾을 수 없습니다.\n"
                f"필요 파일: {self.data_path}\n\n"
                "ZIP 파일을 압축 해제한 뒤 data/kdrg_relation_data_v16_mdc_advanced_search.json 파일이 "
                "실행 py 파일과 같은 폴더 구조에 있는지 확인하세요."
            )

        raw = json.loads(self.data_path.read_text(encoding="utf-8"))
        self.meta: Dict[str, str] = raw.get("meta", {})
        self.version = self.meta.get("kdrg_version", "KDRG")
        self.data_scope = self.meta.get("data_scope", "외부 데이터")
        self.ui_badge = self.meta.get("ui_badge", "MDC 04-05 v16 · RELATION SEARCH")
        self.notice = self.meta.get("notice", "외부 JSON 데이터 파일을 읽어 검색합니다.")
        self.source_note = self.meta.get("source_note", "정식 데이터 구축 시 KDRG 원문에서 재추출·검증 필요")

        self.tables: Dict[str, TableDef] = self._load_tables(raw.get("tables", []))
        self.rules: Dict[str, RuleDef] = self._load_rules(raw.get("rules", []))
        self.mdcs: Dict[str, MDCDef] = self._load_mdcs(raw.get("mdc_master", []))
        self._validate_links()
        self.code_to_tables: Dict[str, List[str]] = self._build_code_to_tables()
        self.table_to_rules: Dict[str, List[str]] = self._build_table_to_rules()

    def _load_tables(self, raw_tables: List[dict]) -> Dict[str, TableDef]:
        tables: Dict[str, TableDef] = {}
        for table_raw in raw_tables:
            members: List[CodeMember] = []
            for idx, member_raw in enumerate(table_raw.get("members", []), start=1):
                members.append(
                    CodeMember(
                        code=str(member_raw.get("code", "")).strip(),
                        name_en=str(member_raw.get("name_en", "")).strip(),
                        name_ko=str(member_raw.get("name_ko", "")).strip(),
                        original_order=int(member_raw.get("original_order") or idx),
                    )
                )
            table = TableDef(
                table_id=str(table_raw.get("table_id", "")).strip(),
                display_label=str(table_raw.get("display_label", "")).strip(),
                code_type=str(table_raw.get("code_type", "")).strip(),
                source_page=str(table_raw.get("source_page", "")).strip(),
                members=tuple(sorted(members, key=lambda m: m.original_order)),
            )
            if not table.table_id:
                raise ValueError("table_id가 비어 있는 TABLE 데이터가 있습니다.")
            if table.table_id in tables:
                raise ValueError(f"중복 table_id가 있습니다: {table.table_id}")
            tables[table.table_id] = table
        return tables

    def _load_rules(self, raw_rules: List[dict]) -> Dict[str, RuleDef]:
        rules: Dict[str, RuleDef] = {}

        def build_components(raw_components: List[dict]) -> Tuple[RuleComponent, ...]:
            components: List[RuleComponent] = []
            for comp_raw in raw_components:
                components.append(
                    RuleComponent(
                        table_id=str(comp_raw.get("table_id", "")).strip(),
                        operator_before=str(comp_raw.get("operator_before", "")).strip(),
                        operator_after=str(comp_raw.get("operator_after", "")).strip(),
                        requirement_label=str(comp_raw.get("requirement_label", "")).strip(),
                    )
                )
            return tuple(components)

        for rule_raw in raw_rules:
            condition_groups: List[ConditionGroup] = []
            raw_groups = rule_raw.get("condition_groups") or []

            if raw_groups:
                for group_index, group_raw in enumerate(raw_groups, start=1):
                    group_no = int(group_raw.get("group_no") or group_index)
                    group_label = str(group_raw.get("group_label") or f"조건식 {group_no}").strip()
                    join_to_next_group = str(group_raw.get("join_to_next_group") or "").strip().upper()
                    condition_groups.append(
                        ConditionGroup(
                            group_no=group_no,
                            group_label=group_label,
                            join_to_next_group=join_to_next_group,
                            components=build_components(group_raw.get("components", [])),
                            requirements=tuple(str(x).strip() for x in group_raw.get("requirements", []) if str(x).strip()),
                        )
                    )
            else:
                # v6 이하 legacy JSON 호환: components를 단일 조건식으로 해석한다.
                condition_groups.append(
                    ConditionGroup(
                        group_no=1,
                        group_label="조건식 1",
                        join_to_next_group="",
                        components=build_components(rule_raw.get("components", [])),
                        requirements=(),
                    )
                )

            raw_mappings = rule_raw.get("aadrg_mappings") or [{
                "aadrg": rule_raw.get("aadrg", ""),
                "group_code": rule_raw.get("group_code", ""),
                "group_name": rule_raw.get("group_name", ""),
                "aadrg_name": rule_raw.get("title", ""),
            }]
            aadrg_mappings = tuple(
                AADRGMapping(
                    aadrg=str(item.get("aadrg", "")).strip(),
                    group_code=str(item.get("group_code", "")).strip(),
                    group_name=str(item.get("group_name", "")).strip(),
                    aadrg_name=str(item.get("aadrg_name", "")).strip(),
                )
                for item in raw_mappings
                if str(item.get("aadrg", "")).strip()
            )

            rule = RuleDef(
                adrg=str(rule_raw.get("adrg", "")).strip(),
                aadrg=str(rule_raw.get("aadrg", "")).strip(),
                mdc=str(rule_raw.get("mdc", "")).strip(),
                group_code=str(rule_raw.get("group_code", "")).strip(),
                group_name=str(rule_raw.get("group_name", "")).strip(),
                title=str(rule_raw.get("title", "")).strip(),
                subtitle=str(rule_raw.get("subtitle", "")).strip(),
                condition_text=str(rule_raw.get("condition_text", "")).strip(),
                source_page=str(rule_raw.get("source_page", "")).strip(),
                condition_summary=str(rule_raw.get("condition_summary", "")).strip(),
                condition_groups=tuple(condition_groups),
                aadrg_mappings=aadrg_mappings,
            )
            if not rule.adrg:
                raise ValueError("ADRG가 비어 있는 rule 데이터가 있습니다.")
            if rule.adrg in rules:
                raise ValueError(f"중복 ADRG가 있습니다: {rule.adrg}")
            rules[rule.adrg] = rule
        return rules

    def _load_mdcs(self, raw_mdcs: List[dict]) -> Dict[str, MDCDef]:
        defaults = {"04": "호흡기계", "05": "순환기계"}
        mdcs: Dict[str, MDCDef] = {}
        for raw_mdc in raw_mdcs:
            code = str(raw_mdc.get("mdc", "")).strip().zfill(2)
            if not code:
                continue
            name = str(raw_mdc.get("name", "")).strip() or defaults.get(code, "")
            aliases = tuple(str(x).strip() for x in raw_mdc.get("aliases", []) if str(x).strip())
            mdcs[code] = MDCDef(code, name, aliases)
        for code in sorted({rule.mdc for rule in self.rules.values()}):
            if code not in mdcs:
                name = defaults.get(code, f"MDC {code}")
                mdcs[code] = MDCDef(code, name, (f"MDC {code}", f"MDC{code}", name))
        return mdcs

    def rules_for_mdc(self, mdc: str) -> List[RuleDef]:
        code = str(mdc).strip().zfill(2)
        return [r for r in self.rules.values() if r.mdc == code]

    def exact_table_ids_for_code(self, code: str, selected_type: str = "자동판별") -> List[str]:
        table_ids = list(self.code_to_tables.get(normalize(code), []))
        if selected_type and selected_type != "자동판별":
            table_ids = [tid for tid in table_ids if self.tables[tid].code_type == selected_type]
        return table_ids

    def relation_search(self, conditions: List[AdvancedCondition], operator: str) -> List[RelationCandidate]:
        operator = normalize(operator) or "AND"
        total_count = len(conditions)
        candidates: List[RelationCandidate] = []

        condition_tables: List[Tuple[AdvancedCondition, Set[str]]] = []
        for condition in conditions:
            condition_tables.append((condition, set(self.exact_table_ids_for_code(condition.code, condition.code_type))))

        for rule in self.rules.values():
            rule_table_ids = {comp.table_id for comp in rule.components}
            rule_matches: List[RelationCodeMatch] = []
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

            group_matches: List[RelationGroupMatch] = []
            strict_group_exists = False
            for group in rule.condition_groups:
                group_table_ids = {comp.table_id for comp in group.components}
                matches: List[RelationCodeMatch] = []
                group_hit_count = 0
                for condition, global_ids in condition_tables:
                    ids = tuple(sorted(global_ids & group_table_ids))
                    if ids:
                        group_hit_count += 1
                    matches.append(RelationCodeMatch(condition.code, condition.code_type, ids))
                all_inputs = group_hit_count == total_count
                any_input = group_hit_count > 0
                if any_input:
                    group_matches.append(RelationGroupMatch(group.group_no, group.group_label, tuple(matches), all_inputs))
                if all_inputs:
                    strict_group_exists = True

            if matched_count == total_count and strict_group_exists:
                level = "strict"
            elif matched_count == total_count:
                level = "split"
            else:
                level = "partial"

            candidates.append(RelationCandidate(rule.adrg, level, matched_count, total_count, tuple(rule_matches), tuple(group_matches)))

        rank = {"strict": 0, "split": 1, "partial": 2}
        return sorted(candidates, key=lambda c: (rank.get(c.relation_level, 9), -c.matched_count, c.adrg))

    def _validate_links(self) -> None:
        missing: List[str] = []
        for rule in self.rules.values():
            for comp in rule.components:
                if comp.table_id not in self.tables:
                    missing.append(f"{rule.adrg} -> {comp.table_id}")
        if missing:
            joined = "\n".join(missing[:20])
            raise ValueError(f"rule_components에 존재하지 않는 table_id가 있습니다.\n{joined}")

    def _build_code_to_tables(self) -> Dict[str, List[str]]:
        mapping: Dict[str, List[str]] = {}
        for table in self.tables.values():
            for member in table.members:
                mapping.setdefault(normalize(member.code), []).append(table.table_id)
        return mapping

    def _build_table_to_rules(self) -> Dict[str, List[str]]:
        mapping: Dict[str, List[str]] = {}
        for rule in self.rules.values():
            for comp in rule.components:
                adrg_list = mapping.setdefault(comp.table_id, [])
                if rule.adrg not in adrg_list:
                    adrg_list.append(rule.adrg)
        return mapping

    def rules_for_code(self, code: str) -> List[RuleDef]:
        table_ids = self.code_to_tables.get(normalize(code), [])
        adrg_set: Set[str] = set()
        for table_id in table_ids:
            adrg_set.update(self.table_to_rules.get(table_id, []))
        return [self.rules[adrg] for adrg in sorted(adrg_set)]

    def tables_for_code(self, code: str) -> List[TableDef]:
        return [self.tables[t] for t in self.code_to_tables.get(normalize(code), [])]

    def member_for_code(self, code: str) -> Optional[CodeMember]:
        for table in self.tables.values():
            member = table.member_by_code(code)
            if member:
                return member
        return None

    def rules_for_table(self, table_id: str) -> List[RuleDef]:
        return [self.rules[a] for a in self.table_to_rules.get(table_id, [])]

    def search(self, query: str, category: str = "전체") -> List[SearchResult]:
        q = normalize(query)
        results: List[SearchResult] = []
        seen: Set[Tuple[str, str]] = set()

        def allow(kind: str) -> bool:
            if category == "전체":
                return True
            if category == "상병코드":
                return kind == "diagnosis_code"
            if category == "기타진단코드":
                return kind == "secondary_diagnosis_code"
            if category == "수술·처치코드":
                return kind == "procedure_code"
            if category == "검사·처치코드":
                return kind == "test_code"
            if category == "부가코드":
                return kind == "supplement_code"
            if category == "ADRG":
                return kind in {"adrg", "aadrg"}
            if category == "MDC":
                return kind == "mdc"
            if category == "TABLE":
                return kind == "table"
            return True

        def add(result: SearchResult) -> None:
            key = (result.kind, result.key)
            if key not in seen and allow(result.kind):
                seen.add(key)
                results.append(result)

        if not q:
            if category == "MDC":
                for mdc in self.mdcs.values():
                    count = len(self.rules_for_mdc(mdc.mdc))
                    add(SearchResult("mdc", mdc.mdc, f"MDC {mdc.mdc}", f"{mdc.name} · ADRG {count}개", 5, mdc=mdc.mdc))
            else:
                for rule in self.rules.values():
                    add(SearchResult("adrg", rule.adrg, rule.adrg, rule.title_full, 20, rule.group_code, rule.group_name, rule.mdc))
            return results

        # MDC 검색: MDC 정식명/별칭이 정확히 일치하면 다른 코드·질병군명 결과를 섞지 않는다.
        exact_mdc_matches: List[MDCDef] = []
        for mdc in self.mdcs.values():
            searchable = [f"MDC {mdc.mdc}", f"MDC{mdc.mdc}", mdc.name, *mdc.aliases]
            normalized_values = [normalize(value) for value in searchable]
            if q in normalized_values:
                exact_mdc_matches.append(mdc)
            elif (not q.isdigit() or category == "MDC") and any(q in value for value in normalized_values):
                count = len(self.rules_for_mdc(mdc.mdc))
                add(SearchResult("mdc", mdc.mdc, f"MDC {mdc.mdc}", f"{mdc.name} · ADRG {count}개", 0, mdc=mdc.mdc))
        if exact_mdc_matches and category in {"전체", "MDC"}:
            return [
                SearchResult("mdc", mdc.mdc, f"MDC {mdc.mdc}", f"{mdc.name} · ADRG {len(self.rules_for_mdc(mdc.mdc))}개", 0, mdc=mdc.mdc)
                for mdc in exact_mdc_matches
            ]

        for table in self.tables.values():
            for member in table.members:
                code_match = q in normalize(member.code)
                name_match = q in normalize(member.display_name)
                if code_match or name_match:
                    kind = result_kind_for_code_type(table.code_type)
                    priority = 0 if normalize(member.code) == q else 10 if code_match else 30
                    add(SearchResult(kind, member.code, member.code, member.display_name, priority))

        for rule in self.rules.values():
            exact_mapping = next((m for m in rule.aadrg_mappings if q == normalize(m.aadrg)), None)
            if exact_mapping is not None:
                add(SearchResult("aadrg", rule.adrg, exact_mapping.aadrg, f"{exact_mapping.aadrg_name} · ADRG {rule.adrg}", 0, exact_mapping.group_code, exact_mapping.group_name, rule.mdc))
                continue
            mapping_fields: List[str] = []
            for mapping in rule.aadrg_mappings:
                mapping_fields.extend([mapping.aadrg, mapping.group_code, mapping.group_name, mapping.aadrg_name])
            fields = [rule.adrg, *mapping_fields, rule.title, rule.subtitle, rule.title_full, rule.condition_text, rule.group_code, rule.group_name, rule.group_display]
            if any(q in normalize(v) for v in fields):
                add(SearchResult("adrg", rule.adrg, rule.adrg, rule.title_full, 0 if q == normalize(rule.adrg) else 20, rule.group_code, rule.group_name, rule.mdc))

        for table in self.tables.values():
            fields = [table.table_id, table.display_label, table.code_type]
            if any(q in normalize(v) for v in fields):
                add(SearchResult("table", table.table_id, table.display_label, f"{table.code_type} · {table.count}개 코드", 25))

        return sorted(results, key=lambda r: (r.priority, r.kind, r.label))


# =============================================================================
# 4. 화면 컴포넌트
# =============================================================================


class ResultCard(QFrame):
    clicked_result = None

    def __init__(self, result: SearchResult, on_click) -> None:
        super().__init__()
        self.result = result
        self.on_click = on_click
        self.setObjectName("ResultCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setFrameShape(QFrame.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(10)
        badge = QLabel(self.kind_label(result.kind))
        badge.setObjectName(self.kind_badge_name(result.kind))
        badge.setAlignment(Qt.AlignCenter)
        top.addWidget(badge)

        title = QLabel(result.label)
        title.setObjectName("ResultTitle")
        top.addWidget(title)
        top.addStretch(1)

        if result.kind in {"adrg", "aadrg", "relation_adrg"} and result.mdc:
            mdc_badge = QLabel(f"MDC {result.mdc}")
            mdc_badge.setObjectName("MDCBadge")
            mdc_badge.setAlignment(Qt.AlignCenter)
            top.addWidget(mdc_badge)

        if result.kind in {"adrg", "aadrg", "relation_adrg"} and result.group_code:
            group = QLabel(f"{result.group_code}군")
            group.setObjectName(group_badge_name(result.group_code, "result"))
            group.setAlignment(Qt.AlignCenter)
            group.setToolTip(f"{result.group_code}군 · {result.group_name}")
            top.addWidget(group)

        layout.addLayout(top)

        sub = QLabel(result.sublabel)
        sub.setObjectName("ResultSub")
        sub.setWordWrap(True)
        layout.addWidget(sub)

    @staticmethod
    def kind_label(kind: str) -> str:
        return {
            "procedure_code": "수술·처치코드",
            "test_code": "검사·처치코드",
            "supplement_code": "부가코드",
            "diagnosis_code": "상병코드",
            "secondary_diagnosis_code": "기타진단코드",
            "adrg": "ADRG",
            "aadrg": "AADRG",
            "table": "TABLE",
            "mdc": "MDC",
            "relation_adrg": "관계 ADRG",
        }.get(kind, kind)

    @staticmethod
    def kind_badge_name(kind: str) -> str:
        return {
            "procedure_code": "BadgeGreen",
            "test_code": "BadgeTeal",
            "supplement_code": "BadgeOrange",
            "diagnosis_code": "BadgeBlue",
            "secondary_diagnosis_code": "BadgeBlue",
            "adrg": "BadgePurple",
            "aadrg": "BadgePurple",
            "table": "BadgeGray",
            "mdc": "BadgeNavy",
            "relation_adrg": "BadgeRelation",
        }.get(kind, "BadgeGray")

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.on_click(self.result)
        super().mousePressEvent(event)


class CodeTableFrame(QFrame):
    """table 버튼 클릭 시 펼쳐지는 상세 코드표."""

    def __init__(self, table_def: TableDef, highlight_code: str = "") -> None:
        super().__init__()
        self.table_def = table_def
        self.highlight_code = normalize(highlight_code)
        self.setObjectName("ExpandedTableFrame")
        self.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        title_row = QHBoxLayout()
        title = QLabel(f"전체 코드 · {table_def.display_label} · {table_def.count}개")
        title.setObjectName("ExpandedTitle")
        title_row.addWidget(title)
        title_row.addStretch(1)

        source = QLabel(table_def.source_page)
        source.setObjectName("SmallMuted")
        title_row.addWidget(source)
        layout.addLayout(title_row)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("현재 table 안에서 코드 또는 코드명을 검색")
        self.filter_edit.setObjectName("InnerSearch")
        self.filter_edit.textChanged.connect(self.apply_filter)
        layout.addWidget(self.filter_edit)

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["코드", "코드명"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setObjectName("CodeTable")
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        layout.addWidget(self.table)

        self.populate_table()

    def populate_table(self) -> None:
        members = list(self.table_def.members)
        self.table.setRowCount(len(members))
        for row, member in enumerate(members):
            code_item = QTableWidgetItem(member.code)
            name_item = QTableWidgetItem(member.display_name)
            if self.highlight_code and normalize(member.code) == self.highlight_code:
                code_item.setData(Qt.UserRole, "highlight")
                name_item.setData(Qt.UserRole, "highlight")
                code_item.setBackground(Qt.GlobalColor.transparent)
                font = code_item.font()
                font.setBold(True)
                code_item.setFont(font)
                name_font = name_item.font()
                name_font.setBold(True)
                name_item.setFont(name_font)
            self.table.setItem(row, 0, code_item)
            self.table.setItem(row, 1, name_item)

        height = min(300, 38 + len(members) * 32)
        self.table.setMinimumHeight(height)
        self.table.setMaximumHeight(height)

    def apply_filter(self, text: str) -> None:
        q = normalize(text)
        for row in range(self.table.rowCount()):
            code = self.table.item(row, 0).text()
            name = self.table.item(row, 1).text()
            visible = not q or q in normalize(code) or q in normalize(name)
            self.table.setRowHidden(row, not visible)


class AdvancedConditionRow(QFrame):
    CODE_TYPES = ["자동판별", "상병코드", "기타진단코드", "수술·처치코드", "검사·처치코드", "부가코드"]

    def __init__(self, index: int, remove_callback) -> None:
        super().__init__()
        self.remove_callback = remove_callback
        self.setObjectName("AdvancedConditionRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        self.index_label = QLabel(f"검색 {index}")
        self.index_label.setObjectName("AdvancedIndex")
        layout.addWidget(self.index_label)

        self.type_combo = QComboBox()
        self.type_combo.addItems(self.CODE_TYPES)
        self.type_combo.setObjectName("AdvancedTypeCombo")
        layout.addWidget(self.type_combo)

        self.code_edit = QLineEdit()
        self.code_edit.setPlaceholderText("정확한 코드 입력 · 예: O1311")
        self.code_edit.setClearButtonEnabled(True)
        self.code_edit.setObjectName("AdvancedCodeEdit")
        layout.addWidget(self.code_edit, 1)

        self.remove_button = QPushButton("삭제")
        self.remove_button.setObjectName("AdvancedRemoveButton")
        self.remove_button.clicked.connect(lambda: self.remove_callback(self))
        layout.addWidget(self.remove_button)

    def set_index(self, index: int) -> None:
        self.index_label.setText(f"검색 {index}")

    def condition(self) -> AdvancedCondition:
        return AdvancedCondition(self.type_combo.currentText(), self.code_edit.text().strip())


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.store = KDRGDataStore()
        self.current_query = ""
        self.current_results: List[SearchResult] = []
        self.selected_result: Optional[SearchResult] = None
        self.advanced_rows: List[AdvancedConditionRow] = []
        self.relation_candidates: Dict[str, RelationCandidate] = {}
        self.relation_operator = "AND"
        # 검색 결과 상세 → ADRG 상세처럼 단계적으로 이동할 때 돌아갈 화면을 저장합니다.
        # 검색어·왼쪽 결과 목록은 그대로 두고 오른쪽 상세 화면만 복원합니다.
        self.detail_history: List[Dict[str, object]] = []
        self.current_detail_kind = ""
        self.current_detail_key = ""
        self.setWindowTitle("KDRG 코드 관계 검색기 v16 - MDC 검색·복수 코드 관계검색")
        self.resize(1500, 900)
        self.setMinimumSize(1180, 760)

        self._build_ui()
        self._apply_style()
        self.search_edit.setText("MDC 04")
        self.run_search()

    # ------------------------------------------------------------------
    # UI 골격
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.setCentralWidget(root)

        root_layout.addWidget(self._build_header())
        root_layout.addWidget(self._build_notice())

        splitter = QSplitter(Qt.Horizontal)
        splitter.setObjectName("MainSplitter")
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([360, 1140])
        root_layout.addWidget(splitter, 1)

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("Header")
        layout = QVBoxLayout(header)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(10)

        title_row = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("KDRG 코드 관계 검색기")
        title.setObjectName("HeaderTitle")
        subtitle = QLabel("코드·ADRG·TABLE·MDC를 검색하고 복수 코드의 조건구조상 관계를 확인합니다.")
        subtitle.setObjectName("HeaderSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        title_row.addLayout(title_box)
        title_row.addStretch(1)
        badge = QLabel(self.store.ui_badge)
        badge.setObjectName("VersionBadge")
        badge.setAlignment(Qt.AlignCenter)
        title_row.addWidget(badge)
        layout.addLayout(title_row)

        search_row = QHBoxLayout()
        self.category_combo = QComboBox()
        self.category_combo.addItems(["전체", "상병코드", "기타진단코드", "수술·처치코드", "검사·처치코드", "부가코드", "ADRG", "MDC", "TABLE"])
        self.category_combo.setObjectName("SearchCombo")
        self.category_combo.currentTextChanged.connect(self.run_search)
        search_row.addWidget(self.category_combo)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("예: MDC 04, 호흡기계, I214, M6565, F051, F0511, 심근경색")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.returnPressed.connect(self.run_search)
        self.search_edit.textChanged.connect(self._search_text_changed)
        self.search_edit.setObjectName("SearchEdit")
        search_row.addWidget(self.search_edit, 1)
        search_button = QPushButton("검색")
        search_button.setObjectName("SearchButton")
        search_button.clicked.connect(self.run_search)
        search_row.addWidget(search_button)
        layout.addLayout(search_row)

        self.advanced_toggle = QToolButton()
        self.advanced_toggle.setText("복수 코드 관계검색 펼치기")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setArrowType(Qt.RightArrow)
        self.advanced_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.advanced_toggle.setObjectName("AdvancedToggle")
        self.advanced_toggle.toggled.connect(self._toggle_advanced_panel)
        layout.addWidget(self.advanced_toggle, 0, Qt.AlignLeft)

        self.advanced_panel = QFrame()
        self.advanced_panel.setObjectName("AdvancedPanel")
        self.advanced_panel.setVisible(False)
        advanced_layout = QVBoxLayout(self.advanced_panel)
        advanced_layout.setContentsMargins(12, 10, 12, 10)
        advanced_layout.setSpacing(8)

        caution = QLabel("입력코드가 같은 ADRG·같은 조건식에 연결되는지 확인하는 관계검색입니다. 최종 조건 충족이나 DRG 판정을 의미하지 않습니다.")
        caution.setObjectName("AdvancedCaution")
        caution.setWordWrap(True)
        advanced_layout.addWidget(caution)

        self.advanced_rows_container = QWidget()
        self.advanced_rows_layout = QVBoxLayout(self.advanced_rows_container)
        self.advanced_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.advanced_rows_layout.setSpacing(6)
        advanced_layout.addWidget(self.advanced_rows_container)

        controls = QHBoxLayout()
        self.relation_operator_combo = QComboBox()
        self.relation_operator_combo.addItems(["AND", "OR"])
        self.relation_operator_combo.setObjectName("RelationOperatorCombo")
        controls.addWidget(QLabel("조건 관계"))
        controls.addWidget(self.relation_operator_combo)
        add_button = QPushButton("+ 조건 추가")
        add_button.setObjectName("AdvancedAddButton")
        add_button.clicked.connect(self.add_advanced_condition_row)
        controls.addWidget(add_button)
        controls.addStretch(1)
        reset_button = QPushButton("초기화")
        reset_button.setObjectName("AdvancedResetButton")
        reset_button.clicked.connect(self.reset_advanced_conditions)
        controls.addWidget(reset_button)
        relation_button = QPushButton("공통 관련 ADRG 검색")
        relation_button.setObjectName("RelationSearchButton")
        relation_button.clicked.connect(self.run_relation_search)
        controls.addWidget(relation_button)
        advanced_layout.addLayout(controls)
        layout.addWidget(self.advanced_panel)

        self.add_advanced_condition_row()
        self.add_advanced_condition_row()
        return header

    def _toggle_advanced_panel(self, checked: bool) -> None:
        self.advanced_panel.setVisible(checked)
        self.advanced_toggle.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
        self.advanced_toggle.setText("복수 코드 관계검색 접기" if checked else "복수 코드 관계검색 펼치기")

    def add_advanced_condition_row(self) -> None:
        if len(self.advanced_rows) >= 6:
            QMessageBox.information(self, "조건 추가", "복수 코드 관계검색은 최대 6개 조건까지 입력할 수 있습니다.")
            return
        row = AdvancedConditionRow(len(self.advanced_rows) + 1, self.remove_advanced_condition_row)
        self.advanced_rows.append(row)
        self.advanced_rows_layout.addWidget(row)
        self._refresh_advanced_row_state()

    def remove_advanced_condition_row(self, row: AdvancedConditionRow) -> None:
        if len(self.advanced_rows) <= 2:
            QMessageBox.information(self, "조건 삭제", "복수 코드 관계검색은 최소 2개의 입력칸을 유지합니다.")
            return
        self.advanced_rows.remove(row)
        row.setParent(None)
        row.deleteLater()
        self._refresh_advanced_row_state()

    def _refresh_advanced_row_state(self) -> None:
        for index, row in enumerate(self.advanced_rows, start=1):
            row.set_index(index)
            row.remove_button.setEnabled(len(self.advanced_rows) > 2)

    def reset_advanced_conditions(self) -> None:
        while len(self.advanced_rows) > 2:
            row = self.advanced_rows.pop()
            row.setParent(None)
            row.deleteLater()
        for row in self.advanced_rows:
            row.type_combo.setCurrentIndex(0)
            row.code_edit.clear()
        self.relation_operator_combo.setCurrentText("AND")
        self._refresh_advanced_row_state()

    def _build_notice(self) -> QWidget:
        notice = QFrame()
        notice.setObjectName("Notice")
        layout = QHBoxLayout(notice)
        layout.setContentsMargins(16, 8, 16, 8)
        label = QLabel(
            self.store.notice + " 복수 코드 관계검색 결과는 최종 분류 판정이 아니라 동일 ADRG·조건식 안의 연결구조를 설명합니다."
        )
        label.setObjectName("NoticeLabel")
        label.setWordWrap(True)
        layout.addWidget(label)
        return notice

    def _build_left_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("LeftPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 14, 8, 12)
        layout.setSpacing(10)

        top = QHBoxLayout()
        title = QLabel("검색 결과")
        title.setObjectName("PanelTitle")
        top.addWidget(title)
        top.addStretch(1)
        self.result_count = QLabel("0건")
        self.result_count.setObjectName("CountLabel")
        top.addWidget(self.result_count)
        layout.addLayout(top)

        self.result_scroll = QScrollArea()
        self.result_scroll.setWidgetResizable(True)
        self.result_scroll.setObjectName("ResultScroll")
        self.result_container = QWidget()
        self.result_layout = QVBoxLayout(self.result_container)
        self.result_layout.setContentsMargins(4, 4, 4, 4)
        self.result_layout.setSpacing(10)
        self.result_layout.addStretch(1)
        self.result_scroll.setWidget(self.result_container)
        layout.addWidget(self.result_scroll, 1)

        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("RightPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setSpacing(10)

        top = QHBoxLayout()
        self.back_button = QPushButton("← 이전 화면")
        self.back_button.setObjectName("BackButton")
        self.back_button.setToolTip("ADRG 상세를 열기 전의 코드 또는 TABLE 상세 화면으로 돌아갑니다.")
        self.back_button.clicked.connect(self.go_back)
        self.back_button.setVisible(False)
        top.addWidget(self.back_button)

        title = QLabel("상세 정보")
        title.setObjectName("PanelTitle")
        top.addWidget(title)
        top.addStretch(1)
        self.current_type_label = QLabel("")
        self.current_type_label.setObjectName("CurrentType")
        top.addWidget(self.current_type_label)
        layout.addLayout(top)

        self.detail_scroll = QScrollArea()
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setObjectName("DetailScroll")
        self.detail_container = QWidget()
        self.detail_layout = QVBoxLayout(self.detail_container)
        self.detail_layout.setContentsMargins(0, 0, 0, 0)
        self.detail_layout.setSpacing(12)
        self.detail_layout.setSizeConstraint(QLayout.SetMinimumSize)
        self.detail_layout.addStretch(1)
        self.detail_scroll.setWidget(self.detail_container)
        layout.addWidget(self.detail_scroll, 1)

        return panel

    # ------------------------------------------------------------------
    # 검색 및 렌더링
    # ------------------------------------------------------------------

    def _search_text_changed(self) -> None:
        # 입력할 때마다 즉시 갱신하면 부담이 커질 수 있어, 엔터/검색 버튼 중심으로 둔다.
        pass

    def run_search(self) -> None:
        # 새 검색은 새로운 탐색 시작점이므로 이전 상세화면 이력을 초기화합니다.
        self._clear_detail_history()
        self.current_query = self.search_edit.text().strip()
        category = self.category_combo.currentText()
        self.current_results = self.store.search(self.current_query, category)
        self._render_results()
        if self.current_results:
            self.select_result(self.current_results[0])
        else:
            self._render_empty_detail("검색 결과가 없습니다.")

    def run_relation_search(self) -> None:
        conditions = [row.condition() for row in self.advanced_rows if row.code_edit.text().strip()]
        if len(conditions) < 2:
            QMessageBox.information(self, "복수 코드 관계검색", "서로 다른 코드 조건을 2개 이상 입력하세요.")
            return

        seen: Set[Tuple[str, str]] = set()
        duplicates: List[str] = []
        for condition in conditions:
            key = (condition.code_type, normalize(condition.code))
            if key in seen:
                duplicates.append(condition.code)
            seen.add(key)
        if duplicates:
            QMessageBox.warning(self, "중복 입력", "동일한 코드·유형 조건이 중복 입력되었습니다: " + ", ".join(duplicates))
            return

        missing: List[str] = []
        for condition in conditions:
            if not self.store.exact_table_ids_for_code(condition.code, condition.code_type):
                missing.append(f"{condition.code} ({condition.code_type})")
        if missing:
            QMessageBox.warning(self, "코드 확인", "현재 데이터에서 정확히 찾지 못한 조건입니다:\n" + "\n".join(missing))
            return

        self._clear_detail_history()
        self.relation_operator = self.relation_operator_combo.currentText()
        candidates = self.store.relation_search(conditions, self.relation_operator)
        self.relation_candidates = {candidate.adrg: candidate for candidate in candidates}
        self.current_query = " / ".join(condition.code for condition in conditions)
        self.current_results = []
        for candidate in candidates:
            rule = self.store.rules[candidate.adrg]
            code_text = ", ".join(condition.code for condition in conditions)
            sublabel = f"{candidate.status_label} · {candidate.matched_count}/{candidate.total_count}개 입력 연결 · {code_text}"
            self.current_results.append(SearchResult("relation_adrg", rule.adrg, rule.adrg, sublabel, 0, rule.group_code, rule.group_name, rule.mdc))
        self._render_results()
        if self.current_results:
            self.select_result(self.current_results[0])
        else:
            self.current_type_label.setText("복수 코드 관계검색")
            self._render_empty_detail("입력한 코드 조건과 연결되는 ADRG가 없습니다.")

    def _render_results(self) -> None:
        clear_layout(self.result_layout)
        self.result_count.setText(f"{len(self.current_results)}건")

        if not self.current_results:
            empty = QLabel("직접 일치하는 항목이 없습니다.")
            empty.setObjectName("EmptyText")
            empty.setAlignment(Qt.AlignCenter)
            self.result_layout.addWidget(empty)
            self.result_layout.addStretch(1)
            return

        for result in self.current_results:
            card = ResultCard(result, self.select_result)
            self.result_layout.addWidget(card)
        self.result_layout.addStretch(1)

    def select_result(self, result: SearchResult) -> None:
        # 왼쪽의 직접 검색 결과를 새로 선택한 경우에는 그 항목을 탐색 시작점으로 삼습니다.
        self._clear_detail_history()
        self.selected_result = result
        if result.kind in {"diagnosis_code", "secondary_diagnosis_code", "procedure_code", "test_code", "supplement_code"}:
            self.current_type_label.setText(ResultCard.kind_label(result.kind))
            self.render_code_detail(result.key)
        elif result.kind in {"adrg", "aadrg"}:
            self.current_type_label.setText(ResultCard.kind_label(result.kind))
            self.render_rule_detail(result.key)
        elif result.kind == "mdc":
            self.current_type_label.setText("MDC")
            self.render_mdc_detail(result.key)
        elif result.kind == "relation_adrg":
            self.current_type_label.setText("복수 코드 관계검색")
            self.render_relation_detail(result.key)
        elif result.kind == "table":
            self.current_type_label.setText("TABLE")
            self.render_table_detail(result.key)
        else:
            self._render_empty_detail("상세 정보를 표시할 수 없습니다.")

    # ------------------------------------------------------------------
    # 상세화면 탐색 이력
    # ------------------------------------------------------------------

    def _clear_detail_history(self) -> None:
        self.detail_history.clear()
        self._update_back_button()

    def _push_current_detail(self) -> None:
        if not self.current_detail_kind or not self.current_detail_key:
            return
        self.detail_history.append(
            {
                "kind": self.current_detail_kind,
                "key": self.current_detail_key,
                "type_label": self.current_type_label.text(),
                "scroll_value": self.detail_scroll.verticalScrollBar().value(),
            }
        )
        self._update_back_button()

    def _set_current_detail(self, kind: str, key: str) -> None:
        self.current_detail_kind = kind
        self.current_detail_key = key

    def _update_back_button(self) -> None:
        if not hasattr(self, "back_button"):
            return
        has_history = bool(self.detail_history)
        self.back_button.setVisible(has_history)
        if not has_history:
            self.back_button.setText("← 이전 화면")
            return

        previous = self.detail_history[-1]
        key = str(previous.get("key", "")).strip()
        kind = str(previous.get("kind", ""))
        if kind == "code" and key:
            self.back_button.setText(f"← {key} 검색 결과")
        elif kind == "table" and key:
            self.back_button.setText(f"← {key} TABLE")
        elif kind == "mdc" and key:
            self.back_button.setText(f"← MDC {key}")
        elif kind == "relation" and key:
            self.back_button.setText("← 복수 코드 관계검색 결과")
        elif key:
            self.back_button.setText(f"← {key} 상세")
        else:
            self.back_button.setText("← 이전 화면")

    def open_rule_detail(self, adrg: str) -> None:
        # 관련 ADRG 요약에서 상세로 들어갈 때만 현재 화면을 이력에 저장합니다.
        if self.current_detail_kind == "rule" and normalize(self.current_detail_key) == normalize(adrg):
            return
        self._push_current_detail()
        self.current_type_label.setText("ADRG")
        self.render_rule_detail(adrg)
        self.detail_scroll.verticalScrollBar().setValue(0)

    def go_back(self) -> None:
        if not self.detail_history:
            return

        previous = self.detail_history.pop()
        kind = str(previous.get("kind", ""))
        key = str(previous.get("key", ""))
        type_label = str(previous.get("type_label", ""))
        scroll_value = int(previous.get("scroll_value", 0) or 0)

        self.current_type_label.setText(type_label)
        if kind == "code":
            self.render_code_detail(key)
        elif kind == "rule":
            self.render_rule_detail(key)
        elif kind == "table":
            self.render_table_detail(key)
        elif kind == "mdc":
            self.render_mdc_detail(key)
        elif kind == "relation":
            self.render_relation_detail(key)
        else:
            self._render_empty_detail("이전 상세 화면을 복원할 수 없습니다.")

        self._update_back_button()
        # 레이아웃이 다시 계산된 뒤 기존 세로 위치로 복원합니다.
        QTimer.singleShot(0, lambda value=scroll_value: self.detail_scroll.verticalScrollBar().setValue(value))

    def _reset_detail_layout(self) -> None:
        clear_layout(self.detail_layout)

    def _render_empty_detail(self, message: str) -> None:
        self._reset_detail_layout()
        box = self._simple_card()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(20, 20, 20, 20)
        label = QLabel(message)
        label.setObjectName("EmptyText")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        self.detail_layout.addWidget(box)
        self.detail_layout.addStretch(1)

    # ------------------------------------------------------------------
    # 상세: 코드
    # ------------------------------------------------------------------

    def render_code_detail(self, code: str) -> None:
        self._set_current_detail("code", code)
        self._reset_detail_layout()
        member = self.store.member_for_code(code)
        tables = self.store.tables_for_code(code)
        related_rules = self.store.rules_for_code(code)

        if not member:
            self._render_empty_detail("코드 상세 정보를 찾을 수 없습니다.")
            return

        code_types = list(dict.fromkeys(t.code_type for t in tables))
        code_type = " / ".join(code_types) if code_types else "코드"
        primary_code_type = code_types[0] if code_types else ""
        table_text = ", ".join(f"{t.table_id} · {t.display_label}" for t in tables) or "-"

        self.detail_layout.addWidget(
            self._build_primary_card(
                badge_text=code_type,
                badge_name=badge_name_for_code_type(primary_code_type),
                title=member.code,
                subtitle=member.display_name,
                rows=[
                    ("코드 유형", code_type),
                    ("포함 TABLE", table_text),
                    ("KDRG 버전", self.store.version),
                ],
            )
        )

        self.detail_layout.addWidget(
            self._build_related_summary(
                title=f"관련 ADRG / 질병군 · {len(related_rules)}건",
                rules=related_rules,
                clickable=True,
            )
        )

        tabs = QTabWidget()
        tabs.setObjectName("Tabs")
        tabs.addTab(self._scroll_wrap(self._build_rule_cards(related_rules, highlight_code=code)), "관련 ADRG")
        tabs.addTab(self._scroll_wrap(self._build_evidence_panel(related_rules)), "원문 근거")
        self.detail_layout.addWidget(tabs, 1)
        self.detail_layout.addStretch(1)

    # ------------------------------------------------------------------
    # 상세: ADRG
    # ------------------------------------------------------------------

    def render_rule_detail(self, adrg: str) -> None:
        self._set_current_detail("rule", adrg)
        self._reset_detail_layout()
        rule = self.store.rules.get(adrg)
        if not rule:
            self._render_empty_detail("ADRG 상세 정보를 찾을 수 없습니다.")
            return

        self.detail_layout.addWidget(
            self._build_primary_card(
                badge_text="ADRG",
                badge_name="BadgePurple",
                title=rule.adrg,
                subtitle=rule.title_full,
                rows=[
                    ("AADRG", rule.aadrg_display),
                    ("질병군 분류", rule.group_display),
                    ("MDC", rule.mdc),
                    ("조건 원문", rule.condition_text),
                    ("KDRG 버전", self.store.version),
                ],
            )
        )

        self.detail_layout.addWidget(
            self._build_related_summary(
                title="관련 ADRG / 질병군 · 1건",
                rules=[rule],
                clickable=False,
            )
        )

        tabs = QTabWidget()
        tabs.setObjectName("Tabs")
        tabs.addTab(self._scroll_wrap(self._build_rule_cards([rule], highlight_code=self.current_query)), "관련 ADRG")
        tabs.addTab(self._scroll_wrap(self._build_evidence_panel([rule])), "원문 근거")
        self.detail_layout.addWidget(tabs, 1)
        self.detail_layout.addStretch(1)

    # ------------------------------------------------------------------
    # 상세: MDC
    # ------------------------------------------------------------------

    def render_mdc_detail(self, mdc_code: str) -> None:
        code = str(mdc_code).strip().zfill(2)
        self._set_current_detail("mdc", code)
        self._reset_detail_layout()
        mdc = self.store.mdcs.get(code)
        if not mdc:
            self._render_empty_detail("MDC 상세 정보를 찾을 수 없습니다.")
            return
        rules = self.store.rules_for_mdc(code)
        mappings = [mapping for rule in rules for mapping in rule.aadrg_mappings]
        group_counts = {group: sum(1 for m in mappings if m.group_code == group) for group in ("A", "B", "C")}
        self.detail_layout.addWidget(self._build_primary_card(
            badge_text="MDC", badge_name="BadgeNavy", title=f"MDC {code}", subtitle=mdc.name,
            rows=[
                ("포함 ADRG", f"{len(rules)}개"),
                ("포함 AADRG", f"{len(mappings)}개"),
                ("질병군 분포", f"A군 {group_counts['A']}개 · B군 {group_counts['B']}개 · C군 {group_counts['C']}개"),
                ("KDRG 버전", self.store.version),
            ],
        ))
        tabs = QTabWidget()
        tabs.setObjectName("Tabs")
        tabs.addTab(self._scroll_wrap(self._build_related_summary(f"MDC {code} 전체 ADRG · {len(rules)}건", rules, clickable=True)), "전체")
        for group_code, label in (("A", "A군"), ("B", "B군"), ("C", "C군")):
            grouped = [rule for rule in rules if any(m.group_code == group_code for m in rule.aadrg_mappings)]
            tabs.addTab(self._scroll_wrap(self._build_related_summary(f"{label} ADRG · {len(grouped)}건", grouped, clickable=True)), label)
        self.detail_layout.addWidget(tabs, 1)
        self.detail_layout.addStretch(1)

    # ------------------------------------------------------------------
    # 상세: 복수 코드 관계검색
    # ------------------------------------------------------------------

    def render_relation_detail(self, adrg: str) -> None:
        self._set_current_detail("relation", adrg)
        self._reset_detail_layout()
        candidate = self.relation_candidates.get(adrg)
        rule = self.store.rules.get(adrg)
        if not candidate or not rule:
            self._render_empty_detail("복수 코드 관계검색 상세를 찾을 수 없습니다.")
            return
        input_text = ", ".join(match.code for match in candidate.rule_matches)
        caution = {
            "strict": "입력코드가 적어도 하나의 동일 조건식 안에 모두 연결됩니다. 남은 table·추가조건은 별도 확인이 필요합니다.",
            "split": "모든 입력코드가 같은 ADRG에는 연결되지만 서로 다른 OR 조건식에 나뉘어 있습니다. 하나의 조합조건으로 해석하면 안 됩니다.",
            "partial": "OR 검색으로 입력코드 일부만 연결된 ADRG입니다.",
        }[candidate.relation_level]
        self.detail_layout.addWidget(self._build_primary_card(
            badge_text="관계검색", badge_name="BadgeRelation", title=rule.adrg, subtitle=rule.title_full,
            rows=[
                ("관계 상태", candidate.status_label),
                ("입력 조건", f"{self.relation_operator} · {input_text}"),
                ("연결 수", f"{candidate.matched_count}/{candidate.total_count}개 입력"),
                ("MDC", f"MDC {rule.mdc}"),
                ("AADRG", rule.aadrg_display),
                ("질병군 분류", rule.group_display),
                ("해석 주의", caution),
            ],
        ))
        self.detail_layout.addWidget(self._build_relation_analysis(candidate, rule))
        tabs = QTabWidget()
        tabs.setObjectName("Tabs")
        tabs.addTab(self._scroll_wrap(self._build_rule_cards([rule])), "ADRG 전체 조건")
        tabs.addTab(self._scroll_wrap(self._build_evidence_panel([rule])), "원문 근거")
        self.detail_layout.addWidget(tabs, 1)
        self.detail_layout.addStretch(1)

    def _build_relation_analysis(self, candidate: RelationCandidate, rule: RuleDef) -> QFrame:
        card = self._simple_card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        title = QLabel("입력코드와 조건식 연결 분석")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        for group_match in candidate.group_matches:
            group_def = next((g for g in rule.condition_groups if g.group_no == group_match.group_no), None)
            if group_def is None:
                continue
            box = QFrame()
            box.setObjectName("RelationGroupBoxStrict" if group_match.all_inputs_in_group else "RelationGroupBoxSplit")
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(12, 10, 12, 10)
            box_layout.setSpacing(7)
            header = QLabel(f"{group_match.group_label} · " + ("모든 입력 연결" if group_match.all_inputs_in_group else "일부 입력 연결"))
            header.setObjectName("RelationGroupTitle")
            box_layout.addWidget(header)

            matched_component_ids: Set[str] = set()
            table_to_codes: Dict[str, List[str]] = {}
            for match in group_match.matches:
                if not match.table_ids:
                    line = QLabel(f"{match.code} → 이 조건식에는 없음")
                    line.setObjectName("RelationMiss")
                    box_layout.addWidget(line)
                    continue
                labels = []
                for tid in match.table_ids:
                    matched_component_ids.add(tid)
                    table_to_codes.setdefault(tid, []).append(match.code)
                    labels.append(self.store.tables[tid].display_label)
                line = QLabel(f"{match.code} → " + ", ".join(labels))
                line.setObjectName("RelationHit")
                line.setWordWrap(True)
                box_layout.addWidget(line)

            remaining = [self.store.tables[c.table_id].display_label for c in group_def.components if c.table_id not in matched_component_ids]
            checks: List[str] = []
            if remaining:
                checks.append("미입력 TABLE: " + ", ".join(remaining))
            if group_def.requirements:
                checks.append("추가 조건: " + " · ".join(group_def.requirements))
            for component in group_def.components:
                if component.requirement_label:
                    count = len(set(table_to_codes.get(component.table_id, [])))
                    if "2개 이상" in component.requirement_label and count >= 2:
                        checks.append(f"{self.store.tables[component.table_id].display_label} {component.requirement_label}: 입력코드 {count}개 구조상 일치")
                    else:
                        checks.append(f"{self.store.tables[component.table_id].display_label}: {component.requirement_label} 추가 확인")
            for tid, codes in table_to_codes.items():
                component = next((c for c in group_def.components if c.table_id == tid), None)
                if len(set(codes)) >= 2 and not (component and component.requirement_label):
                    checks.append(f"{self.store.tables[tid].display_label}에 입력코드 {len(set(codes))}개가 함께 포함되지만, 공식 조건이 두 코드를 모두 요구한다는 뜻은 아님")
            if checks:
                check_label = QLabel("확인 필요\n- " + "\n- ".join(checks))
                check_label.setObjectName("RelationCheck")
                check_label.setWordWrap(True)
                box_layout.addWidget(check_label)
            layout.addWidget(box)

        detail_button = QPushButton("이 ADRG의 전체 상세 보기")
        detail_button.setObjectName("RelationDetailButton")
        detail_button.clicked.connect(lambda checked=False, a=rule.adrg: self.open_rule_detail(a))
        layout.addWidget(detail_button, 0, Qt.AlignRight)
        return card

    # ------------------------------------------------------------------
    # 상세: TABLE
    # ------------------------------------------------------------------

    def render_table_detail(self, table_id: str) -> None:
        self._set_current_detail("table", table_id)
        self._reset_detail_layout()
        table = self.store.tables.get(table_id)
        if not table:
            self._render_empty_detail("TABLE 상세 정보를 찾을 수 없습니다.")
            return

        related_rules = self.store.rules_for_table(table_id)
        codes = [m.code for m in table.members]

        self.detail_layout.addWidget(
            self._build_primary_card(
                badge_text="TABLE",
                badge_name="BadgeGray",
                title=table.display_label,
                subtitle=shorten_codes(codes, limit=30),
                rows=[
                    ("TABLE_ID", table.table_id),
                    ("코드 유형", table.code_type),
                    ("코드 수", f"{table.count}개"),
                    ("근거", table.source_page),
                    ("KDRG 버전", self.store.version),
                ],
            )
        )

        self.detail_layout.addWidget(
            self._build_related_summary(
                title=f"이 TABLE을 사용하는 ADRG · {len(related_rules)}건",
                rules=related_rules,
                clickable=True,
            )
        )

        tabs = QTabWidget()
        tabs.setObjectName("Tabs")
        tabs.addTab(self._scroll_wrap(self._build_table_only_panel(table)), "TABLE 코드")
        tabs.addTab(self._scroll_wrap(self._build_rule_cards(related_rules, highlight_code=self.current_query)), "관련 ADRG")
        tabs.addTab(self._scroll_wrap(self._build_evidence_panel(related_rules)), "원문 근거")
        self.detail_layout.addWidget(tabs, 1)
        self.detail_layout.addStretch(1)

    # ------------------------------------------------------------------
    # 카드/패널 빌더
    # ------------------------------------------------------------------

    def _simple_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("WhiteCard")
        return card

    def _build_primary_card(
        self,
        badge_text: str,
        badge_name: str,
        title: str,
        subtitle: str,
        rows: List[Tuple[str, str]],
    ) -> QFrame:
        card = self._simple_card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        top = QHBoxLayout()
        badge = QLabel(badge_text)
        badge.setObjectName(badge_name)
        badge.setAlignment(Qt.AlignCenter)
        top.addWidget(badge)

        title_label = QLabel(title)
        title_label.setObjectName("DetailTitle")
        top.addWidget(title_label)
        top.addStretch(1)
        layout.addLayout(top)

        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("DetailSubtitle")
        subtitle_label.setWordWrap(True)
        layout.addWidget(subtitle_label)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setObjectName("Divider")
        layout.addWidget(line)

        grid = QGridLayout()
        grid.setHorizontalSpacing(22)
        grid.setVerticalSpacing(8)
        for row, (k, v) in enumerate(rows):
            key_label = QLabel(k)
            key_label.setObjectName("FieldKey")
            value_label = QLabel(v)
            value_label.setObjectName("FieldValue")
            value_label.setWordWrap(True)
            grid.addWidget(key_label, row, 0, Qt.AlignTop)
            grid.addWidget(value_label, row, 1)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        return card

    def _build_related_summary(self, title: str, rules: List[RuleDef], clickable: bool) -> QFrame:
        card = self._simple_card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        title_label = QLabel(title)
        title_label.setObjectName("SectionTitle")
        layout.addWidget(title_label)

        if not rules:
            empty = QLabel("연결된 ADRG가 없습니다.")
            empty.setObjectName("SmallMuted")
            layout.addWidget(empty)
            return card

        for rule in rules:
            row = QFrame()
            row.setObjectName("SummaryRowClickable" if clickable else "SummaryRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(8, 6, 8, 6)
            row_layout.setSpacing(16)

            adrg_label = QLabel(rule.adrg)
            adrg_label.setObjectName("SummaryADRG")
            row_layout.addWidget(adrg_label)

            mdc_badge = QLabel(f"MDC {rule.mdc}")
            mdc_badge.setObjectName("MDCBadge")
            mdc_badge.setAlignment(Qt.AlignCenter)
            row_layout.addWidget(mdc_badge)

            aadrg_label = QLabel(rule.aadrg_display)
            aadrg_label.setObjectName("SummaryAADRG")
            row_layout.addWidget(aadrg_label)

            group = QLabel(rule.group_display)
            group.setObjectName(group_badge_name(rule.group_code, "mini"))
            group.setAlignment(Qt.AlignCenter)
            row_layout.addWidget(group)

            title_label = QLabel(rule.title_full)
            title_label.setObjectName("SummaryText")
            title_label.setWordWrap(True)
            row_layout.addWidget(title_label, 1)

            if clickable:
                button = QPushButton("ADRG 상세")
                button.setObjectName("TinyButton")
                button.clicked.connect(lambda checked=False, a=rule.adrg: self.open_rule_detail(a))
                row_layout.addWidget(button)

            layout.addWidget(row)

        return card

    def _build_rule_cards(self, rules: List[RuleDef], highlight_code: str = "") -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        if not rules:
            empty = QLabel("연결된 ADRG가 없습니다.")
            empty.setObjectName("EmptyText")
            empty.setAlignment(Qt.AlignCenter)
            layout.addWidget(empty)
            layout.addStretch(1)
            return container

        for rule in rules:
            layout.addWidget(self._build_single_rule_card(rule, highlight_code=highlight_code))
        layout.addStretch(1)
        return container

    def _build_single_rule_card(self, rule: RuleDef, highlight_code: str = "") -> QFrame:
        card = self._simple_card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        # 카드 헤더
        header = QHBoxLayout()
        adrg = QLabel(rule.adrg)
        adrg.setObjectName("RuleADRG")
        header.addWidget(adrg)

        mdc_badge = QLabel(f"MDC {rule.mdc}")
        mdc_badge.setObjectName("MDCBadge")
        mdc_badge.setAlignment(Qt.AlignCenter)
        header.addWidget(mdc_badge)

        aadrg = QLabel(f"AADRG {rule.aadrg_display}")
        aadrg.setObjectName("RuleAADRG")
        header.addWidget(aadrg)
        header.addStretch(1)

        group = QLabel(rule.group_display)
        group.setObjectName(group_badge_name(rule.group_code, "full"))
        group.setAlignment(Qt.AlignCenter)
        header.addWidget(group)
        layout.addLayout(header)

        title = QLabel(rule.title_full)
        title.setObjectName("RuleTitle")
        title.setWordWrap(True)
        layout.addWidget(title)

        if len(rule.aadrg_mappings) > 1:
            mapping_detail = QLabel(rule.aadrg_detail_display)
            mapping_detail.setObjectName("ConditionIntro")
            mapping_detail.setWordWrap(True)
            layout.addWidget(mapping_detail)

        condition_label = QLabel("분류조건")
        condition_label.setObjectName("SmallMutedStrong")
        layout.addWidget(condition_label)

        # 조건 table 요약 영역
        condition_box = QFrame()
        condition_box.setObjectName("ConditionBox")
        condition_layout = QVBoxLayout(condition_box)
        condition_layout.setContentsMargins(12, 10, 12, 10)
        condition_layout.setSpacing(10)

        if len(rule.condition_groups) > 1:
            intro_text = rule.condition_summary or f"아래 {len(rule.condition_groups)}개 조건식 중 하나로 구성됨"
            intro = QLabel(intro_text)
            intro.setObjectName("ConditionIntro")
            intro.setWordWrap(True)
            condition_layout.addWidget(intro)

        for group_index, group_def in enumerate(rule.condition_groups):
            group_box = QFrame()
            group_box.setObjectName("ConditionGroupBox")
            group_layout = QVBoxLayout(group_box)
            group_layout.setContentsMargins(10, 9, 10, 9)
            group_layout.setSpacing(8)

            show_group_title = len(rule.condition_groups) > 1
            if show_group_title:
                group_title = QLabel(group_def.group_label or f"조건식 {group_def.group_no}")
                group_title.setObjectName("ConditionGroupTitle")
                group_layout.addWidget(group_title)

            for idx, component in enumerate(group_def.components):
                if idx > 0:
                    op_text = component.operator_before or "AND"
                    op = QLabel("그리고" if op_text.upper() == "AND" else op_text)
                    op.setObjectName("OperatorLabel")
                    op.setAlignment(Qt.AlignCenter)
                    group_layout.addWidget(op)

                table_def = self.store.tables[component.table_id]
                row = self._build_condition_table_row(table_def, highlight_code, component.requirement_label)
                group_layout.addWidget(row)

            if group_def.requirements:
                requirement_text = QLabel("추가 조건 · " + " · ".join(group_def.requirements))
                requirement_text.setObjectName("GroupRequirement")
                requirement_text.setWordWrap(True)
                group_layout.addWidget(requirement_text)

            condition_layout.addWidget(group_box)

            if group_index < len(rule.condition_groups) - 1:
                joiner = group_def.join_to_next_group or "OR"
                joiner_label = "또는" if joiner.upper() == "OR" else joiner
                divider = QLabel(f"──── {joiner_label} ────")
                divider.setObjectName("OrDivider")
                divider.setAlignment(Qt.AlignCenter)
                condition_layout.addWidget(divider)

        layout.addWidget(condition_box)

        note = QLabel("table명 버튼을 누르면 코드명 포함 상세 코드표가 펼쳐집니다. 코드요약은 원문 순서를 유지합니다.")
        note.setObjectName("SmallMuted")
        note.setWordWrap(True)
        layout.addWidget(note)

        return card

    def _build_condition_table_row(self, table_def: TableDef, highlight_code: str, requirement_label: str = "") -> QFrame:
        row = QFrame()
        contains_search = bool(normalize(highlight_code)) and table_def.contains_code(highlight_code)
        row.setObjectName("ConditionRowHit" if contains_search else "ConditionRow")
        layout = QVBoxLayout(row)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(8)

        button_text = f"{table_def.display_label} · {table_def.count}개"
        if contains_search:
            button_text += " · 검색코드 포함"
        button = QToolButton()
        button.setText(button_text)
        button.setCheckable(True)
        button.setCursor(Qt.PointingHandCursor)
        button.setObjectName("TablePillHit" if contains_search else "TablePill")
        top.addWidget(button)

        code_type = QLabel(table_def.code_type)
        code_type.setObjectName("MiniTypeBadge")
        code_type.setAlignment(Qt.AlignCenter)
        top.addWidget(code_type)

        if requirement_label:
            requirement = QLabel(requirement_label)
            requirement.setObjectName("RequirementBadge")
            requirement.setAlignment(Qt.AlignCenter)
            top.addWidget(requirement)

        top.addStretch(1)
        layout.addLayout(top)

        codes = [m.code for m in table_def.members]
        summary = QLabel(rich_code_summary(codes, highlight_code, limit=20))
        summary.setTextFormat(Qt.RichText)
        summary.setObjectName("CodeSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        expanded = CodeTableFrame(table_def, highlight_code=highlight_code)
        layout.addWidget(expanded)

        def toggle_expanded(checked: bool) -> None:
            expanded.setVisible(checked)
            button.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)

        button.setArrowType(Qt.RightArrow)
        button.toggled.connect(toggle_expanded)
        return row

    def _build_evidence_panel(self, rules: List[RuleDef]) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        if not rules:
            empty = QLabel("표시할 원문 근거가 없습니다.")
            empty.setObjectName("EmptyText")
            empty.setAlignment(Qt.AlignCenter)
            layout.addWidget(empty)
            layout.addStretch(1)
            return panel

        for rule in rules:
            card = self._simple_card()
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(18, 16, 18, 16)
            card_layout.setSpacing(10)

            title = QLabel(f"{rule.adrg} · {rule.aadrg_display} · {rule.group_display}")
            title.setObjectName("RuleADRG")
            card_layout.addWidget(title)

            body = QLabel(
                f"조건 원문: {rule.condition_text}\n"
                f"근거: {rule.source_page}\n"
                f"비고: {self.store.source_note}"
            )
            body.setObjectName("EvidenceText")
            body.setWordWrap(True)
            card_layout.addWidget(body)
            layout.addWidget(card)

        layout.addStretch(1)
        return panel

    def _build_table_only_panel(self, table_def: TableDef) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        frame = CodeTableFrame(table_def, highlight_code=self.current_query)
        frame.setVisible(True)
        layout.addWidget(frame)
        layout.addStretch(1)
        return panel

    def _scroll_wrap(self, widget: QWidget) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(widget)
        return wrapper

    # ------------------------------------------------------------------
    # 스타일
    # ------------------------------------------------------------------

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
                background: #edf2f8;
                color: #08264a;
                font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', Arial, sans-serif;
                font-size: 13px;
            }
            #Header {
                background: #173e68;
                border: none;
            }
            #HeaderTitle {
                color: white;
                font-size: 25px;
                font-weight: 800;
            }
            #HeaderSubtitle {
                color: #d6e7fb;
                font-size: 12px;
            }
            #VersionBadge {
                color: #eaf4ff;
                background: #2f5d8b;
                border: 1px solid #5f86ae;
                border-radius: 8px;
                padding: 10px 14px;
                font-size: 12px;
                font-weight: 700;
                min-width: 190px;
            }
            #SearchCombo {
                background: white;
                border: 1px solid #b7c6d6;
                border-radius: 5px;
                padding: 0 10px;
                min-height: 34px;
                min-width: 125px;
            }
            #SearchEdit {
                background: white;
                border: 1px solid #b7c6d6;
                border-radius: 6px;
                padding: 0 12px;
                min-height: 34px;
                color: #173e68;
            }
            #SearchButton {
                background: #2f77bd;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: 800;
                min-height: 34px;
                min-width: 82px;
            }
            #SearchButton:hover {
                background: #2669a9;
            }
            #Notice {
                background: #e8f0f8;
                border-bottom: 1px solid #cbd9e8;
            }
            #NoticeLabel {
                color: #315779;
                font-size: 12px;
            }
            #LeftPanel, #RightPanel {
                background: #edf2f8;
                border: none;
            }
            #BackButton {
                background: #ffffff;
                color: #16436c;
                border: 1px solid #b9cde0;
                border-radius: 7px;
                padding: 6px 11px;
                font-weight: 800;
                min-height: 24px;
            }
            #BackButton:hover {
                background: #e7f2ff;
                border: 1px solid #79abe0;
            }
            #BackButton:pressed {
                background: #d8eaff;
            }
            #PanelTitle {
                font-size: 16px;
                font-weight: 800;
                color: #0a2a4d;
            }
            #CountLabel, #CurrentType {
                color: #62758b;
                font-size: 12px;
            }
            #ResultScroll, #DetailScroll {
                background: transparent;
                border: none;
            }
            #ResultCard {
                background: white;
                border: 1px solid #d4dee9;
                border-radius: 8px;
            }
            #ResultCard:hover {
                background: #f7fbff;
                border: 1px solid #80b6ef;
            }
            #ResultTitle {
                font-size: 14px;
                font-weight: 800;
                color: #08264a;
            }
            #ResultSub {
                color: #2f4b68;
                font-size: 12px;
                line-height: 150%;
            }
            #WhiteCard {
                background: white;
                border: 1px solid #d4dee9;
                border-radius: 10px;
            }
            #Divider {
                color: #d9e2ec;
                background: #d9e2ec;
            }
            #DetailTitle {
                color: #08264a;
                font-size: 24px;
                font-weight: 900;
            }
            #DetailSubtitle {
                color: #0a2a4d;
                font-size: 14px;
                font-weight: 700;
            }
            #FieldKey {
                color: #58708a;
                font-weight: 700;
                min-width: 110px;
            }
            #FieldValue {
                color: #08264a;
            }
            #SectionTitle {
                color: #0a2a4d;
                font-size: 14px;
                font-weight: 800;
            }
            #SummaryRow, #SummaryRowClickable {
                background: #ffffff;
                border-radius: 8px;
            }
            #SummaryRowClickable:hover {
                background: #f1f7ff;
            }
            #SummaryADRG {
                color: #0a2a4d;
                font-weight: 900;
                min-width: 45px;
            }
            #SummaryAADRG {
                color: #657992;
                min-width: 60px;
            }
            #SummaryText {
                color: #1c3e62;
                font-size: 12px;
            }
            #TinyButton {
                background: #eef5fc;
                color: #16436c;
                border: 1px solid #c9dcec;
                border-radius: 6px;
                padding: 4px 9px;
                font-weight: 700;
            }
            #TinyButton:hover {
                background: #dbeeff;
                border: 1px solid #8dbce9;
            }
            #Tabs::pane {
                border: 1px solid #d4dee9;
                border-radius: 8px;
                background: #f6f9fc;
                top: -1px;
            }
            QTabBar::tab {
                background: #e4ebf3;
                color: #244867;
                padding: 10px 18px;
                border-top-left-radius: 7px;
                border-top-right-radius: 7px;
                font-weight: 800;
            }
            QTabBar::tab:selected {
                background: white;
                color: #08264a;
            }
            #RuleADRG {
                font-size: 21px;
                font-weight: 900;
                color: #08264a;
            }
            #RuleAADRG {
                color: #6d7e91;
                font-size: 13px;
                font-weight: 700;
            }
            #RuleTitle {
                color: #0a2a4d;
                font-size: 14px;
                font-weight: 800;
            }
            #ConditionBox {
                background: #f8fbff;
                border: 1px solid #e0e9f3;
                border-radius: 8px;
            }
            #ConditionIntro {
                color: #234766;
                background: #eef6ff;
                border: 1px solid #d3e8fb;
                border-radius: 7px;
                padding: 8px 10px;
                font-weight: 800;
            }
            #ConditionGroupBox {
                background: #ffffff;
                border: 1px solid #d8e5f0;
                border-radius: 9px;
            }
            #ConditionGroupTitle {
                color: #0a2a4d;
                font-size: 13px;
                font-weight: 900;
                padding: 2px 0 4px 0;
            }
            #OrDivider {
                color: #0b4f91;
                font-size: 12px;
                font-weight: 900;
                padding: 4px 0;
            }
            #ConditionRow {
                background: white;
                border: 1px solid #e0e8f0;
                border-radius: 8px;
            }
            #ConditionRowHit {
                background: #f2f8ff;
                border: 1px solid #85b8ee;
                border-radius: 8px;
            }
            #TablePill, #TablePillHit {
                border-radius: 7px;
                padding: 7px 12px;
                font-weight: 800;
            }
            #TablePill {
                color: #183b5f;
                background: #edf3f8;
                border: 1px solid #cbd8e5;
            }
            #TablePill:hover {
                background: #e2edf8;
            }
            #TablePillHit {
                color: #0b4f91;
                background: #dcebff;
                border: 1px solid #7cb2ee;
            }
            #TablePillHit:hover {
                background: #cfe4ff;
            }
            #CodeSummary {
                color: #183b5f;
                background: transparent;
                font-size: 13px;
                line-height: 160%;
            }
            #OperatorLabel {
                color: #5d728a;
                font-size: 11px;
                font-weight: 900;
                padding: 2px 0;
            }
            #ExpandedTableFrame {
                background: #ffffff;
                border: 1px solid #d6e2ef;
                border-radius: 8px;
            }
            #ExpandedTitle {
                color: #0a2a4d;
                font-size: 14px;
                font-weight: 900;
            }
            #InnerSearch {
                background: white;
                border: 1px solid #cbd8e5;
                border-radius: 6px;
                min-height: 30px;
                padding: 0 10px;
            }
            #CodeTable {
                background: white;
                gridline-color: #dfe7ef;
                border: 1px solid #dbe5ef;
                border-radius: 6px;
                alternate-background-color: #f8fbff;
            }
            QHeaderView::section {
                background: #edf3f8;
                color: #183b5f;
                border: none;
                border-right: 1px solid #d9e2ec;
                padding: 8px;
                font-weight: 800;
            }
            #BadgeGreen, #BadgeBlue, #BadgeTeal, #BadgeOrange, #BadgePurple, #BadgeGray, #BadgeNavy, #BadgeRelation, #MiniTypeBadge, #RequirementBadge, #MDCBadge, #ResultGroupBadgeA, #ResultGroupBadgeB, #ResultGroupBadgeC, #ResultGroupBadgeOther, #MiniGroupBadgeA, #MiniGroupBadgeB, #MiniGroupBadgeC, #MiniGroupBadgeOther, #GroupBadgeA, #GroupBadgeB, #GroupBadgeC, #GroupBadgeOther {
                border-radius: 8px;
                padding: 4px 10px;
                font-size: 12px;
                font-weight: 800;
            }
            #BadgeGreen {
                color: #008248;
                background: #def7ea;
            }
            #BadgeBlue {
                color: #0b5cad;
                background: #e4f0ff;
            }
            #BadgeTeal {
                color: #006b68;
                background: #def5f3;
            }
            #BadgeOrange {
                color: #9a4e00;
                background: #fff0db;
            }
            #BadgePurple {
                color: #6832b7;
                background: #efe4ff;
            }
            #BadgeGray {
                color: #46566a;
                background: #eef2f6;
            }
            #ResultGroupBadgeA, #ResultGroupBadgeB, #ResultGroupBadgeC, #ResultGroupBadgeOther {
                border-radius: 8px;
                padding: 4px 9px;
                font-size: 11px;
                font-weight: 900;
            }
            #ResultGroupBadgeA, #MiniGroupBadgeA { color: #0b4f91; background: #e6f1ff; }
            #ResultGroupBadgeB, #MiniGroupBadgeB { color: #087443; background: #e2f6eb; }
            #ResultGroupBadgeC, #MiniGroupBadgeC { color: #9a4e00; background: #fff0db; }
            #ResultGroupBadgeOther, #MiniGroupBadgeOther { color: #46566a; background: #eef2f6; }
            #MiniGroupBadgeA, #MiniGroupBadgeB, #MiniGroupBadgeC, #MiniGroupBadgeOther {
                border-radius: 8px;
                padding: 3px 9px;
                font-size: 11px;
                font-weight: 800;
            }
            #GroupBadgeA, #GroupBadgeB, #GroupBadgeC, #GroupBadgeOther {
                color: white;
                border-radius: 10px;
                padding: 7px 13px;
                font-size: 12px;
                font-weight: 900;
            }
            #GroupBadgeA { background: #0d4f91; }
            #GroupBadgeB { background: #137a4f; }
            #GroupBadgeC { background: #b65c00; }
            #GroupBadgeOther { background: #566779; }
            #MDCBadge {
                color: #35516d;
                background: #edf3f8;
                border: 1px solid #d4e0eb;
                border-radius: 7px;
                padding: 4px 8px;
                font-size: 10px;
                font-weight: 900;
            }
            #GroupRequirement {
                color: #7a3d00;
                background: #fff6e8;
                border: 1px solid #f1d2a7;
                border-radius: 7px;
                padding: 7px 10px;
                font-size: 11px;
                font-weight: 900;
            }
            #RequirementBadge {
                color: #8a3f00;
                background: #fff0db;
                border-radius: 7px;
                padding: 4px 9px;
                font-size: 11px;
                font-weight: 900;
            }
            #MiniTypeBadge {
                color: #42607e;
                background: #eef3f8;
                border-radius: 7px;
                padding: 4px 9px;
                font-size: 11px;
                font-weight: 800;
            }
            #SmallMuted, #SmallMutedStrong {
                color: #667a91;
                font-size: 12px;
            }
            #SmallMutedStrong {
                font-weight: 800;
            }
            #EvidenceText {
                color: #214463;
                line-height: 160%;
            }
            #EmptyText {
                color: #728295;
                font-size: 13px;
                padding: 24px;
            }
            #BadgeNavy { color: #ffffff; background: #234f7a; }
            #BadgeRelation { color: #7a3f00; background: #fff0d7; border: 1px solid #efc27d; }
            #AdvancedToggle { color: #e9f4ff; background: #28567f; border: 1px solid #5f86ae; border-radius: 7px; padding: 6px 10px; font-weight: 800; }
            #AdvancedToggle:hover { background: #346993; }
            #AdvancedPanel { background: #244b72; border: 1px solid #5d81a5; border-radius: 9px; }
            #AdvancedCaution { color: #eef7ff; background: #183e63; border-radius: 6px; padding: 8px 10px; font-weight: 700; }
            #AdvancedConditionRow { background: #f6faff; border: 1px solid #bad0e4; border-radius: 7px; }
            #AdvancedIndex { color: #173e68; font-weight: 900; min-width: 48px; }
            #AdvancedTypeCombo, #RelationOperatorCombo { background: white; border: 1px solid #b7c6d6; border-radius: 5px; min-height: 30px; padding: 0 8px; }
            #AdvancedCodeEdit { background: white; border: 1px solid #b7c6d6; border-radius: 5px; min-height: 30px; padding: 0 9px; }
            #AdvancedRemoveButton, #AdvancedResetButton, #AdvancedAddButton { background: #edf4fb; color: #16436c; border: 1px solid #bfd2e4; border-radius: 6px; padding: 5px 9px; font-weight: 800; }
            #RelationSearchButton { background: #f0a33b; color: #3d2500; border: none; border-radius: 6px; padding: 7px 13px; font-weight: 900; }
            #RelationSearchButton:hover { background: #ffb956; }
            #RelationGroupBoxStrict { background: #eff9f3; border: 1px solid #8ec8a5; border-radius: 8px; }
            #RelationGroupBoxSplit { background: #fff7eb; border: 1px solid #e8bd7a; border-radius: 8px; }
            #RelationGroupTitle { color: #173e68; font-weight: 900; }
            #RelationHit { color: #0c633e; font-weight: 800; }
            #RelationMiss { color: #8a4e00; }
            #RelationCheck { color: #6b3d00; background: #fff2dc; border-radius: 6px; padding: 8px 10px; }
            #RelationDetailButton { background: #e7f1ff; color: #0b4f91; border: 1px solid #9fc5eb; border-radius: 7px; padding: 7px 12px; font-weight: 900; }
            """
        )


# =============================================================================
# 5. 실행
# =============================================================================


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("KDRG 코드 관계 검색기")

    font = QFont("Malgun Gothic")
    font.setPointSize(10)
    app.setFont(font)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ImportError as exc:
        print("PySide6가 설치되어 있지 않습니다. 먼저 'pip install PySide6'를 실행하세요.")
        print(exc)
        raise
