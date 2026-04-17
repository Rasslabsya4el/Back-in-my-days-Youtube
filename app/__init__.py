"""YT Downloader application package."""

from typing import TYPE_CHECKING, Any

from .config import AppConfig, create_default_config
from .models import DownloadMode, JobStatus, QualityOption, QueueItem
from .state_store import QueueStateStore

if TYPE_CHECKING:
    from .shell import AppShell

__all__ = [
    "AppConfig",
    "AppShell",
    "DownloadMode",
    "JobStatus",
    "QualityOption",
    "QueueItem",
    "QueueStateStore",
    "create_default_config",
]


def __getattr__(name: str) -> Any:
    if name == "AppShell":
        from .shell import AppShell

        return AppShell
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
