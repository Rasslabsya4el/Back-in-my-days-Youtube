from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

_ARTWORK_SUFFIX_BY_CONTENT_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
AUDIO_ARTWORK_CONTRACT = "square_centered_crop_original_resolution_only"


@dataclass(slots=True, frozen=True)
class AudioMetadata:
    title: str
    artist: str = ""
    artwork_url: str = ""

    def ffmpeg_arguments(self) -> list[str]:
        arguments: list[str] = []
        if self.title:
            arguments.extend(["-metadata", f"title={self.title}"])
        if self.artist:
            arguments.extend(["-metadata", f"artist={self.artist}"])
        return arguments


def download_artwork(artwork_url: str, *, working_dir: Path) -> Path | None:
    normalized = artwork_url.strip()
    if not normalized:
        return None

    request = Request(normalized, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(request, timeout=20) as response:
            content_type = response.headers.get_content_type()
            if content_type and not content_type.startswith("image/"):
                return None
            payload = response.read()
    except (OSError, ValueError):
        return None

    if not payload:
        return None

    artwork_path = working_dir / f"artwork{_pick_artwork_suffix(normalized, content_type)}"
    artwork_path.write_bytes(payload)
    return artwork_path


def build_audio_artwork_cover_filter() -> str:
    return "crop='min(iw,ih)':'min(iw,ih)':'(iw-ow)/2':'(ih-oh)/2'"


def compute_audio_artwork_square_side(width: int | None, height: int | None) -> int | None:
    if width is None or height is None:
        return None
    if width <= 0 or height <= 0:
        return None
    return min(width, height)


def _pick_artwork_suffix(artwork_url: str, content_type: str) -> str:
    if content_type in _ARTWORK_SUFFIX_BY_CONTENT_TYPE:
        return _ARTWORK_SUFFIX_BY_CONTENT_TYPE[content_type]

    suffix = Path(urlsplit(artwork_url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        return ".jpg" if suffix == ".jpeg" else suffix
    return ".img"
