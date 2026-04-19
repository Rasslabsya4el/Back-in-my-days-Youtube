from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from ..ffmpeg import BinaryResolution
from ..models import FormatOption, ProbeResult, QueueItem


@dataclass(slots=True, frozen=True)
class ToolStatus:
    name: str
    path: str
    source: str
    is_available: bool

    @classmethod
    def from_resolution(cls, resolution: BinaryResolution) -> "ToolStatus":
        return cls(
            name=resolution.name,
            path=str(resolution.path) if resolution.path else "",
            source=resolution.source,
            is_available=resolution.is_available,
        )


@dataclass(slots=True, frozen=True)
class FormatOptionSnapshot:
    format_id: str
    quality_label: str
    ext: str
    note: str

    @classmethod
    def from_option(cls, option: FormatOption) -> "FormatOptionSnapshot":
        return cls(
            format_id=option.format_id,
            quality_label=option.quality_label,
            ext=option.ext,
            note=option.note,
        )


@dataclass(slots=True, frozen=True)
class ProbeSnapshot:
    source_url: str
    title: str
    channel: str
    thumbnail: str
    duration: int
    video_formats: tuple[FormatOptionSnapshot, ...]
    audio_formats: tuple[FormatOptionSnapshot, ...]

    @classmethod
    def from_probe(cls, probe: ProbeResult) -> "ProbeSnapshot":
        return cls(
            source_url=probe.source_url,
            title=probe.title,
            channel=probe.channel,
            thumbnail=probe.thumbnail,
            duration=probe.duration,
            video_formats=tuple(
                FormatOptionSnapshot.from_option(option) for option in probe.video_formats
            ),
            audio_formats=tuple(
                FormatOptionSnapshot.from_option(option) for option in probe.audio_formats
            ),
        )


@dataclass(slots=True, frozen=True)
class QueueItemSnapshot:
    id: str
    source_url: str
    title: str
    mode: str
    quality: str
    status: str
    processing_step: str
    status_detail: str
    output_path: str
    error_message: str
    selected_format_id: str
    created_at: str
    updated_at: str
    probe: ProbeSnapshot | None

    @classmethod
    def from_item(cls, item: QueueItem) -> "QueueItemSnapshot":
        return cls(
            id=item.id,
            source_url=item.source_url,
            title=item.title,
            mode=item.mode.value,
            quality=item.quality,
            status=item.status.value,
            processing_step=item.processing_step.value,
            status_detail=item.status_detail,
            output_path=item.output_path,
            error_message=item.error_message,
            selected_format_id=item.selected_format_id,
            created_at=item.created_at,
            updated_at=item.updated_at,
            probe=ProbeSnapshot.from_probe(item.probe) if item.probe else None,
        )


@dataclass(slots=True, frozen=True)
class SelectionState:
    selected_item_id: str
    mode: str
    quality: str
    selected_format_id: str
    quality_options: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class RuntimeSnapshot:
    project_root: str
    resource_project_root: str
    runtime_dir: str
    output_dir: str
    temp_dir: str
    state_file: str
    debug_log_path: str
    installed_build: bool
    queue_items_loaded: int
    ffmpeg: ToolStatus
    ffprobe: ToolStatus

    def to_dict(self) -> dict[str, Any]:
        return _to_json_safe_payload(self)


@dataclass(slots=True, frozen=True)
class AppState:
    status_message: str
    queue: tuple[QueueItemSnapshot, ...]
    selected_item_id: str
    selected_item: QueueItemSnapshot | None
    selection: SelectionState
    runtime: RuntimeSnapshot

    def to_dict(self) -> dict[str, Any]:
        return _to_json_safe_payload(self)


def _to_json_safe_payload(value: Any) -> Any:
    if is_dataclass(value):
        return {
            field.name: _to_json_safe_payload(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, dict):
        return {
            str(key): _to_json_safe_payload(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_to_json_safe_payload(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    return value


def to_json_safe_payload(value: Any) -> Any:
    return _to_json_safe_payload(value)
