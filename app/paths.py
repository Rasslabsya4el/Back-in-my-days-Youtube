from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def source_root() -> Path:
    return Path(__file__).resolve().parent.parent


def resource_root() -> Path:
    if is_frozen():
        bundle_root = getattr(sys, "_MEIPASS", "")
        if bundle_root:
            return Path(bundle_root).resolve()
        return Path(sys.executable).resolve().parent
    return source_root()


def resource_project_root() -> Path:
    return resource_root()


def app_root() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return source_root()


def frontend_dist_dir() -> Path:
    return resource_project_root() / "frontend" / "dist"


def icon_path() -> Path | None:
    path = resource_project_root() / "app" / "assets" / "icons" / "yt-downloader.ico"
    if path.exists():
        return path
    return None
