# -*- coding: utf-8 -*-
"""오프스크린 GUI 스모크 테스트.

실행 (X 서버 없는 환경 포함)
    QT_QPA_PLATFORM=offscreen python tests/smoke_test_ui.py

검증 항목
- MainWindow가 예외 없이 생성됨
- 초기 화면에 파일럿 9개 ADRG 결과가 노출됨
- 초기 상세화면이 E011로 선택되어 있음 (요구사항: 초기 화면은 E011 기본 선택)
- 검색 카테고리를 ADRG로 좁혀도 정상 동작
- 코드 검색(예: E0110) 시 상세화면이 표시됨
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def fail(message: str) -> None:
    print(f"[실패] {message}")
    sys.exit(1)


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from app.main_window import MainWindow

    app = QApplication.instance() or QApplication([])

    window = MainWindow()

    if window.result_count.text() != "9건":
        fail(f"초기 결과 수가 9건이 아닙니다: {window.result_count.text()}")

    if not window.selected_result or window.selected_result.key != "E011":
        fail(f"초기 선택 ADRG가 E011이 아닙니다: {window.selected_result}")

    if window.current_type_label.text() != "ADRG":
        fail(f"초기 상세화면 유형이 ADRG가 아닙니다: {window.current_type_label.text()}")

    window.search_edit.setText("E0110")
    window.category_combo.setCurrentText("전체")
    window.run_search()
    if not window.current_results:
        fail("E0110 코드 검색 결과가 없습니다.")

    window.category_combo.setCurrentText("ADRG")
    window.search_edit.setText("")
    window.run_search()
    if len(window.current_results) != 9:
        fail(f"ADRG 카테고리 전체 검색 결과가 9건이 아닙니다: {len(window.current_results)}건")

    print("[통과] MainWindow 생성, 초기 E011 선택, 코드/카테고리 검색 정상 동작 확인")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
