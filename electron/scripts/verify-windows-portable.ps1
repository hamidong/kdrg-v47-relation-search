param(
    [Parameter(Mandatory = $true)]
    [string]$ExePath,
    [string]$ReportPath = "$env:RUNNER_TEMP\kdrg_electron_packaged_smoke_report.json",
    [int64]$MinimumBytes = 60MB,
    [int]$TimeoutSeconds = 90
)
$ErrorActionPreference = "Stop"
$resolvedExe = (Resolve-Path $ExePath).Path
$exe = Get-Item $resolvedExe
Write-Host "===== Electron portable exe ====="
Write-Host "Path: $($exe.FullName)"
Write-Host "Size: $($exe.Length) bytes"
if ($exe.Length -lt $MinimumBytes) {
    throw "Electron portable exe가 비정상적으로 작습니다: $($exe.Length) bytes"
}
if (Test-Path $ReportPath) {
    Remove-Item $ReportPath -Force
}
$env:KDRG_ELECTRON_SMOKE_TEST = "1"
$env:KDRG_ELECTRON_SMOKE_REPORT = $ReportPath
$env:CSC_IDENTITY_AUTO_DISCOVERY = "false"
$process = Start-Process -FilePath $resolvedExe -ArgumentList "--kdrg-smoke-test" -PassThru
if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    throw "Electron packaged smoke가 ${TimeoutSeconds}초 안에 종료되지 않았습니다."
}
Write-Host "Smoke exit code: $($process.ExitCode)"
if ($process.ExitCode -ne 0) {
    if (Test-Path $ReportPath) {
        Get-Content $ReportPath -Raw -Encoding utf8 | Write-Host
    }
    throw "Electron packaged smoke 종료코드가 0이 아닙니다: $($process.ExitCode)"
}
if (-not (Test-Path $ReportPath)) {
    throw "Electron packaged smoke 보고서가 생성되지 않았습니다: $ReportPath"
}
$report = Get-Content $ReportPath -Raw -Encoding utf8 | ConvertFrom-Json
Write-Host "===== packaged smoke report ====="
Get-Content $ReportPath -Raw -Encoding utf8 | Write-Host
if ($report.status -ne "PASS") { throw "packaged smoke 상태가 PASS가 아닙니다." }
if ($report.app_is_packaged -ne $true) { throw "packaged smoke에서 app.isPackaged가 true가 아닙니다." }
if ($report.renderer_loaded -ne $true) { throw "packaged renderer가 정상 로드되지 않았습니다." }
if ($report.counts.adrg -ne 1132) { throw "ADRG count 불일치: $($report.counts.adrg)" }
if ($report.counts.aadrg -ne 1233) { throw "AADRG count 불일치: $($report.counts.aadrg)" }
if ($report.counts.rdrg -ne 2699) { throw "RDRG count 불일치: $($report.counts.rdrg)" }
if ($report.counts.tables -ne 1308) { throw "TABLE count 불일치: $($report.counts.tables)" }
if ($report.counts.codes -ne 16571) { throw "CODE count 불일치: $($report.counts.codes)" }
if ($report.search_fixture.found -ne $true) { throw "E011 검색 fixture가 확인되지 않았습니다." }
Write-Host "[PASS] Electron packaged portable exe 정적·기동검증 완료"
