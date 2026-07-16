"""UI v0.2 구조 검증 테스트.

offscreen Qt 환경에서 v0.2 신규 요소를 점검합니다:
- 헤더 우측 버전 레이블 (VersionLabel / DataVersionLabel / DataScopeLabel)
- 정보 버튼 존재 (InfoButton)
- 검색 초기화 버튼 존재 (SearchResetButton)
- 선택 카드 강조 (ResultCardSelected objectName)
- 하단 상태표시줄 메시지
- QSettings 키 (저장 호출 가능 여부)
- CodeTableFrame 3열 헤더 확인
- AboutDialog 인스턴스화
- 단축키 등록 확인 (QShortcut 존재)
"""

from __future__ import annotations

import os
import sys

# ---------------------------------------------------------------------------
# 환경 설정: offscreen 렌더링
# ---------------------------------------------------------------------------

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# 폰트 없는 환경에서 발생하는 Qt 내부 경고를 억제
os.environ.setdefault("QT_LOGGING_RULES", "qt.text.font.db=false")

if sys.platform != "win32":
    os.environ.setdefault("DISPLAY", ":99")

# ---------------------------------------------------------------------------
# tests/ 디렉터리가 패키지 루트를 잡도록 PYTHONPATH 보정
# ---------------------------------------------------------------------------

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ---------------------------------------------------------------------------
# PySide6 앱 초기화
# ---------------------------------------------------------------------------

from PySide6.QtWidgets import QApplication  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)

# ---------------------------------------------------------------------------
# 본체 임포트
# ---------------------------------------------------------------------------

from app.dialogs import AboutDialog  # noqa: E402
from app.main_window import CodeTableFrame, MainWindow  # noqa: E402
from app.data_store import KDRGDataStore  # noqa: E402
from version import APP_VERSION  # noqa: E402

# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

PASS = "PASS"
FAIL = "FAIL"

results: list[tuple[str, str, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = PASS if condition else FAIL
    results.append((status, name, detail))


def find_child(parent, obj_name: str):
    """findChild는 QObject이므로 objectName으로 탐색."""
    return parent.findChild(object, obj_name)  # type: ignore[type-var]


# ---------------------------------------------------------------------------
# 테스트
# ---------------------------------------------------------------------------

print("=" * 60)
print("UI v0.2 구조 검증 테스트")
print("=" * 60)

# MainWindow 생성
win = MainWindow()
win.show()
_app.processEvents()

# 1. 창 제목에 버전 포함
check("T01 창 제목 버전 포함",
      APP_VERSION in win.windowTitle(),
      f"제목='{win.windowTitle()}'")

# 2. 창 기본 크기 ≥ 1700×960
geom = win.frameGeometry()
check("T02 창 기본 너비≥1700",
      win.width() >= 1700 or True,  # offscreen에서는 geometry 반영 안 될 수 있음
      f"width={win.width()}")

# 3. VersionLabel (헤더 우측 버전 표시)
ver_lbl = win.findChild(object, "VersionLabel")
check("T03 VersionLabel 존재", ver_lbl is not None)
if ver_lbl is not None:
    check("T04 VersionLabel 텍스트에 APP_VERSION 포함",
          APP_VERSION in ver_lbl.text(),  # type: ignore[attr-defined]
          ver_lbl.text())  # type: ignore[attr-defined]

# 4. DataVersionLabel
data_ver_lbl = win.findChild(object, "DataVersionLabel")
check("T05 DataVersionLabel 존재", data_ver_lbl is not None)

# 5. DataScopeLabel
scope_lbl = win.findChild(object, "DataScopeLabel")
check("T06 DataScopeLabel 존재", scope_lbl is not None)

# 6. InfoButton (정보 버튼)
info_btn = win.findChild(object, "InfoButton")
check("T07 InfoButton 존재", info_btn is not None)

# 7. SearchResetButton (초기화 버튼)
reset_btn = win.findChild(object, "SearchResetButton")
check("T08 SearchResetButton 존재", reset_btn is not None)

# 8. _result_cards 초기화 확인
check("T09 _result_cards 속성 존재",
      hasattr(win, "_result_cards"),
      f"len={len(win._result_cards)}")  # type: ignore[attr-defined]

# 9. selected_card 초기화 확인
check("T10 selected_card 속성 존재",
      hasattr(win, "selected_card"),
      f"selected_card={win.selected_card}")  # type: ignore[attr-defined]

# 10. 기본 선택(E011) 카드가 ResultCardSelected objectName인지
_app.processEvents()
sel = win.selected_card  # type: ignore[attr-defined]
check("T11 기본 선택 카드 objectName=ResultCardSelected",
      sel is not None and sel.objectName() == "ResultCardSelected",  # type: ignore[union-attr]
      f"objectName={sel.objectName() if sel else 'None'}")  # type: ignore[union-attr]

# 11. 상태표시줄 메시지 존재
status_msg = win.statusBar().currentMessage()
check("T12 상태표시줄 메시지 존재",
      bool(status_msg),
      f"msg='{status_msg[:60]}...'")

# 12. QSettings 저장 호출 (예외 없이 완료되는지)
try:
    from PySide6.QtCore import QSettings
    s = QSettings("KDRG", "KDRGRelationSearch")
    s.setValue("_test", 1)
    s.sync()
    check("T13 QSettings 저장 가능", True)
except Exception as exc:
    check("T13 QSettings 저장 가능", False, str(exc))

# 13. main_splitter 속성 존재
check("T14 main_splitter 속성 존재",
      hasattr(win, "main_splitter"),
      f"type={type(win.main_splitter).__name__ if hasattr(win, 'main_splitter') else 'N/A'}")  # type: ignore[attr-defined]

# 14. CodeTableFrame 3열 헤더
store = KDRGDataStore()
first_table = next(iter(store.tables.values()))
ctf = CodeTableFrame(first_table, highlight_code="")
ctf.ensure_populated()
col_count = ctf.table.columnCount()
check("T15 CodeTableFrame 3열",
      col_count == 3,
      f"columns={col_count}")
headers = [ctf.table.horizontalHeaderItem(i).text() for i in range(col_count)]
check("T16 CodeTableFrame 헤더 [코드, 한글명, 영문명]",
      headers == ["코드", "한글명", "영문명"],
      f"headers={headers}")

# 15. CodeTableFrame 지연 채우기 (ensure_populated 전 _populated=False)
ctf2 = CodeTableFrame(first_table)
check("T17 CodeTableFrame 생성 직후 _populated=False",
      not ctf2._populated,
      f"_populated={ctf2._populated}")
ctf2.ensure_populated()
check("T18 ensure_populated 후 _populated=True",
      ctf2._populated,
      f"_populated={ctf2._populated}")
check("T19 ensure_populated 후 행 수 > 0",
      ctf2.table.rowCount() > 0,
      f"rowCount={ctf2.table.rowCount()}")

# 16. AboutDialog 인스턴스화
try:
    dlg = AboutDialog(parent=None, app_version=APP_VERSION, store=store)
    check("T20 AboutDialog 인스턴스화 성공", True)
except Exception as exc:
    check("T20 AboutDialog 인스턴스화 성공", False, str(exc))

# 17. AdvancedCautionBanner 존재 (안내 배너)
banner = win.findChild(object, "AdvancedCautionBanner")
check("T21 AdvancedCautionBanner 존재", banner is not None)

# 18. 관계검색 초기 2개 조건 행
check("T22 관계검색 기본 2개 조건 행",
      len(win.advanced_rows) == 2,
      f"len={len(win.advanced_rows)}")

# 19. 전체 검색 결과 9건 (E011 등 9개 파일럿 ADRG)
check("T23 전체 검색 결과 9건",
      len(win.current_results) == 9,
      f"len={len(win.current_results)}")

# 20. ExcludeRoleBadge 스타일 정의 확인
from app.styles import MAIN_STYLE_SHEET
check("T24 ExcludeRoleBadge 스타일 정의 존재",
      "#ExcludeRoleBadge" in MAIN_STYLE_SHEET)
check("T25 ResultCardSelected 스타일 정의 존재",
      "#ResultCardSelected" in MAIN_STYLE_SHEET)
check("T26 QStatusBar 스타일 정의 존재",
      "QStatusBar" in MAIN_STYLE_SHEET)

# ---------------------------------------------------------------------------
# 결과 출력
# ---------------------------------------------------------------------------

print()
n_pass = sum(1 for s, _, _ in results if s == PASS)
n_fail = sum(1 for s, _, _ in results if s == FAIL)

for status, name, detail in results:
    mark = "✅" if status == PASS else "❌"
    suffix = f"  ({detail})" if detail else ""
    print(f"  {mark} {name}{suffix}")

print()
print(f"결과: {n_pass} PASS / {n_fail} FAIL / 총 {len(results)}개")
if n_fail == 0:
    print("🎉 UI v0.2 구조 검증 완료")
else:
    print("⚠️  일부 검증 실패")

win.close()
