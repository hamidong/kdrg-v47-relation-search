# -*- coding: utf-8 -*-
"""1700x960 UI 미리보기 PNG 생성 스크립트.

실행 (X 서버 없는 환경 포함)
    QT_QPA_PLATFORM=offscreen python tests/generate_ui_preview.py

한글 렌더링을 위해 Noto Sans CJK 폰트를 찾을 수 있으면 애플리케이션 폰트로 등록합니다.
Windows 배포본에서는 requirements와 무관하게 OS에 설치된 맑은 고딕이 사용됩니다.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUTPUT_PATH = ROOT / "reports" / "ui_preview_v47_initial.png"

CJK_FONT_CANDIDATES = [
    Path.home() / ".local/share/fonts/NotoSansCJK-VF.otf.ttc",
]


def main() -> int:
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication

    from app.main_window import MainWindow

    app = QApplication.instance() or QApplication([])

    for font_path in CJK_FONT_CANDIDATES:
        if font_path.exists():
            font_id = QFontDatabase.addApplicationFont(str(font_path))
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                font = QFont(families[0])
                font.setPointSize(10)
                app.setFont(font)
            break

    window = MainWindow()
    window.resize(1700, 960)
    window.show()
    app.processEvents()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    pixmap = window.grab()
    pixmap.save(str(OUTPUT_PATH))
    print(f"[완료] 미리보기 저장: {OUTPUT_PATH} ({pixmap.size().width()}x{pixmap.size().height()})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
