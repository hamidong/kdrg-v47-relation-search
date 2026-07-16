"""KDRG V4.7 코드 관계 검색기 - QSS 스타일시트 (v0.2).

v0.1 대비 변경:
 - #ResultCardSelected : 선택된 결과 카드 강조 (왼쪽 강조선 + 파란 테두리)
 - #VersionLabel / #DataVersionLabel / #DataScopeLabel : 헤더 우측 버전 정보
 - #InfoButton : 정보 버튼
 - #SearchResetButton : 검색 초기화 버튼
 - #AdvancedCautionBanner / #CautionIcon : 관계검색 안내 배너
 - #ExcludeRoleBadge : 제외조건 역할 배지 (붉은 계열)
 - QStatusBar : 하단 상태표시줄
"""

MAIN_STYLE_SHEET = """
    QMainWindow {
        background: #edf2f8;
        color: #08264a;
        font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', Arial, sans-serif;
        font-size: 13px;
    }

    /* ── 헤더 ── */
    #Header {
        background: #173e68;
        border: none;
    }
    #HeaderTitle {
        color: white;
        font-size: 24px;
        font-weight: 800;
    }
    #HeaderSubtitle {
        color: #d6e7fb;
        font-size: 12px;
    }
    #VersionLabel {
        color: #c8e3f8;
        font-size: 12px;
        font-weight: 700;
    }
    #DataVersionLabel {
        color: #d6e7fb;
        font-size: 11px;
    }
    #DataScopeLabel {
        color: #a8c8e8;
        font-size: 11px;
    }
    #InfoButton {
        background: #2f5d8b;
        color: #eaf4ff;
        border: 1px solid #5f86ae;
        border-radius: 6px;
        padding: 8px 14px;
        font-weight: 700;
        min-height: 56px;
    }
    #InfoButton:hover {
        background: #3a6fa0;
    }
    #InfoButton:pressed {
        background: #245078;
    }

    /* ── 검색 ── */
    #SearchCombo {
        background: white;
        border: 1px solid #b7c6d6;
        border-radius: 5px;
        padding: 0 10px;
        min-height: 34px;
        min-width: 125px;
    }
    #SearchEdit {
        background: white;
        border: 1px solid #b7c6d6;
        border-radius: 6px;
        padding: 0 12px;
        min-height: 34px;
        color: #173e68;
    }
    #SearchButton {
        background: #2f77bd;
        color: white;
        border: none;
        border-radius: 6px;
        font-weight: 800;
        min-height: 34px;
        min-width: 72px;
    }
    #SearchButton:hover {
        background: #2669a9;
    }
    #SearchResetButton {
        background: #edf4fb;
        color: #16436c;
        border: 1px solid #bfd2e4;
        border-radius: 6px;
        min-height: 34px;
        min-width: 62px;
        font-weight: 800;
    }
    #SearchResetButton:hover {
        background: #dbeeff;
        border: 1px solid #8dbce9;
    }

    /* ── 왼쪽/오른쪽 패널 ── */
    #LeftPanel, #RightPanel {
        background: #edf2f8;
        border: none;
    }
    #BackButton {
        background: #ffffff;
        color: #16436c;
        border: 1px solid #b9cde0;
        border-radius: 7px;
        padding: 6px 11px;
        font-weight: 800;
        min-height: 24px;
    }
    #BackButton:hover {
        background: #e7f2ff;
        border: 1px solid #79abe0;
    }
    #BackButton:pressed {
        background: #d8eaff;
    }
    #PanelTitle {
        font-size: 16px;
        font-weight: 800;
        color: #0a2a4d;
    }
    #CountLabel, #CurrentType {
        color: #62758b;
        font-size: 12px;
    }
    #ResultScroll, #DetailScroll {
        background: transparent;
        border: none;
    }

    /* ── 결과 카드 ── */
    #ResultCard {
        background: white;
        border: 1px solid #d4dee9;
        border-radius: 8px;
    }
    #ResultCard:hover {
        background: #f7fbff;
        border: 1px solid #80b6ef;
    }
    #ResultCardSelected {
        background: #eaf4ff;
        border: 1px solid #3a8edc;
        border-left: 5px solid #1565c0;
        border-radius: 8px;
    }
    #ResultCardSelected:hover {
        background: #def0ff;
    }
    #ResultTitle {
        font-size: 14px;
        font-weight: 800;
        color: #08264a;
    }
    #ResultSub {
        color: #2f4b68;
        font-size: 12px;
        line-height: 150%;
    }

    /* ── 상세 카드 ── */
    #WhiteCard {
        background: white;
        border: 1px solid #d4dee9;
        border-radius: 10px;
    }
    #Divider {
        color: #d9e2ec;
        background: #d9e2ec;
    }
    #DetailTitle {
        color: #08264a;
        font-size: 24px;
        font-weight: 900;
    }
    #DetailSubtitle {
        color: #0a2a4d;
        font-size: 14px;
        font-weight: 700;
    }
    #FieldKey {
        color: #58708a;
        font-weight: 700;
        min-width: 110px;
    }
    #FieldValue {
        color: #08264a;
    }
    #SectionTitle {
        color: #0a2a4d;
        font-size: 14px;
        font-weight: 800;
    }
    #SummaryRow, #SummaryRowClickable {
        background: #ffffff;
        border-radius: 8px;
    }
    #SummaryRowClickable:hover {
        background: #f1f7ff;
    }
    #SummaryADRG {
        color: #0a2a4d;
        font-weight: 900;
        min-width: 45px;
    }
    #SummaryAADRG {
        color: #657992;
        min-width: 60px;
    }
    #SummaryText {
        color: #1c3e62;
        font-size: 12px;
    }
    #TinyButton {
        background: #eef5fc;
        color: #16436c;
        border: 1px solid #c9dcec;
        border-radius: 6px;
        padding: 4px 9px;
        font-weight: 700;
    }
    #TinyButton:hover {
        background: #dbeeff;
        border: 1px solid #8dbce9;
    }

    /* ── 탭 ── */
    #Tabs::pane {
        border: 1px solid #d4dee9;
        border-radius: 8px;
        background: #f6f9fc;
        top: -1px;
    }
    QTabBar::tab {
        background: #e4ebf3;
        color: #244867;
        padding: 10px 18px;
        border-top-left-radius: 7px;
        border-top-right-radius: 7px;
        font-weight: 800;
    }
    QTabBar::tab:selected {
        background: white;
        color: #08264a;
    }

    /* ── ADRG 규칙 카드 ── */
    #RuleADRG {
        font-size: 21px;
        font-weight: 900;
        color: #08264a;
    }
    #RuleAADRG {
        color: #6d7e91;
        font-size: 13px;
        font-weight: 700;
    }
    #RuleTitle {
        color: #0a2a4d;
        font-size: 14px;
        font-weight: 800;
    }

    /* ── 조건 구조 ── */
    #ConditionBox {
        background: #f8fbff;
        border: 1px solid #e0e9f3;
        border-radius: 8px;
    }
    #ConditionIntro {
        color: #234766;
        background: #eef6ff;
        border: 1px solid #d3e8fb;
        border-radius: 7px;
        padding: 8px 10px;
        font-weight: 800;
    }
    #ConditionGroupBox {
        background: #ffffff;
        border: 1px solid #d8e5f0;
        border-radius: 9px;
    }
    #ConditionGroupTitle {
        color: #0a2a4d;
        font-size: 13px;
        font-weight: 900;
        padding: 2px 0 4px 0;
    }
    #OrDivider {
        color: #0b4f91;
        font-size: 12px;
        font-weight: 900;
        padding: 4px 0;
    }
    #ExcludeConditionTitle {
        color: #9b2c2c;
        font-size: 12px;
        font-weight: 900;
        padding-top: 4px;
    }
    #ExcludeConditionRow {
        background: #fff7f7;
        border: 1px solid #efcaca;
        border-radius: 8px;
    }
    #ExcludeConditionRowHit {
        background: #fff0f0;
        border: 1px solid #df8585;
        border-radius: 8px;
    }
    #ExcludeTablePill, #ExcludeTablePillHit {
        border-radius: 7px;
        padding: 7px 12px;
        font-weight: 800;
        color: #8a2525;
        background: #fdecec;
        border: 1px solid #e6b4b4;
    }
    #ExcludeTablePill:hover, #ExcludeTablePillHit:hover {
        background: #f9dddd;
    }
    #ConditionRow {
        background: white;
        border: 1px solid #e0e8f0;
        border-radius: 8px;
    }
    #ConditionRowHit {
        background: #f2f8ff;
        border: 1px solid #85b8ee;
        border-radius: 8px;
    }
    #TablePill, #TablePillHit {
        border-radius: 7px;
        padding: 7px 12px;
        font-weight: 800;
    }
    #TablePill {
        color: #183b5f;
        background: #edf3f8;
        border: 1px solid #cbd8e5;
    }
    #TablePill:hover {
        background: #e2edf8;
    }
    #TablePillHit {
        color: #0b4f91;
        background: #dcebff;
        border: 1px solid #7cb2ee;
    }
    #TablePillHit:hover {
        background: #cfe4ff;
    }
    #CodeSummary {
        color: #183b5f;
        background: transparent;
        font-size: 13px;
        line-height: 160%;
    }
    #OperatorLabel {
        color: #5d728a;
        font-size: 11px;
        font-weight: 900;
        padding: 2px 0;
    }

    /* ── 펼쳐진 TABLE 코드표 ── */
    #ExpandedTableFrame {
        background: #ffffff;
        border: 1px solid #d6e2ef;
        border-radius: 8px;
    }
    #ExpandedTitle {
        color: #0a2a4d;
        font-size: 14px;
        font-weight: 900;
    }
    #InnerSearch {
        background: white;
        border: 1px solid #cbd8e5;
        border-radius: 6px;
        min-height: 30px;
        padding: 0 10px;
    }
    #CodeTable {
        background: white;
        gridline-color: #dfe7ef;
        border: 1px solid #dbe5ef;
        border-radius: 6px;
        alternate-background-color: #f8fbff;
    }
    QHeaderView::section {
        background: #edf3f8;
        color: #183b5f;
        border: none;
        border-right: 1px solid #d9e2ec;
        padding: 8px;
        font-weight: 800;
    }

    /* ── 배지 공통 ── */
    #BadgeGreen, #BadgeBlue, #BadgeTeal, #BadgeOrange,
    #BadgePurple, #BadgeGray, #BadgeNavy, #BadgeRelation,
    #MiniTypeBadge, #ExcludeRoleBadge, #RequirementBadge,
    #MDCBadge,
    #ResultGroupBadgeA, #ResultGroupBadgeB, #ResultGroupBadgeC, #ResultGroupBadgeOther,
    #MiniGroupBadgeA, #MiniGroupBadgeB, #MiniGroupBadgeC, #MiniGroupBadgeOther,
    #GroupBadgeA, #GroupBadgeB, #GroupBadgeC, #GroupBadgeOther {
        border-radius: 8px;
        padding: 4px 10px;
        font-size: 12px;
        font-weight: 800;
    }
    #BadgeGreen  { color: #008248; background: #def7ea; }
    #BadgeBlue   { color: #0b5cad; background: #e4f0ff; }
    #BadgeTeal   { color: #006b68; background: #def5f3; }
    #BadgeOrange { color: #9a4e00; background: #fff0db; }
    #BadgePurple { color: #6832b7; background: #efe4ff; }
    #BadgeGray   { color: #46566a; background: #eef2f6; }
    #BadgeNavy   { color: #ffffff; background: #234f7a; }
    #BadgeRelation { color: #7a3f00; background: #fff0d7; border: 1px solid #efc27d; }

    #ResultGroupBadgeA, #ResultGroupBadgeB,
    #ResultGroupBadgeC, #ResultGroupBadgeOther {
        border-radius: 8px;
        padding: 4px 9px;
        font-size: 11px;
        font-weight: 900;
    }
    #ResultGroupBadgeA, #MiniGroupBadgeA { color: #0b4f91; background: #e6f1ff; }
    #ResultGroupBadgeB, #MiniGroupBadgeB { color: #087443; background: #e2f6eb; }
    #ResultGroupBadgeC, #MiniGroupBadgeC { color: #9a4e00; background: #fff0db; }
    #ResultGroupBadgeOther, #MiniGroupBadgeOther { color: #46566a; background: #eef2f6; }
    #MiniGroupBadgeA, #MiniGroupBadgeB, #MiniGroupBadgeC, #MiniGroupBadgeOther {
        border-radius: 8px;
        padding: 3px 9px;
        font-size: 11px;
        font-weight: 800;
    }
    #GroupBadgeA, #GroupBadgeB, #GroupBadgeC, #GroupBadgeOther {
        color: white;
        border-radius: 10px;
        padding: 7px 13px;
        font-size: 12px;
        font-weight: 900;
    }
    #GroupBadgeA { background: #0d4f91; }
    #GroupBadgeB { background: #137a4f; }
    #GroupBadgeC { background: #b65c00; }
    #GroupBadgeOther { background: #566779; }
    #MDCBadge {
        color: #35516d;
        background: #edf3f8;
        border: 1px solid #d4e0eb;
        border-radius: 7px;
        padding: 4px 8px;
        font-size: 10px;
        font-weight: 900;
    }
    #GroupRequirement {
        color: #7a3d00;
        background: #fff6e8;
        border: 1px solid #f1d2a7;
        border-radius: 7px;
        padding: 7px 10px;
        font-size: 11px;
        font-weight: 900;
    }
    #RequirementBadge {
        color: #8a3f00;
        background: #fff0db;
        border-radius: 7px;
        padding: 4px 9px;
        font-size: 11px;
        font-weight: 900;
    }
    #MiniTypeBadge {
        color: #42607e;
        background: #eef3f8;
        border-radius: 7px;
        padding: 4px 9px;
        font-size: 11px;
        font-weight: 800;
    }
    #ExcludeRoleBadge {
        color: #8a2525;
        background: #fdecec;
        border: 1px solid #e6b4b4;
        border-radius: 7px;
        padding: 4px 9px;
        font-size: 11px;
        font-weight: 800;
    }
    #SmallMuted, #SmallMutedStrong {
        color: #667a91;
        font-size: 12px;
    }
    #SmallMutedStrong { font-weight: 800; }
    #EvidenceText {
        color: #214463;
        line-height: 160%;
    }
    #EmptyText {
        color: #728295;
        font-size: 13px;
        padding: 24px;
    }

    /* ── 복수 코드 관계검색 패널 ── */
    #AdvancedToggle {
        color: #e9f4ff;
        background: #28567f;
        border: 1px solid #5f86ae;
        border-radius: 7px;
        padding: 6px 10px;
        font-weight: 800;
    }
    #AdvancedToggle:hover { background: #346993; }
    #AdvancedPanel {
        background: #244b72;
        border: 1px solid #5d81a5;
        border-radius: 9px;
    }
    #AdvancedCautionBanner {
        background: #183e63;
        border: 1px solid #3a6990;
        border-radius: 7px;
    }
    #CautionIcon {
        color: #f0b429;
        font-size: 16px;
        font-weight: 900;
    }
    #AdvancedCaution {
        color: #eef7ff;
        font-size: 12px;
        font-weight: 700;
    }
    #AdvancedConditionRow {
        background: #f6faff;
        border: 1px solid #bad0e4;
        border-radius: 7px;
    }
    #AdvancedIndex { color: #173e68; font-weight: 900; min-width: 48px; }
    #AdvancedTypeCombo, #RelationOperatorCombo {
        background: white;
        border: 1px solid #b7c6d6;
        border-radius: 5px;
        min-height: 30px;
        padding: 0 8px;
    }
    #AdvancedCodeEdit {
        background: white;
        border: 1px solid #b7c6d6;
        border-radius: 5px;
        min-height: 30px;
        padding: 0 9px;
    }
    #AdvancedRemoveButton, #AdvancedResetButton, #AdvancedAddButton {
        background: #edf4fb;
        color: #16436c;
        border: 1px solid #bfd2e4;
        border-radius: 6px;
        padding: 5px 9px;
        font-weight: 800;
    }
    #RelationSearchButton {
        background: #f0a33b;
        color: #3d2500;
        border: none;
        border-radius: 6px;
        padding: 7px 13px;
        font-weight: 900;
    }
    #RelationSearchButton:hover { background: #ffb956; }

    /* ── 복수 코드 관계 분석 ── */
    #RelationGroupBoxStrict { background: #eff9f3; border: 1px solid #8ec8a5; border-radius: 8px; }
    #RelationGroupBoxSplit  { background: #fff7eb; border: 1px solid #e8bd7a; border-radius: 8px; }
    #RelationGroupTitle { color: #173e68; font-weight: 900; }
    #RelationHit  { color: #0c633e; font-weight: 800; }
    #RelationMiss { color: #8a2525; }
    #RelationCheck {
        color: #5c3900;
        background: #fffbf0;
        border: 1px solid #e8d68a;
        border-radius: 7px;
        padding: 8px 10px;
        font-size: 12px;
    }
    #RelationDetailButton {
        background: #eef5fc;
        color: #16436c;
        border: 1px solid #c9dcec;
        border-radius: 6px;
        padding: 6px 12px;
        font-weight: 800;
    }
    #RelationDetailButton:hover { background: #dbeeff; }

    /* ── 하단 상태표시줄 ── */
    QStatusBar {
        background: #e8f0f8;
        color: #315779;
        font-size: 11px;
        border-top: 1px solid #cbd9e8;
    }
    QStatusBar::item { border: none; }
"""
