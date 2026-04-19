from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STAGING_ROOT = PROJECT_ROOT / "build" / "portable-media-tools"
SOURCE_ENV_VAR = "BACK_IN_MY_DAYS_YOUTUBE_PORTABLE_MEDIA_TOOLS_DIR"


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


def _require_source_root() -> tuple[Path, dict[str, Path]]:
    source_value = os.environ.get(SOURCE_ENV_VAR, "").strip()
    if not source_value:
        raise RuntimeError(
            f"{SOURCE_ENV_VAR} is not set. Portable Windows builds require an explicit FFmpeg bundle root."
        )

    source_root = Path(source_value).expanduser().resolve()
    if not source_root.is_dir():
        raise RuntimeError(f"{SOURCE_ENV_VAR} must point to an existing directory: {source_root}")

    resolved_tools = {
        tool_name: _resolve_tool(source_root, tool_name)
        for tool_name in ("ffmpeg", "ffprobe")
    }
    missing_tools = [tool_name for tool_name, tool_path in resolved_tools.items() if tool_path is None]
    if missing_tools:
        expected_locations = ", ".join(str(path).replace("\\", "/") for path in _tool_candidates("ffmpeg"))
        raise RuntimeError(
            "Portable media-tools root is incomplete. "
            f"Missing: {', '.join(missing_tools)} under {source_root}. "
            "Expected one of the supported layouts relative to the root, such as "
            f"{expected_locations}."
        )

    return source_root, {name: path for name, path in resolved_tools.items() if path is not None}


def _stage_bundle(*, source_root: Path, staging_root: Path, source_tools: dict[str, Path]) -> dict[str, object]:
    if staging_root.exists():
        shutil.rmtree(staging_root)

    staged_tools_dir = staging_root / "app" / "bin"
    staged_tools_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_root, staged_tools_dir)

    staged_tools = {
        tool_name: _resolve_tool(staged_tools_dir, tool_name)
        for tool_name in ("ffmpeg", "ffprobe")
    }
    missing_tools = [tool_name for tool_name, tool_path in staged_tools.items() if tool_path is None]
    if missing_tools:
        raise RuntimeError(
            "Staged portable media-tools root is incomplete after copy. "
            f"Missing: {', '.join(missing_tools)} under {staged_tools_dir}."
        )

    manifest_path = staging_root / "manifest.json"
    manifest = {
        "source_env_var": SOURCE_ENV_VAR,
        "source_root": str(source_root),
        "staging_root": str(staging_root),
        "staged_tools_dir": str(staged_tools_dir),
        "source_tools": {name: str(path) for name, path in source_tools.items()},
        "staged_tools": {name: str(path) for name, path in staged_tools.items() if path is not None},
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stage explicit FFmpeg/ffprobe payloads for the portable Windows build."
    )
    parser.add_argument(
        "--staging-root",
        default=str(DEFAULT_STAGING_ROOT),
        help="Build-local staging root for PyInstaller datas.",
    )
    args = parser.parse_args()

    try:
        source_root, source_tools = _require_source_root()
        staging_root = Path(args.staging_root).expanduser().resolve()
        manifest = _stage_bundle(
            source_root=source_root,
            staging_root=staging_root,
            source_tools=source_tools,
        )
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 1

    print(f"PortableMediaToolsSource={manifest['source_root']}")
    print(f"PortableMediaToolsStagingRoot={manifest['staging_root']}")
    print(f"PortableMediaToolsManifest={staging_root / 'manifest.json'}")
    print(f"PortableMediaToolsFfmpeg={manifest['staged_tools']['ffmpeg']}")
    print(f"PortableMediaToolsFfprobe={manifest['staged_tools']['ffprobe']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
