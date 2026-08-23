from __future__ import annotations

from pathlib import Path
from typing import Any

from ..paths import resolve_node_runtime_path


def build_ytdlp_options(
    options: dict[str, Any] | None = None,
    *,
    js_runtime_path: Path | None = None,
) -> dict[str, Any]:
    """Build options shared by metadata probing and media downloads.

    YouTube's current player flow needs both the yt-dlp EJS challenge scripts
    and a supported JavaScript runtime.  The runtime is optional in source
    checkouts, but release builds include a portable Node executable.
    """

    result: dict[str, Any] = {
        "retries": 3,
        "fragment_retries": 3,
        "file_access_retries": 3,
        "extractor_retries": 3,
    }
    if options:
        result.update(options)

    runtime_path = js_runtime_path or resolve_node_runtime_path()
    if runtime_path is not None and runtime_path.is_file():
        result["js_runtimes"] = {
            "node": {
                "path": str(runtime_path),
            }
        }

    return result
