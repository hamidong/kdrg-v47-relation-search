'use strict';

const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

const VALIDATOR_VERSION =
  '2026-07-27_KDRG_V47_ELECTRON_STAGE50D_PACKAGING_VALIDATOR_V1';
const ELECTRON_ROOT = path.resolve(__dirname, '..');
const ROOT = path.resolve(ELECTRON_ROOT, '..');

const EXPECTED_DATA = Object.freeze({
  'kdrg_v47_search_integrated.json':
    '3de5d6d95cd9cbd16e674f5a4cffcd8bf89da2ee70627501f56d81b05bbe8af1',
  'kdrg_v47_ui_semantic_profile.json':
    'c9401fd9d6dcc1253fa2134b22048fe4a73c4c04aeea4d1d86c7fe1504d5456e',
  'kdrg_v47_ui_display_contract.json':
    '9976307acd77bb6a0c8a48b2788d055faf563d497381b2c2cacfc7435df0f1ac',
});

const checks = [];
function check(name, actual, expected, predicate = (value, target) => value === target) {
  const passed = Boolean(predicate(actual, expected));
  checks.push({ name, actual, expected, passed });
  return passed;
}
function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}
function sha256(filePath) {
  return crypto.createHash('sha256').update(fs.readFileSync(filePath)).digest('hex');
}
function includesAll(value, required) {
  return required.every((item) => value.includes(item));
}
function main() {
  const packagePath = path.join(ELECTRON_ROOT, 'package.json');
  const lockPath = path.join(ELECTRON_ROOT, 'package-lock.json');
  const workflowPath = path.join(ROOT, '.github', 'workflows', 'build-electron-windows.yml');
  const smokeSourcePath = path.join(ELECTRON_ROOT, 'src', 'packaged-runtime-smoke.js');
  const verifyScriptPath = path.join(ELECTRON_ROOT, 'scripts', 'verify-windows-portable.ps1');

  for (const filePath of [packagePath, lockPath, workflowPath, smokeSourcePath, verifyScriptPath]) {
    check(`필수 파일 존재 ${path.relative(ROOT, filePath)}`, fs.existsSync(filePath), true);
  }

  const packageJson = readJson(packagePath);
  const lockJson = readJson(lockPath);
  const build = packageJson.build || {};
  const scripts = packageJson.scripts || {};
  const devDependencies = packageJson.devDependencies || {};

  check('package version', packageJson.version, '0.3.0-dev.0');
  check('Electron pin', devDependencies.electron, '43.2.0');
  check('electron-builder pin', devDependencies['electron-builder'], '26.15.3');
  check('Node engine', packageJson.engines?.node, '>=22.0.0');
  check('validate:packaging script', scripts['validate:packaging'], 'node tests/validate-packaging-config.js');
  check('dist:win script', scripts['dist:win'], 'electron-builder --win portable --x64 --publish never');
  check('check script packaging 포함', scripts.check || '', 'validate-packaging-config.js', (value, target) => value.includes(target));

  check('build appId', build.appId, 'kr.kdrg.v47.relationsearch');
  check('build productName', build.productName, 'KDRG V4.7 관계 검색기');
  check('build artifactName', build.artifactName, 'KDRG_V47_Relation_Search_Electron_${version}_Portable.${ext}');
  check('build asar', build.asar, true);
  check('build compression', build.compression, 'maximum');
  check('build npmRebuild', build.npmRebuild, false);
  check('build output', build.directories?.output, 'dist');
  check('build files 최소구성', build.files || [], ['main.js', 'preload.js', 'renderer/**/*', 'src/**/*', 'package.json'], (value, required) => includesAll(value, required));
  check('tests package 제외', build.files || [], '!tests/**/*', (value, required) => value.includes(required));

  const resources = build.extraResources || [];
  check('extraResources 수', resources.length, 3);
  for (const fileName of Object.keys(EXPECTED_DATA)) {
    const item = resources.find((entry) => entry.to === `data/${fileName}`);
    check(`extraResources ${fileName}`, Boolean(item), true);
    if (item) check(`extraResources from ${fileName}`, item.from, `../data/${fileName}`);
    const dataPath = path.join(ROOT, 'data', fileName);
    check(`원본 데이터 존재 ${fileName}`, fs.existsSync(dataPath), true);
    if (fs.existsSync(dataPath)) check(`원본 데이터 SHA256 ${fileName}`, sha256(dataPath), EXPECTED_DATA[fileName]);
  }

  check('Windows target portable', build.win?.target?.[0]?.target, 'portable');
  check('Windows target x64', build.win?.target?.[0]?.arch?.[0], 'x64');
  check('Windows executableName', build.win?.executableName, 'KDRG_V47_Relation_Search_Electron');
  check('Windows requestedExecutionLevel', build.win?.requestedExecutionLevel, 'asInvoker');

  check('lockfileVersion', lockJson.lockfileVersion, 3);
  check('lock root name', lockJson.name, packageJson.name);
  check('lock root version', lockJson.version, packageJson.version);
  check('lock root Electron pin', lockJson.packages?.['']?.devDependencies?.electron, '43.2.0');
  check('lock root electron-builder pin', lockJson.packages?.['']?.devDependencies?.['electron-builder'], '26.15.3');
  check('lock resolved Electron version', lockJson.packages?.['node_modules/electron']?.version, '43.2.0');
  check('lock resolved electron-builder version', lockJson.packages?.['node_modules/electron-builder']?.version, '26.15.3');

  const mainSource = fs.readFileSync(path.join(ELECTRON_ROOT, 'main.js'), 'utf8');
  const smokeSource = fs.readFileSync(smokeSourcePath, 'utf8');
  check('main smoke import', mainSource.includes("require('./src/packaged-runtime-smoke')"), true);
  check('main smoke 실행', mainSource.includes('runPackagedRuntimeSmoke({'), true);
  check('smoke app.isPackaged 기록', smokeSource.includes('app_is_packaged: app.isPackaged'), true);
  check('smoke 데이터 경로 검사', smokeSource.includes('resolveDataFiles({'), true);
  check('smoke E011 검색', smokeSource.includes("service.search('E011'"), true);
  check('smoke renderer load', smokeSource.includes('did-finish-load'), true);
  check('smoke renderer 보안 contextIsolation', smokeSource.includes('contextIsolation: true'), true);
  check('smoke renderer 보안 nodeIntegration', smokeSource.includes('nodeIntegration: false'), true);
  check('smoke renderer 보안 sandbox', smokeSource.includes('sandbox: true'), true);

  const workflow = fs.readFileSync(workflowPath, 'utf8');
  check('workflow Windows runner', workflow.includes('runs-on: windows-latest'), true);
  check('workflow Node 22.23.1', workflow.includes('node-version: "22.23.1"'), true);
  check('workflow npm cache', workflow.includes('cache: npm'), true);
  check('workflow npm ci', workflow.includes('npm ci --no-audit --no-fund'), true);
  check('workflow Python 50D 검증', workflow.includes('50D_validate_kdrg_electron_windows_packaging.py'), true);
  check('workflow portable build', workflow.includes('npm run dist:win'), true);
  check('workflow packaged smoke', workflow.includes('verify-windows-portable.ps1'), true);
  check('workflow tag namespace', workflow.includes('electron-v*'), true);
  check('workflow Release Asset', workflow.includes('softprops/action-gh-release@v2'), true);
  check('workflow Actions artifact 미사용', workflow.includes('actions/upload-artifact'), false);
  check('workflow PySide workflow 비변경', fs.existsSync(path.join(ROOT, '.github', 'workflows', 'build-windows-release.yml')), true);

  const verifySource = fs.readFileSync(verifyScriptPath, 'utf8');
  check('PowerShell exe 크기 검사', verifySource.includes('$MinimumBytes'), true);
  check('PowerShell smoke report env', verifySource.includes('KDRG_ELECTRON_SMOKE_REPORT'), true);
  check('PowerShell 종료코드 검사', verifySource.includes('$process.ExitCode'), true);
  check('PowerShell PASS 상태 검사', verifySource.includes('$report.status -ne "PASS"'), true);
  check('PowerShell packaged 검사', verifySource.includes('$report.app_is_packaged -ne $true'), true);
  check('PowerShell count 검사', verifySource.includes('$report.counts.adrg -ne 1132'), true);

  const failures = checks.filter((item) => !item.passed);
  if (failures.length) {
    console.log(`[FAIL] Electron Stage 50D Windows packaging 검증: ${checks.length - failures.length} PASS / ${failures.length} FAIL`);
    for (const failure of failures) {
      console.log(`- ${failure.name} | actual=${JSON.stringify(failure.actual)} | expected=${JSON.stringify(failure.expected)}`);
    }
    process.exitCode = 1;
    return;
  }
  console.log(`[PASS] Electron Stage 50D Windows packaging 검증: ${checks.length} PASS / 0 FAIL`);
}
console.log(`validator=${VALIDATOR_VERSION}`);
console.log(`electron_root=${ELECTRON_ROOT}`);
console.log(`node=${process.version}`);
main();
