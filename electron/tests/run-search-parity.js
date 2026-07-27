'use strict';

const fs = require('node:fs');
const path = require('node:path');
const {
  KdrgSearchService,
  canonicalJson,
} = require('../src/kdrg-search-service');

function fail(message) {
  console.error(`[FAIL] ${message}`);
  process.exit(1);
}

const baselinePath = process.argv[2];
const dataPath = process.argv[3];
if (!baselinePath || !dataPath) {
  fail('사용법: node run-search-parity.js <baseline.json> <integrated.json>');
}

const baseline = JSON.parse(fs.readFileSync(path.resolve(baselinePath), 'utf8'));
const service = new KdrgSearchService(path.resolve(dataPath));
const failures = [];
let passCount = 0;

function check(name, actual, expected) {
  if (canonicalJson(actual) === canonicalJson(expected)) passCount += 1;
  else failures.push({ name, actual, expected });
}

const status = service.status();
delete status.data_path;
check('status', status, baseline.status);
check('search document fingerprint', service.debugSearchDocumentFingerprint(), baseline.search_document_fingerprint);
check('semantic context fingerprint', service.debugSemanticContextFingerprint(), baseline.semantic_context_fingerprint);
check('exact ID audit', service.debugExactIdAudit(), baseline.exact_id_audit);

for (const scenario of baseline.search_scenarios) {
  const actual = service.search(scenario.request.query, scenario.request.entity_type, scenario.request.options);
  check(`search:${scenario.name}`, actual, scenario.response);
}
for (const scenario of baseline.detail_scenarios) {
  const actual = service.getDetail(scenario.request.entity_type, scenario.request.entity_id);
  check(`detail:${scenario.name}`, actual, scenario.response);
}

console.log('validator=2026-07-27_KDRG_V47_ELECTRON_STAGE50B_PARITY_RUNNER_V1');
console.log(`node=${process.version}`);
console.log(`baseline=${path.resolve(baselinePath)}`);
if (failures.length) {
  console.log(`[FAIL] Python-JavaScript 검색 동등성: ${passCount} PASS / ${failures.length} FAIL`);
  console.log('[FAIL 상세]');
  for (const item of failures.slice(0, 20)) {
    console.log(`- ${item.name}`);
    console.log(`  actual=${canonicalJson(item.actual).slice(0, 2000)}`);
    console.log(`  expected=${canonicalJson(item.expected).slice(0, 2000)}`);
  }
  process.exitCode = 1;
} else {
  console.log(`[PASS] Python-JavaScript 검색 동등성: ${passCount} PASS / 0 FAIL`);
}
