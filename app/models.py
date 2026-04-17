from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


class DownloadMode(StrEnum):
    VIDEO = "video"
    AUDIO = "audio"


class QualityOption(StrEnum):
    BEST = "best"
    Q1080P = "1080p"
    Q720P = "720p"
    Q480P = "480p"
    AUDIO_BEST = "audio-best"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class QueueItem:
    source_url: str
    mode: DownloadMode
    quality: QualityOption
    id: str = field(default_factory=lambda: str(uuid4()))
    status: JobStatus = JobStatus.QUEUED
    title: str = ""
    output_path: str = ""
    error_message: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def touch(self) -> None:
        self.updated_at = utc_now_iso()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "QueueItem":
        return cls(
            id=raw["id"],
            source_url=raw["source_url"],
            title=raw.get("title", ""),
            mode=DownloadMode(raw["mode"]),
            quality=QualityOption(raw["quality"]),
            status=JobStatus(raw.get("status", JobStatus.QUEUED)),
            output_path=raw.get("output_path", ""),
            error_message=raw.get("error_message", ""),
            created_at=raw.get("created_at", utc_now_iso()),
            updated_at=raw.get("updated_at", raw.get("created_at", utc_now_iso())),
        )
