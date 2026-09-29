"""KDRG V4.7 코드 관계 검색기 - JSON 기반 데이터 저장소."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

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
    result_kind_for_code_type,
)

# =============================================================================
# 3. 샘플 데이터 저장소
# =============================================================================


def _app_base_dir() -> Path:
    """실행 기준 경로를 반환합니다.

    PyInstaller로 패키징된 exe에서는 sys._MEIPASS(임시 압축 해제 폴더)를
    기준으로 삼고, 개발 환경(python main.py)에서는 이 파일의 상위 폴더를
    기준으로 삼습니다. exe 위치와 무관하게 내부 data 파일을 정확히
    찾기 위한 처리입니다.
    """

    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent.parent


class KDRGDataStore:
    """외부 JSON 기반 KDRG 관계 데이터 저장소."""

    DEFAULT_DATA_PATH = _app_base_dir() / "data" / "kdrg_v47_ui_fixture.json"

    def __init__(self, data_path: Optional[object] = None) -> None:
        self.data_path = Path(data_path) if data_path else self.DEFAULT_DATA_PATH
        if not self.data_path.exists():
            raise FileNotFoundError(
                "KDRG 데이터 파일을 찾을 수 없습니다.\n"
                f"필요 파일: {self.data_path}\n\n"
                "ZIP 파일을 압축 해제한 뒤 data/kdrg_relation_data_v47_pilot_special_cases_v1.json 파일이 "
                "실행 py 파일과 같은 폴더 구조에 있는지 확인하세요."
            )

        raw = json.loads(self.data_path.read_text(encoding="utf-8"))
        self.meta: Dict[str, str] = raw.get("meta", {})
        self.version = self.meta.get("kdrg_version", "KDRG")
        self.data_scope = self.meta.get("data_scope", "외부 데이터")
        self.ui_badge = self.meta.get("ui_badge", "KDRG V4.7 PILOT · SPECIAL CASE")
        self.notice = self.meta.get("notice", "외부 JSON 데이터 파일을 읽어 검색합니다.")
        self.source_note = self.meta.get("source_note", "KDRG 원문 기준")
        self.abc_basis = self.meta.get("abc_basis", "A/B/C 분류 기준 미기재")
        self.correction_basis = self.meta.get("correction_basis", "-")

        self.tables: Dict[str, TableDef] = self._load_tables(raw.get("tables", []))
        self.rules: Dict[str, RuleDef] = self._load_rules(raw.get("rules", []))
        self.mdcs: Dict[str, MDCDef] = self._load_mdcs(raw.get("mdc_master", []))
        self._validate_links()
        self.code_to_tables: Dict[str, List[str]] = self._build_code_to_tables()
        self.table_to_rules: Dict[str, List[str]] = self._build_table_to_rules()
        self.exclusion_table_to_rules: Dict[str, List[str]] = self._build_exclusion_table_to_rules()

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
                            exclude_components=build_components(group_raw.get("exclude_components", [])),
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
                        exclude_components=(),
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
            exclusion_table_ids = {comp.table_id for comp in rule.exclusion_components}
            # 입력코드가 미포함/제외 TABLE에 있으면 양의 관계 후보에서 제외합니다.
            if any(global_ids & exclusion_table_ids for _, global_ids in condition_tables):
                continue
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
            for comp in (*rule.components, *rule.exclusion_components):
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

    def _build_exclusion_table_to_rules(self) -> Dict[str, List[str]]:
        mapping: Dict[str, List[str]] = {}
        for rule in self.rules.values():
            for comp in rule.exclusion_components:
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

    def exclusion_rules_for_code(self, code: str) -> List[RuleDef]:
        table_ids = self.code_to_tables.get(normalize(code), [])
        adrg_set: Set[str] = set()
        for table_id in table_ids:
            adrg_set.update(self.exclusion_table_to_rules.get(table_id, []))
        return [self.rules[adrg] for adrg in sorted(adrg_set)]

    def exclusion_tables_for_code(self, code: str) -> List[TableDef]:
        tids = set(self.code_to_tables.get(normalize(code), [])) & set(self.exclusion_table_to_rules)
        return [self.tables[t] for t in sorted(tids)]

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

