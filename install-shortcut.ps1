$ErrorActionPreference = "Stop"

$shortcutName = "Encoding Guardian UI.lnk"
$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop $shortcutName
$targetPath = Join-Path $PSScriptRoot "run.bat"

if (-not (Test-Path -LiteralPath $targetPath)) {
  throw "run.bat was not found next to this script."
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $targetPath
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.Description = "Open Encoding Guardian UI"
$shortcut.Save()

Write-Host "Created desktop shortcut:"
Write-Host $shortcutPath
