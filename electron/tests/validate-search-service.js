'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { resolveDataFiles } = require('../src/data-paths');
const {
  KdrgSearchError,
  KdrgSearchService,
  SERVICE_SCHEMA_VERSION,
  RESPONSE_SCHEMA_VERSION,
  SUPPORTED_DATA_SCHEMA,
  normalizeEntityId,
  normalizeQuery,
  queryTokens,
} = require('../src/kdrg-search-service');
const {
  SearchContractError,
  normalizeSearchRequest,
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
const table962 = service.getDetail('TABLE', 'LT_9620_002');
check('9620 excluded context', table962.detail.runtime_contexts.some((item) => item.display_role === 'EXCLUDE'), true);
const table961 = service.getDetail('TABLE', 'LT_9610_001');
check('9610 code count', table961.detail.code_records.length, 7);
const codeA010 = service.getDetail('CODE', 'A010');
check('A010 table detail present', codeA010.detail.logical_tables.length > 0, true);

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
const normalizedDetail = normalizeDetailRequest({ entityType: 'table', entityId: ' LT_9610_001 ' });
check('detail type normalize', normalizedDetail.entityType, 'TABLE');
check('detail id trim', normalizedDetail.entityId, 'LT_9610_001');

expectError('empty search request rejected', () => normalizeSearchRequest({ query: '' }), SearchContractError);
expectError('invalid entity type rejected', () => normalizeSearchRequest({ query: 'A010', entityType: 'BAD' }), SearchContractError);
expectError('oversized limit rejected', () => normalizeSearchRequest({ query: 'A010', limit: 501 }), SearchContractError);
expectError('invalid detail rejected', () => normalizeDetailRequest({ entityType: 'BAD', entityId: 'A010' }), SearchContractError);
expectError('service empty query rejected', () => service.search(''), KdrgSearchError);
expectError('service missing detail rejected', () => service.getDetail('CODE', 'NOT_FOUND_CODE'), KdrgSearchError);

const mainSource = fs.readFileSync(path.join(ELECTRON_ROOT, 'main.js'), 'utf8');
const preloadSource = fs.readFileSync(path.join(ELECTRON_ROOT, 'preload.js'), 'utf8');
const bootstrapSource = fs.readFileSync(path.join(ELECTRON_ROOT, 'src/bootstrap-data.js'), 'utf8');
check('main search service singleton', mainSource.includes('new KdrgSearchService'), true);
check('main search request validation', mainSource.includes('normalizeSearchRequest(payload)'), true);
check('main detail request validation', mainSource.includes('normalizeDetailRequest(payload)'), true);
check('main search IPC', mainSource.includes("search: 'kdrg:search'"), true);
check('main detail IPC', mainSource.includes("detail: 'kdrg:get-detail'"), true);
check('preload search method', preloadSource.includes('search: (request)'), true);
check('preload detail method', preloadSource.includes('getDetail: (request)'), true);
check('preload ipcRenderer object hidden', preloadSource.includes('ipcRenderer,'), false);
check('bootstrap search connected', bootstrapSource.includes('searchServiceConnected: true'), true);
check('bootstrap Stage 50D', bootstrapSource.includes("stage: '50D_ELECTRON_WINDOWS_PACKAGE_READY'"), true);

console.log('validator=2026-07-27_KDRG_V47_ELECTRON_STAGE50C_SEARCH_COMPAT_VALIDATOR_V1');
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
