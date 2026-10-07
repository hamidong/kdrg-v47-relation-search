'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { KdrgSearchService } = require('../src/kdrg-search-service');

const ELECTRON_ROOT = path.resolve(__dirname, '..');
const REPO_ROOT = path.resolve(ELECTRON_ROOT, '..');
const APP_PATH = path.join(ELECTRON_ROOT, 'renderer', 'app.js');
const DATA_PATH = path.join(REPO_ROOT, 'data', 'kdrg_v47_search_integrated_v3.json');

const appJs = fs.readFileSync(APP_PATH, 'utf8');
const service = new KdrgSearchService(DATA_PATH);

assert.match(
  appJs,
  /!\['NO_EXPLICIT_CONDITION', 'TEXT_ONLY'\]\.includes\(coverage\.status\)/,
  'renderer must allow TEXT_ONLY through guarded direct-code candidate path',
);
assert.doesNotMatch(
  appJs,
  /coverage\.status !== 'NO_EXPLICIT_CONDITION'/,
  'legacy NO_EXPLICIT_CONDITION-only gate must be removed',
);
assert.match(
  appJs,
  /const text = structuralText \|\| coverage\.text;/,
  'true textual-condition fallback must remain available',
);
assert.match(
  appJs,
  /sourceIds\.length !== 1/,
  'single-local-source guard must remain',
);
assert.match(
  appJs,
  /directConditionLocalTablePattern\(adrg\)\.test\(tableId\)/,
  'local ADRG TABLE guard must remain',
);
assert.match(
  appJs,
  /codeCount <= 0/,
  'non-empty code-table guard must remain',
);

function uniqueStrings(values) {
  return [...new Set((values || []).map((x) => String(x)).filter(Boolean))];
}

function esc(s) {
  return String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function inspect(adrg) {
  const detail = service.getDetail('ADRG', adrg)?.detail || {};
  const sourceIds = uniqueStrings(detail.source_logical_table_ids);
  const conditionTableIds = uniqueStrings(detail.user_condition_table_ids);
  const text = String(detail.user_condition_text || '').trim();
  const status = String(detail.user_condition_status || '');
  const hasAst = Boolean(detail.condition_ast);
  const localPattern = new RegExp(`^LT_${esc(adrg)}_\\d+$`);
  const localSourceIds = sourceIds.filter((id) => localPattern.test(id));

  let codeCount = 0;
  if (sourceIds.length === 1 && localSourceIds.length === 1) {
    const td = service.getDetail('TABLE', sourceIds[0])?.detail || {};
    codeCount = Number(td.code_count ?? (td.codes || []).length ?? 0);
  }

  const directCandidate = (
    status === 'TEXT_ONLY'
    && !hasAst
    && conditionTableIds.length === 0
    && sourceIds.length === 1
    && localSourceIds.length === 1
    && codeCount > 0
  );

  return {
    adrg,
    status,
    hasAst,
    sourceIds,
    conditionTableIds,
    codeCount,
    text,
    directCandidate,
    markerContamination: directCandidate && (
      /\[PDF_PAGE=/i.test(text)
      || /PRINTED_PAGE=/i.test(text)
      || /\bPROCEDURES?\b/i.test(text)
    ),
  };
}

const all = [];
for (const [id] of service.recordMaps.ADRG.entries()) {
  all.push(inspect(String(id)));
}

const textOnly = all.filter((x) => x.status === 'TEXT_ONLY');
const candidates = all.filter((x) => x.directCandidate);
const markerCandidates = all.filter((x) => x.markerContamination);
const textOnlyNonCandidates = textOnly.filter((x) => !x.directCandidate);

assert.equal(textOnly.length, 143, 'TEXT_ONLY corpus count drift');
assert.equal(candidates.length, 142, 'generalized direct-code candidate count drift');
assert.equal(markerCandidates.length, 99, 'raw marker contamination candidate count drift');
assert.equal(textOnlyNonCandidates.length, 1, 'true/non-direct TEXT_ONLY preservation count drift');

const d150 = inspect('D150');
assert.equal(d150.status, 'TEXT_ONLY');
assert.equal(d150.hasAst, false);
assert.deepEqual(d150.sourceIds, ['LT_D150_001']);
assert.deepEqual(d150.conditionTableIds, []);
assert.equal(d150.codeCount, 12);
assert.equal(d150.directCandidate, true);

const candidateIds = new Set(candidates.map((x) => x.adrg));
assert.ok(candidateIds.has('D150'), 'D150 must be converted by guarded presentation rule');

// Safety contract: this fix is presentation-only. It must not reinterpret AST-based or
// explicit condition-table ADRGs, and it must preserve the one TEXT_ONLY non-candidate.
for (const row of candidates) {
  assert.equal(row.hasAst, false, `${row.adrg} unexpectedly has AST`);
  assert.deepEqual(row.conditionTableIds, [], `${row.adrg} unexpectedly has explicit condition TABLE`);
  assert.equal(row.sourceIds.length, 1, `${row.adrg} source TABLE count`);
  assert.ok(row.codeCount > 0, `${row.adrg} source code count`);
}
for (const row of textOnlyNonCandidates) {
  assert.equal(row.directCandidate, false, `${row.adrg} true TEXT_ONLY must remain fallback`);
}

console.log('[PASS] Stage78B 0.5.22 condition presentation validator', JSON.stringify({
  textOnly: textOnly.length,
  directCandidates: candidates.length,
  markerCandidates: markerCandidates.length,
  preservedTextOnlyNonCandidates: textOnlyNonCandidates.map((x) => x.adrg),
  d150: {
    source: d150.sourceIds[0],
    codeCount: d150.codeCount,
  },
}));
