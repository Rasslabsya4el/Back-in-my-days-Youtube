from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import AppConfig, create_default_config
from app.controller import AppController
from app.models import DownloadMode


TASK_ID = "TZ-OBS-ARTWORK-HARNESS-01"
DEFAULT_PREVIOUS_URL = "https://www.youtube.com/watch?v=Lm7-yFZ5fZQ"
DEFAULT_CURRENT_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
MATCH_AHASH_MAX = 2
MATCH_MAE_MAX = 2.0

PROOF_DIR = PROJECT_ROOT / "runtime" / "media-proof" / TASK_ID
OUTPUT_DIR = PROOF_DIR / "output"
TEMP_DIR = PROOF_DIR / "temp"
STATE_FILE = PROOF_DIR / "queue_state.artwork-harness.json"
SUMMARY_PATH = PROOF_DIR / "artwork-harness-summary.json"
PREVIOUS_INSPECT_PATH = PROOF_DIR / "inspect-previous-audio.json"
CURRENT_INSPECT_PATH = PROOF_DIR / "inspect-current-audio.json"
CURRENT_FFPROBE_PATH = PROOF_DIR / "ffprobe-current-audio.json"
PREVIOUS_THUMB_FFPROBE_PATH = PROOF_DIR / "ffprobe-previous-thumbnail.json"
CURRENT_THUMB_FFPROBE_PATH = PROOF_DIR / "ffprobe-current-thumbnail.json"
PREVIOUS_STATE_PATH = PROOF_DIR / "state-after-previous-download.json"
AFTER_CLEAR_STATE_PATH = PROOF_DIR / "state-after-clear.json"
CURRENT_STATE_PATH = PROOF_DIR / "state-after-current-download.json"
EXTRACTED_ARTWORK_PATH = PROOF_DIR / "extracted-attached-pic.jpg"
CURRENT_THUMB_PATH = PROOF_DIR / "current-thumbnail.jpg"
PREVIOUS_THUMB_PATH = PROOF_DIR / "previous-thumbnail.jpg"


class HarnessError(RuntimeError):
    pass


@dataclass(slots=True, frozen=True)
class ImageSignature:
    average_hash: str
    normalized_sha256: str
    normalized_gray: bytes

    def to_dict(self) -> dict[str, str]:
        return {
            "average_hash": self.average_hash,
            "normalized_sha256": self.normalized_sha256,
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reproduce old-item -> Clear queue -> new audio artwork flow.",
    )
    parser.add_argument(
        "--previous-url",
        default=DEFAULT_PREVIOUS_URL,
        help="URL used to create the old queue item and old artwork.",
    )
    parser.add_argument(
        "--current-url",
        default=DEFAULT_CURRENT_URL,
        help="URL used for the post-clear audio download under test.",
    )
    return parser


def build_config() -> AppConfig:
    default_config = create_default_config(PROJECT_ROOT)
    return AppConfig(
        project_root=PROJECT_ROOT,
        runtime_dir=PROOF_DIR,
        output_dir=OUTPUT_DIR,
        temp_dir=TEMP_DIR,
        state_file=STATE_FILE,
        bundled_tools_dir=default_config.bundled_tools_dir,
    )


def prepare_runtime_dirs() -> None:
    shutil.rmtree(PROOF_DIR, ignore_errors=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def download_file(url: str, destination: Path) -> None:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=30) as response:
        payload = response.read()
    if not payload:
        raise HarnessError(f"Downloaded empty payload from {url!r}.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)


def selected_item_or_raise(controller: AppController) -> Any:
    state = controller.get_state()
    selected = state.selected_item or (state.queue[0] if state.queue else None)
    if selected is None:
        raise HarnessError("Controller state has no selected queue item.")
    return selected


def run_command(
    command: list[str],
    *,
    timeout: int = 300,
    check: bool = True,
) -> dict[str, Any]:
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    payload = {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
    if check and result.returncode != 0:
        raise HarnessError(
            f"Command failed: {' '.join(command)}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return payload


def run_ffprobe(ffprobe_path: Path, media_path: Path, output_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    command_payload = run_command(
        [
            str(ffprobe_path),
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(media_path),
        ],
        timeout=120,
    )
    payload = json.loads(command_payload["stdout"] or "{}")
    write_json(output_path, payload)
    return payload, command_payload


def extract_attached_artwork(
    ffmpeg_path: Path,
    audio_path: Path,
    extracted_artwork_path: Path,
) -> dict[str, Any]:
    return run_command(
        [
            str(ffmpeg_path),
            "-y",
            "-v",
            "error",
            "-i",
            str(audio_path),
            "-map",
            "0:v:0",
            "-frames:v",
            "1",
            "-update",
            "1",
            str(extracted_artwork_path),
        ],
        timeout=120,
        check=False,
    )


def render_normalized_gray(image_path: Path, ffmpeg_path: Path, *, size: int) -> bytes:
    result = subprocess.run(
        [
            str(ffmpeg_path),
            "-v",
            "error",
            "-i",
            str(image_path),
            "-vf",
            (
                f"scale={size}:{size}:force_original_aspect_ratio=decrease,"
                f"pad={size}:{size}:(ow-iw)/2:(oh-ih)/2:black,format=gray"
            ),
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-",
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise HarnessError(
            f"ffmpeg failed to render normalized pixels for {image_path}:\n{result.stderr.decode(errors='replace')}"
        )

    expected_bytes = size * size
    if len(result.stdout) != expected_bytes:
        raise HarnessError(
            f"Expected {expected_bytes} normalized bytes for {image_path}, got {len(result.stdout)}."
        )
    return result.stdout


def average_hash(raw_gray: bytes) -> str:
    average = sum(raw_gray) / len(raw_gray)
    bits = "".join("1" if value >= average else "0" for value in raw_gray)
    return f"{int(bits, 2):0{len(raw_gray) // 4}x}"


def build_image_signature(image_path: Path, ffmpeg_path: Path) -> ImageSignature:
    normalized_gray_64 = render_normalized_gray(image_path, ffmpeg_path, size=64)
    normalized_gray_8 = render_normalized_gray(image_path, ffmpeg_path, size=8)
    return ImageSignature(
        average_hash=average_hash(normalized_gray_8),
        normalized_sha256=hashlib.sha256(normalized_gray_64).hexdigest(),
        normalized_gray=normalized_gray_64,
    )


def hamming_distance(left: str, right: str) -> int:
    return bin(int(left, 16) ^ int(right, 16)).count("1")


def mean_absolute_error(left: bytes, right: bytes) -> float:
    return sum(abs(a - b) for a, b in zip(left, right)) / len(left)


def compare_signatures(left: ImageSignature, right: ImageSignature) -> dict[str, Any]:
    mae = mean_absolute_error(left.normalized_gray, right.normalized_gray)
    return {
        "average_hash_distance": hamming_distance(left.average_hash, right.average_hash),
        "normalized_mae": round(mae, 6),
        "normalized_sha256_equal": left.normalized_sha256 == right.normalized_sha256,
        "match_thresholds": {
            "average_hash_distance_max": MATCH_AHASH_MAX,
            "normalized_mae_max": MATCH_MAE_MAX,
        },
    }


def is_signature_match(compare_payload: dict[str, Any]) -> bool:
    return (
        int(compare_payload["average_hash_distance"]) <= MATCH_AHASH_MAX
        and float(compare_payload["normalized_mae"]) <= MATCH_MAE_MAX
    )


def list_relative_paths(root: Path, pattern: str) -> list[str]:
    if not root.exists():
        return []
    return sorted(str(path.relative_to(PROOF_DIR)) for path in root.rglob(pattern))


def find_attached_pic_stream(ffprobe_payload: dict[str, Any]) -> dict[str, Any] | None:
    streams = ffprobe_payload.get("streams", [])
    if not isinstance(streams, list):
        return None
    for stream in streams:
        if not isinstance(stream, dict):
            continue
        disposition = stream.get("disposition")
        if isinstance(disposition, dict) and bool(disposition.get("attached_pic")):
            return stream
    return None


def find_primary_visual_stream(ffprobe_payload: dict[str, Any]) -> dict[str, Any] | None:
    streams = ffprobe_payload.get("streams", [])
    if not isinstance(streams, list):
        return None
    for stream in streams:
        if not isinstance(stream, dict):
            continue
        if str(stream.get("codec_type") or "") == "video":
            return stream
    return None


def parse_optional_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def run_harness(*, previous_url: str, current_url: str) -> int:
    prepare_runtime_dirs()
    summary: dict[str, Any] = {
        "task_id": TASK_ID,
        "previous_url": previous_url,
        "current_url": current_url,
        "canonical_command": "poetry run python main.py --smoke-artwork-harness",
        "proof_dir": str(PROOF_DIR),
        "output_dir": str(OUTPUT_DIR),
        "temp_dir": str(TEMP_DIR),
        "state_file": str(STATE_FILE),
        "commands": [],
        "errors": [],
        "harness_completed": False,
    }
    exit_code = 0

    try:
        controller = AppController(build_config())
        ffmpeg_resolution = controller.tool_resolver.resolve_ffmpeg()
        ffprobe_resolution = controller.tool_resolver.resolve_ffprobe()
        if not ffmpeg_resolution.path:
            raise HarnessError("ffmpeg is not available; harness cannot extract attached artwork.")
        if not ffprobe_resolution.path:
            raise HarnessError("ffprobe is not available; harness cannot inspect output.")

        summary["runtime_snapshot"] = controller.get_runtime_snapshot().to_dict()

        controller.add_url(previous_url)
        controller.select_mode(DownloadMode.AUDIO)
        controller.start_download()
        previous_item = selected_item_or_raise(controller)
        previous_audio_path = Path(previous_item.output_path)
        if not previous_audio_path.exists():
            raise HarnessError(f"Previous audio output is missing: {previous_audio_path}")

        previous_inspection = controller.inspect_output(previous_audio_path)
        if previous_inspection is None:
            raise HarnessError("Previous audio inspection returned None despite ffprobe availability.")
        write_json(PREVIOUS_INSPECT_PATH, previous_inspection)
        if not previous_inspection.get("has_attached_pic"):
            raise HarnessError(
                "Previous audio download did not produce embedded artwork; requested precondition was not met."
            )
        write_json(PREVIOUS_STATE_PATH, controller.get_state().to_dict())

        cleared_state = controller.clear_queue()
        write_json(AFTER_CLEAR_STATE_PATH, cleared_state.to_dict())
        state_file_exists_after_clear = STATE_FILE.exists()
        queue_reset_flow_green = (
            len(cleared_state.queue) == 0
            and cleared_state.selected_item is None
            and not state_file_exists_after_clear
        )

        controller.add_url(current_url)
        controller.select_mode(DownloadMode.AUDIO)
        controller.start_download()
        current_item = selected_item_or_raise(controller)
        current_audio_path = Path(current_item.output_path)
        if not current_audio_path.exists():
            raise HarnessError(f"Current audio output is missing: {current_audio_path}")
        write_json(CURRENT_STATE_PATH, controller.get_state().to_dict())

        current_inspection = controller.inspect_output(current_audio_path)
        if current_inspection is None:
            raise HarnessError("Current audio inspection returned None despite ffprobe availability.")
        write_json(CURRENT_INSPECT_PATH, current_inspection)

        ffprobe_payload, ffprobe_command = run_ffprobe(
            ffprobe_resolution.path,
            current_audio_path,
            CURRENT_FFPROBE_PATH,
        )
        summary["commands"].append(ffprobe_command)

        extract_command = extract_attached_artwork(
            ffmpeg_resolution.path,
            current_audio_path,
            EXTRACTED_ARTWORK_PATH,
        )
        summary["commands"].append(extract_command)

        previous_thumbnail_url = previous_item.probe.thumbnail if previous_item.probe else ""
        current_thumbnail_url = current_item.probe.thumbnail if current_item.probe else ""
        if not previous_thumbnail_url or not current_thumbnail_url:
            raise HarnessError("Missing previous or current thumbnail URL in probe data.")
        download_file(previous_thumbnail_url, PREVIOUS_THUMB_PATH)
        download_file(current_thumbnail_url, CURRENT_THUMB_PATH)
        previous_thumbnail_ffprobe, previous_thumbnail_ffprobe_command = run_ffprobe(
            ffprobe_resolution.path,
            PREVIOUS_THUMB_PATH,
            PREVIOUS_THUMB_FFPROBE_PATH,
        )
        summary["commands"].append(previous_thumbnail_ffprobe_command)
        current_thumbnail_ffprobe, current_thumbnail_ffprobe_command = run_ffprobe(
            ffprobe_resolution.path,
            CURRENT_THUMB_PATH,
            CURRENT_THUMB_FFPROBE_PATH,
        )
        summary["commands"].append(current_thumbnail_ffprobe_command)

        current_attached_pic_stream = find_attached_pic_stream(ffprobe_payload)
        current_thumbnail_stream = find_primary_visual_stream(current_thumbnail_ffprobe)
        previous_thumbnail_stream = find_primary_visual_stream(previous_thumbnail_ffprobe)
        current_attached_pic_width = parse_optional_int(
            current_attached_pic_stream.get("width") if current_attached_pic_stream else None
        )
        current_attached_pic_height = parse_optional_int(
            current_attached_pic_stream.get("height") if current_attached_pic_stream else None
        )
        current_thumbnail_width = parse_optional_int(
            current_thumbnail_stream.get("width") if current_thumbnail_stream else None
        )
        current_thumbnail_height = parse_optional_int(
            current_thumbnail_stream.get("height") if current_thumbnail_stream else None
        )
        previous_thumbnail_width = parse_optional_int(
            previous_thumbnail_stream.get("width") if previous_thumbnail_stream else None
        )
        previous_thumbnail_height = parse_optional_int(
            previous_thumbnail_stream.get("height") if previous_thumbnail_stream else None
        )
        embedded_artwork_stream_exists = (
            bool(current_inspection.get("has_attached_pic")) and current_attached_pic_stream is not None
        )
        embedded_artwork_is_square = (
            embedded_artwork_stream_exists
            and current_attached_pic_width is not None
            and current_attached_pic_height is not None
            and current_attached_pic_width == current_attached_pic_height
        )
        current_source_artwork_is_square = (
            current_thumbnail_width is not None
            and current_thumbnail_height is not None
            and current_thumbnail_width == current_thumbnail_height
        )
        embedded_artwork_dimensions_match_current_source = (
            embedded_artwork_stream_exists
            and current_attached_pic_width is not None
            and current_attached_pic_height is not None
            and current_thumbnail_width is not None
            and current_thumbnail_height is not None
            and current_attached_pic_width == current_thumbnail_width
            and current_attached_pic_height == current_thumbnail_height
        )

        embedded_artwork_missing = not (
            embedded_artwork_stream_exists
            and EXTRACTED_ARTWORK_PATH.exists()
            and EXTRACTED_ARTWORK_PATH.stat().st_size > 0
        )

        current_compare: dict[str, Any] | None = None
        previous_compare: dict[str, Any] | None = None
        embedded_artwork_matches_current = False
        embedded_artwork_matches_previous = False
        extracted_signature_payload: dict[str, str] | None = None
        current_signature_payload: dict[str, str] | None = None
        previous_signature_payload: dict[str, str] | None = None

        if not embedded_artwork_missing:
            extracted_signature = build_image_signature(EXTRACTED_ARTWORK_PATH, ffmpeg_resolution.path)
            current_signature = build_image_signature(CURRENT_THUMB_PATH, ffmpeg_resolution.path)
            previous_signature = build_image_signature(PREVIOUS_THUMB_PATH, ffmpeg_resolution.path)
            extracted_signature_payload = extracted_signature.to_dict()
            current_signature_payload = current_signature.to_dict()
            previous_signature_payload = previous_signature.to_dict()
            current_compare = compare_signatures(extracted_signature, current_signature)
            previous_compare = compare_signatures(extracted_signature, previous_signature)
            embedded_artwork_matches_current = is_signature_match(current_compare)
            embedded_artwork_matches_previous = is_signature_match(previous_compare)

        temp_entries = list_relative_paths(TEMP_DIR, "*")
        temp_artwork_entries = list_relative_paths(TEMP_DIR, "artwork*")
        staged_output_entries = list_relative_paths(OUTPUT_DIR, "*.staged*")
        cleanup_green = not temp_entries and not temp_artwork_entries and not staged_output_entries

        ui_only_suspected = (
            queue_reset_flow_green
            and cleanup_green
            and embedded_artwork_stream_exists
            and not embedded_artwork_missing
            and embedded_artwork_dimensions_match_current_source
            and embedded_artwork_matches_current
            and not embedded_artwork_matches_previous
        )
        core_bug_confirmed = not ui_only_suspected

        if ui_only_suspected:
            verdict = "core_path_green_ui_only_suspected"
            localization = ["ui_surface"]
        else:
            reasons: list[str] = []
            if not queue_reset_flow_green:
                reasons.append("queue_reset_flow")
            if not cleanup_green:
                reasons.append("cleanup")
            if (
                not embedded_artwork_stream_exists
                or embedded_artwork_missing
                or not embedded_artwork_dimensions_match_current_source
                or embedded_artwork_matches_previous
                or not embedded_artwork_matches_current
            ):
                reasons.append("embedded_artwork")
            localization = reasons or ["unknown_core_failure"]
            verdict = "core_bug_confirmed"

        summary.update(
            {
                "previous_audio_path": str(previous_audio_path),
                "current_audio_path": str(current_audio_path),
                "previous_audio_inspection": previous_inspection,
                "current_audio_inspection": current_inspection,
                "current_audio_ffprobe": ffprobe_payload,
                "audio_artwork_contract": "full_original_downloaded_artwork",
                "attached_pic_can_be_nonsquare": True,
                "previous_thumbnail_path": str(PREVIOUS_THUMB_PATH),
                "current_thumbnail_path": str(CURRENT_THUMB_PATH),
                "previous_reference_artwork_path": str(PREVIOUS_THUMB_PATH),
                "current_reference_artwork_path": str(CURRENT_THUMB_PATH),
                "previous_thumbnail_ffprobe": previous_thumbnail_ffprobe,
                "current_thumbnail_ffprobe": current_thumbnail_ffprobe,
                "extracted_artwork_path": str(EXTRACTED_ARTWORK_PATH),
                "embedded_artwork_stream_exists": embedded_artwork_stream_exists,
                "embedded_artwork_is_square": embedded_artwork_is_square,
                "current_source_artwork_is_square": current_source_artwork_is_square,
                "embedded_artwork_dimensions": {
                    "width": current_attached_pic_width,
                    "height": current_attached_pic_height,
                },
                "current_source_artwork_dimensions": {
                    "width": current_thumbnail_width,
                    "height": current_thumbnail_height,
                },
                "previous_source_artwork_dimensions": {
                    "width": previous_thumbnail_width,
                    "height": previous_thumbnail_height,
                },
                "embedded_artwork_stream": current_attached_pic_stream,
                "embedded_artwork_dimensions_match_current_source": (
                    embedded_artwork_dimensions_match_current_source
                ),
                "queue_reset_flow_green": queue_reset_flow_green,
                "queue_reset_after_clear": {
                    "queue_count": len(cleared_state.queue),
                    "selected_item_id": cleared_state.selected_item_id,
                    "selected_item_present": cleared_state.selected_item is not None,
                    "state_file_exists": state_file_exists_after_clear,
                    "status_message": cleared_state.status_message,
                },
                "cleanup_green": cleanup_green,
                "cleanup": {
                    "temp_entries": temp_entries,
                    "temp_artwork_entries": temp_artwork_entries,
                    "staged_output_entries": staged_output_entries,
                },
                "image_signatures": {
                    "extracted_artwork": extracted_signature_payload,
                    "current_reference_artwork": current_signature_payload,
                    "previous_reference_artwork": previous_signature_payload,
                },
                "image_compare": {
                    "current": current_compare,
                    "previous": previous_compare,
                },
                "embedded_artwork_matches_current": embedded_artwork_matches_current,
                "embedded_artwork_matches_previous": embedded_artwork_matches_previous,
                "embedded_artwork_missing": embedded_artwork_missing,
                "core_bug_confirmed": core_bug_confirmed,
                "ui_only_suspected": ui_only_suspected,
                "verdict": verdict,
                "core_localization": localization,
                "harness_completed": True,
            }
        )
    except Exception as error:
        summary["errors"].append(str(error))
        summary["verdict"] = "execution_failed"
        exit_code = 1
    finally:
        write_json(SUMMARY_PATH, summary)

    print(
        json.dumps(
            {
                "summary_path": str(SUMMARY_PATH),
                "verdict": summary.get("verdict"),
                "core_bug_confirmed": summary.get("core_bug_confirmed"),
                "ui_only_suspected": summary.get("ui_only_suspected"),
            },
            ensure_ascii=False,
        )
    )
    return exit_code


def main() -> int:
    args = build_parser().parse_args()
    return run_harness(previous_url=args.previous_url, current_url=args.current_url)


if __name__ == "__main__":
    raise SystemExit(main())
