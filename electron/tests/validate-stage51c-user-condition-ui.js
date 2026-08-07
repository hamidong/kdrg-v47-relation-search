#!/usr/bin/env node
'use strict';
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const { DATA_FILES, resolveDataFiles } = require('../src/data-paths');
const { buildBootstrapSnapshot } = require('../src/bootstrap-data');
const { KdrgSearchService } = require('../src/kdrg-search-service');
const EXPECTED_SHA = '3f602e08374cb139f74efc5c935a124c560e2802935567f682b69d1ea5d951ce';
const ROOT = path.resolve(__dirname, '..');
const failures = [];
let passes = 0;
function check(name, fn) { try { fn(); passes += 1; } catch (e) { failures.push(`${name}: ${e.message}`); } }
function sha(file) { return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex'); }
const files = resolveDataFiles({ isPackaged: false, resourcesPath: null, moduleDirectory: path.join(ROOT, 'src') });
const service = new KdrgSearchService(files.integrated);
const app = fs.readFileSync(path.join(ROOT, 'renderer', 'app.js'), 'utf8');
const fmt = fs.readFileSync(path.join(ROOT, 'renderer', 'ui-formatters.js'), 'utf8');
const currentReadme = fs.readFileSync(path.join(ROOT, 'README_STAGE51C.md'), 'utf8');
const byteValidator = fs.readFileSync(
  path.join(ROOT, 'scripts', 'validate-checkout-byte-integrity.py'),
  'utf8',
);
const pkg = JSON.parse(fs.readFileSync(path.join(ROOT, 'package.json'), 'utf8'));
check('runtime file', () => assert.equal(DATA_FILES.integrated, 'kdrg_v47_search_integrated_v3.json'));
check('runtime SHA', () => assert.equal(sha(files.integrated), EXPECTED_SHA));
check('runtime schema', () => assert.equal(service.status().data_schema_version, 'kdrg-v47-search-integrated-v3'));
const bootstrap = buildBootstrapSnapshot(files);
check('bootstrap stage', () => assert.equal(bootstrap.capabilities.stage, '51C_USER_CONDITION_UI_READY'));
check('bootstrap nextStage', () => assert.equal(bootstrap.capabilities.nextStage, '51D_WINDOWS_PACKAGE_AND_UI_REVIEW'));
check('ADRG count', () => assert.equal(service.status().counts.adrg_records, 1132));
check('CODE count', () => assert.equal(service.status().counts.unique_search_codes, 16571));
const ids = (adrg) => service.getDetail('ADRG', adrg).detail.user_condition_tables.map((x) => x.entity_id);
check('B013 table2', () => assert.deepEqual(ids('B013'), ['LT_B018_002']));
check('B014 table3', () => assert.deepEqual(ids('B014'), ['LT_B018_003']));
check('B018 table1·4·5', () => assert.deepEqual(ids('B018'), ['LT_B018_001', 'LT_B018_004', 'LT_B018_005']));
check('B018 table2·3 hidden', () => assert.ok(!ids('B018').some((x) => ['LT_B018_002', 'LT_B018_003'].includes(x))));
check('B022 no guessed table', () => assert.deepEqual(ids('B022'), []));
check('L033 no guessed table', () => assert.deepEqual(ids('L033'), []));
check('9610 no guessed table', () => assert.deepEqual(ids('9610'), []));
check('B022 text', () => assert.equal(service.getDetail('ADRG', 'B022').detail.user_condition_text, '시술명 table2'));
check('L033 text', () => assert.equal(service.getDetail('ADRG', 'L033').detail.user_condition_text, '시술명 table1'));
check('9610 status', () => assert.equal(service.getDetail('ADRG', '9610').detail.user_condition_status, 'NO_EXPLICIT_CONDITION'));
check('new sections', () => { assert.match(app, /'분류 조건'/); assert.match(app, /'조건 상세'/); assert.match(app, /'원문 근거'/); });
check('old sections removed', () => { assert.doesNotMatch(app, /기본 분류 TABLE/); assert.doesNotMatch(app, /추가 분기조건/); });
check('inline table kept', () => assert.match(app, /async function loadInlineTable/));
check('formatter contract', () => assert.match(fmt, /function userConditionCoverage/));
check('package resource', () => assert.ok(pkg.build.extraResources.some((x) => x.from === '../data/kdrg_v47_search_integrated_v3.json' && x.to === 'data/kdrg_v47_search_integrated_v3.json')));
check('package validator', () => assert.match(pkg.scripts.validate, /validate:stage51c/));
check('Stage 51C README title', () => assert.match(currentReadme, /^# Stage 51C/));
check('Stage 51C public filters', () => assert.match(currentReadme, /전체·코드·ADRG/));
check('Stage 51C detail sections', () => {
  assert.match(currentReadme, /`분류 조건`/);
  assert.match(currentReadme, /`조건 상세`/);
  assert.match(currentReadme, /`원문 근거`/);
});
check('Stage 51C README old UI absent', () => {
  assert.doesNotMatch(currentReadme, /ADRG 기본 분류 TABLE/);
  assert.doesNotMatch(currentReadme, /ADRG 추가 분기조건/);
});
check('byte validator v3 file', () => assert.match(byteValidator, /data\/kdrg_v47_search_integrated_v3\.json/));
check('byte validator v3 SHA', () => assert.match(byteValidator, /3f602e08374cb139f74efc5c935a124c560e2802935567f682b69d1ea5d951ce/));
check('byte validator old runtime removed', () => assert.doesNotMatch(byteValidator, /data\/kdrg_v47_search_integrated\.json/));
console.log(`sha256=${sha(files.integrated)}`);
if (failures.length) { console.log(`[FAIL] Electron Stage 51C 독립검증: ${passes} PASS / ${failures.length} FAIL`); failures.forEach((x) => console.log(`- ${x}`)); process.exitCode = 1; }
else console.log(`[PASS] Electron Stage 51C 독립검증: ${passes} PASS / 0 FAIL`);
