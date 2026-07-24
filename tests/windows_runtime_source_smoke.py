#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_OPENGL", "software")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPORTS = ROOT / "reports"
REPORT_TXT = REPORTS / "windows_runtime_source_smoke_report.txt"
REPORT_JSON = REPORTS / "windows_runtime_source_smoke_report.json"
SCRIPT_VERSION = "2026-07-24_KDRG_V47_WINDOWS_RUNTIME_SOURCE_SMOKE_V1"


def add_check(
    checks: list[dict[str, Any]],
    name: str,
    passed: bool,
    actual: Any,
    expected: Any,
) -> None:
    checks.append(
        {
            "name": name,
            "status": "PASS" if passed else "FAIL",
            "actual": actual,
            "expected": expected,
        }
    )


def first_key(mapping: Any) -> str:
    if isinstance(mapping, dict) and mapping:
        return sorted(str(key) for key in mapping)[0]
    return ""


def dotted_query(code: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]", "", code).upper()
    if len(normalized) > 3:
        return normalized[:3] + "." + normalized[3:]
    return normalized


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    checks: list[dict[str, Any]] = []

    from PySide6.QtWidgets import QApplication
    from app.kdrg_search_service import KdrgSearchService
    from app.runtime_data_store import KDRGRuntimeDataStore
    from app.main_window import MainWindow

    integrated_path = ROOT / "data" / "kdrg_v47_search_integrated.json"
    add_check(
        checks,
        "통합 JSON 존재",
        integrated_path.is_file(),
        str(integrated_path),
        "exists",
    )

    service = KdrgSearchService()
    status = service.status()
    add_check(checks, "service status", isinstance(status, dict), type(status).__name__, "dict")

    store = KDRGRuntimeDataStore()
    counts = {
        "adrg": len(getattr(store, "rules", {})),
        "aadrg": len(getattr(store, "aadrg_mapping", {})),
        "table": len(getattr(store, "tables", {})),
        "code": len(getattr(store, "code_to_tables", {})),
    }
    add_check(checks, "ADRG count", counts["adrg"] == 1132, counts["adrg"], 1132)
    add_check(checks, "AADRG count", counts["aadrg"] == 1233, counts["aadrg"], 1233)
    add_check(checks, "TABLE count", counts["table"] == 1308, counts["table"], 1308)
    add_check(checks, "CODE count", counts["code"] == 16571, counts["code"], 16571)

    adrg = "E011" if "E011" in getattr(store, "rules", {}) else first_key(getattr(store, "rules", {}))
    adrg_rows = store.search(adrg, "ADRG")
    add_check(
        checks,
        "ADRG exact search",
        bool(adrg_rows) and str(adrg_rows[0].key) == adrg,
        [str(row.key) for row in adrg_rows[:3]],
        adrg,
    )

    table_id = first_key(getattr(store, "tables", {}))
    table_rows = store.search(table_id, "TABLE")
    add_check(
        checks,
        "TABLE exact search",
        bool(table_rows) and str(table_rows[0].key) == table_id,
        [str(row.key) for row in table_rows[:3]],
        table_id,
    )

    code_to_tables = getattr(store, "code_to_tables", {})
    code_candidates = [
        str(code)
        for code in sorted(code_to_tables)
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9]{3,}", str(code))
    ]
    code = code_candidates[0] if code_candidates else first_key(code_to_tables)
    query = dotted_query(code)
    code_rows = store.search(query, "상병코드")
    add_check(
        checks,
        "점 표기 CODE search",
        bool(code_rows) and str(code_rows[0].key) == code,
        {
            "fixture": code,
            "query": query,
            "rows": [str(row.key) for row in code_rows[:3]],
        },
        code,
    )

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()

    search_edit = getattr(window, "search_edit", None)
    category_combo = getattr(window, "category_combo", None)
    run_search = getattr(window, "run_search", None)

    add_check(checks, "MainWindow 생성", window is not None, type(window).__name__, "MainWindow")
    add_check(checks, "검색창 계약", search_edit is not None, bool(search_edit), True)
    add_check(checks, "검색유형 계약", category_combo is not None, bool(category_combo), True)
    add_check(checks, "검색 실행 계약", callable(run_search), callable(run_search), True)

    if search_edit is not None and category_combo is not None and callable(run_search):
        category_combo.setCurrentText("ADRG")
        search_edit.setText(adrg)
        run_search()
        app.processEvents()
        add_check(
            checks,
            "UI ADRG event",
            str(search_edit.text()) == adrg,
            str(search_edit.text()),
            adrg,
        )

        category_combo.setCurrentText("상병코드")
        search_edit.setText(query)
        run_search()
        app.processEvents()
        add_check(
            checks,
            "UI CODE event",
            str(search_edit.text()) == query,
            str(search_edit.text()),
            query,
        )

        category_combo.setCurrentText("TABLE")
        search_edit.setText(table_id)
        run_search()
        app.processEvents()
        add_check(
            checks,
            "UI TABLE event",
            str(search_edit.text()) == table_id,
            str(search_edit.text()),
            table_id,
        )

    status_text = window.statusBar().currentMessage()
    compact_status = re.sub(r"[\s,]", "", status_text)
    add_check(
        checks,
        "상태표시줄 ADRG count",
        "전체ADRG1132개" in compact_status,
        status_text,
        "전체 ADRG 1,132개",
    )
    add_check(
        checks,
        "상태표시줄 TABLE count",
        "TABLE1308개" in compact_status,
        status_text,
        "TABLE 1,308개",
    )
    add_check(
        checks,
        "상태표시줄 CODE count",
        "검색코드16571개" in compact_status,
        status_text,
        "검색코드 16,571개",
    )

    window.close()
    app.processEvents()

    pass_count = sum(item["status"] == "PASS" for item in checks)
    fail_count = sum(item["status"] == "FAIL" for item in checks)
    result = {
        "script_version": SCRIPT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "platform": sys.platform,
        "counts": counts,
        "fixture": {
            "adrg": adrg,
            "table": table_id,
            "code": code,
            "query": query,
        },
        "checks": checks,
        "validation": {
            "status": "PASS" if fail_count == 0 else "FAIL",
            "pass_count": pass_count,
            "fail_count": fail_count,
            "total_count": len(checks),
        },
    }
    REPORT_JSON.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        "KDRG V4.7 Windows runtime source smoke 결과",
        "=" * 72,
        f"스크립트 버전: {SCRIPT_VERSION}",
        f"플랫폼: {sys.platform}",
        "",
        "[집계]",
        f"ADRG/AADRG/TABLE/CODE: {counts['adrg']} / {counts['aadrg']} / {counts['table']} / {counts['code']}",
        "",
        "[검증 항목]",
    ]
    lines.extend(
        f"- [{item['status']}] {item['name']} | actual={item['actual']} | expected={item['expected']}"
        for item in checks
    )
    lines.extend(
        [
            "",
            "[최종 결과]",
            f"PASS: {pass_count}",
            f"FAIL: {fail_count}",
            f"TOTAL: {len(checks)}",
            f"전체 결과: {'PASS' if fail_count == 0 else 'FAIL'}",
        ]
    )
    REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if fail_count:
        print(f"[FAIL] Windows runtime source smoke: {pass_count} PASS / {fail_count} FAIL")
        return 1

    print(f"[PASS] Windows runtime source smoke: {pass_count} PASS / 0 FAIL")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        REPORTS.mkdir(parents=True, exist_ok=True)
        REPORT_TXT.write_text(
            "KDRG V4.7 Windows runtime source smoke 결과\n"
            + "=" * 72
            + f"\n스크립트 버전: {SCRIPT_VERSION}\n\n"
            + "[최종 결과]\n전체 결과: FAIL\n\n"
            + f"[FAIL 상세]\n- {type(exc).__name__}: {exc}\n"
            + traceback.format_exc(),
            encoding="utf-8",
        )
        print(f"[FAIL] Windows runtime source smoke 예외: {type(exc).__name__}: {exc}")
        raise SystemExit(1)
