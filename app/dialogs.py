"""KDRG V4.7 코드 관계 검색기 - 다이얼로그 모음."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class AboutDialog(QDialog):
    """프로그램 정보 및 사용 제한 안내 다이얼로그."""

    def __init__(self, parent=None, app_version: str = "", store=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("KDRG V4.7 코드 관계 검색기 — 정보")
        self.setMinimumWidth(560)
        self.setMaximumWidth(700)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 헤더
        header = QFrame()
        header.setObjectName("AboutHeader")
        header.setStyleSheet(
            "#AboutHeader { background: #173e68; border: none; }"
        )
        h_layout = QVBoxLayout(header)
        h_layout.setContentsMargins(24, 20, 24, 20)
        h_layout.setSpacing(4)

        title = QLabel("KDRG V4.7 코드 관계 검색기")
        title.setStyleSheet("color: white; font-size: 18px; font-weight: 900;")
        h_layout.addWidget(title)

        ver_row = QHBoxLayout()
        prog_ver = QLabel(f"프로그램 버전  v{app_version}")
        prog_ver.setStyleSheet("color: #d6e7fb; font-size: 13px;")
        ver_row.addWidget(prog_ver)
        ver_row.addStretch(1)
        h_layout.addLayout(ver_row)
        layout.addWidget(header)

        # 본문 (스크롤)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body_widget = QWidget()
        body_layout = QVBoxLayout(body_widget)
        body_layout.setContentsMargins(24, 20, 24, 16)
        body_layout.setSpacing(16)
        scroll.setWidget(body_widget)
        layout.addWidget(scroll, 1)

        # 정보 섹션들
        sections = []

        if store:
            sections.append(("데이터 정보", [
                ("데이터 버전", store.version),
                ("데이터 범위", store.data_scope),
                ("교정 반영 기준일", store.correction_basis),
                ("KDRG 기준", f"KDRG V4.7 분류집 원문"),
                ("A/B/C 공식 원천", store.abc_basis),
            ]))


            sections.append(("전체 runtime 데이터 범위", [
                ("ADRG", f"{len(store.rules):,}개"),
                ("AADRG", f"{sum(len(rule.aadrg_mappings) for rule in store.rules.values()):,}개"),
                ("TABLE", f"{len(store.tables):,}개"),
                ("검색 코드", f"{len(store.code_to_tables):,}개"),
                ("출처", store.source_note),
            ]))

        sections.append(("사용 제한", [
            ("기능", "코드·ADRG·TABLE·MDC 관계 조회 및 복수 코드의 조건구조 연결 확인"),
            ("제한", "최종 DRG 판정·조건 충족 확인·EMR 연동 기능이 아닙니다"),
            ("시간 조건", "96시간 이상/미만 등 시간 조건은 코드만으로 확정 불가"),
            ("OR 분산", "서로 다른 OR 조건식에 나뉜 코드는 하나의 조합조건이 아닙니다"),
            ("추가 조건", "연결 확인 후 남은 TABLE·추가조건은 반드시 별도 확인 필요"),
        ]))

        for section_title, rows in sections:
            body_layout.addWidget(self._build_section(section_title, rows))

        # 핵심 제한 경고
        warning = QFrame()
        warning.setStyleSheet(
            "background: #fff7ed; border: 1px solid #f0c070; border-radius: 8px;"
        )
        w_layout = QVBoxLayout(warning)
        w_layout.setContentsMargins(16, 14, 16, 14)
        w_label = QLabel(
            "이 프로그램은 코드 관계와 공식 조건구조 조회용이며\n"
            "최종 DRG 판정기가 아닙니다."
        )
        w_label.setStyleSheet("color: #7a3d00; font-size: 13px; font-weight: 900;")
        w_label.setAlignment(Qt.AlignCenter)
        w_layout.addWidget(w_label)
        body_layout.addWidget(warning)

        body_layout.addStretch(1)

        # 닫기 버튼
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.setStyleSheet(
            "QDialogButtonBox { margin: 0 24px 16px 24px; }"
            "QPushButton { background: #173e68; color: white; border: none; "
            "border-radius: 6px; padding: 8px 24px; font-weight: 800; }"
            "QPushButton:hover { background: #2669a9; }"
        )
        layout.addWidget(buttons)

    def _build_section(self, title: str, rows: list) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame { background: #f6f9fc; border: 1px solid #d4dee9; border-radius: 8px; }"
            "QLabel { border: none; background: transparent; }"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        title_label = QLabel(title)
        title_label.setStyleSheet("color: #0a2a4d; font-size: 13px; font-weight: 900;")
        layout.addWidget(title_label)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #d4dee9;")
        layout.addWidget(line)

        for key, value in rows:
            row = QHBoxLayout()
            row.setSpacing(12)
            k = QLabel(key)
            k.setStyleSheet("color: #58708a; font-weight: 700; min-width: 120px;")
            k.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            v = QLabel(value)
            v.setStyleSheet("color: #08264a; font-size: 12px;")
            v.setWordWrap(True)
            row.addWidget(k)
            row.addWidget(v, 1)
            layout.addLayout(row)

        return frame
