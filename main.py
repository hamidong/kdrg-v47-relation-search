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

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from app.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("KDRG 코드 관계 검색기")

    font = QFont("Malgun Gothic")
    font.setPointSize(10)
    app.setFont(font)

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
