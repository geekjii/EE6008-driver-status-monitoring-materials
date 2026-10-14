$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

Write-Host "检查 Python 3.11..."
& py -3.11 --version
if ($LASTEXITCODE -ne 0) {
    throw "未找到 Python 3.11。请从 python.org 安装 64 位 Python 3.11。"
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "创建项目虚拟环境..."
    & py -3.11 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "创建虚拟环境失败。" }
}

$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
& $python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "升级 pip 失败。" }
& $python -m pip install -e ".[actions]"
if ($LASTEXITCODE -ne 0) { throw "安装项目依赖失败。" }
& $python scripts\download_face_model.py
if ($LASTEXITCODE -ne 0) { throw "下载人脸模型失败。" }
& $python scripts\download_phone_model.py
if ($LASTEXITCODE -ne 0) { throw "下载手机模型失败。" }
& $python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw "自动化测试失败。" }
& $python -m driver_monitor.doctor
if ($LASTEXITCODE -ne 0) { throw "环境诊断失败。" }

Write-Host "安装与无摄像头检查完成。双击 启动疲劳监测.bat 即可启动。"
