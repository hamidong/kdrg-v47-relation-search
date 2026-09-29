'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..', '..');
const app = fs.readFileSync(
  path.join(ROOT, 'electron', 'renderer', 'app.js'),
  'utf8',
);
const css = fs.readFileSync(
  path.join(ROOT, 'electron', 'renderer', 'styles.css'),
  'utf8',
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

check('header summary communicates common related ADRG results', () => {
  assert.match(counts, /STAGE72B_RELATION_SUMMARY_R4/);
  assert.match(counts, /strict:\s*'공통 관련 ADRG'/);
  assert.match(counts, /split:\s*'공통 관련 ADRG'/);
  assert.match(counts, /partial:\s*'부분 관련 ADRG'/);
  assert.match(counts, /같은 선택지/);
  assert.match(counts, /다른 선택지/);
  assert.match(counts, /일부 연결/);
  assert.match(counts, /relation-summary-chip/);
});

check('relation card removes individual relation-level chip', () => {
  assert.match(relation, /STAGE72B_RELATION_CLASSIFICATION_TOP_RIGHT_R4/);
  assert.doesNotMatch(relation, /result-match-chip/);
  assert.doesNotMatch(
    relation,
    /main\.append\(\s*makeChip\(\s*result\.relation_level_label/,
  );
});

check('existing relation classification remains in main', () => {
  assert.match(relation, /STAGE69B_RELATION_RESULT_CLASSIFICATION_TITLE_ROW/);
  assert.match(relation, /result-card-classification/);
  assert.match(relation, /abc_display_labels/);
  assert.match(relation, /main\.append\(relationClassification\)/);
});

check('relation classification is appended exactly once', () => {
  const matches = relation.match(/main\.append\(relationClassification\)/g) || [];
  assert.equal(matches.length, 1);
});

check('relation semantic level remains available', () => {
  assert.match(relation, /relation_level_label/);
  assert.match(app, /function relationLevelDescription/);
  assert.match(app, /candidate\.relation_level_label/);
});

check('summary chip is only slightly larger than normal chip', () => {
  const rule = css.match(/\.relation-summary-chip\s*\{([\s\S]*?)\}/);
  assert.ok(rule, 'relation-summary-chip CSS missing');
  assert.match(rule[1], /min-height\s*:\s*23px\s*;/);
  assert.match(rule[1], /padding\s*:\s*4px\s+9px\s*;/);
  assert.match(rule[1], /font-size\s*:\s*11px\s*;/);
  assert.match(rule[1], /font-weight\s*:\s*800\s*;/);
});

check('general ADRG result classification remains intact', () => {
  assert.match(
    general,
    /String\(result\.entity_type \?\? ''\)\.toUpperCase\(\) === 'ADRG'/,
  );
  assert.match(general, /result-card-classification/);
  assert.match(general, /abc_display_labels/);
});

check('public search policy remains CODE and ADRG', () => {
  assert.match(app, /for \(const type of \['CODE', 'ADRG'\]\)/);
});

console.log(
  `[${fail.length ? 'FAIL' : 'PASS'}] Stage72B R4 / 0.5.19 relation-result layout: ${pass} PASS / ${fail.length} FAIL`,
);
for (const item of fail) console.log(`- ${item}`);
if (fail.length) process.exitCode = 1;

