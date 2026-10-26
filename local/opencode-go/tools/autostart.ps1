param(
    [ValidateSet('install', 'uninstall', 'status')]
    [string]$Action = 'install',
    # override for self-test (defaults to the current user's real Startup folder)
    [string]$StartupDir = '',
    # override for self-test (defaults to the parent of this script)
    [string]$Root = ''
)

# ASCII-only on purpose: Windows PowerShell 5.1 reads .ps1 as ANSI, so non-ASCII
# text here would be mis-decoded and can even break parsing. Chinese messages
# live in the .bat wrappers.
#
# Two launch strategies, best first:
#   1) pythonw.exe  -> no console at all (preferred)
#   2) wscript.exe + proxy_silent.vbs -> hidden .bat wrapper (fallback)

$ErrorActionPreference = 'Stop'
if (-not $Root) { $Root = Split-Path -Parent $PSScriptRoot }
if (-not $StartupDir) { $StartupDir = [Environment]::GetFolderPath('Startup') }

$lnkPath = Join-Path $StartupDir 'opencode-proxy.lnk'
$script = Join-Path $Root 'opencode_proxy.py'

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
        $shell = New-Object -ComObject WScript.Shell
        $lnk = $shell.CreateShortcut($lnkPath)
        if ($pythonw) {
            $lnk.TargetPath = $pythonw
            $lnk.Arguments = '"' + $script + '" --port 8787'
            $mode = 'pythonw'
        } else {
            $vbs = Join-Path $Root 'proxy_silent.vbs'
            if (-not (Test-Path -LiteralPath $vbs)) { throw "missing launcher: $vbs" }
            $wscript = Join-Path $env:WINDIR 'System32\wscript.exe'
            if (-not (Test-Path -LiteralPath $wscript)) { $wscript = 'wscript.exe' }
            $lnk.TargetPath = $wscript
            $lnk.Arguments = '"' + $vbs + '"'
            $mode = 'wscript+vbs'
        }
        $lnk.WorkingDirectory = $Root
        $lnk.WindowStyle = 7
        $lnk.Description = 'opencode Go local proxy for dsh-pet'
        $lnk.Save()
        if (-not (Test-Path -LiteralPath $lnkPath)) { throw "shortcut was not created: $lnkPath" }
        "installed: $lnkPath"
        "  mode  : $mode"
        "  target: $($lnk.TargetPath)"
        "  args  : $($lnk.Arguments)"
        exit 0
    }
}
