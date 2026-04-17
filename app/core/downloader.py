from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from ..config import AppConfig
from ..ffmpeg import BinaryResolution, MediaToolResolver
from ..models import DownloadMode, FormatOption, JobStatus, JobStep, QueueItem
from .postprocess import MediaPostProcessor, MediaPostprocessError


class DownloadPipelineError(Exception):
    def __init__(self, step: JobStep, message: str) -> None:
        super().__init__(message)
        self.step = step


@dataclass(slots=True, frozen=True)
class DownloadPlan:
    output_path: Path
    video_format_id: str = ""
    audio_format_id: str = ""
    selected_format_id: str = ""

    @property
    def requires_audio_merge(self) -> bool:
        return bool(self.video_format_id and self.audio_format_id)


@dataclass(slots=True, frozen=True)
class DownloadedMedia:
    video_path: Path | None = None
    audio_path: Path | None = None


class _SilentYtdlpLogger:
    def debug(self, _message: str) -> None:
        return

    def warning(self, _message: str) -> None:
        return

    def error(self, _message: str) -> None:
        return


class QueueItemDownloader:
    def __init__(
        self,
        config: AppConfig,
        tool_resolver: MediaToolResolver | None = None,
    ) -> None:
        self.config = config
        self.tool_resolver = tool_resolver or MediaToolResolver(config)

    def execute(
        self,
        item: QueueItem,
        *,
        on_update: Callable[[QueueItem], None] | None = None,
    ) -> Path:
        self.config.ensure_directories()
        postprocessor = self._build_postprocessor()
        temp_dir = self.config.temp_dir / item.id
        plan: DownloadPlan | None = None

        try:
            self._set_state(
                item,
                status=JobStatus.RUNNING,
                step=JobStep.PREPARING,
                detail="Validating stored selection and runtime tools.",
                on_update=on_update,
            )
            plan = self._build_plan(item)
            self._ensure_required_tools(postprocessor, item.mode)
            self._prepare_temp_dir(temp_dir)
            self._remove_if_exists(plan.output_path)

            self._set_state(
                item,
                status=JobStatus.RUNNING,
                step=JobStep.DOWNLOADING,
                detail=self._download_detail(plan),
                on_update=on_update,
            )
            downloaded = self._download_selected_media(item, plan, temp_dir)

            self._set_state(
                item,
                status=JobStatus.RUNNING,
                step=JobStep.POSTPROCESSING,
                detail=self._postprocess_detail(item.mode, plan),
                on_update=on_update,
            )
            final_path = self._finalize_download(
                item=item,
                plan=plan,
                downloaded=downloaded,
                postprocessor=postprocessor,
            )

            item.output_path = str(final_path)
            item.error_message = ""
            self._set_state(
                item,
                status=JobStatus.COMPLETED,
                step=JobStep.COMPLETED,
                detail=f"Created final file {final_path.name}.",
                on_update=on_update,
            )
            return final_path
        except DownloadPipelineError as error:
            if plan is not None:
                self._remove_if_exists(plan.output_path)
            self._mark_failed(item, error, on_update=on_update)
            raise
        except MediaPostprocessError as error:
            pipeline_error = DownloadPipelineError(JobStep.POSTPROCESSING, str(error))
            if plan is not None:
                self._remove_if_exists(plan.output_path)
            self._mark_failed(item, pipeline_error, on_update=on_update)
            raise pipeline_error from error
        except Exception as error:  # pragma: no cover - defensive wrapper
            pipeline_error = DownloadPipelineError(
                JobStep.FAILED,
                f"Unexpected pipeline failure: {error}",
            )
            if plan is not None:
                self._remove_if_exists(plan.output_path)
            self._mark_failed(item, pipeline_error, on_update=on_update)
            raise pipeline_error from error
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def inspect_output(self, media_path: Path) -> dict[str, object] | None:
        return self._build_postprocessor().inspect_output(media_path)

    def _build_plan(self, item: QueueItem) -> DownloadPlan:
        if not item.probe:
            raise DownloadPipelineError(
                JobStep.PREPARING,
                "Queue item has no saved probe metadata. Re-probe before download.",
            )
        if not item.selected_format_id:
            raise DownloadPipelineError(
                JobStep.PREPARING,
                "Queue item has no saved selected_format_id.",
            )

        item.title = item.title or item.probe.title
        output_path = self._predict_output_path(item)
        format_ids = [part.strip() for part in item.selected_format_id.split("+") if part.strip()]
        if not format_ids:
            raise DownloadPipelineError(
                JobStep.PREPARING,
                f"Saved selected_format_id {item.selected_format_id!r} is empty after parsing.",
            )

        if item.mode == DownloadMode.AUDIO:
            selected_audio = self._find_option(item.probe.audio_formats, format_ids[0])
            if selected_audio is None:
                raise DownloadPipelineError(
                    JobStep.PREPARING,
                    f"Saved audio format_id {format_ids[0]!r} is not present in the stored probe state.",
                )
            return DownloadPlan(
                output_path=output_path,
                audio_format_id=selected_audio.format_id,
                selected_format_id=item.selected_format_id,
            )

        if len(format_ids) >= 2:
            video_option = self._find_option(item.probe.video_formats, format_ids[0]) or self._find_option(
                item.probe.video_formats,
                format_ids[1],
            )
            audio_option = self._find_option(item.probe.audio_formats, format_ids[0]) or self._find_option(
                item.probe.audio_formats,
                format_ids[1],
            )
            if video_option is None or audio_option is None:
                raise DownloadPipelineError(
                    JobStep.PREPARING,
                    f"Saved combined format_id {item.selected_format_id!r} does not match the stored probe state.",
                )
            return DownloadPlan(
                output_path=output_path,
                video_format_id=video_option.format_id,
                audio_format_id=audio_option.format_id,
                selected_format_id=item.selected_format_id,
            )

        selected_video = self._find_option(item.probe.video_formats, format_ids[0])
        if selected_video is None:
            raise DownloadPipelineError(
                JobStep.PREPARING,
                f"Saved video format_id {format_ids[0]!r} is not present in the stored probe state.",
            )

        if selected_video.note == "video-only":
            companion_audio = self._pick_companion_audio(item)
            return DownloadPlan(
                output_path=output_path,
                video_format_id=selected_video.format_id,
                audio_format_id=companion_audio.format_id,
                selected_format_id=item.selected_format_id,
            )

        return DownloadPlan(
            output_path=output_path,
            video_format_id=selected_video.format_id,
            selected_format_id=item.selected_format_id,
        )

    def _download_selected_media(
        self,
        item: QueueItem,
        plan: DownloadPlan,
        temp_dir: Path,
    ) -> DownloadedMedia:
        if item.mode == DownloadMode.AUDIO:
            audio_path = self._download_format(
                source_url=item.source_url,
                format_id=plan.audio_format_id,
                temp_dir=temp_dir,
            )
            return DownloadedMedia(audio_path=audio_path)

        video_path = self._download_format(
            source_url=item.source_url,
            format_id=plan.video_format_id,
            temp_dir=temp_dir,
        )
        audio_path = None
        if plan.audio_format_id:
            audio_path = self._download_format(
                source_url=item.source_url,
                format_id=plan.audio_format_id,
                temp_dir=temp_dir,
            )
        return DownloadedMedia(video_path=video_path, audio_path=audio_path)

    def _finalize_download(
        self,
        *,
        item: QueueItem,
        plan: DownloadPlan,
        downloaded: DownloadedMedia,
        postprocessor: MediaPostProcessor,
    ) -> Path:
        if item.mode == DownloadMode.AUDIO:
            if downloaded.audio_path is None:
                raise DownloadPipelineError(
                    JobStep.POSTPROCESSING,
                    "Audio pipeline finished download without an audio file.",
                )
            return postprocessor.finalize_audio(
                audio_input=downloaded.audio_path,
                output_path=plan.output_path,
            )

        if downloaded.video_path is None:
            raise DownloadPipelineError(
                JobStep.POSTPROCESSING,
                "Video pipeline finished download without a video file.",
            )
        return postprocessor.finalize_video(
            video_input=downloaded.video_path,
            audio_input=downloaded.audio_path,
            output_path=plan.output_path,
        )

    def _download_format(
        self,
        *,
        source_url: str,
        format_id: str,
        temp_dir: Path,
    ) -> Path:
        downloaded_paths: list[Path] = []

        def progress_hook(update: dict[str, object]) -> None:
            filename = update.get("filename")
            if update.get("status") == "finished" and filename:
                downloaded_paths.append(Path(str(filename)))

        ydl_options = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "logger": _SilentYtdlpLogger(),
            "format": format_id,
            "paths": {"home": str(temp_dir)},
            "outtmpl": {"default": "%(id)s.%(format_id)s.%(ext)s"},
            "progress_hooks": [progress_hook],
        }

        try:
            with YoutubeDL(ydl_options) as ydl:
                info = ydl.extract_info(source_url, download=True)
        except DownloadError as error:
            raise DownloadPipelineError(
                JobStep.DOWNLOADING,
                f"yt-dlp failed to download format {format_id}: {error}",
            ) from error
        except Exception as error:  # pragma: no cover - defensive wrapper
            raise DownloadPipelineError(
                JobStep.DOWNLOADING,
                f"Unexpected yt-dlp failure for format {format_id}: {error}",
            ) from error

        resolved_path = self._resolve_download_path(
            info=info,
            format_id=format_id,
            temp_dir=temp_dir,
            downloaded_paths=downloaded_paths,
        )
        if not resolved_path.exists():
            raise DownloadPipelineError(
                JobStep.DOWNLOADING,
                f"yt-dlp reported format {format_id}, but no media file was found in {temp_dir}.",
            )
        if resolved_path.stat().st_size <= 0:
            raise DownloadPipelineError(
                JobStep.DOWNLOADING,
                f"Downloaded file for format {format_id} is empty.",
            )
        return resolved_path

    def _resolve_download_path(
        self,
        *,
        info: object,
        format_id: str,
        temp_dir: Path,
        downloaded_paths: list[Path],
    ) -> Path:
        for path in reversed(downloaded_paths):
            if path.exists():
                return path

        if isinstance(info, dict):
            requested = info.get("requested_downloads")
            if isinstance(requested, list):
                for entry in requested:
                    if not isinstance(entry, dict):
                        continue
                    filepath = entry.get("filepath")
                    if filepath:
                        candidate = Path(str(filepath))
                        if candidate.exists():
                            return candidate

            filename = info.get("_filename")
            if filename:
                candidate = Path(str(filename))
                if candidate.exists():
                    return candidate

        matching_files = sorted(
            path
            for path in temp_dir.iterdir()
            if path.is_file() and f".{format_id}." in path.name and not path.name.endswith(".part")
        )
        if matching_files:
            return matching_files[-1]

        return temp_dir / f"missing.{format_id}"

    def _ensure_required_tools(
        self,
        postprocessor: MediaPostProcessor,
        mode: DownloadMode,
    ) -> None:
        if postprocessor.ffmpeg.is_available:
            return

        target = "mp4" if mode == DownloadMode.VIDEO else "m4a"
        raise DownloadPipelineError(
            JobStep.PREPARING,
            " ".join(
                [
                    f"ffmpeg is required to produce final {target} output.",
                    f"Resolver status: ffmpeg={self._format_resolution(postprocessor.ffmpeg)}",
                    f"ffprobe={self._format_resolution(postprocessor.ffprobe)}.",
                ]
            ),
        )

    def _build_postprocessor(self) -> MediaPostProcessor:
        return MediaPostProcessor(
            ffmpeg=self.tool_resolver.resolve_ffmpeg(),
            ffprobe=self.tool_resolver.resolve_ffprobe(),
        )

    def _pick_companion_audio(self, item: QueueItem) -> FormatOption:
        if not item.probe or not item.probe.audio_formats:
            raise DownloadPipelineError(
                JobStep.PREPARING,
                "Selected video format requires an audio track, but the saved probe state has no audio formats.",
            )
        return item.probe.audio_formats[0]

    @staticmethod
    def _find_option(options: list[FormatOption], format_id: str) -> FormatOption | None:
        for option in options:
            if option.format_id == format_id:
                return option
        return None

    def _predict_output_path(self, item: QueueItem) -> Path:
        suffix = ".m4a" if item.mode == DownloadMode.AUDIO else ".mp4"
        title = item.title or item.source_url
        safe_title = self._sanitize_filename(title)
        return self.config.output_dir / f"{safe_title}-{item.id[:8]}{suffix}"

    def _prepare_temp_dir(self, temp_dir: Path) -> None:
        shutil.rmtree(temp_dir, ignore_errors=True)
        temp_dir.mkdir(parents=True, exist_ok=True)

    def _set_state(
        self,
        item: QueueItem,
        *,
        status: JobStatus,
        step: JobStep,
        detail: str,
        on_update: Callable[[QueueItem], None] | None,
    ) -> None:
        item.status = status
        item.processing_step = step
        item.status_detail = detail
        item.touch()
        if on_update is not None:
            on_update(item)

    def _mark_failed(
        self,
        item: QueueItem,
        error: DownloadPipelineError,
        *,
        on_update: Callable[[QueueItem], None] | None,
    ) -> None:
        item.status = JobStatus.FAILED
        item.processing_step = JobStep.FAILED
        item.status_detail = f"failed at {error.step.value}"
        item.output_path = ""
        item.error_message = str(error)
        item.touch()
        if on_update is not None:
            on_update(item)

    @staticmethod
    def _download_detail(plan: DownloadPlan) -> str:
        if plan.requires_audio_merge:
            return (
                f"Downloading video format {plan.video_format_id} and companion audio "
                f"{plan.audio_format_id}."
            )
        selected = plan.video_format_id or plan.audio_format_id
        return f"Downloading saved format {selected}."

    @staticmethod
    def _postprocess_detail(mode: DownloadMode, plan: DownloadPlan) -> str:
        if mode == DownloadMode.AUDIO:
            return "Converting downloaded audio into final m4a output."
        if plan.requires_audio_merge:
            return "Merging downloaded streams into final mp4 output."
        return "Converting downloaded media into final mp4 output."

    @staticmethod
    def _format_resolution(resolution: BinaryResolution) -> str:
        if resolution.path:
            return f"{resolution.source}:{resolution.path}"
        return resolution.source

    @staticmethod
    def _sanitize_filename(value: str) -> str:
        collapsed = re.sub(r"\s+", " ", value).strip()
        cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", collapsed)
        cleaned = cleaned.rstrip(". ")
        if not cleaned:
            cleaned = "download"
        return cleaned[:80]

    @staticmethod
    def _remove_if_exists(path: Path) -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            return
