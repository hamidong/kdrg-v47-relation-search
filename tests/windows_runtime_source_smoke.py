#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_OPENGL", "software")
os.environ.setdefault("KDRG_DISABLE_SETTINGS", "1")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPORTS = ROOT / "reports"
REPORT_TXT = REPORTS / "windows_runtime_source_smoke_report.txt"
REPORT_JSON = REPORTS / "windows_runtime_source_smoke_report.json"
SCRIPT_VERSION = "2026-07-27_KDRG_V47_WINDOWS_RUNTIME_SOURCE_SMOKE_V4"


def configure_utf8_stdio() -> None:
    """Windows CI의 cp1252 기본 스트림을 UTF-8로 일반화한다."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None or not hasattr(stream, "reconfigure"):
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
        except (AttributeError, OSError, ValueError):
            pass


def safe_print(*values: Any, sep: str = " ", end: str = "\n") -> None:
    """실패 상세 출력 자체가 원래 회귀검증 오류를 가리지 않게 한다."""
    text = sep.join(str(value) for value in values) + end
    stream = getattr(sys, "stdout", None)
    if stream is None:
        return
    try:
        stream.write(text)
        stream.flush()
        return
    except UnicodeEncodeError:
        pass

    buffer = getattr(stream, "buffer", None)
    if buffer is not None:
        buffer.write(text.encode("utf-8", errors="backslashreplace"))
        buffer.flush()
        return

    encoding = getattr(stream, "encoding", None) or "ascii"
    stream.write(text.encode(encoding, errors="backslashreplace").decode(encoding))
    stream.flush()


configure_utf8_stdio()


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


def normalize_text(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9가-힣]", "", str(value or "")).upper()


def result_keys(rows: Iterable[Any]) -> list[str]:
    return [str(getattr(row, "key", "")) for row in rows]


def has_result_key(rows: Iterable[Any], expected: str) -> bool:
    expected_norm = normalize_text(expected)
    return any(normalize_text(getattr(row, "key", "")) == expected_norm for row in rows)


def dotted_query(code: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]", "", code).upper()
    if len(normalized) > 3:
        return normalized[:3] + "." + normalized[3:]
    return normalized


def choose_searchable_fixture(
    store: Any,
    candidates: Iterable[str],
    category: str,
) -> tuple[str, list[Any]]:
    checked = 0
    for candidate in candidates:
        key = str(candidate or "").strip()
        if not key:
            continue
        checked += 1
        rows = store.search(key, category)
        if has_result_key(rows, key):
            return key, rows
        if checked >= 500:
            break
    return "", []


def choose_code_fixture(store: Any) -> tuple[str, str, list[Any]]:
    type_index = getattr(store, "_code_types_by_code", {})
    candidates = [
        str(code)
        for code in sorted(getattr(store, "code_to_tables", {}))
        if "상병코드" in set(type_index.get(code, set()))
        and re.fullmatch(r"[A-Za-z][A-Za-z0-9]{3,}", str(code))
    ]
    for code in candidates[:1000]:
        query = dotted_query(code)
        rows = store.search(query, "상병코드")
        if has_result_key(rows, code):
            return code, query, rows
    return "", "", []


def print_failed_checks(checks: list[dict[str, Any]]) -> None:
    failed = [item for item in checks if item["status"] == "FAIL"]
    if not failed:
        return
    safe_print("[FAIL 상세]")
    for item in failed:
        safe_print(
            f"- {item['name']} | "
            f"actual={item['actual']} | expected={item['expected']}"
        )


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    checks: list[dict[str, Any]] = []

    from PySide6.QtWidgets import QApplication, QLabel, QToolButton
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
    add_check(
        checks,
        "service status",
        isinstance(status, dict),
        type(status).__name__,
        "dict",
    )

    store = KDRGRuntimeDataStore()
    runtime_counts = dict(getattr(store, "runtime_counts", {}) or {})
    counts = {
        "adrg": len(getattr(store, "rules", {})),
        "aadrg": int(runtime_counts.get("aadrg_records", 0) or 0),
        "rdrg": int(runtime_counts.get("rdrg_records", 0) or 0),
        "table": len(getattr(store, "tables", {})),
        "code": len(getattr(store, "code_to_tables", {})),
    }

    add_check(checks, "ADRG count", counts["adrg"] == 1132, counts["adrg"], 1132)
    add_check(checks, "AADRG count", counts["aadrg"] == 1233, counts["aadrg"], 1233)
    add_check(checks, "RDRG count", counts["rdrg"] == 2699, counts["rdrg"], 2699)
    add_check(checks, "TABLE count", counts["table"] == 1308, counts["table"], 1308)
    add_check(checks, "CODE count", counts["code"] == 16571, counts["code"], 16571)

    semantic_counts = dict(status.get("semantic_context_counts") or {})
    expected_semantic_counts = {
        "relationship_occurrence_count": 939,
        "include_occurrence": 874,
        "exclude_occurrence": 65,
        "exclusion_base_occurrence": 28,
        "exclusion_excluded_occurrence": 65,
        "exclusion_excluded_final_include": 19,
        "legacy_misclassification_occurrence": 47,
    }
    for key, expected in expected_semantic_counts.items():
        actual = int(semantic_counts.get(key, -1))
        add_check(checks, f"UI 의미 polarity {key}", actual == expected, actual, expected)

    e011_groups = store.rules["E011"].condition_groups
    e011_positive = [component.table_id for group in e011_groups for component in group.components]
    e011_negative = [component.table_id for group in e011_groups for component in group.exclude_components]
    add_check(
        checks,
        "E011 EXCLUSION base 포함",
        "LT_E011_002" in e011_positive and "LT_E011_002" not in e011_negative,
        {"positive": e011_positive, "negative": e011_negative},
        "LT_E011_002 include only",
    )
    add_check(
        checks,
        "E011 EXCLUSION excluded 제외",
        e011_negative == ["LT_E011_003"],
        e011_negative,
        ["LT_E011_003"],
    )

    rule_9610 = store.rules["9610"]
    coverage_9610 = store.condition_coverage_for_adrg("9610")
    add_check(
        checks,
        "9610 기본 TABLE과 추가조건 분리",
        coverage_9610.get("basic_table_ids") == ["LT_9610_001"]
        and not coverage_9610.get("has_condition_ast")
        and not rule_9610.condition_groups,
        {"coverage": coverage_9610, "group_count": len(rule_9610.condition_groups)},
        "basic LT_9610_001 + no extra condition",
    )

    groups_9620 = store.rules["9620"].condition_groups
    positive_9620 = [component.table_id for group in groups_9620 for component in group.components]
    negative_9620 = [component.table_id for group in groups_9620 for component in group.exclude_components]
    add_check(
        checks,
        "9620 포함·제외 역할",
        positive_9620 == ["LT_9620_001"] and negative_9620 == ["LT_9620_002"],
        {"positive": positive_9620, "negative": negative_9620},
        {"positive": ["LT_9620_001"], "negative": ["LT_9620_002"]},
    )

    table_categories = {
        "LT_9610_001": (store.table_category("LT_9610_001"), store.tables["LT_9610_001"].code_type),
        "LT_9620_001": (store.table_category("LT_9620_001"), store.tables["LT_9620_001"].code_type),
        "LT_9620_002": (store.table_category("LT_9620_002"), store.tables["LT_9620_002"].code_type),
    }
    add_check(
        checks,
        "TABLE 유형 중립·근거기반 분류",
        table_categories == {
            "LT_9610_001": ("unknown", "코드(유형 미확정)"),
            "LT_9620_001": ("diagnosis", "상병코드"),
            "LT_9620_002": ("procedure", "수술·처치코드"),
        },
        table_categories,
        "contract categories",
    )

    all_name_empty = all(
        not member.name_ko and not member.name_en
        for table in store.tables.values()
        for member in table.members
    )
    add_check(checks, "코드명 미수록 상태 보존", all_name_empty, all_name_empty, True)

    adrg_candidates = [
        "E011",
        *sorted(str(key) for key in getattr(store, "rules", {})),
    ]
    adrg, adrg_rows = choose_searchable_fixture(store, adrg_candidates, "ADRG")
    add_check(
        checks,
        "ADRG searchable fixture",
        bool(adrg) and has_result_key(adrg_rows, adrg),
        {
            "fixture": adrg,
            "rows": result_keys(adrg_rows[:5]),
        },
        "current ADRG corpus에서 exact 검색 가능한 fixture",
    )

    table_candidates = [
        "LT_9610_001",
        *sorted(str(key) for key in getattr(store, "tables", {})),
    ]
    table_id, table_rows = choose_searchable_fixture(
        store,
        table_candidates,
        "TABLE",
    )
    add_check(
        checks,
        "TABLE searchable fixture",
        bool(table_id) and has_result_key(table_rows, table_id),
        {
            "fixture": table_id,
            "rows": result_keys(table_rows[:5]),
        },
        "current TABLE corpus에서 exact 검색 가능한 fixture",
    )

    code, query, code_rows = choose_code_fixture(store)
    add_check(
        checks,
        "점 표기 CODE searchable fixture",
        bool(code) and bool(query) and has_result_key(code_rows, code),
        {
            "fixture": code,
            "query": query,
            "rows": result_keys(code_rows[:5]),
        },
        "상병코드 corpus에서 점 표기 exact 검색 가능한 fixture",
    )

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()

    search_edit = getattr(window, "search_edit", None)
    category_combo = getattr(window, "category_combo", None)
    run_search = getattr(window, "run_search", None)

    add_check(
        checks,
        "MainWindow 생성",
        window is not None,
        type(window).__name__,
        "MainWindow",
    )
    add_check(
        checks,
        "검색창 계약",
        search_edit is not None,
        type(search_edit).__name__ if search_edit is not None else None,
        "QLineEdit",
    )
    add_check(
        checks,
        "검색유형 계약",
        category_combo is not None,
        type(category_combo).__name__ if category_combo is not None else None,
        "QComboBox",
    )
    add_check(
        checks,
        "검색 실행 계약",
        callable(run_search),
        callable(run_search),
        True,
    )

    initial_status = window.statusBar().currentMessage()
    compact_status = re.sub(r"[\s,]", "", initial_status)
    add_check(
        checks,
        "상태표시줄 ADRG count",
        "전체ADRG1132개" in compact_status,
        initial_status,
        "전체 ADRG 1,132개",
    )
    add_check(
        checks,
        "상태표시줄 AADRG count",
        "AADRG1233개" in compact_status,
        initial_status,
        "AADRG 1,233개",
    )
    add_check(
        checks,
        "상태표시줄 TABLE count",
        "TABLE1308개" in compact_status,
        initial_status,
        "TABLE 1,308개",
    )
    add_check(
        checks,
        "상태표시줄 CODE count",
        "검색코드16571개" in compact_status,
        initial_status,
        "검색코드 16,571개",
    )

    if (
        search_edit is not None
        and category_combo is not None
        and callable(run_search)
    ):
        category_combo.setCurrentText("ADRG")
        search_edit.setText(adrg)
        run_search()
        app.processEvents()
        ui_adrg_rows = list(getattr(window, "current_results", []))
        add_check(
            checks,
            "UI ADRG 결과",
            has_result_key(ui_adrg_rows, adrg),
            {
                "query": search_edit.text(),
                "rows": result_keys(ui_adrg_rows[:5]),
            },
            adrg,
        )

        category_combo.setCurrentText("상병코드")
        search_edit.setText(query)
        run_search()
        app.processEvents()
        ui_code_rows = list(getattr(window, "current_results", []))
        add_check(
            checks,
            "UI CODE 결과",
            has_result_key(ui_code_rows, code),
            {
                "query": search_edit.text(),
                "rows": result_keys(ui_code_rows[:5]),
            },
            code,
        )

        category_combo.setCurrentText("TABLE")
        search_edit.setText(table_id)
        run_search()
        app.processEvents()
        ui_table_rows = list(getattr(window, "current_results", []))
        add_check(
            checks,
            "UI TABLE 결과",
            has_result_key(ui_table_rows, table_id),
            {
                "query": search_edit.text(),
                "rows": result_keys(ui_table_rows[:5]),
            },
            table_id,
        )

    window.render_rule_detail("E011")
    app.processEvents()
    e011_labels = [label.text() for label in window.detail_container.findChildren(QLabel)]
    add_check(
        checks,
        "UI E011 제외 문구",
        "단, 다음 대상은 제외" in e011_labels,
        [text for text in e011_labels if "제외" in text],
        "단, 다음 대상은 제외",
    )
    add_check(
        checks,
        "UI 기술식 기본 접힘",
        all(not button.isChecked() for button in window.detail_container.findChildren(QToolButton) if button.text() == "기술식 보기"),
        [button.isChecked() for button in window.detail_container.findChildren(QToolButton) if button.text() == "기술식 보기"],
        "all False",
    )

    window.render_rule_detail("9610")
    app.processEvents()
    labels_9610 = [label.text() for label in window.detail_container.findChildren(QLabel)]
    add_check(
        checks,
        "UI 9610 추가조건 문구",
        "별도의 추가 분기조건 없음" in labels_9610
        and not any("본문 조건 AST 없음" in text for text in labels_9610),
        [text for text in labels_9610 if "조건" in text],
        "별도의 추가 분기조건 없음",
    )

    from app.main_window import CodeTableFrame

    frame_9610 = CodeTableFrame(store.tables["LT_9610_001"])
    frame_9610.ensure_populated()
    headers_9610 = [
        frame_9610.table.horizontalHeaderItem(index).text()
        for index in range(frame_9610.table.columnCount())
    ]
    add_check(
        checks,
        "UI 코드명 없는 TABLE 단일 열",
        frame_9610.table.columnCount() == 1 and headers_9610 == ["코드"],
        {"count": frame_9610.table.columnCount(), "headers": headers_9610},
        {"count": 1, "headers": ["코드"]},
    )

    frame_diagnosis = CodeTableFrame(store.tables["LT_9620_001"])
    frame_diagnosis.ensure_populated()
    diagnosis_headers = [
        frame_diagnosis.table.horizontalHeaderItem(index).text()
        for index in range(frame_diagnosis.table.columnCount())
    ]
    add_check(
        checks,
        "UI 진단 TABLE 코드 열 명칭",
        diagnosis_headers == ["상병코드"],
        diagnosis_headers,
        ["상병코드"],
    )

    frame_procedure = CodeTableFrame(store.tables["LT_9620_002"])
    frame_procedure.ensure_populated()
    procedure_headers = [
        frame_procedure.table.horizontalHeaderItem(index).text()
        for index in range(frame_procedure.table.columnCount())
    ]
    add_check(
        checks,
        "UI 시술 TABLE 코드 열 명칭",
        procedure_headers == ["처치코드"],
        procedure_headers,
        ["처치코드"],
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
            "user_judgment_required": 0,
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
        (
            "ADRG/AADRG/RDRG/TABLE/CODE: "
            f"{counts['adrg']} / {counts['aadrg']} / {counts['rdrg']} / "
            f"{counts['table']} / {counts['code']}"
        ),
        "",
        "[동적 fixture]",
        f"ADRG: {adrg}",
        f"TABLE: {table_id}",
        f"CODE: {code} → {query}",
        "",
        "[검증 항목]",
    ]
    lines.extend(
        f"- [{item['status']}] {item['name']} | "
        f"actual={item['actual']} | expected={item['expected']}"
        for item in checks
    )
    lines.extend(
        [
            "",
            "[최종 결과]",
            f"PASS: {pass_count}",
            f"FAIL: {fail_count}",
            f"TOTAL: {len(checks)}",
            "사용자 판단 필요: 0",
            f"전체 결과: {'PASS' if fail_count == 0 else 'FAIL'}",
        ]
    )
    REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if fail_count:
        safe_print(
            f"[FAIL] Windows runtime source smoke: "
            f"{pass_count} PASS / {fail_count} FAIL"
        )
        print_failed_checks(checks)
        safe_print(f"report={REPORT_TXT}")
        return 1

    safe_print(
        f"[PASS] Windows runtime source smoke: "
        f"{pass_count} PASS / 0 FAIL"
    )
    safe_print(f"report={REPORT_TXT}")
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
        safe_print(
            f"[FAIL] Windows runtime source smoke 예외: "
            f"{type(exc).__name__}: {exc}"
        )
        safe_print(traceback.format_exc())
        safe_print(f"report={REPORT_TXT}")
        raise SystemExit(1)
