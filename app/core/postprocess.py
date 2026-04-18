from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from ..ffmpeg import BinaryResolution
from .audio_metadata import AudioMetadata, download_artwork


class MediaPostprocessError(Exception):
    pass


class MediaPostProcessor:
    def __init__(
        self,
        *,
        ffmpeg: BinaryResolution,
        ffprobe: BinaryResolution,
    ) -> None:
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe

    def finalize_video(
        self,
        *,
        video_input: Path,
        output_path: Path,
        audio_input: Path | None = None,
    ) -> Path:
        self._ensure_ffmpeg("ffmpeg is required to produce the final mp4 output.")
        self._remove_if_exists(output_path)
        base_command = self._video_inputs(video_input=video_input, audio_input=audio_input)
        should_attempt_copy = self._can_remux_windows_friendly(
            video_input=video_input,
            audio_input=audio_input,
        )

        if should_attempt_copy:
            try:
                self._run_ffmpeg(
                    description="remux video to mp4",
                    arguments=[
                        *base_command,
                        *self._video_maps(audio_input=audio_input),
                        "-c",
                        "copy",
                        "-movflags",
                        "+faststart",
                        str(output_path),
                    ],
                )
            except MediaPostprocessError:
                self._remove_if_exists(output_path)
                self._run_ffmpeg(
                    description="transcode video to mp4",
                    arguments=[
                        *base_command,
                        *self._video_maps(audio_input=audio_input),
                        "-c:v",
                        "libx264",
                        "-preset",
                        "fast",
                        "-crf",
                        "23",
                        "-c:a",
                        "aac",
                        "-b:a",
                        "192k",
                        "-movflags",
                        "+faststart",
                        str(output_path),
                    ],
                )
        else:
            self._remove_if_exists(output_path)
            self._run_ffmpeg(
                description="transcode video to mp4",
                arguments=[
                    *base_command,
                    *self._video_maps(audio_input=audio_input),
                    "-c:v",
                    "libx264",
                    "-preset",
                    "fast",
                    "-crf",
                    "23",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-movflags",
                    "+faststart",
                    str(output_path),
                ],
            )

        self._validate_output(output_path, "mp4")
        return output_path

    def _can_remux_windows_friendly(
        self,
        *,
        video_input: Path,
        audio_input: Path | None,
    ) -> bool:
        video_codec = self._probe_primary_codec(video_input, codec_type="video")
        if video_codec != "h264":
            return False

        if audio_input is not None:
            audio_codec = self._probe_primary_codec(audio_input, codec_type="audio")
            return audio_codec == "aac"

        audio_codec = self._probe_primary_codec(video_input, codec_type="audio")
        return audio_codec in {"", "aac"}

    def finalize_audio(
        self,
        *,
        audio_input: Path,
        output_path: Path,
        metadata: AudioMetadata,
        working_dir: Path,
    ) -> Path:
        self._ensure_ffmpeg("ffmpeg is required to produce the final m4a output.")
        self._remove_if_exists(output_path)
        staged_output = output_path.parent / f"{output_path.stem}.staged{output_path.suffix}"
        artwork_input = download_artwork(metadata.artwork_url, working_dir=working_dir)
        self._remove_if_exists(staged_output)
        try:
            self._finalize_audio_variant(
                audio_input=audio_input,
                output_path=staged_output,
                metadata=metadata,
                artwork_input=artwork_input,
                copy_audio=True,
            )
        except MediaPostprocessError:
            self._remove_if_exists(staged_output)
            self._finalize_audio_variant(
                audio_input=audio_input,
                output_path=staged_output,
                metadata=metadata,
                artwork_input=artwork_input,
                copy_audio=False,
            )

        try:
            self._validate_output(staged_output, "m4a")
            staged_output.replace(output_path)
        finally:
            self._remove_if_exists(staged_output)
            if artwork_input is not None:
                self._remove_if_exists(artwork_input)

        self._validate_output(output_path, "m4a")
        return output_path

    def inspect_output(self, media_path: Path) -> dict[str, Any] | None:
        if not self.ffprobe.is_available or self.ffprobe.path is None:
            return None

        command = [
            str(self.ffprobe.path),
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(media_path),
        ]
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise MediaPostprocessError(self._inspection_failed_message())

        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError as error:
            raise MediaPostprocessError(self._inspection_failed_message()) from error
        streams = payload.get("streams", [])
        format_info = payload.get("format", {})
        stream_types: list[str] = []
        codec_names: list[str] = []
        attached_pic_streams: list[dict[str, Any]] = []

        if isinstance(streams, list):
            for stream in streams:
                if not isinstance(stream, dict):
                    continue
                codec_type = stream.get("codec_type")
                codec_name = stream.get("codec_name")
                disposition = stream.get("disposition")
                stream_index = stream.get("index")
                if codec_type:
                    stream_types.append(str(codec_type))
                if codec_name:
                    codec_names.append(str(codec_name))
                if isinstance(disposition, dict) and bool(disposition.get("attached_pic")):
                    attached_pic_streams.append(
                        {
                            "index": stream_index,
                            "codec_type": str(codec_type or ""),
                            "codec_name": str(codec_name or ""),
                        }
                    )

        if not isinstance(format_info, dict):
            format_info = {}

        raw_tags = format_info.get("tags", {})
        format_tags: dict[str, str] = {}
        if isinstance(raw_tags, dict):
            for key in ("title", "artist"):
                value = raw_tags.get(key)
                if value:
                    format_tags[key] = str(value)

        return {
            "format_name": str(format_info.get("format_name", "")),
            "duration": str(format_info.get("duration", "")),
            "size": str(format_info.get("size", "")),
            "stream_types": stream_types,
            "codec_names": codec_names,
            "format_tags": format_tags,
            "has_attached_pic": bool(attached_pic_streams),
            "attached_pic_streams": attached_pic_streams,
        }

    def _finalize_audio_variant(
        self,
        *,
        audio_input: Path,
        output_path: Path,
        metadata: AudioMetadata,
        artwork_input: Path | None,
        copy_audio: bool,
    ) -> None:
        artwork_candidates = [artwork_input]
        if artwork_input is not None:
            artwork_candidates.append(None)

        last_error: MediaPostprocessError | None = None
        for current_artwork in artwork_candidates:
            self._remove_if_exists(output_path)
            try:
                self._run_ffmpeg(
                    description=self._describe_audio_variant(
                        copy_audio=copy_audio,
                        has_artwork=current_artwork is not None,
                    ),
                    arguments=self._audio_arguments(
                        audio_input=audio_input,
                        output_path=output_path,
                        metadata=metadata,
                        artwork_input=current_artwork,
                        copy_audio=copy_audio,
                    ),
                )
                return
            except MediaPostprocessError as error:
                last_error = error

        if last_error is None:
            raise MediaPostprocessError("Audio post-processing finished without running ffmpeg.")
        raise last_error

    @staticmethod
    def _audio_arguments(
        *,
        audio_input: Path,
        output_path: Path,
        metadata: AudioMetadata,
        artwork_input: Path | None,
        copy_audio: bool,
    ) -> list[str]:
        arguments = ["-i", str(audio_input)]
        if artwork_input is not None:
            arguments.extend(["-i", str(artwork_input)])

        arguments.extend(["-map_metadata", "-1", "-map", "0:a:0"])
        if artwork_input is not None:
            arguments.extend(["-map", "1:v:0"])
        else:
            arguments.append("-vn")

        if copy_audio:
            arguments.extend(["-c:a", "copy"])
        else:
            arguments.extend(["-c:a", "aac", "-b:a", "192k"])

        if artwork_input is not None:
            arguments.extend(
                [
                    "-c:v",
                    "mjpeg",
                    "-disposition:v:0",
                    "attached_pic",
                    "-metadata:s:v:0",
                    "title=Album cover",
                    "-metadata:s:v:0",
                    "comment=Cover (front)",
                ]
            )

        arguments.extend(["-movflags", "+faststart", *metadata.ffmpeg_arguments(), str(output_path)])
        return arguments

    @staticmethod
    def _describe_audio_variant(*, copy_audio: bool, has_artwork: bool) -> str:
        action = "remux" if copy_audio else "transcode"
        detail = " with artwork" if has_artwork else ""
        return f"{action} audio to m4a{detail}"

    def _run_ffmpeg(self, *, description: str, arguments: list[str]) -> None:
        if self.ffmpeg.path is None:
            raise MediaPostprocessError("ffmpeg is not available.")

        command = [str(self.ffmpeg.path), "-y", *arguments]
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            del description
            raise MediaPostprocessError(self._postprocess_failed_message(Path(arguments[-1])))

    def _ensure_ffmpeg(self, message: str) -> None:
        if not self.ffmpeg.is_available:
            raise MediaPostprocessError(message)

    @staticmethod
    def _video_inputs(*, video_input: Path, audio_input: Path | None) -> list[str]:
        arguments = ["-i", str(video_input)]
        if audio_input is not None:
            arguments.extend(["-i", str(audio_input)])
        return arguments

    @staticmethod
    def _video_maps(*, audio_input: Path | None) -> list[str]:
        if audio_input is not None:
            return ["-map", "0:v:0", "-map", "1:a:0"]
        return ["-map", "0:v:0", "-map", "0:a:0?"]

    def _probe_primary_codec(self, media_path: Path, *, codec_type: str) -> str:
        if not self.ffprobe.is_available or self.ffprobe.path is None:
            return ""

        command = [
            str(self.ffprobe.path),
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            str(media_path),
        ]
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return ""

        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            return ""

        streams = payload.get("streams", [])
        if not isinstance(streams, list):
            return ""

        for stream in streams:
            if not isinstance(stream, dict):
                continue
            if stream.get("codec_type") != codec_type:
                continue
            codec_name = stream.get("codec_name")
            if codec_name:
                return str(codec_name)
        return ""

    @staticmethod
    def _validate_output(output_path: Path, expected_suffix: str) -> None:
        if not output_path.exists():
            raise MediaPostprocessError(
                MediaPostProcessor._postprocess_failed_message(output_path)
            )
        if output_path.suffix.lower() != f".{expected_suffix}":
            raise MediaPostprocessError(
                MediaPostProcessor._postprocess_failed_message(output_path)
            )
        if output_path.stat().st_size <= 0:
            raise MediaPostprocessError(
                MediaPostProcessor._postprocess_failed_message(output_path)
            )

    @staticmethod
    def _remove_if_exists(path: Path) -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            return

    @staticmethod
    def _inspection_failed_message() -> str:
        return "Output inspection failed. ffprobe could not read the saved file."

    @staticmethod
    def _postprocess_failed_message(output_path: Path) -> str:
        suffix = output_path.suffix.lower().lstrip(".") or "media"
        return f"Post-processing failed. ffmpeg could not create the final {suffix} file."

    @staticmethod
    def _format_process_error(result: subprocess.CompletedProcess[str]) -> str:
        combined = "\n".join(
            part.strip()
            for part in (result.stderr, result.stdout)
            if part and part.strip()
        ).strip()
        if not combined:
            return f"exit code {result.returncode}"

        lines = [line.strip() for line in combined.splitlines() if line.strip()]
        if not lines:
            return f"exit code {result.returncode}"
        return lines[-1]
