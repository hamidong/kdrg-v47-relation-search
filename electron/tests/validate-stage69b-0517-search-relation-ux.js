'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { KdrgSearchService } = require('../src/kdrg-search-service');

const ROOT = path.resolve(__dirname, '..', '..');
const service = new KdrgSearchService(
  path.join(ROOT, 'data', 'kdrg_v47_search_integrated_v3.json'),
);
const app = fs.readFileSync(
  path.join(ROOT, 'electron', 'renderer', 'app.js'),
  'utf8',
);

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

const codeIds = [...service.recordMaps.CODE.keys()].sort();
const adrgIds = [...service.recordMaps.ADRG.keys()].sort();
const shared = codeIds.filter((id) => service.recordMaps.ADRG.has(id));
const codeOnly = codeIds.filter((id) => !service.recordMaps.ADRG.has(id));
const adrgOnly = adrgIds.filter((id) => !service.recordMaps.CODE.has(id));
const publicIds = [...new Set([...codeIds, ...adrgIds])].sort();

check('public namespace counts', () => {
  assert.equal(codeIds.length, 16574);
  assert.equal(adrgIds.length, 1132);
  assert.equal(shared.length, 471);
  assert.equal(codeOnly.length, 16103);
  assert.equal(adrgOnly.length, 661);
  assert.equal(publicIds.length, 17235);
});

check('all 17235 public exact IDs return exact public entities only', () => {
  let mismatchCount = 0;
  const examples = [];

  for (const id of publicIds) {
    const expected = [];
    if (service.recordMaps.CODE.has(id)) expected.push(`CODE:${id}`);
    if (service.recordMaps.ADRG.has(id)) expected.push(`ADRG:${id}`);

    const response = service.search(id, 'ALL', { limit: 10, offset: 0 });
    const actual = response.results.map(
      (row) => `${row.entity_type}:${row.entity_id}`,
    );

    const typeCountExpected = {
      CODE: service.recordMaps.CODE.has(id) ? 1 : 0,
      ADRG: service.recordMaps.ADRG.has(id) ? 1 : 0,
    };

    const ok = JSON.stringify(actual) === JSON.stringify(expected)
      && response.total_count === expected.length
      && Number(response.type_counts?.CODE ?? 0) === typeCountExpected.CODE
      && Number(response.type_counts?.ADRG ?? 0) === typeCountExpected.ADRG;

    if (!ok) {
      mismatchCount += 1;
      if (examples.length < 20) {
        examples.push({
          id,
          expected,
          actual,
          total_count: response.total_count,
          type_counts: response.type_counts,
        });
      }
    }
  }

  assert.equal(
    mismatchCount,
    0,
    `mismatch=${mismatchCount} examples=${JSON.stringify(examples)}`,
  );
});

check('F022 exact pair only', () => {
  const response = service.search('F022', 'ALL', { limit: 10, offset: 0 });
  assert.deepEqual(
    response.results.map((row) => `${row.entity_type}:${row.entity_id}`),
    ['CODE:F022', 'ADRG:F022'],
  );
  assert.ok(
    !response.results.some((row) => row.entity_id === 'U602'),
    'U602 must not leak into exact public-ID search',
  );
});

check('CODE-only exact ID suppresses relation expansion', () => {
  const id = codeOnly[0];
  assert.ok(id, 'CODE-only fixture missing');
  const response = service.search(id, 'ALL', { limit: 10, offset: 0 });
  assert.deepEqual(
    response.results.map((row) => `${row.entity_type}:${row.entity_id}`),
    [`CODE:${id}`],
  );
});

check('ADRG-only exact ID suppresses broad matches', () => {
  const id = adrgOnly[0];
  assert.ok(id, 'ADRG-only fixture missing');
  const response = service.search(id, 'ALL', { limit: 10, offset: 0 });
  assert.deepEqual(
    response.results.map((row) => `${row.entity_type}:${row.entity_id}`),
    [`ADRG:${id}`],
  );
});

check('non-exact text search remains broad', () => {
  const response = service.search('조기 사망', 'ALL', { limit: 20, offset: 0 });
  assert.ok(response.total_count > 0);
  assert.ok(response.results.length > 0);
});

check('type-specific F022 searches remain unchanged', () => {
  const code = service.search('F022', 'CODE', { limit: 10, offset: 0 });
  const adrg = service.search('F022', 'ADRG', { limit: 10, offset: 0 });
  assert.ok(code.results.some(
    (row) => row.entity_type === 'CODE' && row.entity_id === 'F022',
  ));
  assert.ok(adrg.results.some(
    (row) => row.entity_type === 'ADRG' && row.entity_id === 'F022',
  ));
});

check('shared exact pagination contract', () => {
  const first = service.search('F022', 'ALL', { limit: 1, offset: 0 });
  const second = service.search('F022', 'ALL', { limit: 1, offset: 1 });
  assert.equal(first.total_count, 2);
  assert.equal(first.results.length, 1);
  assert.equal(first.has_more, true);
  assert.deepEqual(
    first.results.map((row) => `${row.entity_type}:${row.entity_id}`),
    ['CODE:F022'],
  );
  assert.equal(second.total_count, 2);
  assert.equal(second.results.length, 1);
  assert.equal(second.has_more, false);
  assert.deepEqual(
    second.results.map((row) => `${row.entity_type}:${row.entity_id}`),
    ['ADRG:F022'],
  );
});

const relationFixture = service.relationSearch(
  [
    { code: 'I214', codeType: 'AUTO' },
    { code: 'M6566', codeType: 'AUTO' },
  ],
  'AND',
);

check('relation fixture returns expected comparison ADRGs', () => {
  const ids = new Set(relationFixture.results.map((row) => row.entity_id));
  for (const id of ['F111', 'F112', 'F121', 'F122']) {
    assert.ok(ids.has(id), `missing ${id}`);
  }
});

check('relation fixture carries abc display labels', () => {
  for (const id of ['F111', 'F112', 'F121', 'F122']) {
    const row = relationFixture.results.find((item) => item.entity_id === id);
    assert.ok(row, `missing ${id}`);
    assert.ok(
      Array.isArray(row.summary?.abc_display_labels)
        && row.summary.abc_display_labels.length > 0,
      `${id} abc_display_labels missing`,
    );
  }
});

check('relation result uses abc labels with legacy fallback', () => {
  assert.match(
    app,
    /STAGE69B_RELATION_RESULT_CLASSIFICATION_TITLE_ROW/,
  );
  assert.match(
    app,
    /result\.summary\?\.abc_display_labels/,
  );
  assert.match(
    app,
    /result\.summary\?\.classification_code\s*\|\|\s*result\.summary\?\.classification_display_label/,
  );
  assert.match(
    app,
    /appendClassificationBadges\(\s*relationClassification/,
  );
  assert.match(
    app,
    /main\.append\(relationClassification\)/,
  );
});

check('relation detail loads official ADRG detail', () => {
  assert.match(
    app,
    /async function loadRelationOfficialAdrgConditions/,
  );
  assert.match(
    app,
    /window\.KDRG\.getDetail\(\{[\s\S]*entityType:\s*'ADRG'[\s\S]*candidate\.entity_id/,
  );
});

check('relation detail reuses normal ADRG condition renderers', () => {
  assert.match(app, /renderUserConditionSummary\(detail\)/);
  assert.match(app, /renderUserConditionTables\(detail\)/);
  assert.match(
    app,
    /SHOW_DEVELOPER_METADATA[\s\S]*renderUserConditionEvidence\(detail\)/,
  );
  assert.match(app, /STAGE69B_RELATION_OFFICIAL_CONDITIONS/);
});

check('normal ADRG detail condition renderers remain present', () => {
  assert.match(
    app,
    /function renderAdrgDetail\(payload\)[\s\S]*renderUserConditionSummary\(detail\)[\s\S]*renderUserConditionTables\(detail\)/,
  );
});

console.log(
  `[${failures.length ? 'FAIL' : 'PASS'}] Stage69B R11 0.5.17 exact-public-ID/relation UX validator: ${pass} PASS / ${failures.length} FAIL`,
);
console.log(
  `public_ids=${publicIds.length} code_only=${codeOnly.length} adrg_only=${adrgOnly.length} shared=${shared.length}`,
);
for (const failure of failures) console.log(`- ${failure}`);
if (failures.length) process.exitCode = 1;
