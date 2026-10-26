param(
    [ValidateSet('install', 'uninstall', 'status')]
    [string]$Action = 'install',
    [string]$StartupDir = '',
    [string]$Root = ''
)

# 每次登录 Windows 时做一份桌宠配置快照（保留最近 20 份）。
# 纯 ASCII：PowerShell 5.1 按 ANSI 读 .ps1，中文会乱码甚至破坏语法。

$ErrorActionPreference = 'Stop'
if (-not $Root) { $Root = Split-Path -Parent $PSScriptRoot }
if (-not $StartupDir) { $StartupDir = [Environment]::GetFolderPath('Startup') }

$lnkPath = Join-Path $StartupDir 'pet-config-backup.lnk'
$script = Join-Path $Root 'tools\pet_config_backup.py'

function Find-Pythonw {
    $candidates = @(
        (Join-Path $env:USERPROFILE '.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\pythonw.exe')
    )
    $cmd = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if ($cmd) { $candidates += $cmd.Source }
    foreach ($c in $candidates) {
        if ($c -and (Test-Path -LiteralPath $c)) { return (Resolve-Path -LiteralPath $c).Path }
    }
    return $null
}

switch ($Action) {
    'status' {
        if (Test-Path -LiteralPath $lnkPath) {
            $sc = (New-Object -ComObject WScript.Shell).CreateShortcut($lnkPath)
            "installed: $lnkPath"
            "  target: $($sc.TargetPath)"
            "  args  : $($sc.Arguments)"
        } else {
            "not installed: $lnkPath"
        }
        exit 0
    }
    'uninstall' {
        if (Test-Path -LiteralPath $lnkPath) {
            Remove-Item -LiteralPath $lnkPath -Force
            "removed: $lnkPath"
        } else {
            "nothing to remove: $lnkPath"
        }
        exit 0
    }
    'install' {
        if (-not (Test-Path -LiteralPath $script)) { throw "missing script: $script" }
        if (-not (Test-Path -LiteralPath $StartupDir)) { throw "missing startup dir: $StartupDir" }
        $pythonw = Find-Pythonw
        if (-not $pythonw) { throw "pythonw.exe not found" }
        $shell = New-Object -ComObject WScript.Shell
        $lnk = $shell.CreateShortcut($lnkPath)
        $lnk.TargetPath = $pythonw
        $lnk.Arguments = '"' + $script + '" --quiet'
        $lnk.WorkingDirectory = $Root
        $lnk.WindowStyle = 7
        $lnk.Description = 'dsh-pet config snapshot at logon'
        $lnk.Save()
        if (-not (Test-Path -LiteralPath $lnkPath)) { throw "shortcut was not created: $lnkPath" }
        "installed: $lnkPath"
        "  target: $pythonw"
        "  args  : `"$script`" --quiet"
        exit 0
    }
}
