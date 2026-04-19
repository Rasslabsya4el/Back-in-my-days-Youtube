[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$specPath = Join-Path $repoRoot "packaging\\windows_portable.spec"
$mediaToolsPrepScript = Join-Path $repoRoot "scripts\\prepare_windows_portable_media_tools.py"
$webView2PrepScript = Join-Path $repoRoot "scripts\\prepare_windows_portable_webview2_runtime.py"
$mediaToolsStagingRoot = Join-Path $repoRoot "build\\portable-media-tools"
$webView2StagingRoot = Join-Path $repoRoot "build\\portable-webview2-runtime"
$artifactRoot = Join-Path $repoRoot "dist\\Back in my days Youtube"
$artifactExe = Join-Path $artifactRoot "Back in my days Youtube.exe"
$previousPortableMediaStagingRoot = $env:BACK_IN_MY_DAYS_YOUTUBE_PORTABLE_MEDIA_STAGING_ROOT
$previousPortableWebView2StagingRoot = $env:BACK_IN_MY_DAYS_YOUTUBE_PORTABLE_WEBVIEW2_STAGING_ROOT

Push-Location $repoRoot
try {
    poetry run python -c "import PyInstaller" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller is not available in the Poetry environment. Run 'poetry install --with packaging' first."
    }

    poetry run python $mediaToolsPrepScript --staging-root $mediaToolsStagingRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Portable media-tools staging failed. Prepare BACK_IN_MY_DAYS_YOUTUBE_PORTABLE_MEDIA_TOOLS_DIR before building the portable artifact."
    }
    $env:BACK_IN_MY_DAYS_YOUTUBE_PORTABLE_MEDIA_STAGING_ROOT = $mediaToolsStagingRoot

    poetry run python $webView2PrepScript --staging-root $webView2StagingRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Portable WebView2 runtime staging failed."
    }
    $env:BACK_IN_MY_DAYS_YOUTUBE_PORTABLE_WEBVIEW2_STAGING_ROOT = $webView2StagingRoot

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
    Write-Host "PortableWebView2StagingRoot=$webView2StagingRoot"
}
finally {
    if ($null -ne $previousPortableMediaStagingRoot) {
        $env:BACK_IN_MY_DAYS_YOUTUBE_PORTABLE_MEDIA_STAGING_ROOT = $previousPortableMediaStagingRoot
    }
    else {
        Remove-Item Env:BACK_IN_MY_DAYS_YOUTUBE_PORTABLE_MEDIA_STAGING_ROOT -ErrorAction SilentlyContinue
    }
    if ($null -ne $previousPortableWebView2StagingRoot) {
        $env:BACK_IN_MY_DAYS_YOUTUBE_PORTABLE_WEBVIEW2_STAGING_ROOT = $previousPortableWebView2StagingRoot
    }
    else {
        Remove-Item Env:BACK_IN_MY_DAYS_YOUTUBE_PORTABLE_WEBVIEW2_STAGING_ROOT -ErrorAction SilentlyContinue
    }
    Pop-Location
}
