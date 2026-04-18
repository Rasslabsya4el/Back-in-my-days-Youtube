[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$specPath = Join-Path $repoRoot "packaging\\windows_portable.spec"
$artifactRoot = Join-Path $repoRoot "dist\\YT Downloader"
$artifactExe = Join-Path $artifactRoot "YT Downloader.exe"

Push-Location $repoRoot
try {
    poetry run python -c "import PyInstaller" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller is not available in the Poetry environment. Run 'poetry install --with packaging' first."
    }

    npm run build
    if ($LASTEXITCODE -ne 0) {
        throw "Frontend build failed."
    }

    poetry run pyinstaller $specPath --noconfirm --clean
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller build failed with exit code $LASTEXITCODE."
    }

    if (-not (Test-Path $artifactExe)) {
        throw "Expected packaged executable at $artifactExe"
    }

    Write-Host "ArtifactRoot=$artifactRoot"
    Write-Host "ArtifactExe=$artifactExe"
}
finally {
    Pop-Location
}
