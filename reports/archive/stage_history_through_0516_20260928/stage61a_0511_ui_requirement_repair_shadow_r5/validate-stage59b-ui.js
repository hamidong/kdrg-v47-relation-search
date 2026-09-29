'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'renderer/index.html'), 'utf8');
const app = fs.readFileSync(path.join(root, 'renderer/app.js'), 'utf8');
const fmt = fs.readFileSync(path.join(root, 'renderer/ui-formatters.js'), 'utf8');
const css = fs.readFileSync(path.join(root, 'renderer/styles.css'), 'utf8');
const Ui = require(path.join(root, 'renderer/ui-formatters.js'));

let pass = 0;
const fail = [];

function check(name, fn) {
  try { fn(); pass += 1; }
  catch (error) { fail.push(`${name}: ${error.message}`); }
}

function functionBlock(source, name) {
  const start = source.indexOf(`function ${name}(`);
  assert.ok(start >= 0, `${name} 함수 없음`);
  const next = source.indexOf('\nfunction ', start + 20);
  return source.slice(start, next > start ? next : source.length);
}

check('public type AADRG', () => {
  assert.match(html, /value="AADRG">AADRG/);
  assert.doesNotMatch(html, /<option value="ADRG">/);
});

check('MDC dynamic', () => {
  assert.match(app, /function populateMdcFilter/);
  assert.doesNotMatch(html, /value="24">MDC 24/);
  assert.doesNotMatch(html, /value="25">MDC 25/);
});

check('history', () => {
  assert.match(html, /id="detail-back"/);
  assert.match(app, /historyStack/);
  assert.match(app, /relation-detail/);
  assert.match(app, /restoreWindowScroll/);
  assert.doesNotMatch(app, /openFirst/);
});

check('AADRG detail', () => {
  assert.match(app, /function renderAadrgDetail/);
  assert.match(app, /'관련 코드'/);
  assert.match(app, /renderUserConditionSummary\(detail\)/);
  assert.match(app, /renderUserConditionTables\(detail\)/);
});

check('related AADRG is clickable', () => {
  const body = functionBlock(app, 'renderDerivedAadrgList');
  assert.match(body, /create\('button', 'derived-aadrg-row'\)/);
  assert.match(body, /row\.dataset\.entityType = 'AADRG'/);
  assert.match(body, /row\.dataset\.entityId = String\(record\.entity_id/);
  assert.match(app, /\[data-entity-type\]\[data-entity-id\]/);
  assert.match(app, /openDetail\(entityButton\.dataset\.entityType, entityButton\.dataset\.entityId\)/);
});

check('related AADRG names wrap', () => {
  assert.match(css, /\.derived-aadrg-main \.derived-aadrg-name[\s\S]*white-space:\s*normal/);
  assert.match(css, /\.derived-aadrg-row[\s\S]*cursor:\s*pointer/);
});

check('CODE detail hero is AADRG centered', () => {
  const body = functionBlock(app, 'detailSummaryLine');
  const codeStart = body.indexOf("if (payload.entity_type === 'CODE')");
  assert.ok(codeStart >= 0);
  const codeBody = body.slice(codeStart);
  assert.match(codeBody, /관련 AADRG/);
  assert.match(codeBody, /related_aadrg_summaries/);
  assert.doesNotMatch(codeBody, /연결 TABLE/);
  assert.doesNotMatch(codeBody, /related_adrgs/);
});

check('CODE detail section is AADRG centered', () => {
  const body = functionBlock(app, 'renderCodeDetail');
  assert.match(body, /'관련 AADRG'/);
  assert.doesNotMatch(body, /'관련 ADRG'/);
  assert.doesNotMatch(body, /'포함 TABLE'/);
  assert.doesNotMatch(body, /'연결 TABLE'/);
});

check('AADRG overview metric uses AADRG count', () => {
  const body = functionBlock(app, 'renderMetrics');
  assert.match(
    body,
    /setText\('metric-aadrg', Ui\.formatNumber\(snapshot\.counts\.aadrg\)\)/,
  );
});

check('TABLE technical hidden', () => {
  assert.doesNotMatch(app, /TABLE 기술 상세/);
  assert.doesNotMatch(app, /table-technical-button/);
  assert.doesNotMatch(app, /내부 ID \$\{tableId\}/);
});

check('PDF-style AST formatter exported', () => {
  assert.equal(typeof Ui.buildPrettyConditionTree, 'function');
  assert.match(app, /Ui\.buildPrettyConditionTree/);
  assert.doesNotMatch(app, /function prettyConditionLines/);
  assert.match(css, /condition-pretty-group/);
  assert.match(css, /--condition-depth/);
  assert.match(app, /\$\{leadingOperator\} not/);
  assert.match(app, /const childDepth = nested \|\| compound \? depth \+ 1 : depth/);
});

check('P651-like nested AST stays nested', () => {
  const ast = {
    root_node_id: 'root',
    nodes: [
      { node_id: 'root', node_type: 'AND', child_node_ids: ['weight', 'exclude', 'major'] },
      { node_id: 'weight', node_type: 'TEXT_CONDITION', display_text: '입원시 체중 1500 - 1999g' },
      { node_id: 'exclude', node_type: 'NOT', child_node_ids: ['exclude_or'] },
      { node_id: 'exclude_or', node_type: 'OR', child_node_ids: ['table2', 'vent96'] },
      { node_id: 'table2', node_type: 'TABLE_REF', display_text: '시술명 table2', logical_table_ids: ['LT_P651_002'] },
      { node_id: 'vent96', node_type: 'TEXT_CONDITION', display_text: '인공호흡 ≥ 96 hours' },
      { node_id: 'major', node_type: 'AND', child_node_ids: ['major_or', 'multiple'] },
      { node_id: 'major_or', node_type: 'OR', child_node_ids: ['table3', 'vent24', 'major_problem'] },
      { node_id: 'table3', node_type: 'TABLE_REF', display_text: '시술명 table3', logical_table_ids: ['LT_P651_003'] },
      { node_id: 'vent24', node_type: 'TEXT_CONDITION', display_text: '인공호흡 > 24 hours' },
      { node_id: 'major_problem', node_type: 'TEXT_CONDITION', display_text: '주요 문제' },
      { node_id: 'multiple', node_type: 'TEXT_CONDITION', display_text: '다발성 주요 문제' },
    ],
  };
  const tree = Ui.buildPrettyConditionTree(ast);
  assert.equal(tree.kind, 'group');
  assert.equal(tree.operator, 'and');
  assert.equal(tree.children.length, 3);
  assert.equal(tree.children[1].kind, 'not');
  assert.equal(tree.children[1].child.kind, 'group');
  assert.equal(tree.children[1].child.operator, 'or');
  assert.equal(tree.children[2].kind, 'group');
  assert.equal(tree.children[2].operator, 'and');
  assert.equal(tree.children[2].children[0].operator, 'or');
});

check('condition summary/detail roles remain separated', () => {
  const summary = functionBlock(app, 'renderUserConditionSummary');
  assert.match(summary, /renderPrettyCondition\(detail, coverage\.text\)/);
  assert.match(app, /function renderUserConditionTables/);
  assert.match(app, /function renderConditionGroup/);
});

check('relation AADRG', () => {
  assert.match(app, /관계검색 AADRG/);
  assert.match(app, /makeBadge\('AADRG'\)/);
  assert.match(app, /AADRG 상세 보기/);
  assert.doesNotMatch(app, /ADRG 전체 상세/);
});

check('formatter public counts', () => {
  assert.match(fmt, /const ordered = \['CODE', 'AADRG'\]/);
});

console.log(`stage59_ui: ${pass} PASS / ${fail.length} FAIL`);
if (fail.length) {
  fail.forEach((item) => console.log(`- ${item}`));
  process.exitCode = 1;
}
