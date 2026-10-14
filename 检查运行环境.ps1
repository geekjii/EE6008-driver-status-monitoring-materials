$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

Set-Location $PSScriptRoot
$doctor = Join-Path $PSScriptRoot ".venv\Scripts\driver-monitor-doctor.exe"

if (-not (Test-Path $doctor)) {
    Write-Host "项目环境尚未安装。请先运行 scripts\setup_windows.ps1。"
    exit 1
}

& $doctor
exit $LASTEXITCODE
