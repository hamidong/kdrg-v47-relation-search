"""KDRG V4.7 코드 관계 검색기 - 데이터 모델 및 유틸리티.

이 모듈은 순수 데이터 구조와 문자열/코드 처리 유틸리티만 포함합니다.
PySide6 위젯 의존성이 없어 데이터 계층 단위 테스트에 재사용할 수 있습니다.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

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
    exclude_components: Tuple[RuleComponent, ...] = ()


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
    def exclusion_components(self) -> Tuple[RuleComponent, ...]:
        """미포함/제외조건 TABLE. 양의 관계검색에는 사용하지 않는다."""
        flattened: List[RuleComponent] = []
        for group in self.condition_groups:
            flattened.extend(group.exclude_components)
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

