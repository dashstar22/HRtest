# AI 招聘简历智能筛选助手 —— 一键启动
# 用法：右键「使用 PowerShell 运行」，或在终端执行 .\run.ps1

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $python)) {
    Write-Host '[1/2] 首次运行，正在创建虚拟环境并安装依赖...' -ForegroundColor Cyan
    python -m venv (Join-Path $PSScriptRoot '.venv')
    & $python -m pip install --disable-pip-version-check -q -r (Join-Path $PSScriptRoot 'requirements.txt')
}

if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot '.env'))) {
    Copy-Item (Join-Path $PSScriptRoot '.env.example') (Join-Path $PSScriptRoot '.env')
    Write-Host '已生成 .env，如需真实大模型分析，请填入 DEEPSEEK_API_KEY 后重启。' -ForegroundColor Yellow
}

$env:PYTHONIOENCODING = 'utf-8'
Write-Host '启动中：http://127.0.0.1:8000' -ForegroundColor Green
Start-Process 'http://127.0.0.1:8000'
& $python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
