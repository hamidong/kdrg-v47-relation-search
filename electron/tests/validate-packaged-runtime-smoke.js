'use strict';

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const PACKAGE_VERSION = require('../package.json').version;
const { EventEmitter } = require('node:events');

const {
  RESPONSE_SCHEMA_VERSION,
  RELATION_RESPONSE_SCHEMA_VERSION,
  EXPECTED_COUNTS,
  shouldRunPackagedSmoke,
  validateSearchResponse,
  validateRelationResponse,
  findRelationSmokeFixture,
  validateDetailResponse,
  validateBootstrapCounts,
  waitForRendererLoad,
  runPackagedRuntimeSmoke,
} = require('../src/packaged-runtime-smoke');

const VALIDATOR_VERSION =
  '2026-07-30_KDRG_V47_ELECTRON_PACKAGED_SMOKE_CONTRACT_VALIDATOR_V2';
const checks = [];

function check(name, actual, expected) {
  checks.push({ name, passed: actual === expected, actual, expected });
}

async function expectReject(name, task, expectedMessage) {
  try {
    await task();
    checks.push({
      name,
      passed: false,
      actual: 'resolved',
      expected: `reject includes ${expectedMessage}`,
    });
  } catch (error) {
    const message = String(error?.message || error);
    checks.push({
      name,
      passed: message.includes(expectedMessage),
      actual: message,
      expected: `includes ${expectedMessage}`,
    });
  }
}

class MockWebContents extends EventEmitter {
  setWindowOpenHandler(handler) {
    this.windowOpenHandler = handler;
  }
}

class MockBrowserWindow {
  constructor(options) {
    this.options = options;
    this.webContents = new MockWebContents();
    this.destroyed = false;
    MockBrowserWindow.instances.push(this);
  }

  async loadFile(rendererPath) {
    this.rendererPath = rendererPath;
    setImmediate(() => this.webContents.emit('did-finish-load'));
  }

  isDestroyed() {
    return this.destroyed;
  }

  destroy() {
    this.destroyed = true;
  }
}
MockBrowserWindow.instances = [];

function makeSearchResponse(overrides = {}) {
  return {
    schema_version: RESPONSE_SCHEMA_VERSION,
    query: 'E011',
    normalized_query: 'E011',
    filters: { entity_types: ['ADRG'], mdc: null, classification: null },
    total_count: 1,
    type_counts: { ADRG: 1 },
    offset: 0,
    limit: 10,
    has_more: false,
    results: [{ entity_type: 'ADRG', entity_id: 'E011', label: 'fixture' }],
    ...overrides,
  };
}

function makeRelationResponse(overrides = {}) {
  return {
    schema_version: RELATION_RESPONSE_SCHEMA_VERSION,
    operator: 'AND',
    filters: { mdc: null, classification: null },
    total_count: 1,
    level_counts: { strict: 1 },
    conditions: [
      { code: 'C001', code_type: 'AUTO', table_ids: ['T1'] },
      { code: 'C002', code_type: 'AUTO', table_ids: ['T2'] },
    ],
    results: [{
      entity_type: 'ADRG',
      entity_id: 'E011',
      relation_level: 'strict',
      code_matches: [],
      condition_groups: [{
        group_no: 1,
        group_label: '조건식 1',
        all_inputs: true,
        hit_count: 2,
        matches: [],
        exclude_table_ids: [],
        exclude_tables: [],
      }],
    }],
    disclaimer: 'fixture',
    ...overrides,
  };
}

function makeDetailResponse(overrides = {}) {
  return {
    schema_version: RESPONSE_SCHEMA_VERSION,
    entity_type: 'ADRG',
    entity_id: 'E011',
    detail: { adrg: 'E011' },
    ...overrides,
  };
}

function makeFixture(root, serviceOverrides = {}) {
  const dataFiles = {
    integrated: path.join(root, 'kdrg_v47_search_integrated.json'),
    semanticProfile: path.join(root, 'kdrg_v47_ui_semantic_profile.json'),
    displayContract: path.join(root, 'kdrg_v47_ui_display_contract.json'),
  };
  for (const filePath of Object.values(dataFiles)) {
    fs.writeFileSync(filePath, '{}\n', 'utf8');
  }

  class MockService {
    constructor() {
      this.conditionGroupsByAdrg = new Map([
        ['E011', [{ include_table_ids: ['T1', 'T2'], exclude_table_ids: [] }]],
      ]);
      this.recordMaps = {
        TABLE: new Map([
          ['T1', { logical_table_id: 'T1', codes: ['C001'] }],
          ['T2', { logical_table_id: 'T2', codes: ['C002'] }],
        ]),
      };
    }

    status() {
      return serviceOverrides.status || { ready: true };
    }

    search() {
      return serviceOverrides.search || makeSearchResponse();
    }

    relationSearch() {
      return serviceOverrides.relation || makeRelationResponse();
    }

    getDetail() {
      return serviceOverrides.detail || makeDetailResponse();
    }
  }

  return {
    app: {
      isPackaged: true,
      getVersion: () => PACKAGE_VERSION,
    },
    BrowserWindow: MockBrowserWindow,
    resolveDataFiles: () => dataFiles,
    buildBootstrapSnapshot: () => ({ counts: { ...EXPECTED_COUNTS } }),
    KdrgSearchService: MockService,
    rendererPath: path.join(root, 'index.html'),
    preloadPath: path.join(root, 'preload.js'),
  };
}

async function main() {
  console.log(`validator=${VALIDATOR_VERSION}`);
  console.log(`node=${process.version}`);

  check('smoke env trigger', shouldRunPackagedSmoke([], { KDRG_ELECTRON_SMOKE_TEST: '1' }), true);
  check('smoke argv trigger', shouldRunPackagedSmoke(['--kdrg-smoke-test'], {}), true);
  check('smoke disabled', shouldRunPackagedSmoke([], {}), false);

  const validSearch = makeSearchResponse();
  const validResults = validateSearchResponse(validSearch);
  check('search contract results array', Array.isArray(validResults), true);
  check('search contract E011', validResults[0].entity_id, 'E011');
  const validRelation = makeRelationResponse();
  const validRelationResults = validateRelationResponse(validRelation, 'E011');
  check('relation contract results array', Array.isArray(validRelationResults), true);
  check('relation contract E011', validRelationResults[0].entity_id, 'E011');
  check('relation contract exclusion summary array', Array.isArray(validRelationResults[0].condition_groups[0].exclude_tables), true);
  check('detail contract E011', validateDetailResponse(makeDetailResponse()).entity_id, 'E011');
  check('bootstrap contract counts', validateBootstrapCounts({ counts: { ...EXPECTED_COUNTS } }).codes, 16571, 16571);

  await expectReject(
    'legacy items field controlled failure',
    () => Promise.resolve(validateSearchResponse({
      ...makeSearchResponse(),
      results: undefined,
      items: [{ entity_id: 'E011' }],
    })),
    'obsolete items field detected',
  );
  await expectReject(
    'search schema mismatch controlled failure',
    () => Promise.resolve(validateSearchResponse({ ...makeSearchResponse(), schema_version: 'old' })),
    'schema_version=old',
  );
  await expectReject(
    'search total_count mismatch controlled failure',
    () => Promise.resolve(validateSearchResponse({ ...makeSearchResponse(), total_count: 0 })),
    'total_count=0',
  );
  await expectReject(
    'relation schema mismatch controlled failure',
    () => Promise.resolve(validateRelationResponse({ ...makeRelationResponse(), schema_version: 'old' })),
    'schema_version=old',
  );
  await expectReject(
    'relation result shape controlled failure',
    () => Promise.resolve(validateRelationResponse({ ...makeRelationResponse(), results: [{}] })),
    'invalid results[0]',
  );
  await expectReject(
    'relation fixture missing controlled failure',
    () => Promise.resolve(validateRelationResponse(makeRelationResponse({ results: [{
      entity_type: 'ADRG', entity_id: 'E999', relation_level: 'strict', code_matches: [], condition_groups: [],
    }] }), 'E011')),
    'ADRG E011',
  );

  await expectReject(
    'detail entity mismatch controlled failure',
    () => Promise.resolve(validateDetailResponse(makeDetailResponse({ entity_id: 'E999' }))),
    'E011 detail fixture mismatch',
  );
  await expectReject(
    'bootstrap count mismatch controlled failure',
    () => Promise.resolve(validateBootstrapCounts({ counts: { ...EXPECTED_COUNTS, codes: 1 } })),
    'bootstrap count mismatch: codes=1',
  );

  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'kdrg-smoke-contract-'));
  const previousReport = process.env.KDRG_ELECTRON_SMOKE_REPORT;
  try {
    fs.writeFileSync(path.join(tempRoot, 'index.html'), '<!doctype html>\n', 'utf8');
    fs.writeFileSync(path.join(tempRoot, 'preload.js'), "'use strict';\n", 'utf8');
    const reportPath = path.join(tempRoot, 'smoke-report.json');
    process.env.KDRG_ELECTRON_SMOKE_REPORT = reportPath;

    const fixture = makeFixture(tempRoot);
    const report = await runPackagedRuntimeSmoke(fixture);
    const diskReport = JSON.parse(fs.readFileSync(reportPath, 'utf8'));
    check('runtime smoke PASS', report.status, 'PASS');
    check('runtime report persisted', diskReport.status, 'PASS');
    check('runtime search contract schema', report.search_fixture.response_schema_version, RESPONSE_SCHEMA_VERSION);
    check('runtime result_count uses results', report.search_fixture.result_count, 1);
    check('runtime fixture found', report.search_fixture.found, true);
    check('runtime detail verified', report.search_fixture.detail_entity_id, 'E011');
    check('runtime relation schema', report.relation_fixture.response_schema_version, RELATION_RESPONSE_SCHEMA_VERSION);
    check('runtime relation fixture found', report.relation_fixture.found, true);
    check('runtime relation expected ADRG', report.relation_fixture.expected_adrg, 'E011');
    check('runtime relation discovery helper', findRelationSmokeFixture(new fixture.KdrgSearchService()).adrg, 'E011');
    check('runtime relation step', report.completed_steps.includes('relation_contract_verified'), true);
    check('runtime renderer loaded', report.renderer_loaded, true);
    check('runtime step search contract', report.completed_steps.includes('search_contract_verified'), true);
    check('runtime step renderer', report.completed_steps.at(-1), 'renderer_loaded');
    check('runtime BrowserWindow destroyed', MockBrowserWindow.instances.at(-1).destroyed, true);
    check('runtime contextIsolation', MockBrowserWindow.instances.at(-1).options.webPreferences.contextIsolation, true);
    check('runtime nodeIntegration off', MockBrowserWindow.instances.at(-1).options.webPreferences.nodeIntegration, false);
    check('runtime sandbox on', MockBrowserWindow.instances.at(-1).options.webPreferences.sandbox, true);

    const legacyReportPath = path.join(tempRoot, 'legacy-report.json');
    process.env.KDRG_ELECTRON_SMOKE_REPORT = legacyReportPath;
    await expectReject(
      'runtime legacy contract rejected before renderer',
      () => runPackagedRuntimeSmoke(makeFixture(tempRoot, {
        search: {
          ...makeSearchResponse(),
          results: undefined,
          items: [{ entity_id: 'E011' }],
        },
      })),
      'obsolete items field detected',
    );
    const legacyReport = JSON.parse(fs.readFileSync(legacyReportPath, 'utf8'));
    check('legacy report FAIL', legacyReport.status, 'FAIL');
    check('legacy report descriptive error', legacyReport.error.message.includes('contract mismatch'), true);
    check('legacy report no raw TypeError', legacyReport.error.message.includes('Cannot read properties'), false);
    check('legacy report failed step', legacyReport.failed_step, 'search_contract_validation');
    check('legacy report completed steps', legacyReport.completed_steps.includes('search_service_ready'), true);

    const relationReportPath = path.join(tempRoot, 'relation-report.json');
    process.env.KDRG_ELECTRON_SMOKE_REPORT = relationReportPath;
    await expectReject(
      'runtime relation contract rejected before renderer',
      () => runPackagedRuntimeSmoke(makeFixture(tempRoot, {
        relation: { ...makeRelationResponse(), schema_version: 'old' },
      })),
      'schema_version=old',
    );
    const relationReport = JSON.parse(fs.readFileSync(relationReportPath, 'utf8'));
    check('relation report FAIL', relationReport.status, 'FAIL');
    check('relation report failed step', relationReport.failed_step, 'relation_contract_validation');

    const missingFixture = makeFixture(tempRoot);
    fs.unlinkSync(missingFixture.resolveDataFiles().integrated);
    await expectReject(
      'missing packaged data controlled failure',
      () => runPackagedRuntimeSmoke(missingFixture),
      'packaged data file inaccessible: key=integrated',
    );

    await expectReject(
      'service not ready controlled failure',
      () => runPackagedRuntimeSmoke(makeFixture(tempRoot, { status: { ready: false } })),
      'search service is not ready',
    );

    await expectReject(
      'E011 missing controlled failure',
      () => runPackagedRuntimeSmoke(makeFixture(tempRoot, {
        search: makeSearchResponse({
          total_count: 1,
          results: [{ entity_type: 'ADRG', entity_id: 'E999' }],
        }),
      })),
      'E011 search fixture missing',
    );

    const eventEmitter = new MockWebContents();
    const failedWindow = { webContents: eventEmitter };
    const wait = waitForRendererLoad(failedWindow, 1000);
    setImmediate(() => eventEmitter.emit('did-fail-load', null, -2, 'ERR_FAILED', 'file:///index.html'));
    await expectReject('renderer fail event diagnostic', () => wait, 'renderer load failed: code=-2');
  } finally {
    if (previousReport === undefined) delete process.env.KDRG_ELECTRON_SMOKE_REPORT;
    else process.env.KDRG_ELECTRON_SMOKE_REPORT = previousReport;
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }

  const failures = checks.filter((item) => !item.passed);
  if (failures.length) {
    console.log(`[FAIL] Electron packaged runtime smoke contract 검증: ${checks.length - failures.length} PASS / ${failures.length} FAIL`);
    for (const failure of failures) {
      console.log(`- ${failure.name} | actual=${JSON.stringify(failure.actual)} | expected=${JSON.stringify(failure.expected)}`);
    }
    process.exitCode = 1;
    return;
  }
  console.log(`[PASS] Electron packaged runtime smoke contract 검증: ${checks.length} PASS / 0 FAIL`);
}

main().catch((error) => {
  console.error(error?.stack || error);
  process.exitCode = 1;
});
