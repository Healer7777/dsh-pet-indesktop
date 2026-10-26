@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
rem ============================================================
rem  opencode Go 本地中转代理 —— 一键启动
rem  桌宠设置里保持：API 地址 http://127.0.0.1:8787/v1
rem                  模型     deepseek-v4.1-flash
rem  关掉这个窗口 = 停止代理。
rem ============================================================
set "HERE=%~dp0"
set "PORT=8787"
if not "%~1"=="" set "PORT=%~1"

set "PY="
py -3 -c "import sys" >nul 2>&1 && set "PY=py -3"
if not defined PY (
  python -c "import sys" >nul 2>&1 && set "PY=python"
)
if not defined PY (
  if exist "%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" (
    set "PY=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
  )
)
if not defined PY (
  echo [x] 没找到可用的 Python。请安装 Python 3.10+ 后再运行本脚本。
  pause
  exit /b 1
)

echo === opencode 代理 端口 %PORT% ===
%PY% "%HERE%opencode_proxy.py" --port %PORT%
pause
