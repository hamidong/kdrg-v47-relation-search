'use strict';

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
