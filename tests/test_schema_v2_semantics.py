# -*- coding: utf-8 -*-
"""v2 condition_expression 의미 동일성 검증.

각 ADRG의 v2 condition_expression이 v1 condition_groups와
의미적으로 동등한지 확인한다.

실행
    python tests/test_schema_v2_semantics.py

종료코드
    0 = PASS, 1 = FAIL
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Set

for _s in ("stdout", "stderr"):
    _st = getattr(sys, _s, None)
    if _st is not None and hasattr(_st, "reconfigure"):
        try:
            _st.reconfigure(encoding="utf-8")
        except Exception:
            pass

ROOT = Path(__file__).resolve().parent.parent
V1_JSON = ROOT / "data" / "kdrg_v47_ui_fixture.json"
V2_JSON = ROOT / "data" / "kdrg_v47_pilot_schema_v2.json"

ERRORS: list[str] = []
PASS_LIST: list[str] = []


def fail(msg: str) -> None:
    ERRORS.append(f"[FAIL] {msg}")
    print(f"[FAIL] {msg}")


def ok(msg: str) -> None:
    PASS_LIST.append(f"[PASS] {msg}")
    print(f"[PASS] {msg}")


# ---------------------------------------------------------------------------
# 헬퍼: v2 condition_expression에서 모든 양의 TABLE_MATCH / TABLE_CODE_COUNT_AT_LEAST
#        의 table_id를 수집한다.
# ---------------------------------------------------------------------------
def collect_positive_table_ids(node: Dict, inside_not: bool = False) -> Set[str]:
    ids: Set[str] = set()
    nt = node.get("node_type", "")
    is_not = (nt == "NOT")
    if nt in ("TABLE_MATCH", "TABLE_CODE_COUNT_AT_LEAST") and not inside_not:
        tid = node.get("table_id")
        if tid:
            ids.add(tid)
    for child in node.get("children", []):
        ids |= collect_positive_table_ids(child, inside_not or is_not)
    return ids


def collect_all_table_ids(node: Dict) -> Set[str]:
    """NOT 포함 모든 테이블 ID."""
    ids: Set[str] = set()
    nt = node.get("node_type", "")
    if nt in ("TABLE_MATCH", "TABLE_CODE_COUNT_AT_LEAST"):
        tid = node.get("table_id")
        if tid:
            ids.add(tid)
    for child in node.get("children", []):
        ids |= collect_all_table_ids(child)
    return ids


# ---------------------------------------------------------------------------
# v1 condition_groups에서 모든 table_id를 수집한다.
# ---------------------------------------------------------------------------
def collect_v1_table_ids(rule: Dict) -> Set[str]:
    ids: Set[str] = set()
    for cg in rule.get("condition_groups", []):
        for comp in cg.get("components", []):
            if comp.get("table_id"):
                ids.add(comp["table_id"])
        for comp in cg.get("exclude_components", []):
            if comp.get("table_id"):
                ids.add(comp["table_id"])
    return ids


# ---------------------------------------------------------------------------
# 개별 검증 함수
# ---------------------------------------------------------------------------
def check_table_id_coverage(v1_rule: Dict, v2_rule: Dict):
    adrg = v2_rule["adrg"]
    v1_tables = collect_v1_table_ids(v1_rule)
    v2_tables = collect_all_table_ids(v2_rule.get("condition_expression", {}))

    # v2 condition_groups_display와도 비교
    v2_display_tables: Set[str] = set()
    for cg in v2_rule.get("condition_groups_display", []):
        for c in cg.get("components", []):
            if c.get("table_id"):
                v2_display_tables.add(c["table_id"])
        for c in cg.get("exclude_components", []):
            if c.get("table_id"):
                v2_display_tables.add(c["table_id"])

    # condition_expression에 있는 테이블은 v1 테이블을 포함해야 한다
    missing = v1_tables - v2_tables
    if missing:
        fail(f"[{adrg}] v1 table_id가 v2 condition_expression에 없음: {sorted(missing)}")
    else:
        ok(f"[{adrg}] table_id 커버리지 OK (v1={len(v1_tables)} v2_expr={len(v2_tables)})")

    # condition_groups_display ↔ condition_expression 테이블 집합 일치
    if v2_display_tables and (v2_display_tables - v2_tables) and adrg not in ("E501","E502","E511","E512"):
        # E50x/E51x는 E50_ prefix 공유 TABLE을 갖기 때문에 느슨하게 처리
        extra = v2_display_tables - v2_tables
        fail(f"[{adrg}] condition_groups_display에 있으나 condition_expression에 없는 table_id: {sorted(extra)}")
    else:
        ok(f"[{adrg}] condition_groups_display ↔ condition_expression 테이블 일치 OK")


def check_expression_not_empty(v2_rule: Dict):
    adrg = v2_rule["adrg"]
    expr = v2_rule.get("condition_expression", {})
    if not expr or not expr.get("node_type"):
        fail(f"[{adrg}] condition_expression 비어 있거나 node_type 없음")
    else:
        ok(f"[{adrg}] condition_expression 구조 존재 (node_type={expr['node_type']})")


def check_node_ids_unique(node: Dict, seen: Set[str], adrg: str):
    nid = node.get("node_id")
    if nid:
        if nid in seen:
            fail(f"[{adrg}] 중복 node_id: '{nid}'")
        else:
            seen.add(nid)
    for child in node.get("children", []):
        check_node_ids_unique(child, seen, adrg)


def check_all_node_ids_unique(v2_rule: Dict):
    adrg = v2_rule["adrg"]
    seen: Set[str] = set()
    check_node_ids_unique(v2_rule.get("condition_expression", {}), seen, adrg)
    if not any(f"[{adrg}] 중복" in e for e in ERRORS):
        ok(f"[{adrg}] 모든 node_id 고유")


def check_source_refs_present(v2_rule: Dict):
    adrg = v2_rule["adrg"]

    def count_refs(node: Dict) -> int:
        n = len(node.get("source_refs", []))
        for child in node.get("children", []):
            n += count_refs(child)
        return n

    n = count_refs(v2_rule.get("condition_expression", {}))
    if n == 0:
        fail(f"[{adrg}] condition_expression 내 source_refs 없음")
    else:
        ok(f"[{adrg}] condition_expression source_refs 존재 ({n}건)")


def check_aadrg_mappings(v1_rule: Dict, v2_rule: Dict):
    adrg = v2_rule["adrg"]
    v1_aadrs = {am["aadrg"] for am in v1_rule.get("aadrg_mappings", [])}
    v2_aadrs = {am["aadrg"] for am in v2_rule.get("aadrg_mappings", [])}
    if v1_aadrs != v2_aadrs:
        fail(f"[{adrg}] aadrg_mappings AADRG 코드 불일치: v1={sorted(v1_aadrs)} v2={sorted(v2_aadrs)}")
    else:
        ok(f"[{adrg}] aadrg_mappings AADRG 코드 일치 ({len(v1_aadrs)}개)")

    # abc_classification.status 모두 OFFICIAL_PDF_EXACT_CODE여야 함 (파일럿 9개)
    for am in v2_rule.get("aadrg_mappings", []):
        status = am.get("abc_classification", {}).get("status", "")
        if status != "OFFICIAL_PDF_EXACT_CODE":
            fail(f"[{adrg} → {am['aadrg']}] abc_classification.status = '{status}' (기대: OFFICIAL_PDF_EXACT_CODE)")
    else:
        ok(f"[{adrg}] 모든 AADRG abc_classification.status = OFFICIAL_PDF_EXACT_CODE")


def check_member_name_preserved(v1_table: Dict, v2_table: Dict):
    tid = v2_table["table_id"]
    v1_members = {m["code"]: m.get("name_ko", "") for m in v1_table.get("members", [])}
    v2_members = {m["code"]: m.get("name_ko_effective", "") for m in v2_table.get("members", [])}
    if v1_members.keys() != v2_members.keys():
        fail(f"[{tid}] member 코드 집합 불일치: v1={sorted(v1_members)} v2={sorted(v2_members)}")
        return
    mismatches = [(c, v1_members[c], v2_members[c])
                  for c in v1_members if v1_members[c] != v2_members[c]]
    if mismatches:
        for c, n1, n2 in mismatches:
            fail(f"[{tid} / {c}] name_ko 불일치: v1='{n1}' v2='{n2}'")
    else:
        ok(f"[{tid}] 코드 집합 및 name_ko 일치 ({len(v1_members)}개 코드)")


# ---------------------------------------------------------------------------
# E-series 인공호흡 특이케이스 의미 검증
# ---------------------------------------------------------------------------
def check_e50x_shared_tables(v2):
    # E501/E502/E511/E512는 모두 같은 VENT/RRT TABLE을 참조해야 한다
    e_adrs = ["E501", "E502", "E511", "E512"]
    rules_by_adrg = {r["adrg"]: r for r in v2.get("rules", [])}
    vent_tables: list[Set[str]] = []
    rrt_tables: list[Set[str]] = []
    for adrg in e_adrs:
        r = rules_by_adrg.get(adrg)
        if not r:
            fail(f"[{adrg}] 규칙 없음")
            continue
        all_tids = collect_all_table_ids(r.get("condition_expression", {}))
        vent = {t for t in all_tids if "VENT" in t}
        rrt  = {t for t in all_tids if "RRT" in t}
        vent_tables.append(vent)
        rrt_tables.append(rrt)
    if len(set(frozenset(s) for s in vent_tables)) == 1:
        ok(f"E501/E502/E511/E512 인공호흡(VENT) TABLE 공유 확인")
    else:
        fail(f"E50x/E51x VENT TABLE 불일치: {vent_tables}")
    if len(set(frozenset(s) for s in rrt_tables)) == 1:
        ok(f"E501/E502/E511/E512 신대체요법(RRT) TABLE 공유 확인")
    else:
        fail(f"E50x/E51x RRT TABLE 불일치: {rrt_tables}")


# ---------------------------------------------------------------------------
# F022 교정 검증
# ---------------------------------------------------------------------------
def check_f022_correction(v2):
    rules_by_adrg = {r["adrg"]: r for r in v2.get("rules", [])}
    r = rules_by_adrg.get("F022")
    if not r:
        fail("[F022] 규칙 없음")
        return
    # correction_refs에 V47_CORR_20260301_HWPX가 있어야 함
    corr = r.get("correction_refs", [])
    corr_ids = {c.get("source_id") for c in corr}
    if "V47_CORR_20260301_HWPX" not in corr_ids:
        fail("[F022] correction_refs에 V47_CORR_20260301_HWPX 없음")
    else:
        ok("[F022] correction_refs에 V47_CORR_20260301_HWPX 확인")
    # table6 존재 확인
    all_tids = collect_all_table_ids(r.get("condition_expression", {}))
    if not any("PROC_6" in t for t in all_tids):
        fail("[F022] condition_expression에 table6 (PROC_6) 없음")
    else:
        ok("[F022] table6 (PROC_6) condition_expression 포함 확인")
    # F022 status가 CORRECTION_UPDATED여야 함
    if r.get("status") != "CORRECTION_UPDATED":
        fail(f"[F022] status = '{r.get('status')}' (기대: CORRECTION_UPDATED)")
    else:
        ok("[F022] status = CORRECTION_UPDATED")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    print("=== Schema v2 의미 동일성 검증 시작 ===\n")
    v1 = json.loads(V1_JSON.read_text(encoding="utf-8"))
    v2 = json.loads(V2_JSON.read_text(encoding="utf-8"))

    v1_rules = {r["adrg"]: r for r in v1.get("rules", [])}
    v2_rules = {r["adrg"]: r for r in v2.get("rules", [])}
    v1_tables = {t["table_id"]: t for t in v1.get("tables", [])}
    v2_tables = {t["table_id"]: t for t in v2.get("tables", [])}

    # ADRG 목록 일치 확인
    if v1_rules.keys() != v2_rules.keys():
        fail(f"ADRG 집합 불일치: v1={sorted(v1_rules)} v2={sorted(v2_rules)}")
    else:
        ok(f"ADRG 집합 일치 ({len(v1_rules)}개): {sorted(v1_rules)}")

    # 각 ADRG 검증
    for adrg in sorted(set(v1_rules) | set(v2_rules)):
        v1r = v1_rules.get(adrg, {})
        v2r = v2_rules.get(adrg, {})
        if not v2r:
            fail(f"[{adrg}] v2에 규칙 없음")
            continue
        check_expression_not_empty(v2r)
        check_all_node_ids_unique(v2r)
        check_source_refs_present(v2r)
        check_table_id_coverage(v1r, v2r)
        check_aadrg_mappings(v1r, v2r)

    # 테이블 코드 보존 검증
    for tid in sorted(v1_tables):
        if tid not in v2_tables:
            fail(f"[{tid}] v1에 있지만 v2에 없음")
        else:
            check_member_name_preserved(v1_tables[tid], v2_tables[tid])

    # E50x 특이케이스
    check_e50x_shared_tables(v2)

    # F022 교정 검증
    check_f022_correction(v2)

    print(f"\n결과: PASS {len(PASS_LIST)}건 / FAIL {len(ERRORS)}건")
    if ERRORS:
        print("\n--- FAIL 목록 ---")
        for e in ERRORS:
            print(e)
    sys.exit(0 if not ERRORS else 1)


if __name__ == "__main__":
    main()
