'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { KdrgSearchService } = require('../src/kdrg-search-service');
const { normalizeSearchRequest } = require('../src/search-result-contract');
const Ui = require('../renderer/ui-formatters');

const SCRIPT_VERSION = '2026-08-07_KDRG_V47_ELECTRON_STAGE53C_ADRG_NAME_RECOVERY_VALIDATOR_V5';
const ELECTRON_ROOT = path.resolve(__dirname, '..');
const WORKSPACE_ROOT = path.resolve(ELECTRON_ROOT, '..');
const DATA_PATH = path.join(WORKSPACE_ROOT, 'data', 'kdrg_v47_search_integrated_v3.json');

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
check('분류 조건 섹션', () => assert.match(appJs, /'분류 조건'/));
check('조건 상세 섹션', () => assert.match(appJs, /'조건 상세'/));
check('원문 근거 섹션', () => assert.match(appJs, /'원문 근거'/));
check('Stage56 개발 메타 기본 숨김', () => {
  assert.match(appJs, /const SHOW_DEVELOPER_METADATA = false/);

  const adrgStart = appJs.indexOf('function renderAdrgDetail(payload)');
  const adrgEnd = appJs.indexOf('function renderAadrgDetail(payload)');
  assert.ok(adrgStart >= 0);
  assert.ok(adrgEnd > adrgStart);

  const renderAdrgSource = appJs.slice(adrgStart, adrgEnd);

  assert.match(
    renderAdrgSource,
    /\.\.\.\(SHOW_DEVELOPER_METADATA[\s\S]*?'조건 상태'[\s\S]*?: \[\]\)/,
  );
  assert.match(
    renderAdrgSource,
    /\.\.\.\(SHOW_DEVELOPER_METADATA[\s\S]*?renderUserConditionEvidence\(detail\)[\s\S]*?: \[\]\)/,
  );
  assert.doesNotMatch(
    renderAdrgSource,
    /\['조건 상태',\s*userConditionStatusLabel/,
  );
});

check('Stage56 분류조건 기술상태 기본 숨김', () => {
  assert.match(
    appJs,
    /SHOW_DEVELOPER_METADATA[\s\S]*?\|\| coverage\.needs_review/,
  );
  assert.match(
    appJs,
    /ADRG 분류에 적용되는 조건입니다/,
  );
});

check('Stage56 질병군 분류 badge helper', () => {
  assert.match(
    appJs,
    /const CLASSIFICATION_BADGE_META = Object\.freeze/,
  );
  assert.match(
    appJs,
    /function makeClassificationBadge\(/,
  );
  assert.match(
    appJs,
    /function appendClassificationBadges\(/,
  );
  assert.match(
    appJs,
    /function makeClassificationBadgeGroup\(/,
  );
  assert.match(
    appJs,
    /function classificationCode\(/,
  );
});

check('Stage56 검색결과 분류 badge 사용', () => {
  assert.match(
    appJs,
    /function appendResultSummaryMeta\(/,
  );
  assert.match(
    appJs,
    /appendResultSummaryMeta\(chips, result\)/,
  );
  assert.match(
    appJs,
    /appendClassificationBadges\([\s\S]*?summary\.abc_display_labels/,
  );
});

check('Stage56 ADRG 상세 분류 badge 사용', () => {
  assert.match(
    appJs,
    /makeClassificationBadgeGroup\([\s\S]*?detail\.abc_classification_codes/,
  );
  assert.match(
    appJs,
    /detail-hero-classification/,
  );
  assert.match(
    appJs,
    /classification-badge-group/,
  );
});
check('구형 기본 TABLE 제거', () => assert.doesNotMatch(appJs, /기본 분류 TABLE/));
check('구형 추가 분기조건 제거', () => assert.doesNotMatch(appJs, /추가 분기조건/));
check('사용자 조건 TABLE 계약', () => assert.match(appJs, /detail\.user_condition_tables/));
check('추정 TABLE 표시 금지', () => assert.match(appJs, /TABLE을 추정 표시하지 않습니다/));
check('상세 section details 사용', () => assert.match(appJs, /create\('details', 'detail-section'\)/));
check('전체 펼치기 제어', () => assert.match(appJs, /setAllDetailSections\(true\)/));
check('전체 접기 제어', () => assert.match(appJs, /setAllDetailSections\(false\)/));

check('검색결과 컴팩트 행 구조', () => assert.match(appJs, /create\('div', 'result-card-main'\)/));
check('검색결과 보조 메타 행', () => assert.match(appJs, /result-meta-row/));
check('상세 핵심 요약 함수', () => assert.match(appJs, /function detailSummaryLine\(payload\)/));
check('ADRG 명칭 null 방어 함수', () => assert.match(appJs, /function displayNameText\(/));
check('ADRG 표시명 전용 함수', () => assert.match(appJs, /function adrgDisplayName\(/));
check('ADRG 상세 제목 null 방어', () => assert.match(appJs, /\$\{detail\.adrg\} · \$\{adrgDisplayName\(detail\)\}/));
check('ADRG 메타 명칭 null 방어', () => assert.match(appJs, /\['질병군명', adrgDisplayName\(detail\)\]/));
check('ADRG 원시 명칭 직접 보간 제거', () => assert.doesNotMatch(appJs, /\$\{detail\.adrg\} · \$\{detail\.adrg_name\}/));
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
check('TABLE 코드·코드명 검색', () => assert.match(appJs, /현재 TABLE의 코드 또는 코드명 검색/));
check('TABLE 검색형 2열 표', () => assert.match(appJs, /create\('table', 'inline-code-table'\)/));
check('TABLE 전체 코드 표시', () => assert.doesNotMatch(appJs, /const limit = 160/));
check('직접 코드조건 판별', () => assert.match(appJs, /function directConditionTables\(/));
check('직접 코드조건 단일 원천 TABLE 제한', () => assert.match(appJs, /sourceIds\.length !== 1/));
check('직접 코드조건 ADRG 로컬 TABLE 제한', () => assert.match(appJs, /function directConditionLocalTablePattern\(/));
check('직접 코드조건 중립 라벨', () => assert.match(appJs, /분류 코드 목록/));
check('직접 코드조건 중립 설명', () => assert.match(appJs, /아래 코드 목록 자체가 이 ADRG의 분류 조건입니다/));
check('WITHOUT 제외 구조', () => assert.match(appJs, /제외 조건 · WITHOUT/));
check('AND·OR·WITHOUT 시각 토큰', () => assert.match(appJs, /condition-operator-without/));
check('조건 연산자 보조문구 제거', () => {
  assert.doesNotMatch(appJs, /AND · 모두 충족/);
  assert.doesNotMatch(appJs, /OR · 하나 선택/);
  assert.doesNotMatch(appJs, /WITHOUT · 해당 시 제외/);
});
check('조건 구조 기반 요약 함수', () => assert.match(appJs, /function conditionGroupsExpression\(/));
check('조건 구조식 우선 표시', () => assert.match(appJs, /const text = structuralText \|\| coverage\.text/));
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
  'inline-code-table',
  'inline-code-search',
  'condition-logic-group',
  'condition-exclude-block',
  'direct-condition-block',
  'table-technical-button',
  'derived-aadrg-row',
  'user-condition-summary',
  'user-condition-text',
  'user-condition-warning',
  'user-condition-empty',
  'user-condition-table-stack',
  'user-condition-evidence',
  'classification-badge',
  'classification-code',
  'classification-badge-group',
  'classification-a',
  'classification-b',
  'classification-c',
  'detail-hero-classification',
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
check('사용자 조건 formatter export', () => assert.equal(typeof Ui.userConditionCoverage, 'function'));

const service = new KdrgSearchService(DATA_PATH);
check('service ready', () => assert.equal(service.status().ready, true));
const integratedData = JSON.parse(fs.readFileSync(DATA_PATH, 'utf8'));
const missingAdrgNames = (integratedData.adrg_records ?? []).filter((record) => {
  const value = String(record?.adrg_name ?? '').trim();
  return !value || /^(null|none|undefined)$/i.test(value);
});
check('ADRG 데이터 1,132개', () => assert.equal((integratedData.adrg_records ?? []).length, 1132));
check('ADRG 명칭 누락 0개', () => assert.equal(missingAdrgNames.length, 0));

const detailI653Name = service.getDetail('ADRG', 'I653').detail;
check('I653 공식 ADRG명', () => assert.equal(detailI653Name.adrg_name, '병적 골절을 포함한 결합조직의 악성종양(방사선치료 및 화학요법을 받지 않은 경우)'));
const detailI760Name = service.getDetail('ADRG', 'I760').detail;
check('I760 복원 ADRG명', () => assert.equal(detailI760Name.adrg_name, '기타 근골격계 질환'));
const detailB510Name = service.getDetail('ADRG', 'B510').detail;
check('B510 복원 ADRG명', () => assert.equal(detailB510Name.adrg_name, '뇌파검사'));
const detailT620Name = service.getDetail('ADRG', 'T620').detail;
check('T620 한 글자 ADRG명', () => assert.equal(detailT620Name.adrg_name, '열'));

const searchI653Name = service.search('병적 골절을 포함한 결합조직의 악성종양', 'ADRG', { limit: 100 });
check('I653 복원 명칭검색', () => assert.ok(searchI653Name.results.some((item) => item.entity_type === 'ADRG' && item.entity_id === 'I653')));
const searchI760Name = service.search('기타 근골격계 질환', 'ADRG', { limit: 50 });
check('I760 복원 명칭검색', () => assert.ok(searchI760Name.results.some((item) => item.entity_type === 'ADRG' && item.entity_id === 'I760')));
const searchB510Name = service.search('뇌파검사', 'ADRG', { limit: 50 });
check('B510 복원 명칭검색', () => assert.ok(searchB510Name.results.some((item) => item.entity_type === 'ADRG' && item.entity_id === 'B510')));
const searchT620Name = service.search('열', 'ADRG', { limit: 50 });
check('T620 한 글자 명칭검색', () => assert.ok(searchT620Name.results.some((item) => item.entity_type === 'ADRG' && item.entity_id === 'T620')));
const publicRequest = normalizeSearchRequest({ query: 'A01.0', entityType: 'ALL', limit: 20 });
const publicResults = service.search(publicRequest.query, publicRequest.entityType, { limit: publicRequest.limit });
check('renderer ALL 계약 CODE/ADRG만 요청', () => assert.deepEqual(publicRequest.entityType, ['CODE', 'ADRG']));
check('renderer 결과 CODE/ADRG만 표시', () => assert.ok(publicResults.results.every((item) => ['CODE', 'ADRG'].includes(item.entity_type))));
check('검색 문서 수', () => assert.equal(service.debugSearchDocumentFingerprint().count, 22943));
check('관계검색 service method', () => assert.equal(typeof service.relationSearch, 'function'));
check('관계검색 condition group index', () => assert.ok(service.conditionGroupsByAdrg instanceof Map));
check('관계검색 AST ADRG 존재', () => assert.ok([...service.conditionGroupsByAdrg.values()].some((groups) => groups.length > 0)));

const e011 = service.getDetail('ADRG', 'E011').detail;
check('E011 질병군 분류 A 전문', () => {
  assert.ok((e011.abc_classification_codes ?? []).includes('A'));
  assert.ok((e011.abc_display_labels ?? []).some((value) => String(value).includes('전문')));
});
const detailB172Stage56 = service.getDetail('ADRG', 'B172').detail;
check('B172 질병군 분류 C 단순', () => {
  assert.ok((detailB172Stage56.abc_classification_codes ?? []).includes('C'));
  assert.ok((detailB172Stage56.abc_display_labels ?? []).some((value) => String(value).includes('단순')));
});
check('Stage56 분류 badge CSS A/B/C 개별색', () => {
  assert.match(css, /\.classification-a[\s\S]*?background:/);
  assert.match(css, /\.classification-b[\s\S]*?background:/);
  assert.match(css, /\.classification-c[\s\S]*?background:/);
});
const e011Groups = Ui.buildConditionGroups(e011.condition_ast);
check('E011 조건 그룹 2개', () => assert.equal(e011Groups.length, 2));
check('E011 첫 그룹 include table1', () => assert.deepEqual(e011Groups[0].includes[0].table_ids, ['LT_E011_001']));
check('E011 두 번째 include table2', () => assert.deepEqual(e011Groups[1].includes[0].table_ids, ['LT_E011_002']));
check('E011 두 번째 exclude 부가코드', () => assert.deepEqual(e011Groups[1].excludes[0].table_ids, ['LT_E011_003']));
check('E011 사용자 조건 AST', () => assert.equal(Ui.userConditionCoverage(e011).status, 'RESOLVED_AST'));
check('E011 사용자 조건 TABLE 3개', () => assert.equal(Ui.userConditionCoverage(e011).table_count, 3));

const detailB013 = service.getDetail('ADRG', 'B013').detail;
check('B013 사용자 table2', () => assert.deepEqual(Ui.userConditionCoverage(detailB013).table_ids, ['LT_B018_002']));
const detailB018 = service.getDetail('ADRG', 'B018').detail;
check('B018 사용자 TABLE 1·4·5', () => assert.deepEqual(Ui.userConditionCoverage(detailB018).table_ids, ['LT_B018_001', 'LT_B018_004', 'LT_B018_005']));
const detailB022 = service.getDetail('ADRG', 'B022').detail;
check('B022 검토 필요', () => assert.equal(Ui.userConditionCoverage(detailB022).needs_review, true));
check('B022 TABLE 카드 없음', () => assert.deepEqual(detailB022.user_condition_tables, []));
const detailL033 = service.getDetail('ADRG', 'L033').detail;
check('L033 검토 필요', () => assert.equal(Ui.userConditionCoverage(detailL033).needs_review, true));
check('L033 TABLE 카드 없음', () => assert.deepEqual(detailL033.user_condition_tables, []));

const detail9610 = service.getDetail('ADRG', '9610').detail;
check('9610 AST 없음', () => assert.equal(detail9610.condition_ast, null));
check('9610 원천 status 보존', () => assert.equal(Ui.userConditionCoverage(detail9610).status, 'NO_EXPLICIT_CONDITION'));
check('9610 명시적 사용자 TABLE 없음', () => assert.deepEqual(Ui.userConditionCoverage(detail9610).table_ids, []));
check('9610 source TABLE 존재', () => assert.deepEqual(detail9610.source_logical_table_ids, ['LT_9610_001']));
check('9610 source TABLE ADRG 요약 존재', () => {
  const summary = detail9610.logical_tables.find((item) => item.entity_id === 'LT_9610_001');
  assert.ok(summary);
  assert.equal(Number(summary.summary?.code_count ?? 0), 7);
});
check('9610 단일 로컬 TABLE 구조', () => {
  assert.equal(detail9610.source_logical_table_ids.length, 1);
  assert.match(detail9610.source_logical_table_ids[0], /^LT_9610_\d{3}$/);
});
check('9610 직접 코드조건 UI 계약', () => assert.match(appJs, /DIRECT_CODE_CONDITION/));

const detailI760 = service.getDetail('ADRG', 'I760').detail;
check('I760 다중 원천 TABLE 36개', () => assert.equal(detailI760.source_logical_table_ids.length, 36));
check('I760 공용 TABLE 포함', () => assert.ok(
  detailI760.source_logical_table_ids.some((tableId) => tableId.startsWith('LT_GROUP_')),
));
check('I760 직접 코드조건 자동 승격 차단 계약', () => assert.match(appJs, /sourceIds\.length !== 1/));

const detail9620 = service.getDetail('ADRG', '9620').detail;
const groups9620 = Ui.buildConditionGroups(detail9620.condition_ast);
check('9620 조건 그룹 1개', () => assert.equal(groups9620.length, 1));
check('9620 include 진단 TABLE', () => assert.deepEqual(groups9620[0].includes[0].table_ids, ['LT_9620_001']));
check('9620 exclude 시술 TABLE', () => assert.deepEqual(groups9620[0].excludes[0].table_ids, ['LT_9620_002']));
check('9620 표시용 TABLE 라벨', () => {
  assert.match(groups9620[0].includes[0].display_text, /주진단명\s*table1/i);
  assert.match(groups9620[0].excludes[0].display_text, /시술명\s*table2/i);
});
const detailF600 = service.getDetail('ADRG', 'F600').detail;
const groupsF600 = Ui.buildConditionGroups(detailF600.condition_ast);
check('F600 조건 그룹 2개', () => assert.equal(groupsF600.length, 2));
check('F600 첫 OR 분기 주진단명 table1', () => {
  assert.equal(groupsF600[0].includes.length, 1);
  assert.match(groupsF600[0].includes[0].display_text, /주진단명\s*table1/i);
});
check('F600 두 번째 OR 분기 AND 2개', () => {
  assert.equal(groupsF600[1].includes.length, 2);
  const labels = groupsF600[1].includes.map((item) => item.display_text).join(' | ');
  assert.match(labels, /주진단명\s*table2/i);
  assert.match(labels, /기타진단명\s*table3/i);
});
const conditionLabelCollisionCases = [
  ['C063', 'LT_C064_004', '부가코드 table1'],
  ['C063', 'LT_C064_005', '부가코드 table2'],
  ['C064', 'LT_C064_004', '부가코드 table1'],
  ['C064', 'LT_C064_005', '부가코드 table2'],
  ['D062', 'LT_D068_005', '부가코드 table1'],
  ['D062', 'LT_D068_006', '부가코드 table2'],
  ['G222', 'LT_G224_002', '부가코드 table1'],
  ['G222', 'LT_G224_003', '부가코드 table2'],
  ['G242', 'LT_G242_002', '부가코드 table1'],
  ['G242', 'LT_G242_003', '부가코드 table2'],
];
function conditionRefMatchesTable(ref, tableId) {
  return [
    ref?.entity_id,
    ref?.logical_table_id,
    ref?.table_id,
    ref?.id,
  ]
    .filter(Boolean)
    .map(String)
    .includes(String(tableId));
}
check('조건 요약 TABLE 충돌 일반화 helper', () => {
  assert.match(appJs, /function conditionDisambiguatedLeafTerms\(/);
  assert.match(appJs, /function conditionNumberedRefLabels\(/);
  assert.match(appJs, /user_condition_table_refs/);
  assert.match(appJs, /conditionGroupsExpression\(groups, detail\)/);
});
check('구조식 operator는 uppercase 논리연산자만 토큰화', () => {
  assert.match(appJs, /const strictOperators = options\.strictOperators === true/);
  assert.match(appJs, /\? \/\(\\bAND\\b\|\\bOR\\b\|\\bWITHOUT\\b\)\/g/);
  assert.match(appJs, /: \/\(\\bAND\\b\|\\bOR\\b\|\\bWITHOUT\\b\)\/gi/);
  assert.match(appJs, /structural_text: Boolean\(structuralText\)/);
  assert.match(appJs, /strictOperators: coverage\.structural_text === true/);
});
for (const adrg of ['C063', 'C064']) {
  const detail = service.getDetail('ADRG', adrg).detail;
  const groups = Ui.buildConditionGroups(detail.condition_ast);
  check(`${adrg} source phrase with or without 보존 근거`, () => {
    const texts = groups.flatMap((group) => [
      ...(group.includes ?? []).flatMap((leaf) => [
        leaf.display_text,
        leaf.source_fragment,
      ]),
      ...(group.excludes ?? []).flatMap((leaf) => [
        leaf.display_text,
        leaf.source_fragment,
      ]),
      ...(group.requirements ?? []).map(
        (item) => item.text || item.display_text || '',
      ),
    ]).map((value) => String(value || ''));
    assert.ok(texts.some((value) => /with or without/i.test(value)));
  });
}
for (const [adrg, tableId, expectedLabel] of conditionLabelCollisionCases) {
  const detail = service.getDetail('ADRG', adrg).detail;
  check(`${adrg} ${tableId} 공식 numbered label`, () => {
    const refs = (detail.user_condition_table_refs ?? [])
      .filter((ref) => conditionRefMatchesTable(ref, tableId));
    assert.ok(refs.length >= 1);
    const labels = refs
      .map((ref) => String(ref.display_label ?? '').trim())
      .filter(Boolean);
    assert.ok(labels.includes(expectedLabel));
  });
}

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
