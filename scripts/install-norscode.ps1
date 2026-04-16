param(
  [string]$InstallDir = "$env:LOCALAPPDATA\Norscode\bin",
  [string]$Version = "latest"
)

$ErrorActionPreference = "Stop"
$Repo = "rfwwp8k542-maker/Norscode-language"
$Asset = "norscode-windows.exe"

if ($Version -eq "latest") {
  $DownloadUrl = "https://github.com/$Repo/releases/latest/download/$Asset"
} else {
  $DownloadUrl = "https://github.com/$Repo/releases/download/$Version/$Asset"
}

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
$Target = Join-Path $InstallDir "norscode.exe"
$TempFile = Join-Path $env:TEMP $Asset

Invoke-WebRequest -Uri $DownloadUrl -OutFile $TempFile
Copy-Item $TempFile $Target -Force
Remove-Item $TempFile -Force

Write-Host "Norscode ble installert i: $Target"
Write-Host "Legg $InstallDir i PATH hvis det ikke allerede er gjort."
