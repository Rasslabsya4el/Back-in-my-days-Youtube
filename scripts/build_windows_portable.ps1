[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$specPath = Join-Path $repoRoot "packaging\\windows_portable.spec"
$mediaToolsPrepScript = Join-Path $repoRoot "scripts\\prepare_windows_portable_media_tools.py"
$mediaToolsStagingRoot = Join-Path $repoRoot "build\\portable-media-tools"
$artifactRoot = Join-Path $repoRoot "dist\\YT Downloader"
$artifactExe = Join-Path $artifactRoot "YT Downloader.exe"
$previousPortableMediaStagingRoot = $env:YT_PORTABLE_MEDIA_STAGING_ROOT

Push-Location $repoRoot
try {
    poetry run python -c "import PyInstaller" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller is not available in the Poetry environment. Run 'poetry install --with packaging' first."
    }

    poetry run python $mediaToolsPrepScript --staging-root $mediaToolsStagingRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Portable media-tools staging failed. Prepare YT_PORTABLE_MEDIA_TOOLS_DIR before building the portable artifact."
    }
    $env:YT_PORTABLE_MEDIA_STAGING_ROOT = $mediaToolsStagingRoot

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
    Write-Host "PortableMediaToolsStagingRoot=$mediaToolsStagingRoot"
}
finally {
    if ($null -ne $previousPortableMediaStagingRoot) {
        $env:YT_PORTABLE_MEDIA_STAGING_ROOT = $previousPortableMediaStagingRoot
    }
    else {
        Remove-Item Env:YT_PORTABLE_MEDIA_STAGING_ROOT -ErrorAction SilentlyContinue
    }
    Pop-Location
}
