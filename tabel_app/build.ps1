# Build the "Tabel" application into a single .exe.
# The project path contains Cyrillic, which breaks PyInstaller, so we copy the
# sources into an ASCII folder, build there, and report the resulting .exe.
# NOTE: keep this script ASCII-only (Windows PowerShell 5.1 misreads UTF-8 w/o BOM).
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File build.ps1            # full (4 features, OCR)
#   powershell -ExecutionPolicy Bypass -File build.ps1 -Variant lite   # 3 features, no proezd/OCR
# Result: <build>\dist\Tabel.exe  (packaging into a delivery folder is done separately).

param([string]$Variant = "full")

$ErrorActionPreference = "Stop"
$src = $PSScriptRoot
$build = "C:\Users\$env:USERNAME\tabel_build"

Write-Host "Variant: $Variant"
Write-Host "Source: $src"
Write-Host "Build dir: $build"

if (Test-Path $build) { Remove-Item -Recurse -Force $build }
New-Item -ItemType Directory -Path $build | Out-Null
robocopy $src $build /E /XD build dist __pycache__ /XF *.spec /NFL /NDL /NJH /NJS /NP | Out-Null

Set-Location $build

# Stamp version from VERSION into version.py (fallback for one-file .exe where VERSION is absent).
# Read/write as UTF-8 (no BOM) so Cyrillic comments survive (do NOT use Get/Set-Content here).
$verFile = Join-Path $src "VERSION"
if (Test-Path $verFile) {
  $ver = ([System.IO.File]::ReadAllText($verFile)).Trim()
  $today = (Get-Date -Format "yyyy-MM-dd")
  $vp = Join-Path $build "app\core\version.py"
  $enc = New-Object System.Text.UTF8Encoding($false)
  $txt = [System.IO.File]::ReadAllText($vp, [System.Text.Encoding]::UTF8)
  $txt = [System.Text.RegularExpressions.Regex]::Replace($txt, '_EMBEDDED_VERSION = "[^"]*"', "_EMBEDDED_VERSION = `"$ver`"")
  $txt = [System.Text.RegularExpressions.Regex]::Replace($txt, 'APP_RELEASE_DATE = "[^"]*"', "APP_RELEASE_DATE = `"$today`"")
  [System.IO.File]::WriteAllText($vp, $txt, $enc)
  Write-Host "Stamped version: $ver ($today)"
}

$ts = 'app/features/timesheet'
$re = 'app/features/reestr'
$pr = 'app/features/prilozhenie'
$pz = 'app/features/proezd'
$ud = 'app/features/uslugi_dengi'
$gz = 'app/features/gos_zadanie'
$pl = 'app/features/plany'

# Common args + data for the 3 always-present features.
$common = @(
  '--noconfirm', '--windowed', '--onefile', '--name', 'Tabel',
  '--add-data', "$ts/templates/t13_template.xls;features/timesheet/templates",
  '--add-data', "$ts/data/departments.json;features/timesheet/data",
  '--add-data', "$ts/data/settings.json;features/timesheet/data",
  '--add-data', "$ts/data/calendar.json;features/timesheet/data",
  '--add-data', "$re/templates/reestr_template.ods;features/reestr/templates",
  '--add-data', "$re/data/settings.json;features/reestr/data",
  '--add-data', "$re/data/grouping_seed.json;features/reestr/data",
  '--add-data', "$pr/data/loads_seed.json;features/prilozhenie/data",
  '--add-data', "$ud/templates/uslugi_dengi_template.xlsx;features/uslugi_dengi/templates",
  '--add-data', "$gz/data/services_seed.json;features/gos_zadanie/data",
  '--add-data', "$pl/data/plany_templates.json;features/plany/data",
  '--hidden-import', 'xlrd', '--hidden-import', 'sqlite3',
  '--collect-submodules', 'xlwt', '--collect-submodules', 'odf',
  '--collect-submodules', 'openpyxl',
  # CustomTkinter (главное меню, Фаза 6): нужны его JSON-темы (--collect-data) и darkdetect.
  '--collect-data', 'customtkinter', '--collect-submodules', 'customtkinter',
  '--hidden-import', 'darkdetect'
)

if ($Variant -eq 'lite') {
  # No "Proezd": exclude its package and the heavy OCR deps; do not bundle its data.
  $pyiArgs = $common + @(
    '--exclude-module', 'app.features.proezd',
    '--exclude-module', 'cv2', '--exclude-module', 'winrt', '--exclude-module', 'numpy',
    'main.py'
  )
} else {
  # Full: all features incl. Proezd; collect the whole app package and OCR deps.
  # winrt (Windows OCR projections) is lazily imported inside functions, so PyInstaller
  # does not auto-detect it -> collect it explicitly (native runtime + winrt.windows.*).
  # cv2/numpy are picked up by their PyInstaller hooks via import detection.
  $pyiArgs = $common + @(
    '--collect-submodules', 'app',
    '--collect-all', 'winrt',
    '--add-data', "$pz/templates/proezd_template.ods;features/proezd/templates",
    '--add-data', "$pz/data/settings.json;features/proezd/data",
    'main.py'
  )
}

& pyinstaller @pyiArgs

$exe = Join-Path $build "dist\Tabel.exe"
if (Test-Path $exe) {
    Write-Host "DONE ($Variant): $exe"
} else {
    Write-Host "ERROR: exe was not created."
}
