from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STAGING_ROOT = PROJECT_ROOT / "build" / "portable-webview2-runtime"
DISCOVERY_URL = "https://developer.microsoft.com/en-us/microsoft-edge/webview2?form=MA13LH"
ARCH = "x64"
SOURCE_URL_ENV_VAR = "BACK_IN_MY_DAYS_YOUTUBE_PORTABLE_WEBVIEW2_RUNTIME_URL"
SOURCE_CAB_ENV_VAR = "BACK_IN_MY_DAYS_YOUTUBE_PORTABLE_WEBVIEW2_RUNTIME_CAB"


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _discover_runtime_download() -> tuple[str, str]:
    override_url = os.environ.get(SOURCE_URL_ENV_VAR, "").strip()
    if override_url:
        version_match = re.search(
            r"Microsoft\.WebView2\.FixedVersionRuntime\.([0-9.]+)\." + ARCH + r"\.cab",
            override_url,
        )
        return override_url, version_match.group(1) if version_match else ""

    try:
        html = urllib.request.urlopen(DISCOVERY_URL).read().decode("utf-8", errors="ignore")
    except Exception as error:
        raise RuntimeError(f"Unable to fetch WebView2 download metadata from {DISCOVERY_URL} ({error}).")

    matches = re.findall(
        rf"(https:[^\"<>]*Microsoft\.WebView2\.FixedVersionRuntime\.([0-9.]+)\.{ARCH}\.cab)",
        html,
    )
    if not matches:
        raise RuntimeError(
            "Unable to discover an official fixed WebView2 Runtime download URL for Windows x64."
        )

    resolved_url, version = max(matches, key=lambda item: _version_key(item[1]))
    return resolved_url.replace("\\u002F", "/"), version


def _resolve_source_cab(staging_root: Path) -> tuple[Path, dict[str, str]]:
    explicit_cab_value = os.environ.get(SOURCE_CAB_ENV_VAR, "").strip()
    if explicit_cab_value:
        cab_path = Path(explicit_cab_value).expanduser().resolve()
        if not cab_path.is_file():
            raise RuntimeError(f"{SOURCE_CAB_ENV_VAR} must point to an existing CAB file: {cab_path}")
        version_match = re.search(
            r"Microsoft\.WebView2\.FixedVersionRuntime\.([0-9.]+)\." + ARCH + r"\.cab",
            cab_path.name,
        )
        return cab_path, {
            "source_kind": "cab",
            "version": version_match.group(1) if version_match else "",
            "download_url": "",
        }

    download_url, version = _discover_runtime_download()
    download_root = staging_root.parent / "portable-webview2-downloads"
    download_root.mkdir(parents=True, exist_ok=True)
    cab_path = download_root / download_url.rsplit("/", 1)[-1]
    if not cab_path.exists():
        try:
            urllib.request.urlretrieve(download_url, cab_path)
        except Exception as error:
            raise RuntimeError(f"Unable to download fixed WebView2 Runtime from {download_url} ({error}).")
    return cab_path.resolve(), {
        "source_kind": "download",
        "version": version,
        "download_url": download_url,
    }


def _extract_runtime_root(*, cab_path: Path, extract_root: Path) -> Path:
    if extract_root.exists():
        shutil.rmtree(extract_root)
    extract_root.mkdir(parents=True, exist_ok=True)

    try:
        subprocess.run(
            ["expand.exe", "-F:*", str(cab_path), str(extract_root)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError as error:
        raise RuntimeError(
            f"Failed to extract fixed WebView2 Runtime CAB {cab_path} ({error.stderr.strip() or error.stdout.strip()})."
        )

    matches = sorted(path.parent for path in extract_root.rglob("msedgewebview2.exe"))
    if not matches:
        raise RuntimeError(f"Extracted CAB {cab_path} does not contain msedgewebview2.exe.")
    return matches[0].resolve()


def _infer_runtime_version(*, metadata_version: str, runtime_root: Path) -> str:
    if metadata_version:
        return metadata_version
    match = re.search(r"([0-9]+(?:\.[0-9]+){3,})", runtime_root.name)
    if match:
        return match.group(1)
    return ""


def _stage_runtime(*, runtime_root: Path, staging_root: Path, metadata: dict[str, str]) -> dict[str, str]:
    if staging_root.exists():
        shutil.rmtree(staging_root)

    staged_runtime_dir = staging_root / "webview2-fixed-runtime"
    staged_runtime_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(runtime_root, staged_runtime_dir)

    staged_browser = staged_runtime_dir / "msedgewebview2.exe"
    if not staged_browser.is_file():
        raise RuntimeError(
            f"Staged fixed WebView2 Runtime is incomplete: missing {staged_browser}."
        )

    manifest = {
        "architecture": ARCH,
        "source_cab_env_var": SOURCE_CAB_ENV_VAR,
        "source_url_env_var": SOURCE_URL_ENV_VAR,
        "source_kind": metadata["source_kind"],
        "version": metadata["version"],
        "download_url": metadata["download_url"],
        "runtime_root": str(runtime_root),
        "staging_root": str(staging_root),
        "staged_runtime_dir": str(staged_runtime_dir),
        "browser_executable": str(staged_browser),
    }
    (staging_root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stage a fixed Microsoft WebView2 Runtime for the portable Windows build."
    )
    parser.add_argument(
        "--staging-root",
        default=str(DEFAULT_STAGING_ROOT),
        help="Build-local staging root for PyInstaller datas.",
    )
    args = parser.parse_args()

    try:
        staging_root = Path(args.staging_root).expanduser().resolve()
        cab_path, metadata = _resolve_source_cab(staging_root)
        extract_root = staging_root.parent / "portable-webview2-extracted"
        runtime_root = _extract_runtime_root(cab_path=cab_path, extract_root=extract_root)
        metadata["version"] = _infer_runtime_version(
            metadata_version=metadata["version"],
            runtime_root=runtime_root,
        )
        manifest = _stage_runtime(runtime_root=runtime_root, staging_root=staging_root, metadata=metadata)
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 1

    print(f"PortableWebView2SourceKind={manifest['source_kind']}")
    print(f"PortableWebView2Version={manifest['version']}")
    print(f"PortableWebView2StagingRoot={manifest['staging_root']}")
    print(f"PortableWebView2Manifest={staging_root / 'manifest.json'}")
    print(f"PortableWebView2BrowserExecutable={manifest['browser_executable']}")
    if manifest["download_url"]:
        print(f"PortableWebView2DownloadUrl={manifest['download_url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
