$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

Set-Location $PSScriptRoot
$launcher = Join-Path $PSScriptRoot ".venv\Scripts\driver-monitor-web.exe"

if (-not (Test-Path $launcher)) {
    Write-Host "项目环境尚未安装。请先运行 scripts\setup_windows.ps1。"
    exit 1
}

& $launcher
exit $LASTEXITCODE
