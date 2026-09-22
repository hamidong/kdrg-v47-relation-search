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

check('public type ADRG', () => {
  assert.match(html, /value="ADRG">ADRG/);
  assert.doesNotMatch(html, /<option value="AADRG">/);
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

check('CODE detail hero is ADRG centered', () => {
  const body = functionBlock(app, 'detailSummaryLine');
  const codeStart = body.indexOf("if (payload.entity_type === 'CODE')");
  assert.ok(codeStart >= 0);
  const codeBody = body.slice(codeStart);
  assert.match(codeBody, /관련 ADRG/);
  assert.match(codeBody, /related_adrg_summaries/);
  assert.doesNotMatch(codeBody, /연결 TABLE/);
  assert.doesNotMatch(codeBody, /related_adrgs/);
});

check('CODE detail section is ADRG centered', () => {
  const body = functionBlock(app, 'renderCodeDetail');
  assert.match(body, /'관련 ADRG'/);
  assert.doesNotMatch(body, /'관련 AADRG'/);
  assert.doesNotMatch(body, /'포함 TABLE'/);
  assert.doesNotMatch(body, /'연결 TABLE'/);
});

check('ADRG overview metric uses ADRG count', () => {
  const body = functionBlock(app, 'renderMetrics');
  assert.match(
    body,
    /setText\('metric-aadrg', Ui\.formatNumber\(snapshot\.counts\.adrg\)\)/,
  );
});

check('TABLE technical hidden', () => {
  assert.doesNotMatch(app, /TABLE 기술 상세/);
  assert.doesNotMatch(app, /table-technical-button/);
  assert.doesNotMatch(app, /내부 ID \$\{tableId\}/);
});

check('PDF-style AST formatter exported / compact', () => {
  assert.equal(typeof Ui.buildPrettyConditionTree, 'function');
  assert.match(app, /Ui\.buildPrettyConditionTree/);
  assert.doesNotMatch(app, /function prettyConditionLines/);

  const body = functionBlock(app, 'appendPrettyConditionNode');
  const render = functionBlock(app, 'renderPrettyCondition');

  assert.match(app, /function appendCompactConditionToken/);
  assert.match(body, /condition-pretty-bracket-inline/);
  assert.match(body, /op\('and not'\)/);
  assert.match(render, /condition-pretty-line-compact/);
  assert.match(render, /index === 0 \? '' : tree\.operator/);
  assert.doesNotMatch(body, /condition-pretty-group/);

  assert.match(
    css,
    /Stage63B: 0\.5\.12 compact condition presentation/,
  );
  assert.match(css, /flex-wrap:\s*wrap/);
  assert.match(
    css,
    /\.condition-pretty-expression-compact[\s\S]*margin-left:\s*0/,
  );
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

check('relation ADRG', () => {
  assert.match(app, /관계검색 ADRG/);
  assert.match(app, /makeBadge\('ADRG'\)/);
  assert.match(app, /ADRG 상세 보기/);
  assert.doesNotMatch(app, /ADRG 전체 상세/);
});

check('formatter public counts', () => {
  assert.match(fmt, /const ordered = \['CODE', 'ADRG'\]/);
});

check('Stage63B generic parent direct-condition inheritance', () => {
  const body = functionBlock(app, 'directConditionTables');
  assert.match(body, /detail\?\.parent_adrg_detail/); assert.match(body, /childParentAdrg === parentAdrg/); assert.match(body, /inheritedFromParent: sourceDetail !== detail/); assert.doesNotMatch(body, /F2120|F212/);
});
check('Stage63B compact condition renderer', () => {
  const body = functionBlock(app, 'appendPrettyConditionNode'); const render = functionBlock(app, 'renderPrettyCondition');
  assert.match(app, /function appendCompactConditionToken/); assert.match(body, /condition-pretty-bracket-inline/); assert.match(body, /op\('and not'\)/); assert.match(render, /condition-pretty-line-compact/); assert.doesNotMatch(body, /condition-pretty-group/); assert.match(css, /Stage63B: 0\.5\.12 compact condition presentation/); assert.match(css, /flex-wrap:\s*wrap/);
});
check('Stage63B direct-condition wording', () => {
  const body = functionBlock(app, 'conditionPresentation'); assert.match(body, /직접 코드 조건/); assert.match(body, /이 질병군의 분류 조건입니다/); assert.doesNotMatch(body, /TABLE 번호 없는 직접 코드조건/);
});
check('Stage63B F2120 source evidence remains intact', () => {
  const { KdrgSearchService: S63 } = require(path.join(root, 'src/kdrg-search-service.js'));
  const s63 = new S63(path.resolve(root, '..', 'data', 'kdrg_v47_search_integrated_v3.json'));
  const d = s63.getDetail('AADRG', 'F2120').detail; assert.equal(d.adrg, 'F212'); assert.deepEqual(d.source_logical_table_ids ?? [], []); assert.deepEqual(d.parent_adrg_detail.source_logical_table_ids ?? [], ['LT_F212_001']);
  const t=s63.getDetail('TABLE','LT_F212_001').detail; const codes=new Set((t.code_records||[]).map(x=>x.entity_id)); for(const c of ['O0205','O0206','O0241','O2223']) assert.ok(codes.has(c),c);
});

check('Stage64B official condition source map', () => {
  const official = require(
    path.join(root, 'renderer/official-condition-text.js'),
  );
  assert.equal(
    official.meta.schema_version,
    'kdrg-official-condition-text-v3-authority-overlay',
  );
  assert.equal(
    official.meta.base_source_pdf_sha256,
    'f88cc3810639b72fb4a28a2484ea6e4da7988b101ce2866c40c45ecd0d0e8ae4',
  );
  assert.equal(
    official.meta.correction_source_sha256,
    '5199c2cd75a11da722557b08e2d8a59cf147af08507b85ccf4044ed0361718b3',
  );
  assert.equal(official.meta.ast_adrg_count, 390);
  assert.equal(official.meta.override_adrg_count, 121);
  assert.equal(official.meta.base_pdf_override_count, 120);
  assert.equal(official.meta.official_correction_override_count, 1);
  assert.equal(official.meta.ast_fallback_already_matches_count, 269);
  assert.equal(Object.keys(official.byAdrg).length, 121);
  assert.match(
    official.byAdrg.P651.text,
    /시술명 table2을 제외한 OR procedure/,
  );
  assert.doesNotMatch(
    official.byAdrg.P651.text,
    /OR procedure\s+and not\(시술명 table2\)/,
  );
  assert.equal(
    official.byAdrg.F022.source_kind,
    'OFFICIAL_CORRECTION_20260731',
  );
  assert.equal(
    official.byAdrg.F022.text,
    '(시술명 table2 and 시술명 table 3) or 시술명 table6',
  );
});

check('Stage64B source-first condition renderer contract', () => {
  const stage64Index = fs.readFileSync(
    path.join(root, 'renderer/index.html'),
    'utf8',
  );
  const render = functionBlock(app, 'renderPrettyCondition');
  const helper = functionBlock(app, 'officialConditionDisplayText');

  assert.match(
    stage64Index,
    /official-condition-text\.js/,
  );
  assert.ok(
    stage64Index.indexOf('official-condition-text.js')
      < stage64Index.indexOf('app.js'),
  );
  assert.match(helper, /KDRGOfficialConditionText/);
  assert.match(render, /officialConditionDisplayText\(detail\)/);
  assert.match(render, /conditionSource = 'official-pdf'/);
  assert.match(render, /conditionSource = 'ast-fallback'/);
  assert.match(render, /Ui\.buildPrettyConditionTree/);
});

console.log(`stage59_ui: ${pass} PASS / ${fail.length} FAIL`);
if (fail.length) {
  fail.forEach((item) => console.log(`- ${item}`));
  process.exitCode = 1;
}
