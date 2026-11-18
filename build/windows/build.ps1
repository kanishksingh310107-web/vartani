param([string]$RuntimeArchive)

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Artifacts = Join-Path $Root 'artifacts'
$BuildId = Get-Date -Format 'yyyyMMdd-HHmmss'
$Stage = Join-Path $Artifacts "Vartani-Windows-x64-$BuildId"
$Bundle = Join-Path $Stage 'Vartani'
$App = Join-Path $Bundle 'app'
$BuildLock = Join-Path $Root 'requirements-windows.lock'
$Hash = '0DC3A404D4D6501F3B8F99D58354410A0B1699DD5C21070778A594DB02070DD3'
$RuntimeUrl = 'https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.11.16%2B20260924-x86_64-pc-windows-msvc-install_only.tar.gz'
$Compiler = Join-Path $env:SystemRoot 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -or -not (Test-Path -LiteralPath $Compiler)) {
    throw 'Build on 64-bit Windows with the .NET Framework C# compiler available.'
}
if (-not (Test-Path -LiteralPath (Join-Path $Root 'frontend\node_modules\vite\bin\vite.js'))) {
    throw 'Install the frontend build dependencies first with npm ci in the frontend folder.'
}
if ($RuntimeArchive) { $RuntimeArchive = (Resolve-Path -LiteralPath $RuntimeArchive).Path }
New-Item -ItemType Directory -Path $Artifacts -Force | Out-Null
New-Item -ItemType Directory -Path $Stage | Out-Null
New-Item -ItemType Directory -Path $App -Force | Out-Null

Write-Host 'Building the frontend...'
Push-Location (Join-Path $Root 'frontend')
try {
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
} finally { Pop-Location }

if (-not $RuntimeArchive) {
    $RuntimeArchive = Join-Path $Stage 'python-runtime.tar.gz'
    & curl.exe --fail --location --retry 2 --connect-timeout 15 --max-time 180 --output $RuntimeArchive $RuntimeUrl
    if ($LASTEXITCODE -ne 0) { throw 'Python runtime download failed. Check your network and retry.' }
}
if ((Get-FileHash -LiteralPath $RuntimeArchive -Algorithm SHA256).Hash -ne $Hash) {
    throw 'The Python runtime archive does not match its pinned SHA-256 checksum.'
}
& tar.exe '-xzf' $RuntimeArchive '--exclude=*.pdb' '-C' $Bundle
if ($LASTEXITCODE -ne 0) { throw 'Could not extract the Python runtime. Free disk space and retry.' }
$Python = Join-Path $Bundle 'python\python.exe'

Write-Host 'Installing locked core dependencies and running the test suite...'
& $Python -m venv (Join-Path $Stage 'test-venv')
if ($LASTEXITCODE -ne 0) { throw 'Could not create the test environment.' }
$TestPython = Join-Path $Stage 'test-venv\Scripts\python.exe'
& $TestPython -m pip install --no-input --disable-pip-version-check --only-binary=:all: -r $BuildLock
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check your network and free disk space, then retry.' }
Push-Location $Root
try {
    & $TestPython -B -m pytest -q -p no:cacheprovider tests
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed. The package was not published.' }
} finally { Pop-Location }

$CoreLock = Join-Path $Stage 'core.lock'
Get-Content -LiteralPath $BuildLock |
    Where-Object { $_ -notmatch '^(iniconfig|pluggy|pytest)==' } |
    Set-Content -LiteralPath $CoreLock -Encoding ascii
& $Python -m pip install --no-input --disable-pip-version-check --only-binary=:all: -r $CoreLock
if ($LASTEXITCODE -ne 0) { throw 'Could not populate the portable Python runtime.' }
& $Python -m pip check
if ($LASTEXITCODE -ne 0) { throw 'The bundled core dependencies are inconsistent.' }
foreach ($Name in @('launcher.py','README.md','requirements-speech.txt','requirements-local-models.txt','requirements-windows.lock','docs','web','vartani')) {
    Copy-Item -LiteralPath (Join-Path $Root $Name) -Destination $App -Recurse
}
$Data = New-Item -ItemType Directory -Path (Join-Path $App 'data')
foreach ($Name in @('starter','paper')) {
    Copy-Item -LiteralPath (Join-Path $Root "data\$Name") -Destination $Data.FullName -Recurse
}

$Launcher = Join-Path $Bundle 'Vartani.exe'
& $Compiler /nologo /target:winexe /platform:x64 /reference:System.Windows.Forms.dll "/out:$Launcher" (Join-Path $PSScriptRoot 'Vartani.cs')
if ($LASTEXITCODE -ne 0) { throw 'Could not compile Vartani.exe.' }
$SmokeLog = Join-Path $Stage 'packaged-smoke.log'
$Smoke = Start-Process -FilePath $Launcher -ArgumentList @('--smoke-test', ('"{0}"' -f $SmokeLog)) -WindowStyle Hidden -PassThru -Wait
if (Test-Path -LiteralPath $SmokeLog) { Get-Content -LiteralPath $SmokeLog }
if ($Smoke.ExitCode -ne 0) { throw 'The packaged smoke test failed.' }

Add-Type -AssemblyName System.IO.Compression.FileSystem
$ZipPath = "$Stage.zip"
[IO.Compression.ZipFile]::CreateFromDirectory($Bundle, $ZipPath, [IO.Compression.CompressionLevel]::Optimal, $true)
Write-Host "Windows package created: $ZipPath"
