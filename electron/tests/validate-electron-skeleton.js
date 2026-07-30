'use strict';

const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const { buildBootstrapSnapshot } = require('../src/bootstrap-data');
const { resolveDataDirectory, resolveDataFiles } = require('../src/data-paths');

const ELECTRON_ROOT = path.resolve(__dirname, '..');
const REPO_ROOT = path.resolve(ELECTRON_ROOT, '..');
const failures = [];
let passCount = 0;

function check(name, actual, expected, predicate = (a, e) => a === e) {
  const passed = Boolean(predicate(actual, expected));
  if (passed) {
    passCount += 1;
  } else {
    failures.push({ name, actual, expected });
  }
  return passed;
}

function sha256(filePath) {
  return crypto.createHash('sha256').update(fs.readFileSync(filePath)).digest('hex');
}

function read(filePath) {
  return fs.readFileSync(filePath, 'utf8');
}

const requiredFiles = [
  'package.json',
  '.gitignore',
  'main.js',
  'preload.js',
  'src/data-paths.js',
  'src/bootstrap-data.js',
  'renderer/index.html',
  'renderer/app.js',
  'renderer/styles.css',
  'renderer/ui-formatters.js',
  'tests/validate-electron-skeleton.js',
  'tests/validate-renderer-ui.js',
  'README_STAGE50A.md',
  'README_STAGE50B.md',
  'README_STAGE50C.md',
];
for (const relativePath of requiredFiles) {
  check(`필수 파일 ${relativePath}`, fs.existsSync(path.join(ELECTRON_ROOT, relativePath)), true);
}

const packageJson = JSON.parse(read(path.join(ELECTRON_ROOT, 'package.json')));
check('package name', packageJson.name, 'kdrg-v47-relation-search-electron');
check('package version', packageJson.version, '0.3.0-dev.0');
check('package main', packageJson.main, 'main.js');
check('Electron pin', packageJson.devDependencies.electron, '43.2.0');
check('Node engine', packageJson.engines.node, '>=22.0.0');
check('start script', packageJson.scripts.start, 'electron .');
check('validate skeleton script', packageJson.scripts['validate:skeleton'], 'node tests/validate-electron-skeleton.js');
check('validate search script', packageJson.scripts['validate:search'], 'node tests/validate-search-service.js');
check('validate UI script', packageJson.scripts['validate:ui'], 'node tests/validate-renderer-ui.js');
check('validate smoke contract script', packageJson.scripts['validate:smoke-contract'], 'node tests/validate-packaged-runtime-smoke.js');
check('validate packaging script', packageJson.scripts['validate:packaging'], 'node tests/validate-packaging-config.js');

const aggregateScript = String(packageJson.scripts.validate || '');
const aggregateStages = [
  'validate:skeleton',
  'validate:search',
  'validate:ui',
  'validate:smoke-contract',
  'validate:packaging',
];
for (const stage of aggregateStages) {
  const token = `npm run ${stage}`;
  const occurrences = aggregateScript.split(token).length - 1;
  check(`validate aggregate ${stage} 단일 포함`, occurrences, 1);
}
const aggregatePositions = aggregateStages.map((stage) => aggregateScript.indexOf(`npm run ${stage}`));
check(
  'validate aggregate 단계 순서',
  aggregatePositions,
  aggregateStages,
  (positions) => positions.every((position) => position >= 0)
    && positions.every((position, index) => index === 0 || positions[index - 1] < position),
);
check('repository', packageJson.repository.url, 'https://github.com/hamidong/kdrg-v47-relation-search.git');

const mainSource = read(path.join(ELECTRON_ROOT, 'main.js'));
const preloadSource = read(path.join(ELECTRON_ROOT, 'preload.js'));
const htmlSource = read(path.join(ELECTRON_ROOT, 'renderer/index.html'));
const rendererSource = read(path.join(ELECTRON_ROOT, 'renderer/app.js'));
const formatterSource = read(path.join(ELECTRON_ROOT, 'renderer/ui-formatters.js'));

check('contextIsolation 활성', mainSource.includes('contextIsolation: true'), true);
check('nodeIntegration 비활성', mainSource.includes('nodeIntegration: false'), true);
check('sandbox 활성', mainSource.includes('sandbox: true'), true);
check('새 창 차단', mainSource.includes("setWindowOpenHandler(() => ({ action: 'deny' }))"), true);
check('외부 이동 차단', mainSource.includes("on('will-navigate'"), true);
check('단일 인스턴스', mainSource.includes('requestSingleInstanceLock'), true);
check('preload contextBridge', preloadSource.includes('contextBridge.exposeInMainWorld'), true);
check('ipcRenderer 직접 노출 금지', preloadSource.includes('ipcRenderer,'), false);
check('bootstrap IPC 채널', (preloadSource.match(/kdrg:get-bootstrap-snapshot/g) || []).length, 1);
check('search IPC 채널', (preloadSource.match(/kdrg:search/g) || []).length, 1);
check('detail IPC 채널', (preloadSource.match(/kdrg:get-detail/g) || []).length, 1);
check('status IPC 채널', (preloadSource.match(/kdrg:get-search-status/g) || []).length, 1);
check('CSP 존재', htmlSource.includes('Content-Security-Policy'), true);
check('connect-src none', htmlSource.includes("connect-src 'none'"), true);
check('inline script 없음', htmlSource.includes('<script>'), false);
check('renderer require 없음', rendererSource.includes('require('), false);
check('동적 데이터 textContent', rendererSource.includes('textContent'), true);
check('동적 데이터 innerHTML 미사용', rendererSource.includes('innerHTML'), false);
check('renderer eval 미사용', /\beval\s*\(/.test(rendererSource), false);
check('formatter require 없음', formatterSource.includes('require('), false);
check('formatter 선로드', htmlSource.indexOf('ui-formatters.js') < htmlSource.indexOf('app.js'), true);
check('검색 form 존재', htmlSource.includes('id="search-form"'), true);
check('상세 panel 존재', htmlSource.includes('id="detail-content"'), true);

const dataDirectory = resolveDataDirectory({
  isPackaged: false,
  resourcesPath: null,
  moduleDirectory: path.join(ELECTRON_ROOT, 'src'),
});
check('개발 데이터 경로', dataDirectory, path.join(REPO_ROOT, 'data'));

const dataFiles = resolveDataFiles({
  isPackaged: false,
  resourcesPath: null,
  moduleDirectory: path.join(ELECTRON_ROOT, 'src'),
});
check('통합 JSON SHA256', sha256(dataFiles.integrated), '3de5d6d95cd9cbd16e674f5a4cffcd8bf89da2ee70627501f56d81b05bbe8af1');
check('semantic profile SHA256', sha256(dataFiles.semanticProfile), 'c9401fd9d6dcc1253fa2134b22048fe4a73c4c04aeea4d1d86c7fe1504d5456e');
check('display contract SHA256', sha256(dataFiles.displayContract), '9976307acd77bb6a0c8a48b2788d055faf563d497381b2c2cacfc7435df0f1ac');

const snapshot = buildBootstrapSnapshot(dataFiles);
check('snapshot status', snapshot.status, 'ready');
check('ADRG count', snapshot.counts.adrg, 1132);
check('AADRG count', snapshot.counts.aadrg, 1233);
check('RDRG count', snapshot.counts.rdrg, 2699);
check('TABLE count', snapshot.counts.tables, 1308);
check('code count', snapshot.counts.codes, 16571);
check('AST count', snapshot.counts.conditionAst, 390);
check('condition occurrence count', snapshot.counts.conditionTableOccurrences, 939);
check('include occurrence count', snapshot.displayContract.includeOccurrences, 874);
check('exclude occurrence count', snapshot.displayContract.excludeOccurrences, 65);
check('unknown TABLE count', snapshot.displayContract.unknownTableCount, 646);
check('raw corpus 미노출', snapshot.capabilities.rawCorpusExposedToRenderer, false);
check('검색 서비스 연결 표시', snapshot.capabilities.searchServiceConnected, true);
check('50D stage', snapshot.capabilities.stage, '50D_ELECTRON_WINDOWS_PACKAGE_READY');
check('50E next stage', snapshot.capabilities.nextStage, '50E_PREVIEW_RELEASE_AND_UI_REVIEW');

const serialized = JSON.stringify(snapshot);
check('원본 ADRG 배열 미포함', serialized.includes('adrg_records'), false);
check('원본 code 배열 미포함', serialized.includes('code_records'), false);
check('bootstrap snapshot 크기 제한', Buffer.byteLength(serialized, 'utf8') < 20000, true);

console.log(`validator=2026-07-30_KDRG_V47_ELECTRON_STAGE50C_SKELETON_VALIDATOR_V2_AGGREGATE_CONTRACT`);
console.log(`electron_root=${ELECTRON_ROOT}`);
console.log(`node=${process.version}`);
if (failures.length) {
  console.log(`[FAIL] Electron Stage 50C 보안 골격 검증: ${passCount} PASS / ${failures.length} FAIL`);
  console.log('[FAIL 상세]');
  for (const item of failures) {
    console.log(`- ${item.name} | actual=${JSON.stringify(item.actual)} | expected=${JSON.stringify(item.expected)}`);
  }
  process.exitCode = 1;
} else {
  console.log(`[PASS] Electron Stage 50C 보안 골격 검증: ${passCount} PASS / 0 FAIL`);
}
