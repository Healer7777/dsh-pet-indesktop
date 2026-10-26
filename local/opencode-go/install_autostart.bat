@echo off
chcp 65001 >nul
setlocal
rem 把「opencode 中转代理」注册为登录时自动后台启动（无窗口）。
echo 正在安装开机自启...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\autostart.ps1" -Action install
if errorlevel 1 (
  echo.
  echo [x] 安装失败，请把上面的报错发给我。
) else (
  echo.
  echo [ok] 完成。代理会在下次登录 Windows 时自动启动，桌宠无需任何改动。
  echo      现在想立刻生效，直接双击 proxy_silent.vbs 即可（无窗口）。
)
echo.
pause
