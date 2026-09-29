# -*- coding: utf-8 -*-
"""UI v0.2 추가 미리보기 5종 생성기.

실행
    QT_QPA_PLATFORM=offscreen python tests/generate_extra_previews.py

생성
- reports/ui_v02_fixed_02_relation_panel.png
- reports/ui_v02_fixed_03_relation_split_result.png
- reports/ui_v02_fixed_04_table_expanded.png
- reports/ui_v02_fixed_05_about_dialog.png
- reports/ui_v02_fixed_06_small_window.png
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["KDRG_PREVIEW_MODE"] = "1"
os.environ["KDRG_DISABLE_SETTINGS"] = "1"

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPORTS_DIR = ROOT / "reports"


def _settle(app, rounds: int = 4) -> None:
    for _ in range(rounds):
        app.processEvents()


def _close_existing_top_levels(app) -> None:
    for widget in list(app.topLevelWidgets()):
        try:
            widget.close()
            widget.deleteLater()
        except RuntimeError:
            pass
    _settle(app)


def _visible_top_levels(app):
    return [widget for widget in app.topLevelWidgets() if widget.isVisible()]


def _assert_top_levels(app, allowed) -> None:
    allowed_ids = {id(widget) for widget in allowed}
    unexpected = [
        widget
        for widget in _visible_top_levels(app)
        if id(widget) not in allowed_ids
    ]
    if unexpected:
        names = [f"{type(widget).__name__}:{widget.windowTitle()!r}" for widget in unexpected]
        raise SystemExit(f"[실패] 의도하지 않은 top-level window가 있습니다: {names}")


def _save_widget(widget, path: Path) -> None:
    pixmap = widget.grab()
    if not pixmap.save(str(path)):
        raise SystemExit(f"[실패] PNG 저장 실패: {path}")
    print(f"[완료] {path} ({pixmap.width()}x{pixmap.height()})")


def main() -> int:
    from PySide6.QtWidgets import QApplication, QToolButton

    from app.font_utils import configure_application_font

    app = QApplication.instance() or QApplication([])
    _close_existing_top_levels(app)

    selection = configure_application_font(app, point_size=10)
    if not selection.supports_korean:
        raise SystemExit(
            "[실패] 한글 글리프 지원 폰트를 찾지 못했습니다. "
            f"선택 family={selection.family!r}"
        )

    from app.dialogs import AboutDialog
    from app.main_window import MainWindow
    from version import APP_VERSION

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    window = MainWindow()
    window.resize(1700, 960)
    window.show()
    window.raise_()
    window.activateWindow()
    _settle(app)
    _assert_top_levels(app, [window])

    # 2. 복수 코드 관계검색 패널
    window.advanced_toggle.setChecked(True)
    window.relation_operator_combo.setCurrentText("AND")
    _settle(app)
    if not window.advanced_panel.isVisible():
        raise SystemExit("[실패] 복수 코드 관계검색 패널이 펼쳐지지 않았습니다.")
    _assert_top_levels(app, [window])
    _save_widget(window, REPORTS_DIR / "ui_v02_fixed_02_relation_panel.png")

    # 3. O1311 + O1326 AND 관계검색 분산 결과
    row1, row2 = window.advanced_rows[0], window.advanced_rows[1]
    row1.type_combo.setCurrentText("수술·처치코드")
    row1.code_edit.setText("O1311")
    row2.type_combo.setCurrentText("수술·처치코드")
    row2.code_edit.setText("O1326")
    window.relation_operator_combo.setCurrentText("AND")
    window.run_relation_search()
    _settle(app)

    candidate = window.relation_candidates.get("E011")
    if candidate is None:
        raise SystemExit("[실패] 관계검색 결과에 E011이 없습니다.")
    if candidate.relation_level != "split":
        raise SystemExit(f"[실패] E011 relation_level={candidate.relation_level!r}")
    if candidate.status_label != "서로 다른 OR 조건식에 분산":
        raise SystemExit(f"[실패] E011 상태 문구={candidate.status_label!r}")
    _assert_top_levels(app, [window])
    _save_widget(window, REPORTS_DIR / "ui_v02_fixed_03_relation_split_result.png")

    # 4. E011 TABLE 펼침
    window.advanced_toggle.setChecked(False)
    window.search_edit.clear()
    window.category_combo.setCurrentText("전체")
    window.run_search()
    e011 = next((result for result in window.current_results if result.key == "E011"), None)
    if e011 is None:
        raise SystemExit("[실패] E011을 찾지 못했습니다.")
    window.select_result(e011)
    _settle(app)

    table_pills = [
        button
        for button in window.detail_container.findChildren(QToolButton)
        if button.objectName() in {
            "TablePill",
            "TablePillHit",
            "ExcludeTablePill",
            "ExcludeTablePillHit",
        }
        and button.isCheckable()
    ]
    if not table_pills:
        raise SystemExit("[실패] E011 TABLE 버튼을 찾지 못했습니다.")

    # 화면이 과도하게 길어지지 않도록 첫 번째 TABLE만 펼칩니다.
    table_pills[0].setChecked(True)
    _settle(app)
    first_pos = table_pills[0].mapTo(
        window.detail_container,
        table_pills[0].rect().topLeft(),
    )
    window.detail_scroll.verticalScrollBar().setValue(max(0, first_pos.y() - 50))
    _settle(app)
    _assert_top_levels(app, [window])
    _save_widget(window, REPORTS_DIR / "ui_v02_fixed_04_table_expanded.png")

    # 5. AboutDialog
    dialog = AboutDialog(parent=window, app_version=APP_VERSION, store=window.store)
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    _settle(app)
    _assert_top_levels(app, [window, dialog])
    _save_widget(dialog, REPORTS_DIR / "ui_v02_fixed_05_about_dialog.png")
    dialog.close()
    dialog.deleteLater()
    _settle(app)
    _assert_top_levels(app, [window])

    # 6. 최소 창 크기
    window.resize(1180, 760)
    window.advanced_toggle.setChecked(False)
    window.detail_scroll.verticalScrollBar().setValue(0)
    _settle(app)
    _assert_top_levels(app, [window])
    _save_widget(window, REPORTS_DIR / "ui_v02_fixed_06_small_window.png")

    print(
        "[검증 완료] "
        f"font={selection.family!r}, "
        f"supports_korean={selection.supports_korean}, "
        f"visible_top_levels={len(_visible_top_levels(app))}"
    )

    window.close()
    window.deleteLater()
    _settle(app)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
