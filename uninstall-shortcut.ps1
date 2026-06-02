$ErrorActionPreference = "Stop"

$shortcutName = "Encoding Guardian UI.lnk"
$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop $shortcutName

if (Test-Path -LiteralPath $shortcutPath) {
  Remove-Item -LiteralPath $shortcutPath -Force
  Write-Host "Removed desktop shortcut:"
  Write-Host $shortcutPath
} else {
  Write-Host "Desktop shortcut was not found:"
  Write-Host $shortcutPath
}
