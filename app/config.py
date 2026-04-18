from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .paths import app_root, resource_project_root


@dataclass(slots=True, frozen=True)
class AppConfig:
    project_root: Path
    resource_project_root: Path
    runtime_dir: Path
    output_dir: Path
    temp_dir: Path
    state_file: Path
    bundled_tools_dir: Path

    @property
    def bundled_tools_roots(self) -> tuple[Path, Path, Path]:
        return (
            self.bundled_tools_dir,
            self.resource_project_root / "tools",
            self.resource_project_root / "vendor",
        )

    def ensure_directories(self) -> None:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)


def create_default_config(project_root: Path | None = None) -> AppConfig:
    writable_root = project_root or app_root()
    resource_root = resource_project_root()
    runtime_dir = writable_root / "runtime"
    output_dir = writable_root / "output"
    temp_dir = writable_root / "temp"
    bundled_tools_dir = resource_root / "app" / "bin"

    return AppConfig(
        project_root=writable_root,
        resource_project_root=resource_root,
        runtime_dir=runtime_dir,
        output_dir=output_dir,
        temp_dir=temp_dir,
        state_file=runtime_dir / "queue_state.json",
        bundled_tools_dir=bundled_tools_dir,
    )
