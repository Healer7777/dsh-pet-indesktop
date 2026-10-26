@echo off
chcp 65001 >nul
setlocal
rem 调试启动器：保留控制台，异常/traceback 直接可见。Ctrl+C 结束。
set "ROOT=%~dp0.."
set "PYTHONPATH=%ROOT%\dev;%PYTHONPATH%"
cd /d "%ROOT%"
"%ROOT%\.venv\Scripts\python.exe" -m pet %*
pause
