# Build both installers on Windows, then create a matching GitHub manifest.
param(
  [string]$OutDir = (Join-Path $env:RUNNER_TEMP "tabel-release"),
  [string]$Repository = "TasFoster/TABEL_soc.work"
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$version = ([IO.File]::ReadAllText((Join-Path $root 'VERSION'))).Trim()
if ($version -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid VERSION' }
$out = [IO.Path]::GetFullPath($OutDir)
New-Item -ItemType Directory -Force $out | Out-Null
$iscc = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'
if (-not (Test-Path $iscc)) { throw 'Inno Setup 6 is required' }
$utf8 = New-Object Text.UTF8Encoding($false)
foreach ($variant in @('full', 'lite')) {
  $build = Join-Path $env:TEMP "tabel-build-$variant"
  # Run in a child shell: build.ps1 changes its working directory.
  & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'build.ps1') -Variant $variant -BuildDir $build
  if ($LASTEXITCODE -ne 0) { throw "Build failed: $variant" }
  $exe = Join-Path $build 'dist\Tabel.exe'
  $smoke = Start-Process -FilePath $exe -ArgumentList @('--selftest-release', $variant, $version) -PassThru
  if (-not $smoke.WaitForExit(120000)) { $smoke.Kill(); throw 'Frozen smoke test timed out' }
  $resultFile = Join-Path $build 'dist\selftest_release_result.json'
  if (-not (Test-Path $resultFile)) { throw 'Frozen smoke test produced no result' }
  $result = [IO.File]::ReadAllText($resultFile) | ConvertFrom-Json
  if (-not $result.ok) { throw "Frozen smoke test failed: $($result.error)" }
  $stage = Join-Path $out "stage-$variant"
  New-Item -ItemType Directory -Force (Join-Path $stage 'data') | Out-Null
  Copy-Item (Join-Path $build 'dist\Tabel.exe') (Join-Path $stage 'Tabel.exe')
  # Never package a developer's live database or generated documents.
  [IO.File]::WriteAllText((Join-Path $stage 'instruction.txt'), "Tabel $version ($variant)`r`nStart Tabel.exe. Existing user data is preserved on update.`r`n", $utf8)
  [IO.File]::WriteAllText((Join-Path $stage 'data\README.txt'), "User data is created on first launch.`r`n", $utf8)
  $script = Join-Path $root "installer\$variant.iss"
  & $iscc "/DAppVer=$version" "/DSrcDir=$stage" "/DOutDir=$out" "/DSetupName=Tabel-$variant-setup" $script
  if ($LASTEXITCODE -ne 0) { throw "Installer compilation failed: $variant" }
}
& python (Join-Path $PSScriptRoot 'make_manifest.py') --version $version --repository $Repository --full (Join-Path $out 'Tabel-full-setup.exe') --lite (Join-Path $out 'Tabel-lite-setup.exe') --out (Join-Path $out 'version.json') --notes-file (Join-Path $root 'RELEASE_NOTES.md')
if ($LASTEXITCODE -ne 0) { throw 'Manifest generation failed' }
Write-Host "Release $version built in $out"
