from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from .config import AppConfig


@dataclass(slots=True, frozen=True)
class BinaryResolution:
    name: str
    path: Path | None
    source: str

    @property
    def is_available(self) -> bool:
        return self.path is not None


class MediaToolResolver:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def resolve_ffmpeg(self) -> BinaryResolution:
        return self._resolve_binary("ffmpeg")

    def resolve_ffprobe(self) -> BinaryResolution:
        return self._resolve_binary("ffprobe")

    def _resolve_binary(self, name: str) -> BinaryResolution:
        env_path = os.getenv(f"{name.upper()}_PATH")
        if env_path:
            candidate = Path(env_path).expanduser()
            if candidate.exists():
                return BinaryResolution(name=name, path=candidate, source="env")

        project_candidates = self._project_candidates(name)
        for candidate in project_candidates:
            if candidate.exists():
                return BinaryResolution(name=name, path=candidate, source="bundled")

        system_path = shutil.which(name)
        if system_path:
            return BinaryResolution(name=name, path=Path(system_path), source="path")

        if os.name == "nt":
            system_path = shutil.which(f"{name}.exe")
            if system_path:
                return BinaryResolution(name=name, path=Path(system_path), source="path")

        return BinaryResolution(name=name, path=None, source="missing")

    def _project_candidates(self, name: str) -> list[Path]:
        exe_name = f"{name}.exe" if os.name == "nt" else name
        roots = [
            self.config.bundled_tools_dir,
            self.config.project_root / "tools",
            self.config.project_root / "vendor",
        ]
        suffixes = [
            Path(exe_name),
            Path("bin") / exe_name,
            Path("ffmpeg") / exe_name,
            Path("ffmpeg") / "bin" / exe_name,
            Path("win-x64") / exe_name,
        ]

        return [root / suffix for root in roots for suffix in suffixes]
