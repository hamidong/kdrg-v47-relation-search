from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent

BASE_COMMIT = "08b51f4fa487a3ae05c1e279aa1c533f9f3aed52"
BASE_VERSION = "0.5.17"
NEXT_VERSION = "0.5.18"
BASE_TAG = "electron-v0.5.17"

RUNTIME_REL = Path("data/kdrg_v47_search_integrated_v3.json")
RUNTIME_SHA = "1a3d50400567ecaad9695b7be8e7c0382131f8652f398e010cf01f4d8dda6c58"

APP_REL = Path("electron/renderer/app.js")
CSS_REL = Path("electron/renderer/styles.css")
VALIDATOR_REL = Path("electron/tests/validate-stage70b-0518-phase1-ui.js")

REPORT_DIR = ROOT / "reports/stage70b_0518_phase1_ui_shadow_r2"
SHADOW = REPORT_DIR / "shadow"
REPORT_JSON = REPORT_DIR / "shadow.json"
REPORT_TXT = REPORT_DIR / "shadow_summary.txt"

UNCLASSIFIED_ADRGS = [
    "9900", "9990", "D014", "G241", "G242",
    "G650", "K630", "K720", "K730", "R634",
    "R635", "R636", "R637", "R671", "R672",
]


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


def run(cmd, cwd=ROOT, timeout=1200):
    p = subprocess.run(
        [str(x) for x in cmd],
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    return p.returncode, p.stdout


def git_text(*args, cwd=ROOT):
    rc, out = run(["git", *args], cwd=cwd, timeout=120)
    require(rc == 0, f"git {' '.join(args)} 실패\n{out[-3000:]}")
    return out.strip()


def brace_span(source: str, brace_start: int) -> tuple[int, int]:
    require(
        0 <= brace_start < len(source) and source[brace_start] == "{",
        "brace_span 시작점 오류",
    )
    depth = 0
    quote = None
    escape = False
    line_comment = False
    block_comment = False
    i = brace_start

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

        if quote:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
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
                return brace_start, i + 1

        i += 1

    raise Stop("JS brace 종료점을 찾지 못함")


def function_span(source: str, name: str) -> tuple[int, int]:
    marker = f"function {name}"
    start = source.find(marker)
    require(start >= 0, f"function 없음: {name}")
    brace = source.find("{", start)
    require(brace >= 0, f"function 여는 괄호 없음: {name}")
    _, end = brace_span(source, brace)
    return start, end


def function_block(source: str, name: str) -> str:
    a, b = function_span(source, name)
    return source[a:b]


def find_enclosing_if(block: str, marker: str) -> tuple[int, int] | None:
    marker_pos = block.find(marker)
    if marker_pos < 0:
        return None

    starts = [m.start() for m in re.finditer(r"\bif\s*\(", block[:marker_pos])]
    for start in reversed(starts):
        brace = block.find("{", start)
        if brace < 0 or brace > marker_pos:
            continue
        try:
            _, end = brace_span(block, brace)
        except Stop:
            continue
        if start <= marker_pos < end:
            line_start = block.rfind("\n", 0, start) + 1
            line_end = end
            if line_end < len(block) and block[line_end:line_end + 1] == "\n":
                line_end += 1
            return line_start, line_end
    return None


def replace_function(source: str, name: str, new_block: str) -> str:
    a, b = function_span(source, name)
    return source[:a] + new_block + source[b:]


def patch_render_results(source: str) -> str:
    block = function_block(source, "renderResults")
    require(
        "STAGE70B_GENERAL_ADRG_CLASSIFICATION_RIGHT" not in block,
        "Stage70B renderResults marker가 이미 존재함",
    )

    old_span = find_enclosing_if(block, "result-card-classification")
    if old_span is not None:
        a, b = old_span
        block = block[:a] + block[b:]

    subtitle_pattern = re.compile(
        r"(?m)^(?P<indent>[ \t]*)const\s+subtitle\s*=\s*create\(\s*"
        r"'p'\s*,\s*'result-subtitle'\s*,\s*result\.subtitle\s*\)\s*;\s*$"
    )
    subtitle_match = subtitle_pattern.search(block)
    require(subtitle_match is not None, "renderResults subtitle anchor를 찾지 못함")
    indent = subtitle_match.group("indent")

    classification_snippet = (
        f"{indent}/* STAGE70B_GENERAL_ADRG_CLASSIFICATION_RIGHT */\n"
        f"{indent}if (String(result.entity_type ?? '').toUpperCase() === 'ADRG') {{\n"
        f"{indent}  const classification = create(\n"
        f"{indent}    'span',\n"
        f"{indent}    'classification-badge-group result-card-classification',\n"
        f"{indent}  );\n"
        f"{indent}  const classificationValues =\n"
        f"{indent}    (result.summary?.abc_display_labels ?? []).length\n"
        f"{indent}      ? result.summary.abc_display_labels\n"
        f"{indent}      : [\n"
        f"{indent}          result.summary?.classification_code\n"
        f"{indent}            || result.summary?.classification_display_label,\n"
        f"{indent}        ];\n"
        f"{indent}  const classificationCount = appendClassificationBadges(\n"
        f"{indent}    classification,\n"
        f"{indent}    classificationValues,\n"
        f"{indent}  );\n"
        f"{indent}  if (!classificationCount) {{\n"
        f"{indent}    classification.append(\n"
        f"{indent}      makeChip('분류정보 없음', 'classification-unavailable-chip'),\n"
        f"{indent}    );\n"
        f"{indent}  }}\n"
        f"{indent}  main.append(classification);\n"
        f"{indent}}}\n"
    )

    subtitle_replacement = (
        f"{indent}const rawSubtitle = String(result.subtitle ?? '');\n"
        f"{indent}const resultSubtitle = (\n"
        f"{indent}  String(result.entity_type ?? '').toUpperCase() === 'ADRG'\n"
        f"{indent}  && result.summary?.mdc\n"
        f"{indent})\n"
        f"{indent}  ? (() => {{\n"
        f"{indent}      const mdcText = mdcDisplayText(\n"
        f"{indent}        result.summary.mdc,\n"
        f"{indent}        result.summary?.mdc_name,\n"
        f"{indent}      );\n"
        f"{indent}      if (!rawSubtitle) return mdcText;\n"
        f"{indent}      if (/^MDC\\s+[^·]+\\s*·\\s*/.test(rawSubtitle)) {{\n"
        f"{indent}        return rawSubtitle.replace(\n"
        f"{indent}          /^MDC\\s+[^·]+\\s*·\\s*/,\n"
        f"{indent}          `${{mdcText}} · `,\n"
        f"{indent}        );\n"
        f"{indent}      }}\n"
        f"{indent}      if (/^MDC\\s+\\S+/.test(rawSubtitle)) {{\n"
        f"{indent}        return rawSubtitle.replace(/^MDC\\s+\\S+/, mdcText);\n"
        f"{indent}      }}\n"
        f"{indent}      return `${{mdcText}} · ${{rawSubtitle}}`;\n"
        f"{indent}    }})()\n"
        f"{indent}  : rawSubtitle;\n"
        f"{indent}const subtitle = create('p', 'result-subtitle', resultSubtitle);"
    )

    insert_at = subtitle_match.start()
    block = block[:insert_at] + classification_snippet + block[insert_at:]
    block = subtitle_pattern.sub(lambda _m: subtitle_replacement, block, count=1)

    old_append = re.compile(
        r"if\s*\(\s*result\.subtitle\s*\)\s*button\.append\(\s*subtitle\s*\)\s*;"
    )
    require(old_append.search(block) is not None, "renderResults subtitle append anchor를 찾지 못함")
    block = old_append.sub(
        "if (resultSubtitle) button.append(subtitle);",
        block,
        count=1,
    )

    require("=== 'ADRG'" in block, "일반 ADRG classification branch 삽입 실패")
    require("분류정보 없음" in block, "분류정보 없음 fallback 삽입 실패")
    require("mdcDisplayText(" in block, "검색결과 MDC 명칭 renderer 삽입 실패")

    marker_pos = block.index("STAGE70B_GENERAL_ADRG_CLASSIFICATION_RIGHT")
    local = block[marker_pos:marker_pos + 1800]
    require("=== 'AADRG'" not in local, "일반 검색 classification이 AADRG에 잘못 연결됨")

    return replace_function(source, "renderResults", block)


def patch_relation_results(source: str) -> str:
    block = function_block(source, "renderRelationResults")

    if "STAGE69B_RELATION_RESULT_CLASSIFICATION_TITLE_ROW" in block:
        old = re.compile(
            r"if\s*\(\s*relationClassificationCount\s*\)\s*"
            r"main\.append\(\s*relationClassification\s*\)\s*;"
        )
        if old.search(block):
            block = old.sub(
                "if (!relationClassificationCount) "
                "relationClassification.append("
                "makeChip('분류정보 없음', 'classification-unavailable-chip')); "
                "main.append(relationClassification);",
                block,
                count=1,
            )

    candidates = [
        (
            "makeChip(result.summary?.mdc ? `MDC ${result.summary.mdc}` : 'MDC 미확인')",
            "makeChip(result.summary?.mdc "
            "? mdcDisplayText(result.summary.mdc, result.summary?.mdc_name) "
            ": 'MDC 미확인')",
        ),
        (
            "if (result.summary?.mdc) chips.append(makeChip(`MDC ${result.summary.mdc}`));",
            "if (result.summary?.mdc) chips.append("
            "makeChip(mdcDisplayText(result.summary.mdc, result.summary?.mdc_name)));",
        ),
    ]
    for old_text, new_text in candidates:
        if old_text in block:
            block = block.replace(old_text, new_text, 1)
            break

    require("result-card-classification" in block, "복수검색 classification class가 없음")
    return replace_function(source, "renderRelationResults", block)


def patch_adrg_detail(source: str) -> str:
    block = function_block(source, "renderAdrgDetail")

    if "mdcDisplayText(detail.mdc, detail.mdc_name)" not in block:
        patterns = [
            re.compile(
                r"\['MDC',\s*detail\.mdc\s*\?\s*`MDC \$\{detail\.mdc\}`\s*:\s*'-'\]"
            ),
            re.compile(
                r'\["MDC",\s*detail\.mdc\s*\?\s*`MDC \$\{detail\.mdc\}`\s*:\s*"-"\]'
            ),
        ]
        changed = False
        for pat in patterns:
            if pat.search(block):
                block = pat.sub(
                    "['MDC', detail.mdc "
                    "? mdcDisplayText(detail.mdc, detail.mdc_name) : '-']",
                    block,
                    count=1,
                )
                changed = True
                break
        require(changed, "renderAdrgDetail MDC anchor를 찾지 못함")

    require(
        "mdcDisplayText(detail.mdc, detail.mdc_name)" in block,
        "ADRG 상세 MDC 명칭 적용 실패",
    )
    return replace_function(source, "renderAdrgDetail", block)


def patch_app(source: str) -> str:
    require("function mdcDisplayText" in source, "mdcDisplayText helper 없음")
    require(
        "function appendClassificationBadges" in source,
        "classification badge helper 없음",
    )
    source = patch_render_results(source)
    source = patch_relation_results(source)
    source = patch_adrg_detail(source)
    return source


def patch_css(source: str) -> str:
    require(
        "STAGE70B_CLASSIFICATION_RIGHT_ALIGN" not in source,
        "Stage70B CSS marker가 이미 존재함",
    )

    pat = re.compile(
        r"(?ms)(?P<head>\.result-card-classification\s*\{)"
        r"(?P<body>.*?)(?P<tail>\})"
    )
    matches = list(pat.finditer(source))
    require(
        len(matches) == 1,
        f".result-card-classification rule 개수 불일치: {len(matches)}",
    )
    m = matches[0]
    body = m.group("body")

    for prop in (
        "justify-self",
        "margin-left",
        "justify-content",
        "flex-wrap",
        "flex",
    ):
        body = re.sub(
            rf"(?m)^[ \t]*{re.escape(prop)}\s*:\s*[^;]+;\s*\n?",
            "",
            body,
        )

    canonical = (
        "\n"
        "  /* STAGE70B_CLASSIFICATION_RIGHT_ALIGN */\n"
        "  margin-left: auto;\n"
        "  justify-content: flex-end;\n"
        "  flex: 0 0 auto;\n"
        "  flex-wrap: wrap;\n"
    )
    body = body.rstrip() + canonical
    new_rule = m.group("head") + body + "\n" + m.group("tail")
    source = source[:m.start()] + new_rule + source[m.end():]

    if ".classification-unavailable-chip" not in source:
        insertion = (
            "\n.classification-unavailable-chip {\n"
            "  white-space: nowrap;\n"
            "  opacity: 0.78;\n"
            "}\n"
        )
        rule_end = m.start() + len(new_rule)
        source = source[:rule_end] + insertion + source[rule_end:]

    return source


VALIDATOR_JS = r"""'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { KdrgSearchService } = require('../src/kdrg-search-service');

const ROOT = path.resolve(__dirname, '..', '..');
const app = fs.readFileSync(
  path.join(ROOT, 'electron', 'renderer', 'app.js'),
  'utf8',
);
const css = fs.readFileSync(
  path.join(ROOT, 'electron', 'renderer', 'styles.css'),
  'utf8',
);
const service = new KdrgSearchService(
  path.join(ROOT, 'data', 'kdrg_v47_search_integrated_v3.json'),
);

let pass = 0;
const fail = [];

function check(name, fn) {
  try {
    fn();
    pass += 1;
  } catch (error) {
    fail.push(`${name}: ${error.message}`);
  }
}

function functionBody(name) {
  const start = app.indexOf(`function ${name}`);
  assert.ok(start >= 0, `missing function ${name}`);
  const next = app.indexOf('\nfunction ', start + 20);
  return app.slice(start, next >= 0 ? next : app.length);
}

const general = functionBody('renderResults');
const relation = functionBody('renderRelationResults');
const adrgDetail = functionBody('renderAdrgDetail');

check('general ADRG result classification branch', () => {
  assert.match(general, /STAGE70B_GENERAL_ADRG_CLASSIFICATION_RIGHT/);
  assert.match(
    general,
    /String\(result\.entity_type \?\? ''\)\.toUpperCase\(\) === 'ADRG'/,
  );
  const marker = general.indexOf('STAGE70B_GENERAL_ADRG_CLASSIFICATION_RIGHT');
  const local = general.slice(marker, marker + 1800);
  assert.doesNotMatch(local, /=== 'AADRG'/);
  assert.match(local, /abc_display_labels/);
  assert.match(local, /classification_code/);
  assert.match(local, /classification_display_label/);
  assert.match(local, /appendClassificationBadges/);
});

check('general result unclassified explicit fallback', () => {
  assert.match(general, /분류정보 없음/);
  assert.match(general, /classification-unavailable-chip/);
});

check('general result MDC name display', () => {
  assert.match(
    general,
    /mdcDisplayText\(\s*result\.summary\.mdc,\s*result\.summary\?\.mdc_name/,
  );
  assert.match(general, /resultSubtitle/);
});

check('ADRG detail MDC name display', () => {
  assert.match(
    adrgDetail,
    /mdcDisplayText\(detail\.mdc,\s*detail\.mdc_name\)/,
  );
});

check('result classification right alignment CSS', () => {
  const rule = css.match(/\.result-card-classification\s*\{([\s\S]*?)\}/);
  assert.ok(rule, 'result-card-classification rule missing');
  assert.match(rule[1], /margin-left\s*:\s*auto\s*;/);
  assert.match(rule[1], /justify-content\s*:\s*flex-end\s*;/);
  assert.match(rule[1], /flex\s*:\s*0\s+0\s+auto\s*;/);
});

check('relation result classification preserved and shares right class', () => {
  assert.match(relation, /STAGE69B_RELATION_RESULT_CLASSIFICATION_TITLE_ROW/);
  assert.match(relation, /result-card-classification/);
  assert.match(relation, /abc_display_labels/);
  assert.match(relation, /main\.append\(relationClassification\)/);
  assert.match(relation, /분류정보 없음/);
});

check('relation level chip preserved', () => {
  assert.match(relation, /relation_level_label/);
  assert.match(relation, /result-match-chip/);
});

check('relation result MDC helper when MDC is rendered', () => {
  if (/MDC 미확인|summary\?\.mdc/.test(relation)) {
    assert.match(relation, /mdcDisplayText/);
  }
});

const expectedUnclassified = [
  '9900', '9990', 'D014', 'G241', 'G242',
  'G650', 'K630', 'K720', 'K730', 'R634',
  'R635', 'R636', 'R637', 'R671', 'R672',
];

check('ADRG classification runtime coverage', () => {
  const ids = [...service.recordMaps.ADRG.keys()].sort();
  assert.equal(ids.length, 1132);

  let classified = 0;
  const unclassified = [];
  let multi = 0;

  for (const id of ids) {
    const row = service.makeSearchResult(
      'ADRG',
      id,
      1000,
      'EXACT_ID',
      ['entity_id'],
    );
    const labels = Array.isArray(row?.summary?.abc_display_labels)
      ? row.summary.abc_display_labels.filter(Boolean)
      : [];
    const fallback = row?.summary?.classification_code
      || row?.summary?.classification_display_label
      || null;

    if (labels.length || fallback) classified += 1;
    else unclassified.push(id);
    if (labels.length > 1) multi += 1;
  }

  assert.equal(classified, 1117);
  assert.deepEqual(unclassified, expectedUnclassified);
  assert.equal(unclassified.length, 15);
  assert.ok(multi >= 1);
});

check('F111 search result has classification data', () => {
  const response = service.search('F111', 'ADRG', { limit: 10, offset: 0 });
  const row = response.results.find(
    (item) => item.entity_type === 'ADRG' && item.entity_id === 'F111',
  );
  assert.ok(row, 'F111 ADRG result missing');
  const labels = row.summary?.abc_display_labels ?? [];
  const fallback = row.summary?.classification_code
    || row.summary?.classification_display_label;
  assert.ok(labels.length || fallback, 'F111 classification missing');
});

check('0.5.17 exact public-ID contract preserved', () => {
  const response = service.search('F022', 'ALL', { limit: 10, offset: 0 });
  assert.deepEqual(
    response.results.map((row) => `${row.entity_type}:${row.entity_id}`),
    ['CODE:F022', 'ADRG:F022'],
  );
});

check('runtime JSON count contract preserved', () => {
  assert.equal(service.recordMaps.CODE.size, 16571);
  assert.equal(service.recordMaps.ADRG.size, 1132);
});

console.log(
  `[${fail.length ? 'FAIL' : 'PASS'}] Stage70B / 0.5.18 phase1 UI validator: ${pass} PASS / ${fail.length} FAIL`,
);
console.log(
  'classification_runtime=1117 label-present / 15 no-label-data',
);
for (const item of fail) console.log(`- ${item}`);
if (fail.length) process.exitCode = 1;
"""


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "stage": "70B_SHADOW_0518_PHASE1_UI_R2",
        "status": "FAIL",
        "actual_performed": False,
    }

    try:
        head = git_text("rev-parse", "HEAD")
        origin_main = git_text("rev-parse", "origin/main")
        branch = git_text("branch", "--show-current")
        tracked = [
            x for x in git_text("diff", "--name-only", "HEAD").splitlines() if x
        ]
        staged = [
            x for x in git_text("diff", "--cached", "--name-only").splitlines() if x
        ]
        package = json.loads(
            (ROOT / "electron/package.json").read_text(encoding="utf-8")
        )

        require(head == BASE_COMMIT, f"HEAD 불일치: {head}")
        require(origin_main == BASE_COMMIT, f"origin/main 불일치: {origin_main}")
        require(branch == "main", f"branch 불일치: {branch}")
        require(not tracked, f"tracked worktree 변경 있음: {tracked}")
        require(not staged, f"staging 변경 있음: {staged}")
        require(
            package.get("version") == BASE_VERSION,
            "package version != 0.5.17",
        )
        require(
            sha256(ROOT / RUNTIME_REL) == RUNTIME_SHA,
            "운영 JSON SHA 불일치",
        )

        local_tag = git_text("rev-list", "-n", "1", BASE_TAG)
        require(
            local_tag == BASE_COMMIT,
            f"{BASE_TAG} local tag commit 불일치",
        )

        remote_tag_line = git_text(
            "ls-remote",
            "--tags",
            "origin",
            f"refs/tags/{BASE_TAG}",
        )
        require(
            remote_tag_line.startswith(BASE_COMMIT),
            f"{BASE_TAG} remote tag commit 불일치",
        )

        if SHADOW.exists():
            shutil.rmtree(SHADOW)

        rc, out = run(
            [
                "git",
                "clone",
                "--quiet",
                "--no-hardlinks",
                "--local",
                str(ROOT),
                str(SHADOW),
            ],
            timeout=600,
        )
        require(rc == 0, f"Shadow clone 실패\n{out[-3000:]}")
        require(
            git_text("rev-parse", "HEAD", cwd=SHADOW) == BASE_COMMIT,
            "Shadow HEAD 불일치",
        )

        app_path = SHADOW / APP_REL
        css_path = SHADOW / CSS_REL
        validator_path = SHADOW / VALIDATOR_REL

        app_before = app_path.read_text(encoding="utf-8")
        css_before = css_path.read_text(encoding="utf-8")

        app_after = patch_app(app_before)
        css_after = patch_css(css_before)

        require(app_after != app_before, "app.js 변경 없음")
        require(css_after != css_before, "styles.css 변경 없음")

        app_path.write_text(app_after, encoding="utf-8")
        css_path.write_text(css_after, encoding="utf-8")
        validator_path.parent.mkdir(parents=True, exist_ok=True)
        validator_path.write_text(VALIDATOR_JS + "\n", encoding="utf-8")

        for rel in (APP_REL, VALIDATOR_REL):
            rc, output = run(
                ["node", "--check", str(rel.relative_to("electron"))],
                cwd=SHADOW / "electron",
                timeout=120,
            )
            require(
                rc == 0,
                f"node --check FAIL: {rel}\n{output[-3000:]}",
            )

        modified = sorted(
            x
            for x in git_text(
                "diff",
                "--name-only",
                "HEAD",
                "--",
                str(APP_REL),
                str(CSS_REL),
                cwd=SHADOW,
            ).splitlines()
            if x
        )
        require(
            modified == sorted([str(APP_REL), str(CSS_REL)]),
            f"Shadow tracked 변경범위 불일치: {modified}",
        )

        rc, new_status = run(
            ["git", "status", "--short", "--", str(VALIDATOR_REL)],
            cwd=SHADOW,
            timeout=120,
        )
        require(rc == 0, "Stage70B validator git status 실패")
        require(
            new_status.strip() == f"?? {VALIDATOR_REL.as_posix()}",
            f"Stage70B validator 상태 불일치: {new_status.strip()}",
        )

        validations = [
            (
                "stage70b_validator",
                ["node", "tests/validate-stage70b-0518-phase1-ui.js"],
                SHADOW / "electron",
            ),
            (
                "stage69b_validator",
                ["node", "tests/validate-stage69b-0517-search-relation-ux.js"],
                SHADOW / "electron",
            ),
            (
                "stage68d_validator",
                ["node", "tests/validate-stage68d-0516-classification-derived-aadrg.js"],
                SHADOW / "electron",
            ),
            (
                "npm_check",
                ["npm", "run", "check"],
                SHADOW / "electron",
            ),
            (
                "50B",
                ["python", "50B_validate_kdrg_electron_search_service.py"],
                SHADOW,
            ),
            (
                "50C",
                ["python", "50C_validate_kdrg_electron_renderer_ui.py"],
                SHADOW,
            ),
            (
                "50D",
                ["python", "50D_validate_kdrg_electron_windows_packaging.py"],
                SHADOW,
            ),
            (
                "release_version_0517",
                [
                    "node",
                    "tests/validate-release-version.js",
                    BASE_VERSION,
                ],
                SHADOW / "electron",
            ),
        ]

        results = []
        failures = []
        for name, cmd, cwd in validations:
            rc, output = run(cmd, cwd=cwd, timeout=1200)
            results.append(
                {
                    "name": name,
                    "rc": rc,
                    "status": "PASS" if rc == 0 else "FAIL",
                    "tail": output[-8000:],
                }
            )
            if rc != 0:
                failures.append(f"{name} FAIL\n{output[-6000:]}")

        if failures:
            raise Stop(
                "Stage70B Shadow 검증 실패를 전체 실행 후 수집함\n\n"
                + "\n\n".join(failures)
            )

        require(
            sha256(SHADOW / RUNTIME_REL) == RUNTIME_SHA,
            "Shadow 운영 JSON 변경됨",
        )
        require(
            sha256(ROOT / RUNTIME_REL) == RUNTIME_SHA,
            "Actual 운영 JSON 변경됨",
        )

        require(
            (ROOT / APP_REL).read_text(encoding="utf-8") == app_before,
            "Shadow 단계에서 Actual app.js 변경됨",
        )
        require(
            (ROOT / CSS_REL).read_text(encoding="utf-8") == css_before,
            "Shadow 단계에서 Actual styles.css 변경됨",
        )
        require(
            json.loads(
                (ROOT / "electron/package.json").read_text(encoding="utf-8")
            ).get("version")
            == BASE_VERSION,
            "Shadow 단계에서 Actual package version 변경됨",
        )
        require(
            not [
                x
                for x in git_text(
                    "diff",
                    "--cached",
                    "--name-only",
                ).splitlines()
                if x
            ],
            "Shadow 단계에서 Actual staging 변경됨",
        )

        candidate_sha = {
            str(APP_REL): sha256(app_path),
            str(CSS_REL): sha256(css_path),
            str(VALIDATOR_REL): sha256(validator_path),
        }

        report.update(
            {
                "status": "PASS",
                "readiness": "READY_FOR_70C_0518_PHASE1_UI_ACTUAL",
                "head": head,
                "base_version": BASE_VERSION,
                "next_version": NEXT_VERSION,
                "actual_performed": False,
                "runtime_json": "UNCHANGED",
                "shadow_product_files": [
                    str(APP_REL),
                    str(CSS_REL),
                    str(VALIDATOR_REL),
                ],
                "candidate_sha256": candidate_sha,
                "unclassified_adrgs": UNCLASSIFIED_ADRGS,
                "unclassified_policy": (
                    "Do not infer A/B/C. Render neutral '분류정보 없음' "
                    "when no classification source value exists."
                ),
                "layout_policy": {
                    "general_adrg_classification": "RIGHT",
                    "relation_classification": "RIGHT",
                    "shared_class": "result-card-classification",
                    "relation_level_chip": "PRESERVED",
                },
                "mdc_policy": (
                    "Use mdcDisplayText for general ADRG result/detail "
                    "and relation result when rendered."
                ),
                "checks": results,
            }
        )

        REPORT_JSON.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        lines = [
            "[PASS] Stage70B R2 / 0.5.18 1차 UI 마감 Shadow",
            "general_adrg_classification=RIGHT",
            "relation_classification=RIGHT",
            "relation_level_chip=PRESERVED",
            "classified_adrg=1117",
            "no_classification_value_adrg=15",
            "unclassified_display=분류정보 없음",
            "classification_data_inference=NONE",
            "general_result_mdc_name=PASS",
            "adrg_detail_mdc_name=PASS",
            "relation_result_mdc_name=PASS",
            "stage70b_validator=PASS",
            "stage69b_validator=PASS",
            "stage68d_validator=PASS",
            "npm_check=PASS",
            "50B_50C_50D=PASS",
            "release_version_0.5.17=PASS",
            "runtime_json=UNCHANGED",
            "shadow_product_files=3",
            "actual=NOT_PERFORMED",
            "readiness=READY_FOR_70C_0518_PHASE1_UI_ACTUAL",
            f"report={REPORT_TXT.relative_to(ROOT)}",
            f"json={REPORT_JSON.relative_to(ROOT)}",
        ]

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
            "[FAIL] Stage70B 0.5.18 1차 UI 마감 Shadow — Actual 미수행",
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
