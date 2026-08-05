'use strict';

const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

const RESPONSE_SCHEMA_VERSION = 'kdrg-runtime-search-response-v1';
const RELATION_RESPONSE_SCHEMA_VERSION = 'kdrg-runtime-relation-response-v1';
const UI_SMOKE_SCHEMA_VERSION = 'kdrg-packaged-ui-smoke-v1';

const EXPECTED_COUNTS = Object.freeze({
  adrg: 1132,
  aadrg: 1233,
  rdrg: 2699,
  tables: 1308,
  codes: 16571,
  conditionAst: 390,
  conditionTableOccurrences: 939,
});

const UI_FIXTURES = Object.freeze([
  Object.freeze({
    adrg: 'B013',
    expected_table_ids: Object.freeze(['LT_B018_002']),
    forbidden_table_ids: Object.freeze([]),
    required_table_labels: Object.freeze(['시술명 table2']),
  }),
  Object.freeze({
    adrg: 'B014',
    expected_table_ids: Object.freeze(['LT_B018_003']),
    forbidden_table_ids: Object.freeze([]),
    required_table_labels: Object.freeze(['시술명 table3']),
  }),
  Object.freeze({
    adrg: 'B018',
    expected_table_ids: Object.freeze([
      'LT_B018_001',
      'LT_B018_004',
      'LT_B018_005',
    ]),
    forbidden_table_ids: Object.freeze([
      'LT_B018_002',
      'LT_B018_003',
    ]),
    required_table_labels: Object.freeze([
      '주진단명 또는 기타진단명 table1',
      '시술명 table4',
      '시술명 table5',
    ]),
  }),
  Object.freeze({
    adrg: 'B022',
    expected_table_ids: Object.freeze([]),
    forbidden_table_ids: Object.freeze([]),
    required_table_labels: Object.freeze([]),
  }),
  Object.freeze({
    adrg: 'L033',
    expected_table_ids: Object.freeze([]),
    forbidden_table_ids: Object.freeze([]),
    required_table_labels: Object.freeze([]),
  }),
  Object.freeze({
    adrg: '9610',
    expected_table_ids: Object.freeze([]),
    forbidden_table_ids: Object.freeze([]),
    required_table_labels: Object.freeze([]),
  }),
]);

const REQUIRED_DETAIL_LABELS = Object.freeze([
  '분류 조건',
  '조건 상세',
  '원문 근거',
]);

const FORBIDDEN_DETAIL_LABELS = Object.freeze([
  '기본 분류 TABLE',
  '추가 분기조건',
]);

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

function uniqueStrings(values) {
  return [...new Set(
    (Array.isArray(values) ? values : [])
      .map((value) => String(value ?? '').trim())
      .filter(Boolean),
  )];
}

function sortedStrings(values) {
  return uniqueStrings(values).sort((left, right) => left.localeCompare(right));
}

function sameStringSet(actual, expected) {
  return JSON.stringify(sortedStrings(actual)) === JSON.stringify(sortedStrings(expected));
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
      || item.condition_groups.some((group) => !Array.isArray(group.exclude_table_ids)
        || !Array.isArray(group.exclude_tables))) {
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

function sha256Buffer(buffer) {
  return crypto.createHash('sha256').update(buffer).digest('hex');
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function htmlEscape(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function normalizeConsoleMessage(args) {
  if (args.length === 1 && isPlainObject(args[0])) {
    const details = args[0];
    return {
      level: Number(details.level ?? -1),
      message: String(details.message ?? ''),
      line: Number(details.lineNumber ?? details.line ?? 0),
      source_id: String(details.sourceId ?? details.source_id ?? ''),
    };
  }
  return {
    level: Number(args[0] ?? -1),
    message: String(args[1] ?? ''),
    line: Number(args[2] ?? 0),
    source_id: String(args[3] ?? ''),
  };
}

function analyzeNativeImage(image, pngBuffer) {
  const size = image.getSize();
  const bitmap = image.toBitmap();
  const unique = new Set();
  const targetSamples = 5000;
  const pixelCount = Math.max(1, Math.floor(bitmap.length / 4));
  const pixelStep = Math.max(1, Math.floor(pixelCount / targetSamples));

  for (let pixelIndex = 0; pixelIndex < pixelCount; pixelIndex += pixelStep) {
    const offset = pixelIndex * 4;
    if (offset + 3 >= bitmap.length) break;
    unique.add(bitmap.readUInt32LE(offset));
  }

  return {
    width: size.width,
    height: size.height,
    size_bytes: pngBuffer.length,
    sampled_unique_colors: unique.size,
    non_blank: (
      size.width >= 1200
      && size.height >= 700
      && pngBuffer.length >= 10000
      && unique.size >= 20
    ),
  };
}

function validateUiCaseSnapshot(snapshot, fixture) {
  requirePlainObject(snapshot, `${fixture.adrg} UI snapshot`);
  const tableIds = sortedStrings(snapshot.table_ids);
  const expectedTableIds = sortedStrings(fixture.expected_table_ids);
  const forbiddenTableIds = sortedStrings(fixture.forbidden_table_ids);
  const labels = uniqueStrings(snapshot.table_labels);
  const detailText = String(snapshot.detail_text ?? '');
  const errors = uniqueStrings(snapshot.error_messages);
  const checks = [];

  const add = (name, passed, actual, expected) => {
    checks.push({ name, passed: Boolean(passed), actual, expected });
  };

  add('selected_adrg', snapshot.selected_adrg === fixture.adrg, snapshot.selected_adrg, fixture.adrg);
  add('table_ids_exact', sameStringSet(tableIds, expectedTableIds), tableIds, expectedTableIds);
  add(
    'forbidden_table_ids_absent',
    forbiddenTableIds.every((tableId) => !tableIds.includes(tableId)),
    tableIds,
    `exclude=${forbiddenTableIds.join(',') || 'none'}`,
  );
  add(
    'required_detail_labels',
    REQUIRED_DETAIL_LABELS.every((label) => detailText.includes(label)),
    REQUIRED_DETAIL_LABELS.filter((label) => detailText.includes(label)),
    REQUIRED_DETAIL_LABELS,
  );
  add(
    'obsolete_detail_labels_absent',
    FORBIDDEN_DETAIL_LABELS.every((label) => !detailText.includes(label)),
    FORBIDDEN_DETAIL_LABELS.filter((label) => detailText.includes(label)),
    [],
  );
  add(
    'required_table_labels',
    fixture.required_table_labels.every((label) => labels.includes(label)),
    labels,
    fixture.required_table_labels,
  );
  add(
    'internal_table_id_not_used_as_label',
    labels.every((label) => !/^LT_[A-Z0-9_]+$/i.test(label)),
    labels,
    'no LT_* user label',
  );
  add('inline_error_messages_0', errors.length === 0, errors, []);
  add(
    'loaded_table_count',
    Number(snapshot.loaded_table_count) === expectedTableIds.length,
    Number(snapshot.loaded_table_count),
    expectedTableIds.length,
  );
  add(
    'code_rows_loaded',
    expectedTableIds.length === 0 || Number(snapshot.code_row_total) > 0,
    Number(snapshot.code_row_total),
    expectedTableIds.length === 0 ? 0 : '> 0',
  );

  const failed = checks.filter((check) => !check.passed);
  return {
    passed: failed.length === 0,
    checks,
    failed_checks: failed.map((check) => check.name),
  };
}

async function waitForRendererCondition(webContents, expression, label, timeoutMs = 30000) {
  const started = Date.now();
  let lastValue = null;
  while (Date.now() - started < timeoutMs) {
    lastValue = await webContents.executeJavaScript(
      `Promise.resolve(Boolean(${expression}))`,
      true,
    );
    if (lastValue) return true;
    await delay(100);
  }
  throw new Error(`${label} timeout: ${timeoutMs}ms, last=${lastValue}`);
}

async function executeRendererFixture(webContents, fixture) {
  const fixtureJson = JSON.stringify(fixture);
  return webContents.executeJavaScript(
    `(async () => {
      const fixture = ${fixtureJson};
      const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
      const waitFor = async (predicate, label, timeoutMs = 30000) => {
        const started = Date.now();
        let last = null;
        while (Date.now() - started < timeoutMs) {
          try {
            last = predicate();
            if (last) return last;
          } catch (_error) {
            last = null;
          }
          await sleep(100);
        }
        throw new Error(label + ' timeout: ' + timeoutMs + 'ms');
      };

      const input = document.querySelector('#search-query');
      const filter = document.querySelector('#filter-type');
      const form = document.querySelector('#search-form');
      if (!input || !filter || !form) {
        throw new Error('search DOM contract mismatch');
      }

      filter.value = 'ADRG';
      filter.dispatchEvent(new Event('change', { bubbles: true }));
      input.value = fixture.adrg;
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));

      if (typeof form.requestSubmit === 'function') {
        form.requestSubmit();
      } else {
        form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
      }

      await waitFor(() => {
        const detail = document.querySelector('#detail-content');
        const result = document.querySelector(
          '#result-list [data-entity-type="ADRG"][data-entity-id="' + fixture.adrg + '"]'
        );
        return Boolean(
          detail
          && result
          && detail.textContent.includes(fixture.adrg)
          && !document.querySelector('#search-submit')?.disabled
        );
      }, fixture.adrg + ' detail ready');

      const cards = [
        ...document.querySelectorAll('#detail-content details.inline-table-card')
      ];
      for (const card of cards) {
        if (!card.open) card.open = true;
      }

      if (cards.length) {
        await waitFor(
          () => cards.every((card) => (
            card.dataset.loaded === 'true'
            || Boolean(card.querySelector('.error-message'))
          )),
          fixture.adrg + ' inline TABLE load',
        );
      }

      document.querySelector('#detail-content')?.scrollTo?.({ top: 0 });
      document.scrollingElement?.scrollTo?.({ top: 0 });
      await sleep(250);

      const refreshedCards = [
        ...document.querySelectorAll('#detail-content details.inline-table-card')
      ];
      const tableIds = refreshedCards.map((card) => (
        card.dataset.inlineTableId
        || card.getAttribute('data-inline-table-id')
        || card.querySelector('[data-entity-id]')?.dataset.entityId
        || ''
      )).filter(Boolean);
      const tableLabels = refreshedCards.map((card) => (
        card.querySelector('.table-user-label')?.textContent?.trim() || ''
      )).filter(Boolean);
      const codeRowCounts = Object.fromEntries(
        refreshedCards.map((card) => {
          const tableId = (
            card.dataset.inlineTableId
            || card.getAttribute('data-inline-table-id')
            || card.querySelector('[data-entity-id]')?.dataset.entityId
            || ''
          );
          return [tableId, card.querySelectorAll('.inline-code-row').length];
        }).filter(([tableId]) => tableId)
      );

      return {
        selected_adrg: fixture.adrg,
        result_count_text: document.querySelector('#result-count')?.textContent?.trim() || '',
        result_caption: document.querySelector('#result-caption')?.textContent?.trim() || '',
        detail_caption: document.querySelector('#detail-caption')?.textContent?.trim() || '',
        detail_text: document.querySelector('#detail-content')?.textContent || '',
        table_ids: tableIds,
        table_labels: tableLabels,
        inline_table_count: refreshedCards.length,
        loaded_table_count: refreshedCards.filter(
          (card) => card.dataset.loaded === 'true'
        ).length,
        code_row_counts: codeRowCounts,
        code_row_total: Object.values(codeRowCounts).reduce(
          (total, value) => total + Number(value || 0),
          0
        ),
        error_messages: [
          ...document.querySelectorAll('#detail-content .error-message')
        ].map((node) => node.textContent?.trim() || '').filter(Boolean),
      };
    })()`,
    true,
  );
}

function writeUiIndex(directory, cases) {
  const cards = cases.map((item) => `
    <section class="card">
      <h2>${htmlEscape(item.adrg)}</h2>
      <p>TABLE: ${htmlEscape(item.table_ids.join(', ') || '없음')}</p>
      <p>검증: ${item.passed ? 'PASS' : 'FAIL'}</p>
      <img src="${htmlEscape(item.screenshot_filename)}" alt="${htmlEscape(item.adrg)}">
    </section>
  `).join('\n');

  const indexPath = path.join(directory, 'index.html');
  fs.writeFileSync(indexPath, `<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>KDRG Stage 51D Windows packaged UI smoke</title>
<style>
body { margin: 0; padding: 24px; font-family: "Malgun Gothic", sans-serif; background: #f3f6fb; color: #172033; }
.card { margin: 0 0 24px; padding: 18px; background: white; border: 1px solid #d8e0ea; border-radius: 12px; }
.card h2 { margin: 0 0 8px; }
.card p { margin: 4px 0; }
.card img { display: block; width: 100%; margin-top: 14px; border: 1px solid #cfd8e3; }
</style>
</head>
<body>
<h1>KDRG V4.7 Stage 51D Windows packaged UI smoke</h1>
${cards}
</body>
</html>
`, 'utf8');
  return indexPath;
}

async function runPackagedUiValidation(smokeWindow, screenshotDirectory) {
  const webContents = smokeWindow.webContents;
  const consoleErrors = [];
  const renderProcessGone = [];
  const loadFailures = [];

  const onConsoleMessage = (_event, ...args) => {
    const message = normalizeConsoleMessage(args);
    if (message.level >= 3) consoleErrors.push(message);
  };
  const onGone = (_event, details) => {
    renderProcessGone.push({
      reason: details?.reason || 'unknown',
      exit_code: details?.exitCode ?? null,
    });
  };
  const onFail = (_event, errorCode, errorDescription, validatedURL, isMainFrame) => {
    if (isMainFrame === false) return;
    loadFailures.push({
      error_code: errorCode,
      error_description: errorDescription,
      validated_url: validatedURL,
    });
  };

  webContents.on('console-message', onConsoleMessage);
  webContents.on('render-process-gone', onGone);
  webContents.on('did-fail-load', onFail);

  try {
    fs.mkdirSync(screenshotDirectory, { recursive: true });

    await waitForRendererCondition(
      webContents,
      `window.KDRG
        && document.readyState === 'complete'
        && document.querySelector('#search-form')
        && document.querySelector('#status-detail')
        && document.querySelector('#status-detail').textContent
          !== '검색 서비스를 준비하고 있습니다.'`,
      'renderer initialize',
      30000,
    );

    const cases = [];
    for (const [index, fixture] of UI_FIXTURES.entries()) {
      const snapshot = await executeRendererFixture(webContents, fixture);
      const validation = validateUiCaseSnapshot(snapshot, fixture);
      const filename = `${String(index + 1).padStart(2, '0')}_${fixture.adrg}.png`;
      const screenshotPath = path.join(screenshotDirectory, filename);
      const image = await webContents.capturePage();
      const png = image.toPNG();
      const metrics = analyzeNativeImage(image, png);
      const screenshotSha256 = sha256Buffer(png);
      fs.writeFileSync(screenshotPath, png);

      cases.push({
        adrg: fixture.adrg,
        expected_table_ids: [...fixture.expected_table_ids],
        forbidden_table_ids: [...fixture.forbidden_table_ids],
        required_table_labels: [...fixture.required_table_labels],
        ...snapshot,
        ...validation,
        screenshot_filename: filename,
        screenshot_path: screenshotPath,
        screenshot_sha256: screenshotSha256,
        screenshot: metrics,
        passed: validation.passed && metrics.non_blank,
      });
    }

    const hashes = cases.map((item) => item.screenshot_sha256);
    const distinctCount = new Set(hashes).size;
    const indexPath = writeUiIndex(screenshotDirectory, cases);

    const result = {
      schema_version: UI_SMOKE_SCHEMA_VERSION,
      status: (
        cases.length === UI_FIXTURES.length
        && cases.every((item) => item.passed)
        && distinctCount === UI_FIXTURES.length
        && consoleErrors.length === 0
        && renderProcessGone.length === 0
        && loadFailures.length === 0
      ) ? 'PASS' : 'FAIL',
      case_count: cases.length,
      screenshot_count: cases.length,
      screenshot_distinct_count: distinctCount,
      console_error_count: consoleErrors.length,
      render_process_gone_count: renderProcessGone.length,
      load_failure_count: loadFailures.length,
      console_errors: consoleErrors,
      render_process_gone: renderProcessGone,
      load_failures: loadFailures,
      index_html: indexPath,
      cases,
    };

    if (result.status !== 'PASS') {
      throw new Error(
        `packaged UI validation failed: cases=${cases.filter((item) => item.passed).length}/${cases.length}, `
        + `distinct=${distinctCount}/${UI_FIXTURES.length}, `
        + `console=${consoleErrors.length}, gone=${renderProcessGone.length}, load=${loadFailures.length}`,
      );
    }

    return result;
  } finally {
    webContents.removeListener('console-message', onConsoleMessage);
    webContents.removeListener('render-process-gone', onGone);
    webContents.removeListener('did-fail-load', onFail);
  }
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
  const screenshotDirectory = path.resolve(
    process.env.KDRG_ELECTRON_SMOKE_SCREENSHOT_DIR
      || path.join(path.dirname(reportPath || process.cwd()), 'kdrg_electron_ui_smoke'),
  );
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
      width: 1600,
      height: 980,
      show: false,
      backgroundColor: '#f3f6fb',
      webPreferences: {
        preload: preloadPath,
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true,
        devTools: false,
        spellcheck: false,
        backgroundThrottling: false,
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

    currentStep = 'packaged_ui_validation';
    const uiValidation = await runPackagedUiValidation(
      smokeWindow,
      screenshotDirectory,
    );
    markStep('packaged_ui_verified');

    const report = {
      status: 'PASS',
      schema_version: 'kdrg-packaged-runtime-smoke-v2',
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
      ui_validation: uiValidation,
    };
    writeSmokeReport(reportPath, report);
    return report;
  } catch (error) {
    const report = {
      status: 'FAIL',
      schema_version: 'kdrg-packaged-runtime-smoke-v2',
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
  UI_SMOKE_SCHEMA_VERSION,
  EXPECTED_COUNTS,
  UI_FIXTURES,
  REQUIRED_DETAIL_LABELS,
  FORBIDDEN_DETAIL_LABELS,
  shouldRunPackagedSmoke,
  validateSearchResponse,
  validateRelationResponse,
  findRelationSmokeFixture,
  validateDetailResponse,
  validateBootstrapCounts,
  waitForRendererLoad,
  normalizeConsoleMessage,
  analyzeNativeImage,
  validateUiCaseSnapshot,
  runPackagedUiValidation,
  runPackagedRuntimeSmoke,
});
