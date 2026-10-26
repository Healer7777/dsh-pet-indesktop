@echo off
chcp 65001 >nul
setlocal
rem 交互式恢复：先列出快照，再按序号写回配置。
rem 恢复前请先在托盘退出桌宠，否则运行中的进程可能把配置再写回去。
set "HERE=%~dp0"
set "PY="
if exist "%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" (
  set "PY=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
)
if not defined PY ( py -3 -c "import sys" >nul 2>&1 && set "PY=py -3" )
if not defined PY ( python -c "import sys" >nul 2>&1 && set "PY=python" )
if not defined PY (
  echo [x] 没找到可用的 Python。
  pause
  exit /b 1
)
%PY% "%HERE%tools\pet_config_backup.py" --interactive
echo.
pause
