from __future__ import annotations

from dataclasses import dataclass, field
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


class JobStep(StrEnum):
    QUEUED = "queued"
    PREPARING = "preparing"
    DOWNLOADING = "downloading"
    POSTPROCESSING = "postprocessing"
    COMPLETED = "completed"
    FAILED = "failed"


class ProbeErrorCode(StrEnum):
    INVALID = "invalid"
    PRIVATE = "private"
    UNAVAILABLE = "unavailable"


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def default_quality_for_mode(mode: DownloadMode) -> str:
    if mode == DownloadMode.AUDIO:
        return QualityOption.AUDIO_BEST.value
    return QualityOption.BEST.value


@dataclass(slots=True)
class FormatOption:
    format_id: str
    quality_label: str
    ext: str = ""
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "format_id": self.format_id,
            "quality_label": self.quality_label,
            "ext": self.ext,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "FormatOption":
        return cls(
            format_id=str(raw.get("format_id", "")),
            quality_label=str(raw.get("quality_label", "")),
            ext=str(raw.get("ext", "")),
            note=str(raw.get("note", "")),
        )


@dataclass(slots=True)
class ProbeResult:
    source_url: str
    title: str
    channel: str = ""
    thumbnail: str = ""
    duration: int = 0
    video_formats: list[FormatOption] = field(default_factory=list)
    audio_formats: list[FormatOption] = field(default_factory=list)

    def options_for_mode(self, mode: DownloadMode) -> list[FormatOption]:
        if mode == DownloadMode.AUDIO:
            return self.audio_formats
        return self.video_formats

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_url": self.source_url,
            "title": self.title,
            "channel": self.channel,
            "thumbnail": self.thumbnail,
            "duration": self.duration,
            "video_formats": [option.to_dict() for option in self.video_formats],
            "audio_formats": [option.to_dict() for option in self.audio_formats],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ProbeResult":
        return cls(
            source_url=str(raw.get("source_url", "")),
            title=str(raw.get("title", "")),
            channel=str(raw.get("channel", "")),
            thumbnail=str(raw.get("thumbnail", "")),
            duration=int(raw.get("duration", 0) or 0),
            video_formats=[
                FormatOption.from_dict(option)
                for option in raw.get("video_formats", [])
            ],
            audio_formats=[
                FormatOption.from_dict(option)
                for option in raw.get("audio_formats", [])
            ],
        )


@dataclass(slots=True)
class QueueItem:
    source_url: str
    mode: DownloadMode
    quality: str
    id: str = field(default_factory=lambda: str(uuid4()))
    status: JobStatus = JobStatus.QUEUED
    processing_step: JobStep = JobStep.QUEUED
    status_detail: str = ""
    title: str = ""
    output_path: str = ""
    error_message: str = ""
    probe: ProbeResult | None = None
    selected_format_id: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def touch(self) -> None:
        self.updated_at = utc_now_iso()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_url": self.source_url,
            "title": self.title,
            "mode": self.mode.value,
            "quality": self.quality,
            "status": self.status.value,
            "processing_step": self.processing_step.value,
            "status_detail": self.status_detail,
            "output_path": self.output_path,
            "error_message": self.error_message,
            "probe": self.probe.to_dict() if self.probe else None,
            "selected_format_id": self.selected_format_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "QueueItem":
        mode = DownloadMode(raw.get("mode", DownloadMode.VIDEO))
        probe_raw = raw.get("probe")
        return cls(
            id=str(raw["id"]),
            source_url=str(raw["source_url"]),
            title=str(raw.get("title", "")),
            mode=mode,
            quality=str(raw.get("quality", default_quality_for_mode(mode))),
            status=JobStatus(raw.get("status", JobStatus.QUEUED)),
            processing_step=JobStep(raw.get("processing_step", JobStep.QUEUED)),
            status_detail=str(raw.get("status_detail", "")),
            output_path=str(raw.get("output_path", "")),
            error_message=str(raw.get("error_message", "")),
            probe=ProbeResult.from_dict(probe_raw) if probe_raw else None,
            selected_format_id=str(raw.get("selected_format_id", "")),
            created_at=str(raw.get("created_at", utc_now_iso())),
            updated_at=str(raw.get("updated_at", raw.get("created_at", utc_now_iso()))),
        )
