from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from ..models import FormatOption, ProbeErrorCode, ProbeResult

YOUTUBE_HOSTS = {
    "youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
}
VIDEO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")


@dataclass(slots=True)
class YoutubeProbeError(Exception):
    code: ProbeErrorCode
    message: str

    def __str__(self) -> str:
        return self.message


class _SilentYtdlpLogger:
    def debug(self, _message: str) -> None:
        return

    def warning(self, _message: str) -> None:
        return

    def error(self, _message: str) -> None:
        return


class YoutubeProbeService:
    def __init__(self) -> None:
        self._ydl_options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "logger": _SilentYtdlpLogger(),
        }

    def probe(self, url: str) -> ProbeResult:
        normalized_url = self.normalize_url(url)

        try:
            with YoutubeDL(self._ydl_options) as ydl:
                info = ydl.extract_info(normalized_url, download=False)
        except DownloadError as error:
            raise self._normalize_download_error(error) from error
        except Exception as error:  # pragma: no cover - defensive normalization
            raise YoutubeProbeError(
                ProbeErrorCode.UNAVAILABLE,
                f"Failed to probe YouTube URL: {error}",
            ) from error

        if not isinstance(info, dict):
            raise YoutubeProbeError(
                ProbeErrorCode.UNAVAILABLE,
                "yt-dlp did not return video metadata.",
            )

        probe = ProbeResult(
            source_url=str(info.get("webpage_url") or normalized_url),
            title=str(info.get("title") or ""),
            channel=self._pick_channel(info),
            thumbnail=str(info.get("thumbnail") or ""),
            duration=int(info.get("duration") or 0),
            video_formats=self._collect_video_formats(info),
            audio_formats=self._collect_audio_formats(info),
        )

        if not probe.title:
            raise YoutubeProbeError(
                ProbeErrorCode.UNAVAILABLE,
                "yt-dlp returned incomplete metadata for the YouTube video.",
            )

        if not probe.video_formats and not probe.audio_formats:
            raise YoutubeProbeError(
                ProbeErrorCode.UNAVAILABLE,
                "No downloadable media formats were found for the YouTube video.",
            )

        return probe

    @staticmethod
    def normalize_url(url: str) -> str:
        trimmed = url.strip()
        if not trimmed:
            raise YoutubeProbeError(ProbeErrorCode.INVALID, "YouTube URL is empty.")

        parsed = urlparse(trimmed)
        host = parsed.netloc.lower().split(":")[0]
        if host.startswith("www.") and host != "www.youtube-nocookie.com":
            host = host[4:]

        if parsed.scheme not in {"http", "https"} or host not in YOUTUBE_HOSTS:
            raise YoutubeProbeError(
                ProbeErrorCode.INVALID,
                "Expected a valid YouTube video URL.",
            )

        video_id = YoutubeProbeService._extract_video_id(host, parsed)
        if not video_id:
            raise YoutubeProbeError(
                ProbeErrorCode.INVALID,
                "Expected a direct YouTube video URL with a valid video id.",
            )

        return f"https://www.youtube.com/watch?v={video_id}"

    @staticmethod
    def _extract_video_id(host: str, parsed_url: object) -> str:
        parsed = parsed_url
        path_parts = [part for part in parsed.path.split("/") if part]
        query = parse_qs(parsed.query)
        candidate = ""

        if host == "youtu.be":
            candidate = path_parts[0] if path_parts else ""
        elif path_parts[:1] == ["watch"]:
            candidate = query.get("v", [""])[0]
        elif path_parts[:1] in (["shorts"], ["embed"], ["live"], ["v"]):
            candidate = path_parts[1] if len(path_parts) > 1 else ""
        else:
            candidate = query.get("v", [""])[0]

        if VIDEO_ID_PATTERN.fullmatch(candidate):
            return candidate
        return ""

    @staticmethod
    def _pick_channel(info: dict[str, object]) -> str:
        for key in ("channel", "uploader", "creator"):
            value = info.get(key)
            if value:
                return str(value)
        return ""

    def _collect_video_formats(self, info: dict[str, object]) -> list[FormatOption]:
        candidates: list[tuple[tuple[float, float, float], FormatOption]] = []
        for raw_format in info.get("formats", []):
            if not isinstance(raw_format, dict):
                continue
            if str(raw_format.get("vcodec") or "none") == "none":
                continue

            height = float(raw_format.get("height") or 0)
            fps = float(raw_format.get("fps") or 0)
            bitrate = float(raw_format.get("tbr") or 0)
            note = "muxed" if str(raw_format.get("acodec") or "none") != "none" else "video-only"
            option = FormatOption(
                format_id=str(raw_format.get("format_id") or ""),
                quality_label=self._build_video_label(raw_format),
                ext=str(raw_format.get("ext") or ""),
                note=note,
            )
            if option.format_id and option.quality_label:
                candidates.append(((-height, -fps, -bitrate), option))

        return self._dedupe_options([option for _, option in sorted(candidates, key=lambda item: item[0])])

    def _collect_audio_formats(self, info: dict[str, object]) -> list[FormatOption]:
        candidates: list[tuple[tuple[float, float], FormatOption]] = []
        fallback_candidates: list[tuple[tuple[float, float], FormatOption]] = []

        for raw_format in info.get("formats", []):
            if not isinstance(raw_format, dict):
                continue
            if str(raw_format.get("acodec") or "none") == "none":
                continue

            abr = float(raw_format.get("abr") or raw_format.get("tbr") or 0)
            asr = float(raw_format.get("asr") or 0)
            option = FormatOption(
                format_id=str(raw_format.get("format_id") or ""),
                quality_label=self._build_audio_label(raw_format),
                ext=str(raw_format.get("ext") or ""),
                note="audio-only" if str(raw_format.get("vcodec") or "none") == "none" else "muxed",
            )
            if not option.format_id or not option.quality_label:
                continue

            target = candidates
            if str(raw_format.get("vcodec") or "none") != "none":
                target = fallback_candidates
            target.append(((-abr, -asr), option))

        ordered = [option for _, option in sorted(candidates, key=lambda item: item[0])]
        if not ordered:
            ordered = [option for _, option in sorted(fallback_candidates, key=lambda item: item[0])]
        return self._dedupe_options(ordered)

    @staticmethod
    def _build_video_label(raw_format: dict[str, object]) -> str:
        resolution = raw_format.get("resolution")
        height = raw_format.get("height")
        ext = str(raw_format.get("ext") or "unknown")
        fps = raw_format.get("fps")
        note = "muxed" if str(raw_format.get("acodec") or "none") != "none" else "video-only"

        quality = ""
        if height:
            quality = f"{int(height)}p"
        elif resolution and resolution != "audio only":
            quality = str(resolution)
        elif raw_format.get("format_note"):
            quality = str(raw_format["format_note"])
        else:
            quality = "video"

        parts = [quality, ext, note]
        if fps:
            parts.append(f"{int(float(fps))}fps")
        parts.append(f"fmt {raw_format.get('format_id')}")
        return " | ".join(parts)

    @staticmethod
    def _build_audio_label(raw_format: dict[str, object]) -> str:
        abr = raw_format.get("abr") or raw_format.get("tbr")
        ext = str(raw_format.get("ext") or "unknown")
        note = "audio-only" if str(raw_format.get("vcodec") or "none") == "none" else "muxed"

        quality = "audio"
        if abr:
            quality = f"{int(float(abr))} kbps"
        elif raw_format.get("format_note"):
            quality = str(raw_format["format_note"])

        return " | ".join([quality, ext, note, f"fmt {raw_format.get('format_id')}"])

    @staticmethod
    def _dedupe_options(options: list[FormatOption]) -> list[FormatOption]:
        seen_format_ids: set[str] = set()
        deduped: list[FormatOption] = []
        for option in options:
            if option.format_id in seen_format_ids:
                continue
            seen_format_ids.add(option.format_id)
            deduped.append(option)
        return deduped

    @staticmethod
    def _normalize_download_error(error: DownloadError) -> YoutubeProbeError:
        message = str(error)
        lowered = message.lower()

        if "private" in lowered:
            return YoutubeProbeError(
                ProbeErrorCode.PRIVATE,
                "The YouTube video is private or requires access.",
            )

        if any(
            token in lowered
            for token in (
                "unsupported url",
                "invalid url",
                "incomplete youtube id",
                "did not match",
            )
        ):
            return YoutubeProbeError(
                ProbeErrorCode.INVALID,
                "Expected a valid YouTube video URL.",
            )

        return YoutubeProbeError(
            ProbeErrorCode.UNAVAILABLE,
            f"The YouTube video is unavailable: {message}",
        )
