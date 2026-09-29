# -*- coding: utf-8 -*-
"""KDRG 검색기 v16 PySide GUI 핵심 동작 스모크 테스트."""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent
APP_PATH = BASE_DIR / "kdrg_relation_search_v16_mdc_advanced_search.py"


def load_app_module():
    spec = importlib.util.spec_from_file_location("kdrg_v16_app", APP_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("앱 모듈을 불러올 수 없습니다.")
    module = importlib.util.module_from_spec(spec)
    sys.modules["kdrg_v16_app"] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    module = load_app_module()
    app = QApplication.instance() or QApplication([])
    window = module.MainWindow()
    app.processEvents()

    checks: list[str] = []

    # MDC 정확검색
    assert len(window.current_results) == 1
    assert window.current_results[0].kind == "mdc" and window.current_results[0].key == "04"
    assert window.current_detail_kind == "mdc"
    checks.append("MDC 04 정확검색 및 MDC 상세")

    window.search_edit.setText("순환기계")
    window.category_combo.setCurrentText("전체")
    window.run_search()
    app.processEvents()
    assert len(window.current_results) == 1
    assert window.current_results[0].kind == "mdc" and window.current_results[0].key == "05"
    checks.append("순환기계 별칭 검색")

    # MDC 상세 → ADRG 상세 → 뒤로가기
    window.select_result(window.current_results[0])
    window.open_rule_detail("F600")
    app.processEvents()
    assert window.current_detail_kind == "rule"
    assert window.detail_history[-1]["kind"] == "mdc"
    window.go_back()
    app.processEvents()
    assert window.current_detail_kind == "mdc" and window.current_detail_key == "05"
    checks.append("MDC→ADRG→뒤로가기")

    # E011 분산 OR 조건
    window.advanced_rows[0].type_combo.setCurrentText("수술·처치코드")
    window.advanced_rows[0].code_edit.setText("O1311")
    window.advanced_rows[1].type_combo.setCurrentText("수술·처치코드")
    window.advanced_rows[1].code_edit.setText("O1326")
    window.relation_operator_combo.setCurrentText("AND")
    window.run_relation_search()
    app.processEvents()
    assert window.relation_candidates["E011"].relation_level == "split"
    assert window.current_detail_kind == "relation"
    checks.append("E011 서로 다른 OR 조건식 분산 경고")

    # 관계검색 → ADRG 상세 → 뒤로가기
    window.open_rule_detail("E011")
    app.processEvents()
    assert window.detail_history[-1]["kind"] == "relation"
    window.go_back()
    app.processEvents()
    assert window.current_detail_kind == "relation"
    checks.append("관계검색→ADRG→뒤로가기")

    # F600 주진단/기타진단 조합
    window.reset_advanced_conditions()
    window.advanced_rows[0].type_combo.setCurrentText("상병코드")
    window.advanced_rows[0].code_edit.setText("I210")
    window.advanced_rows[1].type_combo.setCurrentText("기타진단코드")
    window.advanced_rows[1].code_edit.setText("I110")
    window.run_relation_search()
    app.processEvents()
    assert window.relation_candidates["F600"].relation_level == "strict"
    checks.append("F600 주진단+기타진단 동일 조건식 연결")

    print("KDRG v16 GUI 스모크 테스트 PASS")
    for check in checks:
        print(f"- {check}")

    window.close()
    app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
