'use strict';

const fs = require('node:fs');
const path = require('node:path');

const SCRIPT_VERSION = '2026-08-12_KDRG_V47_ELECTRON_STAGE50B_PARITY_RUNNER_V5_CODE_NAME_ENRICHMENT';

const STATUS_TRANSITIONS = Object.freeze({
  data_schema_version: Object.freeze({
    baseline: 'kdrg-v47-search-integrated-v2',
    actual: 'kdrg-v47-search-integrated-v3',
  }),
  data_state: Object.freeze({
    baseline: 'search_ready_integrated_base_v2',
    actual: 'production_ready_with_review_required_exceptions',
  }),
});

const SEARCH_DOCUMENT_FINGERPRINT_TRANSITION = Object.freeze({
  baseline: Object.freeze({
    count: 22943,
    sha256: '8a832be02ae4dec16c3cfc93d2be8366914c23fdb0872bfa088a1a6c788f56f3',
  }),
  actual: Object.freeze({
    count: 22943,
    sha256: '2e6e89bb7dd3eb027c2aa8d65fe90e59a50f26e08991061c989640a0489f33dd',
  }),
  reason: 'Stage 54 official code-name enrichment changes Electron v3 CODE documents while preserving prior baseline entities',
});

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

function projectByBaseline(actual, baseline, location = 'root') {
  if (Array.isArray(baseline)) {
    if (!Array.isArray(actual)) {
      throw new TypeError(`${location}: actual value must be an array`);
    }
    if (actual.length !== baseline.length) {
      throw new Error(
        `${location}: array length changed: actual=${actual.length}, baseline=${baseline.length}`,
      );
    }
    return baseline.map(
      (baselineItem, index) => projectByBaseline(
        actual[index],
        baselineItem,
        `${location}[${index}]`,
      ),
    );
  }

  if (isPlainObject(baseline)) {
    if (!isPlainObject(actual)) {
      throw new TypeError(`${location}: actual value must be a plain object`);
    }

    const projected = {};
    for (const key of Object.keys(baseline)) {
      if (!Object.prototype.hasOwnProperty.call(actual, key)) {
        throw new Error(`${location}: actual is missing baseline key: ${key}`);
      }
      projected[key] = projectByBaseline(
        actual[key],
        baseline[key],
        `${location}.${key}`,
      );
    }
    return projected;
  }

  return actual;
}

function projectSearchDocumentFingerprint(actual, baseline) {
  if (!isPlainObject(actual)) {
    throw new TypeError('actual search document fingerprint must be a plain object');
  }
  if (!isPlainObject(baseline)) {
    throw new TypeError('baseline search document fingerprint must be a plain object');
  }

  const expectedBaseline = SEARCH_DOCUMENT_FINGERPRINT_TRANSITION.baseline;
  const expectedActual = SEARCH_DOCUMENT_FINGERPRINT_TRANSITION.actual;

  if (canonicalJson(baseline) !== canonicalJson(expectedBaseline)) {
    throw new Error(
      `unexpected baseline search document fingerprint: ${canonicalJson(baseline)}`,
    );
  }
  if (canonicalJson(actual) !== canonicalJson(expectedActual)) {
    throw new Error(
      `unexpected actual search document fingerprint: ${canonicalJson(actual)}`,
    );
  }
  return baseline;
}

function entityKey(row) {
  return `${row?.entity_type || ''}:${row?.entity_id || ''}`;
}

function projectCodeNameEnrichment(
  actual,
  baseline,
  location = 'root',
  inheritedCodeContext = false,
  key = '',
) {
  if (
    inheritedCodeContext
    && key === 'names'
    && Array.isArray(baseline)
  ) {
    if (!Array.isArray(actual)) {
      throw new TypeError(
        `${location}: CODE names actual value must be an array`,
      );
    }
    return baseline;
  }

  if (
    inheritedCodeContext
    && key === 'subtitle'
    && typeof baseline === 'string'
  ) {
    if (typeof actual !== 'string') {
      throw new TypeError(
        `${location}: CODE subtitle actual value must be a string`,
      );
    }
    return baseline;
  }

  if (Array.isArray(baseline)) {
    if (!Array.isArray(actual)) {
      throw new TypeError(
        `${location}: actual value must be an array`,
      );
    }
    if (actual.length !== baseline.length) {
      throw new Error(
        `${location}: array length changed: `
        + `actual=${actual.length}, baseline=${baseline.length}`,
      );
    }
    return baseline.map(
      (baselineItem, index) => projectCodeNameEnrichment(
        actual[index],
        baselineItem,
        `${location}[${index}]`,
        false,
        '',
      ),
    );
  }

  if (isPlainObject(baseline)) {
    if (!isPlainObject(actual)) {
      throw new TypeError(
        `${location}: actual value must be a plain object`,
      );
    }

    const ownCodeContext = (
      baseline.entity_type === 'CODE'
      && actual.entity_type === 'CODE'
      && baseline.entity_id === actual.entity_id
    );
    const activeCodeContext = (
      inheritedCodeContext || ownCodeContext
    );

    const projected = {};
    for (const baselineKey of Object.keys(baseline)) {
      if (!Object.prototype.hasOwnProperty.call(actual, baselineKey)) {
        throw new Error(
          `${location}: actual is missing baseline key: ${baselineKey}`,
        );
      }

      const childCodeContext = (
        activeCodeContext
        && (
          baselineKey === 'summary'
          || baselineKey === 'detail'
          || baselineKey === 'names'
          || baselineKey === 'subtitle'
        )
      );

      projected[baselineKey] = projectCodeNameEnrichment(
        actual[baselineKey],
        baseline[baselineKey],
        `${location}.${baselineKey}`,
        childCodeContext,
        baselineKey,
      );
    }
    return projected;
  }

  return actual;
}

function projectSearchCodeResult(actual, baseline) {
  if (
    actual?.entity_type !== 'CODE'
    || baseline?.entity_type !== 'CODE'
  ) {
    throw new TypeError(
      'search CODE projector requires CODE rows',
    );
  }

  const comparable = {
    ...actual,
    subtitle: baseline.subtitle,
    score: baseline.score,
    match_type: baseline.match_type,
    matched_fields: baseline.matched_fields,
    summary: {
      ...(actual.summary || {}),
      names: baseline.summary?.names || [],
    },
  };

  return projectByBaseline(
    comparable,
    baseline,
    'search-code-item',
  );
}

function collectSearchComparison(
  service,
  query,
  entityType,
  options,
) {
  const results = [];
  let first = null;
  let offset = 0;

  while (true) {
    const page = service.search(
      query,
      entityType,
      {
        ...options,
        limit: 500,
        offset,
      },
    );

    if (!first) first = page;

    if (page.offset !== offset) {
      throw new Error(
        `comparison pagination offset mismatch: `
        + `actual=${page.offset}, expected=${offset}`,
      );
    }

    results.push(...page.results);

    if (!page.has_more) break;

    if (!page.results.length) {
      throw new Error(
        'comparison pagination stalled with has_more=true',
      );
    }

    offset += page.results.length;

    if (offset > page.total_count) {
      throw new Error(
        'comparison pagination exceeded total_count',
      );
    }
  }

  if (!first) {
    throw new Error(
      'comparison pagination produced no response',
    );
  }

  if (results.length !== first.total_count) {
    throw new Error(
      `comparison pagination incomplete: `
      + `results=${results.length}, total=${first.total_count}`,
    );
  }

  return {
    total_count: first.total_count,
    type_counts: first.type_counts,
    results,
  };
}

function projectSearchScenarioByCodeNames(
  actual,
  baseline,
  actualComparison,
) {
  if (!isPlainObject(actual) || !isPlainObject(baseline)) {
    throw new TypeError(
      'search responses must be plain objects',
    );
  }

  if (!isPlainObject(actualComparison)) {
    throw new TypeError(
      'actual full search comparison must be a plain object',
    );
  }

  if (
    actualComparison.results.length
      !== actualComparison.total_count
  ) {
    throw new Error(
      'actual full search comparison is incomplete',
    );
  }

  for (const key of [
    'schema_version',
    'query',
    'normalized_query',
    'filters',
    'offset',
    'limit',
  ]) {
    const projected = projectByBaseline(
      actual[key],
      baseline[key],
      `search.${key}`,
    );

    if (
      canonicalJson(projected)
        !== canonicalJson(baseline[key])
    ) {
      throw new Error(
        `search metadata changed: ${key}`,
      );
    }
  }

  const baselineTypeCounts = baseline.type_counts || {};
  const actualTypeCounts = actualComparison.type_counts || {};
  const typeNames = new Set([
    ...Object.keys(baselineTypeCounts),
    ...Object.keys(actualTypeCounts),
  ]);

  for (const typeName of typeNames) {
    const before = Number(
      baselineTypeCounts[typeName] || 0,
    );
    const after = Number(
      actualTypeCounts[typeName] || 0,
    );

    if (typeName === 'CODE') {
      if (after < before) {
        throw new Error(
          `CODE result count decreased: `
          + `actual=${after}, baseline=${before}`,
        );
      }
    } else if (after !== before) {
      throw new Error(
        `non-CODE result count changed: `
        + `${typeName} actual=${after}, baseline=${before}`,
      );
    }
  }

  const baselineCodeCount = Number(
    baselineTypeCounts.CODE || 0,
  );
  const actualCodeCount = Number(
    actualTypeCounts.CODE || 0,
  );
  const totalDelta = (
    actualComparison.total_count - baseline.total_count
  );
  const codeDelta = (
    actualCodeCount - baselineCodeCount
  );

  if (totalDelta !== codeDelta) {
    throw new Error(
      `search total delta is not CODE-only: `
      + `total_delta=${totalDelta}, code_delta=${codeDelta}`,
    );
  }

  const actualMap = new Map(
    actualComparison.results.map(
      (row) => [entityKey(row), row],
    ),
  );

  if (actualMap.size !== actualComparison.results.length) {
    throw new Error(
      'actual comparison contains duplicate entity keys',
    );
  }

  // Python v2 baseline 전체 deep 결과가 아니라,
  // 기존 parity가 실제로 보증하던 baseline page를 보존한다.
  for (const baselineItem of baseline.results) {
    const key = entityKey(baselineItem);
    const actualItem = actualMap.get(key);

    if (!actualItem) {
      throw new Error(
        `baseline page result disappeared: ${key}`,
      );
    }

    const projected = (
      baselineItem.entity_type === 'CODE'
        ? projectSearchCodeResult(
          actualItem,
          baselineItem,
        )
        : projectByBaseline(
          actualItem,
          baselineItem,
          'baseline-page-non-code-item',
        )
    );

    if (
      canonicalJson(projected)
        !== canonicalJson(baselineItem)
    ) {
      throw new Error(
        `baseline page result changed: ${key}`,
      );
    }
  }

  const expectedHasMore = (
    actual.offset + actual.results.length
      < actual.total_count
  );

  if (actual.has_more !== expectedHasMore) {
    throw new Error(
      'actual has_more is inconsistent',
    );
  }

  return baseline;
}

function projectDetailByCodeNameEnrichment(
  actual,
  baseline,
) {
  return projectCodeNameEnrichment(
    actual,
    baseline,
    'detail',
  );
}

function projectStatusByBaseline(actualStatus, baselineStatus) {
  if (!isPlainObject(actualStatus)) {
    throw new TypeError('actual status must be a plain object');
  }
  if (!isPlainObject(baselineStatus)) {
    throw new TypeError('baseline status must be a plain object');
  }

  const comparableActual = { ...actualStatus };
  for (const [key, transition] of Object.entries(STATUS_TRANSITIONS)) {
    if (!Object.prototype.hasOwnProperty.call(baselineStatus, key)) {
      throw new Error(`baseline status is missing transition key: ${key}`);
    }
    if (baselineStatus[key] !== transition.baseline) {
      throw new Error(
        `unexpected baseline status transition value: ${key}=${baselineStatus[key]}`,
      );
    }
    if (actualStatus[key] !== transition.actual) {
      throw new Error(
        `unexpected actual status transition value: ${key}=${actualStatus[key]}`,
      );
    }
    comparableActual[key] = baselineStatus[key];
  }

  return projectByBaseline(comparableActual, baselineStatus, 'status');
}

function additiveObjectKeys(actual, baseline) {
  if (!isPlainObject(actual) || !isPlainObject(baseline)) {
    return [];
  }
  return Object.keys(actual)
    .filter((key) => !Object.prototype.hasOwnProperty.call(baseline, key))
    .sort();
}

function runSelfTest() {
  const failures = [];
  let passCount = 0;

  function check(name, actual, expected) {
    if (canonicalJson(actual) === canonicalJson(expected)) passCount += 1;
    else failures.push({ name, actual, expected });
  }

  function detectsError(name, fn, expectedPattern) {
    let detected = false;
    try {
      fn();
    } catch (error) {
      detected = expectedPattern.test(String(error.message));
    }
    check(name, detected, true);
  }

  const nestedBaseline = {
    result: {
      id: 'E011',
      summary: {
        count: 3,
        labels: ['A', 'B'],
      },
    },
  };
  const nestedAdditive = {
    result: {
      id: 'E011',
      summary: {
        count: 3,
        labels: ['A', 'B'],
        user_condition_status: 'RESOLVED_AST',
      },
      user_condition_table_count: 3,
    },
    schema_version: 'response-v1',
  };

  check(
    'nested additive fields accepted',
    projectByBaseline(nestedAdditive, nestedBaseline),
    nestedBaseline,
  );

  detectsError(
    'missing baseline key detected',
    () => projectByBaseline(
      { result: { id: 'E011', summary: { labels: ['A', 'B'] } } },
      nestedBaseline,
    ),
    /missing baseline key: count/,
  );

  check(
    'changed baseline value remains detectable',
    canonicalJson(projectByBaseline(
      {
        result: {
          id: 'E012',
          summary: { count: 3, labels: ['A', 'B'] },
        },
      },
      nestedBaseline,
    )) !== canonicalJson(nestedBaseline),
    true,
  );

  check(
    'array order change remains detectable',
    canonicalJson(projectByBaseline(
      {
        result: {
          id: 'E011',
          summary: { count: 3, labels: ['B', 'A'] },
        },
      },
      nestedBaseline,
    )) !== canonicalJson(nestedBaseline),
    true,
  );

  detectsError(
    'array length change detected',
    () => projectByBaseline(
      {
        result: {
          id: 'E011',
          summary: { count: 3, labels: ['A', 'B', 'C'] },
        },
      },
      nestedBaseline,
    ),
    /array length changed/,
  );

  const statusBaseline = {
    ready: true,
    data_schema_version: STATUS_TRANSITIONS.data_schema_version.baseline,
    data_state: STATUS_TRANSITIONS.data_state.baseline,
    policies: {
      abc_exact_match_only: true,
    },
  };
  const statusActual = {
    ready: true,
    data_schema_version: STATUS_TRANSITIONS.data_schema_version.actual,
    data_state: STATUS_TRANSITIONS.data_state.actual,
    policies: {
      abc_exact_match_only: true,
      user_condition_display_separated_from_source_provenance: true,
    },
    relation_response_schema_version: 'relation-v1',
  };

  check(
    'allowed status transition accepted',
    projectStatusByBaseline(statusActual, statusBaseline),
    statusBaseline,
  );

  detectsError(
    'unexpected schema transition rejected',
    () => projectStatusByBaseline(
      { ...statusActual, data_schema_version: 'unexpected-v4' },
      statusBaseline,
    ),
    /unexpected actual status transition value/,
  );

  detectsError(
    'unexpected data state transition rejected',
    () => projectStatusByBaseline(
      { ...statusActual, data_state: 'unexpected-state' },
      statusBaseline,
    ),
    /unexpected actual status transition value/,
  );

  detectsError(
    'missing baseline policy rejected',
    () => projectStatusByBaseline(
      { ...statusActual, policies: {} },
      statusBaseline,
    ),
    /missing baseline key: abc_exact_match_only/,
  );

  check(
    'top-level additive status field reported',
    additiveObjectKeys(statusActual, statusBaseline),
    ['relation_response_schema_version'],
  );

  check(
    'allowed search fingerprint transition accepted',
    projectSearchDocumentFingerprint(
      SEARCH_DOCUMENT_FINGERPRINT_TRANSITION.actual,
      SEARCH_DOCUMENT_FINGERPRINT_TRANSITION.baseline,
    ),
    SEARCH_DOCUMENT_FINGERPRINT_TRANSITION.baseline,
  );

  detectsError(
    'unexpected baseline search fingerprint rejected',
    () => projectSearchDocumentFingerprint(
      SEARCH_DOCUMENT_FINGERPRINT_TRANSITION.actual,
      {
        ...SEARCH_DOCUMENT_FINGERPRINT_TRANSITION.baseline,
        sha256: '0'.repeat(64),
      },
    ),
    /unexpected baseline search document fingerprint/,
  );

  detectsError(
    'unexpected actual search fingerprint rejected',
    () => projectSearchDocumentFingerprint(
      {
        ...SEARCH_DOCUMENT_FINGERPRINT_TRANSITION.actual,
        sha256: 'f'.repeat(64),
      },
      SEARCH_DOCUMENT_FINGERPRINT_TRANSITION.baseline,
    ),
    /unexpected actual search document fingerprint/,
  );

  detectsError(
    'search fingerprint count change rejected',
    () => projectSearchDocumentFingerprint(
      {
        ...SEARCH_DOCUMENT_FINGERPRINT_TRANSITION.actual,
        count: 22944,
      },
      SEARCH_DOCUMENT_FINGERPRINT_TRANSITION.baseline,
    ),
    /unexpected actual search document fingerprint/,
  );

  const searchBaseline = {
    schema_version: 'search-v1',
    query: 'sample',
    normalized_query: 'sample',
    filters: {
      classification: null,
      entity_types: ['CODE', 'ADRG'],
      mdc: null,
    },
    offset: 0,
    limit: 2,
    has_more: false,
    total_count: 2,
    type_counts: {
      ADRG: 1,
      CODE: 1,
    },
    results: [
      {
        entity_type: 'ADRG',
        entity_id: '9600',
        title: '9600',
        subtitle: 'A',
        score: 920,
        match_type: 'EXACT_TEXT',
        matched_fields: ['classification'],
        summary: { mdc: 'PRE' },
      },
      {
        entity_type: 'CODE',
        entity_id: 'A010',
        title: 'A010',
        subtitle: '',
        score: 500,
        match_type: 'ANY_TOKEN',
        matched_fields: ['text'],
        summary: {
          names: [],
          logical_table_count: 1,
        },
      },
    ],
  };

  const searchActual = {
    ...searchBaseline,
    has_more: true,
    total_count: 3,
    type_counts: {
      ADRG: 1,
      CODE: 2,
    },
    results: [
      {
        entity_type: 'CODE',
        entity_id: 'B020',
        title: 'B020',
        subtitle: '신규 코드명',
        score: 920,
        match_type: 'EXACT_TEXT',
        matched_fields: ['name'],
        summary: {
          names: ['신규 코드명'],
          logical_table_count: 1,
        },
      },
      searchBaseline.results[0],
    ],
  };

  const actualComparison = {
    total_count: 3,
    type_counts: {
      ADRG: 1,
      CODE: 2,
    },
    results: [
      searchActual.results[0],
      searchActual.results[1],
      {
        entity_type: 'CODE',
        entity_id: 'A010',
        title: 'A010',
        subtitle: '기존 코드명',
        score: 920,
        match_type: 'EXACT_TEXT',
        matched_fields: ['name'],
        summary: {
          names: ['기존 코드명'],
          logical_table_count: 1,
        },
      },
    ],
  };

  check(
    'additive CODE-name search accepted',
    projectSearchScenarioByCodeNames(
      searchActual,
      searchBaseline,
      actualComparison,
    ),
    searchBaseline,
  );

  detectsError(
    'additive non-CODE count rejected',
    () => projectSearchScenarioByCodeNames(
      {
        ...searchActual,
        total_count: 4,
        type_counts: {
          ADRG: 2,
          CODE: 2,
        },
      },
      searchBaseline,
      {
        total_count: 4,
        type_counts: {
          ADRG: 2,
          CODE: 2,
        },
        results: [
          ...actualComparison.results,
          {
            entity_type: 'ADRG',
            entity_id: '9700',
          },
        ],
      },
    ),
    /non-CODE result count changed/,
  );

  detectsError(
    'baseline page result disappearance rejected',
    () => projectSearchScenarioByCodeNames(
      {
        ...searchActual,
        total_count: 2,
        type_counts: {
          ADRG: 1,
          CODE: 1,
        },
      },
      searchBaseline,
      {
        total_count: 2,
        type_counts: {
          ADRG: 1,
          CODE: 1,
        },
        results: actualComparison.results.filter(
          (row) => row.entity_id !== 'A010',
        ),
      },
    ),
    /baseline page result disappeared/,
  );

  check(
    'nested TABLE CODE names enrichment accepted',
    projectDetailByCodeNameEnrichment(
      {
        entity_type: 'TABLE',
        entity_id: 'LT_SAMPLE',
        detail: {
          code_records: [
            {
              entity_type: 'CODE',
              entity_id: 'A010',
              subtitle: '공식명',
              summary: {
                names: ['공식명', 'Official name'],
                logical_table_count: 1,
              },
            },
          ],
        },
      },
      {
        entity_type: 'TABLE',
        entity_id: 'LT_SAMPLE',
        detail: {
          code_records: [
            {
              entity_type: 'CODE',
              entity_id: 'A010',
              subtitle: '코드명 원천 미수록',
              summary: {
                names: [],
                logical_table_count: 1,
              },
            },
          ],
        },
      },
    ),
    {
      entity_type: 'TABLE',
      entity_id: 'LT_SAMPLE',
      detail: {
        code_records: [
          {
            entity_type: 'CODE',
            entity_id: 'A010',
            subtitle: '코드명 원천 미수록',
            summary: {
              names: [],
              logical_table_count: 1,
            },
          },
        ],
      },
    },
  );

  console.log(`validator=${SCRIPT_VERSION}`);
  if (failures.length) {
    console.log(
      `[FAIL] Python-JavaScript recursive subset parity self-test: `
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
      `[PASS] Python-JavaScript recursive subset parity self-test: `
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

  function checkProjected(name, actual, expected, projector = projectByBaseline) {
    try {
      const projected = projector(actual, expected);
      if (canonicalJson(projected) === canonicalJson(expected)) passCount += 1;
      else failures.push({ name, actual: projected, expected });
    } catch (error) {
      failures.push({
        name,
        actual: `${error.name}: ${error.message}`,
        expected,
      });
    }
  }

  const status = service.status();
  delete status.data_path;

  checkProjected(
    'status baseline contract',
    status,
    baseline.status,
    projectStatusByBaseline,
  );

  const additiveKeys = additiveObjectKeys(status, baseline.status);

  checkProjected(
    'search document fingerprint transition',
    service.debugSearchDocumentFingerprint(),
    baseline.search_document_fingerprint,
    projectSearchDocumentFingerprint,
  );
  checkProjected(
    'semantic context fingerprint',
    service.debugSemanticContextFingerprint(),
    baseline.semantic_context_fingerprint,
  );
  checkProjected(
    'exact ID audit',
    service.debugExactIdAudit(),
    baseline.exact_id_audit,
  );

  for (const scenario of baseline.search_scenarios) {
    const actual = service.search(
      scenario.request.query,
      scenario.request.entity_type,
      scenario.request.options,
    );

    const actualComparison = collectSearchComparison(
      service,
      scenario.request.query,
      scenario.request.entity_type,
      scenario.request.options,
    );

    checkProjected(
      `search:${scenario.name}`,
      actual,
      scenario.response,
      (actualValue, expectedValue) => projectSearchScenarioByCodeNames(
        actualValue,
        expectedValue,
        actualComparison,
      ),
    );
  }

  for (const scenario of baseline.detail_scenarios) {
    const actual = service.getDetail(
      scenario.request.entity_type,
      scenario.request.entity_id,
    );

    checkProjected(
      `detail:${scenario.name}`,
      actual,
      scenario.response,
      projectDetailByCodeNameEnrichment,
    );
  }

  console.log(`validator=${SCRIPT_VERSION}`);
  console.log(`node=${process.version}`);
  console.log(`baseline=${path.resolve(baselinePath)}`);
  console.log(
    `status_additive_keys=${additiveKeys.length ? additiveKeys.join(',') : 'none'}`,
  );
  console.log(
    `search_document_fingerprint_transition=`
    + `${SEARCH_DOCUMENT_FINGERPRINT_TRANSITION.baseline.sha256}`
    + `->${SEARCH_DOCUMENT_FINGERPRINT_TRANSITION.actual.sha256}`,
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
