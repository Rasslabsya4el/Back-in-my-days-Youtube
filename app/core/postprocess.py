from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from ..ffmpeg import BinaryResolution


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

        self._validate_output(output_path, "mp4")
        return output_path

    def finalize_audio(
        self,
        *,
        audio_input: Path,
        output_path: Path,
    ) -> Path:
        self._ensure_ffmpeg("ffmpeg is required to produce the final m4a output.")
        self._remove_if_exists(output_path)

        try:
            self._run_ffmpeg(
                description="remux audio to m4a",
                arguments=[
                    "-i",
                    str(audio_input),
                    "-vn",
                    "-map",
                    "0:a:0",
                    "-c",
                    "copy",
                    str(output_path),
                ],
            )
        except MediaPostprocessError:
            self._remove_if_exists(output_path)
            self._run_ffmpeg(
                description="transcode audio to m4a",
                arguments=[
                    "-i",
                    str(audio_input),
                    "-vn",
                    "-map",
                    "0:a:0",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    str(output_path),
                ],
            )

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
            "-show_entries",
            "format=format_name,duration,size:stream=index,codec_type,codec_name",
            str(media_path),
        ]
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise MediaPostprocessError(
                f"ffprobe failed for {media_path.name}: {self._format_process_error(result)}"
            )

        payload = json.loads(result.stdout or "{}")
        format_info = payload.get("format", {})
        streams = payload.get("streams", [])
        stream_types: list[str] = []
        codec_names: list[str] = []

        if isinstance(streams, list):
            for stream in streams:
                if not isinstance(stream, dict):
                    continue
                codec_type = stream.get("codec_type")
                codec_name = stream.get("codec_name")
                if codec_type:
                    stream_types.append(str(codec_type))
                if codec_name:
                    codec_names.append(str(codec_name))

        if not isinstance(format_info, dict):
            format_info = {}

        return {
            "format_name": str(format_info.get("format_name", "")),
            "duration": str(format_info.get("duration", "")),
            "size": str(format_info.get("size", "")),
            "stream_types": stream_types,
            "codec_names": codec_names,
        }

    def _run_ffmpeg(self, *, description: str, arguments: list[str]) -> None:
        if self.ffmpeg.path is None:
            raise MediaPostprocessError("ffmpeg resolver returned no executable path.")

        command = [str(self.ffmpeg.path), "-y", *arguments]
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise MediaPostprocessError(
                f"ffmpeg failed to {description}: {self._format_process_error(result)}"
            )

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

    @staticmethod
    def _validate_output(output_path: Path, expected_suffix: str) -> None:
        if not output_path.exists():
            raise MediaPostprocessError(
                f"Post-processing finished without creating {output_path.name}."
            )
        if output_path.suffix.lower() != f".{expected_suffix}":
            raise MediaPostprocessError(
                f"Expected .{expected_suffix} output, got {output_path.suffix or 'no extension'}."
            )
        if output_path.stat().st_size <= 0:
            raise MediaPostprocessError(f"Output file {output_path.name} is empty.")

    @staticmethod
    def _remove_if_exists(path: Path) -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            return

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
