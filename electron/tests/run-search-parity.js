'use strict';

const fs = require('node:fs');
const path = require('node:path');
function canonicalize(value) {
  if (Array.isArray(value)) {
    return value.map(canonicalize);
  }
  if (value && typeof value === 'object') {
    if (value instanceof Set) {
      return [...value].sort();
    }
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, canonicalize(value[key])]),
    );
  }
  return value;
}

function canonicalJson(value) {
  return JSON.stringify(canonicalize(value));
}

const SCRIPT_VERSION = '2026-07-30_KDRG_V47_ELECTRON_STAGE50B_PARITY_RUNNER_V2';

function fail(message) {
  console.error(`[FAIL] ${message}`);
  process.exit(1);
}

function isPlainObject(value) {
  return Boolean(value)
    && typeof value === 'object'
    && !Array.isArray(value)
    && Object.getPrototypeOf(value) === Object.prototype;
}

function projectStatusByBaseline(actualStatus, baselineStatus) {
  if (!isPlainObject(actualStatus)) {
    throw new TypeError('actual status must be a plain object');
  }
  if (!isPlainObject(baselineStatus)) {
    throw new TypeError('baseline status must be a plain object');
  }

  const projected = {};
  for (const key of Object.keys(baselineStatus)) {
    if (!Object.prototype.hasOwnProperty.call(actualStatus, key)) {
      throw new Error(`actual status is missing baseline key: ${key}`);
    }
    projected[key] = actualStatus[key];
  }
  return projected;
}

function additiveStatusKeys(actualStatus, baselineStatus) {
  return Object.keys(actualStatus)
    .filter((key) => !Object.prototype.hasOwnProperty.call(baselineStatus, key))
    .sort();
}

function runSelfTest() {
  const failures = [];
  let passCount = 0;

  function check(name, actual, expected) {
    if (canonicalJson(actual) === canonicalJson(expected)) passCount += 1;
    else failures.push({ name, actual, expected });
  }

  const baseline = { ready: true, response_schema_version: 'search-v1' };
  const additive = {
    ready: true,
    response_schema_version: 'search-v1',
    relation_response_schema_version: 'relation-v1',
  };

  check(
    'additive status field accepted',
    projectStatusByBaseline(additive, baseline),
    baseline,
  );
  check(
    'additive status field reported',
    additiveStatusKeys(additive, baseline),
    ['relation_response_schema_version'],
  );

  let missingDetected = false;
  try {
    projectStatusByBaseline({ ready: true }, baseline);
  } catch (error) {
    missingDetected = /missing baseline key/.test(String(error.message));
  }
  check('missing baseline key detected', missingDetected, true);

  let changedDetected = false;
  const changed = projectStatusByBaseline(
    { ready: false, response_schema_version: 'search-v1' },
    baseline,
  );
  changedDetected = canonicalJson(changed) !== canonicalJson(baseline);
  check('changed baseline value remains detectable', changedDetected, true);

  console.log(`validator=${SCRIPT_VERSION}`);
  if (failures.length) {
    console.log(
      `[FAIL] Python-JavaScript status parity self-test: `
      + `${passCount} PASS / ${failures.length} FAIL`,
    );
    for (const item of failures) {
      console.log(`- ${item.name}`);
      console.log(`  actual=${canonicalJson(item.actual)}`);
      console.log(`  expected=${canonicalJson(item.expected)}`);
    }
    process.exitCode = 1;
  } else {
    console.log(
      `[PASS] Python-JavaScript status parity self-test: `
      + `${passCount} PASS / 0 FAIL`,
    );
  }
}

if (process.argv.includes('--self-test')) {
  runSelfTest();
} else {
  const baselinePath = process.argv[2];
  const dataPath = process.argv[3];
  if (!baselinePath || !dataPath) {
    fail('사용법: node run-search-parity.js <baseline.json> <integrated.json>');
  }

  const { KdrgSearchService } = require('../src/kdrg-search-service');
  const baseline = JSON.parse(
    fs.readFileSync(path.resolve(baselinePath), 'utf8'),
  );
  const service = new KdrgSearchService(path.resolve(dataPath));
  const failures = [];
  let passCount = 0;

  function check(name, actual, expected) {
    if (canonicalJson(actual) === canonicalJson(expected)) passCount += 1;
    else failures.push({ name, actual, expected });
  }

  const status = service.status();
  delete status.data_path;

  let projectedStatus;
  try {
    projectedStatus = projectStatusByBaseline(status, baseline.status);
  } catch (error) {
    failures.push({
      name: 'status baseline contract',
      actual: `${error.name}: ${error.message}`,
      expected: baseline.status,
    });
  }
  if (projectedStatus) {
    check('status baseline contract', projectedStatus, baseline.status);
  }

  const additiveKeys = additiveStatusKeys(status, baseline.status);
  check(
    'search document fingerprint',
    service.debugSearchDocumentFingerprint(),
    baseline.search_document_fingerprint,
  );
  check(
    'semantic context fingerprint',
    service.debugSemanticContextFingerprint(),
    baseline.semantic_context_fingerprint,
  );
  check('exact ID audit', service.debugExactIdAudit(), baseline.exact_id_audit);

  for (const scenario of baseline.search_scenarios) {
    const actual = service.search(
      scenario.request.query,
      scenario.request.entity_type,
      scenario.request.options,
    );
    check(`search:${scenario.name}`, actual, scenario.response);
  }

  for (const scenario of baseline.detail_scenarios) {
    const actual = service.getDetail(
      scenario.request.entity_type,
      scenario.request.entity_id,
    );
    check(`detail:${scenario.name}`, actual, scenario.response);
  }

  console.log(`validator=${SCRIPT_VERSION}`);
  console.log(`node=${process.version}`);
  console.log(`baseline=${path.resolve(baselinePath)}`);
  console.log(
    `status_additive_keys=${additiveKeys.length ? additiveKeys.join(',') : 'none'}`,
  );

  if (failures.length) {
    console.log(
      `[FAIL] Python-JavaScript 검색 동등성: `
      + `${passCount} PASS / ${failures.length} FAIL`,
    );
    console.log('[FAIL 상세]');
    for (const item of failures.slice(0, 20)) {
      console.log(`- ${item.name}`);
      console.log(`  actual=${canonicalJson(item.actual).slice(0, 2000)}`);
      console.log(`  expected=${canonicalJson(item.expected).slice(0, 2000)}`);
    }
    process.exitCode = 1;
  } else {
    console.log(
      `[PASS] Python-JavaScript 검색 동등성: ${passCount} PASS / 0 FAIL`,
    );
  }
}
