from __future__ import annotations

import hashlib
import html
import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PREVIEW_DIR = ROOT / "reports" / "runtime_ui_preview"
RESULT_JSON = PREVIEW_DIR / "preview_result.json"

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_OPENGL", "software")
os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit

from app.main_window import MainWindow


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def settle(app: QApplication, rounds: int = 5, delay: float = 0.06) -> None:
    for _ in range(rounds):
        app.processEvents()
        time.sleep(delay)


def get_search_edit(window: MainWindow) -> QLineEdit:
    widget = getattr(window, "search_edit", None)
    if isinstance(widget, QLineEdit):
        return widget
    for object_name in ("SearchEdit", "searchEdit", "search_input", "searchInput"):
        found = window.findChild(QLineEdit, object_name)
        if isinstance(found, QLineEdit):
            return found
    edits = window.findChildren(QLineEdit)
    if edits:
        return edits[0]
    raise RuntimeError("검색 입력창을 찾지 못했습니다.")


def get_category_combo(window: MainWindow) -> QComboBox:
    widget = getattr(window, "category_combo", None)
    if isinstance(widget, QComboBox):
        return widget
    for object_name in ("SearchCombo", "categoryCombo", "search_category"):
        found = window.findChild(QComboBox, object_name)
        if isinstance(found, QComboBox):
            return found
    combos = window.findChildren(QComboBox)
    if combos:
        return combos[0]
    raise RuntimeError("검색 유형 콤보를 찾지 못했습니다.")


def select_category(combo: QComboBox, candidates: list[str]) -> str:
    items = [combo.itemText(index) for index in range(combo.count())]
    normalized_candidates = [candidate.casefold() for candidate in candidates]

    for index, item in enumerate(items):
        item_fold = item.casefold()
        if item_fold in normalized_candidates:
            combo.setCurrentIndex(index)
            return item

    for index, item in enumerate(items):
        item_fold = item.casefold()
        if any(candidate in item_fold or item_fold in candidate for candidate in normalized_candidates):
            combo.setCurrentIndex(index)
            return item

    raise RuntimeError(
        f"검색 유형을 찾지 못했습니다. candidates={candidates}, items={items}"
    )


def run_search(window: MainWindow, query: str, candidates: list[str]) -> dict[str, Any]:
    search_edit = get_search_edit(window)
    category_combo = get_category_combo(window)
    selected = select_category(category_combo, candidates)

    search_edit.clear()
    search_edit.setText(query)

    runner = getattr(window, "run_search", None)
    if not callable(runner):
        raise RuntimeError("MainWindow.run_search()를 찾지 못했습니다.")
    runner()

    status_text = ""
    status_bar = window.statusBar()
    if status_bar is not None:
        status_text = status_bar.currentMessage()

    return {
        "query": query,
        "selected_category": selected,
        "status_text": status_text,
    }


def render_window(window: MainWindow, target: Path) -> dict[str, Any]:
    target.parent.mkdir(parents=True, exist_ok=True)
    size = window.size()
    pixmap = QPixmap(size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    try:
        # PySide6의 QPainter overload는 targetOffset을 명시해야 한다.
        window.render(painter, QPoint(0, 0))
    finally:
        if painter.isActive():
            painter.end()

    if not pixmap.save(str(target), "PNG"):
        raise RuntimeError(f"PNG 저장 실패: {target}")

    image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGB32)
    width = image.width()
    height = image.height()

    sample_step_x = max(1, width // 80)
    sample_step_y = max(1, height // 50)
    sampled_colors: set[int] = set()
    for y in range(0, height, sample_step_y):
        for x in range(0, width, sample_step_x):
            sampled_colors.add(int(image.pixel(x, y)))

    return {
        "path": str(target),
        "filename": target.name,
        "width": width,
        "height": height,
        "size_bytes": target.stat().st_size,
        "sha256": sha256_file(target),
        "sampled_unique_colors": len(sampled_colors),
        "non_blank": (
            width >= 1200
            and height >= 700
            and target.stat().st_size >= 10_000
            and len(sampled_colors) >= 20
        ),
    }


def write_index(screenshots: list[dict[str, Any]]) -> Path:
    index_path = PREVIEW_DIR / "index.html"
    cards = []
    for screenshot in screenshots:
        caption = html.escape(str(screenshot.get("caption", "")))
        filename = html.escape(str(screenshot["filename"]))
        query = html.escape(str(screenshot.get("query", "")))
        category = html.escape(str(screenshot.get("selected_category", "")))
        cards.append(
            f"""
            <section class="card">
              <h2>{caption}</h2>
              <p>검색유형: {category or '-'} · 검색어: {query or '-'}</p>
              <img src="{filename}" alt="{caption}">
            </section>
            """
        )

    body = "\n".join(cards)
    index_path.write_text(
        f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>KDRG V4.7 Runtime UI Preview</title>
<style>
body {{ margin: 0; padding: 24px; font-family: sans-serif; background: #f4f6f8; color: #1f2937; }}
header {{ margin-bottom: 24px; }}
.card {{ background: white; border: 1px solid #d8dee6; border-radius: 12px; padding: 18px; margin-bottom: 24px; }}
.card h2 {{ margin: 0 0 8px; }}
.card p {{ margin: 0 0 14px; color: #4b5563; }}
.card img {{ display: block; width: 100%; height: auto; border: 1px solid #d1d5db; }}
</style>
</head>
<body>
<header>
<h1>KDRG V4.7 Runtime UI Preview</h1>
<p>통합 JSON V2와 KdrgSearchService가 연결된 PySide 화면의 offscreen 캡처입니다.</p>
</header>
{body}
</body>
</html>
""",
        encoding="utf-8",
    )
    return index_path


def main() -> int:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)

    result: dict[str, Any] = {
        "script_version": "2026-07-24_KDRG_V47_RUNTIME_UI_PREVIEW_RUNNER_V2",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "screenshots": [],
        "checks": [],
        "errors": [],
    }

    app = QApplication.instance() or QApplication([])
    window = None

    try:
        window = MainWindow()
        window.resize(1700, 1000)
        window.show()
        settle(app)

        states = [
            {
                "filename": "01_initial.png",
                "caption": "초기 전체 ADRG 화면",
                "query": None,
                "categories": None,
            },
            {
                "filename": "02_adrg_9600.png",
                "caption": "ADRG 9600 검색",
                "query": "9600",
                "categories": ["ADRG"],
            },
            {
                "filename": "03_code_A010.png",
                "caption": "상병코드 A01.0 검색",
                "query": "A01.0",
                "categories": ["상병코드", "CODE", "코드"],
            },
            {
                "filename": "04_table_LT_9610_001.png",
                "caption": "TABLE LT_9610_001 검색",
                "query": "LT_9610_001",
                "categories": ["TABLE", "테이블"],
            },
        ]

        for state in states:
            search_meta: dict[str, Any] = {}
            if state["query"] is not None:
                search_meta = run_search(
                    window,
                    str(state["query"]),
                    list(state["categories"] or []),
                )
                settle(app)

            screenshot = render_window(window, PREVIEW_DIR / str(state["filename"]))
            screenshot.update(
                {
                    "caption": state["caption"],
                    "query": search_meta.get("query", ""),
                    "selected_category": search_meta.get("selected_category", ""),
                    "status_text": search_meta.get("status_text", ""),
                }
            )
            result["screenshots"].append(screenshot)

        hashes = [item["sha256"] for item in result["screenshots"]]
        result["checks"] = [
            {
                "name": "screenshot_count",
                "passed": len(result["screenshots"]) == 4,
                "actual": len(result["screenshots"]),
                "expected": 4,
            },
            {
                "name": "all_non_blank",
                "passed": all(item["non_blank"] for item in result["screenshots"]),
                "actual": [item["non_blank"] for item in result["screenshots"]],
                "expected": [True, True, True, True],
            },
            {
                "name": "all_states_distinct",
                "passed": len(set(hashes)) == len(hashes),
                "actual": len(set(hashes)),
                "expected": len(hashes),
            },
            {
                "name": "window_title",
                "passed": bool(window.windowTitle().strip()),
                "actual": window.windowTitle(),
                "expected": "non-empty",
            },
        ]

        index_path = write_index(result["screenshots"])
        result["index_html"] = str(index_path)
        result["index_sha256"] = sha256_file(index_path)
        result["passed"] = all(check["passed"] for check in result["checks"])

    except Exception as exc:
        result["passed"] = False
        result["errors"].append(
            {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            }
        )
    finally:
        if window is not None:
            window.close()
            settle(app, rounds=2, delay=0.02)

    RESULT_JSON.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if result.get("passed"):
        print(
            "[PASS] runtime UI preview 캡처 완료: "
            f"{len(result['screenshots'])} screens / "
            f"{sum(1 for check in result['checks'] if check['passed'])} PASS / 0 FAIL"
        )
        return 0

    print("[FAIL] runtime UI preview 캡처 실패")
    for error in result.get("errors", []):
        print(error.get("traceback") or error.get("message"))
    for check in result.get("checks", []):
        if not check.get("passed"):
            print(
                f"- {check.get('name')}: "
                f"actual={check.get('actual')} expected={check.get('expected')}"
            )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
