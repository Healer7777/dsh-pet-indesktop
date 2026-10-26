' Hidden launcher for the opencode local proxy (used by the Startup shortcut).
' Kept ASCII-only on purpose: WScript reads .vbs as ANSI, non-ASCII would garble.
Option Explicit
Dim fso, sh, here, target
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
here = fso.GetParentFolderName(WScript.ScriptFullName)
target = here & "\proxy_silent.bat"
If Not fso.FileExists(target) Then
  MsgBox "proxy_silent.bat not found next to this script:" & vbCrLf & target, 16, "opencode proxy"
  WScript.Quit 1
End If
sh.CurrentDirectory = here
' 0 = hidden window, False = do not wait for it to finish
sh.Run """" & target & """", 0, False
