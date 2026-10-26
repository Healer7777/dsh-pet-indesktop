@echo off
chcp 65001 >nul
setlocal
rem 让 Windows 每次登录时自动做一份配置快照（保留最近 20 份）。
echo 正在开启「每次登录自动备份桌宠配置」...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\autostart_backup.ps1" -Action install
if errorlevel 1 (
  echo.
  echo [x] 安装失败，把上面的报错发我。
) else (
  echo.
  echo [ok] 完成。以后每次开机/登录都会自动存一份，误点重置也能找回来。
)
echo.
pause
