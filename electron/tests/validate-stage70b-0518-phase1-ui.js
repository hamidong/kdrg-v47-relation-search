'use strict';

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

check('relation context preserved after card-chip relocation', () => {
  assert.match(relation, /relation_level_label/);
  assert.doesNotMatch(relation, /result-match-chip/);
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

