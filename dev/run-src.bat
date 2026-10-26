@echo off
chcp 65001 >nul
setlocal
rem ============================================================
rem  源码版启动器（静默：用 pythonw，不开控制台）
rem  排错请看 debug-src.bat（保留控制台，能看到 traceback）
rem ============================================================
set "ROOT=%~dp0.."
set "PYTHONPATH=%ROOT%\dev;%PYTHONPATH%"
cd /d "%ROOT%"

if not exist "%ROOT%\.venv\Scripts\pythonw.exe" (
  echo [x] 没找到 .venv，请先按 docs\SOURCE-DEPLOY-2026-10-26.md 建环境
  pause
  exit /b 1
)
start "" "%ROOT%\.venv\Scripts\pythonw.exe" -m pet --slot 0 %*
