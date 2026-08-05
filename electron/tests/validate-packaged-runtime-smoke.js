'use strict';

const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {
  RESPONSE_SCHEMA_VERSION,
  RELATION_RESPONSE_SCHEMA_VERSION,
  UI_SMOKE_SCHEMA_VERSION,
  EXPECTED_COUNTS,
  UI_FIXTURES,
  REQUIRED_DETAIL_LABELS,
  FORBIDDEN_DETAIL_LABELS,
  shouldRunPackagedSmoke,
  validateSearchResponse,
  validateRelationResponse,
  validateDetailResponse,
  validateBootstrapCounts,
  normalizeConsoleMessage,
  validateUiCaseSnapshot,
  runPackagedRuntimeSmoke,
} = require('../src/packaged-runtime-smoke');

const checks = [];

function check(name, actual, expected = true) {
  const passed = actual === expected;
  checks.push({ name, passed, actual, expected });
  if (!passed) {
    throw new Error(`${name}: actual=${JSON.stringify(actual)} expected=${JSON.stringify(expected)}`);
  }
}

function checkThrows(name, callback) {
  let thrown = false;
  try {
    callback();
  } catch (_error) {
    thrown = true;
  }
  check(name, thrown, true);
}

check('search schema', RESPONSE_SCHEMA_VERSION, 'kdrg-runtime-search-response-v1');
check('relation schema', RELATION_RESPONSE_SCHEMA_VERSION, 'kdrg-runtime-relation-response-v1');
check('UI smoke schema', UI_SMOKE_SCHEMA_VERSION, 'kdrg-packaged-ui-smoke-v1');
check('fixture count', UI_FIXTURES.length, 6);
check('required detail label count', REQUIRED_DETAIL_LABELS.length, 3);
check('forbidden detail label count', FORBIDDEN_DETAIL_LABELS.length, 2);
check('B013 TABLE', UI_FIXTURES[0].expected_table_ids.join('|'), 'LT_B018_002');
check('B014 TABLE', UI_FIXTURES[1].expected_table_ids.join('|'), 'LT_B018_003');
check(
  'B018 TABLE',
  UI_FIXTURES[2].expected_table_ids.join('|'),
  'LT_B018_001|LT_B018_004|LT_B018_005',
);
check(
  'B018 forbidden TABLE',
  UI_FIXTURES[2].forbidden_table_ids.join('|'),
  'LT_B018_002|LT_B018_003',
);
check('B022 no TABLE', UI_FIXTURES[3].expected_table_ids.length, 0);
check('L033 no TABLE', UI_FIXTURES[4].expected_table_ids.length, 0);
check('9610 no TABLE', UI_FIXTURES[5].expected_table_ids.length, 0);
check('ADRG count', EXPECTED_COUNTS.adrg, 1132);
check('TABLE count', EXPECTED_COUNTS.tables, 1308);
check('CODE count', EXPECTED_COUNTS.codes, 16571);

check('smoke env', shouldRunPackagedSmoke([], { KDRG_ELECTRON_SMOKE_TEST: '1' }), true);
check('smoke arg', shouldRunPackagedSmoke(['--kdrg-smoke-test'], {}), true);
check('smoke off', shouldRunPackagedSmoke([], {}), false);

const search = {
  schema_version: RESPONSE_SCHEMA_VERSION,
  total_count: 1,
  results: [{ entity_id: 'E011' }],
};
check('search response valid', validateSearchResponse(search).length, 1);
checkThrows('search schema invalid', () => validateSearchResponse({ ...search, schema_version: 'x' }));
checkThrows('search results invalid', () => validateSearchResponse({ ...search, results: null }));

const relation = {
  schema_version: RELATION_RESPONSE_SCHEMA_VERSION,
  conditions: [{}, {}],
  total_count: 1,
  results: [{
    entity_type: 'ADRG',
    entity_id: 'E011',
    relation_level: 'strict',
    code_matches: [],
    condition_groups: [{
      exclude_table_ids: [],
      exclude_tables: [],
    }],
  }],
};
check('relation response valid', validateRelationResponse(relation, 'E011').length, 1);
checkThrows('relation fixture missing', () => validateRelationResponse(relation, 'B013'));

const detail = {
  schema_version: RESPONSE_SCHEMA_VERSION,
  entity_type: 'ADRG',
  entity_id: 'E011',
  detail: {},
};
check('detail response valid', validateDetailResponse(detail).entity_id, 'E011');
checkThrows('detail entity invalid', () => validateDetailResponse({ ...detail, entity_id: 'X' }));

const bootstrap = { counts: { ...EXPECTED_COUNTS } };
check('bootstrap valid', validateBootstrapCounts(bootstrap).adrg, 1132);
checkThrows(
  'bootstrap count invalid',
  () => validateBootstrapCounts({ counts: { ...EXPECTED_COUNTS, adrg: 1 } }),
);

const legacyConsole = normalizeConsoleMessage([3, 'boom', 12, 'app.js']);
check('legacy console level', legacyConsole.level, 3);
check('legacy console message', legacyConsole.message, 'boom');
const objectConsole = normalizeConsoleMessage([{
  level: 3,
  message: 'error',
  lineNumber: 7,
  sourceId: 'renderer.js',
}]);
check('object console level', objectConsole.level, 3);
check('object console source', objectConsole.source_id, 'renderer.js');

function validSnapshot(fixture) {
  const codeCounts = Object.fromEntries(
    fixture.expected_table_ids.map((tableId) => [tableId, 3]),
  );
  return {
    selected_adrg: fixture.adrg,
    detail_text: [
      fixture.adrg,
      ...REQUIRED_DETAIL_LABELS,
      ...fixture.required_table_labels,
    ].join(' '),
    table_ids: [...fixture.expected_table_ids],
    table_labels: [...fixture.required_table_labels],
    loaded_table_count: fixture.expected_table_ids.length,
    code_row_counts: codeCounts,
    code_row_total: fixture.expected_table_ids.length ? 3 : 0,
    error_messages: [],
  };
}

for (const fixture of UI_FIXTURES) {
  const result = validateUiCaseSnapshot(validSnapshot(fixture), fixture);
  check(`${fixture.adrg} valid snapshot`, result.passed, true);
  check(`${fixture.adrg} failed checks zero`, result.failed_checks.length, 0);
}

const badB018 = validSnapshot(UI_FIXTURES[2]);
badB018.table_ids.push('LT_B018_002');
check(
  'B018 forbidden table rejected',
  validateUiCaseSnapshot(badB018, UI_FIXTURES[2]).passed,
  false,
);

const oldLabel = validSnapshot(UI_FIXTURES[0]);
oldLabel.detail_text += ' 기본 분류 TABLE';
check(
  'obsolete label rejected',
  validateUiCaseSnapshot(oldLabel, UI_FIXTURES[0]).passed,
  false,
);

const internalLabel = validSnapshot(UI_FIXTURES[0]);
internalLabel.table_labels = ['LT_B018_002'];
check(
  'internal label rejected',
  validateUiCaseSnapshot(internalLabel, UI_FIXTURES[0]).passed,
  false,
);

const unloaded = validSnapshot(UI_FIXTURES[0]);
unloaded.loaded_table_count = 0;
check(
  'unloaded table rejected',
  validateUiCaseSnapshot(unloaded, UI_FIXTURES[0]).passed,
  false,
);

const noRows = validSnapshot(UI_FIXTURES[0]);
noRows.code_row_total = 0;
check(
  'no code rows rejected',
  validateUiCaseSnapshot(noRows, UI_FIXTURES[0]).passed,
  false,
);


function checkRejects(name, callback) {
  return Promise.resolve()
    .then(callback)
    .then(
      () => check(name, false, true),
      () => check(name, true, true),
    );
}

function mockSnapshotForFixture(fixture) {
  const codeCounts = Object.fromEntries(
    fixture.expected_table_ids.map((tableId) => [tableId, 3]),
  );
  return {
    selected_adrg: fixture.adrg,
    result_count_text: '1건',
    result_caption: fixture.adrg,
    detail_caption: fixture.adrg,
    detail_text: [
      fixture.adrg,
      ...REQUIRED_DETAIL_LABELS,
      ...fixture.required_table_labels,
    ].join(' '),
    table_ids: [...fixture.expected_table_ids],
    table_labels: [...fixture.required_table_labels],
    inline_table_count: fixture.expected_table_ids.length,
    loaded_table_count: fixture.expected_table_ids.length,
    code_row_counts: codeCounts,
    code_row_total: fixture.expected_table_ids.length ? 3 : 0,
    error_messages: [],
  };
}

function parseFixtureFromScript(script) {
  const marker = 'const fixture = ';
  const start = script.indexOf(marker);
  if (start < 0) return null;
  const jsonStart = start + marker.length;
  const end = script.indexOf(';\n      const sleep', jsonStart);
  if (end < 0) return null;
  return JSON.parse(script.slice(jsonStart, end));
}

function createMockImage(seed = 1) {
  const bitmap = Buffer.alloc(1600 * 980 * 4);
  for (let offset = 0; offset < bitmap.length; offset += 4) {
    const index = offset / 4;
    bitmap.writeUInt32LE((index + seed * 1009) % 100000, offset);
  }
  const png = Buffer.alloc(15000, seed);
  return {
    getSize: () => ({ width: 1600, height: 980 }),
    toBitmap: () => bitmap,
    toPNG: () => png,
  };
}

class MockWebContents extends EventEmitter {
  constructor() {
    super();
    this.captureSeed = 1;
  }

  setWindowOpenHandler() {}

  async executeJavaScript(script) {
    const fixture = parseFixtureFromScript(script);
    if (fixture) {
      this.captureSeed = UI_FIXTURES.findIndex(
        (item) => item.adrg === fixture.adrg,
      ) + 1;
      return mockSnapshotForFixture(fixture);
    }
    return true;
  }

  async capturePage() {
    return createMockImage(this.captureSeed);
  }
}

class MockBrowserWindow {
  constructor() {
    this.webContents = new MockWebContents();
    this.destroyed = false;
  }

  async loadFile() {
    setImmediate(() => this.webContents.emit('did-finish-load'));
  }

  isDestroyed() {
    return this.destroyed;
  }

  destroy() {
    this.destroyed = true;
  }
}

function createRuntimeService({ relationFailure = false } = {}) {
  const table = { codes: ['A001', 'A002'] };
  return {
    conditionGroupsByAdrg: new Map([
      ['E011', [{
        include_table_ids: ['LT_TEST_001'],
        exclude_table_ids: [],
      }]],
    ]),
    recordMaps: {
      TABLE: new Map([['LT_TEST_001', table]]),
    },
    status: () => ({ ready: true }),
    search: () => ({
      schema_version: RESPONSE_SCHEMA_VERSION,
      total_count: 1,
      results: [{ entity_id: 'E011' }],
    }),
    relationSearch: () => {
      if (relationFailure) {
        throw new Error('relation fixture failure');
      }
      return {
        schema_version: RELATION_RESPONSE_SCHEMA_VERSION,
        conditions: [{ code: 'A001' }, { code: 'A002' }],
        total_count: 1,
        results: [{
          entity_type: 'ADRG',
          entity_id: 'E011',
          relation_level: 'strict',
          code_matches: [],
          condition_groups: [{
            exclude_table_ids: [],
            exclude_tables: [],
          }],
        }],
      };
    },
    getDetail: () => ({
      schema_version: RESPONSE_SCHEMA_VERSION,
      entity_type: 'ADRG',
      entity_id: 'E011',
      detail: {},
    }),
  };
}

function makeRuntimeFixture(tempRoot, options = {}) {
  const dataFiles = {
    integrated: path.join(tempRoot, 'integrated.json'),
    semanticProfile: path.join(tempRoot, 'semantic.json'),
    displayContract: path.join(tempRoot, 'display.json'),
  };
  for (const filePath of Object.values(dataFiles)) {
    fs.writeFileSync(filePath, '{}\n', 'utf8');
  }

  const service = createRuntimeService(options);
  function MockKdrgSearchService() {
    return service;
  }

  return {
    app: {
      isPackaged: true,
      getVersion: () => '0.5.1',
    },
    BrowserWindow: MockBrowserWindow,
    resolveDataFiles: () => dataFiles,
    buildBootstrapSnapshot: () => ({ counts: { ...EXPECTED_COUNTS } }),
    KdrgSearchService: MockKdrgSearchService,
    rendererPath: path.join(tempRoot, 'index.html'),
    preloadPath: path.join(tempRoot, 'preload.js'),
  };
}

async function runLegacyAndPackagedFixtures() {
  const obsoleteItems = {
    schema_version: RESPONSE_SCHEMA_VERSION,
    total_count: 0,
    items: [],
  };
  let obsoleteMessage = '';
  try {
    validateSearchResponse(obsoleteItems);
  } catch (error) {
    obsoleteMessage = error.message;
  }
  check(
    'obsolete items field detected',
    obsoleteMessage.includes('obsolete items field detected'),
    true,
  );

  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'kdrg-stage51d-contract-'));
  const previousReport = process.env.KDRG_ELECTRON_SMOKE_REPORT;
  const previousScreenshots = process.env.KDRG_ELECTRON_SMOKE_SCREENSHOT_DIR;

  try {
    const reportPath = path.join(tempRoot, 'runtime-report.json');
    const screenshotPath = path.join(tempRoot, 'screenshots');
    process.env.KDRG_ELECTRON_SMOKE_REPORT = reportPath;
    process.env.KDRG_ELECTRON_SMOKE_SCREENSHOT_DIR = screenshotPath;

    const fixture = makeRuntimeFixture(tempRoot);
    const runtimeReport = await runPackagedRuntimeSmoke(fixture);
    check('runPackagedRuntimeSmoke(fixture)', runtimeReport.status, 'PASS');
    check(
      'runtime relation schema',
      runtimeReport.relation_fixture.response_schema_version,
      RELATION_RESPONSE_SCHEMA_VERSION,
    );
    check('runtime UI case count', runtimeReport.ui_validation.case_count, 6);
    check('runtime UI status', runtimeReport.ui_validation.status, 'PASS');

    const failureReportPath = path.join(tempRoot, 'relation-failure-report.json');
    process.env.KDRG_ELECTRON_SMOKE_REPORT = failureReportPath;
    await checkRejects(
      'relation runtime rejection',
      () => runPackagedRuntimeSmoke(
        makeRuntimeFixture(tempRoot, { relationFailure: true }),
      ),
    );
    const relationFailureReport = JSON.parse(
      fs.readFileSync(failureReportPath, 'utf8'),
    );
    check(
      'relation report failed step',
      relationFailureReport.failed_step,
      'relation_contract_validation',
    );

    const legacyReportPath = path.join(tempRoot, 'legacy-failure-report.json');
    process.env.KDRG_ELECTRON_SMOKE_REPORT = legacyReportPath;
    const legacyFixture = makeRuntimeFixture(tempRoot);
    legacyFixture.buildBootstrapSnapshot = () => null;
    await checkRejects(
      'legacy runtime rejection',
      () => runPackagedRuntimeSmoke(legacyFixture),
    );
    const legacyReport = JSON.parse(
      fs.readFileSync(legacyReportPath, 'utf8'),
    );
    check(
      'legacy report no raw TypeError',
      String(legacyReport.error?.message || '').includes('TypeError'),
      false,
    );
    check(
      'legacy report failed step',
      legacyReport.failed_step,
      'bootstrap_count_validation',
    );
  } finally {
    if (previousReport === undefined) {
      delete process.env.KDRG_ELECTRON_SMOKE_REPORT;
    } else {
      process.env.KDRG_ELECTRON_SMOKE_REPORT = previousReport;
    }
    if (previousScreenshots === undefined) {
      delete process.env.KDRG_ELECTRON_SMOKE_SCREENSHOT_DIR;
    } else {
      process.env.KDRG_ELECTRON_SMOKE_SCREENSHOT_DIR = previousScreenshots;
    }
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
}

function finalize() {
  const passCount = checks.filter((item) => item.passed).length;
  const failCount = checks.length - passCount;

  console.log('validator=2026-08-04_KDRG_V47_STAGE51D_WINDOWS_PACKAGED_UI_SMOKE_CONTRACT_V2');
  if (failCount) {
    console.log(`[FAIL] Electron packaged runtime smoke 계약검증: ${passCount} PASS / ${failCount} FAIL`);
    process.exitCode = 1;
  } else {
    console.log(`[PASS] Electron packaged runtime smoke 계약검증: ${passCount} PASS / 0 FAIL`);
  }
}

runLegacyAndPackagedFixtures()
  .then(finalize)
  .catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
