"""KDRG V4.7 코드 관계 검색기 - 화면 컴포넌트 및 메인 윈도우 (v0.2)."""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Set, Tuple

from PySide6.QtCore import Qt, QSettings, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLayout,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.runtime_data_store import KDRGRuntimeDataStore as KDRGDataStore
from app.models import (
    AdvancedCondition,
    RelationCandidate,
    RuleDef,
    SearchResult,
    TableDef,
    badge_name_for_code_type,
    clear_layout,
    group_badge_name,
    normalize,
    rich_code_summary,
    shorten_codes,
)
from app.styles import MAIN_STYLE_SHEET
from version import APP_VERSION

# 코드유형 → 역할 배지 표시명 매핑
_CODE_TYPE_ROLE: Dict[str, str] = {
    "상병코드": "주진단",
    "기타진단코드": "기타진단",
    "수술·처치코드": "수술·처치",
    "검사·처치코드": "검사·처치",
    "부가코드": "부가코드",
}

# =============================================================================
# 4. 화면 컴포넌트
# =============================================================================


class ResultCard(QFrame):
    """왼쪽 결과 목록의 카드 한 장."""

    def __init__(self, result: SearchResult, on_click) -> None:
        super().__init__()
        self.result = result
        self.on_click = on_click
        self.setObjectName("ResultCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setFrameShape(QFrame.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(10)
        badge = QLabel(self.kind_label(result.kind))
        badge.setObjectName(self.kind_badge_name(result.kind))
        badge.setAlignment(Qt.AlignCenter)
        top.addWidget(badge)

        title = QLabel(result.label)
        title.setObjectName("ResultTitle")
        top.addWidget(title)
        top.addStretch(1)

        if result.kind in {"adrg", "aadrg", "relation_adrg"} and result.mdc:
            mdc_badge = QLabel(f"MDC {result.mdc}")
            mdc_badge.setObjectName("MDCBadge")
            mdc_badge.setAlignment(Qt.AlignCenter)
            top.addWidget(mdc_badge)

        if result.kind in {"adrg", "aadrg", "relation_adrg"} and result.group_code:
            group = QLabel(f"{result.group_code}군")
            group.setObjectName(group_badge_name(result.group_code, "result"))
            group.setAlignment(Qt.AlignCenter)
            group.setToolTip(f"{result.group_code}군 · {result.group_name}")
            top.addWidget(group)

        layout.addLayout(top)

        sub = QLabel(result.sublabel)
        sub.setObjectName("ResultSub")
        sub.setWordWrap(True)
        layout.addWidget(sub)

    @staticmethod
    def kind_label(kind: str) -> str:
        return {
            "procedure_code": "수술·처치코드",
            "test_code": "검사·처치코드",
            "supplement_code": "부가코드",
            "diagnosis_code": "상병코드",
            "secondary_diagnosis_code": "기타진단코드",
            "adrg": "ADRG",
            "aadrg": "AADRG",
            "table": "TABLE",
            "mdc": "MDC",
            "relation_adrg": "관계 ADRG",
        }.get(kind, kind)

    @staticmethod
    def kind_badge_name(kind: str) -> str:
        return {
            "procedure_code": "BadgeGreen",
            "test_code": "BadgeTeal",
            "supplement_code": "BadgeOrange",
            "diagnosis_code": "BadgeBlue",
            "secondary_diagnosis_code": "BadgeBlue",
            "adrg": "BadgePurple",
            "aadrg": "BadgePurple",
            "table": "BadgeGray",
            "mdc": "BadgeNavy",
            "relation_adrg": "BadgeRelation",
        }.get(kind, "BadgeGray")

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.on_click(self.result)
        super().mousePressEvent(event)


class CodeTableFrame(QFrame):
    """TABLE 버튼 클릭 시 펼쳐지는 상세 코드표 (코드·한글명·영문명 3열, 지연 채우기)."""

    def __init__(
        self,
        table_def: TableDef,
        highlight_code: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.table_def = table_def
        self.highlight_code = normalize(highlight_code)
        self._populated = False  # 지연 채우기: 펼칠 때만 행을 추가
        self.setObjectName("ExpandedTableFrame")
        self.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        title_row = QHBoxLayout()
        title = QLabel(f"전체 코드 · {table_def.display_label} · {table_def.count}개")
        title.setObjectName("ExpandedTitle")
        title_row.addWidget(title)
        title_row.addStretch(1)

        source = QLabel(table_def.source_page)
        source.setObjectName("SmallMuted")
        title_row.addWidget(source)
        layout.addLayout(title_row)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("현재 table 안에서 코드 또는 코드명을 검색")
        self.filter_edit.setObjectName("InnerSearch")
        self.filter_edit.textChanged.connect(self.apply_filter)
        layout.addWidget(self.filter_edit)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["코드", "한글명", "영문명"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setObjectName("CodeTable")
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        layout.addWidget(self.table)

    def ensure_populated(self) -> None:
        """처음 펼쳐질 때 한 번만 행을 채웁니다."""
        if not self._populated:
            self.populate_table()
            self._populated = True

    def populate_table(self) -> None:
        members = list(self.table_def.members)
        self.table.setRowCount(len(members))
        for row, member in enumerate(members):
            # display_name = "en / ko" 또는 "ko" 형식을 분리
            raw = member.display_name or ""
            if " / " in raw:
                parts = raw.split(" / ", 1)
                en_name, ko_name = parts[0].strip(), parts[1].strip()
            elif hasattr(member, "name_ko") and hasattr(member, "name_en"):
                ko_name = getattr(member, "name_ko", raw)
                en_name = getattr(member, "name_en", "")
            else:
                ko_name = raw
                en_name = ""

            code_item = QTableWidgetItem(member.code)
            ko_item = QTableWidgetItem(ko_name)
            en_item = QTableWidgetItem(en_name)

            is_hl = self.highlight_code and normalize(member.code) == self.highlight_code
            for item in (code_item, ko_item, en_item):
                if is_hl:
                    item.setData(Qt.UserRole, "highlight")
                    item.setBackground(Qt.GlobalColor.transparent)
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
            self.table.setItem(row, 0, code_item)
            self.table.setItem(row, 1, ko_item)
            self.table.setItem(row, 2, en_item)

        height = min(320, 42 + len(members) * 32)
        self.table.setMinimumHeight(height)
        self.table.setMaximumHeight(height)

    def apply_filter(self, text: str) -> None:
        q = normalize(text)
        for row in range(self.table.rowCount()):
            code = self.table.item(row, 0).text() if self.table.item(row, 0) else ""
            ko = self.table.item(row, 1).text() if self.table.item(row, 1) else ""
            en = self.table.item(row, 2).text() if self.table.item(row, 2) else ""
            visible = not q or q in normalize(code) or q in normalize(ko) or q in normalize(en)
            self.table.setRowHidden(row, not visible)


class AdvancedConditionRow(QFrame):
    CODE_TYPES = ["자동판별", "상병코드", "기타진단코드", "수술·처치코드", "검사·처치코드", "부가코드"]

    def __init__(self, index: int, remove_callback) -> None:
        super().__init__()
        self.remove_callback = remove_callback
        self.setObjectName("AdvancedConditionRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        self.index_label = QLabel(f"검색 {index}")
        self.index_label.setObjectName("AdvancedIndex")
        layout.addWidget(self.index_label)

        self.type_combo = QComboBox()
        self.type_combo.addItems(self.CODE_TYPES)
        self.type_combo.setObjectName("AdvancedTypeCombo")
        layout.addWidget(self.type_combo)

        self.code_edit = QLineEdit()
        self.code_edit.setPlaceholderText("정확한 코드 입력 · 예: O1311")
        self.code_edit.setClearButtonEnabled(True)
        self.code_edit.setObjectName("AdvancedCodeEdit")
        layout.addWidget(self.code_edit, 1)

        self.remove_button = QPushButton("삭제")
        self.remove_button.setObjectName("AdvancedRemoveButton")
        self.remove_button.clicked.connect(lambda: self.remove_callback(self))
        layout.addWidget(self.remove_button)

    def set_index(self, index: int) -> None:
        self.index_label.setText(f"검색 {index}")

    def condition(self) -> AdvancedCondition:
        return AdvancedCondition(self.type_combo.currentText(), self.code_edit.text().strip())


# =============================================================================
# 5. 메인 윈도우
# =============================================================================


class MainWindow(QMainWindow):
    """KDRG V4.7 코드 관계 검색기 메인 창 (v0.2)."""

    SETTINGS_ORG = "KDRG"
    SETTINGS_APP = "KDRGRelationSearch"

    def __init__(self) -> None:
        super().__init__()
        self.store = KDRGDataStore()
        self.current_query = ""
        self.current_results: List[SearchResult] = []
        self.selected_result: Optional[SearchResult] = None
        self.selected_card: Optional[ResultCard] = None   # 현재 선택된 결과 카드
        self._result_cards: List[ResultCard] = []          # 렌더링된 카드 목록
        self.advanced_rows: List[AdvancedConditionRow] = []
        self.relation_candidates: Dict[str, RelationCandidate] = {}
        self.relation_operator = "AND"
        self.detail_history: List[Dict[str, object]] = []
        self.current_detail_kind = ""
        self.current_detail_key = ""

        self.setWindowTitle(f"KDRG V4.7 코드 관계 검색기  v{APP_VERSION}")
        self.resize(1700, 960)
        self.setMinimumSize(1180, 760)

        self._build_ui()
        self._apply_style()
        self._setup_shortcuts()

        # 초기 화면: 전체 9개 파일럿 ADRG를 노출하고 E011을 기본 선택
        self.category_combo.setCurrentText("전체")
        self.search_edit.setText("")
        self.run_search()
        default_result = next((r for r in self.current_results if normalize(r.key) == "E011"), None)
        if default_result is not None:
            self.select_result(default_result)

        self._update_status_bar()
        self._restore_settings()  # 창 크기·위치·splitter 복원 (마지막에)

    # ------------------------------------------------------------------
    # UI 골격
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.setCentralWidget(root)

        root_layout.addWidget(self._build_header())

        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.setObjectName("MainSplitter")
        self.main_splitter.addWidget(self._build_left_panel())
        self.main_splitter.addWidget(self._build_right_panel())
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setSizes([380, 1320])
        root_layout.addWidget(self.main_splitter, 1)

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("Header")
        layout = QVBoxLayout(header)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(10)

        # ── 행 1: 프로그램명(좌) + 버전 정보(우) + 정보 버튼 ──
        title_row = QHBoxLayout()
        title_row.setSpacing(16)

        title_box = QVBoxLayout()
        title_box.setSpacing(3)
        title_lbl = QLabel("KDRG V4.7 코드 관계 검색기")
        title_lbl.setObjectName("HeaderTitle")
        subtitle_lbl = QLabel("코드·ADRG·TABLE·MDC 및 공식 조건구조 관계 조회")
        subtitle_lbl.setObjectName("HeaderSubtitle")
        title_box.addWidget(title_lbl)
        title_box.addWidget(subtitle_lbl)
        title_row.addLayout(title_box)
        title_row.addStretch(1)

        ver_box = QVBoxLayout()
        ver_box.setSpacing(2)
        ver_box.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        prog_ver = QLabel(f"프로그램 v{APP_VERSION}")
        prog_ver.setObjectName("VersionLabel")
        prog_ver.setAlignment(Qt.AlignRight)
        data_ver = QLabel(f"데이터 {self.store.version} · {self.store.correction_basis} 교정 반영")
        data_ver.setObjectName("DataVersionLabel")
        data_ver.setAlignment(Qt.AlignRight)
        scope_lbl = QLabel(self.store.data_scope)
        scope_lbl.setObjectName("DataScopeLabel")
        scope_lbl.setAlignment(Qt.AlignRight)
        ver_box.addWidget(prog_ver)
        ver_box.addWidget(data_ver)
        ver_box.addWidget(scope_lbl)
        title_row.addLayout(ver_box)

        info_btn = QPushButton("ℹ 정보")
        info_btn.setObjectName("InfoButton")
        info_btn.setToolTip("프로그램 정보 및 사용 제한 안내")
        info_btn.clicked.connect(self.open_about_dialog)
        title_row.addWidget(info_btn)
        layout.addLayout(title_row)

        # ── 행 2: 검색 ──
        search_row = QHBoxLayout()
        search_row.setSpacing(8)

        self.category_combo = QComboBox()
        self.category_combo.addItems(["전체", "상병코드", "기타진단코드", "수술·처치코드", "검사·처치코드", "부가코드", "ADRG", "RDRG", "MDC", "TABLE"])
        self.category_combo.setObjectName("SearchCombo")
        self.category_combo.currentTextChanged.connect(self.run_search)
        search_row.addWidget(self.category_combo)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("예: MDC 04, 9600, 96000, 960000, E011, A00.0, M6586, ADC2A, LT_9610_001")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.returnPressed.connect(self.run_search)
        self.search_edit.textChanged.connect(self._search_text_changed)
        self.search_edit.setObjectName("SearchEdit")
        search_row.addWidget(self.search_edit, 1)

        search_btn = QPushButton("검색")
        search_btn.setObjectName("SearchButton")
        search_btn.clicked.connect(self.run_search)
        search_row.addWidget(search_btn)

        reset_btn = QPushButton("초기화")
        reset_btn.setObjectName("SearchResetButton")
        reset_btn.setToolTip("검색어를 지우고 전체 목록을 표시합니다  (Esc)")
        reset_btn.clicked.connect(self._reset_search)
        search_row.addWidget(reset_btn)

        layout.addLayout(search_row)

        # ── 행 3: 복수 코드 관계검색 토글 ──
        self.advanced_toggle = QToolButton()
        self.advanced_toggle.setText("복수 코드 관계검색 펼치기")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setArrowType(Qt.RightArrow)
        self.advanced_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.advanced_toggle.setObjectName("AdvancedToggle")
        self.advanced_toggle.toggled.connect(self._toggle_advanced_panel)
        layout.addWidget(self.advanced_toggle, 0, Qt.AlignLeft)

        # ── 고급 패널 ──
        self.advanced_panel = QFrame()
        self.advanced_panel.setObjectName("AdvancedPanel")
        self.advanced_panel.setVisible(False)
        adv_layout = QVBoxLayout(self.advanced_panel)
        adv_layout.setContentsMargins(12, 10, 12, 10)
        adv_layout.setSpacing(8)

        # 안내 배너
        banner = QFrame()
        banner.setObjectName("AdvancedCautionBanner")
        banner_layout = QHBoxLayout(banner)
        banner_layout.setContentsMargins(12, 9, 12, 9)
        banner_layout.setSpacing(10)
        icon_lbl = QLabel("⚠")
        icon_lbl.setObjectName("CautionIcon")
        caution_lbl = QLabel(
            "입력코드가 같은 ADRG·같은 조건식에 연결되는지 확인하는 관계검색입니다. "
            "최종 조건 충족이나 DRG 판정을 의미하지 않으며 시간·연령 조건은 별도 확인이 필요합니다."
        )
        caution_lbl.setObjectName("AdvancedCaution")
        caution_lbl.setWordWrap(True)
        banner_layout.addWidget(icon_lbl)
        banner_layout.addWidget(caution_lbl, 1)
        adv_layout.addWidget(banner)

        self.advanced_rows_container = QWidget()
        self.advanced_rows_layout = QVBoxLayout(self.advanced_rows_container)
        self.advanced_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.advanced_rows_layout.setSpacing(6)
        adv_layout.addWidget(self.advanced_rows_container)

        controls = QHBoxLayout()
        self.relation_operator_combo = QComboBox()
        self.relation_operator_combo.addItems(["AND", "OR"])
        self.relation_operator_combo.setObjectName("RelationOperatorCombo")
        controls.addWidget(QLabel("조건 관계"))
        controls.addWidget(self.relation_operator_combo)

        add_btn = QPushButton("+ 조건 추가")
        add_btn.setObjectName("AdvancedAddButton")
        add_btn.clicked.connect(self.add_advanced_condition_row)
        controls.addWidget(add_btn)
        controls.addStretch(1)

        reset_adv_btn = QPushButton("초기화")
        reset_adv_btn.setObjectName("AdvancedResetButton")
        reset_adv_btn.clicked.connect(self.reset_advanced_conditions)
        controls.addWidget(reset_adv_btn)

        relation_btn = QPushButton("공통 관련 ADRG 검색")
        relation_btn.setObjectName("RelationSearchButton")
        relation_btn.clicked.connect(self.run_relation_search)
        controls.addWidget(relation_btn)
        adv_layout.addLayout(controls)
        layout.addWidget(self.advanced_panel)

        self.add_advanced_condition_row()
        self.add_advanced_condition_row()
        return header

    def _toggle_advanced_panel(self, checked: bool) -> None:
        self.advanced_panel.setVisible(checked)
        self.advanced_toggle.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
        self.advanced_toggle.setText("복수 코드 관계검색 접기" if checked else "복수 코드 관계검색 펼치기")

    def add_advanced_condition_row(self) -> None:
        if len(self.advanced_rows) >= 6:
            QMessageBox.information(self, "조건 추가", "복수 코드 관계검색은 최대 6개 조건까지 입력할 수 있습니다.")
            return
        row = AdvancedConditionRow(len(self.advanced_rows) + 1, self.remove_advanced_condition_row)
        self.advanced_rows.append(row)
        self.advanced_rows_layout.addWidget(row)
        self._refresh_advanced_row_state()

    def remove_advanced_condition_row(self, row: AdvancedConditionRow) -> None:
        if len(self.advanced_rows) <= 2:
            QMessageBox.information(self, "조건 삭제", "복수 코드 관계검색은 최소 2개의 입력칸을 유지합니다.")
            return
        self.advanced_rows.remove(row)
        row.setParent(None)
        row.deleteLater()
        self._refresh_advanced_row_state()

    def _refresh_advanced_row_state(self) -> None:
        for index, row in enumerate(self.advanced_rows, start=1):
            row.set_index(index)
            row.remove_button.setEnabled(len(self.advanced_rows) > 2)

    def reset_advanced_conditions(self) -> None:
        while len(self.advanced_rows) > 2:
            row = self.advanced_rows.pop()
            row.setParent(None)
            row.deleteLater()
        for row in self.advanced_rows:
            row.type_combo.setCurrentIndex(0)
            row.code_edit.clear()
        self.relation_operator_combo.setCurrentText("AND")
        self._refresh_advanced_row_state()

    def _build_left_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("LeftPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 14, 8, 12)
        layout.setSpacing(10)

        top = QHBoxLayout()
        title = QLabel("검색 결과")
        title.setObjectName("PanelTitle")
        top.addWidget(title)
        top.addStretch(1)
        self.result_count = QLabel("0건")
        self.result_count.setObjectName("CountLabel")
        top.addWidget(self.result_count)
        layout.addLayout(top)

        self.result_scroll = QScrollArea()
        self.result_scroll.setWidgetResizable(True)
        self.result_scroll.setObjectName("ResultScroll")
        self.result_container = QWidget()
        self.result_layout = QVBoxLayout(self.result_container)
        self.result_layout.setContentsMargins(4, 4, 4, 4)
        self.result_layout.setSpacing(10)
        self.result_layout.addStretch(1)
        self.result_scroll.setWidget(self.result_container)
        layout.addWidget(self.result_scroll, 1)

        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("RightPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setSpacing(10)

        top = QHBoxLayout()
        self.back_button = QPushButton("← 이전 화면")
        self.back_button.setObjectName("BackButton")
        self.back_button.setToolTip("ADRG 상세를 열기 전의 코드 또는 TABLE 상세 화면으로 돌아갑니다.")
        self.back_button.clicked.connect(self.go_back)
        self.back_button.setVisible(False)
        top.addWidget(self.back_button)

        title = QLabel("상세 정보")
        title.setObjectName("PanelTitle")
        top.addWidget(title)
        top.addStretch(1)
        self.current_type_label = QLabel("")
        self.current_type_label.setObjectName("CurrentType")
        top.addWidget(self.current_type_label)
        layout.addLayout(top)

        self.detail_scroll = QScrollArea()
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setObjectName("DetailScroll")
        self.detail_container = QWidget()
        self.detail_layout = QVBoxLayout(self.detail_container)
        self.detail_layout.setContentsMargins(0, 0, 0, 0)
        self.detail_layout.setSpacing(12)
        self.detail_layout.setSizeConstraint(QLayout.SetMinimumSize)
        self.detail_layout.addStretch(1)
        self.detail_scroll.setWidget(self.detail_container)
        layout.addWidget(self.detail_scroll, 1)

        return panel

    # ------------------------------------------------------------------
    # 단축키·상태바·설정
    # ------------------------------------------------------------------

    def _setup_shortcuts(self) -> None:
        """Ctrl+L(검색창 포커스), Esc(검색 초기화/포커스 이동)."""
        sc_focus = QShortcut(QKeySequence("Ctrl+L"), self)
        sc_focus.activated.connect(lambda: (self.search_edit.setFocus(), self.search_edit.selectAll()))
        sc_esc = QShortcut(QKeySequence("Escape"), self)
        sc_esc.activated.connect(self._handle_esc)

    def _handle_esc(self) -> None:
        if self.search_edit.hasFocus() and self.search_edit.text():
            self._reset_search()
        else:
            self.search_edit.setFocus()

    def _reset_search(self) -> None:
        """검색어를 초기화하고 전체 목록을 표시합니다."""
        self.search_edit.clear()
        self.category_combo.setCurrentText("전체")
        self.run_search()

    def _update_status_bar(self) -> None:
        n_adrg = len(self.store.rules)
        n_table = len(self.store.tables)
        scope = self.store.data_scope
        msg = (
            f"데이터 로드 완료  │  {scope}  │  "
            f"ADRG {n_adrg}개 · TABLE {n_table}개  │  "
            f"v{APP_VERSION}  │  "
            "이 프로그램은 코드 관계 조회용이며 최종 DRG 판정기가 아닙니다"
        )
        self.statusBar().showMessage(msg)

    def open_about_dialog(self) -> None:
        from app.dialogs import AboutDialog

        dlg = AboutDialog(parent=self, app_version=APP_VERSION, store=self.store)
        dlg.exec()

    @staticmethod
    def _settings_disabled() -> bool:
        """미리보기·자동검증에서는 이전 사용자 QSettings를 적용하지 않습니다."""
        value = os.environ.get("KDRG_DISABLE_SETTINGS", "")
        preview = os.environ.get("KDRG_PREVIEW_MODE", "")
        return value.strip().lower() in {"1", "true", "yes", "on"} or preview.strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    def _restore_settings(self) -> None:
        if self._settings_disabled():
            self.main_splitter.setSizes([380, 1320])
            self.advanced_toggle.setChecked(False)
            return

        settings = QSettings(self.SETTINGS_ORG, self.SETTINGS_APP)
        geom = settings.value("geometry")
        if geom is not None:
            self.restoreGeometry(geom)
        splitter_state = settings.value("splitter")
        if splitter_state is not None:
            self.main_splitter.restoreState(splitter_state)
        panel_open = settings.value("advancedPanelOpen", False, type=bool)
        if panel_open:
            self.advanced_toggle.setChecked(True)

    def closeEvent(self, event) -> None:  # noqa: N802
        if not self._settings_disabled():
            settings = QSettings(self.SETTINGS_ORG, self.SETTINGS_APP)
            settings.setValue("geometry", self.saveGeometry())
            settings.setValue("splitter", self.main_splitter.saveState())
            settings.setValue("advancedPanelOpen", self.advanced_toggle.isChecked())
            settings.sync()
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # 검색 및 렌더링
    # ------------------------------------------------------------------

    def _search_text_changed(self) -> None:
        pass  # 엔터/버튼 중심 검색 유지

    def run_search(self) -> None:
        self._clear_detail_history()
        self.current_query = self.search_edit.text().strip()
        category = self.category_combo.currentText()
        self.current_results = self.store.search(self.current_query, category)
        self._render_results()
        if self.current_results:
            self.select_result(self.current_results[0])
        else:
            self._render_empty_detail("검색 결과가 없습니다.")

    def run_relation_search(self) -> None:
        conditions = [row.condition() for row in self.advanced_rows if row.code_edit.text().strip()]
        if len(conditions) < 2:
            QMessageBox.information(self, "복수 코드 관계검색", "서로 다른 코드 조건을 2개 이상 입력하세요.")
            return

        seen: Set[Tuple[str, str]] = set()
        duplicates: List[str] = []
        for condition in conditions:
            key = (condition.code_type, normalize(condition.code))
            if key in seen:
                duplicates.append(condition.code)
            seen.add(key)
        if duplicates:
            QMessageBox.warning(self, "중복 입력", "동일한 코드·유형 조건이 중복 입력되었습니다: " + ", ".join(duplicates))
            return

        missing: List[str] = []
        for condition in conditions:
            if not self.store.exact_table_ids_for_code(condition.code, condition.code_type):
                missing.append(f"{condition.code} ({condition.code_type})")
        if missing:
            QMessageBox.warning(self, "코드 확인", "현재 데이터에서 정확히 찾지 못한 조건입니다:\n" + "\n".join(missing))
            return

        self._clear_detail_history()
        self.relation_operator = self.relation_operator_combo.currentText()
        candidates = self.store.relation_search(conditions, self.relation_operator)
        self.relation_candidates = {candidate.adrg: candidate for candidate in candidates}
        self.current_query = " / ".join(condition.code for condition in conditions)
        self.current_results = []
        for candidate in candidates:
            rule = self.store.rules[candidate.adrg]
            code_text = ", ".join(condition.code for condition in conditions)
            sublabel = f"{candidate.status_label} · {candidate.matched_count}/{candidate.total_count}개 입력 연결 · {code_text}"
            self.current_results.append(SearchResult("relation_adrg", rule.adrg, rule.adrg, sublabel, 0, rule.group_code, rule.group_name, rule.mdc))
        self._render_results()
        if self.current_results:
            self.select_result(self.current_results[0])
        else:
            self.current_type_label.setText("복수 코드 관계검색")
            self._render_empty_detail("입력한 코드 조건과 연결되는 ADRG가 없습니다.")

    def _render_results(self) -> None:
        clear_layout(self.result_layout)
        self.selected_card = None
        self._result_cards = []
        self.result_count.setText(f"{len(self.current_results)}건")

        if not self.current_results:
            empty = QLabel("직접 일치하는 항목이 없습니다.")
            empty.setObjectName("EmptyText")
            empty.setAlignment(Qt.AlignCenter)
            self.result_layout.addWidget(empty)
            self.result_layout.addStretch(1)
            return

        for result in self.current_results:
            card = ResultCard(result, self.select_result)
            self._result_cards.append(card)
            self.result_layout.addWidget(card)
        self.result_layout.addStretch(1)

    def select_result(self, result: SearchResult) -> None:
        # 이전 선택 카드의 강조 해제
        if self.selected_card is not None:
            self.selected_card.setObjectName("ResultCard")
            self.selected_card.style().unpolish(self.selected_card)
            self.selected_card.style().polish(self.selected_card)
            self.selected_card = None

        # 새 선택 카드 강조
        for card in self._result_cards:
            if card.result is result:
                card.setObjectName("ResultCardSelected")
                card.style().unpolish(card)
                card.style().polish(card)
                self.selected_card = card
                break

        self._clear_detail_history()
        self.selected_result = result
        if result.kind in {"diagnosis_code", "secondary_diagnosis_code", "procedure_code", "test_code", "supplement_code"}:
            self.current_type_label.setText(ResultCard.kind_label(result.kind))
            self.render_code_detail(result.key)
        elif result.kind in {"adrg", "aadrg"}:
            self.current_type_label.setText(ResultCard.kind_label(result.kind))
            self.render_rule_detail(result.key)
        elif result.kind == "mdc":
            self.current_type_label.setText("MDC")
            self.render_mdc_detail(result.key)
        elif result.kind == "relation_adrg":
            self.current_type_label.setText("복수 코드 관계검색")
            self.render_relation_detail(result.key)
        elif result.kind == "table":
            self.current_type_label.setText("TABLE")
            self.render_table_detail(result.key)
        else:
            self._render_empty_detail("상세 정보를 표시할 수 없습니다.")

    # ------------------------------------------------------------------
    # 상세화면 탐색 이력
    # ------------------------------------------------------------------

    def _clear_detail_history(self) -> None:
        self.detail_history.clear()
        self._update_back_button()

    def _push_current_detail(self) -> None:
        if not self.current_detail_kind or not self.current_detail_key:
            return
        self.detail_history.append(
            {
                "kind": self.current_detail_kind,
                "key": self.current_detail_key,
                "type_label": self.current_type_label.text(),
                "scroll_value": self.detail_scroll.verticalScrollBar().value(),
            }
        )
        self._update_back_button()

    def _set_current_detail(self, kind: str, key: str) -> None:
        self.current_detail_kind = kind
        self.current_detail_key = key

    def _update_back_button(self) -> None:
        if not hasattr(self, "back_button"):
            return
        has_history = bool(self.detail_history)
        self.back_button.setVisible(has_history)
        if not has_history:
            self.back_button.setText("← 이전 화면")
            return

        previous = self.detail_history[-1]
        key = str(previous.get("key", "")).strip()
        kind = str(previous.get("kind", ""))
        if kind == "code" and key:
            self.back_button.setText(f"← {key} 검색 결과")
        elif kind == "table" and key:
            self.back_button.setText(f"← {key} TABLE")
        elif kind == "mdc" and key:
            self.back_button.setText(f"← MDC {key}")
        elif kind == "relation" and key:
            self.back_button.setText("← 복수 코드 관계검색 결과")
        elif key:
            self.back_button.setText(f"← {key} 상세")
        else:
            self.back_button.setText("← 이전 화면")

    def open_rule_detail(self, adrg: str) -> None:
        if self.current_detail_kind == "rule" and normalize(self.current_detail_key) == normalize(adrg):
            return
        self._push_current_detail()
        self.current_type_label.setText("ADRG")
        self.render_rule_detail(adrg)
        self.detail_scroll.verticalScrollBar().setValue(0)

    def go_back(self) -> None:
        if not self.detail_history:
            return

        previous = self.detail_history.pop()
        kind = str(previous.get("kind", ""))
        key = str(previous.get("key", ""))
        type_label = str(previous.get("type_label", ""))
        scroll_value = int(previous.get("scroll_value", 0) or 0)

        self.current_type_label.setText(type_label)
        if kind == "code":
            self.render_code_detail(key)
        elif kind == "rule":
            self.render_rule_detail(key)
        elif kind == "table":
            self.render_table_detail(key)
        elif kind == "mdc":
            self.render_mdc_detail(key)
        elif kind == "relation":
            self.render_relation_detail(key)
        else:
            self._render_empty_detail("이전 상세 화면을 복원할 수 없습니다.")

        self._update_back_button()
        QTimer.singleShot(0, lambda value=scroll_value: self.detail_scroll.verticalScrollBar().setValue(value))

    def _reset_detail_layout(self) -> None:
        clear_layout(self.detail_layout)

    def _render_empty_detail(self, message: str) -> None:
        self._reset_detail_layout()
        box = self._simple_card()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(20, 20, 20, 20)
        label = QLabel(message)
        label.setObjectName("EmptyText")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        self.detail_layout.addWidget(box)
        self.detail_layout.addStretch(1)

    # ------------------------------------------------------------------
    # 상세: 코드
    # ------------------------------------------------------------------

    def render_code_detail(self, code: str) -> None:
        self._set_current_detail("code", code)
        self._reset_detail_layout()
        member = self.store.member_for_code(code)
        tables = self.store.tables_for_code(code)
        related_rules = self.store.rules_for_code(code)
        exclusion_rules = self.store.exclusion_rules_for_code(code)
        exclusion_tables = self.store.exclusion_tables_for_code(code)

        if not member:
            self._render_empty_detail("코드 상세 정보를 찾을 수 없습니다.")
            return

        code_types = list(dict.fromkeys(t.code_type for t in tables))
        code_type = " / ".join(code_types) if code_types else "코드"
        primary_code_type = code_types[0] if code_types else ""
        exclusion_ids = {t.table_id for t in exclusion_tables}
        relation_summary = self.store.relation_summary_for_code(code)
        table_text = ", ".join(
            f"{t.table_id} · {t.display_label}" + (" [미포함 조건]" if t.table_id in exclusion_ids else "")
            for t in tables
        ) or "-"

        self.detail_layout.addWidget(
            self._build_primary_card(
                badge_text=code_type,
                badge_name=badge_name_for_code_type(primary_code_type),
                title=member.code,
                subtitle=member.display_name,
                rows=[
                    ("코드 유형", code_type),
                    ("포함 TABLE", table_text),
                    ("원문 TABLE 정의 ADRG", relation_summary.get("physical_source", "-")),
                    ("조건 AST 사용 ADRG", relation_summary.get("condition_usage", "-")),
                    ("검색용 관련 ADRG", relation_summary.get("runtime_related", "-")),
                    ("원문 family 근거", relation_summary.get("source_families", "-")),
                    ("KDRG 버전", self.store.version),
                    ("교정자료 기준일", self.store.correction_basis),
                ],
            )
        )

        self.detail_layout.addWidget(
            self._build_related_summary(
                title=f"관련 ADRG / 질병군 · {len(related_rules)}건",
                rules=related_rules,
                clickable=True,
            )
        )
        if exclusion_rules:
            self.detail_layout.addWidget(
                self._build_related_summary(
                    title=f"미포함·제외조건으로 연결된 ADRG · {len(exclusion_rules)}건",
                    rules=exclusion_rules,
                    clickable=True,
                )
            )

        tabs = QTabWidget()
        tabs.setObjectName("Tabs")
        tabs.addTab(self._scroll_wrap(self._build_rule_cards(related_rules, highlight_code=code)), "관련 ADRG")
        if exclusion_rules:
            tabs.addTab(self._scroll_wrap(self._build_rule_cards(exclusion_rules, highlight_code=code)), "미포함·제외조건")
        tabs.addTab(self._scroll_wrap(self._build_evidence_panel([*related_rules, *exclusion_rules])), "원문 근거")
        self.detail_layout.addWidget(tabs, 1)
        self.detail_layout.addStretch(1)

    # ------------------------------------------------------------------
    # 상세: ADRG
    # ------------------------------------------------------------------

    def render_rule_detail(self, adrg: str) -> None:
        self._set_current_detail("rule", adrg)
        self._reset_detail_layout()
        rule = self.store.rules.get(adrg)
        if not rule:
            self._render_empty_detail("ADRG 상세 정보를 찾을 수 없습니다.")
            return

        self.detail_layout.addWidget(
            self._build_primary_card(
                badge_text="ADRG",
                badge_name="BadgePurple",
                title=rule.adrg,
                subtitle=rule.title_full,
                rows=[
                    ("AADRG", rule.aadrg_display),
                    ("질병군 분류", rule.group_display),
                    ("MDC", rule.mdc),
                    ("조건 원문", rule.condition_text),
                    ("KDRG 버전", self.store.version),
                    ("교정자료 기준일", self.store.correction_basis),
                    ("질병군 분류 기준", self.store.abc_basis),
                ],
            )
        )

        self.detail_layout.addWidget(
            self._build_related_summary(
                title="관련 ADRG / 질병군 · 1건",
                rules=[rule],
                clickable=False,
            )
        )

        tabs = QTabWidget()
        tabs.setObjectName("Tabs")
        tabs.addTab(self._scroll_wrap(self._build_rule_cards([rule], highlight_code=self.current_query)), "관련 ADRG")
        tabs.addTab(self._scroll_wrap(self._build_evidence_panel([rule])), "원문 근거")
        self.detail_layout.addWidget(tabs, 1)
        self.detail_layout.addStretch(1)

    # ------------------------------------------------------------------
    # 상세: MDC
    # ------------------------------------------------------------------

    def render_mdc_detail(self, mdc_code: str) -> None:
        code = str(mdc_code).strip().zfill(2)
        self._set_current_detail("mdc", code)
        self._reset_detail_layout()
        mdc = self.store.mdcs.get(code)
        if not mdc:
            self._render_empty_detail("MDC 상세 정보를 찾을 수 없습니다.")
            return
        rules = self.store.rules_for_mdc(code)
        mappings = [mapping for rule in rules for mapping in rule.aadrg_mappings]
        group_counts = {group: sum(1 for m in mappings if m.group_code == group) for group in ("A", "B", "C")}
        self.detail_layout.addWidget(self._build_primary_card(
            badge_text="MDC", badge_name="BadgeNavy", title=f"MDC {code}", subtitle=mdc.name,
            rows=[
                ("포함 ADRG", f"{len(rules)}개"),
                ("포함 AADRG", f"{len(mappings)}개"),
                ("질병군 분포", f"A군 {group_counts['A']}개 · B군 {group_counts['B']}개 · C군 {group_counts['C']}개"),
                ("KDRG 버전", self.store.version),
            ],
        ))
        tabs = QTabWidget()
        tabs.setObjectName("Tabs")
        tabs.addTab(self._scroll_wrap(self._build_related_summary(f"MDC {code} 전체 ADRG · {len(rules)}건", rules, clickable=True)), "전체")
        for group_code, label in (("A", "A군"), ("B", "B군"), ("C", "C군")):
            grouped = [rule for rule in rules if any(m.group_code == group_code for m in rule.aadrg_mappings)]
            tabs.addTab(self._scroll_wrap(self._build_related_summary(f"{label} ADRG · {len(grouped)}건", grouped, clickable=True)), label)
        self.detail_layout.addWidget(tabs, 1)
        self.detail_layout.addStretch(1)

    # ------------------------------------------------------------------
    # 상세: 복수 코드 관계검색
    # ------------------------------------------------------------------

    def render_relation_detail(self, adrg: str) -> None:
        self._set_current_detail("relation", adrg)
        self._reset_detail_layout()
        candidate = self.relation_candidates.get(adrg)
        rule = self.store.rules.get(adrg)
        if not candidate or not rule:
            self._render_empty_detail("복수 코드 관계검색 상세를 찾을 수 없습니다.")
            return
        input_text = ", ".join(match.code for match in candidate.rule_matches)
        caution = {
            "strict": "입력코드가 적어도 하나의 동일 조건식 안에 모두 연결됩니다. 남은 table·추가조건은 별도 확인이 필요합니다.",
            "split": "모든 입력코드가 같은 ADRG에는 연결되지만 서로 다른 OR 조건식에 나뉘어 있습니다. 하나의 조합조건으로 해석하면 안 됩니다.",
            "partial": "OR 검색으로 입력코드 일부만 연결된 ADRG입니다.",
        }[candidate.relation_level]
        self.detail_layout.addWidget(self._build_primary_card(
            badge_text="관계검색", badge_name="BadgeRelation", title=rule.adrg, subtitle=rule.title_full,
            rows=[
                ("관계 상태", candidate.status_label),
                ("입력 조건", f"{self.relation_operator} · {input_text}"),
                ("연결 수", f"{candidate.matched_count}/{candidate.total_count}개 입력"),
                ("MDC", f"MDC {rule.mdc}"),
                ("AADRG", rule.aadrg_display),
                ("질병군 분류", rule.group_display),
                ("해석 주의", caution),
            ],
        ))
        self.detail_layout.addWidget(self._build_relation_analysis(candidate, rule))
        tabs = QTabWidget()
        tabs.setObjectName("Tabs")
        tabs.addTab(self._scroll_wrap(self._build_rule_cards([rule])), "ADRG 전체 조건")
        tabs.addTab(self._scroll_wrap(self._build_evidence_panel([rule])), "원문 근거")
        self.detail_layout.addWidget(tabs, 1)
        self.detail_layout.addStretch(1)

    def _build_relation_analysis(self, candidate: RelationCandidate, rule: RuleDef) -> QFrame:
        card = self._simple_card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        title = QLabel("입력코드와 조건식 연결 분석")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        for group_match in candidate.group_matches:
            group_def = next((g for g in rule.condition_groups if g.group_no == group_match.group_no), None)
            if group_def is None:
                continue
            box = QFrame()
            box.setObjectName("RelationGroupBoxStrict" if group_match.all_inputs_in_group else "RelationGroupBoxSplit")
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(12, 10, 12, 10)
            box_layout.setSpacing(7)
            header = QLabel(f"{group_match.group_label} · " + ("모든 입력 연결" if group_match.all_inputs_in_group else "일부 입력 연결"))
            header.setObjectName("RelationGroupTitle")
            box_layout.addWidget(header)

            matched_component_ids: Set[str] = set()
            table_to_codes: Dict[str, List[str]] = {}
            for match in group_match.matches:
                if not match.table_ids:
                    line = QLabel(f"{match.code} → 이 조건식에는 없음")
                    line.setObjectName("RelationMiss")
                    box_layout.addWidget(line)
                    continue
                labels = []
                for tid in match.table_ids:
                    matched_component_ids.add(tid)
                    table_to_codes.setdefault(tid, []).append(match.code)
                    labels.append(self.store.tables[tid].display_label)
                line = QLabel(f"{match.code} → " + ", ".join(labels))
                line.setObjectName("RelationHit")
                line.setWordWrap(True)
                box_layout.addWidget(line)

            remaining = [self.store.tables[c.table_id].display_label for c in group_def.components if c.table_id not in matched_component_ids]
            checks: List[str] = []
            if remaining:
                checks.append("미입력 TABLE: " + ", ".join(remaining))
            if group_def.exclude_components:
                checks.append("미포함·제외조건: " + ", ".join(self.store.tables[c.table_id].display_label for c in group_def.exclude_components))
            if group_def.requirements:
                checks.append("추가 조건: " + " · ".join(group_def.requirements))
            for component in group_def.components:
                if component.requirement_label:
                    count = len(set(table_to_codes.get(component.table_id, [])))
                    if "2개 이상" in component.requirement_label and count >= 2:
                        checks.append(f"{self.store.tables[component.table_id].display_label} {component.requirement_label}: 입력코드 {count}개 구조상 일치")
                    else:
                        checks.append(f"{self.store.tables[component.table_id].display_label}: {component.requirement_label} 추가 확인")
            for tid, codes in table_to_codes.items():
                component = next((c for c in group_def.components if c.table_id == tid), None)
                if len(set(codes)) >= 2 and not (component and component.requirement_label):
                    checks.append(f"{self.store.tables[tid].display_label}에 입력코드 {len(set(codes))}개가 함께 포함되지만, 공식 조건이 두 코드를 모두 요구한다는 뜻은 아님")
            if checks:
                check_label = QLabel("확인 필요\n- " + "\n- ".join(checks))
                check_label.setObjectName("RelationCheck")
                check_label.setWordWrap(True)
                box_layout.addWidget(check_label)
            layout.addWidget(box)

        detail_button = QPushButton("이 ADRG의 전체 상세 보기")
        detail_button.setObjectName("RelationDetailButton")
        detail_button.clicked.connect(lambda checked=False, a=rule.adrg: self.open_rule_detail(a))
        layout.addWidget(detail_button, 0, Qt.AlignRight)
        return card

    # ------------------------------------------------------------------
    # 상세: TABLE
    # ------------------------------------------------------------------

    def render_table_detail(self, table_id: str) -> None:
        self._set_current_detail("table", table_id)
        self._reset_detail_layout()
        table = self.store.tables.get(table_id)
        if not table:
            self._render_empty_detail("TABLE 상세 정보를 찾을 수 없습니다.")
            return

        related_rules = self.store.rules_for_table(table_id)
        relation_summary = self.store.relation_summary_for_table(table_id)
        codes = [m.code for m in table.members]

        self.detail_layout.addWidget(
            self._build_primary_card(
                badge_text="TABLE",
                badge_name="BadgeGray",
                title=table.display_label,
                subtitle=shorten_codes(codes, limit=30),
                rows=[
                    ("TABLE_ID", table.table_id),
                    ("코드 유형", table.code_type),
                    ("코드 수", f"{table.count}개"),
                    ("원문 정의 ADRG", relation_summary.get("physical_source", "-")),
                    ("조건 AST 사용 ADRG", relation_summary.get("condition_usage", "-")),
                    ("검색용 관련 ADRG", relation_summary.get("runtime_related", "-")),
                    ("원문 family 근거", relation_summary.get("source_families", "-")),
                    ("근거", table.source_page),
                    ("KDRG 버전", self.store.version),
                ],
            )
        )

        self.detail_layout.addWidget(
            self._build_related_summary(
                title=f"이 TABLE을 사용하는 ADRG · {len(related_rules)}건",
                rules=related_rules,
                clickable=True,
            )
        )

        tabs = QTabWidget()
        tabs.setObjectName("Tabs")
        tabs.addTab(self._scroll_wrap(self._build_table_only_panel(table)), "TABLE 코드")
        tabs.addTab(self._scroll_wrap(self._build_rule_cards(related_rules, highlight_code=self.current_query)), "관련 ADRG")
        tabs.addTab(self._scroll_wrap(self._build_evidence_panel(related_rules)), "원문 근거")
        self.detail_layout.addWidget(tabs, 1)
        self.detail_layout.addStretch(1)

    # ------------------------------------------------------------------
    # 카드/패널 빌더
    # ------------------------------------------------------------------

    def _simple_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("WhiteCard")
        return card

    def _build_primary_card(
        self,
        badge_text: str,
        badge_name: str,
        title: str,
        subtitle: str,
        rows: List[Tuple[str, str]],
    ) -> QFrame:
        card = self._simple_card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        top = QHBoxLayout()
        badge = QLabel(badge_text)
        badge.setObjectName(badge_name)
        badge.setAlignment(Qt.AlignCenter)
        top.addWidget(badge)

        title_label = QLabel(title)
        title_label.setObjectName("DetailTitle")
        top.addWidget(title_label)
        top.addStretch(1)
        layout.addLayout(top)

        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("DetailSubtitle")
        subtitle_label.setWordWrap(True)
        layout.addWidget(subtitle_label)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setObjectName("Divider")
        layout.addWidget(line)

        grid = QGridLayout()
        grid.setHorizontalSpacing(22)
        grid.setVerticalSpacing(8)
        for row, (k, v) in enumerate(rows):
            key_label = QLabel(k)
            key_label.setObjectName("FieldKey")
            value_label = QLabel(v)
            value_label.setObjectName("FieldValue")
            value_label.setWordWrap(True)
            grid.addWidget(key_label, row, 0, Qt.AlignTop)
            grid.addWidget(value_label, row, 1)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        return card

    def _build_related_summary(self, title: str, rules: List[RuleDef], clickable: bool) -> QFrame:
        card = self._simple_card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        title_label = QLabel(title)
        title_label.setObjectName("SectionTitle")
        layout.addWidget(title_label)

        if not rules:
            empty = QLabel("연결된 ADRG가 없습니다.")
            empty.setObjectName("SmallMuted")
            layout.addWidget(empty)
            return card

        for rule in rules:
            row = QFrame()
            row.setObjectName("SummaryRowClickable" if clickable else "SummaryRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(8, 6, 8, 6)
            row_layout.setSpacing(16)

            adrg_label = QLabel(rule.adrg)
            adrg_label.setObjectName("SummaryADRG")
            row_layout.addWidget(adrg_label)

            mdc_badge = QLabel(f"MDC {rule.mdc}")
            mdc_badge.setObjectName("MDCBadge")
            mdc_badge.setAlignment(Qt.AlignCenter)
            row_layout.addWidget(mdc_badge)

            aadrg_label = QLabel(rule.aadrg_display)
            aadrg_label.setObjectName("SummaryAADRG")
            row_layout.addWidget(aadrg_label)

            group = QLabel(rule.group_display)
            group.setObjectName(group_badge_name(rule.group_code, "mini"))
            group.setAlignment(Qt.AlignCenter)
            row_layout.addWidget(group)

            title_label = QLabel(rule.title_full)
            title_label.setObjectName("SummaryText")
            title_label.setWordWrap(True)
            row_layout.addWidget(title_label, 1)

            if clickable:
                button = QPushButton("ADRG 상세")
                button.setObjectName("TinyButton")
                button.clicked.connect(lambda checked=False, a=rule.adrg: self.open_rule_detail(a))
                row_layout.addWidget(button)

            layout.addWidget(row)

        return card

    def _build_rule_cards(self, rules: List[RuleDef], highlight_code: str = "") -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        if not rules:
            empty = QLabel("연결된 ADRG가 없습니다.")
            empty.setObjectName("EmptyText")
            empty.setAlignment(Qt.AlignCenter)
            layout.addWidget(empty)
            layout.addStretch(1)
            return container

        for rule in rules:
            layout.addWidget(self._build_single_rule_card(rule, highlight_code=highlight_code))
        layout.addStretch(1)
        return container

    def _build_single_rule_card(self, rule: RuleDef, highlight_code: str = "") -> QFrame:
        card = self._simple_card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        header = QHBoxLayout()
        adrg = QLabel(rule.adrg)
        adrg.setObjectName("RuleADRG")
        header.addWidget(adrg)

        mdc_badge = QLabel(f"MDC {rule.mdc}")
        mdc_badge.setObjectName("MDCBadge")
        mdc_badge.setAlignment(Qt.AlignCenter)
        header.addWidget(mdc_badge)

        aadrg = QLabel(f"AADRG {rule.aadrg_display}")
        aadrg.setObjectName("RuleAADRG")
        header.addWidget(aadrg)
        header.addStretch(1)

        group = QLabel(rule.group_display)
        group.setObjectName(group_badge_name(rule.group_code, "full"))
        group.setAlignment(Qt.AlignCenter)
        header.addWidget(group)
        layout.addLayout(header)

        title = QLabel(rule.title_full)
        title.setObjectName("RuleTitle")
        title.setWordWrap(True)
        layout.addWidget(title)

        if len(rule.aadrg_mappings) > 1:
            mapping_detail = QLabel(rule.aadrg_detail_display)
            mapping_detail.setObjectName("ConditionIntro")
            mapping_detail.setWordWrap(True)
            layout.addWidget(mapping_detail)

        condition_label = QLabel("분류조건")
        condition_label.setObjectName("SmallMutedStrong")
        layout.addWidget(condition_label)

        condition_box = QFrame()
        condition_box.setObjectName("ConditionBox")
        condition_layout = QVBoxLayout(condition_box)
        condition_layout.setContentsMargins(12, 10, 12, 10)
        condition_layout.setSpacing(10)

        if len(rule.condition_groups) > 1:
            intro_text = rule.condition_summary or f"아래 {len(rule.condition_groups)}개 조건식 중 하나로 구성됨"
            intro = QLabel(intro_text)
            intro.setObjectName("ConditionIntro")
            intro.setWordWrap(True)
            condition_layout.addWidget(intro)

        for group_index, group_def in enumerate(rule.condition_groups):
            group_box = QFrame()
            group_box.setObjectName("ConditionGroupBox")
            group_layout = QVBoxLayout(group_box)
            group_layout.setContentsMargins(10, 9, 10, 9)
            group_layout.setSpacing(8)

            show_group_title = len(rule.condition_groups) > 1
            if show_group_title:
                group_title = QLabel(group_def.group_label or f"조건식 {group_def.group_no}")
                group_title.setObjectName("ConditionGroupTitle")
                group_layout.addWidget(group_title)

            for idx, component in enumerate(group_def.components):
                if idx > 0:
                    op_text = component.operator_before or "AND"
                    op = QLabel("그리고" if op_text.upper() == "AND" else op_text)
                    op.setObjectName("OperatorLabel")
                    op.setAlignment(Qt.AlignCenter)
                    group_layout.addWidget(op)

                table_def = self.store.tables[component.table_id]
                row = self._build_condition_table_row(table_def, highlight_code, component.requirement_label)
                group_layout.addWidget(row)

            if group_def.exclude_components:
                exclude_title = QLabel("미포함·제외조건")
                exclude_title.setObjectName("ExcludeConditionTitle")
                group_layout.addWidget(exclude_title)
                for component in group_def.exclude_components:
                    table_def = self.store.tables[component.table_id]
                    row = self._build_condition_table_row(table_def, highlight_code, component.requirement_label, exclusion=True)
                    group_layout.addWidget(row)

            if group_def.requirements:
                requirement_text = QLabel("추가 조건 · " + " · ".join(group_def.requirements))
                requirement_text.setObjectName("GroupRequirement")
                requirement_text.setWordWrap(True)
                group_layout.addWidget(requirement_text)

            condition_layout.addWidget(group_box)

            if group_index < len(rule.condition_groups) - 1:
                joiner = group_def.join_to_next_group or "OR"
                joiner_label = "또는" if joiner.upper() == "OR" else joiner
                divider = QLabel(f"──── {joiner_label} ────")
                divider.setObjectName("OrDivider")
                divider.setAlignment(Qt.AlignCenter)
                condition_layout.addWidget(divider)

        layout.addWidget(condition_box)

        note = QLabel("table명 버튼을 누르면 코드·한글명·영문명 상세 코드표가 펼쳐집니다. 코드요약은 원문 순서를 유지합니다.")
        note.setObjectName("SmallMuted")
        note.setWordWrap(True)
        layout.addWidget(note)

        return card

    def _build_condition_table_row(
        self,
        table_def: TableDef,
        highlight_code: str,
        requirement_label: str = "",
        exclusion: bool = False,
    ) -> QFrame:
        row = QFrame()
        contains_search = bool(normalize(highlight_code)) and table_def.contains_code(highlight_code)
        if exclusion:
            row.setObjectName("ExcludeConditionRowHit" if contains_search else "ExcludeConditionRow")
        else:
            row.setObjectName("ConditionRowHit" if contains_search else "ConditionRow")
        layout = QVBoxLayout(row)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(8)

        button_text = f"{table_def.display_label} · {table_def.count}개"
        if contains_search:
            button_text += " · 검색코드 포함"
        button = QToolButton()
        button.setText(button_text)
        button.setCheckable(True)
        button.setCursor(Qt.PointingHandCursor)
        if exclusion:
            button.setObjectName("ExcludeTablePillHit" if contains_search else "ExcludeTablePill")
        else:
            button.setObjectName("TablePillHit" if contains_search else "TablePill")
        top.addWidget(button)

        # 역할 배지: 코드유형 → 역할명 변환
        role_text = _CODE_TYPE_ROLE.get(table_def.code_type, table_def.code_type)
        if exclusion:
            role_text = "제외조건"
        code_type_lbl = QLabel(role_text)
        code_type_lbl.setObjectName("ExcludeRoleBadge" if exclusion else "MiniTypeBadge")
        code_type_lbl.setAlignment(Qt.AlignCenter)
        top.addWidget(code_type_lbl)

        if requirement_label:
            req_lbl = QLabel(requirement_label)
            req_lbl.setObjectName("RequirementBadge")
            req_lbl.setAlignment(Qt.AlignCenter)
            top.addWidget(req_lbl)

        top.addStretch(1)
        layout.addLayout(top)

        codes = [m.code for m in table_def.members]
        summary = QLabel(rich_code_summary(codes, highlight_code, limit=20))
        summary.setTextFormat(Qt.RichText)
        summary.setObjectName("CodeSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        expanded = CodeTableFrame(table_def, highlight_code=highlight_code, parent=row)
        layout.addWidget(expanded)

        def toggle_expanded(checked: bool) -> None:
            if checked:
                expanded.ensure_populated()  # 지연 채우기: 처음 펼칠 때만 행 추가
            expanded.setVisible(checked)
            button.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)

        button.setArrowType(Qt.RightArrow)
        button.toggled.connect(toggle_expanded)
        return row

    def _build_evidence_panel(self, rules: List[RuleDef]) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        if not rules:
            empty = QLabel("표시할 원문 근거가 없습니다.")
            empty.setObjectName("EmptyText")
            empty.setAlignment(Qt.AlignCenter)
            layout.addWidget(empty)
            layout.addStretch(1)
            return panel

        for rule in rules:
            card = self._simple_card()
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(18, 16, 18, 16)
            card_layout.setSpacing(10)

            title = QLabel(f"{rule.adrg} · {rule.aadrg_display} · {rule.group_display}")
            title.setObjectName("RuleADRG")
            card_layout.addWidget(title)

            body = QLabel(
                f"조건 원문: {rule.condition_text}\n"
                f"근거: {rule.source_page}\n"
                f"비고: {self.store.source_note}\n"
                f"A/B/C 기준: {self.store.abc_basis}"
            )
            body.setObjectName("EvidenceText")
            body.setWordWrap(True)
            card_layout.addWidget(body)
            layout.addWidget(card)

        layout.addStretch(1)
        return panel

    def _build_table_only_panel(self, table_def: TableDef) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        frame = CodeTableFrame(table_def, highlight_code=self.current_query, parent=panel)
        frame.ensure_populated()
        frame.setVisible(True)
        layout.addWidget(frame)
        layout.addStretch(1)
        return panel

    def _scroll_wrap(self, widget: QWidget) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(widget)
        return wrapper

    # ------------------------------------------------------------------
    # 스타일
    # ------------------------------------------------------------------

    def _apply_style(self) -> None:
        self.setStyleSheet(MAIN_STYLE_SHEET)
