#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage68D — KDRG 0.5.16 Actual Apply R5

R3 보정:
- 정규식으로 함수 일부를 치환하지 않는다.
- 0.5.15 tag와 동일한 현재 app.js를 기준으로 "줄 삽입"만 한다.
- 실제 app.js에 쓰기 전에 reports/.../candidate_app.js에 먼저 만들고
  `node --check`를 통과해야만 Actual에 반영한다.
- Electron 검증은 과거 릴리스와 동일하게 electron/ cwd에서 `npm run check`.
- 실패 시 app.js와 신규 validator만 exact rollback.

Actual 변경:
1) relation 상세의 질병군 분류 표시
2) ADRG 상세의 파생 AADRG 섹션 복원
3) 영구 회귀검증기 추가

운영 JSON / search service / CSS는 수정하지 않는다.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
ELECTRON = ROOT / "electron"

STAGE = "stage68d_0516_actual_classification_derived_aadrg_r5"
REPORT_DIR = ROOT / "reports" / STAGE
REPORT_DIR.mkdir(parents=True, exist_ok=True)

APP = ELECTRON / "renderer" / "app.js"
VALIDATOR = ELECTRON / "tests" / "validate-stage68d-0516-classification-derived-aadrg.js"
DATA = ROOT / "data" / "kdrg_v47_search_integrated_v3.json"

CANDIDATE_APP = REPORT_DIR / "candidate_app.js"
CANDIDATE_DIFF = REPORT_DIR / "candidate_app.diff"
REPORT_JSON = REPORT_DIR / "apply.json"
REPORT_TXT = REPORT_DIR / "apply_summary.txt"

EXPECTED_HEAD = "6e0bc2857ebf6abb482428b90f452d5e07c486ac"
EXPECTED_TAG = "electron-v0.5.15"
EXPECTED_DATA_SHA = "1a3d50400567ecaad9695b7be8e7c0382131f8652f398e010cf01f4d8dda6c58"

def run(args, *, cwd=None, timeout=300):
    p = subprocess.run(
        args,
        cwd=(cwd or ROOT),
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    output = (p.stdout or "") + (("\n" + p.stderr) if p.stderr else "")
    return p.returncode, output

def git(*args):
    return run(["git", *args], cwd=ROOT, timeout=120)

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def find_function_range(text: str, name: str):
    """문자열/템플릿을 고려한 brace-depth로 JS function 전체 범위 반환."""
    m = re.search(rf"(?m)^(?:async\s+)?function\s+{re.escape(name)}\s*\([^)]*\)\s*\{{", text)
    if not m:
        raise RuntimeError(f"함수 없음: {name}")

    brace = text.find("{", m.start(), m.end())
    depth = 0
    quote = None
    escaped = False
    template_expr_depth = 0

    i = brace
    while i < len(text):
        ch = text[i]

        if quote:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif quote == "`":
                if ch == "`" and template_expr_depth == 0:
                    quote = None
                elif ch == "$" and i + 1 < len(text) and text[i + 1] == "{":
                    template_expr_depth += 1
                    i += 1
                elif ch == "}" and template_expr_depth:
                    template_expr_depth -= 1
            elif ch == quote:
                quote = None
            i += 1
            continue

        if ch in ("'", '"', "`"):
            quote = ch
            i += 1
            continue

        # line comment
        if ch == "/" and i + 1 < len(text) and text[i + 1] == "/":
            j = text.find("\n", i + 2)
            if j < 0:
                i = len(text)
            else:
                i = j + 1
            continue

        # block comment
        if ch == "/" and i + 1 < len(text) and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            if j < 0:
                raise RuntimeError(f"{name}: block comment 종료 없음")
            i = j + 2
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return m.start(), i + 1
        i += 1

    raise RuntimeError(f"{name}: 함수 종료 brace를 찾지 못함")

def get_function(text: str, name: str) -> str:
    a, b = find_function_range(text, name)
    return text[a:b]

def replace_function(text: str, name: str, new_block: str) -> str:
    a, b = find_function_range(text, name)
    return text[:a] + new_block + text[b:]

def patch_relation_detail(block: str, full_source: str) -> str:
    # 이미 정상이라면 그대로.
    if (
        "질병군 분류" in block
        and "candidate.summary" in block
        and "abc_display_labels" in block
    ):
        return block

    lines = block.splitlines(keepends=True)

    # makeMetaGrid 내부 MDC row를 찾는다.
    mdc_idx = None
    for i, line in enumerate(lines):
        if "['MDC'," in line and "candidate" in line:
            mdc_idx = i
            break
    if mdc_idx is None:
        raise RuntimeError("renderRelationDetail: MDC row를 찾지 못함")

    indent = re.match(r"[ \t]*", lines[mdc_idx]).group(0)

    # 현재 앱에 badge-group helper가 있으면 direct ADRG와 같은 badge 표현을 사용.
    if "function makeClassificationBadgeGroup(" in full_source:
        insert = [
            f"{indent}[\n",
            f"{indent}  '질병군 분류',\n",
            f"{indent}  makeClassificationBadgeGroup(\n",
            f"{indent}    candidate.summary?.abc_display_labels ?? [],\n",
            f"{indent}  ),\n",
            f"{indent}],\n",
        ]
    else:
        # 구형 renderer fallback. 데이터 자체는 relation candidate에 존재함.
        insert = [
            f"{indent}['질병군 분류', Ui.summarizeList(candidate.summary?.abc_display_labels)],\n"
        ]

    lines[mdc_idx + 1:mdc_idx + 1] = insert
    return "".join(lines)

def patch_adrg_detail(block: str) -> str:
    """
    ADRG 상단 메타정보 뒤, 조건 summary 앞에 파생 AADRG 섹션을 삽입한다.
    첫 fragment.append(meta grid)를 건드리지 않고,
    renderUserConditionSummary(detail)가 들어 있는 별도 fragment.append만 수정한다.
    """
    if "renderDerivedAadrgList(detail.aadrg_records)" in block:
        return block

    lines = block.splitlines(keepends=True)

    # 1) 상단 메타정보 fragment.append 위치
    meta_line = None
    for i, line in enumerate(lines):
        if "makeMetaGrid([" in line:
            meta_line = i
            break
    if meta_line is None:
        raise RuntimeError("renderAdrgDetail: 상단 makeMetaGrid를 찾지 못함")

    meta_append = None
    for i in range(meta_line, -1, -1):
        if "fragment.append(" in lines[i]:
            meta_append = i
            break
    if meta_append is None:
        raise RuntimeError("renderAdrgDetail: 상단 meta fragment.append를 찾지 못함")

    # 2) 조건 summary 실제 라인에서 역방향으로 가장 가까운 fragment.append 검색
    summary_line = None
    for i, line in enumerate(lines):
        if "renderUserConditionSummary(detail)" in line:
            summary_line = i
            break
    if summary_line is None:
        raise RuntimeError("renderAdrgDetail: renderUserConditionSummary(detail)를 찾지 못함")

    condition_append = None
    for i in range(summary_line, -1, -1):
        if "fragment.append(" in lines[i]:
            condition_append = i
            break
    if condition_append is None:
        raise RuntimeError("renderAdrgDetail: 조건 fragment.append를 찾지 못함")

    # 메타 append와 조건 append가 같은 호출이면 안전하게 자동 수정하지 않는다.
    if condition_append == meta_append:
        raise RuntimeError(
            "renderAdrgDetail: 상단 meta와 조건이 같은 fragment.append에 있어 "
            "자동 삽입을 중단함"
        )
    if condition_append < meta_append:
        raise RuntimeError("renderAdrgDetail: fragment.append 순서가 비정상")

    base_indent = re.match(r"[ \t]*", lines[condition_append]).group(0)
    child_indent = base_indent + "  "

    declaration = [
        f"{base_indent}const aadrgSection = makeSection(\n",
        f"{base_indent}  '파생 AADRG',\n",
        f"{base_indent}  'ADRG에서 파생되는 AADRG와 질병군 분류를 함께 확인합니다.',\n",
        f"{base_indent}  {{ open: false, count: (detail.aadrg_records ?? []).length }},\n",
        f"{base_indent});\n",
        f"{base_indent}aadrgSection.append(renderDerivedAadrgList(detail.aadrg_records));\n",
        "\n",
    ]

    # 조건 fragment.append 바로 앞에 선언을 넣는다.
    lines[condition_append:condition_append] = declaration
    condition_append += len(declaration)

    # 조건 fragment.append의 첫 argument로 aadrgSection 삽입.
    line = lines[condition_append]
    stripped = line.rstrip("\n")
    if re.match(r"^\s*fragment\.append\(\s*$", stripped):
        lines[condition_append + 1:condition_append + 1] = [
            f"{child_indent}aadrgSection,\n"
        ]
    else:
        m = re.match(
            r"^(?P<indent>\s*)fragment\.append\(\s*(?P<rest>.*)$",
            stripped,
        )
        if not m:
            raise RuntimeError(
                "renderAdrgDetail: 조건 fragment.append line 해석 실패"
            )
        rest = m.group("rest")
        newline = "\n" if line.endswith("\n") else ""
        lines[condition_append] = (
            f"{m.group('indent')}fragment.append({newline}"
        )
        inserts = [f"{child_indent}aadrgSection,\n"]
        if rest:
            inserts.append(f"{child_indent}{rest}\n")
        lines[condition_append + 1:condition_append + 1] = inserts

    patched = "".join(lines)

    # 최종 순서 계약:
    # 상단정보(makeMetaGrid) -> 파생 AADRG -> 조건 summary
    pos_meta = patched.find("makeMetaGrid([")
    pos_derived = patched.find("'파생 AADRG'")
    pos_summary = patched.find("renderUserConditionSummary(detail)")
    if not (0 <= pos_meta < pos_derived < pos_summary):
        raise RuntimeError(
            "renderAdrgDetail: UI 순서 계약 위반 "
            "(상단정보 -> 파생 AADRG -> 조건 summary)"
        )

    return patched


def self_test_patch_engine():
    """
    실제 제품을 건드리기 전에 패치엔진 자체를 두 구조로 검증한다.
    - 구형 단순 구조
    - 현재 계열 SHOW_DEVELOPER_METADATA 구조
    두 경우 모두 Python 패치 -> JS node --check -> UI 순서를 확인한다.
    """
    fixtures = [
        (
            "legacy",
            """
'use strict';
function makeClassificationBadgeGroup(x) { return x; }
function renderRelationDetail(candidate, response) {
  const panel = byId('detail-content');
  panel.append(makeMetaGrid([
    ['ADRG', candidate.entity_id],
    ['질병군명', candidate.title],
    ['MDC', candidate.summary?.mdc ? `MDC ${candidate.summary.mdc}` : '-'],
    ['연결 코드', `${candidate.matched_count}/${candidate.total_count}`],
  ], 'detail-overview-grid'));
}
function clearDetail() {}
function renderDerivedAadrgList(records) {
  for (const record of records) {
    const summary = record.summary ?? {};
    meta.append(makeChip(summary.classification_code || summary.classification_display_label));
  }
}
function renderAdrgDetail(payload) {
  const detail = payload.detail;
  const fragment = document.createDocumentFragment();
  fragment.append(
    makeMetaGrid([
      ['ADRG', detail.adrg],
      ['질병군명', detail.adrg_name],
      ['MDC', detail.mdc ? `MDC ${detail.mdc}` : '-'],
      ['AADRG', `${Ui.formatNumber(detail.aadrg_count ?? 0)}개`],
    ], 'detail-overview-grid'),
  );

  fragment.append(
    renderUserConditionSummary(detail),
    renderUserConditionTables(detail),
    renderUserConditionEvidence(detail),
  );
  return fragment;
}
function renderAadrgDetail(payload) {}
""",
        ),
        (
            "modern",
            """
'use strict';
function makeClassificationBadgeGroup(x) { return x; }
function appendClassificationBadges(a, b) {}
function renderRelationDetail(candidate, response) {
  const panel = byId('detail-content');
  panel.append(makeMetaGrid([
    ['ADRG', candidate.entity_id],
    ['질병군명', candidate.title],
    ['MDC', candidate.summary?.mdc ? `MDC ${candidate.summary.mdc}` : '-'],
    ['연결 코드', `${candidate.matched_count}/${candidate.total_count}`],
  ], 'detail-overview-grid'));
}
function clearDetail() {}
function renderDerivedAadrgList(records) {
  for (const record of records) {
    const summary = record.summary ?? {};
    appendClassificationBadges(
      meta,
      [summary.classification_code || summary.classification_display_label],
    );
  }
}
function renderAdrgDetail(payload) {
  const detail = payload.detail;
  const fragment = document.createDocumentFragment();
  fragment.append(
    makeMetaGrid([
      ['ADRG', detail.adrg],
      ['질병군명', detail.adrg_name],
      ['MDC', detail.mdc ? `MDC ${detail.mdc}` : '-'],
      ['AADRG', `${Ui.formatNumber(detail.aadrg_count ?? 0)}개`],
    ], 'detail-overview-grid'),
  );

  fragment.append(
    renderUserConditionSummary(detail),
    renderUserConditionTables(detail),
    ...(SHOW_DEVELOPER_METADATA
      ? [renderUserConditionEvidence(detail)]
      : []),
  );
  return fragment;
}
function renderAadrgDetail(payload) {}
""",
        ),
    ]

    results = []
    for name, source in fixtures:
        relation = get_function(source, "renderRelationDetail")
        relation_patched = patch_relation_detail(relation, source)
        candidate = replace_function(
            source,
            "renderRelationDetail",
            relation_patched,
        )

        adrg = get_function(candidate, "renderAdrgDetail")
        adrg_patched = patch_adrg_detail(adrg)
        candidate = replace_function(
            candidate,
            "renderAdrgDetail",
            adrg_patched,
        )

        adrg_after = get_function(candidate, "renderAdrgDetail")
        relation_after = get_function(candidate, "renderRelationDetail")

        if "renderDerivedAadrgList(detail.aadrg_records)" not in adrg_after:
            raise RuntimeError(
                f"self-test {name}: derived AADRG 호출 누락"
            )
        if not (
            adrg_after.find("makeMetaGrid([")
            < adrg_after.find("'파생 AADRG'")
            < adrg_after.find("renderUserConditionSummary(detail)")
        ):
            raise RuntimeError(
                f"self-test {name}: ADRG UI 순서 계약 실패"
            )
        if not (
            "질병군 분류" in relation_after
            and "abc_display_labels" in relation_after
        ):
            raise RuntimeError(
                f"self-test {name}: relation classification 삽입 실패"
            )

        test_file = REPORT_DIR / f"_self_test_{name}.js"
        test_file.write_text(candidate, encoding="utf-8")
        rc, output = run(
            ["node", "--check", str(test_file)],
            cwd=ROOT,
            timeout=120,
        )
        if rc != 0:
            raise RuntimeError(
                f"self-test {name}: node --check 실패\n"
                + output[-1500:]
            )

        results.append({
            "fixture": name,
            "node_check": "PASS",
            "order": "meta -> derived -> condition",
        })

    # 신규 validator 자체 JS syntax도 사전검사.
    validator_test = REPORT_DIR / "_self_test_validator.js"
    validator_test.write_text(VALIDATOR_JS, encoding="utf-8")
    rc, output = run(
        ["node", "--check", str(validator_test)],
        cwd=ROOT,
        timeout=120,
    )
    if rc != 0:
        raise RuntimeError(
            "self-test validator: node --check 실패\n"
            + output[-1500:]
        )

    return results

VALIDATOR_JS = r"""'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ELECTRON_ROOT = path.resolve(__dirname, '..');
const { resolveDataFiles } = require('../src/data-paths');
const {
  KdrgSearchService,
  normalizeEntityId,
} = require('../src/kdrg-search-service');
const { SEARCH_ENTITY_TYPES } = require('../src/search-result-contract');

const appText = fs.readFileSync(
  path.join(ELECTRON_ROOT, 'renderer', 'app.js'),
  'utf8',
);

const dataFiles = resolveDataFiles({
  isPackaged: false,
  resourcesPath: null,
  moduleDirectory: path.join(ELECTRON_ROOT, 'src'),
});
const service = new KdrgSearchService(dataFiles.integrated);

let pass = 0;
const failures = [];

function check(name, fn) {
  try {
    fn();
    pass += 1;
  } catch (error) {
    failures.push(`${name}: ${error.message}`);
  }
}

function sameSet(a, b) {
  const aa = [...new Set((a ?? []).map(String))].sort();
  const bb = [...new Set((b ?? []).map(String))].sort();
  return JSON.stringify(aa) === JSON.stringify(bb);
}

function functionSlice(name, nextName) {
  const start = appText.indexOf(`function ${name}(`);
  assert.ok(start >= 0, `${name} 없음`);
  const end = appText.indexOf(`function ${nextName}(`, start + 1);
  assert.ok(end > start, `${nextName} 경계 없음`);
  return appText.slice(start, end);
}

function codesForTables(tableIds) {
  const output = [];
  const seen = new Set();
  for (const tableId of tableIds ?? []) {
    const table = service.recordMaps.TABLE.get(String(tableId));
    for (const code of table?.codes ?? []) {
      const normalized = normalizeEntityId(code, 'CODE');
      if (!normalized || seen.has(normalized)) continue;
      seen.add(normalized);
      output.push(String(code));
    }
  }
  return output;
}

function findRelationFixture(adrg) {
  const groups = service.conditionGroupsByAdrg.get(adrg) ?? [];

  // 같은 조건 선택지 내 2코드 AND 우선.
  for (const group of groups) {
    const codes = codesForTables(group.include_table_ids).slice(0, 80);
    for (let i = 0; i < codes.length; i += 1) {
      for (let j = i + 1; j < codes.length; j += 1) {
        if (
          normalizeEntityId(codes[i], 'CODE')
          === normalizeEntityId(codes[j], 'CODE')
        ) continue;
        const response = service.relationSearch([
          { code: codes[i], codeType: 'AUTO' },
          { code: codes[j], codeType: 'AUTO' },
        ], 'AND');
        const candidate = response.results.find(
          (row) => row.entity_id === adrg,
        );
        if (candidate) {
          return {
            codes: [codes[i], codes[j]],
            operator: 'AND',
            candidate,
          };
        }
      }
    }
  }

  return null;
}

check('public search CODE/ADRG only', () => {
  assert.deepEqual(Array.from(SEARCH_ENTITY_TYPES), ['CODE', 'ADRG']);
});

check('service counts', () => {
  const status = service.status();
  assert.equal(status.counts.adrg_records, 1132);
  assert.equal(status.counts.aadrg_records, 1233);
});

const f111Direct = service.search('F111', 'ADRG', { limit: 50 })
  .results.find(
    (row) => row.entity_type === 'ADRG' && row.entity_id === 'F111',
  );
const f111Detail = service.getDetail('ADRG', 'F111');

check('F111 direct classification', () => {
  assert.ok(f111Direct);
  assert.deepEqual(
    f111Direct.summary?.abc_display_labels,
    ['질병군 분류(전문)'],
  );
});

check('F111 detail classification', () => {
  assert.deepEqual(
    f111Detail.detail?.abc_display_labels,
    ['질병군 분류(전문)'],
  );
});

check('F1110 derived classification', () => {
  const row = (f111Detail.detail?.aadrg_records ?? [])
    .find((x) => x.entity_id === 'F1110');
  assert.ok(row);
  assert.equal(row.summary?.classification_code, 'A');
  assert.equal(
    row.summary?.classification_display_label,
    '질병군 분류(전문)',
  );
});

const f111Fixture = findRelationFixture('F111');

check('F111 valid relation fixture', () => {
  assert.ok(f111Fixture);
});

check('F111 relation classification', () => {
  assert.ok(f111Fixture);
  const labels = f111Fixture.candidate.summary?.abc_display_labels ?? [];
  assert.ok(labels.length > 0);
  assert.ok(sameSet(labels, f111Direct.summary?.abc_display_labels));
  assert.ok(sameSet(labels, f111Detail.detail?.abc_display_labels));
});

// 1,132 ADRG의 derived AADRG 1,233건 전수검사.
// classification_code 21건 부재는 이미 확인된 데이터 특성이고,
// display label은 1,233건 모두 존재해야 UI 표시가 가능하다.
check('all derived AADRG display labels complete', () => {
  let adrgCount = 0;
  let childCount = 0;
  const missing = [];
  for (const adrg of service.recordMaps.ADRG.keys()) {
    adrgCount += 1;
    const detail = service.getDetail('ADRG', adrg).detail;
    for (const child of detail.aadrg_records ?? []) {
      childCount += 1;
      const label = String(
        child?.summary?.classification_display_label ?? '',
      ).trim();
      if (!child?.entity_id || !label) {
        missing.push({
          adrg,
          aadrg: child?.entity_id ?? null,
          label,
        });
      }
    }
  }
  assert.equal(adrgCount, 1132);
  assert.equal(childCount, 1233);
  assert.deepEqual(missing, []);
});

const relationResults = functionSlice(
  'renderRelationResults',
  'relationMatchCard',
);
const relationDetail = functionSlice(
  'renderRelationDetail',
  'clearDetail',
);
const derived = functionSlice(
  'renderDerivedAadrgList',
  'renderAdrgDetail',
);
const adrgDetail = functionSlice(
  'renderAdrgDetail',
  'renderAadrgDetail',
);

check('relation result card classification contract', () => {
  assert.ok(relationResults.includes('abc_display_labels'));
  assert.ok(
    relationResults.includes('appendClassificationBadges')
    || relationResults.includes('makeChip'),
  );
});

check('relation detail classification contract', () => {
  assert.ok(relationDetail.includes('질병군 분류'));
  assert.ok(relationDetail.includes('candidate.summary'));
  assert.ok(relationDetail.includes('abc_display_labels'));
});

check('derived AADRG classification renderer contract', () => {
  assert.ok(derived.includes('summary.classification_code'));
  assert.ok(derived.includes('summary.classification_display_label'));
  assert.ok(
    derived.includes('appendClassificationBadges')
    || derived.includes('makeChip'),
  );
});

check('ADRG detail derived section contract', () => {
  assert.ok(adrgDetail.includes('파생 AADRG'));
  assert.ok(
    adrgDetail.includes(
      'renderDerivedAadrgList(detail.aadrg_records)',
    ),
  );
  assert.ok(/open\s*:\s*false/.test(adrgDetail));
});

// relation 가능한 ADRG 전수 projection 비교.
// fixture를 만들 수 있는 ADRG만 비교하며, expected 분류가 있는 candidate의
// relation labels는 direct/detail과 일치해야 한다.
check('relation classification full audit', () => {
  let eligible = 0;
  let compared = 0;
  const missing = [];
  const mismatch = [];

  for (const adrg of service.recordMaps.ADRG.keys()) {
    const fixture = findRelationFixture(adrg);
    if (!fixture) continue;
    eligible += 1;

    const direct = service.search(adrg, 'ADRG', { limit: 50 })
      .results.find(
        (row) => row.entity_type === 'ADRG' && row.entity_id === adrg,
      );
    const detail = service.getDetail('ADRG', adrg);

    const expected = (
      detail.detail?.abc_display_labels?.length
        ? detail.detail.abc_display_labels
        : direct?.summary?.abc_display_labels ?? []
    );
    if (!expected.length) continue;

    compared += 1;
    const actual = fixture.candidate.summary?.abc_display_labels ?? [];
    if (!actual.length) {
      missing.push(adrg);
    } else if (!sameSet(actual, expected)) {
      mismatch.push({ adrg, expected, actual });
    }
  }

  assert.ok(eligible > 0);
  assert.ok(compared > 0);
  assert.deepEqual(missing, []);
  assert.deepEqual(mismatch, []);
});

console.log(
  `stage68d_0516: ${pass} PASS / ${failures.length} FAIL`,
);
if (f111Fixture) {
  console.log(
    `F111 relation fixture=${f111Fixture.codes.join(' + ')} / `
    + f111Fixture.operator,
  );
}
if (failures.length) {
  for (const failure of failures) console.log(`- ${failure}`);
  process.exitCode = 1;
}
"""

def main():
    # ---------- script / patch-engine self-test ----------
    try:
        self_test_results = self_test_patch_engine()
    except Exception as exc:
        REPORT_TXT.write_text(
            "[FAIL] Stage68D R5 self-test\n"
            + str(exc)
            + "\n",
            encoding="utf-8",
        )
        print("[FAIL] Stage68D R5 self-test — 제품파일 미수정")
        print(str(exc).splitlines()[0][:800])
        print(f"report={REPORT_TXT.relative_to(ROOT)}")
        return 1

    # ---------- preflight ----------
    required = [APP, DATA]
    missing = [str(p.relative_to(ROOT)) for p in required if not p.exists()]
    if missing:
        print(f"[FAIL] 필수 파일 누락: {missing}")
        return 1

    rc, head_out = git("rev-parse", "HEAD")
    head = head_out.strip() if rc == 0 else ""
    rc, tag_out = git("rev-parse", EXPECTED_TAG)
    tag_commit = tag_out.strip() if rc == 0 else ""

    if head != EXPECTED_HEAD:
        print(f"[FAIL] HEAD 불일치: {head}")
        return 1
    if tag_commit != EXPECTED_HEAD:
        print(f"[FAIL] {EXPECTED_TAG} commit 불일치: {tag_commit}")
        return 1
    if sha256(DATA) != EXPECTED_DATA_SHA:
        print(f"[FAIL] 운영 JSON SHA 불일치: {sha256(DATA)}")
        return 1

    # app.js는 0.5.15 tag와 완전 동일해야 한다.
    rc, _ = git(
        "diff", "--quiet", EXPECTED_TAG, "--",
        str(APP.relative_to(ROOT)),
    )
    if rc != 0:
        print("[FAIL] app.js가 0.5.15 tag와 이미 다름")
        return 1

    if VALIDATOR.exists():
        print(
            "[FAIL] 신규 Stage68D validator가 이미 존재함. "
            "이전 rollback 상태 확인 필요"
        )
        return 1

    original = APP.read_text(encoding="utf-8")

    # ---------- candidate build ----------
    relation = get_function(original, "renderRelationDetail")
    relation_patched = patch_relation_detail(relation, original)
    candidate = replace_function(
        original,
        "renderRelationDetail",
        relation_patched,
    )

    adrg = get_function(candidate, "renderAdrgDetail")
    adrg_patched = patch_adrg_detail(adrg)
    candidate = replace_function(
        candidate,
        "renderAdrgDetail",
        adrg_patched,
    )

    # 정확히 필요한 계약이 생겼는지 확인.
    if "renderDerivedAadrgList(detail.aadrg_records)" not in candidate:
        print("[FAIL] candidate에 derived AADRG 호출 없음")
        return 1
    relation_after = get_function(candidate, "renderRelationDetail")
    if (
        "질병군 분류" not in relation_after
        or "candidate.summary" not in relation_after
        or "abc_display_labels" not in relation_after
    ):
        print("[FAIL] candidate relation classification 계약 없음")
        return 1

    # 변경은 추가 중심이며 지나치게 커지면 중단.
    diff_lines = list(difflib.unified_diff(
        original.splitlines(),
        candidate.splitlines(),
        fromfile="electron-v0.5.15/app.js",
        tofile="0.5.16-candidate/app.js",
        lineterm="",
    ))
    CANDIDATE_DIFF.write_text(
        "\n".join(diff_lines) + "\n",
        encoding="utf-8",
    )
    changed_diff_lines = [
        x for x in diff_lines
        if (x.startswith("+") or x.startswith("-"))
        and not x.startswith("+++")
        and not x.startswith("---")
    ]
    if len(changed_diff_lines) > 40:
        print(
            f"[FAIL] candidate diff가 예상보다 큼: "
            f"{len(changed_diff_lines)} lines"
        )
        print(f"diff={CANDIDATE_DIFF.relative_to(ROOT)}")
        return 1

    CANDIDATE_APP.write_text(candidate, encoding="utf-8")

    # 실제 파일에 쓰기 전에 syntax check.
    rc, out = run(
        ["node", "--check", str(CANDIDATE_APP)],
        cwd=ROOT,
        timeout=120,
    )
    if rc != 0:
        REPORT_TXT.write_text(
            "[FAIL] candidate syntax check\n"
            + out[-5000:]
            + "\n",
            encoding="utf-8",
        )
        print("[FAIL] candidate app.js syntax — live file 미수정")
        print(out[-1200:].strip())
        print(f"report={REPORT_TXT.relative_to(ROOT)}")
        return 1

    # ---------- actual ----------
    original_validator = None
    validations = []
    try:
        APP.write_text(candidate, encoding="utf-8")
        VALIDATOR.write_text(VALIDATOR_JS, encoding="utf-8")

        commands = [
            (
                ["node", "--check", "renderer/app.js"],
                ELECTRON,
                "app syntax",
            ),
            (
                [
                    "node", "--check",
                    "tests/validate-stage68d-0516-classification-derived-aadrg.js",
                ],
                ELECTRON,
                "stage68d validator syntax",
            ),
            (
                [
                    "node",
                    "tests/validate-stage68d-0516-classification-derived-aadrg.js",
                ],
                ELECTRON,
                "stage68d regression",
            ),
            (
                ["npm", "run", "check"],
                ELECTRON,
                "0.5.15 release validation chain",
            ),
        ]

        for cmd, cwd, label in commands:
            vrc, output = run(cmd, cwd=cwd, timeout=600)
            validations.append({
                "label": label,
                "cmd": " ".join(cmd),
                "cwd": str(cwd),
                "status": "PASS" if vrc == 0 else "FAIL",
                "returncode": vrc,
                "output_tail": output[-5000:],
            })
            if vrc != 0:
                raise RuntimeError(
                    f"{label} 실패: {' '.join(cmd)}\n"
                    + output[-3000:]
                )

        # Python validators는 존재할 때 추가 확인.
        for script in [
            "50B_validate_kdrg_electron_search_service.py",
            "50C_validate_kdrg_electron_renderer_ui.py",
        ]:
            p = ROOT / script
            if not p.exists():
                validations.append({
                    "label": script,
                    "cmd": f"python {script}",
                    "cwd": str(ROOT),
                    "status": "SKIP_NOT_FOUND",
                })
                continue
            vrc, output = run(
                ["python", script],
                cwd=ROOT,
                timeout=600,
            )
            validations.append({
                "label": script,
                "cmd": f"python {script}",
                "cwd": str(ROOT),
                "status": "PASS" if vrc == 0 else "FAIL",
                "returncode": vrc,
                "output_tail": output[-5000:],
            })
            if vrc != 0:
                raise RuntimeError(
                    f"{script} 실패\n" + output[-3000:]
                )

        rc, status_out = git(
            "status", "--short", "--",
            str(APP.relative_to(ROOT)),
            str(VALIDATOR.relative_to(ROOT)),
        )

        result = {
            "stage": "68D_R5",
            "actual": True,
            "status": "PASS",
            "head": head,
            "tag": EXPECTED_TAG,
            "operating_json_sha256": sha256(DATA),
            "modified_files": [
                str(APP.relative_to(ROOT)),
                str(VALIDATOR.relative_to(ROOT)),
            ],
            "protected_unchanged": [
                "data/kdrg_v47_search_integrated_v3.json",
                "electron/src/kdrg-search-service.js",
                "electron/renderer/styles.css",
            ],
            "self_test_results": self_test_results,
            "candidate_diff_lines": len(changed_diff_lines),
            "app_sha256": sha256(APP),
            "validator_sha256": sha256(VALIDATOR),
            "validations": validations,
            "git_status_targets": status_out.splitlines(),
        }
        REPORT_JSON.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        lines = [
            "Stage68D R5 — KDRG 0.5.16 Actual",
            "=" * 58,
            "status=PASS",
            f"HEAD={head}",
            "self_test=PASS",
            f"candidate_diff_lines={len(changed_diff_lines)}",
            f"app_sha256={sha256(APP)}",
            f"validator_sha256={sha256(VALIDATOR)}",
            "",
            "[validation]",
        ]
        for v in validations:
            lines.append(
                f"{v['status']} {v['label']} :: {v['cmd']}"
            )
        lines += [
            "",
            "[git status target]",
            *status_out.splitlines(),
            "",
            "operating_json=UNCHANGED",
            "search_service=UNCHANGED",
            "styles=UNCHANGED",
        ]
        REPORT_TXT.write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )

        print("[PASS] Stage68D R5 0.5.16 Actual")
        print("self_test=PASS")
        print("modified=electron/renderer/app.js")
        print(
            "added="
            "electron/tests/"
            "validate-stage68d-0516-classification-derived-aadrg.js"
        )
        print(f"candidate_diff_lines={len(changed_diff_lines)}")
        for v in validations:
            print(f"{v['status']} {v['label']}")
        print("operating_json=UNCHANGED")
        print("search_service=UNCHANGED")
        print("styles=UNCHANGED")
        print(f"app_sha256={sha256(APP)}")
        print(f"validator_sha256={sha256(VALIDATOR)}")
        print(f"report={REPORT_TXT.relative_to(ROOT)}")
        print(f"json={REPORT_JSON.relative_to(ROOT)}")
        return 0

    except Exception as exc:
        # exact rollback
        APP.write_text(original, encoding="utf-8")
        if VALIDATOR.exists():
            VALIDATOR.unlink()

        failure = {
            "stage": "68D_R5",
            "actual": True,
            "status": "FAIL",
            "rolled_back": True,
            "error": str(exc),
            "validations": validations,
        }
        REPORT_JSON.write_text(
            json.dumps(failure, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        REPORT_TXT.write_text(
            "[FAIL] Stage68D R5\n"
            "rollback=YES\n"
            + str(exc)
            + "\n",
            encoding="utf-8",
        )

        print("[FAIL] Stage68D R5 — exact rollback 완료")
        print(str(exc).splitlines()[0][:800])
        print(f"report={REPORT_TXT.relative_to(ROOT)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
