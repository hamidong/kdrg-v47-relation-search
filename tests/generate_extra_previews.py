# -*- coding: utf-8 -*-
"""추가 UI 캡처 4종 생성 스크립트 (앱 코드/데이터/스타일은 변경하지 않음).

실행 (X 서버 없는 환경 포함)
    QT_QPA_PLATFORM=offscreen python tests/generate_extra_previews.py

생성 파일
- reports/ui_preview_v47_default.png        기본 화면(E011 선택)
- reports/ui_preview_v47_relation_panel.png  복수 코드 관계검색 패널 펼침
- reports/ui_preview_v47_relation_result.png O1311/O1326 AND 관계검색 결과(E011 분산)
- reports/ui_preview_v47_table_expanded.png  E011 table1/table2 전체 코드 펼침
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REPORTS_DIR = ROOT / "reports"

CJK_FONT_CANDIDATES = [
    Path.home() / ".local/share/fonts/NotoSansCJK-VF.otf.ttc",
]


def _load_cjk_font(app) -> None:
    from PySide6.QtGui import QFont, QFontDatabase

    for font_path in CJK_FONT_CANDIDATES:
        if font_path.exists():
            font_id = QFontDatabase.addApplicationFont(str(font_path))
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                font = QFont(families[0])
                font.setPointSize(10)
                app.setFont(font)
            return


def main() -> int:
    from PySide6.QtWidgets import QApplication, QToolButton

    from app.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    _load_cjk_font(app)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 1. 기본 화면 (E011 선택 상태) - ui_preview_v47_initial.png와 동일 조건
    # ------------------------------------------------------------------
    window = MainWindow()
    window.resize(1700, 960)
    window.show()
    app.processEvents()
    if window.result_count.text() != "9건":
        raise SystemExit(f"[실패] 기본 화면 결과 수가 9건이 아닙니다: {window.result_count.text()}")
    if not window.selected_result or window.selected_result.key != "E011":
        raise SystemExit(f"[실패] 기본 화면 선택 ADRG가 E011이 아닙니다: {window.selected_result}")
    pix1 = window.grab()
    out1 = REPORTS_DIR / "ui_preview_v47_default.png"
    pix1.save(str(out1))
    print(f"[완료] {out1} ({pix1.size().width()}x{pix1.size().height()})")

    # ------------------------------------------------------------------
    # 2. 복수 코드 관계검색 패널 펼침 (검색1/검색2 입력행, AND 선택)
    # ------------------------------------------------------------------
    window.advanced_toggle.setChecked(True)
    if len(window.advanced_rows) < 2:
        raise SystemExit(f"[실패] 관계검색 입력행이 2개 미만입니다: {len(window.advanced_rows)}")
    window.relation_operator_combo.setCurrentText("AND")
    app.processEvents()
    if not window.advanced_panel.isVisible():
        raise SystemExit("[실패] 복수 코드 관계검색 패널이 펼쳐지지 않았습니다.")
    pix2 = window.grab()
    out2 = REPORTS_DIR / "ui_preview_v47_relation_panel.png"
    pix2.save(str(out2))
    print(f"[완료] {out2} ({pix2.size().width()}x{pix2.size().height()})")

    # ------------------------------------------------------------------
    # 3. 관계검색 결과: 검색1=O1311(수술·처치코드), 검색2=O1326(수술·처치코드), AND
    # ------------------------------------------------------------------
    row1, row2 = window.advanced_rows[0], window.advanced_rows[1]
    row1.type_combo.setCurrentText("수술·처치코드")
    row1.code_edit.setText("O1311")
    row2.type_combo.setCurrentText("수술·처치코드")
    row2.code_edit.setText("O1326")
    window.relation_operator_combo.setCurrentText("AND")
    app.processEvents()
    window.run_relation_search()
    app.processEvents()

    candidate = window.relation_candidates.get("E011")
    if candidate is None:
        raise SystemExit("[실패] 관계검색 결과에 E011이 없습니다.")
    if candidate.relation_level != "split":
        raise SystemExit(f"[실패] E011의 relation_level이 split이 아닙니다: {candidate.relation_level}")
    if window.selected_result is None or window.selected_result.key != "E011":
        for result in window.current_results:
            if result.key == "E011":
                window.select_result(result)
                app.processEvents()
                break
    if "분산" not in window.selected_result.sublabel if window.selected_result else True:
        # sublabel에 상태 문구가 포함되는지 재확인 (RelationCandidate.status_label 참조)
        pass
    status_text = candidate.status_label
    if status_text != "서로 다른 OR 조건식에 분산":
        raise SystemExit(f"[실패] 예상한 상태 문구가 아닙니다: {status_text}")
    pix3 = window.grab()
    out3 = REPORTS_DIR / "ui_preview_v47_relation_result.png"
    pix3.save(str(out3))
    print(f"[완료] {out3} ({pix3.size().width()}x{pix3.size().height()}) - E011 상태: {status_text}")

    # ------------------------------------------------------------------
    # 4. E011 상세: table1/table2 전체 코드 펼침
    # ------------------------------------------------------------------
    window.advanced_toggle.setChecked(False)
    window.search_edit.setText("")
    window.category_combo.setCurrentText("전체")
    window.run_search()
    e011 = next((r for r in window.current_results if r.key == "E011"), None)
    if e011 is None:
        raise SystemExit("[실패] 검색 결과에서 E011을 찾지 못했습니다.")
    window.select_result(e011)
    app.processEvents()

    table_pills = [
        btn
        for btn in window.detail_container.findChildren(QToolButton)
        if btn.objectName() in ("TablePill", "TablePillHit") and btn.isCheckable()
    ]
    if len(table_pills) < 2:
        raise SystemExit(f"[실패] E011 상세에서 table 버튼을 2개 이상 찾지 못했습니다: {len(table_pills)}개")
    for pill in table_pills:
        pill.setChecked(True)
    app.processEvents()

    for pill in table_pills:
        if not pill.isChecked():
            raise SystemExit("[실패] table 버튼이 펼침 상태로 전환되지 않았습니다.")

    # 펼쳐진 코드표가 스크린샷 안에 보이도록 첫 번째 table 버튼 위치로 스크롤합니다.
    app.processEvents()
    first_pill_pos = table_pills[0].mapTo(window.detail_container, table_pills[0].rect().topLeft())
    window.detail_scroll.verticalScrollBar().setValue(max(0, first_pill_pos.y() - 40))
    app.processEvents()

    pix4 = window.grab()
    out4 = REPORTS_DIR / "ui_preview_v47_table_expanded.png"
    pix4.save(str(out4))
    print(f"[완료] {out4} ({pix4.size().width()}x{pix4.size().height()}) - 펼친 table 버튼 수: {len(table_pills)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
