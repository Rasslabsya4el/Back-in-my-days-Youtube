from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True)
class AppConfig:
    project_root: Path
    runtime_dir: Path
    output_dir: Path
    temp_dir: Path
    state_file: Path
    bundled_tools_dir: Path

    def ensure_directories(self) -> None:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.bundled_tools_dir.mkdir(parents=True, exist_ok=True)


def create_default_config(project_root: Path | None = None) -> AppConfig:
    root = project_root or Path(__file__).resolve().parent.parent
    runtime_dir = root / "runtime"
    output_dir = root / "output"
    temp_dir = root / "temp"
    bundled_tools_dir = root / "app" / "bin"

    return AppConfig(
        project_root=root,
        runtime_dir=runtime_dir,
        output_dir=output_dir,
        temp_dir=temp_dir,
        state_file=runtime_dir / "queue_state.json",
        bundled_tools_dir=bundled_tools_dir,
    )
