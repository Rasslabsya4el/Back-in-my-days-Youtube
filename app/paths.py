from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_NAME = "Back in my days Youtube"
APP_SLUG = "back-in-my-days-youtube"
LOGGER_NAMESPACE = "back_in_my_days_youtube"
ICON_FILE_NAME = "back-in-my-days-youtube.ico"
DEBUG_LOG_OVERRIDE_ENV = "BACK_IN_MY_DAYS_YOUTUBE_DEBUG_LOG_PATH"
INSTALL_MARKER_NAME = "install-mode.txt"
DEBUG_LOG_POINTER_NAME = "debug-log-path.txt"
WEBVIEW2_RUNTIME_OVERRIDE_ENV = "BACK_IN_MY_DAYS_YOUTUBE_WEBVIEW2_RUNTIME_PATH"


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


def local_app_data_root() -> Path:
    if os.name == "nt":
        base_dir = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        return base_dir / APP_NAME
    return Path.home() / f".{APP_SLUG}"


def common_app_data_root() -> Path:
    if os.name == "nt":
        base_dir = Path(os.environ.get("PROGRAMDATA") or (Path.home() / "AppData" / "Local"))
        return base_dir / APP_NAME
    return local_app_data_root()


def install_marker_path() -> Path:
    return app_root() / INSTALL_MARKER_NAME


def debug_log_pointer_path() -> Path:
    return app_root() / DEBUG_LOG_POINTER_NAME


def is_installed_build() -> bool:
    return is_frozen() and install_marker_path().is_file()


def writable_app_root() -> Path:
    if not is_frozen():
        return source_root()
    if is_installed_build():
        return local_app_data_root()
    return app_root()


def resolve_debug_log_path() -> Path:
    override_value = os.environ.get(DEBUG_LOG_OVERRIDE_ENV, "").strip()
    if override_value:
        return Path(override_value).expanduser().resolve()

    pointer_path = debug_log_pointer_path()
    if pointer_path.is_file():
        try:
            raw_pointer_value = pointer_path.read_text(encoding="utf-8").strip()
        except OSError:
            raw_pointer_value = ""
        if raw_pointer_value:
            candidate = Path(raw_pointer_value).expanduser()
            if not candidate.is_absolute():
                candidate = (app_root() / candidate).resolve()
            return candidate

    if is_installed_build():
        return common_app_data_root() / "logs" / "debug.log"
    return writable_app_root() / "runtime" / "debug.log"


def frontend_dist_dir() -> Path:
    return resource_project_root() / "frontend" / "dist"


def icon_path() -> Path | None:
    path = resource_project_root() / "app" / "assets" / "icons" / ICON_FILE_NAME
    if path.exists():
        return path
    return None


def _looks_like_webview2_runtime(path: Path) -> bool:
    return path.is_dir() and (path / "msedgewebview2.exe").is_file()


def resolve_webview2_runtime_dir() -> tuple[str, Path | None]:
    override_value = os.environ.get(WEBVIEW2_RUNTIME_OVERRIDE_ENV, "").strip()
    if override_value:
        override_path = Path(override_value).expanduser().resolve()
        if _looks_like_webview2_runtime(override_path):
            return "override", override_path

    bundled_path = resource_project_root() / "webview2-fixed-runtime"
    if _looks_like_webview2_runtime(bundled_path):
        return "bundled", bundled_path
    return "", None


def webview2_runtime_dir() -> Path | None:
    return resolve_webview2_runtime_dir()[1]


def resolve_node_runtime_path() -> Path | None:
    """Return the bundled Node runtime, or a Node executable on PATH."""

    bundled_path = resource_project_root() / "node-runtime" / "node.exe"
    if bundled_path.is_file():
        return bundled_path

    node_name = "node.exe" if os.name == "nt" else "node"
    system_path = shutil.which(node_name)
    return Path(system_path).resolve() if system_path else None
