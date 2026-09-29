'use strict';

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
