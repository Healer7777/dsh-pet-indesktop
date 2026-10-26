@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
rem ============================================================
rem  静默启动 opencode 中转代理（无窗口）
rem  由 proxy_silent.vbs 在开机时隐藏调用；手动调试也可以直接双击。
rem  日志：opencode_proxy.log（同目录）
rem ============================================================
set "HERE=%~dp0"
set "PORT=8787"
if not "%~1"=="" set "PORT=%~1"

set "PY="
rem 1) DSH 自带的 Python（本机最稳，不依赖用户装没装 Python）
if exist "%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" (
  set "PY=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
)
rem 2) py 启动器
if not defined PY (
  py -3 -c "import sys" >nul 2>&1 && set "PY=py -3"
)
if not defined PY (
  echo [%date% %time%] 找不到可用的 Python，代理未启动。 >> "%HERE%opencode_proxy.log"
  exit /b 1
)

%PY% "%HERE%opencode_proxy.py" --port %PORT%
