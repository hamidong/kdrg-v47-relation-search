# -*- coding: utf-8 -*-
"""UI v0.2 기본 화면 미리보기 생성기.

실행
    QT_QPA_PLATFORM=offscreen python tests/generate_ui_preview.py

생성
- reports/ui_v02_fixed_01_default.png

검증
- 실제 설치된 한글 폰트 선택
- 한글 글리프 지원
- MainWindow 외 의도하지 않은 visible top-level window 없음
- QSettings 복원 비활성화로 캡처 상태 고정
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

OUTPUT_PATH = ROOT / "reports" / "ui_v02_fixed_01_default.png"


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


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from app.font_utils import configure_application_font

    app = QApplication.instance() or QApplication([])
    _close_existing_top_levels(app)

    selection = configure_application_font(app, point_size=10)
    if not selection.supports_korean:
        raise SystemExit(
            "[실패] 한글 글리프를 지원하는 폰트를 찾지 못했습니다. "
            "Linux에서는 fonts-noto-cjk 또는 NanumGothic 설치 상태를 확인하세요. "
            f"선택 family={selection.family!r}"
        )

    from app.main_window import MainWindow

    window = MainWindow()
    window.resize(1700, 960)
    window.show()
    window.raise_()
    window.activateWindow()
    _settle(app)

    visible = _visible_top_levels(app)
    unexpected = [widget for widget in visible if widget is not window]
    if unexpected:
        names = [f"{type(widget).__name__}:{widget.windowTitle()!r}" for widget in unexpected]
        raise SystemExit(f"[실패] 의도하지 않은 top-level window가 있습니다: {names}")

    if window.result_count.text() != "9건":
        raise SystemExit(f"[실패] 기본 결과 수가 9건이 아닙니다: {window.result_count.text()}")
    if not window.selected_result or window.selected_result.key != "E011":
        raise SystemExit(f"[실패] 기본 선택 ADRG가 E011이 아닙니다: {window.selected_result}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    pixmap = window.grab()
    if not pixmap.save(str(OUTPUT_PATH)):
        raise SystemExit(f"[실패] PNG 저장 실패: {OUTPUT_PATH}")

    print(
        "[완료] "
        f"{OUTPUT_PATH} "
        f"({pixmap.width()}x{pixmap.height()}) · "
        f"font={selection.family} · "
        f"top_levels={len(visible)}"
    )

    window.close()
    window.deleteLater()
    _settle(app)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
