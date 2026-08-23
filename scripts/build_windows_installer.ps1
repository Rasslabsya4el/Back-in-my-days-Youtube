[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$specPath = Join-Path $repoRoot "packaging\\windows_installer.spec"
$issPath = Join-Path $repoRoot "packaging\\windows_installer.iss"
$mediaToolsPrepScript = Join-Path $repoRoot "scripts\\prepare_windows_portable_media_tools.py"
$webView2PrepScript = Join-Path $repoRoot "scripts\\prepare_windows_portable_webview2_runtime.py"
$mediaToolsStagingRoot = Join-Path $repoRoot "build\\portable-media-tools"
$webView2StagingRoot = Join-Path $repoRoot "build\\installer-webview2-runtime"
$nodeStagingRoot = Join-Path $repoRoot "build\\installer-node-runtime"
$nodePath = Join-Path $nodeStagingRoot "node-runtime\\node.exe"
$payloadRoot = Join-Path $repoRoot "dist\\Back in my days Youtube Installer Payload"
$setupExe = Join-Path $repoRoot "dist\\Back in my days Youtube Setup.exe"
$isccPath = "C:\\Users\\user\\AppData\\Local\\Programs\\Inno Setup 6\\ISCC.exe"
$previousPortableMediaStagingRoot = $env:BACK_IN_MY_DAYS_YOUTUBE_PORTABLE_MEDIA_STAGING_ROOT
$previousInstallerWebView2StagingRoot = $env:BACK_IN_MY_DAYS_YOUTUBE_WINDOWS_INSTALLER_WEBVIEW2_STAGING_ROOT
$previousNodeStagingRoot = $env:BACK_IN_MY_DAYS_YOUTUBE_NODE_RUNTIME_STAGING_ROOT

Push-Location $repoRoot
try {
    if (-not (Test-Path $isccPath)) {
        throw "ISCC.exe is not available at $isccPath. Install Inno Setup 6 first."
    }

    poetry run python -c "import PyInstaller" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller is not available in the Poetry environment. Run 'poetry install --with packaging' first."
    }

    poetry run python $mediaToolsPrepScript --staging-root $mediaToolsStagingRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Portable media-tools staging failed. Prepare BACK_IN_MY_DAYS_YOUTUBE_PORTABLE_MEDIA_TOOLS_DIR before building the installer artifact."
    }
    $env:BACK_IN_MY_DAYS_YOUTUBE_PORTABLE_MEDIA_STAGING_ROOT = $mediaToolsStagingRoot

    poetry run python $webView2PrepScript --staging-root $webView2StagingRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Installer WebView2 runtime staging failed."
    }
    $env:BACK_IN_MY_DAYS_YOUTUBE_WINDOWS_INSTALLER_WEBVIEW2_STAGING_ROOT = $webView2StagingRoot

    $nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
    if ($null -eq $nodeCommand) {
        throw "Node.js 22+ is required on the build machine to provide yt-dlp YouTube JavaScript support."
    }
    $nodeVersionText = (& $nodeCommand.Source --version 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $nodeVersionText -notmatch '^v(?<major>\d+)\.') {
        throw "Could not determine the Node.js version from $($nodeCommand.Source). Node.js 22+ is required."
    }
    if ([int]$Matches.major -lt 22) {
        throw "Node.js 22+ is required on the build machine; detected $nodeVersionText."
    }
    if (Test-Path $nodeStagingRoot) {
        Remove-Item -LiteralPath $nodeStagingRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Path (Split-Path $nodePath -Parent) -Force | Out-Null
    Copy-Item -LiteralPath $nodeCommand.Source -Destination $nodePath
    $env:BACK_IN_MY_DAYS_YOUTUBE_NODE_RUNTIME_STAGING_ROOT = $nodeStagingRoot

    npm run build
    if ($LASTEXITCODE -ne 0) {
        throw "Frontend build failed."
    }

    poetry run pyinstaller $specPath --noconfirm --clean
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller build failed with exit code $LASTEXITCODE."
    }

    if (-not (Test-Path $payloadRoot)) {
        throw "Expected installer payload at $payloadRoot"
    }

    & $isccPath $issPath | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup build failed with exit code $LASTEXITCODE."
    }

    if (-not (Test-Path $setupExe)) {
        throw "Expected setup executable at $setupExe"
    }

    Write-Host "InstallerPayloadRoot=$payloadRoot"
    Write-Host "InstallerWebView2StagingRoot=$webView2StagingRoot"
    Write-Host "SetupExe=$setupExe"
}
finally {
    if ($null -ne $previousPortableMediaStagingRoot) {
        $env:BACK_IN_MY_DAYS_YOUTUBE_PORTABLE_MEDIA_STAGING_ROOT = $previousPortableMediaStagingRoot
    }
    else {
        Remove-Item Env:BACK_IN_MY_DAYS_YOUTUBE_PORTABLE_MEDIA_STAGING_ROOT -ErrorAction SilentlyContinue
    }
    if ($null -ne $previousInstallerWebView2StagingRoot) {
        $env:BACK_IN_MY_DAYS_YOUTUBE_WINDOWS_INSTALLER_WEBVIEW2_STAGING_ROOT = $previousInstallerWebView2StagingRoot
    }
    else {
        Remove-Item Env:BACK_IN_MY_DAYS_YOUTUBE_WINDOWS_INSTALLER_WEBVIEW2_STAGING_ROOT -ErrorAction SilentlyContinue
    }
    if ($null -ne $previousNodeStagingRoot) {
        $env:BACK_IN_MY_DAYS_YOUTUBE_NODE_RUNTIME_STAGING_ROOT = $previousNodeStagingRoot
    }
    else {
        Remove-Item Env:BACK_IN_MY_DAYS_YOUTUBE_NODE_RUNTIME_STAGING_ROOT -ErrorAction SilentlyContinue
    }
    Pop-Location
}
