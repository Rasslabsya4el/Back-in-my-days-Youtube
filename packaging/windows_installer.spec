# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

PROJECT_ROOT = Path(SPECPATH).resolve().parent
APP_NAME = "Back in my days Youtube"
DIST_NAME = "Back in my days Youtube Installer Payload"
ENTRY_SCRIPT = PROJECT_ROOT / "main.py"
ICON_PATH = PROJECT_ROOT / "app" / "assets" / "icons" / "back-in-my-days-youtube.ico"
MEDIA_STAGING_ROOT_ENV = "BACK_IN_MY_DAYS_YOUTUBE_PORTABLE_MEDIA_STAGING_ROOT"
WEBVIEW2_STAGING_ROOT_ENV = "BACK_IN_MY_DAYS_YOUTUBE_WINDOWS_INSTALLER_WEBVIEW2_STAGING_ROOT"
NODE_STAGING_ROOT_ENV = "BACK_IN_MY_DAYS_YOUTUBE_NODE_RUNTIME_STAGING_ROOT"


def _tool_candidates(name: str) -> tuple[Path, ...]:
    exe_name = f"{name}.exe"
    return (
        Path(exe_name),
        Path("bin") / exe_name,
        Path("ffmpeg") / exe_name,
        Path("ffmpeg") / "bin" / exe_name,
        Path("win-x64") / exe_name,
    )


def _resolve_tool(root: Path, name: str) -> Path | None:
    for suffix in _tool_candidates(name):
        candidate = root / suffix
        if candidate.is_file():
            return candidate.resolve()
    return None


def _require_staged_media_tools() -> Path:
    staging_root_value = os.environ.get(MEDIA_STAGING_ROOT_ENV, "").strip()
    if not staging_root_value:
        raise SystemExit(
            "Windows installer build requires staged media tools. "
            f"Set {MEDIA_STAGING_ROOT_ENV} via scripts/build_windows_installer.ps1."
        )

    staging_root = Path(staging_root_value).expanduser().resolve()
    staged_tools_dir = staging_root / "app" / "bin"
    if not staged_tools_dir.is_dir():
        raise SystemExit(
            f"Staged media-tools root is missing: {staged_tools_dir}. "
            "Run scripts/build_windows_installer.ps1 to prepare the bundle."
        )

    missing_tools = [
        tool_name
        for tool_name in ("ffmpeg", "ffprobe")
        if _resolve_tool(staged_tools_dir, tool_name) is None
    ]
    if missing_tools:
        raise SystemExit(
            "Windows installer build is missing bundled media tools after staging. "
            f"Missing: {', '.join(missing_tools)} under {staged_tools_dir}."
        )
    return staged_tools_dir


def _require_staged_webview2_runtime() -> Path:
    staging_root_value = os.environ.get(WEBVIEW2_STAGING_ROOT_ENV, "").strip()
    if not staging_root_value:
        raise SystemExit(
            "Windows installer build requires a staged fixed WebView2 Runtime. "
            f"Set {WEBVIEW2_STAGING_ROOT_ENV} via scripts/build_windows_installer.ps1."
        )

    staging_root = Path(staging_root_value).expanduser().resolve()
    staged_runtime_dir = staging_root / "webview2-fixed-runtime"
    browser_executable = staged_runtime_dir / "msedgewebview2.exe"
    if not browser_executable.is_file():
        raise SystemExit(
            f"Staged fixed WebView2 Runtime is missing: {browser_executable}. "
            "Run scripts/build_windows_installer.ps1 to prepare the bundle."
        )
    return staged_runtime_dir


def _require_staged_node_runtime() -> Path:
    staging_root_value = os.environ.get(NODE_STAGING_ROOT_ENV, "").strip()
    if not staging_root_value:
        raise SystemExit(
            "Windows installer build requires a staged Node.js runtime. "
            f"Set {NODE_STAGING_ROOT_ENV} via scripts/build_windows_installer.ps1."
        )

    node_path = Path(staging_root_value).expanduser().resolve() / "node-runtime" / "node.exe"
    if not node_path.is_file():
        raise SystemExit(
            f"Staged Node.js runtime is missing: {node_path}. "
            "Run scripts/build_windows_installer.ps1 to prepare the bundle."
        )
    return node_path.parent


STAGED_MEDIA_TOOLS_DIR = _require_staged_media_tools()
STAGED_WEBVIEW2_RUNTIME_DIR = _require_staged_webview2_runtime()
STAGED_NODE_RUNTIME_DIR = _require_staged_node_runtime()

datas = [
    (str(PROJECT_ROOT / "frontend" / "dist"), "frontend/dist"),
    (str(PROJECT_ROOT / "app" / "assets"), "app/assets"),
    (str(STAGED_MEDIA_TOOLS_DIR), "app/bin"),
    (str(STAGED_WEBVIEW2_RUNTIME_DIR), "webview2-fixed-runtime"),
    (str(STAGED_NODE_RUNTIME_DIR), "node-runtime"),
]
datas += collect_data_files("yt_dlp_ejs")

for optional_dir in ("tools", "vendor"):
    source_dir = PROJECT_ROOT / optional_dir
    if source_dir.exists():
        datas.append((str(source_dir), optional_dir))

hiddenimports = [
    "webview.platforms.edgechromium",
    "webview.platforms.winforms",
    "yt_dlp_ejs",
    "yt_dlp_ejs.yt.solver",
]
hiddenimports += collect_submodules("yt_dlp_ejs")


a = Analysis(
    [str(ENTRY_SCRIPT)],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(ICON_PATH),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=DIST_NAME,
)
