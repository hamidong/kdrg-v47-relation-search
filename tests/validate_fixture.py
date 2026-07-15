# -*- coding: utf-8 -*-
"""데이터 fixture(kdrg_v47_ui_fixture.json) 무결성 검증 스크립트.

실행
    python tests/validate_fixture.py

검증 항목
- meta에 KDRG V4.6 관련 금지 문구가 없는지 확인
- table_id 중복 없음, rule -> table_id 참조가 모두 존재
- 파일럿 9개 ADRG(E011/E501/E502/E511/E512/F022/F136/F194/F195)가 모두 존재
- A/B/C 질병군 코드가 sources/raw의 [별표 1] PDF 기준과 일치(사전 확인된 값 하드코딩 비교)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_PATH = ROOT / "data" / "kdrg_v47_ui_fixture.json"

FORBIDDEN_STRINGS = ["KDRG V4.6", "V4.6 호환", "V4.6 목록"]

EXPECTED_PILOT_ADRGS = ["E011", "E501", "E502", "E511", "E512", "F022", "F136", "F194", "F195"]

# [별표 1] 입원환자의 질병군별 질병의 종류(제3조제1항 관련)(상급종합병원의 지정 및 평가 규정) PDF에서
# 직접 확인한 AADRG -> A/B/C 소속(2026-07-15 확인).
EXPECTED_GROUP_CODE = {
    "E0110": "A",
    "E5010": "A",
    "E5020": "A",
    "E5110": "A",
    "E5120": "B",
    "F0220": "A",
    "F1360": "A",
    "F1940": "B",
    "F1950": "B",
}


def fail(message: str) -> None:
    print(f"[실패] {message}")
    sys.exit(1)


def main() -> int:
    if not FIXTURE_PATH.exists():
        fail(f"fixture 파일을 찾을 수 없습니다: {FIXTURE_PATH}")

    raw_text = FIXTURE_PATH.read_text(encoding="utf-8")
    for forbidden in FORBIDDEN_STRINGS:
        if forbidden in raw_text:
            fail(f"금지 문구 발견: '{forbidden}'")

    data = json.loads(raw_text)

    tables = data.get("tables", [])
    table_ids = [t["table_id"] for t in tables]
    if len(table_ids) != len(set(table_ids)):
        fail("중복된 table_id가 있습니다.")
    table_id_set = set(table_ids)

    rules = data.get("rules", [])
    found_adrgs = sorted(r["adrg"] for r in rules)
    missing = [a for a in EXPECTED_PILOT_ADRGS if a not in found_adrgs]
    if missing:
        fail(f"파일럿 ADRG가 누락되었습니다: {missing}")

    for rule in rules:
        adrg = rule["adrg"]
        for group in rule.get("condition_groups", []):
            for comp in [*group.get("components", []), *group.get("exclude_components", [])]:
                tid = comp.get("table_id")
                if tid not in table_id_set:
                    fail(f"{adrg} -> 존재하지 않는 table_id 참조: {tid}")
        for mapping in rule.get("aadrg_mappings", []):
            aadrg = mapping.get("aadrg")
            expected = EXPECTED_GROUP_CODE.get(aadrg)
            actual = mapping.get("group_code")
            if expected and expected != actual:
                fail(
                    f"{adrg}({aadrg}) 질병군 분류 불일치: fixture={actual}, "
                    f"[별표 1] PDF 확인값={expected}"
                )

    print(f"[통과] table {len(tables)}개, rule {len(rules)}개, ADRG 9개 파일럿 케이스 · A/B/C 분류 [별표 1] PDF 대비 일치 확인")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
