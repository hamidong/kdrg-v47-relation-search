# -*- coding: utf-8 -*-
"""UI v0.2 구조 검증 테스트.

폰트 정책
- Windows 또는 KDRG_REQUIRE_KOREAN_FONT=1에서는 한글 폰트 미지원이 FAIL입니다.
- Replit/Linux offscreen에서는 폰트 항목만 WARN으로 기록하고 구조 검증은 계속합니다.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_LOGGING_RULES", "qt.text.font.db=false")
os.environ["KDRG_PREVIEW_MODE"] = "1"
os.environ["KDRG_DISABLE_SETTINGS"] = "1"

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.font_utils import configure_application_font  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)
font_selection = configure_application_font(app, point_size=10)

from app.data_store import KDRGDataStore  # noqa: E402
from app.dialogs import AboutDialog  # noqa: E402
from app.main_window import CodeTableFrame, MainWindow  # noqa: E402
from app.styles import MAIN_STYLE_SHEET  # noqa: E402
from version import APP_VERSION  # noqa: E402

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"
results: list[tuple[str, str, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((PASS if condition else FAIL, name, detail))


def warn(name: str, detail: str = "") -> None:
    results.append((WARN, name, detail))


def settle(rounds: int = 4) -> None:
    for _ in range(rounds):
        app.processEvents()


def korean_font_is_required() -> bool:
    return (
        os.environ.get("KDRG_REQUIRE_KOREAN_FONT") == "1"
        or sys.platform.startswith("win")
    )


print("=" * 60)
print("UI v0.2 구조 검증 테스트")
print("=" * 60)

win = None
ctf = None
ctf2 = None
dlg = None

try:
    win = MainWindow()
    win.show()
    settle()

    check("T01 창 제목 버전 포함", APP_VERSION in win.windowTitle(), win.windowTitle())
    check("T02 창 기본 너비≥1700", win.width() >= 1700, f"width={win.width()}")

    ver_lbl = win.findChild(object, "VersionLabel")
    check("T03 VersionLabel 존재", ver_lbl is not None)
    if ver_lbl is not None:
        check("T04 VersionLabel APP_VERSION", APP_VERSION in ver_lbl.text(), ver_lbl.text())

    check("T05 DataVersionLabel 존재", win.findChild(object, "DataVersionLabel") is not None)
    check("T06 DataScopeLabel 존재", win.findChild(object, "DataScopeLabel") is not None)
    check("T07 InfoButton 존재", win.findChild(object, "InfoButton") is not None)
    check("T08 SearchResetButton 존재", win.findChild(object, "SearchResetButton") is not None)

    check("T09 _result_cards 속성", hasattr(win, "_result_cards"), f"len={len(win._result_cards)}")
    check("T10 selected_card 속성", hasattr(win, "selected_card"))
    check(
        "T11 기본 선택 카드 강조",
        win.selected_card is not None and win.selected_card.objectName() == "ResultCardSelected",
        f"objectName={win.selected_card.objectName() if win.selected_card else 'None'}",
    )

    check("T12 상태표시줄", bool(win.statusBar().currentMessage()))
    check("T13 main_splitter", hasattr(win, "main_splitter"))

    store = KDRGDataStore()
    first_table = next(iter(store.tables.values()))

    ctf = CodeTableFrame(first_table, highlight_code="", parent=win)
    ctf.ensure_populated()
    headers = [
        ctf.table.horizontalHeaderItem(index).text()
        for index in range(ctf.table.columnCount())
    ]
    check("T14 CodeTableFrame 3열", ctf.table.columnCount() == 3)
    check("T15 CodeTableFrame 헤더", headers == ["코드", "한글명", "영문명"], str(headers))

    ctf2 = CodeTableFrame(first_table, parent=win)
    check("T16 생성 직후 미채움", not ctf2._populated)
    ctf2.ensure_populated()
    check("T17 ensure_populated 후 채움", ctf2._populated)
    check("T18 코드행 존재", ctf2.table.rowCount() > 0, f"rows={ctf2.table.rowCount()}")

    dlg = AboutDialog(parent=win, app_version=APP_VERSION, store=store)
    check("T19 AboutDialog 인스턴스화", dlg.parent() is win)

    check("T20 AdvancedCautionBanner", win.findChild(object, "AdvancedCautionBanner") is not None)
    check("T21 관계검색 기본 2행", len(win.advanced_rows) == 2)
    check("T22 전체 검색 결과 9건", len(win.current_results) == 9)

    check("T23 ExcludeRoleBadge 스타일", "#ExcludeRoleBadge" in MAIN_STYLE_SHEET)
    check("T24 ResultCardSelected 스타일", "#ResultCardSelected" in MAIN_STYLE_SHEET)
    check("T25 QStatusBar 스타일", "QStatusBar" in MAIN_STYLE_SHEET)

    if font_selection.supports_korean:
        check(
            "T26 한글 폰트 검증 보류(Electron 전환 후)",
            True,
            f"family={font_selection.family}",
        )
    elif korean_font_is_required():
        check(
            "T26 한글 폰트 검증 보류(Electron 전환 후)",
            False,
            f"family={font_selection.family}",
        )
    else:
        warn(
            "T26 한글 폰트 검증 보류(Electron 전환 후)",
            f"Replit 비차단 경고, family={font_selection.family}",
        )

    visible_top_levels = [widget for widget in app.topLevelWidgets() if widget.isVisible()]
    check(
        "T27 기본 화면 top-level 1개",
        visible_top_levels == [win],
        str([type(widget).__name__ for widget in visible_top_levels]),
    )

finally:
    for widget in (dlg, ctf, ctf2, win):
        if widget is not None:
            try:
                widget.close()
                widget.deleteLater()
            except RuntimeError:
                pass
    settle()

n_pass = sum(1 for status, _, _ in results if status == PASS)
n_warn = sum(1 for status, _, _ in results if status == WARN)
n_fail = sum(1 for status, _, _ in results if status == FAIL)

for status, name, detail in results:
    mark = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}[status]
    suffix = f"  ({detail})" if detail else ""
    print(f"  {mark} {name}{suffix}")

print()
print(
    f"결과: {n_pass} PASS / {n_warn} WARN / "
    f"{n_fail} FAIL / 총 {len(results)}개"
)
raise SystemExit(0 if n_fail == 0 else 1)
