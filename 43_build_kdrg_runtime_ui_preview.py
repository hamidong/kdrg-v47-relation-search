from __future__ import annotations

import hashlib
import json
import os
import py_compile
import re
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_VERSION = "2026-07-24_KDRG_V47_RUNTIME_UI_PREVIEW_BUILDER_V3"
EXPECTED_VALIDATOR_VERSION = "2026-07-24_KDRG_V47_PYSIDE_RUNTIME_UI_BRIDGE_VALIDATOR_V4"

ROOT = Path(__file__).resolve().parent
APP_DIR = ROOT / "app"
TOOLS_DIR = ROOT / "tools"
REPORTS_DIR = ROOT / "reports"
PREVIEW_DIR = REPORTS_DIR / "runtime_ui_preview"
SHIM_DIR = REPORTS_DIR / "qt_native_shim"

VALIDATION_REPORT_TXT = REPORTS_DIR / "runtime_ui_bridge_validation_report.txt"
VALIDATION_REPORT_JSON = REPORTS_DIR / "runtime_ui_bridge_validation_report.json"

PREVIEW_RUNNER = TOOLS_DIR / "run_runtime_ui_preview.py"
PREVIEW_RESULT = PREVIEW_DIR / "preview_result.json"
REPORT_TXT = REPORTS_DIR / "runtime_ui_preview_build_report.txt"
REPORT_JSON = REPORTS_DIR / "runtime_ui_preview_build_report.json"

IMMUTABLE_INPUTS = [
    ROOT / "data" / "kdrg_v47_search_integrated.json",
    APP_DIR / "kdrg_search_service.py",
    APP_DIR / "runtime_data_store.py",
    APP_DIR / "main_window.py",
    APP_DIR / "dialogs.py",
]

PREVIEW_RUNNER_SOURCE = 'from __future__ import annotations\n\nimport hashlib\nimport html\nimport json\nimport os\nimport sys\nimport time\nimport traceback\nfrom datetime import datetime, timezone\nfrom pathlib import Path\nfrom typing import Any\n\nROOT = Path(__file__).resolve().parents[1]\nif str(ROOT) not in sys.path:\n    sys.path.insert(0, str(ROOT))\n\nPREVIEW_DIR = ROOT / "reports" / "runtime_ui_preview"\nRESULT_JSON = PREVIEW_DIR / "preview_result.json"\n\nos.environ.setdefault("QT_QPA_PLATFORM", "offscreen")\nos.environ.setdefault("QT_OPENGL", "software")\nos.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")\n\nfrom PySide6.QtCore import QPoint, Qt\nfrom PySide6.QtGui import QImage, QPainter, QPixmap\nfrom PySide6.QtWidgets import QApplication, QComboBox, QLineEdit\n\nfrom app.main_window import MainWindow\n\n\ndef sha256_file(path: Path) -> str:\n    digest = hashlib.sha256()\n    with path.open("rb") as handle:\n        for chunk in iter(lambda: handle.read(1024 * 1024), b""):\n            digest.update(chunk)\n    return digest.hexdigest()\n\n\ndef settle(app: QApplication, rounds: int = 5, delay: float = 0.06) -> None:\n    for _ in range(rounds):\n        app.processEvents()\n        time.sleep(delay)\n\n\ndef get_search_edit(window: MainWindow) -> QLineEdit:\n    widget = getattr(window, "search_edit", None)\n    if isinstance(widget, QLineEdit):\n        return widget\n    for object_name in ("SearchEdit", "searchEdit", "search_input", "searchInput"):\n        found = window.findChild(QLineEdit, object_name)\n        if isinstance(found, QLineEdit):\n            return found\n    edits = window.findChildren(QLineEdit)\n    if edits:\n        return edits[0]\n    raise RuntimeError("검색 입력창을 찾지 못했습니다.")\n\n\ndef get_category_combo(window: MainWindow) -> QComboBox:\n    widget = getattr(window, "category_combo", None)\n    if isinstance(widget, QComboBox):\n        return widget\n    for object_name in ("SearchCombo", "categoryCombo", "search_category"):\n        found = window.findChild(QComboBox, object_name)\n        if isinstance(found, QComboBox):\n            return found\n    combos = window.findChildren(QComboBox)\n    if combos:\n        return combos[0]\n    raise RuntimeError("검색 유형 콤보를 찾지 못했습니다.")\n\n\ndef select_category(combo: QComboBox, candidates: list[str]) -> str:\n    items = [combo.itemText(index) for index in range(combo.count())]\n    normalized_candidates = [candidate.casefold() for candidate in candidates]\n\n    for index, item in enumerate(items):\n        item_fold = item.casefold()\n        if item_fold in normalized_candidates:\n            combo.setCurrentIndex(index)\n            return item\n\n    for index, item in enumerate(items):\n        item_fold = item.casefold()\n        if any(candidate in item_fold or item_fold in candidate for candidate in normalized_candidates):\n            combo.setCurrentIndex(index)\n            return item\n\n    raise RuntimeError(\n        f"검색 유형을 찾지 못했습니다. candidates={candidates}, items={items}"\n    )\n\n\ndef run_search(window: MainWindow, query: str, candidates: list[str]) -> dict[str, Any]:\n    search_edit = get_search_edit(window)\n    category_combo = get_category_combo(window)\n    selected = select_category(category_combo, candidates)\n\n    search_edit.clear()\n    search_edit.setText(query)\n\n    runner = getattr(window, "run_search", None)\n    if not callable(runner):\n        raise RuntimeError("MainWindow.run_search()를 찾지 못했습니다.")\n    runner()\n\n    status_text = ""\n    status_bar = window.statusBar()\n    if status_bar is not None:\n        status_text = status_bar.currentMessage()\n\n    return {\n        "query": query,\n        "selected_category": selected,\n        "status_text": status_text,\n    }\n\n\ndef render_window(window: MainWindow, target: Path) -> dict[str, Any]:\n    target.parent.mkdir(parents=True, exist_ok=True)\n    size = window.size()\n    pixmap = QPixmap(size)\n    pixmap.fill(Qt.GlobalColor.transparent)\n    painter = QPainter(pixmap)\n    try:\n        # PySide6의 QPainter overload는 targetOffset을 명시해야 한다.\n        window.render(painter, QPoint(0, 0))\n    finally:\n        if painter.isActive():\n            painter.end()\n\n    if not pixmap.save(str(target), "PNG"):\n        raise RuntimeError(f"PNG 저장 실패: {target}")\n\n    image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGB32)\n    width = image.width()\n    height = image.height()\n\n    sample_step_x = max(1, width // 80)\n    sample_step_y = max(1, height // 50)\n    sampled_colors: set[int] = set()\n    for y in range(0, height, sample_step_y):\n        for x in range(0, width, sample_step_x):\n            sampled_colors.add(int(image.pixel(x, y)))\n\n    return {\n        "path": str(target),\n        "filename": target.name,\n        "width": width,\n        "height": height,\n        "size_bytes": target.stat().st_size,\n        "sha256": sha256_file(target),\n        "sampled_unique_colors": len(sampled_colors),\n        "non_blank": (\n            width >= 1200\n            and height >= 700\n            and target.stat().st_size >= 10_000\n            and len(sampled_colors) >= 20\n        ),\n    }\n\n\ndef write_index(screenshots: list[dict[str, Any]]) -> Path:\n    index_path = PREVIEW_DIR / "index.html"\n    cards = []\n    for screenshot in screenshots:\n        caption = html.escape(str(screenshot.get("caption", "")))\n        filename = html.escape(str(screenshot["filename"]))\n        query = html.escape(str(screenshot.get("query", "")))\n        category = html.escape(str(screenshot.get("selected_category", "")))\n        cards.append(\n            f"""\n            <section class="card">\n              <h2>{caption}</h2>\n              <p>검색유형: {category or \'-\'} · 검색어: {query or \'-\'}</p>\n              <img src="{filename}" alt="{caption}">\n            </section>\n            """\n        )\n\n    body = "\\n".join(cards)\n    index_path.write_text(\n        f"""<!doctype html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>KDRG V4.7 Runtime UI Preview</title>\n<style>\nbody {{ margin: 0; padding: 24px; font-family: sans-serif; background: #f4f6f8; color: #1f2937; }}\nheader {{ margin-bottom: 24px; }}\n.card {{ background: white; border: 1px solid #d8dee6; border-radius: 12px; padding: 18px; margin-bottom: 24px; }}\n.card h2 {{ margin: 0 0 8px; }}\n.card p {{ margin: 0 0 14px; color: #4b5563; }}\n.card img {{ display: block; width: 100%; height: auto; border: 1px solid #d1d5db; }}\n</style>\n</head>\n<body>\n<header>\n<h1>KDRG V4.7 Runtime UI Preview</h1>\n<p>통합 JSON V2와 KdrgSearchService가 연결된 PySide 화면의 offscreen 캡처입니다.</p>\n</header>\n{body}\n</body>\n</html>\n""",\n        encoding="utf-8",\n    )\n    return index_path\n\n\ndef main() -> int:\n    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)\n\n    result: dict[str, Any] = {\n        "script_version": "2026-07-24_KDRG_V47_RUNTIME_UI_PREVIEW_RUNNER_V2",\n        "created_at": datetime.now(timezone.utc).isoformat(),\n        "screenshots": [],\n        "checks": [],\n        "errors": [],\n    }\n\n    app = QApplication.instance() or QApplication([])\n    window = None\n\n    try:\n        window = MainWindow()\n        window.resize(1700, 1000)\n        window.show()\n        settle(app)\n\n        states = [\n            {\n                "filename": "01_initial.png",\n                "caption": "초기 전체 ADRG 화면",\n                "query": None,\n                "categories": None,\n            },\n            {\n                "filename": "02_adrg_9600.png",\n                "caption": "ADRG 9600 검색",\n                "query": "9600",\n                "categories": ["ADRG"],\n            },\n            {\n                "filename": "03_code_A010.png",\n                "caption": "상병코드 A01.0 검색",\n                "query": "A01.0",\n                "categories": ["상병코드", "CODE", "코드"],\n            },\n            {\n                "filename": "04_table_LT_9610_001.png",\n                "caption": "TABLE LT_9610_001 검색",\n                "query": "LT_9610_001",\n                "categories": ["TABLE", "테이블"],\n            },\n        ]\n\n        for state in states:\n            search_meta: dict[str, Any] = {}\n            if state["query"] is not None:\n                search_meta = run_search(\n                    window,\n                    str(state["query"]),\n                    list(state["categories"] or []),\n                )\n                settle(app)\n\n            screenshot = render_window(window, PREVIEW_DIR / str(state["filename"]))\n            screenshot.update(\n                {\n                    "caption": state["caption"],\n                    "query": search_meta.get("query", ""),\n                    "selected_category": search_meta.get("selected_category", ""),\n                    "status_text": search_meta.get("status_text", ""),\n                }\n            )\n            result["screenshots"].append(screenshot)\n\n        hashes = [item["sha256"] for item in result["screenshots"]]\n        result["checks"] = [\n            {\n                "name": "screenshot_count",\n                "passed": len(result["screenshots"]) == 4,\n                "actual": len(result["screenshots"]),\n                "expected": 4,\n            },\n            {\n                "name": "all_non_blank",\n                "passed": all(item["non_blank"] for item in result["screenshots"]),\n                "actual": [item["non_blank"] for item in result["screenshots"]],\n                "expected": [True, True, True, True],\n            },\n            {\n                "name": "all_states_distinct",\n                "passed": len(set(hashes)) == len(hashes),\n                "actual": len(set(hashes)),\n                "expected": len(hashes),\n            },\n            {\n                "name": "window_title",\n                "passed": bool(window.windowTitle().strip()),\n                "actual": window.windowTitle(),\n                "expected": "non-empty",\n            },\n        ]\n\n        index_path = write_index(result["screenshots"])\n        result["index_html"] = str(index_path)\n        result["index_sha256"] = sha256_file(index_path)\n        result["passed"] = all(check["passed"] for check in result["checks"])\n\n    except Exception as exc:\n        result["passed"] = False\n        result["errors"].append(\n            {\n                "type": type(exc).__name__,\n                "message": str(exc),\n                "traceback": traceback.format_exc(),\n            }\n        )\n    finally:\n        if window is not None:\n            window.close()\n            settle(app, rounds=2, delay=0.02)\n\n    RESULT_JSON.write_text(\n        json.dumps(result, ensure_ascii=False, indent=2),\n        encoding="utf-8",\n    )\n\n    if result.get("passed"):\n        print(\n            "[PASS] runtime UI preview 캡처 완료: "\n            f"{len(result[\'screenshots\'])} screens / "\n            f"{sum(1 for check in result[\'checks\'] if check[\'passed\'])} PASS / 0 FAIL"\n        )\n        return 0\n\n    print("[FAIL] runtime UI preview 캡처 실패")\n    for error in result.get("errors", []):\n        print(error.get("traceback") or error.get("message"))\n    for check in result.get("checks", []):\n        if not check.get("passed"):\n            print(\n                f"- {check.get(\'name\')}: "\n                f"actual={check.get(\'actual\')} expected={check.get(\'expected\')}"\n            )\n    return 1\n\n\nif __name__ == "__main__":\n    raise SystemExit(main())\n'


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"JSON object가 아닙니다: {path}")
    return value


def _match_int(text: str, pattern: str) -> int | None:
    matched = re.search(pattern, text, flags=re.MULTILINE)
    if not matched:
        return None
    return int(matched.group(1))


def read_validation_status() -> tuple[dict[str, Any], bool]:
    """42번 V4 보고서를 JSON 우선·텍스트 보조 방식으로 의미 기반 검증한다."""
    status: dict[str, Any] = {
        "txt_exists": VALIDATION_REPORT_TXT.exists(),
        "json_exists": VALIDATION_REPORT_JSON.exists(),
        "expected_version": EXPECTED_VALIDATOR_VERSION,
        "required_counts": {"pass": 98, "fail": 0, "total": 98},
        "json": {},
        "text": {},
        "source": None,
        "pass": False,
    }

    json_ok = False
    if VALIDATION_REPORT_JSON.exists():
        try:
            payload = load_json(VALIDATION_REPORT_JSON)
            validation = payload.get("validation")
            validation = validation if isinstance(validation, dict) else {}

            json_values = {
                "script_version": str(payload.get("script_version") or ""),
                "status": str(validation.get("status") or ""),
                "pass_count": validation.get("pass_count"),
                "fail_count": validation.get("fail_count"),
                "total_count": validation.get("total_count"),
                "user_judgment_required": validation.get("user_judgment_required"),
            }
            json_ok = (
                json_values["script_version"] == EXPECTED_VALIDATOR_VERSION
                and json_values["status"] == "PASS"
                and json_values["pass_count"] == 98
                and json_values["fail_count"] == 0
                and json_values["total_count"] == 98
                and json_values["user_judgment_required"] in (0, None)
            )
            status["json"] = {**json_values, "pass": json_ok}
        except Exception as exc:
            status["json"] = {
                "pass": False,
                "error": f"{type(exc).__name__}: {exc}",
            }

    text_ok = False
    if VALIDATION_REPORT_TXT.exists():
        try:
            validation_text = VALIDATION_REPORT_TXT.read_text(encoding="utf-8")
            version_match = re.search(
                r"^검증 스크립트 버전:\s*(.+?)\s*$",
                validation_text,
                flags=re.MULTILINE,
            )
            final_match = re.search(
                r"^전체 결과:\s*(PASS|FAIL)\s*$",
                validation_text,
                flags=re.MULTILINE,
            )
            text_values = {
                "script_version": version_match.group(1).strip() if version_match else "",
                "status": final_match.group(1) if final_match else "",
                "pass_count": _match_int(validation_text, r"^PASS:\s*(\d+)\s*$"),
                "fail_count": _match_int(validation_text, r"^FAIL:\s*(\d+)\s*$"),
                "total_count": _match_int(validation_text, r"^TOTAL:\s*(\d+)\s*$"),
                "user_judgment_required": _match_int(
                    validation_text,
                    r"^사용자 판단 필요:\s*(\d+)\s*$",
                ),
            }
            text_ok = (
                text_values["script_version"] == EXPECTED_VALIDATOR_VERSION
                and text_values["status"] == "PASS"
                and text_values["pass_count"] == 98
                and text_values["fail_count"] == 0
                and text_values["total_count"] == 98
                and text_values["user_judgment_required"] in (0, None)
            )
            status["text"] = {**text_values, "pass": text_ok}
        except Exception as exc:
            status["text"] = {
                "pass": False,
                "error": f"{type(exc).__name__}: {exc}",
            }

    status["pass"] = json_ok or text_ok
    status["source"] = (
        "json"
        if json_ok
        else "text"
        if text_ok
        else None
    )
    return status, bool(status["pass"])


def check_item(
    checks: list[dict[str, Any]],
    name: str,
    passed: bool,
    actual: Any,
    expected: Any,
) -> None:
    checks.append(
        {
            "name": name,
            "passed": bool(passed),
            "actual": actual,
            "expected": expected,
        }
    )


def write_reports(report: dict[str, Any]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    passed_count = sum(1 for item in report["checks"] if item["passed"])
    failed_items = [item for item in report["checks"] if not item["passed"]]

    lines = [
        "KDRG V4.7 전체 Runtime UI Preview 구축 결과",
        "=" * 72,
        f"생성시각: {report['created_at']}",
        f"스크립트 버전: {SCRIPT_VERSION}",
        "",
        "[현재 진행 위치]",
        "통합 JSON V2·runtime service·PySide UI bridge 독립검증 완료 후 전체 화면을 실제 렌더링하는 단계",
        "Replit에서는 데스크톱 창을 직접 확인하기 어려우므로 offscreen으로 초기·ADRG·CODE·TABLE 화면을 캡처함",
        "통합 JSON·service·adapter·UI 원본은 수정하지 않음",
        "",
        "[입력 검증]",
        f"42번 독립검증 상태: {report.get('validation_status')}",
        f"qt_native_shim: {SHIM_DIR}",
        f"불변 입력 파일: {len(IMMUTABLE_INPUTS)}개",
        "",
        "[생성 파일]",
        f"preview runner: {PREVIEW_RUNNER}",
        f"preview result: {PREVIEW_RESULT}",
        f"preview index: {report.get('preview_result', {}).get('index_html', '')}",
    ]

    for screenshot in report.get("preview_result", {}).get("screenshots", []):
        lines.append(
            f"- {screenshot.get('caption')}: "
            f"{screenshot.get('filename')} / "
            f"{screenshot.get('width')}x{screenshot.get('height')} / "
            f"{screenshot.get('size_bytes')} bytes / "
            f"colors={screenshot.get('sampled_unique_colors')} / "
            f"non_blank={screenshot.get('non_blank')}"
        )

    lines.extend(
        [
            "",
            "[실행 검증]",
            f"preview runner 종료코드: {report.get('runner_returncode')}",
            (report.get("runner_output") or "").strip(),
            "",
            "[불변성]",
        ]
    )

    for path_text, values in report.get("immutability", {}).items():
        lines.append(
            f"- {path_text}: changed={values.get('changed')} "
            f"before={values.get('before')} after={values.get('after')}"
        )

    lines.extend(
        [
            "",
            "[검증 항목 집계]",
            f"PASS: {passed_count}",
            f"FAIL: {len(failed_items)}",
            f"TOTAL: {len(report['checks'])}",
            "사용자 판단 필요: 0",
            "사용자 수동 Excel 검토: 없음",
            "",
            "[다음 단계]",
            "Preview PASS 후 캡처 이미지에서 실제 가독성·레이아웃을 확인하고 Windows exe 회귀검증 구성을 구축함",
            "Windows 배포에서는 Replit 전용 qt_native_shim을 포함하지 않음",
            "",
            "[최종 결과]",
            f"전체 결과: {'PASS' if not failed_items else 'FAIL'}",
        ]
    )

    if failed_items:
        lines.extend(["", "[FAIL 상세]"])
        for item in failed_items:
            lines.append(
                f"- {item['name']} | actual={item['actual']} | expected={item['expected']}"
            )

    REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    checks: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "script_version": SCRIPT_VERSION,
        "created_at": now_iso(),
        "checks": checks,
        "errors": [],
    }

    try:
        validation_status, validation_ok = read_validation_status()
        report["validation_status"] = validation_status
        check_item(
            checks,
            "A01 42번 독립검증 PASS",
            validation_ok,
            report["validation_status"],
            "VALIDATOR_V4 / PASS 98 / FAIL 0 / TOTAL 98",
        )

        required_paths = [
            *IMMUTABLE_INPUTS,
            VALIDATION_REPORT_TXT,
            SHIM_DIR,
        ]
        for index, path in enumerate(required_paths, start=2):
            check_item(
                checks,
                f"A{index:02d} 필수 경로 {path.relative_to(ROOT)}",
                path.exists(),
                str(path),
                "exists",
            )

        if any(not item["passed"] for item in checks):
            raise RuntimeError("필수 입력 검증에 실패했습니다.")

        before_hashes = {
            str(path.relative_to(ROOT)): sha256_file(path)
            for path in IMMUTABLE_INPUTS
        }

        TOOLS_DIR.mkdir(parents=True, exist_ok=True)
        PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
        PREVIEW_RUNNER.write_text(PREVIEW_RUNNER_SOURCE, encoding="utf-8")
        py_compile.compile(
            str(PREVIEW_RUNNER),
            cfile=str(PREVIEW_DIR / "run_runtime_ui_preview.pyc"),
            doraise=True,
        )

        check_item(
            checks,
            "B01 preview runner 생성",
            PREVIEW_RUNNER.exists(),
            str(PREVIEW_RUNNER),
            "exists",
        )
        check_item(
            checks,
            "B02 preview runner py_compile",
            True,
            "PASS",
            "PASS",
        )

        env = os.environ.copy()
        env.update(
            {
                "LD_LIBRARY_PATH": str(SHIM_DIR),
                "QT_QPA_PLATFORM": "offscreen",
                "QT_OPENGL": "software",
                "LIBGL_ALWAYS_SOFTWARE": "1",
                "PYTHONUNBUFFERED": "1",
            }
        )

        completed = subprocess.run(
            [sys.executable, str(PREVIEW_RUNNER)],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        runner_output = "\n".join(
            part for part in (completed.stdout.strip(), completed.stderr.strip()) if part
        )
        report["runner_returncode"] = completed.returncode
        report["runner_output"] = runner_output

        check_item(
            checks,
            "B03 preview runner 종료코드",
            completed.returncode == 0,
            completed.returncode,
            0,
        )
        check_item(
            checks,
            "B04 preview result 생성",
            PREVIEW_RESULT.exists(),
            str(PREVIEW_RESULT),
            "exists",
        )

        preview_result = load_json(PREVIEW_RESULT) if PREVIEW_RESULT.exists() else {}
        report["preview_result"] = preview_result

        screenshots = preview_result.get("screenshots", [])
        check_item(
            checks,
            "B05 screenshot 4종",
            isinstance(screenshots, list) and len(screenshots) == 4,
            len(screenshots) if isinstance(screenshots, list) else type(screenshots).__name__,
            4,
        )
        check_item(
            checks,
            "B06 screenshot 전체 비공백",
            bool(screenshots) and all(bool(item.get("non_blank")) for item in screenshots),
            [item.get("non_blank") for item in screenshots] if screenshots else [],
            [True, True, True, True],
        )

        screenshot_hashes = [
            str(item.get("sha256", ""))
            for item in screenshots
            if item.get("sha256")
        ]
        check_item(
            checks,
            "B07 화면 상태별 이미지 구분",
            len(screenshot_hashes) == 4 and len(set(screenshot_hashes)) == 4,
            len(set(screenshot_hashes)),
            4,
        )

        index_path_text = str(preview_result.get("index_html", ""))
        index_path = Path(index_path_text) if index_path_text else Path()
        check_item(
            checks,
            "B08 preview HTML index",
            bool(index_path_text) and index_path.exists(),
            index_path_text,
            "exists",
        )
        check_item(
            checks,
            "B09 preview 자체검증",
            bool(preview_result.get("passed")),
            preview_result.get("passed"),
            True,
        )

        after_hashes = {
            str(path.relative_to(ROOT)): sha256_file(path)
            for path in IMMUTABLE_INPUTS
        }
        immutability: dict[str, Any] = {}
        for path_text, before_hash in before_hashes.items():
            after_hash = after_hashes[path_text]
            changed = before_hash != after_hash
            immutability[path_text] = {
                "before": before_hash,
                "after": after_hash,
                "changed": changed,
            }
        report["immutability"] = immutability

        check_item(
            checks,
            "C01 통합 JSON·service·adapter·UI 불변",
            all(not value["changed"] for value in immutability.values()),
            {key: value["changed"] for key, value in immutability.items()},
            "all false",
        )

    except subprocess.TimeoutExpired as exc:
        report["errors"].append(
            {
                "type": "TimeoutExpired",
                "message": str(exc),
                "traceback": traceback.format_exc(),
            }
        )
        check_item(
            checks,
            "Z01 예외 없음",
            False,
            f"TimeoutExpired: {exc}",
            "no exception",
        )
    except Exception as exc:
        report["errors"].append(
            {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            }
        )
        check_item(
            checks,
            "Z01 예외 없음",
            False,
            f"{type(exc).__name__}: {exc}",
            "no exception",
        )

    write_reports(report)

    failed = [item for item in checks if not item["passed"]]
    passed_count = len(checks) - len(failed)

    if failed:
        print(
            "[FAIL] 전체 Runtime UI Preview 구축 실패: "
            f"{passed_count} PASS / {len(failed)} FAIL"
        )
        print(f"report={REPORT_TXT}")
        return 1

    screenshot_count = len(report.get("preview_result", {}).get("screenshots", []))
    print(
        "[PASS] 전체 Runtime UI Preview 구축 완료: "
        f"{screenshot_count} screens / {passed_count} PASS / 0 FAIL"
    )
    print(f"preview={PREVIEW_DIR}")
    print(f"report={REPORT_TXT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
