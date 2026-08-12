'use strict';

const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

const VALIDATOR_VERSION =
  '2026-07-30_KDRG_V47_ELECTRON_STAGE50D_PACKAGING_VALIDATOR_V5_RELATION_UI';
const ELECTRON_ROOT = path.resolve(__dirname, '..');
const ROOT = path.resolve(ELECTRON_ROOT, '..');

const EXPECTED_DATA = Object.freeze({
  'kdrg_v47_search_integrated_v3.json':
    '3cc370dfb7e3d3c9480e66fc6cdb2b83c9f05f39fa82c0ce4d9403c0812d7f0b',
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
function collectResolvedUrls(value, output = []) {
  if (Array.isArray(value)) {
    for (const child of value) {
      collectResolvedUrls(child, output);
    }
    return output;
  }
  if (value && typeof value === 'object') {
    if (typeof value.resolved === 'string' && value.resolved.trim()) {
      output.push(value.resolved.trim());
    }
    for (const child of Object.values(value)) {
      collectResolvedUrls(child, output);
    }
  }
  return output;
}
function main() {
  const packagePath = path.join(ELECTRON_ROOT, 'package.json');
  const lockPath = path.join(ELECTRON_ROOT, 'package-lock.json');
  const workflowPath = path.join(ROOT, '.github', 'workflows', 'build-electron-windows.yml');
  const smokeSourcePath = path.join(ELECTRON_ROOT, 'src', 'packaged-runtime-smoke.js');
  const rendererHtmlPath = path.join(ELECTRON_ROOT, 'renderer', 'index.html');
  const rendererAppPath = path.join(ELECTRON_ROOT, 'renderer', 'app.js');
  const relationContractPath = path.join(ELECTRON_ROOT, 'src', 'search-result-contract.js');
  const searchServicePath = path.join(ELECTRON_ROOT, 'src', 'kdrg-search-service.js');
  const verifyScriptPath = path.join(ELECTRON_ROOT, 'scripts', 'verify-windows-portable.ps1');
  const smokeContractTestPath = path.join(
    ELECTRON_ROOT,
    'tests',
    'validate-packaged-runtime-smoke.js',
  );
  const releaseVersionValidatorPath = path.join(
    ELECTRON_ROOT,
    'tests',
    'validate-release-version.js',
  );
  const registryValidatorPath = path.join(
    ELECTRON_ROOT,
    'scripts',
    'validate-package-lock-registry.py',
  );

  for (const filePath of [
    packagePath,
    lockPath,
    workflowPath,
    smokeSourcePath,
    rendererHtmlPath,
    rendererAppPath,
    relationContractPath,
    searchServicePath,
    smokeContractTestPath,
    releaseVersionValidatorPath,
    verifyScriptPath,
    registryValidatorPath,
  ]) {
    check(`필수 파일 존재 ${path.relative(ROOT, filePath)}`, fs.existsSync(filePath), true);
  }

  const packageJson = readJson(packagePath);
  const lockJson = readJson(lockPath);
  const build = packageJson.build || {};
  const scripts = packageJson.scripts || {};
  const devDependencies = packageJson.devDependencies || {};

  check(
    'package version semver',
    packageJson.version,
    'semver',
    (value) => /^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/.test(String(value || '')),
  );
  check('Electron pin', devDependencies.electron, '43.2.0');
  check('electron-builder pin', devDependencies['electron-builder'], '26.15.3');
  check('Node engine', packageJson.engines?.node, '>=22.0.0');
  check('validate:packaging script', scripts['validate:packaging'], 'node tests/validate-packaging-config.js');
  check('validate:release-version script', scripts['validate:release-version'], 'node tests/validate-release-version.js');
  check(
    'validate:smoke-contract script',
    scripts['validate:smoke-contract'],
    'node tests/validate-packaged-runtime-smoke.js',
  );
  check(
    'validate script smoke contract 포함',
    scripts.validate || '',
    'validate:smoke-contract',
    (value, target) => value.includes(target),
  );
  check('dist:win script', scripts['dist:win'], 'electron-builder --win portable --x64 --publish never');
  check('check script packaging 포함', scripts.check || '', 'validate-packaging-config.js', (value, target) => value.includes(target));
  check(
    'check script smoke contract 문법검증 포함',
    scripts.check || '',
    'validate-packaged-runtime-smoke.js',
    (value, target) => value.includes(target),
  );

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
  check('lock top version', lockJson.version, packageJson.version);
  check('lock root version', lockJson.packages?.['']?.version, packageJson.version);
  check('lock root Electron pin', lockJson.packages?.['']?.devDependencies?.electron, '43.2.0');
  check('lock root electron-builder pin', lockJson.packages?.['']?.devDependencies?.['electron-builder'], '26.15.3');
  check('lock resolved Electron version', lockJson.packages?.['node_modules/electron']?.version, '43.2.0');
  check('lock resolved electron-builder version', lockJson.packages?.['node_modules/electron-builder']?.version, '26.15.3');

  const resolvedUrls = collectResolvedUrls(lockJson);
  const internalRegistryUrls = resolvedUrls.filter((url) =>
    url.toLowerCase().includes('package-firewall.replit.local'));
  const plainHttpUrls = resolvedUrls.filter((url) =>
    url.toLowerCase().startsWith('http://'));
  const officialRegistryUrls = resolvedUrls.filter((url) =>
    url.startsWith('https://registry.npmjs.org/'));
  check('lock resolved URL 수', resolvedUrls.length, '>= 50', (value) => value >= 50);
  check('lock Replit 내부 registry URL 없음', internalRegistryUrls.length, 0);
  check('lock 평문 HTTP URL 없음', plainHttpUrls.length, 0);
  check('lock 공식 npm registry URL 전체', officialRegistryUrls.length, resolvedUrls.length);

  const releaseValidatorSource = fs.readFileSync(releaseVersionValidatorPath, 'utf8');
  check('release validator package-lock 일치검증', releaseValidatorSource.includes('lock root version'), true);
  check('release validator stable semver', releaseValidatorSource.includes('STABLE_SEMVER'), true);
  const registryValidatorSource = fs.readFileSync(registryValidatorPath, 'utf8');
  check(
    'registry validator 공식 host',
    registryValidatorSource.includes('registry.npmjs.org'),
    true,
  );
  check(
    'registry validator 내부 host 차단',
    registryValidatorSource.includes('package-firewall.replit.local'),
    true,
  );

  const mainSource = fs.readFileSync(path.join(ELECTRON_ROOT, 'main.js'), 'utf8');
  const preloadSource = fs.readFileSync(path.join(ELECTRON_ROOT, 'preload.js'), 'utf8');
  const smokeSource = fs.readFileSync(smokeSourcePath, 'utf8');
  const rendererHtml = fs.readFileSync(rendererHtmlPath, 'utf8');
  const rendererApp = fs.readFileSync(rendererAppPath, 'utf8');
  const relationContractSource = fs.readFileSync(relationContractPath, 'utf8');
  const searchServiceSource = fs.readFileSync(searchServicePath, 'utf8');
  check('main smoke import', mainSource.includes("require('./src/packaged-runtime-smoke')"), true);
  check('main smoke 실행', mainSource.includes('runPackagedRuntimeSmoke({'), true);
  check('main 관계검색 request 검증', mainSource.includes('normalizeRelationRequest(payload)'), true);
  check('main 관계검색 IPC', mainSource.includes("relationSearch: 'kdrg:relation-search'"), true);
  check('preload 관계검색 bridge', preloadSource.includes('relationSearch: (request)'), true);
  check('관계검색 request 2~6개 계약', relationContractSource.includes('payload.conditions.length < 2') && relationContractSource.includes('payload.conditions.length > 6'), true);
  check('관계검색 중복코드 차단', relationContractSource.includes('같은 코드를 중복 입력할 수 없습니다'), true);
  check('검색 service 관계 응답 schema', searchServiceSource.includes('kdrg-runtime-relation-response-v1'), true);
  check('검색 service 관계검색 method', searchServiceSource.includes("relationSearch(conditions, operator = 'AND'"), true);
  check('검색 service 제외 TABLE 차단', searchServiceSource.includes('exclusionTableIds.has(tableId)'), true);
  check('검색 service strict split partial', ['strict', 'split', 'partial'].every((level) => searchServiceSource.includes(`'${level}'`)), true);
  check(
    'smoke app.isPackaged 기록',
    smokeSource.includes('app_is_packaged: Boolean(app?.isPackaged)'),
    true,
  );
  check('smoke 데이터 경로 검사', smokeSource.includes('resolveDataFiles({'), true);
  check('smoke E011 검색', smokeSource.includes("service.search('E011'"), true);
  check('smoke 현재 search.results 계약', smokeSource.includes('search.results'), true);
  check('smoke 과거 search.items 직접참조 제거', smokeSource.includes('search.items.some'), false);
  check('smoke search 계약 명시검증', smokeSource.includes('validateSearchResponse(search)'), true);
  check('smoke detail 계약 명시검증', smokeSource.includes('validateDetailResponse'), true);
  check('smoke 관계검색 실제 fixture 탐색', smokeSource.includes('findRelationSmokeFixture(service)'), true);
  check('smoke 관계검색 응답 계약 검증', smokeSource.includes('validateRelationResponse'), true);
  check('smoke 관계검색 완료 단계', smokeSource.includes('relation_contract_verified'), true);
  check('smoke 단계별 진단', smokeSource.includes('completed_steps'), true);
  check('smoke 실패단계 진단', smokeSource.includes('failed_step'), true);
  const smokeContractTestSource = fs.readFileSync(smokeContractTestPath, 'utf8');
  check(
    'smoke contract test 과거 items 회귀 fixture',
    smokeContractTestSource.includes('obsolete items field detected'),
    true,
  );
  check(
    'smoke contract test raw TypeError 방지',
    smokeContractTestSource.includes('legacy report no raw TypeError'),
    true,
  );
  check(
    'smoke contract test packaged 실행 모의검증',
    smokeContractTestSource.includes('runPackagedRuntimeSmoke(fixture)'),
    true,
  );
  check(
    'smoke contract test 관계검색 정상 fixture',
    smokeContractTestSource.includes('runtime relation schema'),
    true,
  );
  check(
    'smoke contract test 관계검색 실패단계',
    smokeContractTestSource.includes('relation report failed step'),
    true,
  );
  check('smoke renderer load', smokeSource.includes('did-finish-load'), true);
  check('smoke renderer 보안 contextIsolation', smokeSource.includes('contextIsolation: true'), true);
  check('smoke renderer 보안 nodeIntegration', smokeSource.includes('nodeIntegration: false'), true);
  check('smoke renderer 보안 sandbox', smokeSource.includes('sandbox: true'), true);
  check('renderer 데이터 현황 기본 접힘', /<details[^>]+id="data-overview"(?![^>]*\sopen)[^>]*>/.test(rendererHtml), true);
  check('renderer 복수 코드 관계검색 panel', rendererHtml.includes('id="relation-search-panel"'), true);
  check('renderer 기존 MDC 필터 유지', rendererHtml.includes('id="filter-mdc"'), true);
  check('renderer 기존 질병군 분류 필터 유지', rendererHtml.includes('id="filter-classification"'), true);
  check('renderer 상세 section details', rendererApp.includes("create('details', 'detail-section')"), true);
  check('renderer TABLE 코드 기본 접힘', rendererApp.includes("makeSection('TABLE 코드'") && rendererApp.includes('open: false'), true);
  check('renderer 전체 펼치기·접기', rendererApp.includes('setAllDetailSections(true)') && rendererApp.includes('setAllDetailSections(false)'), true);

  const workflow = fs.readFileSync(workflowPath, 'utf8');
  check('workflow Windows runner', workflow.includes('runs-on: windows-latest'), true);
  check('workflow checkout Node24 세대', workflow.includes('actions/checkout@v6'), true);
  check('workflow setup-node Node24 세대', workflow.includes('actions/setup-node@v6'), true);
  check('workflow setup-python Node24 세대', workflow.includes('actions/setup-python@v6'), true);
  check('workflow Node 22.23.1', workflow.includes('node-version: "22.23.1"'), true);
  check('workflow npm CLI pin', workflow.includes('NPM_CLI_VERSION: "11.17.0"'), true);
  check(
    'workflow 공식 npm registry 고정',
    workflow.includes('NPM_CONFIG_REGISTRY: "https://registry.npmjs.org"'),
    true,
  );
  check(
    'workflow package-lock registry 사전검증',
    workflow.includes('package-lock 공식 registry 사전검증'),
    true,
  );
  check(
    'workflow registry validator 실행',
    workflow.includes('scripts/validate-package-lock-registry.py'),
    true,
  );
  check(
    'workflow npm ci 공식 registry 명시',
    workflow.includes('--registry=https://registry.npmjs.org'),
    true,
  );
  check('workflow setup-node npm cache 미사용', workflow.includes('cache: npm'), false);
  const jobEnvStart = workflow.indexOf('    env:');
  const stepsStart = workflow.indexOf('    steps:');
  const jobEnvBlock = jobEnvStart >= 0 && stepsStart > jobEnvStart
    ? workflow.slice(jobEnvStart, stepsStart)
    : '';
  check('workflow job env runner context 미사용', jobEnvBlock.includes('${{ runner.'), false);
  check('workflow 전체 runner context 조기평가 미사용', workflow.includes('${{ runner.'), false);
  check('workflow 런타임 임시경로 초기화 단계', workflow.includes('Actions 런타임 임시경로 초기화'), true);
  check('workflow RUNNER_TEMP 런타임 사용', workflow.includes('$env:RUNNER_TEMP'), true);
  check('workflow 실행 식별자 환경변수 사용', workflow.includes('$env:GITHUB_RUN_ID') && workflow.includes('$env:GITHUB_RUN_ATTEMPT'), true);
  check('workflow 실행별 fresh npm cache', workflow.includes('npm-cache-$($env:GITHUB_RUN_ID)-$($env:GITHUB_RUN_ATTEMPT)'), true);
  check('workflow npm cache GITHUB_ENV 전달', workflow.includes('"NPM_CONFIG_CACHE=$npmCache" >> $env:GITHUB_ENV'), true);
  check('workflow Electron cache GITHUB_ENV 전달', workflow.includes('"ELECTRON_CACHE=$electronCache" >> $env:GITHUB_ENV'), true);
  check('workflow builder cache GITHUB_ENV 전달', workflow.includes('"ELECTRON_BUILDER_CACHE=$builderCache" >> $env:GITHUB_ENV'), true);
  check('workflow npm registry metadata', workflow.includes('https://registry.npmjs.org/npm/$npmVersion'), true);
  check('workflow npm tarball SHA512', workflow.includes('SHA512') && workflow.includes('expectedIntegrity'), true);
  check('workflow npm CLI 직접 실행', workflow.includes('& node $npmCli ci'), true);
  check('workflow npm ci 옵션', workflow.includes('--no-audit') && workflow.includes('--no-fund') && workflow.includes('--foreground-scripts'), true);
  check('workflow npm ci 2회 복구', workflow.includes('$attempt -le 2'), true);
  check('workflow npm debug log 출력', workflow.includes('*-debug-0.log') && workflow.includes('-Tail 250'), true);
  check('workflow check 고정 npm CLI', workflow.includes('& node $npmCli run check'), true);
  check('workflow dist 고정 npm CLI', workflow.includes('& node $npmCli run dist:win'), true);
  check('workflow Python 50D 검증', workflow.includes('50D_validate_kdrg_electron_windows_packaging.py'), true);
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
