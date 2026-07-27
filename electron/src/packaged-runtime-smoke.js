'use strict';

const fs = require('node:fs');
const path = require('node:path');

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

function waitForRendererLoad(window, timeoutMs = 30000) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(new Error(`renderer load timeout: ${timeoutMs}ms`));
    }, timeoutMs);

    window.webContents.once('did-finish-load', () => {
      clearTimeout(timer);
      resolve();
    });
    window.webContents.once(
      'did-fail-load',
      (_event, errorCode, errorDescription, validatedURL) => {
        clearTimeout(timer);
        reject(
          new Error(
            `renderer load failed: code=${errorCode}, description=${errorDescription}, url=${validatedURL}`,
          ),
        );
      },
    );
  });
}

function writeSmokeReport(reportPath, payload) {
  if (!reportPath) return;
  const resolved = path.resolve(reportPath);
  fs.mkdirSync(path.dirname(resolved), { recursive: true });
  fs.writeFileSync(resolved, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
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
  let smokeWindow = null;

  try {
    const dataFiles = resolveDataFiles({
      isPackaged: app.isPackaged,
      resourcesPath: process.resourcesPath,
    });

    for (const filePath of Object.values(dataFiles)) {
      if (!fs.statSync(filePath).isFile()) {
        throw new Error(`packaged data file missing: ${filePath}`);
      }
    }

    const bootstrap = buildBootstrapSnapshot(dataFiles);
    const service = new KdrgSearchService(dataFiles.integrated);
    const status = service.status();
    const search = service.search('E011', 'ALL', { limit: 10, offset: 0 });
    const detail = service.getDetail('ADRG', 'E011');

    for (const [key, expected] of Object.entries(EXPECTED_COUNTS)) {
      if (bootstrap.counts[key] !== expected) {
        throw new Error(
          `bootstrap count mismatch: ${key}=${bootstrap.counts[key]}, expected=${expected}`,
        );
      }
    }
    if (!status.ready) throw new Error('search service is not ready');
    if (!search.items.some((item) => item.entity_id === 'E011')) {
      throw new Error('E011 search fixture missing');
    }
    if (detail.entity_id !== 'E011') {
      throw new Error(`E011 detail fixture mismatch: ${detail.entity_id}`);
    }

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
    smokeWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
    smokeWindow.webContents.on('will-navigate', (event) => event.preventDefault());

    const rendererLoaded = waitForRendererLoad(smokeWindow);
    await smokeWindow.loadFile(rendererPath);
    await rendererLoaded;

    const report = {
      status: 'PASS',
      started_at: startedAt,
      finished_at: new Date().toISOString(),
      app_is_packaged: app.isPackaged,
      app_version: app.getVersion(),
      electron_version: process.versions.electron,
      node_version: process.versions.node,
      platform: process.platform,
      arch: process.arch,
      resources_path: process.resourcesPath,
      data_files: dataFiles,
      counts: bootstrap.counts,
      search_fixture: {
        query: 'E011',
        result_count: search.items.length,
        found: true,
        detail_entity_id: detail.entity_id,
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
      app_is_packaged: app.isPackaged,
      app_version: app.getVersion(),
      electron_version: process.versions.electron,
      node_version: process.versions.node,
      platform: process.platform,
      arch: process.arch,
      resources_path: process.resourcesPath,
      error: {
        name: error?.name || 'Error',
        message: error?.message || String(error),
        stack: error?.stack || '',
      },
    };
    writeSmokeReport(reportPath, report);
    throw error;
  } finally {
    if (smokeWindow && !smokeWindow.isDestroyed()) {
      smokeWindow.destroy();
    }
  }
}

module.exports = Object.freeze({
  EXPECTED_COUNTS,
  shouldRunPackagedSmoke,
  runPackagedRuntimeSmoke,
});
