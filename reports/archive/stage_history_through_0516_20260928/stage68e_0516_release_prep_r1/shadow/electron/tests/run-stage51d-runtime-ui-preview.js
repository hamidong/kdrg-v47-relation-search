#!/usr/bin/env node
'use strict';

const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

const {
  app,
  BrowserWindow,
  ipcMain,
  nativeImage,
} = require('electron');
const { buildBootstrapSnapshot } = require('../src/bootstrap-data');
const { resolveDataFiles } = require('../src/data-paths');
const { KdrgSearchService } = require('../src/kdrg-search-service');
const {
  normalizeSearchRequest,
  normalizeRelationRequest,
  normalizeDetailRequest,
} = require('../src/search-result-contract');

const VERSION = '2026-08-04_KDRG_V47_STAGE51D_ELECTRON_RUNTIME_UI_PREVIEW_HARNESS_V1';
const ELECTRON_ROOT = path.resolve(__dirname, '..');
const WORKSPACE_ROOT = path.resolve(ELECTRON_ROOT, '..');
const REPORT_DIR = path.resolve(
  process.env.KDRG_STAGE51D_REPORT_DIR
    || path.join(WORKSPACE_ROOT, 'reports', 'electron_stage51d_runtime_ui_preview', 'direct'),
);
const RESULT_JSON = path.join(REPORT_DIR, 'preview_result.json');
const INDEX_HTML = path.join(REPORT_DIR, 'index.html');
const MODE = process.env.KDRG_STAGE51D_MODE || 'direct';
const HEADLESS = process.env.KDRG_STAGE51D_HEADLESS === '1';

const CASES = Object.freeze([
  Object.freeze({
    adrg: 'B013',
    expectedText: ['시술명 table2'],
    expectedTables: ['LT_B018_002'],
    expectedLoadedTables: 1,
    expectedStatus: '조건 TABLE 연결 완료',
  }),
  Object.freeze({
    adrg: 'B014',
    expectedText: ['시술명 table3'],
    expectedTables: ['LT_B018_003'],
    expectedLoadedTables: 1,
    expectedStatus: '조건 TABLE 연결 완료',
  }),
  Object.freeze({
    adrg: 'B018',
    expectedText: [
      '주진단명 또는 기타진단명 table1',
      '시술명 table4',
      '시술명 table5',
    ],
    expectedTables: ['LT_B018_001', 'LT_B018_004', 'LT_B018_005'],
    forbiddenTables: ['LT_B018_002', 'LT_B018_003'],
    expectedLoadedTables: 3,
    expectedStatus: '조건 TABLE 연결 완료',
  }),
  Object.freeze({
    adrg: 'B022',
    expectedText: ['시술명 table2', 'TABLE 연결 검토 필요'],
    expectedTables: [],
    expectedLoadedTables: 0,
    expectedStatus: 'TABLE 연결 검토 필요',
  }),
  Object.freeze({
    adrg: 'L033',
    expectedText: ['시술명 table1', 'TABLE 연결 검토 필요'],
    expectedTables: [],
    expectedLoadedTables: 0,
    expectedStatus: 'TABLE 연결 검토 필요',
  }),
  Object.freeze({
    adrg: '9610',
    expectedText: ['명시적 분류 조건', '명시적 조건 없음'],
    expectedTables: [],
    expectedLoadedTables: 0,
    expectedStatus: '명시적 조건 없음',
  }),
]);

if (HEADLESS) {
  app.commandLine.appendSwitch('headless', 'new');
  app.commandLine.appendSwitch('ozone-platform', 'headless');
}
app.commandLine.appendSwitch('disable-gpu');
app.commandLine.appendSwitch('disable-dev-shm-usage');
app.commandLine.appendSwitch('force-device-scale-factor', '1');

fs.mkdirSync(REPORT_DIR, { recursive: true });

const consoleErrors = [];
const rendererGone = [];
const loadFailures = [];
let bootstrapSnapshot = null;
let searchService = null;
let mainWindow = null;

function sha256(buffer) {
  return crypto.createHash('sha256').update(buffer).digest('hex');
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function dataFiles() {
  return resolveDataFiles({
    isPackaged: false,
    resourcesPath: process.resourcesPath,
    moduleDirectory: path.join(ELECTRON_ROOT, 'src'),
  });
}

function bootstrap() {
  if (!bootstrapSnapshot) {
    bootstrapSnapshot = buildBootstrapSnapshot(dataFiles());
  }
  return bootstrapSnapshot;
}

function service() {
  if (!searchService) {
    searchService = new KdrgSearchService(dataFiles().integrated);
  }
  return searchService;
}

function registerIpc() {
  const channels = {
    bootstrap: 'kdrg:get-bootstrap-snapshot',
    searchStatus: 'kdrg:get-search-status',
    search: 'kdrg:search',
    relationSearch: 'kdrg:relation-search',
    detail: 'kdrg:get-detail',
  };
  for (const channel of Object.values(channels)) {
    ipcMain.removeHandler(channel);
  }

  ipcMain.handle(channels.bootstrap, async () => bootstrap());
  ipcMain.handle(channels.searchStatus, async () => service().status());
  ipcMain.handle(channels.search, async (_event, payload) => {
    const request = normalizeSearchRequest(payload);
    return service().search(request.query, request.entityType, {
      limit: request.limit,
      offset: request.offset,
      mdc: request.mdc,
      classification: request.classification,
    });
  });
  ipcMain.handle(channels.relationSearch, async (_event, payload) => {
    const request = normalizeRelationRequest(payload);
    return service().relationSearch(request.conditions, request.operator, {
      mdc: request.mdc,
      classification: request.classification,
    });
  });
  ipcMain.handle(channels.detail, async (_event, payload) => {
    const request = normalizeDetailRequest(payload);
    return service().getDetail(request.entityType, request.entityId);
  });
}

async function execute(script) {
  return mainWindow.webContents.executeJavaScript(script, true);
}

async function waitFor(script, label, timeoutMs = 15000, intervalMs = 100) {
  const started = Date.now();
  let lastValue = null;
  while (Date.now() - started < timeoutMs) {
    try {
      lastValue = await execute(script);
      if (lastValue) return lastValue;
    } catch (_error) {
      lastValue = null;
    }
    await delay(intervalMs);
  }
  throw new Error(`대기시간 초과: ${label} | last=${JSON.stringify(lastValue)}`);
}

function createWindow() {
  const window = new BrowserWindow({
    width: 1600,
    height: 980,
    minWidth: 1180,
    minHeight: 720,
    show: false,
    backgroundColor: '#f3f6fb',
    title: 'KDRG V4.7 Stage 51D Runtime UI Preview',
    webPreferences: {
      preload: path.join(ELECTRON_ROOT, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      devTools: false,
      spellcheck: false,
    },
  });

  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  window.webContents.on('will-navigate', (event) => event.preventDefault());
  window.webContents.on('console-message', (_event, level, message, line, sourceId) => {
    if (Number(level) >= 2) {
      consoleErrors.push({
        level,
        message,
        line,
        sourceId,
      });
    }
  });
  window.webContents.on('render-process-gone', (_event, details) => {
    rendererGone.push(details);
  });
  window.webContents.on(
    'did-fail-load',
    (_event, errorCode, errorDescription, validatedURL, isMainFrame) => {
      if (isMainFrame) {
        loadFailures.push({
          errorCode,
          errorDescription,
          validatedURL,
        });
      }
    },
  );
  return window;
}

async function initializeRenderer() {
  await mainWindow.loadFile(path.join(ELECTRON_ROOT, 'renderer', 'index.html'));
  await waitFor(
    `(() => {
      const input = document.querySelector('#search-query');
      const status = document.querySelector('#status-detail');
      return Boolean(
        document.readyState === 'complete'
        && input
        && !input.disabled
        && status
      );
    })()`,
    'renderer 초기화',
    20000,
  );
}

async function runSearch(adrg) {
  const encoded = JSON.stringify(adrg);
  await execute(
    `(() => {
      const input = document.querySelector('#search-query');
      const type = document.querySelector('#filter-type');
      const form = document.querySelector('#search-form');
      input.value = ${encoded};
      type.value = 'ADRG';
      type.dispatchEvent(new Event('change', { bubbles: true }));
      form.dispatchEvent(new Event('submit', {
        bubbles: true,
        cancelable: true,
      }));
      return true;
    })()`,
  );

  await waitFor(
    `(() => {
      const panel = document.querySelector('#detail-content');
      const caption = document.querySelector('#detail-caption');
      return Boolean(
        panel
        && panel.textContent.includes(${encoded})
        && caption
        && !caption.textContent.includes('불러오는 중')
      );
    })()`,
    `${adrg} 상세 로드`,
    20000,
  );
}

async function inspectCase(fixture) {
  const fixtureJson = JSON.stringify(fixture);
  return execute(
    `(() => {
      const fixture = ${fixtureJson};
      const panel = document.querySelector('#detail-content');
      const panelText = panel?.textContent || '';
      const tableCards = [...panel.querySelectorAll('details[data-inline-table-id]')];
      const tableIds = tableCards.map((card) => card.dataset.inlineTableId);
      const oldLabels = ['기본 분류 TABLE', '추가 분기조건']
        .filter((label) => panelText.includes(label));
      const sectionLabels = ['분류 조건', '조건 상세', '원문 근거']
        .filter((label) => panelText.includes(label));
      return {
        panel_text: panelText.replace(/\\s+/g, ' ').trim(),
        table_ids: tableIds,
        old_labels: oldLabels,
        section_labels: sectionLabels,
        expected_text_presence: Object.fromEntries(
          fixture.expectedText.map((text) => [text, panelText.includes(text)]),
        ),
        expected_status_present: panelText.includes(fixture.expectedStatus),
      };
    })()`,
  );
}

async function expandAndLoadTables(expectedCount) {
  if (!expectedCount) {
    return {
      loaded_table_count: 0,
      code_row_counts: [],
    };
  }

  await execute(
    `(() => {
      for (const section of document.querySelectorAll(
        '#detail-content details.detail-section, #detail-content details.table-card'
      )) {
        section.open = true;
      }
      return true;
    })()`,
  );

  await waitFor(
    `(() => {
      const cards = [...document.querySelectorAll(
        '#detail-content details[data-inline-table-id]'
      )];
      return cards.length === ${Number(expectedCount)}
        && cards.every((card) => card.dataset.loaded === 'true');
    })()`,
    `인라인 TABLE ${expectedCount}개 로드`,
    30000,
  );

  return execute(
    `(() => {
      const cards = [...document.querySelectorAll(
        '#detail-content details[data-inline-table-id]'
      )];
      return {
        loaded_table_count: cards.filter(
          (card) => card.dataset.loaded === 'true'
        ).length,
        code_row_counts: cards.map(
          (card) => card.querySelectorAll('.inline-code-row').length
        ),
      };
    })()`,
  );
}

async function captureCase(adrg) {
  await delay(250);
  const image = await mainWindow.webContents.capturePage();
  if (!image || image.isEmpty()) {
    throw new Error(`${adrg} 화면 캡처가 비어 있습니다.`);
  }
  const png = image.toPNG();
  const fileName = `${adrg}.png`;
  const filePath = path.join(REPORT_DIR, fileName);
  fs.writeFileSync(filePath, png);
  const size = image.getSize();
  return {
    filename: fileName,
    path: filePath,
    width: size.width,
    height: size.height,
    size_bytes: png.length,
    sha256: sha256(png),
    non_blank: size.width >= 1180 && size.height >= 720 && png.length >= 15000,
  };
}

function arraysEqual(actual, expected) {
  return JSON.stringify(actual) === JSON.stringify(expected);
}

function buildCaseChecks(fixture, inspection, inline, screenshot) {
  const checks = [];
  const add = (name, passed, actual, expected) => {
    checks.push({ name, passed: Boolean(passed), actual, expected });
  };

  add(
    'section_labels',
    arraysEqual(inspection.section_labels, ['분류 조건', '조건 상세', '원문 근거']),
    inspection.section_labels,
    ['분류 조건', '조건 상세', '원문 근거'],
  );
  add('old_labels_absent', inspection.old_labels.length === 0, inspection.old_labels, []);
  add(
    'table_ids',
    arraysEqual(inspection.table_ids, fixture.expectedTables),
    inspection.table_ids,
    fixture.expectedTables,
  );
  add(
    'expected_text',
    Object.values(inspection.expected_text_presence).every(Boolean),
    inspection.expected_text_presence,
    'all true',
  );
  add(
    'expected_status',
    inspection.expected_status_present,
    inspection.expected_status_present,
    true,
  );
  add(
    'loaded_table_count',
    inline.loaded_table_count === fixture.expectedLoadedTables,
    inline.loaded_table_count,
    fixture.expectedLoadedTables,
  );
  if (fixture.expectedLoadedTables > 0) {
    add(
      'inline_code_rows',
      inline.code_row_counts.length === fixture.expectedLoadedTables
        && inline.code_row_counts.every((count) => count > 0),
      inline.code_row_counts,
      'all > 0',
    );
  }
  add(
    'forbidden_tables_absent',
    !(fixture.forbiddenTables || []).some(
      (tableId) => inspection.table_ids.includes(tableId),
    ),
    inspection.table_ids,
    `exclude ${JSON.stringify(fixture.forbiddenTables || [])}`,
  );
  add(
    'screenshot_non_blank',
    screenshot.non_blank,
    {
      width: screenshot.width,
      height: screenshot.height,
      size_bytes: screenshot.size_bytes,
    },
    '>=1180x720 and >=15000 bytes',
  );
  return checks;
}

function writeIndex(cases) {
  const cards = cases.map((item) => {
    const checks = item.checks
      .map((check) => `<li class="${check.passed ? 'pass' : 'fail'}">${
        check.passed ? 'PASS' : 'FAIL'
      } · ${check.name}</li>`)
      .join('');
    return `
      <section class="card">
        <h2>${item.adrg}</h2>
        <p>TABLE: ${item.table_ids.join(', ') || '없음'}</p>
        <img src="${item.screenshot_filename}" alt="${item.adrg} Electron 화면">
        <ul>${checks}</ul>
      </section>
    `;
  }).join('\n');

  const html = `<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>KDRG Stage 51D Electron Runtime UI Preview</title>
<style>
body { margin: 0; padding: 24px; font-family: sans-serif; background: #f3f6fb; color: #172033; }
header, .card { background: white; border: 1px solid #d7e0ea; border-radius: 12px; padding: 18px; margin-bottom: 20px; }
img { display: block; width: 100%; height: auto; border: 1px solid #cbd5e1; }
ul { columns: 2; }
.pass { color: #116b3a; }
.fail { color: #b42318; font-weight: 700; }
</style>
</head>
<body>
<header>
<h1>KDRG V4.7 Stage 51D Electron 실제 화면 검증</h1>
<p>mode=${MODE} · Electron ${process.versions.electron} · Node ${process.versions.node}</p>
</header>
${cards}
</body>
</html>`;
  fs.writeFileSync(INDEX_HTML, html, 'utf8');
}

async function run() {
  const result = {
    meta: {
      schema_version: 'kdrg-v47-stage51d-electron-runtime-ui-preview-v1',
      script_version: VERSION,
      generated_at: new Date().toISOString(),
      mode: MODE,
      headless: HEADLESS,
      electron: process.versions.electron,
      chrome: process.versions.chrome,
      node: process.versions.node,
    },
    passed: false,
    case_count: CASES.length,
    screenshot_count: 0,
    console_error_count: 0,
    render_process_gone_count: 0,
    load_failure_count: 0,
    bootstrap: null,
    service_status: null,
    cases: [],
    console_errors: consoleErrors,
    renderer_gone: rendererGone,
    load_failures: loadFailures,
    errors: [],
  };

  try {
    registerIpc();
    result.bootstrap = bootstrap();
    result.service_status = service().status();

    mainWindow = createWindow();
    await initializeRenderer();

    for (const fixture of CASES) {
      await runSearch(fixture.adrg);
      const inspection = await inspectCase(fixture);
      const inline = await expandAndLoadTables(fixture.expectedLoadedTables);
      const screenshot = await captureCase(fixture.adrg);
      const checks = buildCaseChecks(fixture, inspection, inline, screenshot);
      result.cases.push({
        adrg: fixture.adrg,
        table_ids: inspection.table_ids,
        loaded_table_count: inline.loaded_table_count,
        code_row_counts: inline.code_row_counts,
        screenshot_filename: screenshot.filename,
        screenshot_path: screenshot.path,
        screenshot_sha256: screenshot.sha256,
        screenshot_non_blank: screenshot.non_blank,
        screenshot_size_bytes: screenshot.size_bytes,
        panel_text: inspection.panel_text,
        checks,
        passed: checks.every((check) => check.passed),
      });
    }

    result.screenshot_count = result.cases.length;
    result.console_error_count = consoleErrors.length;
    result.render_process_gone_count = rendererGone.length;
    result.load_failure_count = loadFailures.length;

    const screenshotHashes = result.cases.map((item) => item.screenshot_sha256);
    result.global_checks = [
      {
        name: 'all_cases_pass',
        passed: result.cases.every((item) => item.passed),
      },
      {
        name: 'console_error_count',
        passed: consoleErrors.length === 0,
        actual: consoleErrors.length,
        expected: 0,
      },
      {
        name: 'render_process_gone_count',
        passed: rendererGone.length === 0,
        actual: rendererGone.length,
        expected: 0,
      },
      {
        name: 'load_failure_count',
        passed: loadFailures.length === 0,
        actual: loadFailures.length,
        expected: 0,
      },
      {
        name: 'all_screenshots_distinct',
        passed: new Set(screenshotHashes).size === CASES.length,
        actual: new Set(screenshotHashes).size,
        expected: CASES.length,
      },
    ];
    result.passed = result.global_checks.every((check) => check.passed);
    writeIndex(result.cases);
    result.index_html = INDEX_HTML;
  } catch (error) {
    result.errors.push({
      type: error?.name || 'Error',
      message: error?.message || String(error),
      stack: error?.stack || '',
    });
    result.passed = false;
  } finally {
    result.console_error_count = consoleErrors.length;
    result.render_process_gone_count = rendererGone.length;
    result.load_failure_count = loadFailures.length;
    fs.writeFileSync(RESULT_JSON, `${JSON.stringify(result, null, 2)}\n`, 'utf8');
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.destroy();
    }
  }

  if (!result.passed) {
    console.error('[FAIL] Electron Stage 51D runtime UI preview');
    for (const item of result.cases) {
      for (const check of item.checks || []) {
        if (!check.passed) {
          console.error(
            `- ${item.adrg} ${check.name}: `
            + `actual=${JSON.stringify(check.actual)} `
            + `expected=${JSON.stringify(check.expected)}`,
          );
        }
      }
    }
    for (const error of result.errors) {
      console.error(error.stack || error.message);
    }
    process.exitCode = 1;
    return;
  }

  console.log(
    `[PASS] Electron Stage 51D runtime UI preview: `
    + `${result.cases.length} cases / `
    + `${result.screenshot_count} screenshots / 0 FAIL`,
  );
  console.log(`result=${RESULT_JSON}`);
  console.log(`index=${INDEX_HTML}`);
}

app.whenReady()
  .then(run)
  .then(() => {
    setTimeout(() => app.exit(process.exitCode || 0), 50);
  })
  .catch((error) => {
    console.error(error?.stack || error);
    app.exit(1);
  });
