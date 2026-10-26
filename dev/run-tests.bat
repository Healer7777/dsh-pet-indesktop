@echo off
chcp 65001 >nul
setlocal
rem 跑测试 / 静态检查（用仓库自己的 .venv）
set "ROOT=%~dp0.."
cd /d "%ROOT%"
if "%~1"=="" (
  "%ROOT%\.venv\Scripts\python.exe" -m pytest tests\test_opencode_go_headers.py -q
) else (
  "%ROOT%\.venv\Scripts\python.exe" -m pytest %* -q
)
pause
