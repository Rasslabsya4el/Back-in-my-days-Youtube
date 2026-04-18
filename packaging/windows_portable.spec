# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

PROJECT_ROOT = Path(SPECPATH).resolve().parent
APP_NAME = "YT Downloader"
ENTRY_SCRIPT = PROJECT_ROOT / "main.py"
ICON_PATH = PROJECT_ROOT / "app" / "assets" / "icons" / "yt-downloader.ico"
MEDIA_STAGING_ROOT_ENV = "YT_PORTABLE_MEDIA_STAGING_ROOT"


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
            "Portable Windows build requires staged media tools. "
            f"Set {MEDIA_STAGING_ROOT_ENV} via scripts/build_windows_portable.ps1."
        )

    staging_root = Path(staging_root_value).expanduser().resolve()
    staged_tools_dir = staging_root / "app" / "bin"
    if not staged_tools_dir.is_dir():
        raise SystemExit(
            f"Staged media-tools root is missing: {staged_tools_dir}. "
            "Run scripts/build_windows_portable.ps1 to prepare the bundle."
        )

    missing_tools = [
        tool_name
        for tool_name in ("ffmpeg", "ffprobe")
        if _resolve_tool(staged_tools_dir, tool_name) is None
    ]
    if missing_tools:
        raise SystemExit(
            "Portable Windows build is missing bundled media tools after staging. "
            f"Missing: {', '.join(missing_tools)} under {staged_tools_dir}."
        )
    return staged_tools_dir


STAGED_MEDIA_TOOLS_DIR = _require_staged_media_tools()

datas = [
    (str(PROJECT_ROOT / "frontend" / "dist"), "frontend/dist"),
    (str(PROJECT_ROOT / "app" / "assets"), "app/assets"),
    (str(STAGED_MEDIA_TOOLS_DIR), "app/bin"),
]

for optional_dir in ("tools", "vendor"):
    source_dir = PROJECT_ROOT / optional_dir
    if source_dir.exists():
        datas.append((str(source_dir), optional_dir))

hiddenimports = [
    "webview.platforms.edgechromium",
    "webview.platforms.winforms",
]


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
    name=APP_NAME,
)
