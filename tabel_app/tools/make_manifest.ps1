# Generate version.json (update manifest) from the two compiled installers.
# IMPORTANT: keep this script ASCII-only (Windows PowerShell 5.1 misreads UTF-8 w/o BOM),
# so we do NOT hardcode the Cyrillic installer names — we discover them in OutDir and
# classify by size (full build is much larger than lite). The Cyrillic names are read
# from the filesystem as string objects (safe) and written into version.json as UTF-8.
#
# Usage (from tabel_app/):
#   powershell -ExecutionPolicy Bypass -File tools\make_manifest.ps1 -Notes "What's new..."
# Result: <OutDir>\version.json  — upload it together with both *setup.exe to the
# public Yandex.Disk folder referenced by updater.YANDEX_PUBLIC_KEY.

param(
  [string]$Ver = "",
  [string]$Notes = "",
  [string]$OutDir = "C:\Users\$env:USERNAME\tabel_pkg\out"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot   # tabel_app/

if (-not $Ver) {
  $verFile = Join-Path $root "VERSION"
  if (Test-Path $verFile) { $Ver = ([System.IO.File]::ReadAllText($verFile)).Trim() }
}
if (-not $Ver) { throw "Version not set (pass -Ver or create tabel_app\VERSION)." }
$today = (Get-Date -Format "yyyy-MM-dd")

$setups = @(Get-ChildItem -Path $OutDir -Filter "*setup.exe" | Sort-Object Length -Descending)
if ($setups.Count -lt 2) { throw "Need two *setup.exe in $OutDir (full + lite). Found $($setups.Count)." }
$fullFile = $setups[0]                      # larger = full (with proezd/OCR)
$liteFile = $setups[$setups.Count - 1]      # smaller = lite

function Entry($f) {
  return [ordered]@{
    version = $Ver
    date    = $today
    path    = "/" + $f.Name                  # relative path inside the public Yandex folder
    size    = $f.Length
    sha256  = (Get-FileHash -Algorithm SHA256 -Path $f.FullName).Hash.ToLower()
    notes   = $Notes
  }
}

$manifest = [ordered]@{
  schema = 1
  latest = [ordered]@{ full = (Entry $fullFile); lite = (Entry $liteFile) }
}

$json = $manifest | ConvertTo-Json -Depth 6
$enc = New-Object System.Text.UTF8Encoding($false)   # UTF-8 without BOM
[System.IO.File]::WriteAllText((Join-Path $OutDir "version.json"), $json, $enc)
Write-Host "Wrote version.json (version $Ver):"
Write-Host ("  full -> " + $fullFile.Name)
Write-Host ("  lite -> " + $liteFile.Name)
Write-Host "Upload version.json + both setup.exe to the public Yandex.Disk folder."
