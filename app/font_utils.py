# -*- coding: utf-8 -*-
"""KDRG 검색기의 최소 폰트 설정 유틸리티.

현재 PySide6 UI는 Electron 전환 전 임시 실행환경입니다.
복잡한 Linux/Nix 폰트 탐색은 수행하지 않습니다.

- Windows: Malgun Gothic을 우선 적용합니다.
- 그 외 운영체제: Qt 시스템 기본 폰트를 그대로 사용합니다.
- 호출부(main.py 및 UI 테스트)와의 호환성을 유지합니다.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class FontSelection:
    family: str
    point_size: int
    supports_korean: bool
    registered_files: tuple[str, ...] = ()


def _font_supports_korean(font: QFont) -> bool:
    """현재 선택 폰트가 대표 한글 글리프를 포함하는지 확인합니다."""
    metrics = QFontMetrics(font)
    return all(metrics.inFontUcs4(ord(ch)) for ch in ("한", "글", "가", "힣"))


def configure_application_font(
    app: QApplication,
    point_size: int = 10,
) -> FontSelection:
    """운영체제 기본 폰트를 단순 적용하고 선택 결과를 반환합니다."""
    if sys.platform.startswith("win"):
        font = QFont("Malgun Gothic", point_size)
    else:
        font = app.font()
        font.setPointSize(point_size)

    app.setFont(font)

    family = app.font().family()
    supports_korean = _font_supports_korean(app.font())

    app.setProperty("kdrgSelectedFontFamily", family)
    app.setProperty("kdrgFontSupportsKorean", supports_korean)
    app.setProperty("kdrgRegisteredFontFiles", ())

    return FontSelection(
        family=family,
        point_size=point_size,
        supports_korean=supports_korean,
        registered_files=(),
    )
