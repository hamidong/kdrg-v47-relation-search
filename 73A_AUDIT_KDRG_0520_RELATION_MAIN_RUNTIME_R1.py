from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent

BASE_COMMIT = "108e959c02eb88acc519d6be3094e380935793c5"
BASE_VERSION = "0.5.19"
BASE_TAG = "electron-v0.5.19"
RUNTIME_REL = Path("data/kdrg_v47_search_integrated_v3.json")
RUNTIME_SHA = "1a3d50400567ecaad9695b7be8e7c0382131f8652f398e010cf01f4d8dda6c58"

APP = ROOT / "electron/renderer/app.js"
VALIDATOR_72B = ROOT / "electron/tests/validate-stage72b-0519-relation-result-layout.js"

REPORT_DIR = ROOT / "reports/stage73a_0520_relation_main_runtime_audit_r1"
REPORT_JSON = REPORT_DIR / "audit.json"
REPORT_TXT = REPORT_DIR / "audit_summary.txt"


class Stop(RuntimeError):
    pass


def require(ok, message):
    if not ok:
        raise Stop(message)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def run(cmd, cwd=ROOT, timeout=120):
    p = subprocess.run(
        [str(x) for x in cmd],
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    return p.returncode, p.stdout


def git_text(*args):
    rc, out = run(["git", *args])
    require(rc == 0, f"git {' '.join(args)} 실패\n{out[-2500:]}")
    return out.strip()


def find_function_span(source: str, name: str) -> tuple[int, int]:
    marker = f"function {name}"
    start = source.find(marker)
    require(start >= 0, f"function 없음: {name}")

    brace = source.find("{", start)
    require(brace >= 0, f"여는 괄호 없음: {name}")

    depth = 0
    quote = None
    escaped = False
    line_comment = False
    block_comment = False
    i = brace

    while i < len(source):
        ch = source[i]
        nxt = source[i + 1] if i + 1 < len(source) else ""

        if line_comment:
            if ch == "\n":
                line_comment = False
            i += 1
            continue

        if block_comment:
            if ch == "*" and nxt == "/":
                block_comment = False
                i += 2
                continue
            i += 1
            continue

        if quote is not None:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
            i += 1
            continue

        if ch == "/" and nxt == "/":
            line_comment = True
            i += 2
            continue

        if ch == "/" and nxt == "*":
            block_comment = True
            i += 2
            continue

        if ch in ("'", '"', "`"):
            quote = ch
            i += 1
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1

        i += 1

    raise Stop(f"닫는 괄호 탐색 실패: {name}")


def block_paths(source: str):
    """Return lexical block stack at each interesting character offset."""
    stack = []
    next_id = 0
    paths = {}

    quote = None
    escaped = False
    line_comment = False
    block_comment = False
    i = 0

    while i < len(source):
        paths[i] = tuple(stack)
        ch = source[i]
        nxt = source[i + 1] if i + 1 < len(source) else ""

        if line_comment:
            if ch == "\n":
                line_comment = False
            i += 1
            continue

        if block_comment:
            if ch == "*" and nxt == "/":
                block_comment = False
                i += 2
                continue
            i += 1
            continue

        if quote is not None:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
            i += 1
            continue

        if ch == "/" and nxt == "/":
            line_comment = True
            i += 2
            continue

        if ch == "/" and nxt == "*":
            block_comment = True
            i += 2
            continue

        if ch in ("'", '"', "`"):
            quote = ch
            i += 1
            continue

        if ch == "{":
            next_id += 1
            stack.append(next_id)
        elif ch == "}":
            if stack:
                stack.pop()

        i += 1

    paths[len(source)] = tuple(stack)
    return paths


def nearest_path(paths, pos: int):
    while pos >= 0:
        if pos in paths:
            return paths[pos]
        pos -= 1
    return ()


def line_no(source: str, pos: int) -> int:
    return source.count("\n", 0, pos) + 1


def prefix_scope(decl_path, use_path):
    return len(decl_path) <= len(use_path) and tuple(use_path[:len(decl_path)]) == tuple(decl_path)


def analyze_identifier_scope(block: str, identifier: str):
    paths = block_paths(block)

    decl_pattern = re.compile(rf"\b(?:const|let)\s+{re.escape(identifier)}\b")
    use_pattern = re.compile(rf"\b{re.escape(identifier)}\s*\.")

    declarations = []
    for m in decl_pattern.finditer(block):
        declarations.append({
            "pos": m.start(),
            "line": line_no(block, m.start()),
            "path": nearest_path(paths, m.start()),
            "text": block[m.start(): block.find("\n", m.start()) if "\n" in block[m.start():] else len(block)].strip(),
        })

    uses = []
    for m in use_pattern.finditer(block):
        visible = []
        use_path = nearest_path(paths, m.start())
        for decl in declarations:
            if decl["pos"] < m.start() and prefix_scope(decl["path"], use_path):
                visible.append(decl)

        uses.append({
            "pos": m.start(),
            "line": line_no(block, m.start()),
            "path": use_path,
            "visible_declarations": [
                {"line": x["line"], "path": list(x["path"])}
                for x in visible
            ],
            "safe": bool(visible),
            "text": block[m.start(): block.find("\n", m.start()) if "\n" in block[m.start():] else len(block)].strip(),
        })

    return declarations, uses


def snippet_with_lines(source: str, start_line: int, end_line: int):
    lines = source.splitlines()
    start_line = max(1, start_line)
    end_line = min(len(lines), end_line)
    return [
        f"{i:04d}: {lines[i-1]}"
        for i in range(start_line, end_line + 1)
    ]


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    report = {
        "stage": "73A_0520_RELATION_MAIN_RUNTIME_AUDIT_R1",
        "status": "FAIL",
        "mutated": False,
    }

    try:
        head = git_text("rev-parse", "HEAD")
        origin_main = git_text("rev-parse", "origin/main")
        branch = git_text("branch", "--show-current")
        staged = [
            x for x in git_text("diff", "--cached", "--name-only").splitlines()
            if x
        ]

        require(head == BASE_COMMIT, f"HEAD 불일치: {head}")
        require(origin_main == BASE_COMMIT, f"origin/main 불일치: {origin_main}")
        require(branch == "main", f"branch 불일치: {branch}")
        require(not staged, f"staging 변경 있음: {staged}")

        package = json.loads(
            (ROOT / "electron/package.json").read_text(encoding="utf-8")
        )
        require(
            package.get("version") == BASE_VERSION,
            f"package version 불일치: {package.get('version')}",
        )
        require(
            sha256(ROOT / RUNTIME_REL) == RUNTIME_SHA,
            "운영 JSON SHA 불일치",
        )
        require(APP.is_file(), "electron/renderer/app.js 없음")
        require(VALIDATOR_72B.is_file(), "Stage72B validator 없음")

        app = APP.read_text(encoding="utf-8")
        validator = VALIDATOR_72B.read_text(encoding="utf-8")

        start, end = find_function_span(app, "renderRelationResults")
        block = app[start:end]
        global_start_line = line_no(app, start)

        main_decls, main_uses = analyze_identifier_scope(block, "main")
        rel_decls, rel_uses = analyze_identifier_scope(block, "relationClassification")

        unsafe_main = [x for x in main_uses if not x["safe"]]
        unsafe_relation = [x for x in rel_uses if not x["safe"]]

        stage72_marker = "STAGE72B_RELATION_CLASSIFICATION_TOP_RIGHT_R4" in block
        stage69_marker = "STAGE69B_RELATION_RESULT_CLASSIFICATION_TITLE_ROW" in block
        relation_chip_removed = "result-match-chip" not in block
        classification_present = (
            "result-card-classification" in block
            and "main.append(relationClassification)" in block
        )

        # The 0.5.19 validator was static-string based if it extracts function text
        # but never invokes renderRelationResults itself.
        static_function_body = "functionBody('renderRelationResults')" in validator
        invokes_renderer = bool(
            re.search(
                r"(?<!functionBody\(['\"])\brenderRelationResults\s*\(",
                validator,
            )
        )
        runtime_smoke_coverage = invokes_renderer

        focus_lines = []
        focus_local = []

        for item in unsafe_main:
            focus_local.append(item["line"])
        for token in (
            "const main",
            "main.append(relationClassification)",
            "STAGE72B_RELATION_CLASSIFICATION_TOP_RIGHT_R4",
            "STAGE69B_RELATION_RESULT_CLASSIFICATION_TITLE_ROW",
        ):
            p = block.find(token)
            if p >= 0:
                focus_local.append(line_no(block, p))

        if focus_local:
            lo = max(1, min(focus_local) - 5)
            hi = max(focus_local) + 8
            focus_lines = snippet_with_lines(
                block,
                lo,
                hi,
            )

        scope_error_confirmed = bool(unsafe_main)
        if scope_error_confirmed:
            readiness = "READY_FOR_73B_0520_RELATION_MAIN_SCOPE_FIX_SHADOW"
            root_cause = (
                "renderRelationResults 내부에서 `main.` 사용 중 하나 이상이 "
                "`const main`의 lexical block 밖에서 실행되는 구조"
            )
        else:
            readiness = "READY_FOR_73B_0520_RELATION_RUNTIME_PROBE"
            root_cause = (
                "정적 lexical scope만으로는 `main is not defined` 원인이 확정되지 않음; "
                "실행형 DOM runtime probe 필요"
            )

        report.update({
            "status": "PASS",
            "head": head,
            "origin_main": origin_main,
            "package_version": BASE_VERSION,
            "runtime_json": "UNCHANGED",
            "stage72_marker": stage72_marker,
            "stage69_marker": stage69_marker,
            "relation_chip_removed": relation_chip_removed,
            "classification_present": classification_present,
            "main_declarations": main_decls,
            "main_uses": main_uses,
            "unsafe_main_uses": unsafe_main,
            "relation_classification_declarations": rel_decls,
            "relation_classification_uses": rel_uses,
            "unsafe_relation_classification_uses": unsafe_relation,
            "validator_static_function_body": static_function_body,
            "validator_invokes_renderRelationResults": invokes_renderer,
            "runtime_smoke_coverage": runtime_smoke_coverage,
            "scope_error_confirmed": scope_error_confirmed,
            "root_cause": root_cause,
            "function_start_line": global_start_line,
            "focus_snippet": focus_lines,
            "readiness": readiness,
            "mutated": False,
        })

        REPORT_JSON.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        lines = [
            "[PASS] Stage73A R1 / 0.5.20 relation main runtime audit",
            f"base_commit={head}",
            f"package_version={BASE_VERSION}",
            f"stage72_marker={stage72_marker}",
            f"stage69_marker={stage69_marker}",
            f"relation_chip_removed={relation_chip_removed}",
            f"classification_present={classification_present}",
            f"main_declarations={len(main_decls)}",
            f"main_uses={len(main_uses)}",
            f"unsafe_main_uses={len(unsafe_main)}",
            f"unsafe_relation_classification_uses={len(unsafe_relation)}",
            f"validator_static_function_body={static_function_body}",
            f"validator_invokes_renderRelationResults={invokes_renderer}",
            f"runtime_smoke_coverage={'YES' if runtime_smoke_coverage else 'NO'}",
            f"scope_error_confirmed={'YES' if scope_error_confirmed else 'NO'}",
            f"root_cause={root_cause}",
            "runtime_json=UNCHANGED",
            "mutated=NO",
            f"readiness={readiness}",
            f"report={REPORT_TXT.relative_to(ROOT)}",
            f"json={REPORT_JSON.relative_to(ROOT)}",
        ]

        if focus_lines:
            lines.append("---- renderRelationResults focus ----")
            lines.extend(focus_lines)

        REPORT_TXT.write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )
        print("\n".join(lines))
        return 0

    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        REPORT_JSON.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        lines = [
            "[FAIL] Stage73A relation main runtime audit — 제품 수정 없음",
            f"{type(exc).__name__}: {exc}",
            f"report={REPORT_TXT.relative_to(ROOT)}",
        ]
        REPORT_TXT.write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )
        print("\n".join(lines))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
