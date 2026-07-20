# -*- coding: utf-8 -*-
"""KDRG V4.7 코드 관계 검색기 - 실행 진입점.

실행
    pip install -r requirements.txt
    python main.py

이 도구는 KDRG 코드/ADRG/TABLE/MDC를 검색하고 복수 코드가 같은 ADRG·같은
조건식 안에서 구조적으로 연결되는지 보여줍니다. 최종 DRG/질병군 판정 도구가
아닙니다.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.font_utils import configure_application_font


def main() -> int:
    # Qt6는 DPI 대응이 기본 활성화되어 있으나, Windows 배율 반올림 정책을 명시합니다.
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("KDRG V4.7 코드 관계 검색기")
    app.setOrganizationName("KDRG")

    # 실제로 설치된 폰트만 선택합니다.
    selection = configure_application_font(app, point_size=10)
    print(
        "[KDRG FONT] "
        f"family={selection.family!r}, "
        f"supports_korean={selection.supports_korean}, "
        f"registered_files={len(selection.registered_files)}"
    )

    # QApplication 전역 폰트를 적용한 뒤 UI 모듈을 불러옵니다.
    from app.main_window import MainWindow

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ImportError as exc:
        print("PySide6가 설치되어 있지 않습니다. 먼저 'pip install -r requirements.txt'를 실행하세요.")
        print(exc)
        raise
