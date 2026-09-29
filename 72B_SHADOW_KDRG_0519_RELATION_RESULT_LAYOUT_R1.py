from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent

BASE_COMMIT = "1bd70d50c85305e2ff64ebb0a17ec619719e8a40"
BASE_VERSION = "0.5.18"
NEXT_VERSION = "0.5.19"
BASE_TAG = "electron-v0.5.18"

RUNTIME_REL = Path("data/kdrg_v47_search_integrated_v3.json")
RUNTIME_SHA = "1a3d50400567ecaad9695b7be8e7c0382131f8652f398e010cf01f4d8dda6c58"

AUDIT_SCRIPT = ROOT / "72A_AUDIT_KDRG_0519_RELATION_RESULT_LAYOUT_R1.py"
AUDIT_SCRIPT_SHA = "36d810fca9edec4e4f635144b054f3beaf553fd064ad7c5bae204deb1cc2e528"
AUDIT_REPORT = ROOT / "reports/stage72a_0519_relation_result_layout_audit_r1/audit.json"

APP_REL = Path("electron/renderer/app.js")
CSS_REL = Path("electron/renderer/styles.css")
OLD_VALIDATOR_REL = Path("electron/tests/validate-stage70b-0518-phase1-ui.js")
NEW_VALIDATOR_REL = Path("electron/tests/validate-stage72b-0519-relation-result-layout.js")

REPORT_DIR = ROOT / "reports/stage72b_0519_relation_result_layout_shadow_r1"
SHADOW = REPORT_DIR / "shadow"
REPORT_JSON = REPORT_DIR / "shadow.json"
REPORT_TXT = REPORT_DIR / "shadow_summary.txt"

PRODUCT_FILES = [
    APP_REL,
    CSS_REL,
    OLD_VALIDATOR_REL,
    NEW_VALIDATOR_REL,
]

EXPECTED_TRACKED = sorted(str(x) for x in [
    APP_REL,
    CSS_REL,
    OLD_VALIDATOR_REL,
])

EXPECTED_UNTRACKED = [str(NEW_VALIDATOR_REL)]


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
        "brace 시작점 오류",
    )

    depth = 0
    quote = None
    escaped = False
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


def replace_function(source: str, name: str, new_block: str) -> str:
    a, b = function_span(source, name)
    return source[:a] + new_block + source[b:]


def patch_relation_counts(source: str) -> str:
    old = function_block(source, "renderRelationCounts")
    require(
        "STAGE72B_RELATION_SUMMARY" not in old,
        "Stage72B relation summary marker가 이미 존재함",
    )
    require(
        "같은 선택지" in old
        and "다른 선택지" in old
        and "일부 연결" in old
        and "relation-${level}-chip" in old,
        "현재 relation count chip 구조 불일치",
    )

    new = r"""function renderRelationCounts(response) {
  const container = byId('type-counts');
  container.replaceChildren();

  /* STAGE72B_RELATION_SUMMARY */
  const labels = {
    strict: '같은 선택지',
    split: '다른 선택지',
    partial: '일부 연결',
  };
  const scopes = {
    strict: '공통 관련 ADRG',
    split: '공통 관련 ADRG',
    partial: '부분 관련 ADRG',
  };

  for (const level of ['strict', 'split', 'partial']) {
    const count = Number(response?.level_counts?.[level] ?? 0);
    if (!count) continue;

    const chip = makeChip(
      `${scopes[level]} ${Ui.formatNumber(count)} · ${labels[level]}`,
      `relation-summary-chip relation-${level}-chip`,
    );
    chip.dataset.relationLevel = level;
    container.append(chip);
  }
}"""

    return replace_function(source, "renderRelationCounts", new)


def patch_relation_results(source: str) -> str:
    block = function_block(source, "renderRelationResults")
    require(
        "STAGE72B_RELATION_CLASSIFICATION_TOP_RIGHT" not in block,
        "Stage72B relation card marker가 이미 존재함",
    )
    require(
        "STAGE69B_RELATION_RESULT_CLASSIFICATION_TITLE_ROW" in block,
        "0.5.18 relation classification title-row marker 없음",
    )
    require(
        "result-card-classification" in block,
        "0.5.18 relation classification class 없음",
    )
    require(
        "main.append(relationClassification)" in block,
        "0.5.18 relation classification main append 없음",
    )

    pattern = re.compile(
        r"(?m)^(?P<indent>[ \t]*)main\.append\(\s*"
        r"makeChip\(\s*result\.relation_level_label\s*,\s*"
        r"`relation-\$\{result\.relation_level\}-chip result-match-chip`"
        r"\s*\)\s*\)\s*;\s*$"
    )
    matches = list(pattern.finditer(block))
    require(
        len(matches) == 1,
        f"관계카드 relation-level chip anchor 불일치: {len(matches)}",
    )

    m = matches[0]
    indent = m.group("indent")
    replacement = (
        f"{indent}/* STAGE72B_RELATION_CLASSIFICATION_TOP_RIGHT\n"
        f"{indent} * 개별 카드의 관계수준 chip은 제거하고,\n"
        f"{indent} * 질병군 분류 badge를 우상단 정보로 사용한다.\n"
        f"{indent} */"
    )
    block = block[:m.start()] + replacement + block[m.end():]

    require(
        "result-match-chip" not in block,
        "관계카드에 result-match-chip이 남아 있음",
    )
    require(
        "relation_level_label" in block,
        "관계수준 의미 자체가 relation renderer에서 사라짐",
    )
    require(
        "result.summary?.abc_display_labels" in block,
        "복수분류 labels 연결 손실",
    )
    require(
        "분류정보 없음" in block,
        "분류정보 없음 fallback 손실",
    )

    return replace_function(source, "renderRelationResults", block)


def patch_app(source: str) -> str:
    source = patch_relation_counts(source)
    source = patch_relation_results(source)

    general = function_block(source, "renderResults")
    require(
        "STAGE70B_GENERAL_ADRG_CLASSIFICATION_RIGHT" in general,
        "일반 ADRG 우상단 분류 계약 손실",
    )
    require(
        "result-card-classification" in general,
        "일반 ADRG classification class 손실",
    )
    return source


def patch_css(source: str) -> str:
    require(
        "STAGE72B_RELATION_SUMMARY_EMPHASIS" not in source,
        "Stage72B summary CSS marker가 이미 존재함",
    )
    require(
        ".relation-strict-chip" in source
        and ".relation-split-chip" in source
        and ".relation-partial-chip" in source,
        "relation level chip CSS anchor 없음",
    )
    require(
        ".result-card-classification" in source,
        "0.5.18 classification right CSS 없음",
    )

    anchor = re.search(
        r"(?m)^\.relation-partial-chip\s*\{[^\n]*\}\s*$",
        source,
    )
    require(anchor is not None, ".relation-partial-chip CSS anchor 없음")

    addition = r"""

/* STAGE72B_RELATION_SUMMARY_EMPHASIS */
.relation-summary-chip {
  min-height: 23px;
  padding: 4px 9px;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: -0.01em;
  white-space: nowrap;
}
"""

    return source[:anchor.end()] + addition + source[anchor.end():]


def patch_stage70b_validator(source: str) -> str:
    require(
        "relation level chip preserved" in source,
        "Stage70B 기존 relation-level validator anchor 없음",
    )
    require(
        "STAGE72B_UPDATED_RELATION_LEVEL_CONTRACT" not in source,
        "Stage70B validator에 Stage72B marker가 이미 있음",
    )

    old = """check('relation level chip preserved', () => {
  assert.match(relation, /relation_level_label/);
  assert.match(relation, /result-match-chip/);
});"""
    require(
        source.count(old) == 1,
        f"Stage70B relation chip check anchor 불일치: {source.count(old)}",
    )

    replacement = """check('relation context moved to header summary', () => {
  /* STAGE72B_UPDATED_RELATION_LEVEL_CONTRACT */
  const relationCounts = functionBody('renderRelationCounts');
  assert.match(relationCounts, /공통 관련 ADRG/);
  assert.match(relationCounts, /relation-summary-chip/);
  assert.doesNotMatch(relation, /result-match-chip/);
  assert.match(relation, /relation_level_label/);
});"""

    updated = source.replace(old, replacement, 1)
    require(
        "relation level chip preserved" not in updated,
        "구 Stage70B relation chip 계약이 남아 있음",
    )
    return updated


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

const counts = functionBody('renderRelationCounts');
const relation = functionBody('renderRelationResults');
const general = functionBody('renderResults');

check('relation header summary identifies common ADRG results', () => {
  assert.match(counts, /STAGE72B_RELATION_SUMMARY/);
  assert.match(counts, /strict:\s*'공통 관련 ADRG'/);
  assert.match(counts, /split:\s*'공통 관련 ADRG'/);
  assert.match(counts, /partial:\s*'부분 관련 ADRG'/);
  assert.match(counts, /같은 선택지/);
  assert.match(counts, /다른 선택지/);
  assert.match(counts, /일부 연결/);
  assert.match(counts, /relation-summary-chip/);
});

check('relation card removes duplicated relation-level chip', () => {
  assert.match(relation, /STAGE72B_RELATION_CLASSIFICATION_TOP_RIGHT/);
  assert.doesNotMatch(relation, /result-match-chip/);
  assert.doesNotMatch(
    relation,
    /main\.append\(\s*makeChip\(\s*result\.relation_level_label/,
  );
});

check('relation card keeps classification at title row', () => {
  assert.match(relation, /STAGE69B_RELATION_RESULT_CLASSIFICATION_TITLE_ROW/);
  assert.match(relation, /result-card-classification/);
  assert.match(relation, /abc_display_labels/);
  assert.match(relation, /main\.append\(relationClassification\)/);
  assert.match(relation, /분류정보 없음/);
});

check('relation-level semantics remain available outside card chip', () => {
  assert.match(relation, /relation_level_label/);
  assert.match(app, /function relationLevelDescription/);
  assert.match(app, /candidate\.relation_level_label/);
});

check('relation summary chip is slightly larger than base chip', () => {
  const rule = css.match(/\.relation-summary-chip\s*\{([\s\S]*?)\}/);
  assert.ok(rule, 'relation-summary-chip CSS missing');
  assert.match(rule[1], /min-height\s*:\s*23px\s*;/);
  assert.match(rule[1], /padding\s*:\s*4px\s+9px\s*;/);
  assert.match(rule[1], /font-size\s*:\s*11px\s*;/);
  assert.match(rule[1], /font-weight\s*:\s*800\s*;/);
});

check('general ADRG classification layout remains intact', () => {
  assert.match(general, /STAGE70B_GENERAL_ADRG_CLASSIFICATION_RIGHT/);
  assert.match(general, /result-card-classification/);
  assert.match(general, /abc_display_labels/);
});

const fixture = service.relationSearch(
  [
    { code: 'I214', codeType: 'AUTO' },
    { code: 'M6566', codeType: 'AUTO' },
  ],
  'AND',
);

check('relation fixture still returns expected ADRGs', () => {
  const ids = new Set(fixture.results.map((row) => row.entity_id));
  for (const id of ['F111', 'F112', 'F121', 'F122']) {
    assert.ok(ids.has(id), `missing ${id}`);
  }
});

check('relation fixture classification data remains present', () => {
  for (const id of ['F111', 'F112', 'F121', 'F122']) {
    const row = fixture.results.find((item) => item.entity_id === id);
    assert.ok(row, `missing ${id}`);
    const labels = row.summary?.abc_display_labels ?? [];
    const fallback = row.summary?.classification_code
      || row.summary?.classification_display_label;
    assert.ok(labels.length || fallback, `${id} classification missing`);
  }
});

check('0.5.18 exact F022 contract remains intact', () => {
  const response = service.search('F022', 'ALL', { limit: 10, offset: 0 });
  assert.deepEqual(
    response.results.map((row) => `${row.entity_type}:${row.entity_id}`),
    ['CODE:F022', 'ADRG:F022'],
  );
});

check('runtime counts remain intact', () => {
  assert.equal(service.recordMaps.CODE.size, 16571);
  assert.equal(service.recordMaps.ADRG.size, 1132);
});

console.log(
  `[${fail.length ? 'FAIL' : 'PASS'}] Stage72B / 0.5.19 relation-result layout validator: ${pass} PASS / ${fail.length} FAIL`,
);
for (const item of fail) console.log(`- ${item}`);
if (fail.length) process.exitCode = 1;
"""


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    report = {
        "stage": "72B_0519_RELATION_RESULT_LAYOUT_SHADOW_R1",
        "status": "FAIL",
        "actual_performed": False,
    }

    try:
        # ------------------------------------------------------------
        # 1) Exact immutable 0.5.18 baseline
        # ------------------------------------------------------------
        head = git_text("rev-parse", "HEAD")
        origin_main = git_text("rev-parse", "origin/main")
        branch = git_text("branch", "--show-current")
        tracked = [
            x for x in git_text("diff", "--name-only", "HEAD").splitlines() if x
        ]
        staged = [
            x for x in git_text("diff", "--cached", "--name-only").splitlines() if x
        ]

        require(head == BASE_COMMIT, f"HEAD 불일치: {head}")
        require(origin_main == BASE_COMMIT, f"origin/main 불일치: {origin_main}")
        require(branch == "main", f"branch 불일치: {branch}")
        require(not tracked, f"tracked 변경 있음: {tracked}")
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

        local_tag = git_text("rev-list", "-n", "1", BASE_TAG)
        require(local_tag == BASE_COMMIT, f"{BASE_TAG} local tag 불일치")

        remote_tag = git_text(
            "ls-remote",
            "--tags",
            "origin",
            f"refs/tags/{BASE_TAG}",
        )
        require(
            remote_tag.startswith(BASE_COMMIT),
            f"{BASE_TAG} remote tag 불일치",
        )

        # ------------------------------------------------------------
        # 2) Bind to Stage72A PASS
        # ------------------------------------------------------------
        require(AUDIT_SCRIPT.is_file(), "72A audit script 없음")
        require(
            sha256(AUDIT_SCRIPT) == AUDIT_SCRIPT_SHA,
            "72A audit script SHA 불일치",
        )
        require(AUDIT_REPORT.is_file(), "72A audit.json 없음")

        audit = json.loads(AUDIT_REPORT.read_text(encoding="utf-8"))
        require(audit.get("status") == "PASS", "72A audit status != PASS")
        require(audit.get("head") == BASE_COMMIT, "72A HEAD 불일치")
        require(audit.get("package_version") == BASE_VERSION, "72A version 불일치")
        require(audit.get("runtime_json") == "UNCHANGED", "72A runtime 계약 불일치")
        require(
            audit.get("readiness") == "READY_FOR_72B_GENERALIZED_SHADOW_FIX",
            f"72A readiness 불일치: {audit.get('readiness')}",
        )

        # ------------------------------------------------------------
        # 3) Clone immutable release and patch only Shadow
        # ------------------------------------------------------------
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
        old_validator_path = SHADOW / OLD_VALIDATOR_REL
        new_validator_path = SHADOW / NEW_VALIDATOR_REL

        app_before = app_path.read_text(encoding="utf-8")
        css_before = css_path.read_text(encoding="utf-8")
        old_validator_before = old_validator_path.read_text(encoding="utf-8")

        app_after = patch_app(app_before)
        css_after = patch_css(css_before)
        old_validator_after = patch_stage70b_validator(old_validator_before)

        require(app_after != app_before, "app.js 변경 없음")
        require(css_after != css_before, "styles.css 변경 없음")
        require(
            old_validator_after != old_validator_before,
            "Stage70B validator 변경 없음",
        )

        app_path.write_text(app_after, encoding="utf-8")
        css_path.write_text(css_after, encoding="utf-8")
        old_validator_path.write_text(old_validator_after, encoding="utf-8")
        new_validator_path.parent.mkdir(parents=True, exist_ok=True)
        new_validator_path.write_text(VALIDATOR_JS + "\n", encoding="utf-8")

        # ------------------------------------------------------------
        # 4) Static syntax and exact scope
        # ------------------------------------------------------------
        for rel in (APP_REL, OLD_VALIDATOR_REL, NEW_VALIDATOR_REL):
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
                str(OLD_VALIDATOR_REL),
                cwd=SHADOW,
            ).splitlines()
            if x
        )
        require(
            modified == EXPECTED_TRACKED,
            f"Shadow tracked 범위 불일치: {modified}",
        )

        rc, new_status = run(
            ["git", "status", "--short", "--", str(NEW_VALIDATOR_REL)],
            cwd=SHADOW,
            timeout=120,
        )
        require(rc == 0, "Stage72B validator status 확인 실패")
        require(
            new_status.strip() == f"?? {NEW_VALIDATOR_REL.as_posix()}",
            f"Stage72B validator 상태 불일치: {new_status.strip()}",
        )

        # ------------------------------------------------------------
        # 5) Full regression validation
        # ------------------------------------------------------------
        validations = [
            (
                "stage72b_validator",
                ["node", "tests/validate-stage72b-0519-relation-result-layout.js"],
                SHADOW / "electron",
            ),
            (
                "stage70b_validator_updated",
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
                "release_version_0518",
                ["node", "tests/validate-release-version.js", BASE_VERSION],
                SHADOW / "electron",
            ),
        ]

        results = []
        failures = []

        for name, cmd, cwd in validations:
            rc, output = run(cmd, cwd=cwd, timeout=1200)
            results.append({
                "name": name,
                "rc": rc,
                "status": "PASS" if rc == 0 else "FAIL",
                "tail": output[-8000:],
            })
            if rc != 0:
                failures.append(f"{name} FAIL\n{output[-6000:]}")

        if failures:
            raise Stop(
                "Stage72B Shadow 검증 실패를 전체 수집함\n\n"
                + "\n\n".join(failures)
            )

        # ------------------------------------------------------------
        # 6) Actual workspace must remain untouched
        # ------------------------------------------------------------
        require(
            (ROOT / APP_REL).read_text(encoding="utf-8") == app_before,
            "Shadow가 Actual app.js를 변경함",
        )
        require(
            (ROOT / CSS_REL).read_text(encoding="utf-8") == css_before,
            "Shadow가 Actual styles.css를 변경함",
        )
        require(
            (ROOT / OLD_VALIDATOR_REL).read_text(encoding="utf-8")
            == old_validator_before,
            "Shadow가 Actual Stage70B validator를 변경함",
        )
        require(
            not (ROOT / NEW_VALIDATOR_REL).exists(),
            "Shadow가 Actual Stage72B validator를 생성함",
        )
        require(
            sha256(ROOT / RUNTIME_REL) == RUNTIME_SHA,
            "Actual 운영 JSON 변경됨",
        )
        require(
            not [
                x for x in git_text("diff", "--name-only", "HEAD").splitlines() if x
            ],
            "Shadow 후 Actual tracked 변경 발생",
        )
        require(
            not [
                x
                for x in git_text("diff", "--cached", "--name-only").splitlines()
                if x
            ],
            "Shadow 후 Actual staging 변경 발생",
        )

        candidate_sha = {
            str(rel): sha256(SHADOW / rel)
            for rel in PRODUCT_FILES
        }

        report.update({
            "status": "PASS",
            "readiness": "READY_FOR_72C_0519_RELATION_RESULT_LAYOUT_ACTUAL",
            "head": head,
            "base_version": BASE_VERSION,
            "next_version": NEXT_VERSION,
            "runtime_json": "UNCHANGED",
            "actual_performed": False,
            "shadow_product_files": [str(x) for x in PRODUCT_FILES],
            "candidate_sha256": candidate_sha,
            "layout_contract": {
                "relation_card_top_right": "DISEASE_CLASSIFICATION",
                "relation_card_relation_level_chip": "REMOVED",
                "header_summary": (
                    "공통 관련 ADRG N · 같은/다른 선택지 "
                    "(partial은 부분 관련 ADRG)"
                ),
                "header_summary_size": "11px / 23px minimum height",
                "general_adrg_layout": "PRESERVED",
            },
            "checks": results,
        })

        REPORT_JSON.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        lines = [
            "[PASS] Stage72B R1 / 0.5.19 복수검색 결과 레이아웃 Shadow",
            "relation_card_top_right=DISEASE_CLASSIFICATION",
            "relation_card_relation_level_chip=REMOVED",
            "relation_card_lower_classification_duplicate=NONE",
            "header_summary=COMMON_RELATED_ADRG",
            "header_summary_same_choice_context=PRESERVED",
            "header_summary_emphasis=SLIGHTLY_LARGER",
            "general_adrg_layout=PRESERVED",
            "stage72b_validator=PASS",
            "stage70b_validator_updated=PASS",
            "stage69b_validator=PASS",
            "stage68d_validator=PASS",
            "npm_check=PASS",
            "50B_50C_50D=PASS",
            "release_version_0.5.18=PASS",
            "runtime_json=UNCHANGED",
            "shadow_product_files=4",
            "actual=NOT_PERFORMED",
            "readiness=READY_FOR_72C_0519_RELATION_RESULT_LAYOUT_ACTUAL",
            f"report={REPORT_TXT.relative_to(ROOT)}",
            f"json={REPORT_JSON.relative_to(ROOT)}",
        ]

        REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\n".join(lines))
        return 0

    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        REPORT_JSON.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        lines = [
            "[FAIL] Stage72B 0.5.19 복수검색 결과 레이아웃 Shadow — Actual 미수행",
            f"{type(exc).__name__}: {exc}",
            f"report={REPORT_TXT.relative_to(ROOT)}",
        ]
        REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\n".join(lines))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
