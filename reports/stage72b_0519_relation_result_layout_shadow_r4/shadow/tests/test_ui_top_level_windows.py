# -*- coding: utf-8 -*-
"""의도하지 않은 독립 top-level widget이 생기지 않는지 검증합니다."""

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


def _settle(app, rounds: int = 4) -> None:
    for _ in range(rounds):
        app.processEvents()


def _visible(app):
    return [widget for widget in app.topLevelWidgets() if widget.isVisible()]


def _describe(widgets):
    return [f"{type(widget).__name__}:{widget.windowTitle()!r}" for widget in widgets]


def main() -> int:
    from PySide6.QtWidgets import QApplication, QToolButton

    from app.font_utils import configure_application_font

    app = QApplication.instance() or QApplication([])
    configure_application_font(app)

    from app.dialogs import AboutDialog
    from app.main_window import MainWindow
    from version import APP_VERSION

    window = MainWindow()
    window.show()
    _settle(app)

    visible = _visible(app)
    if visible != [window]:
        print(f"[FAIL] 기본 화면 top-level: {_describe(visible)}")
        return 1

    # TABLE 펼침 후에도 MainWindow만 top-level이어야 합니다.
    table_pills = [
        button
        for button in window.detail_container.findChildren(QToolButton)
        if button.isCheckable()
        and button.objectName() in {
            "TablePill",
            "TablePillHit",
            "ExcludeTablePill",
            "ExcludeTablePillHit",
        }
    ]
    if not table_pills:
        print("[FAIL] TABLE 버튼을 찾지 못했습니다.")
        return 1
    table_pills[0].setChecked(True)
    _settle(app)

    visible = _visible(app)
    if visible != [window]:
        print(f"[FAIL] TABLE 펼침 후 top-level: {_describe(visible)}")
        return 1

    # AboutDialog만 예외적으로 두 번째 top-level 창입니다.
    dialog = AboutDialog(parent=window, app_version=APP_VERSION, store=window.store)
    dialog.show()
    _settle(app)

    visible = _visible(app)
    if set(map(id, visible)) != {id(window), id(dialog)}:
        print(f"[FAIL] AboutDialog 표시 중 top-level: {_describe(visible)}")
        return 1

    dialog.close()
    dialog.deleteLater()
    _settle(app)

    visible = _visible(app)
    if visible != [window]:
        print(f"[FAIL] AboutDialog 종료 후 top-level: {_describe(visible)}")
        return 1

    print("[PASS] 의도하지 않은 top-level window 없음")
    window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
