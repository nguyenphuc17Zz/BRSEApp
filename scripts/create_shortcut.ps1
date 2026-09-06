$WshShell = New-Object -ComObject WScript.Shell
$DesktopPath = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Desktop)
$ShortcutPath = Join-Path $DesktopPath "Start Translation App.lnk"

$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = "E:\AutomationTranslate\start.bat"
$Shortcut.WorkingDirectory = "E:\AutomationTranslate"
$Shortcut.IconLocation = "E:\AutomationTranslate\app_icon.ico, 0"
$Shortcut.Description = "Launch AI Comtor / BrSE Translation Copilot"
$Shortcut.Save()

Write-Host "SUCCESS: Shortcut created at $ShortcutPath"
