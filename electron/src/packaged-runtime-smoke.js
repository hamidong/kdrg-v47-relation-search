'use strict';

const fs = require('node:fs');
const path = require('node:path');

const RESPONSE_SCHEMA_VERSION = 'kdrg-runtime-search-response-v1';
const RELATION_RESPONSE_SCHEMA_VERSION = 'kdrg-runtime-relation-response-v1';
const EXPECTED_COUNTS = Object.freeze({
  adrg: 1132,
  aadrg: 1233,
  rdrg: 2699,
  tables: 1308,
  codes: 16571,
  conditionAst: 390,
  conditionTableOccurrences: 939,
});

function shouldRunPackagedSmoke(argv = process.argv, env = process.env) {
  return env.KDRG_ELECTRON_SMOKE_TEST === '1'
    || argv.includes('--kdrg-smoke-test');
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function requirePlainObject(value, label) {
  if (!isPlainObject(value)) {
    throw new Error(`${label} contract mismatch: expected object`);
  }
  return value;
}

function validateSearchResponse(search) {
  requirePlainObject(search, 'packaged search response');
  if (search.schema_version !== RESPONSE_SCHEMA_VERSION) {
    throw new Error(
      `packaged search response contract mismatch: schema_version=${search.schema_version}, expected=${RESPONSE_SCHEMA_VERSION}`,
    );
  }
  if (!Array.isArray(search.results)) {
    const legacyItems = Array.isArray(search.items);
    throw new Error(
      `packaged search response contract mismatch: results must be an array${legacyItems ? '; obsolete items field detected' : ''}`,
    );
  }
  if (!Number.isInteger(search.total_count) || search.total_count < search.results.length) {
    throw new Error(
      `packaged search response contract mismatch: total_count=${search.total_count}, results=${search.results.length}`,
    );
  }
  for (const [index, item] of search.results.entries()) {
    if (!isPlainObject(item) || typeof item.entity_id !== 'string' || !item.entity_id) {
      throw new Error(
        `packaged search response contract mismatch: invalid results[${index}]`,
      );
    }
  }
  return search.results;
}


function validateRelationResponse(response, expectedAdrg = null) {
  requirePlainObject(response, 'packaged relation response');
  if (response.schema_version !== RELATION_RESPONSE_SCHEMA_VERSION) {
    throw new Error(
      `packaged relation response contract mismatch: schema_version=${response.schema_version}, expected=${RELATION_RESPONSE_SCHEMA_VERSION}`,
    );
  }
  if (!Array.isArray(response.conditions) || response.conditions.length < 2) {
    throw new Error('packaged relation response contract mismatch: conditions must contain at least 2 rows');
  }
  if (!Array.isArray(response.results)) {
    throw new Error('packaged relation response contract mismatch: results must be an array');
  }
  if (!Number.isInteger(response.total_count) || response.total_count !== response.results.length) {
    throw new Error(
      `packaged relation response contract mismatch: total_count=${response.total_count}, results=${response.results.length}`,
    );
  }
  for (const [index, item] of response.results.entries()) {
    if (!isPlainObject(item)
      || item.entity_type !== 'ADRG'
      || typeof item.entity_id !== 'string'
      || !['strict', 'split', 'partial'].includes(item.relation_level)
      || !Array.isArray(item.code_matches)
      || !Array.isArray(item.condition_groups)
      || item.condition_groups.some((group) => !Array.isArray(group.exclude_table_ids) || !Array.isArray(group.exclude_tables))) {
      throw new Error(`packaged relation response contract mismatch: invalid results[${index}]`);
    }
  }
  if (expectedAdrg && !response.results.some((item) => item.entity_id === expectedAdrg)) {
    throw new Error(`packaged relation fixture missing: ADRG ${expectedAdrg}`);
  }
  return response.results;
}

function findRelationSmokeFixture(service) {
  const conditionGroups = service?.conditionGroupsByAdrg;
  const tableMap = service?.recordMaps?.TABLE;
  if (!(conditionGroups instanceof Map) || !(tableMap instanceof Map)) {
    throw new Error('relation smoke discovery contract mismatch: condition/table indexes unavailable');
  }
  for (const [adrg, groups] of conditionGroups.entries()) {
    const exclusionIds = new Set((groups ?? []).flatMap((group) => group.exclude_table_ids ?? []));
    for (const group of groups ?? []) {
      const codes = [];
      const seen = new Set();
      for (const tableId of group.include_table_ids ?? []) {
        if (exclusionIds.has(tableId)) continue;
        const table = tableMap.get(String(tableId));
        for (const code of table?.codes ?? []) {
          const normalized = String(code ?? '').replace(/[^0-9A-Za-z]/g, '').toUpperCase();
          if (!normalized || seen.has(normalized)) continue;
          seen.add(normalized);
          codes.push(String(code));
          if (codes.length >= 2) break;
        }
        if (codes.length >= 2) break;
      }
      if (codes.length < 2) continue;
      const conditions = codes.map((code) => ({ code, codeType: 'AUTO' }));
      const response = service.relationSearch(conditions, 'AND', {});
      if (response.results.some((item) => item.entity_id === adrg)) {
        return { adrg, codes, response };
      }
    }
  }
  throw new Error('packaged relation smoke fixture discovery failed');
}

function validateDetailResponse(detail) {
  requirePlainObject(detail, 'packaged detail response');
  if (detail.schema_version !== RESPONSE_SCHEMA_VERSION) {
    throw new Error(
      `packaged detail response contract mismatch: schema_version=${detail.schema_version}, expected=${RESPONSE_SCHEMA_VERSION}`,
    );
  }
  if (detail.entity_type !== 'ADRG' || detail.entity_id !== 'E011') {
    throw new Error(
      `E011 detail fixture mismatch: entity_type=${detail.entity_type}, entity_id=${detail.entity_id}`,
    );
  }
  requirePlainObject(detail.detail, 'packaged detail payload');
  return detail;
}

function validateBootstrapCounts(bootstrap) {
  requirePlainObject(bootstrap, 'bootstrap snapshot');
  requirePlainObject(bootstrap.counts, 'bootstrap counts');
  for (const [key, expected] of Object.entries(EXPECTED_COUNTS)) {
    const actual = bootstrap.counts[key];
    if (actual !== expected) {
      throw new Error(
        `bootstrap count mismatch: ${key}=${actual}, expected=${expected}`,
      );
    }
  }
  return bootstrap.counts;
}

function waitForRendererLoad(window, timeoutMs = 30000) {
  return new Promise((resolve, reject) => {
    let settled = false;
    const webContents = window?.webContents;
    if (!webContents || typeof webContents.once !== 'function') {
      reject(new Error('renderer contract mismatch: webContents.once is unavailable'));
      return;
    }

    const cleanup = () => {
      clearTimeout(timer);
      if (typeof webContents.removeListener === 'function') {
        webContents.removeListener('did-finish-load', onFinish);
        webContents.removeListener('did-fail-load', onFail);
        webContents.removeListener('render-process-gone', onGone);
      }
    };
    const finish = (callback) => {
      if (settled) return;
      settled = true;
      cleanup();
      callback();
    };
    const onFinish = () => finish(resolve);
    const onFail = (_event, errorCode, errorDescription, validatedURL) => {
      finish(() => reject(new Error(
        `renderer load failed: code=${errorCode}, description=${errorDescription}, url=${validatedURL}`,
      )));
    };
    const onGone = (_event, details) => {
      finish(() => reject(new Error(
        `renderer process gone: reason=${details?.reason || 'unknown'}, exitCode=${details?.exitCode ?? 'unknown'}`,
      )));
    };
    const timer = setTimeout(() => {
      finish(() => reject(new Error(`renderer load timeout: ${timeoutMs}ms`)));
    }, timeoutMs);

    webContents.once('did-finish-load', onFinish);
    webContents.once('did-fail-load', onFail);
    webContents.once('render-process-gone', onGone);
  });
}

function writeSmokeReport(reportPath, payload) {
  if (!reportPath) return;
  const resolved = path.resolve(reportPath);
  fs.mkdirSync(path.dirname(resolved), { recursive: true });
  fs.writeFileSync(resolved, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
}

function runtimeMetadata(app) {
  return {
    app_is_packaged: Boolean(app?.isPackaged),
    app_version: typeof app?.getVersion === 'function' ? app.getVersion() : null,
    electron_version: process.versions.electron || null,
    node_version: process.versions.node || null,
    platform: process.platform,
    arch: process.arch,
    resources_path: process.resourcesPath || null,
  };
}

async function runPackagedRuntimeSmoke({
  app,
  BrowserWindow,
  resolveDataFiles,
  buildBootstrapSnapshot,
  KdrgSearchService,
  rendererPath,
  preloadPath,
}) {
  const startedAt = new Date().toISOString();
  const reportPath = process.env.KDRG_ELECTRON_SMOKE_REPORT || '';
  const completedSteps = [];
  let smokeWindow = null;
  let currentStep = 'initialize';

  const markStep = (step) => {
    completedSteps.push(step);
  };

  try {
    currentStep = 'dependency_validation';
    requirePlainObject(app, 'Electron app');
    if (typeof resolveDataFiles !== 'function') {
      throw new Error('smoke dependency contract mismatch: resolveDataFiles is unavailable');
    }
    if (typeof buildBootstrapSnapshot !== 'function') {
      throw new Error('smoke dependency contract mismatch: buildBootstrapSnapshot is unavailable');
    }
    if (typeof KdrgSearchService !== 'function') {
      throw new Error('smoke dependency contract mismatch: KdrgSearchService is unavailable');
    }
    if (typeof BrowserWindow !== 'function') {
      throw new Error('smoke dependency contract mismatch: BrowserWindow is unavailable');
    }
    markStep('dependencies_verified');

    currentStep = 'data_path_resolution';
    const dataFiles = requirePlainObject(resolveDataFiles({
      isPackaged: app.isPackaged,
      resourcesPath: process.resourcesPath,
    }), 'packaged data files');
    markStep('data_paths_resolved');

    currentStep = 'data_file_validation';
    const requiredDataKeys = ['integrated', 'semanticProfile', 'displayContract'];
    for (const key of requiredDataKeys) {
      const filePath = dataFiles[key];
      if (typeof filePath !== 'string' || !filePath) {
        throw new Error(`packaged data path missing: key=${key}`);
      }
      let stat;
      try {
        stat = fs.statSync(filePath);
      } catch (error) {
        throw new Error(`packaged data file inaccessible: key=${key}, path=${filePath}, reason=${error.message}`);
      }
      if (!stat.isFile()) {
        throw new Error(`packaged data file missing: key=${key}, path=${filePath}`);
      }
    }
    markStep('data_files_verified');

    currentStep = 'bootstrap_count_validation';
    const bootstrap = buildBootstrapSnapshot(dataFiles);
    const counts = validateBootstrapCounts(bootstrap);
    markStep('bootstrap_counts_verified');

    currentStep = 'search_service_initialization';
    const service = new KdrgSearchService(dataFiles.integrated);
    if (!service || typeof service.status !== 'function'
      || typeof service.search !== 'function'
      || typeof service.relationSearch !== 'function'
      || typeof service.getDetail !== 'function') {
      throw new Error('search service contract mismatch: required methods are unavailable');
    }
    const status = requirePlainObject(service.status(), 'search service status');
    if (status.ready !== true) {
      throw new Error(`search service is not ready: ready=${status.ready}`);
    }
    markStep('search_service_ready');

    currentStep = 'search_contract_validation';
    const search = service.search('E011', 'ALL', { limit: 10, offset: 0 });
    const searchResults = validateSearchResponse(search);
    markStep('search_contract_verified');
    currentStep = 'search_fixture_validation';
    const fixture = searchResults.find((item) => item.entity_id === 'E011');
    if (!fixture) {
      throw new Error('E011 search fixture missing');
    }
    markStep('search_fixture_verified');

    currentStep = 'detail_contract_validation';
    const detail = validateDetailResponse(service.getDetail('ADRG', 'E011'));
    markStep('detail_contract_verified');

    currentStep = 'relation_contract_validation';
    const relationFixture = findRelationSmokeFixture(service);
    const relationResults = validateRelationResponse(relationFixture.response, relationFixture.adrg);
    markStep('relation_contract_verified');

    currentStep = 'browser_window_creation';
    smokeWindow = new BrowserWindow({
      width: 1200,
      height: 760,
      show: false,
      webPreferences: {
        preload: preloadPath,
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true,
        devTools: false,
        spellcheck: false,
      },
    });
    if (!smokeWindow?.webContents || typeof smokeWindow.loadFile !== 'function') {
      throw new Error('BrowserWindow contract mismatch: loadFile/webContents unavailable');
    }
    smokeWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
    smokeWindow.webContents.on('will-navigate', (event) => event.preventDefault());
    markStep('browser_window_created');

    currentStep = 'renderer_load';
    const rendererLoaded = waitForRendererLoad(smokeWindow);
    await smokeWindow.loadFile(rendererPath);
    await rendererLoaded;
    markStep('renderer_loaded');

    const report = {
      status: 'PASS',
      started_at: startedAt,
      finished_at: new Date().toISOString(),
      ...runtimeMetadata(app),
      completed_steps: [...completedSteps],
      data_files: dataFiles,
      counts,
      search_fixture: {
        query: 'E011',
        response_schema_version: search.schema_version,
        result_count: searchResults.length,
        total_count: search.total_count,
        found: true,
        result_entity_id: fixture.entity_id,
        detail_entity_id: detail.entity_id,
      },
      relation_fixture: {
        codes: relationFixture.codes,
        expected_adrg: relationFixture.adrg,
        response_schema_version: relationFixture.response.schema_version,
        result_count: relationResults.length,
        found: true,
      },
      renderer_loaded: true,
    };
    writeSmokeReport(reportPath, report);
    return report;
  } catch (error) {
    const report = {
      status: 'FAIL',
      started_at: startedAt,
      finished_at: new Date().toISOString(),
      ...runtimeMetadata(app),
      failed_step: currentStep,
      completed_steps: [...completedSteps],
      error: {
        name: error?.name || 'Error',
        message: error?.message || String(error),
        stack: error?.stack || '',
      },
    };
    writeSmokeReport(reportPath, report);
    throw error;
  } finally {
    if (smokeWindow && typeof smokeWindow.isDestroyed === 'function'
      && !smokeWindow.isDestroyed()) {
      smokeWindow.destroy();
    }
  }
}

module.exports = Object.freeze({
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
});
