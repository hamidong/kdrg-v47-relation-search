# -*- coding: utf-8 -*-
"""KDRG 관계 검색기 v16 MDC 검색·복수 코드 관계검색 자동 검증기."""
from __future__ import annotations

import json
import py_compile
import re
from collections import Counter, defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
APP_PATH = BASE_DIR / "kdrg_relation_search_v16_mdc_advanced_search.py"
DATA_PATH = BASE_DIR / "data" / "kdrg_relation_data_v16_mdc_advanced_search.json"
REPORT_PATH = BASE_DIR / "validation_report_v16_mdc_advanced_search.txt"

EXPECTED_RULES_BY_MDC = {"04": 57, "05": 104}
EXPECTED_RULE_COUNT = 161
EXPECTED_TABLE_COUNT = 194
EXPECTED_MEMBER_COUNT = 2947
EXPECTED_AADRG_COUNT = 173
EXPECTED_GROUP_COUNTS = {"A": 90, "B": 73, "C": 10}


def norm(value: object) -> str:
    return str(value or "").strip().upper().replace(" ", "")


def table_mdc(table_id: str) -> str:
    if table_id.startswith("E04_"):
        return "04"
    if table_id.startswith("F"):
        return "05"
    return ""


def relation_search(data: dict, conditions: list[tuple[str, str]], operator: str) -> dict[str, str]:
    """앱의 핵심 관계검색 규칙을 독립적으로 재검증한다."""
    tables = {t["table_id"]: t for t in data["tables"]}
    code_to_tables: dict[str, set[str]] = defaultdict(set)
    for table in tables.values():
        for member in table.get("members", []):
            code_to_tables[norm(member.get("code"))].add(table["table_id"])

    condition_tables: list[set[str]] = []
    for code_type, code in conditions:
        ids = set(code_to_tables.get(norm(code), set()))
        if code_type != "자동판별":
            ids = {tid for tid in ids if tables[tid].get("code_type") == code_type}
        condition_tables.append(ids)

    results: dict[str, str] = {}
    total = len(conditions)
    for rule in data["rules"]:
        groups = rule.get("condition_groups", [])
        rule_ids = {c["table_id"] for g in groups for c in g.get("components", [])}
        matched = sum(bool(ids & rule_ids) for ids in condition_tables)
        if operator == "AND" and matched != total:
            continue
        if operator == "OR" and matched == 0:
            continue
        strict = False
        for group in groups:
            group_ids = {c["table_id"] for c in group.get("components", [])}
            if all(bool(ids & group_ids) for ids in condition_tables):
                strict = True
                break
        if matched == total and strict:
            level = "strict"
        elif matched == total:
            level = "split"
        else:
            level = "partial"
        results[rule["adrg"]] = level
    return results


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    lines: list[str] = []

    if not DATA_PATH.exists():
        print(f"데이터 파일 없음: {DATA_PATH}")
        return 2
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    rules = data.get("rules", [])
    tables = data.get("tables", [])
    mdcs = data.get("mdc_master", [])
    meta = data.get("meta", {})

    rule_ids = [r.get("adrg", "") for r in rules]
    table_ids = [t.get("table_id", "") for t in tables]
    rules_by_id = {r["adrg"]: r for r in rules}
    tables_by_id = {t["table_id"]: t for t in tables}

    if len(rules) != EXPECTED_RULE_COUNT:
        errors.append(f"ADRG 수: {len(rules)} != {EXPECTED_RULE_COUNT}")
    if len(tables) != EXPECTED_TABLE_COUNT:
        errors.append(f"TABLE 수: {len(tables)} != {EXPECTED_TABLE_COUNT}")
    if len(rule_ids) != len(set(rule_ids)):
        errors.append("중복 ADRG 존재")
    if len(table_ids) != len(set(table_ids)):
        errors.append("중복 TABLE_ID 존재")

    rules_by_mdc = Counter(str(r.get("mdc", "")) for r in rules)
    if dict(rules_by_mdc) != EXPECTED_RULES_BY_MDC:
        errors.append(f"MDC별 ADRG 수 오류: {dict(rules_by_mdc)}")
    member_count = sum(len(t.get("members", [])) for t in tables)
    if member_count != EXPECTED_MEMBER_COUNT:
        errors.append(f"코드 멤버 수: {member_count} != {EXPECTED_MEMBER_COUNT}")
    mapping_count = sum(len(r.get("aadrg_mappings", [])) for r in rules)
    if mapping_count != EXPECTED_AADRG_COUNT:
        errors.append(f"AADRG 수: {mapping_count} != {EXPECTED_AADRG_COUNT}")
    group_counts = Counter(m.get("group_code", "") for r in rules for m in r.get("aadrg_mappings", []))
    if dict(group_counts) != EXPECTED_GROUP_COUNTS:
        errors.append(f"A/B/C 수 오류: {dict(group_counts)}")

    # MDC master 및 검색 별칭
    mdc_by_code = {str(x.get("mdc", "")).zfill(2): x for x in mdcs}
    for code, name in {"04": "호흡기계", "05": "순환기계"}.items():
        item = mdc_by_code.get(code)
        if not item:
            errors.append(f"MDC master 누락: {code}")
            continue
        aliases = {norm(x) for x in item.get("aliases", [])}
        for expected in {f"MDC {code}", f"MDC{code}", name}:
            if norm(expected) not in aliases and norm(expected) not in {norm(item.get('name')), norm(f"MDC {code}")}:
                errors.append(f"MDC {code} 검색별칭 누락: {expected}")

    # TABLE/조건 참조 구조
    table_to_rules: dict[str, set[str]] = defaultdict(set)
    code_to_tables: dict[str, set[str]] = defaultdict(set)
    for table in tables:
        tid = table.get("table_id", "")
        members = table.get("members", [])
        if not members:
            errors.append(f"빈 TABLE: {tid}")
        seen_codes: set[str] = set()
        for index, member in enumerate(members, start=1):
            code = str(member.get("code", "")).strip()
            if not code:
                errors.append(f"빈 코드: {tid}#{index}")
            if code in seen_codes:
                errors.append(f"TABLE 내 중복코드: {tid}:{code}")
            seen_codes.add(code)
            if member.get("original_order") != index:
                errors.append(f"원문순서 오류: {tid}:{code}")
            code_to_tables[norm(code)].add(tid)

    for rule in rules:
        adrg = rule["adrg"]
        groups = rule.get("condition_groups", [])
        if not groups:
            errors.append(f"조건그룹 누락: {adrg}")
        for index, group in enumerate(groups):
            join = str(group.get("join_to_next_group") or "").upper()
            if index < len(groups) - 1 and join not in {"AND", "OR"}:
                errors.append(f"조건그룹 연결자 오류: {adrg}:{join}")
            if index == len(groups) - 1 and join:
                errors.append(f"마지막 그룹 연결자 존재: {adrg}:{join}")
            for comp in group.get("components", []):
                tid = comp.get("table_id", "")
                if tid not in tables_by_id:
                    errors.append(f"존재하지 않는 TABLE 참조: {adrg}->{tid}")
                else:
                    table_to_rules[tid].add(adrg)
    unused = set(table_ids) - set(table_to_rules)
    if unused:
        errors.append("미사용 TABLE: " + ", ".join(sorted(unused)[:20]))

    # 기존 특수조건 회귀
    for adrg, count in {"E011": 2, "E672": 2, "F136": 2, "F194": 2, "F600": 2}.items():
        if len(rules_by_id.get(adrg, {}).get("condition_groups", [])) != count:
            errors.append(f"{adrg} 조건그룹 수 오류")
    e011_req = rules_by_id["E011"]["condition_groups"][1].get("requirements", [])
    if "부가코드 ADC02 미포함" not in e011_req:
        errors.append("E011 ADC02 미포함 요구사항 누락")

    # 복수 코드 관계검색 핵심 회귀검증
    relation_cases = [
        ("E011 OR그룹 분산", [("수술·처치코드", "O1311"), ("수술·처치코드", "O1326")], "AND", "E011", "split"),
        ("E011 동일 table2", [("수술·처치코드", "O1326"), ("수술·처치코드", "O1351")], "AND", "E011", "strict"),
        ("F136 동일 조건식", [("수술·처치코드", "M6552"), ("수술·처치코드", "M6554")], "AND", "F136", "strict"),
        ("F194 2개 시술+주진단", [("상병코드", "E1050"), ("수술·처치코드", "M6597"), ("수술·처치코드", "M6605")], "AND", "F194", "strict"),
        ("F600 주진단+기타진단", [("상병코드", "I210"), ("기타진단코드", "I110")], "AND", "F600", "strict"),
        ("E501 인공호흡+신대체", [("수술·처치코드", "M5850"), ("수술·처치코드", "O7020")], "AND", "E501", "strict"),
    ]
    relation_lines: list[str] = []
    for label, conditions, operator, expected_adrg, expected_level in relation_cases:
        result = relation_search(data, conditions, operator)
        actual = result.get(expected_adrg)
        relation_lines.append(f"- {label}: {expected_adrg}={actual}")
        if actual != expected_level:
            errors.append(f"관계검색 오류 {label}: {actual} != {expected_level}")

    # 잘못된 코드유형은 검색대상 없음
    wrong_type_tables = [tid for tid in code_to_tables[norm("O1311")] if tables_by_id[tid].get("code_type") == "상병코드"]
    if wrong_type_tables:
        errors.append("O1311이 상병코드 TABLE에 잘못 연결됨")

    # 앱 정적검증
    required_tokens = {
        "v16 데이터 경로": "kdrg_relation_data_v16_mdc_advanced_search.json",
        "MDC 검색": 'category == "MDC"',
        "MDC 상세": "def render_mdc_detail(self, mdc_code: str)",
        "관계검색 실행": "def run_relation_search(self)",
        "같은 조건식 분석": "same ADRG",  # docstring/설명에 없어도 아래 실제 토큰으로 대체
        "관계검색 상세": "def render_relation_detail(self, adrg: str)",
        "분산 경고": "서로 다른 OR 조건식에 분산",
        "최종판정 금지 문구": "최종 조건 충족이나 DRG 판정을 의미하지 않습니다",
        "뒤로가기": "def go_back(self)",
    }
    if APP_PATH.exists():
        source = APP_PATH.read_text(encoding="utf-8")
        # 'same ADRG' 영문 토큰 대신 실제 한국어 구조 토큰 검사
        required_tokens["같은 조건식 분석"] = "같은 조건식 내 공통 연결"
        for label, token in required_tokens.items():
            if token not in source:
                errors.append(f"UI/로직 토큰 누락: {label}")
        try:
            py_compile.compile(str(APP_PATH), doraise=True)
        except Exception as exc:
            errors.append(f"py_compile 실패: {exc}")
    else:
        errors.append(f"앱 파일 없음: {APP_PATH}")

    lines.extend([
        "KDRG 관계 검색기 v16 - MDC 검색·복수 코드 관계검색 자동 검증 결과",
        "=" * 82,
        f"데이터 버전: {meta.get('app_data_version', '')}",
        f"범위: {meta.get('data_scope', '')}",
        "",
        "[구조 집계]",
        f"- MDC: {len(mdcs)}개 · {', '.join(f'MDC {x}' for x in sorted(mdc_by_code))}",
        f"- ADRG: {len(rules)}개 · MDC04 {rules_by_mdc.get('04', 0)} / MDC05 {rules_by_mdc.get('05', 0)}",
        f"- AADRG: {mapping_count}개",
        f"- TABLE: {len(tables)}개",
        f"- 코드 멤버: {member_count}개",
        f"- 질병군: A {group_counts.get('A', 0)} / B {group_counts.get('B', 0)} / C {group_counts.get('C', 0)}",
        "",
        "[복수 코드 관계검색 회귀검증]",
        *relation_lines,
        "",
        "[검증 결과]",
        f"- 오류: {len(errors)}건",
        f"- 경고: {len(warnings)}건",
    ])
    if errors:
        lines.append("\n오류 상세:")
        lines.extend(f"  * {x}" for x in errors)
    if warnings:
        lines.append("\n경고 상세:")
        lines.extend(f"  * {x}" for x in warnings)
    lines.append("\n최종 판정: " + ("PASS" if not errors else "FAIL"))
    report = "\n".join(lines) + "\n"
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(report)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
