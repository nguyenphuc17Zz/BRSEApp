$WshShell = New-Object -ComObject WScript.Shell
$DesktopPath = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Desktop)
$ShortcutPath = Join-Path $DesktopPath "Start Translation App.lnk"

if (Test-Path $ShortcutPath) {
    $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
    Write-Host "File exists: YES"
    Write-Host "FullName: $($Shortcut.FullName)"
    Write-Host "TargetPath: $($Shortcut.TargetPath)"
    Write-Host "WorkingDirectory: $($Shortcut.WorkingDirectory)"
    Write-Host "IconLocation: $($Shortcut.IconLocation)"
    Write-Host "Description: $($Shortcut.Description)"
} else {
    Write-Host "ERROR: File does not exist!"
}
