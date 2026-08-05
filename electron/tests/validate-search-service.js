'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { resolveDataFiles } = require('../src/data-paths');
const {
  KdrgSearchError,
  KdrgSearchService,
  SERVICE_SCHEMA_VERSION,
  RESPONSE_SCHEMA_VERSION,
  RELATION_RESPONSE_SCHEMA_VERSION,
  SUPPORTED_DATA_SCHEMA,
  normalizeEntityId,
  normalizeQuery,
  queryTokens,
} = require('../src/kdrg-search-service');
const {
  SearchContractError,
  SEARCH_ENTITY_TYPES,
  normalizeSearchRequest,
  normalizeRelationRequest,
  normalizeDetailRequest,
} = require('../src/search-result-contract');

const ELECTRON_ROOT = path.resolve(__dirname, '..');
const failures = [];
let passCount = 0;

function check(name, actual, expected, predicate = (a, e) => a === e) {
  const passed = Boolean(predicate(actual, expected));
  if (passed) passCount += 1;
  else failures.push({ name, actual, expected });
  return passed;
}

function expectError(name, callback, errorType) {
  try {
    callback();
    failures.push({ name, actual: 'NO_ERROR', expected: errorType.name });
  } catch (error) {
    check(name, error instanceof errorType, true);
  }
}

const requiredFiles = [
  'src/search-normalizer.js',
  'src/search-result-contract.js',
  'src/kdrg-search-service.js',
  'tests/validate-search-service.js',
  'tests/run-search-parity.js',
  'README_STAGE50B.md',
];
for (const relativePath of requiredFiles) {
  check(`필수 파일 ${relativePath}`, fs.existsSync(path.join(ELECTRON_ROOT, relativePath)), true);
}

const dataFiles = resolveDataFiles({
  isPackaged: false,
  resourcesPath: null,
  moduleDirectory: path.join(ELECTRON_ROOT, 'src'),
});
const service = new KdrgSearchService(dataFiles.integrated);
const status = service.status();

check('service schema', status.service_schema_version, SERVICE_SCHEMA_VERSION);
check('response schema', status.response_schema_version, RESPONSE_SCHEMA_VERSION);
check('relation response schema', status.relation_response_schema_version, RELATION_RESPONSE_SCHEMA_VERSION);
check('data schema', status.data_schema_version, SUPPORTED_DATA_SCHEMA);
check('service ready', status.ready, true);
check('ADRG count', status.counts.adrg_records, 1132);
check('AADRG count', status.counts.aadrg_records, 1233);
check('RDRG count', status.counts.rdrg_records, 2699);
check('TABLE count', status.counts.logical_table_records, 1308);
check('CODE count', status.counts.unique_search_codes, 16571);
check('search document count', service.searchDocuments.size, 22943);
check('semantic relationship keys', status.semantic_context_counts.relationship_key_count, 906);
check('semantic occurrence count', status.semantic_context_counts.relationship_occurrence_count, 939);
check('include occurrence', status.semantic_context_counts.include_occurrence, 874);
check('exclude occurrence', status.semantic_context_counts.exclude_occurrence, 65);
check('EXCLUSION base occurrence', status.semantic_context_counts.exclusion_base_occurrence, 28);
check('double-negative include occurrence', status.semantic_context_counts.exclusion_excluded_final_include, 19);
check('legacy misclassification count', status.semantic_context_counts.legacy_misclassification_occurrence, 47);

check('normalize dotted code', normalizeEntityId('A01.0', 'CODE'), 'A010');
check('normalize TABLE', normalizeEntityId(' lt_9610-001 ', 'TABLE'), 'LT_9610001');
check('normalize query spacing', normalizeQuery('  조기   사망  '), '조기 사망');
check('query token dedupe', queryTokens('A010 A010 조기'), ['a010', '조기'], (a, e) => JSON.stringify(a) === JSON.stringify(e));

const exactAudit = service.debugExactIdAudit();
check('전체 entity exact ID audit count', exactAudit.checked, 22943);
check('전체 entity exact ID audit failures', exactAudit.failures, [], (a) => a.length === 0);

const documentFingerprint = service.debugSearchDocumentFingerprint();
check('search document fingerprint count', documentFingerprint.count, 22943);
check('search document fingerprint', documentFingerprint.sha256, '8a832be02ae4dec16c3cfc93d2be8366914c23fdb0872bfa088a1a6c788f56f3');
const semanticFingerprint = service.debugSemanticContextFingerprint();
check('semantic fingerprint keys', semanticFingerprint.key_count, 906);
check('semantic fingerprint occurrence', semanticFingerprint.occurrence_count, 939);
check('semantic fingerprint', semanticFingerprint.sha256, 'e734f6550461414eedf7d2b042ebf4c274d174b9948e29573c516090fbc62405');

const fixtureExpectations = [
  ['E011', 'ALL', {}, 24, ['CODE:E011', 'ADRG:E011']],
  ['A010', 'ALL', {}, 31, ['CODE:A010', 'ADRG:A010']],
  ['A01.0', 'ALL', {}, 5, ['CODE:A010', 'ADRG:A010', 'AADRG:A0100']],
  ['LT_9610_001', 'TABLE', {}, 1, ['TABLE:LT_9610_001']],
  ['9610', ['ADRG', 'AADRG', 'RDRG'], {}, 3, ['ADRG:9610', 'AADRG:96100', 'RDRG:961000']],
  ['조기 사망', 'ALL', {}, 6, ['ADRG:9600', 'AADRG:96000', 'RDRG:960000']],
];
for (const [query, type, options, total, leading] of fixtureExpectations) {
  const response = service.search(query, type, { limit: 50, ...options });
  check(`fixture ${query} schema`, response.schema_version, RESPONSE_SCHEMA_VERSION);
  check(`fixture ${query} total`, response.total_count, total);
  check(
    `fixture ${query} leading`,
    response.results.slice(0, leading.length).map((row) => `${row.entity_type}:${row.entity_id}`),
    leading,
    (a, e) => JSON.stringify(a) === JSON.stringify(e),
  );
}

const e011 = service.getDetail('ADRG', 'E011');
check('E011 detail type', e011.entity_type, 'ADRG');
check('E011 AST', e011.detail.condition_ast.condition_ast_id, 'AST_E011');
check('E011 사용자 조건 TABLE 3개', e011.detail.user_condition_tables.length, 3);
const b013 = service.getDetail('ADRG', 'B013');
check('B013 사용자 TABLE', b013.detail.user_condition_tables.map((item) => item.entity_id), ['LT_B018_002'], (a, e) => JSON.stringify(a) === JSON.stringify(e));
const b014 = service.getDetail('ADRG', 'B014');
check('B014 사용자 TABLE', b014.detail.user_condition_tables.map((item) => item.entity_id), ['LT_B018_003'], (a, e) => JSON.stringify(a) === JSON.stringify(e));
const b018 = service.getDetail('ADRG', 'B018');
check('B018 사용자 TABLE 1·4·5', b018.detail.user_condition_tables.map((item) => item.entity_id), ['LT_B018_001', 'LT_B018_004', 'LT_B018_005'], (a, e) => JSON.stringify(a) === JSON.stringify(e));
const b022 = service.getDetail('ADRG', 'B022');
check('B022 검토 필요', b022.detail.user_condition_status, 'UNRESOLVED_TABLE_LINK');
check('B022 사용자 TABLE 없음', b022.detail.user_condition_tables, [], (a, e) => JSON.stringify(a) === JSON.stringify(e));
const l033 = service.getDetail('ADRG', 'L033');
check('L033 검토 필요', l033.detail.user_condition_status, 'UNRESOLVED_TABLE_LINK');
check('L033 사용자 TABLE 없음', l033.detail.user_condition_tables, [], (a, e) => JSON.stringify(a) === JSON.stringify(e));
const adrg9610 = service.getDetail('ADRG', '9610');
check('9610 명시적 조건 없음', adrg9610.detail.user_condition_status, 'NO_EXPLICIT_CONDITION');
check('9610 사용자 TABLE 없음', adrg9610.detail.user_condition_tables, [], (a, e) => JSON.stringify(a) === JSON.stringify(e));
const table962 = service.getDetail('TABLE', 'LT_9620_002');
check('9620 excluded context', table962.detail.runtime_contexts.some((item) => item.display_role === 'EXCLUDE'), true);
const table961 = service.getDetail('TABLE', 'LT_9610_001');
check('9610 code count', table961.detail.code_records.length, 7);
const codeA010 = service.getDetail('CODE', 'A010');
check('A010 table detail present', codeA010.detail.logical_tables.length > 0, true);


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

function findStrictFixture() {
  for (const [adrg, groups] of service.conditionGroupsByAdrg.entries()) {
    for (const group of groups) {
      const codes = codesForTables(group.include_table_ids).slice(0, 2);
      if (codes.length < 2) continue;
      const response = service.relationSearch(codes.map((code) => ({ code, codeType: 'AUTO' })), 'AND');
      const candidate = response.results.find((item) => item.entity_id === adrg && item.relation_level === 'strict');
      if (candidate) return { adrg, codes, response, candidate };
    }
  }
  return null;
}

function findSplitFixture() {
  for (const [adrg, groups] of service.conditionGroupsByAdrg.entries()) {
    if (groups.length < 2) continue;
    for (let leftIndex = 0; leftIndex < groups.length; leftIndex += 1) {
      for (let rightIndex = leftIndex + 1; rightIndex < groups.length; rightIndex += 1) {
        const leftCodes = codesForTables(groups[leftIndex].include_table_ids);
        const rightCodes = codesForTables(groups[rightIndex].include_table_ids);
        const left = leftCodes[0];
        const right = rightCodes.find((code) => normalizeEntityId(code, 'CODE') !== normalizeEntityId(left, 'CODE'));
        if (!left || !right) continue;
        const response = service.relationSearch([
          { code: left, codeType: 'AUTO' },
          { code: right, codeType: 'AUTO' },
        ], 'AND');
        const candidate = response.results.find((item) => item.entity_id === adrg && item.relation_level === 'split');
        if (candidate) return { adrg, codes: [left, right], response, candidate };
      }
    }
  }
  return null;
}

const strictFixture = findStrictFixture();
check('relation strict fixture discovered', Boolean(strictFixture), true);
if (strictFixture) {
  check('relation strict schema', strictFixture.response.schema_version, RELATION_RESPONSE_SCHEMA_VERSION);
  check('relation strict level', strictFixture.candidate.relation_level, 'strict');
  check('relation strict all inputs', strictFixture.candidate.matched_count, 2);
  check('relation strict candidate ADRG', strictFixture.response.results.some((item) => item.entity_id === strictFixture.adrg), true);
  check('relation strict exact code rows', strictFixture.response.conditions.every((item) => item.exact_code_found), true);
  check('relation group exclusion summaries', strictFixture.candidate.condition_groups.every((group) => Array.isArray(group.exclude_tables)), true);
  const adrgRow = service.recordMaps.ADRG.get(normalizeEntityId(strictFixture.adrg, 'ADRG'));
  const filtered = service.relationSearch(
    strictFixture.codes.map((code) => ({ code, codeType: 'AUTO' })),
    'AND',
    { mdc: adrgRow.mdc },
  );
  check('relation MDC filter keeps matching ADRG', filtered.results.some((item) => item.entity_id === strictFixture.adrg), true);
  const partial = service.relationSearch([
    { code: strictFixture.codes[0], codeType: 'AUTO' },
    { code: 'KDRG_NOT_FOUND_FIXTURE', codeType: 'AUTO' },
  ], 'OR');
  check('relation OR partial level', partial.results.some((item) => item.entity_id === strictFixture.adrg && item.relation_level === 'partial'), true);
  const blockedAnd = service.relationSearch([
    { code: strictFixture.codes[0], codeType: 'AUTO' },
    { code: 'KDRG_NOT_FOUND_FIXTURE', codeType: 'AUTO' },
  ], 'AND');
  check('relation AND missing code excludes ADRG', blockedAnd.results.some((item) => item.entity_id === strictFixture.adrg), false);
}

const splitFixture = findSplitFixture();
check('relation split fixture discovered', Boolean(splitFixture), true);
if (splitFixture) {
  check('relation split level', splitFixture.candidate.relation_level, 'split');
  check('relation split no all-input group', splitFixture.candidate.condition_groups.some((group) => group.all_inputs), false);
}

const exclusionFixture = (() => {
  for (const [adrg, groups] of service.conditionGroupsByAdrg.entries()) {
    const includeCodes = codesForTables(groups.flatMap((group) => group.include_table_ids));
    const excludeCodes = codesForTables(groups.flatMap((group) => group.exclude_table_ids));
    const include = includeCodes[0];
    const exclude = excludeCodes.find((code) => normalizeEntityId(code, 'CODE') !== normalizeEntityId(include, 'CODE'));
    if (!include || !exclude) continue;
    const response = service.relationSearch([
      { code: include, codeType: 'AUTO' },
      { code: exclude, codeType: 'AUTO' },
    ], 'AND');
    if (!response.results.some((item) => item.entity_id === adrg)) return { adrg, include, exclude };
  }
  return null;
})();
check('relation exclusion fixture discovered', Boolean(exclusionFixture), true);

const normalizedSearch = normalizeSearchRequest({
  query: ' A01.0 ',
  entityType: ['CODE', 'ADRG', 'CODE'],
  limit: 25,
  offset: 0,
  mdc: '01',
  classification: '전문',
});
check('request query trim', normalizedSearch.query, 'A01.0');
check('request entity dedupe', normalizedSearch.entityType, ['CODE', 'ADRG'], (a, e) => JSON.stringify(a) === JSON.stringify(e));
check('request classification', normalizedSearch.classification, '전문');
check('public search entity types', SEARCH_ENTITY_TYPES, ['CODE', 'ADRG'], (a, e) => JSON.stringify(a) === JSON.stringify(e));
const normalizedPublicAll = normalizeSearchRequest({ query: 'A0100', entityType: 'ALL', limit: 20 });
check('ALL maps to public search types', normalizedPublicAll.entityType, ['CODE', 'ADRG'], (a, e) => JSON.stringify(a) === JSON.stringify(e));
const publicAadrgLookup = service.search(
  normalizedPublicAll.query,
  normalizedPublicAll.entityType,
  { limit: normalizedPublicAll.limit, offset: normalizedPublicAll.offset },
);
check('public search only CODE/ADRG', publicAadrgLookup.results.every((item) => ['CODE', 'ADRG'].includes(item.entity_type)), true);
check('AADRG code resolves through parent ADRG hierarchy field', publicAadrgLookup.results.some((item) => item.entity_type === 'ADRG' && item.entity_id === 'A010'), true);
const normalizedRelation = normalizeRelationRequest({
  conditions: [
    { code: ' A01.0 ', codeType: 'diagnosis' },
    { code: 'O1311', codeType: 'procedure' },
  ],
  operator: 'and',
  mdc: '04',
  classification: 'B',
});
check('relation request operator', normalizedRelation.operator, 'AND');
check('relation request code normalize', normalizedRelation.conditions[0].normalizedCode, 'A010');
check('relation request code type', normalizedRelation.conditions[1].codeType, 'PROCEDURE');
check('relation request shared MDC', normalizedRelation.mdc, '04');
const normalizedDetail = normalizeDetailRequest({ entityType: 'table', entityId: ' LT_9610_001 ' });
check('detail type normalize', normalizedDetail.entityType, 'TABLE');
check('detail id trim', normalizedDetail.entityId, 'LT_9610_001');

expectError('empty search request rejected', () => normalizeSearchRequest({ query: '' }), SearchContractError);
expectError('invalid entity type rejected', () => normalizeSearchRequest({ query: 'A010', entityType: 'BAD' }), SearchContractError);
expectError('AADRG public filter rejected', () => normalizeSearchRequest({ query: 'A0100', entityType: 'AADRG' }), SearchContractError);
expectError('RDRG public filter rejected', () => normalizeSearchRequest({ query: 'A01000', entityType: 'RDRG' }), SearchContractError);
expectError('TABLE public filter rejected', () => normalizeSearchRequest({ query: 'LT_A010_001', entityType: 'TABLE' }), SearchContractError);
expectError('oversized limit rejected', () => normalizeSearchRequest({ query: 'A010', limit: 501 }), SearchContractError);
expectError('invalid detail rejected', () => normalizeDetailRequest({ entityType: 'BAD', entityId: 'A010' }), SearchContractError);
expectError('relation one condition rejected', () => normalizeRelationRequest({ conditions: [{ code: 'A010' }] }), SearchContractError);
expectError('relation duplicate code rejected', () => normalizeRelationRequest({ conditions: [{ code: 'A01.0' }, { code: 'A010' }] }), SearchContractError);
expectError('relation invalid operator rejected', () => normalizeRelationRequest({ conditions: [{ code: 'A010' }, { code: 'O1311' }], operator: 'XOR' }), SearchContractError);
expectError('relation invalid code type rejected', () => normalizeRelationRequest({ conditions: [{ code: 'A010', codeType: 'BAD' }, { code: 'O1311' }] }), SearchContractError);
expectError('service relation one condition rejected', () => service.relationSearch([{ code: 'A010', codeType: 'AUTO' }], 'AND'), KdrgSearchError);
expectError('service empty query rejected', () => service.search(''), KdrgSearchError);
expectError('service missing detail rejected', () => service.getDetail('CODE', 'NOT_FOUND_CODE'), KdrgSearchError);

const mainSource = fs.readFileSync(path.join(ELECTRON_ROOT, 'main.js'), 'utf8');
const preloadSource = fs.readFileSync(path.join(ELECTRON_ROOT, 'preload.js'), 'utf8');
const bootstrapSource = fs.readFileSync(path.join(ELECTRON_ROOT, 'src/bootstrap-data.js'), 'utf8');
check('main search service singleton', mainSource.includes('new KdrgSearchService'), true);
check('main search request validation', mainSource.includes('normalizeSearchRequest(payload)'), true);
check('main relation request validation', mainSource.includes('normalizeRelationRequest(payload)'), true);
check('main detail request validation', mainSource.includes('normalizeDetailRequest(payload)'), true);
check('main search IPC', mainSource.includes("search: 'kdrg:search'"), true);
check('main relation IPC', mainSource.includes("relationSearch: 'kdrg:relation-search'"), true);
check('main detail IPC', mainSource.includes("detail: 'kdrg:get-detail'"), true);
check('preload search method', preloadSource.includes('search: (request)'), true);
check('preload relation method', preloadSource.includes('relationSearch: (request)'), true);
check('preload detail method', preloadSource.includes('getDetail: (request)'), true);
check('preload ipcRenderer object hidden', preloadSource.includes('ipcRenderer,'), false);
check('bootstrap search connected', bootstrapSource.includes('searchServiceConnected: true'), true);
check('bootstrap Stage 51C', bootstrapSource.includes("stage: '51C_USER_CONDITION_UI_READY'"), true);

console.log('validator=2026-07-31_KDRG_V47_ELECTRON_STAGE50G_PUBLIC_SEARCH_CONTRACT_VALIDATOR_V2');
console.log(`electron_root=${ELECTRON_ROOT}`);
console.log(`node=${process.version}`);
if (failures.length) {
  console.log(`[FAIL] Electron Stage 50C 검색 service 호환성 검증: ${passCount} PASS / ${failures.length} FAIL`);
  console.log('[FAIL 상세]');
  for (const item of failures) {
    console.log(`- ${item.name} | actual=${JSON.stringify(item.actual)} | expected=${JSON.stringify(item.expected)}`);
  }
  process.exitCode = 1;
} else {
  console.log(`[PASS] Electron Stage 50C 검색 service 호환성 검증: ${passCount} PASS / 0 FAIL`);
}
