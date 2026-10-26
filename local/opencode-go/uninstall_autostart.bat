@echo off
chcp 65001 >nul
setlocal
rem 移除「opencode 中转代理」的开机自启项。
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\autostart.ps1" -Action uninstall
echo.
pause
