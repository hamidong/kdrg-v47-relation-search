param(
    [Parameter(Mandatory = $true)]
    [string]$ExePath,
    [string]$ReportPath = "$env:RUNNER_TEMP\kdrg_electron_packaged_smoke_report.json",
    [string]$ScreenshotDirectory = "$env:RUNNER_TEMP\kdrg_electron_packaged_ui_smoke",
    [string]$EvidenceZipPath = "electron\dist\KDRG_ELECTRON_UI_SMOKE_EVIDENCE.zip",
    [int64]$MinimumBytes = 60MB,
    [int]$TimeoutSeconds = 180
)

$ErrorActionPreference = "Stop"

function Assert-Equal {
    param(
        [string]$Label,
        $Actual,
        $Expected
    )
    if ($Actual -ne $Expected) {
        throw "$Label 불일치: actual=$Actual expected=$Expected"
    }
}

function Assert-StringSet {
    param(
        [string]$Label,
        [object[]]$Actual,
        [object[]]$Expected
    )
    $actualList = @($Actual | ForEach-Object { [string]$_ } | Sort-Object -Unique)
    $expectedList = @($Expected | ForEach-Object { [string]$_ } | Sort-Object -Unique)
    $actualText = $actualList -join "|"
    $expectedText = $expectedList -join "|"
    if ($actualText -cne $expectedText) {
        throw "$Label 불일치: actual=$actualText expected=$expectedText"
    }
}

$resolvedExe = (Resolve-Path $ExePath).Path
$exe = Get-Item $resolvedExe
$resolvedReportPath = [System.IO.Path]::GetFullPath($ReportPath)
$resolvedScreenshotDirectory = [System.IO.Path]::GetFullPath($ScreenshotDirectory)
$resolvedEvidenceZipPath = [System.IO.Path]::GetFullPath($EvidenceZipPath)

Write-Host "===== Electron portable exe ====="
Write-Host "Path: $($exe.FullName)"
Write-Host "Size: $($exe.Length) bytes"
Write-Host "Report: $resolvedReportPath"
Write-Host "Screenshots: $resolvedScreenshotDirectory"
Write-Host "Evidence ZIP: $resolvedEvidenceZipPath"

if ($exe.Length -lt $MinimumBytes) {
    throw "Electron portable exe가 비정상적으로 작습니다: $($exe.Length) bytes"
}

foreach ($path in @($resolvedReportPath, $resolvedEvidenceZipPath)) {
    if (Test-Path $path) {
        Remove-Item $path -Force
    }
}
if (Test-Path $resolvedScreenshotDirectory) {
    Remove-Item $resolvedScreenshotDirectory -Recurse -Force
}
New-Item -ItemType Directory -Path $resolvedScreenshotDirectory -Force | Out-Null

$evidenceParent = Split-Path $resolvedEvidenceZipPath -Parent
if (-not (Test-Path $evidenceParent)) {
    New-Item -ItemType Directory -Path $evidenceParent -Force | Out-Null
}

$env:KDRG_ELECTRON_SMOKE_TEST = "1"
$env:KDRG_ELECTRON_SMOKE_REPORT = $resolvedReportPath
$env:KDRG_ELECTRON_SMOKE_SCREENSHOT_DIR = $resolvedScreenshotDirectory
$env:CSC_IDENTITY_AUTO_DISCOVERY = "false"

$process = Start-Process `
    -FilePath $resolvedExe `
    -ArgumentList "--kdrg-smoke-test" `
    -PassThru

if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    throw "Electron packaged smoke가 ${TimeoutSeconds}초 안에 종료되지 않았습니다."
}

Write-Host "Smoke exit code: $($process.ExitCode)"
if ($process.ExitCode -ne 0) {
    if (Test-Path $resolvedReportPath) {
        Get-Content $resolvedReportPath -Raw -Encoding utf8 | Write-Host
    }
    throw "Electron packaged smoke 종료코드가 0이 아닙니다: $($process.ExitCode)"
}

if (-not (Test-Path $resolvedReportPath -PathType Leaf)) {
    throw "Electron packaged smoke 보고서가 생성되지 않았습니다: $resolvedReportPath"
}

$report = Get-Content $resolvedReportPath -Raw -Encoding utf8 | ConvertFrom-Json

Write-Host "===== packaged smoke report ====="
Get-Content $resolvedReportPath -Raw -Encoding utf8 | Write-Host

if ($report.status -ne "PASS") { throw "packaged smoke 상태가 PASS가 아닙니다." }
if ($report.app_is_packaged -ne $true) { throw "packaged smoke에서 app.isPackaged가 true가 아닙니다." }
if ($report.counts.adrg -ne 1132) { throw "ADRG count 불일치: $($report.counts.adrg)" }

Assert-Equal "packaged smoke schema" $report.schema_version "kdrg-packaged-runtime-smoke-v2"
Assert-Equal "packaged renderer_loaded" $report.renderer_loaded $true

Assert-Equal "ADRG count" $report.counts.adrg 1132
Assert-Equal "AADRG count" $report.counts.aadrg 1233
Assert-Equal "RDRG count" $report.counts.rdrg 2699
Assert-Equal "TABLE count" $report.counts.tables 1308
Assert-Equal "CODE count" $report.counts.codes 16571
Assert-Equal "condition AST count" $report.counts.conditionAst 390
Assert-Equal "condition TABLE occurrence count" $report.counts.conditionTableOccurrences 939
Assert-Equal "E011 검색 fixture" $report.search_fixture.found $true
Assert-Equal "관계검색 fixture" $report.relation_fixture.found $true

$ui = $report.ui_validation
if (-not $ui) {
    throw "packaged smoke 보고서에 ui_validation이 없습니다."
}

Assert-Equal "UI schema" $ui.schema_version "kdrg-packaged-ui-smoke-v1"
Assert-Equal "UI status" $ui.status "PASS"
Assert-Equal "UI case count" $ui.case_count 6
Assert-Equal "UI screenshot count" $ui.screenshot_count 6
Assert-Equal "UI screenshot distinct count" $ui.screenshot_distinct_count 6
Assert-Equal "renderer console error count" $ui.console_error_count 0
Assert-Equal "renderer gone count" $ui.render_process_gone_count 0
Assert-Equal "renderer load failure count" $ui.load_failure_count 0

$expected = @{
    "B013" = @("LT_B018_002")
    "B014" = @("LT_B018_003")
    "B018" = @("LT_B018_001", "LT_B018_004", "LT_B018_005")
    "B022" = @()
    "L033" = @()
    "9610" = @()
}

$caseMap = @{}
foreach ($case in @($ui.cases)) {
    $caseMap[[string]$case.adrg] = $case
}

Assert-StringSet "UI ADRG fixture 집합" @($caseMap.Keys) @($expected.Keys)

$screenshotHashes = @()
foreach ($adrg in @("B013", "B014", "B018", "B022", "L033", "9610")) {
    $case = $caseMap[$adrg]
    if (-not $case) {
        throw "UI fixture가 없습니다: $adrg"
    }

    Assert-Equal "$adrg case PASS" $case.passed $true
    Assert-StringSet "$adrg TABLE" @($case.table_ids) @($expected[$adrg])
    Assert-Equal "$adrg inline TABLE count" $case.inline_table_count @($expected[$adrg]).Count
    Assert-Equal "$adrg loaded TABLE count" $case.loaded_table_count @($expected[$adrg]).Count
    Assert-Equal "$adrg inline error count" @($case.error_messages).Count 0
    Assert-Equal "$adrg screenshot nonblank" $case.screenshot.non_blank $true

    if (@($expected[$adrg]).Count -gt 0 -and [int]$case.code_row_total -le 0) {
        throw "$adrg TABLE 코드 행이 로드되지 않았습니다: $($case.code_row_total)"
    }

    $screenshotPath = [string]$case.screenshot_path
    if (-not (Test-Path $screenshotPath -PathType Leaf)) {
        throw "$adrg screenshot 파일이 없습니다: $screenshotPath"
    }

    $screenshotFile = Get-Item $screenshotPath
    if ($screenshotFile.Length -lt 10000) {
        throw "$adrg screenshot 파일이 비정상적으로 작습니다: $($screenshotFile.Length)"
    }

    $actualHash = (Get-FileHash $screenshotPath -Algorithm SHA256).Hash.ToLower()
    $expectedHash = ([string]$case.screenshot_sha256).ToLower()
    Assert-Equal "$adrg screenshot SHA256" $actualHash $expectedHash
    $screenshotHashes += $actualHash

    Write-Host "[PASS] $adrg | TABLE=$(@($case.table_ids) -join ',') | rows=$($case.code_row_total) | PNG=$($screenshotFile.Name)"
}

Assert-Equal "screenshot SHA256 고유 수" @($screenshotHashes | Sort-Object -Unique).Count 6

$indexPath = [string]$ui.index_html
if (-not (Test-Path $indexPath -PathType Leaf)) {
    throw "UI screenshot index가 없습니다: $indexPath"
}

Copy-Item $resolvedReportPath `
    (Join-Path $resolvedScreenshotDirectory "packaged_smoke_report.json") `
    -Force

if (Test-Path $resolvedEvidenceZipPath) {
    Remove-Item $resolvedEvidenceZipPath -Force
}
Compress-Archive `
    -Path (Join-Path $resolvedScreenshotDirectory "*") `
    -DestinationPath $resolvedEvidenceZipPath `
    -CompressionLevel Optimal

if (-not (Test-Path $resolvedEvidenceZipPath -PathType Leaf)) {
    throw "UI smoke 증거 ZIP이 생성되지 않았습니다: $resolvedEvidenceZipPath"
}

$evidence = Get-Item $resolvedEvidenceZipPath
if ($evidence.Length -lt 50000) {
    throw "UI smoke 증거 ZIP이 비정상적으로 작습니다: $($evidence.Length)"
}
$evidenceHash = (Get-FileHash $resolvedEvidenceZipPath -Algorithm SHA256).Hash.ToLower()

Write-Host "===== packaged UI evidence ====="
Write-Host "ZIP: $resolvedEvidenceZipPath"
Write-Host "Size: $($evidence.Length) bytes"
Write-Host "SHA256: $evidenceHash"
Write-Host "[PASS] Electron packaged portable exe 데이터·검색·실제 UI 6건 검증 완료"
