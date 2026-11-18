$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$InputFile = Join-Path $Root 'requirements-windows.in'
$LockFile = Join-Path $Root 'requirements-windows.lock'
$VenvDir = Join-Path $PSScriptRoot '.build-venv'
$BuildId = Get-Date -Format 'yyyyMMdd-HHmmss'
$ArtifactName = "Vartani-Windows-x64-$BuildId"
$ArtifactsDir = Join-Path $Root 'artifacts'
$ArtifactDir = Join-Path $ArtifactsDir $ArtifactName
$WorkDir = Join-Path $PSScriptRoot ".work-$BuildId"

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw 'The Windows artifact must be built on Windows.'
}
$PythonExe = $null
$PythonPrefix = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
    $VersionCheck = & py -3.11 -c "import platform,sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{platform.architecture()[0]}')" 2>$null
    if ($LASTEXITCODE -eq 0 -and $VersionCheck -eq '3.11.64bit') {
        $PythonExe = 'py'
        $PythonPrefix = @('-3.11')
    }
}
if (-not $PythonExe) {
    $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($PythonCommand) {
        $VersionCheck = & $PythonCommand.Source -c "import platform,sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{platform.architecture()[0]}')" 2>$null
        if ($LASTEXITCODE -eq 0 -and $VersionCheck -eq '3.11.64bit') { $PythonExe = $PythonCommand.Source }
    }
}
if (-not $PythonExe) {
    throw "Python 3.11 x64 is required on the build machine; found '$VersionCheck'. Install it from python.org, then rerun this script."
}

if (-not (Test-Path $LockFile)) {
    throw "Missing $LockFile. See docs/windows-build.md for how to generate the tested dependency lock."
}
if (Test-Path $VenvDir) {
    $BuildPython = Join-Path $VenvDir 'Scripts\python.exe'
} else {
    Write-Progress -Activity 'Preparing Windows build' -Status 'Creating isolated build environment' -PercentComplete 10
    & $PythonExe @PythonPrefix -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the isolated build environment. Check disk space and retry.' }
    $BuildPython = Join-Path $VenvDir 'Scripts\python.exe'
}

Write-Progress -Activity 'Preparing Windows build' -Status 'Installing locked build dependencies (internet required on the build machine)' -PercentComplete 25
& $BuildPython -m pip install --disable-pip-version-check -r $LockFile
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check the network, disk space, and the pip error above, then rerun; the build environment can be reused.' }
& $BuildPython -m pip check
if ($LASTEXITCODE -ne 0) { throw 'The locked build dependencies are inconsistent. Refresh requirements-windows.lock and retry.' }

Write-Progress -Activity 'Preparing Windows build' -Status 'Running automated tests' -PercentComplete 45
Push-Location $Root
try {
    & $BuildPython -m pytest -q tests/test_core.py tests/test_windows_launcher.py
    if ($LASTEXITCODE -ne 0) { throw 'Automated checks failed; no Windows artifact was created.' }
} finally { Pop-Location }

New-Item -ItemType Directory -Path $ArtifactsDir -Force | Out-Null
if (Test-Path $ArtifactDir) { throw "Refusing to replace existing output folder $ArtifactDir" }
New-Item -ItemType Directory -Path $ArtifactDir | Out-Null
Write-Progress -Activity 'Preparing Windows build' -Status 'Bundling Vartani and its Python runtime' -PercentComplete 65
& $BuildPython -m PyInstaller --clean --noconfirm --distpath $ArtifactDir --workpath $WorkDir (Join-Path $PSScriptRoot 'vartani.spec')
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed. Review its diagnostic above; retry with a fresh build timestamp. Output: $ArtifactDir" }

$BundleDir = Join-Path $ArtifactDir 'Vartani'
$Launcher = Join-Path $BundleDir 'Vartani.exe'
if (-not (Test-Path $Launcher)) { throw "PyInstaller did not produce $Launcher" }
$SmokeLog = Join-Path $ArtifactDir 'packaged-smoke.log'
Write-Progress -Activity 'Preparing Windows build' -Status 'Checking the packaged app and bundled resources' -PercentComplete 85
$Smoke = Start-Process -FilePath $Launcher -ArgumentList @('--smoke-test', ('"{0}"' -f $SmokeLog)) -PassThru -Wait
if ($Smoke.ExitCode -ne 0) {
    $Details = if (Test-Path $SmokeLog) { Get-Content $SmokeLog -Raw } else { 'No smoke-test details were written.' }
    throw "Packaged artifact smoke check failed: $Details"
}
Remove-Item -LiteralPath $SmokeLog -Force -ErrorAction SilentlyContinue

$ZipPath = Join-Path $ArtifactsDir "$ArtifactName.zip"
if (Test-Path $ZipPath) { throw "Refusing to replace existing artifact $ZipPath" }
Write-Progress -Activity 'Preparing Windows build' -Status 'Creating the distributable ZIP' -PercentComplete 95
Compress-Archive -Path $BundleDir -DestinationPath $ZipPath -CompressionLevel Optimal
Write-Progress -Activity 'Preparing Windows build' -Completed
Write-Host "Windows package created: $ZipPath"
Write-Host 'The package contains Vartani.exe plus its bundled runtime. End users do not need Python.'
