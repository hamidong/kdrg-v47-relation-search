from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("KDRG_DISABLE_SETTINGS", "1")

from PySide6.QtWidgets import QApplication

from app.main_window import MainWindow
from app.runtime_data_store import KDRGRuntimeDataStore


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        checks.append((name, bool(condition), detail))

    store = KDRGRuntimeDataStore()
    check("ADRG 1132", len(store.rules) == 1132, str(len(store.rules)))
    check("TABLE 1308", len(store.tables) == 1308, str(len(store.tables)))
    check("CODE 16571", len(store.code_to_tables) == 16571, str(len(store.code_to_tables)))
    check("E011 rule", "E011" in store.rules, str("E011" in store.rules))
    check("default bounded", 1 <= len(store.search("", "전체")) <= 200, str(len(store.search("", "전체"))))
    check("default E011 first", store.search("", "전체")[0].key == "E011", store.search("", "전체")[0].key)
    adrg_rows = store.search("9600", "ADRG")
    check("ADRG exact", bool(adrg_rows) and adrg_rows[0].key == "9600", str(adrg_rows[:1]))

    aadrg_rows = store.search("96000", "ADRG")
    check("AADRG exact parent", bool(aadrg_rows) and aadrg_rows[0].key == "9600", str(aadrg_rows[:1]))

    rdrg_rows = store.search("960000", "RDRG")
    check("RDRG exact parent", bool(rdrg_rows) and rdrg_rows[0].key == "9600", str(rdrg_rows[:1]))

    # 특정 코드(A000)를 fixture로 가정하지 않는다. 현재 통합 데이터에 실제 존재하는
    # 진단코드 전체에서 점 표기 변환이 가능한 대표 코드를 결정론적으로 선택한다.
    diagnosis_codes = sorted(
        code
        for code, code_types in store._code_types_by_code.items()
        if "상병코드" in code_types and len(code) > 3 and code.isalnum()
    )
    dotted_code = diagnosis_codes[0] if diagnosis_codes else ""
    dotted_query = f"{dotted_code[:3]}.{dotted_code[3:]}" if dotted_code else ""
    dotted_rows = store.search(dotted_query, "상병코드") if dotted_query else []
    check(
        "CODE dotted",
        bool(dotted_code) and bool(dotted_rows) and dotted_rows[0].key == dotted_code,
        f"fixture={dotted_code or '-'} query={dotted_query or '-'} result={dotted_rows[:1]}",
    )

    table_rows = store.search("LT_9610_001", "TABLE")
    check("TABLE exact", bool(table_rows) and table_rows[0].key == "LT_9610_001", str(table_rows[:1]))
    relation = store.relation_summary_for_code("S710")
    check("physical relation", relation["physical_source"] == "X012, X030, X600", str(relation))
    check("condition relation", relation["condition_usage"] == "X011, X012, X041, X042", str(relation))
    check("X04 hidden", "X04," not in relation["runtime_related"] and relation["source_families"] == "X04", str(relation))

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    app.processEvents()
    check("MainWindow runtime store", isinstance(window.store, KDRGRuntimeDataStore), type(window.store).__name__)
    check("MainWindow results", len(window.current_results) <= 200, str(len(window.current_results)))
    check("MainWindow E011 selected", bool(window.selected_result and window.selected_result.key == "E011"), str(window.selected_result))
    check("MainWindow status full", "ADRG 1132개" in window.statusBar().currentMessage(), window.statusBar().currentMessage())
    window.close()
    app.processEvents()

    failed = [(name, detail) for name, passed, detail in checks if not passed]
    for name, passed, detail in checks:
        print(f"[{'PASS' if passed else 'FAIL'}] {name} | {detail}")
    print(f"결과: {len(checks) - len(failed)} PASS / {len(failed)} FAIL")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
