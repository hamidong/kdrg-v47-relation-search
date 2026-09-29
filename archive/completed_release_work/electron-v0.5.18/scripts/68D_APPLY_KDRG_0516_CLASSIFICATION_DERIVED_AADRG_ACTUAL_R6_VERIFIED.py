#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage68D — KDRG 0.5.16 Actual Apply R6
실제 0.5.15 app.js 구조 기반 exact-anchor 수정.

변경:
- electron/renderer/app.js
- electron/tests/validate-stage68d-0516-classification-derived-aadrg.js

보호:
- data/kdrg_v47_search_integrated_v3.json 변경 금지
- electron/src/kdrg-search-service.js 변경 금지
- electron/renderer/styles.css 변경 금지

안전장치:
1) HEAD/tag/runtime SHA 확인
2) 현재 app.js에서 정확한 old anchor 각각 1개 확인
3) actual 쓰기 전 candidate 생성
4) candidate node --check PASS 후 actual 반영
5) 신규 validator node --check + 실행
6) electron cwd에서 npm run check
7) 50B/50C 검증
8) 실패 시 exact rollback
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
ELECTRON = ROOT / "electron"

APP = ELECTRON / "renderer" / "app.js"
VALIDATOR = ELECTRON / "tests" / "validate-stage68d-0516-classification-derived-aadrg.js"
DATA = ROOT / "data" / "kdrg_v47_search_integrated_v3.json"
SERVICE = ELECTRON / "src" / "kdrg-search-service.js"
STYLES = ELECTRON / "renderer" / "styles.css"

REPORT_DIR = ROOT / "reports" / "stage68d_0516_actual_r6"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
CANDIDATE = REPORT_DIR / "candidate_app.js"
DIFF_FILE = REPORT_DIR / "candidate_app.diff"
REPORT_JSON = REPORT_DIR / "apply.json"
REPORT_TXT = REPORT_DIR / "apply_summary.txt"

EXPECTED_HEAD = "6e0bc2857ebf6abb482428b90f452d5e07c486ac"
EXPECTED_TAG = "electron-v0.5.15"
EXPECTED_DATA_SHA = "1a3d50400567ecaad9695b7be8e7c0382131f8652f398e010cf01f4d8dda6c58"

OLD_RELATION = """  panel.append(makeMetaGrid([['ADRG', candidate.entity_id], ['MDC', candidate.summary?.mdc ? mdcDisplayText(candidate.summary.mdc, candidate.summary?.mdc_name) : '-'], ['질병군 분류', makeClassificationBadgeGroup([candidate.summary?.classification_code || candidate.summary?.classification_display_label])], ['연결 코드', `${candidate.matched_count}/${candidate.total_count}`]], 'detail-overview-grid'));"""

NEW_RELATION = """  panel.append(makeMetaGrid([['ADRG', candidate.entity_id], ['MDC', candidate.summary?.mdc ? mdcDisplayText(candidate.summary.mdc, candidate.summary?.mdc_name) : '-'], ['질병군 분류', makeClassificationBadgeGroup((candidate.summary?.abc_display_labels ?? []).length ? candidate.summary.abc_display_labels : [candidate.summary?.classification_code || candidate.summary?.classification_display_label])], ['연결 코드', `${candidate.matched_count}/${candidate.total_count}`]], 'detail-overview-grid'));"""

OLD_ADRG_CONDITION_APPEND = """  fragment.append(
    renderUserConditionSummary(detail),
    renderUserConditionTables(detail),
    ...(SHOW_DEVELOPER_METADATA
      ? [renderUserConditionEvidence(detail)]
      : []),
  );"""

NEW_ADRG_CONDITION_APPEND = """  const aadrgSection = makeSection(
    '파생 AADRG',
    'ADRG에서 파생되는 AADRG와 질병군 분류를 함께 확인합니다.',
    { open: false, count: (detail.aadrg_records ?? []).length },
  );
  aadrgSection.append(renderDerivedAadrgList(detail.aadrg_records));

  fragment.append(
    aadrgSection,
    renderUserConditionSummary(detail),
    renderUserConditionTables(detail),
    ...(SHOW_DEVELOPER_METADATA
      ? [renderUserConditionEvidence(detail)]
      : []),
  );"""

VALIDATOR_JS = r"""'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ELECTRON_ROOT = path.resolve(__dirname, '..');
const { resolveDataFiles } = require('../src/data-paths');
const { KdrgSearchService } = require('../src/kdrg-search-service');
const { SEARCH_ENTITY_TYPES } = require('../src/search-result-contract');

const appPath = path.join(ELECTRON_ROOT, 'renderer', 'app.js');
const app = fs.readFileSync(appPath, 'utf8');

const files = resolveDataFiles({
  isPackaged: false,
  resourcesPath: null,
  moduleDirectory: path.join(ELECTRON_ROOT, 'src'),
});
const service = new KdrgSearchService(files.integrated);

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

function normalizedLabels(values) {
  return [...new Set((values ?? []).map(String).filter(Boolean))].sort();
}

function sameLabels(a, b) {
  return JSON.stringify(normalizedLabels(a)) === JSON.stringify(normalizedLabels(b));
}

check('public search types CODE/ADRG only', () => {
  assert.deepEqual(Array.from(SEARCH_ENTITY_TYPES), ['CODE', 'ADRG']);
});

check('canonical service counts', () => {
  const status = service.status();
  assert.equal(status.counts.adrg_records, 1132);
  assert.equal(status.counts.aadrg_records, 1233);
});

check('relation detail renderer reads abc_display_labels', () => {
  const start = app.indexOf('function renderRelationDetail(');
  const end = app.indexOf('function clearDetail(', start);
  assert.ok(start >= 0 && end > start);
  const body = app.slice(start, end);
  assert.ok(body.includes('candidate.summary?.abc_display_labels'));
  assert.ok(body.includes('질병군 분류'));
  assert.ok(body.includes('makeClassificationBadgeGroup'));
});

check('ADRG detail derived section position/contract', () => {
  const start = app.indexOf('function renderAdrgDetail(');
  const end = app.indexOf('function renderAadrgDetail(', start);
  assert.ok(start >= 0 && end > start);
  const body = app.slice(start, end);

  const meta = body.indexOf('makeMetaGrid([');
  const derived = body.indexOf("'파생 AADRG'");
  const call = body.indexOf('renderDerivedAadrgList(detail.aadrg_records)');
  const condition = body.indexOf('renderUserConditionSummary(detail)');

  assert.ok(meta >= 0);
  assert.ok(derived > meta);
  assert.ok(call > derived);
  assert.ok(condition > call);
  assert.ok(body.includes('open: false'));
});

check('derived AADRG renderer retains classification fields', () => {
  const start = app.indexOf('function renderDerivedAadrgList(');
  const end = app.indexOf('function renderRelatedAdrgList(', start);
  assert.ok(start >= 0 && end > start);
  const body = app.slice(start, end);
  assert.ok(body.includes('summary.classification_code'));
  assert.ok(body.includes('summary.classification_display_label'));
  assert.ok(body.includes('appendClassificationBadges'));
});

const f111Search = service.search('F111', 'ADRG', { limit: 50 });
const f111Direct = f111Search.results.find(
  (row) => row.entity_type === 'ADRG' && row.entity_id === 'F111',
);
const f111Detail = service.getDetail('ADRG', 'F111');

check('F111 direct classification A 전문', () => {
  assert.ok(f111Direct);
  assert.deepEqual(
    normalizedLabels(f111Direct.summary?.abc_display_labels),
    ['질병군 분류(전문)'],
  );
});

check('F111 detail classification A 전문', () => {
  assert.deepEqual(
    normalizedLabels(f111Detail.detail?.abc_display_labels),
    ['질병군 분류(전문)'],
  );
});

check('F1110 derived AADRG A 전문', () => {
  const child = (f111Detail.detail?.aadrg_records ?? [])
    .find((row) => row.entity_id === 'F1110');
  assert.ok(child);
  assert.equal(child.summary?.classification_code, 'A');
  assert.equal(
    child.summary?.classification_display_label,
    '질병군 분류(전문)',
  );
});

const relation = service.relationSearch(
  [
    { code: 'I210', codeType: 'AUTO' },
    { code: 'I211', codeType: 'AUTO' },
  ],
  'AND',
);
const f111Relation = relation.results.find((row) => row.entity_id === 'F111');

check('F111 valid relation fixture I210+I211', () => {
  assert.ok(f111Relation);
});

check('F111 relation classification equals direct/detail', () => {
  assert.ok(f111Relation);
  const relationLabels = f111Relation.summary?.abc_display_labels ?? [];
  assert.ok(relationLabels.length > 0);
  assert.ok(sameLabels(relationLabels, f111Direct.summary?.abc_display_labels));
  assert.ok(sameLabels(relationLabels, f111Detail.detail?.abc_display_labels));
});

check('all 1132 ADRG direct/detail classification parity', () => {
  let scanned = 0;
  const mismatches = [];

  for (const adrg of service.recordMaps.ADRG.keys()) {
    scanned += 1;
    const search = service.search(adrg, 'ADRG', { limit: 50 });
    const direct = search.results.find(
      (row) => row.entity_type === 'ADRG' && row.entity_id === adrg,
    );
    const detail = service.getDetail('ADRG', adrg);

    if (!direct) {
      mismatches.push({ adrg, reason: 'direct exact result missing' });
      continue;
    }

    const a = direct.summary?.abc_display_labels ?? [];
    const b = detail.detail?.abc_display_labels ?? [];
    if (!sameLabels(a, b)) {
      mismatches.push({ adrg, direct: a, detail: b });
    }
  }

  assert.equal(scanned, 1132);
  assert.deepEqual(mismatches, []);
});

check('all 1233 derived AADRG classifications renderable', () => {
  let adrgCount = 0;
  let childCount = 0;
  const missing = [];

  for (const adrg of service.recordMaps.ADRG.keys()) {
    adrgCount += 1;
    const detail = service.getDetail('ADRG', adrg).detail;
    for (const child of detail.aadrg_records ?? []) {
      childCount += 1;
      const code = String(child?.summary?.classification_code ?? '').trim();
      const label = String(
        child?.summary?.classification_display_label ?? '',
      ).trim();

      if (!child?.entity_id || (!code && !label) || !label) {
        missing.push({
          adrg,
          aadrg: child?.entity_id ?? null,
          code,
          label,
        });
      }
    }
  }

  assert.equal(adrgCount, 1132);
  assert.equal(childCount, 1233);
  assert.deepEqual(missing, []);
});

console.log(`stage68d_0516_r6: ${pass} PASS / ${failures.length} FAIL`);
console.log('F111_relation_fixture=I210 + I211 / AND');

if (failures.length) {
  for (const failure of failures) {
    console.log(`- ${failure}`);
  }
  process.exitCode = 1;
}
"""

def run(args, *, cwd=None, timeout=600):
    p = subprocess.run(
        args,
        cwd=(cwd or ROOT),
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    output = (p.stdout or '') + (('\n' + p.stderr) if p.stderr else '')
    return p.returncode, output

def git(*args):
    return run(['git', *args], cwd=ROOT, timeout=120)

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def write_report(status, payload, message=''):
    payload = dict(payload)
    payload['status'] = status
    REPORT_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    lines = [
        'Stage68D R6 — KDRG 0.5.16 Actual',
        '=' * 56,
        f'status={status}',
    ]
    if message:
        lines += ['', message]
    REPORT_TXT.write_text('\n'.join(lines) + '\n', encoding='utf-8')

def main():
    # 1. baseline
    for p in (APP, DATA, SERVICE, STYLES):
        if not p.exists():
            print(f'[FAIL] 필수 파일 없음: {p}')
            return 1

    rc, out = git('rev-parse', 'HEAD')
    head = out.strip() if rc == 0 else ''
    rc, out = git('rev-parse', EXPECTED_TAG)
    tag_commit = out.strip() if rc == 0 else ''

    if head != EXPECTED_HEAD:
        print(f'[FAIL] HEAD 불일치: {head}')
        return 1
    if tag_commit != EXPECTED_HEAD:
        print(f'[FAIL] {EXPECTED_TAG} 불일치: {tag_commit}')
        return 1
    if sha256(DATA) != EXPECTED_DATA_SHA:
        print(f'[FAIL] 운영 JSON SHA 불일치: {sha256(DATA)}')
        return 1

    # 현재 app.js는 0.5.15 tag와 동일해야 한다.
    rc, _ = git(
        'diff', '--quiet', EXPECTED_TAG, '--',
        str(APP.relative_to(ROOT)),
    )
    if rc != 0:
        print('[FAIL] app.js가 electron-v0.5.15 기준과 이미 다름')
        return 1

    if VALIDATOR.exists():
        print('[FAIL] Stage68D validator가 이미 존재함')
        return 1

    original_app = APP.read_text(encoding='utf-8')
    original_service_sha = sha256(SERVICE)
    original_styles_sha = sha256(STYLES)
    original_data_sha = sha256(DATA)

    # 2. exact anchors — 실제 사용자 제공 0.5.15 source 기준
    relation_count = original_app.count(OLD_RELATION)
    adrg_count = original_app.count(OLD_ADRG_CONDITION_APPEND)

    if relation_count != 1 or adrg_count != 1:
        payload = {
            'head': head,
            'relation_anchor_count': relation_count,
            'adrg_anchor_count': adrg_count,
        }
        write_report(
            'FAIL_BEFORE_ACTUAL',
            payload,
            'exact anchor count mismatch; product files unchanged',
        )
        print('[FAIL] exact anchor mismatch — 제품파일 미수정')
        print(f'relation_anchor={relation_count} adrg_anchor={adrg_count}')
        print(f'report={REPORT_TXT.relative_to(ROOT)}')
        return 1

    candidate = original_app.replace(OLD_RELATION, NEW_RELATION, 1)
    candidate = candidate.replace(
        OLD_ADRG_CONDITION_APPEND,
        NEW_ADRG_CONDITION_APPEND,
        1,
    )

    # 3. candidate contract/order
    adrg_start = candidate.find('function renderAdrgDetail(')
    adrg_end = candidate.find('function renderAadrgDetail(', adrg_start)
    adrg_body = candidate[adrg_start:adrg_end]

    positions = {
        'meta': adrg_body.find('makeMetaGrid(['),
        'derived': adrg_body.find("'파생 AADRG'"),
        'derived_call': adrg_body.find(
            'renderDerivedAadrgList(detail.aadrg_records)'
        ),
        'condition': adrg_body.find('renderUserConditionSummary(detail)'),
    }
    if not (
        0 <= positions['meta']
        < positions['derived']
        < positions['derived_call']
        < positions['condition']
    ):
        write_report(
            'FAIL_BEFORE_ACTUAL',
            {'positions': positions},
            'ADRG UI order contract failed; product files unchanged',
        )
        print('[FAIL] candidate UI 순서 계약 실패 — 제품파일 미수정')
        return 1

    relation_start = candidate.find('function renderRelationDetail(')
    relation_end = candidate.find('function clearDetail(', relation_start)
    relation_body = candidate[relation_start:relation_end]
    if (
        'candidate.summary?.abc_display_labels' not in relation_body
        or 'makeClassificationBadgeGroup' not in relation_body
    ):
        print('[FAIL] candidate relation classification 계약 실패 — 제품파일 미수정')
        return 1

    CANDIDATE.write_text(candidate, encoding='utf-8')

    # 4. actual 쓰기 전에 candidate JS 문법
    rc, output = run(
        ['node', '--check', str(CANDIDATE)],
        cwd=ROOT,
        timeout=120,
    )
    if rc != 0:
        write_report(
            'FAIL_BEFORE_ACTUAL',
            {'candidate_node_check_tail': output[-3000:]},
            'candidate app.js syntax failed; product files unchanged',
        )
        print('[FAIL] candidate app.js node --check — 제품파일 미수정')
        print(output[-1000:].strip())
        return 1

    # 변경 diff 저장
    rc, diff_output = run(
        ['git', 'diff', '--no-index', '--', str(APP), str(CANDIDATE)],
        cwd=ROOT,
        timeout=120,
    )
    # git diff --no-index는 차이가 있으면 rc=1이 정상
    DIFF_FILE.write_text(diff_output, encoding='utf-8')
    change_lines = [
        line for line in diff_output.splitlines()
        if (line.startswith('+') or line.startswith('-'))
        and not line.startswith('+++')
        and not line.startswith('---')
    ]
    if not (2 <= len(change_lines) <= 30):
        print(
            f'[FAIL] candidate diff 범위 비정상: '
            f'{len(change_lines)} lines — 제품파일 미수정'
        )
        return 1

    # 5. actual + exact rollback
    validations = []
    try:
        APP.write_text(candidate, encoding='utf-8')
        VALIDATOR.write_text(VALIDATOR_JS, encoding='utf-8')

        checks = [
            (
                'app syntax',
                ['node', '--check', 'renderer/app.js'],
                ELECTRON,
            ),
            (
                'validator syntax',
                [
                    'node', '--check',
                    'tests/validate-stage68d-0516-classification-derived-aadrg.js',
                ],
                ELECTRON,
            ),
            (
                'stage68d exhaustive validator',
                [
                    'node',
                    'tests/validate-stage68d-0516-classification-derived-aadrg.js',
                ],
                ELECTRON,
            ),
            (
                'release validation chain',
                ['npm', 'run', 'check'],
                ELECTRON,
            ),
        ]

        for label, cmd, cwd in checks:
            rc, output = run(cmd, cwd=cwd, timeout=900)
            validations.append({
                'label': label,
                'cmd': ' '.join(cmd),
                'cwd': str(cwd),
                'rc': rc,
                'status': 'PASS' if rc == 0 else 'FAIL',
                'tail': output[-5000:],
            })
            if rc != 0:
                raise RuntimeError(
                    f'{label} 실패\n{output[-3000:]}'
                )

        for script in (
            '50B_validate_kdrg_electron_search_service.py',
            '50C_validate_kdrg_electron_renderer_ui.py',
        ):
            path = ROOT / script
            if not path.exists():
                validations.append({
                    'label': script,
                    'status': 'SKIP_NOT_FOUND',
                })
                continue
            rc, output = run(
                ['python', script],
                cwd=ROOT,
                timeout=900,
            )
            validations.append({
                'label': script,
                'cmd': f'python {script}',
                'cwd': str(ROOT),
                'rc': rc,
                'status': 'PASS' if rc == 0 else 'FAIL',
                'tail': output[-5000:],
            })
            if rc != 0:
                raise RuntimeError(
                    f'{script} 실패\n{output[-3000:]}'
                )

        # 보호 파일 변조 여부
        if sha256(DATA) != original_data_sha:
            raise RuntimeError('운영 JSON이 변경됨')
        if sha256(SERVICE) != original_service_sha:
            raise RuntimeError('search service가 변경됨')
        if sha256(STYLES) != original_styles_sha:
            raise RuntimeError('styles.css가 변경됨')

        rc, status = git(
            'status', '--short', '--',
            str(APP.relative_to(ROOT)),
            str(VALIDATOR.relative_to(ROOT)),
        )

        payload = {
            'head': head,
            'tag': EXPECTED_TAG,
            'candidate_node_check': 'PASS',
            'candidate_change_lines': len(change_lines),
            'ui_order': positions,
            'modified_files': [
                str(APP.relative_to(ROOT)),
                str(VALIDATOR.relative_to(ROOT)),
            ],
            'protected_files': {
                str(DATA.relative_to(ROOT)): 'UNCHANGED',
                str(SERVICE.relative_to(ROOT)): 'UNCHANGED',
                str(STYLES.relative_to(ROOT)): 'UNCHANGED',
            },
            'app_sha256': sha256(APP),
            'validator_sha256': sha256(VALIDATOR),
            'validations': validations,
            'git_status_targets': status.splitlines(),
        }
        write_report('PASS', payload)

        print('[PASS] Stage68D R6 0.5.16 Actual')
        print('candidate_node_check=PASS')
        print(
            'ui_order=ADRG상단정보 -> 파생AADRG -> 분류조건'
        )
        for item in validations:
            print(f"{item['status']} {item['label']}")
        print('operating_json=UNCHANGED')
        print('search_service=UNCHANGED')
        print('styles=UNCHANGED')
        print(f'candidate_diff_lines={len(change_lines)}')
        print(f'app_sha256={sha256(APP)}')
        print(f'validator_sha256={sha256(VALIDATOR)}')
        print(f'report={REPORT_TXT.relative_to(ROOT)}')
        print(f'json={REPORT_JSON.relative_to(ROOT)}')
        return 0

    except Exception as exc:
        APP.write_text(original_app, encoding='utf-8')
        if VALIDATOR.exists():
            VALIDATOR.unlink()

        payload = {
            'head': head,
            'rolled_back': True,
            'error': str(exc),
            'validations': validations,
        }
        write_report('FAIL_ROLLED_BACK', payload, str(exc))

        print('[FAIL] Stage68D R6 — exact rollback 완료')
        print(str(exc).splitlines()[0][:800])
        print(f'report={REPORT_TXT.relative_to(ROOT)}')
        return 1


if __name__ == '__main__':
    sys.exit(main())
