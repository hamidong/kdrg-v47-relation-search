'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { KdrgSearchService } = require('../src/kdrg-search-service');
const { normalizeSearchRequest } = require('../src/search-result-contract');
const Ui = require('../renderer/ui-formatters');

const SCRIPT_VERSION = '2026-07-31_KDRG_V47_ELECTRON_STAGE50G_PUBLIC_RESULT_INLINE_TABLE_UI_VALIDATOR_V3';
const ELECTRON_ROOT = path.resolve(__dirname, '..');
const WORKSPACE_ROOT = path.resolve(ELECTRON_ROOT, '..');
const DATA_PATH = path.join(WORKSPACE_ROOT, 'data', 'kdrg_v47_search_integrated.json');

let passCount = 0;
const failures = [];

function check(name, callback) {
  try {
    callback();
    passCount += 1;
  } catch (error) {
    failures.push(`${name}: ${error.message}`);
  }
}

function read(relative) {
  return fs.readFileSync(path.join(ELECTRON_ROOT, relative), 'utf8');
}

const html = read('renderer/index.html');
const appJs = read('renderer/app.js');
const formattersJs = read('renderer/ui-formatters.js');
const css = read('renderer/styles.css');
const packageJson = JSON.parse(read('package.json'));

for (const relative of [
  'renderer/index.html',
  'renderer/app.js',
  'renderer/styles.css',
  'renderer/ui-formatters.js',
  'tests/validate-renderer-ui.js',
  'README_STAGE50C.md',
]) {
  check(`필수 파일 ${relative}`, () => assert.ok(fs.statSync(path.join(ELECTRON_ROOT, relative)).size > 0));
}

check('HTML ko 언어', () => assert.match(html, /<html lang="ko">/));
check('CSP 유지', () => assert.match(html, /Content-Security-Policy/));
check('외부 연결 차단', () => assert.match(html, /connect-src 'none'/));
check('인라인 script 없음', () => assert.doesNotMatch(html, /<script(?![^>]+src=)[^>]*>/));
check('formatter가 app보다 먼저 로드', () => {
  assert.ok(html.indexOf('./ui-formatters.js') < html.indexOf('./app.js'));
});

check('HTML ID 중복 없음', () => {
  const ids = [...html.matchAll(/\sid="([^"]+)"/g)].map((match) => match[1]);
  assert.equal(new Set(ids).size, ids.length);
});
check('상단 헤더 컴팩트 구조', () => {
  assert.match(html, /class="topbar compact-topbar"/);
  assert.match(html, /class="version-chip" id="data-version"/);
  assert.doesNotMatch(html, /class="subtitle"/);
  assert.doesNotMatch(html, />통합 검색</);
  assert.doesNotMatch(html, />코드·질병군·TABLE 검색</);
});
check('검색 패널 컴팩트 구조', () => {
  assert.match(html, /class="search-panel compact-search-panel"/);
  assert.match(html, /class="search-support-row"/);
  assert.match(html, /placeholder="코드·ADRG·질병군명 입력"/);
});
check('유틸리티 한 줄 배치', () => assert.match(html, /class="utility-row"/));
check('결과·상세 헤더 간소화', () => {
  assert.match(html, /class="panel-heading compact-panel-heading result-panel-heading"/);
  assert.match(html, /class="panel-heading compact-panel-heading detail-panel-heading"/);
});

for (const id of [
  'status-title',
  'status-detail',
  'search-form',
  'search-query',
  'filter-type',
  'filter-mdc',
  'filter-classification',
  'search-submit',
  'search-reset',
  'data-overview',
  'relation-search-panel',
  'relation-form',
  'relation-condition-list',
  'relation-operator',
  'relation-add',
  'relation-reset',
  'relation-submit',
  'result-list',
  'result-count',
  'type-counts',
  'page-previous',
  'page-next',
  'detail-content',
  'detail-heading',
  'detail-fold-actions',
  'detail-expand-all',
  'detail-collapse-all',
  'metric-adrg',
  'metric-table',
  'metric-code',
  'metric-condition',
]) {
  check(`HTML ID ${id}`, () => assert.match(html, new RegExp(`id="${id}"`)));
}

check('전체 검색 유형', () => assert.match(html, /value="ALL">전체/));
for (const type of ['CODE', 'ADRG']) {
  check(`사용자 검색 유형 ${type}`, () => assert.match(html, new RegExp(`value="${type}"`)));
}
for (const type of ['AADRG', 'RDRG', 'TABLE']) {
  check(`사용자 검색 유형 ${type} 제거`, () => assert.doesNotMatch(html, new RegExp(`<option value="${type}"`)));
}
for (const code of ['A', 'B', 'C']) {
  check(`질병군 분류 ${code}`, () => assert.match(html, new RegExp(`value="${code}"`)));
}
check('MDC 01', () => assert.match(html, /value="01">MDC 01/));
check('MDC 25', () => assert.match(html, /value="25">MDC 25/));
check('예시 E011', () => assert.match(html, /data-sample-query="E011"/));
check('예시 A01.0', () => assert.match(html, /data-sample-query="A01\.0"/));
check('접근성 live region', () => assert.match(html, /aria-live="polite"/));
check('데이터 현황 기본 접힘', () => {
  const tag = html.match(/<details[^>]+id="data-overview"[^>]*>/)?.[0] || '';
  assert.doesNotMatch(tag, /\sopen(?:\s|>|=)/);
});
check('관계검색 기본 접힘', () => {
  const tag = html.match(/<details[^>]+id="relation-search-panel"[^>]*>/)?.[0] || '';
  assert.doesNotMatch(tag, /\sopen(?:\s|>|=)/);
});
check('관계검색 주의문구', () => assert.match(html, /최종 DRG 판정을 의미하지 않습니다/));
check('관계검색 AND', () => assert.match(html, /value="AND"/));
check('관계검색 OR', () => assert.match(html, /value="OR"/));
check('기존 검색 필터 유지', () => {
  assert.match(html, /id="filter-type"/);
  assert.match(html, /id="filter-mdc"/);
  assert.match(html, /id="filter-classification"/);
});

check('renderer require 미사용', () => assert.doesNotMatch(appJs, /\brequire\s*\(/));
check('renderer innerHTML 미사용', () => assert.doesNotMatch(appJs, /\.innerHTML\b/));
check('renderer insertAdjacentHTML 미사용', () => assert.doesNotMatch(appJs, /insertAdjacentHTML/));
check('renderer eval 미사용', () => assert.doesNotMatch(appJs, /\beval\s*\(/));
check('renderer textContent 사용', () => assert.match(appJs, /textContent/));
check('renderer replaceChildren 사용', () => assert.match(appJs, /replaceChildren/));
check('검색 bridge 사용', () => assert.match(appJs, /window\.KDRG\.search/));
check('관계검색 bridge 사용', () => assert.match(appJs, /window\.KDRG\.relationSearch/));
check('상세 bridge 사용', () => assert.match(appJs, /window\.KDRG\.getDetail/));
check('검색 status bridge 사용', () => assert.match(appJs, /window\.KDRG\.getSearchStatus/));
check('기본 TABLE 섹션', () => assert.match(appJs, /기본 분류 TABLE/));
check('추가 분기조건 섹션', () => assert.match(appJs, /추가 분기조건/));
check('제외 문구', () => assert.match(appJs, /단, 다음 대상은 제외/));
check('기술식 접기', () => assert.match(appJs, /기술식·원문 근거 보기/));
check('상세 section details 사용', () => assert.match(appJs, /create\('details', 'detail-section'\)/));
check('전체 펼치기 제어', () => assert.match(appJs, /setAllDetailSections\(true\)/));
check('전체 접기 제어', () => assert.match(appJs, /setAllDetailSections\(false\)/));

check('검색결과 컴팩트 행 구조', () => assert.match(appJs, /create\('div', 'result-card-main'\)/));
check('검색결과 보조 메타 행', () => assert.match(appJs, /result-meta-row/));
check('상세 핵심 요약 함수', () => assert.match(appJs, /function detailSummaryLine\(payload\)/));
check('상세 요약 그리드', () => assert.match(appJs, /detail-overview-grid/));
check('상태 문구 간소화', () => {
  assert.match(appJs, /`\$\{Ui\.formatNumber\(response\.total_count\)\}건`/);
  assert.doesNotMatch(appJs, /건을 찾았습니다/);
});
check('TABLE 코드 기본 접힘', () => assert.match(appJs, /makeSection\('TABLE 코드'[\s\S]*open: false/));
check('TABLE 카드 인라인 details', () => assert.match(appJs, /create\('details', `table-card inline-table-card/));
check('TABLE 클릭 시 인라인 상세 로드', () => assert.match(appJs, /async function loadInlineTable\(/));
check('TABLE 기술 상세 보조 버튼', () => assert.match(appJs, /TABLE 기술 상세/));
check('PDF 원문 TABLE명 추출', () => assert.match(appJs, /OFFICIAL_TABLE_LABEL_PATTERN/));
check('내부 TABLE ID 보조표시', () => assert.match(appJs, /내부 ID \$\{tableId\}/));
check('TABLE명 미수록 정직 표시', () => assert.match(appJs, /원문 TABLE명 미수록/));
check('파생 AADRG 정적 표시', () => assert.match(appJs, /function renderDerivedAadrgList\(/));
check('전체 펼치기 인라인 TABLE 포함', () => assert.match(appJs, /details\.detail-section, #detail-content details\.table-card/));
check('관계검색 조건 최소 2개 초기화', () => assert.match(appJs, /addRelationCondition\(\);[\s\S]*addRelationCondition\(\);/));
check('관계검색 최대 6개', () => assert.match(appJs, /childElementCount >= 6/));
check('관계 level strict 설명', () => assert.match(appJs, /같은 조건 선택지/));
check('관계 level split 경고', () => assert.match(appJs, /서로 다른 OR 조건 선택지/));
check('관계검색 제외 TABLE 표시', () => assert.match(appJs, /relation-group-exclusion/));
check('관계검색 sequence guard', () => assert.match(appJs, /relationSequence/));
check('TABLE 코드 표시 상한', () => assert.match(appJs, /const limit = 160/));
check('검색 sequence guard', () => assert.match(appJs, /searchSequence/));
check('상세 sequence guard', () => assert.match(appJs, /detailSequence/));

for (const className of [
  'workspace',
  'result-card',
  'detail-panel',
  'condition-group',
  'condition-exclusion',
  'technical-details',
  'code-grid',
  'entity-badge',
  'status-dot',
  'data-overview',
  'relation-search-panel',
  'relation-condition-row',
  'relation-result-card',
  'relation-level-notice',
  'relation-group-exclusion',
  'detail-fold-actions',
  'section-title-row',
  'compact-topbar',
  'version-chip',
  'compact-search-panel',
  'utility-row',
  'compact-panel-heading',
  'result-card-main',
  'result-meta-row',
  'detail-hero',
  'detail-overview-grid',
  'inline-table-card',
  'table-card-summary',
  'inline-table-content',
  'inline-code-row',
  'table-technical-button',
  'derived-aadrg-row',
]) {
  check(`CSS class ${className}`, () => assert.match(css, new RegExp(`\\.${className.replace('-', '\\-')}`)));
}
check('고정 색상모드', () => assert.match(css, /color-scheme: light/));
check('최소 화면 폭', () => assert.match(css, /min-width: 1180px/));

check('컴팩트 헤더 높이', () => assert.match(css, /\.compact-topbar[\s\S]*?min-height:\s*52px/));
check('컴팩트 결과 카드 여백', () => assert.match(css, /\.result-card[\s\S]*?padding:\s*8px 9px/));
check('메인 상세 비중 확대', () => assert.match(css, /grid-template-columns:\s*minmax\(330px, 0\.31fr\) minmax\(720px, 0\.69fr\)/));
check('상세 accordion 컴팩트 높이', () => assert.match(css, /\.detail-section > \.section-header[\s\S]*?min-height:\s*42px/));

check('formatter module export', () => assert.equal(typeof Ui.buildConditionGroups, 'function'));
check('숫자 포맷', () => assert.equal(Ui.formatNumber(16571), '16,571'));
check('점유형 label CODE', () => assert.equal(Ui.entityLabel('CODE'), '코드'));
check('역할 procedure', () => assert.equal(Ui.roleLabel('procedure'), '수술·처치코드'));
check('역할 unknown', () => assert.equal(Ui.roleLabel('unknown'), '코드(유형 미확정)'));
check('분류 A', () => assert.equal(Ui.classificationLabel('A'), '질병군 분류(전문)'));
check('중복 문자열 제거', () => assert.deepEqual(Ui.uniqueStrings(['A', 'A', '', 'B']), ['A', 'B']));
check('목록 축약', () => assert.equal(Ui.summarizeList(['A', 'B', 'C'], 2), 'A, B 외 1개'));
check('빈 AST', () => assert.deepEqual(Ui.buildConditionGroups(null), []));

const service = new KdrgSearchService(DATA_PATH);
check('service ready', () => assert.equal(service.status().ready, true));
const publicRequest = normalizeSearchRequest({ query: 'A01.0', entityType: 'ALL', limit: 20 });
const publicResults = service.search(publicRequest.query, publicRequest.entityType, { limit: publicRequest.limit });
check('renderer ALL 계약 CODE/ADRG만 요청', () => assert.deepEqual(publicRequest.entityType, ['CODE', 'ADRG']));
check('renderer 결과 CODE/ADRG만 표시', () => assert.ok(publicResults.results.every((item) => ['CODE', 'ADRG'].includes(item.entity_type))));
check('검색 문서 수', () => assert.equal(service.debugSearchDocumentFingerprint().count, 22943));
check('관계검색 service method', () => assert.equal(typeof service.relationSearch, 'function'));
check('관계검색 condition group index', () => assert.ok(service.conditionGroupsByAdrg instanceof Map));
check('관계검색 AST ADRG 존재', () => assert.ok([...service.conditionGroupsByAdrg.values()].some((groups) => groups.length > 0)));

const e011 = service.getDetail('ADRG', 'E011').detail;
const e011Groups = Ui.buildConditionGroups(e011.condition_ast);
check('E011 조건 그룹 2개', () => assert.equal(e011Groups.length, 2));
check('E011 첫 그룹 include table1', () => assert.deepEqual(e011Groups[0].includes[0].table_ids, ['LT_E011_001']));
check('E011 두 번째 include table2', () => assert.deepEqual(e011Groups[1].includes[0].table_ids, ['LT_E011_002']));
check('E011 두 번째 exclude 부가코드', () => assert.deepEqual(e011Groups[1].excludes[0].table_ids, ['LT_E011_003']));
check('E011 coverage AST', () => assert.equal(Ui.conditionCoverage(e011).has_condition_ast, true));
check('E011 기본 TABLE 3개', () => assert.equal(Ui.conditionCoverage(e011).basic_table_ids.length, 3));

const detail9610 = service.getDetail('ADRG', '9610').detail;
check('9610 AST 없음', () => assert.equal(detail9610.condition_ast, null));
check('9610 coverage 기본 TABLE만', () => assert.equal(Ui.conditionCoverage(detail9610).state, 'BASIC_TABLE_NO_EXTRA_CONDITION'));
check('9610 기본 TABLE ID', () => assert.deepEqual(Ui.conditionCoverage(detail9610).basic_table_ids, ['LT_9610_001']));

const detail9620 = service.getDetail('ADRG', '9620').detail;
const groups9620 = Ui.buildConditionGroups(detail9620.condition_ast);
check('9620 조건 그룹 1개', () => assert.equal(groups9620.length, 1));
check('9620 include 진단 TABLE', () => assert.deepEqual(groups9620[0].includes[0].table_ids, ['LT_9620_001']));
check('9620 exclude 시술 TABLE', () => assert.deepEqual(groups9620[0].excludes[0].table_ids, ['LT_9620_002']));

const resultA010 = service.search('A01.0', 'ALL', { limit: 20 });
check('A01.0 점표기 검색', () => assert.ok(resultA010.results.some((item) => item.entity_type === 'CODE' && item.entity_id === 'A010')));
const resultE011 = service.search('E011', 'ALL', { limit: 20 });
check('E011 ADRG 검색', () => assert.ok(resultE011.results.some((item) => item.entity_type === 'ADRG' && item.entity_id === 'E011')));
const result9610 = service.search('9610', 'ALL', { limit: 20 });
check('9610 ADRG 검색', () => assert.ok(result9610.results.some((item) => item.entity_type === 'ADRG' && item.entity_id === '9610')));
check('결과 chip ADRG', () => assert.ok(Ui.resultSummaryChips(resultE011.results.find((item) => item.entity_type === 'ADRG')).some((item) => item.includes('MDC'))));

check('package validate:ui', () => assert.equal(packageJson.scripts['validate:ui'], 'node tests/validate-renderer-ui.js'));
check('package validate 연결', () => assert.match(packageJson.scripts.validate, /validate:ui/));
check('package check formatter', () => assert.match(packageJson.scripts.check, /renderer\/ui-formatters\.js/));
check('package check UI validator', () => assert.match(packageJson.scripts.check, /validate-renderer-ui\.js/));
check('Electron pin 유지', () => assert.equal(packageJson.devDependencies.electron, '43.2.0'));
check('Node engine 유지', () => assert.equal(packageJson.engines.node, '>=22.0.0'));

console.log(`validator=${SCRIPT_VERSION}`);
console.log(`electron_root=${ELECTRON_ROOT}`);
console.log(`node=${process.version}`);
if (failures.length) {
  console.log(`[FAIL] Electron Stage 50C renderer UI 검증: ${passCount} PASS / ${failures.length} FAIL`);
  for (const failure of failures) console.log(`- ${failure}`);
  process.exitCode = 1;
} else {
  console.log(`[PASS] Electron Stage 50C renderer UI 검증: ${passCount} PASS / 0 FAIL`);
}
