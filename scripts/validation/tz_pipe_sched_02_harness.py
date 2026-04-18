from __future__ import annotations

import json
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.bridge import AppBridgeApi
from app.config import AppConfig, create_default_config
from app.controller import AppController
from app.core.downloader import DownloadPipelineError, DownloadedMedia, QueueItemDownloader
from app.models import DownloadMode, FormatOption, JobStep, ProbeResult, QueueItem


TASK_ID = "TZ-PIPE-SCHED-02"
PROOF_DIR = PROJECT_ROOT / "runtime" / "pipeline-proof" / TASK_ID
OUTPUT_DIR = PROOF_DIR / "output"
TEMP_DIR = PROOF_DIR / "temp"
STATE_FILE = PROOF_DIR / "queue_state.scheduler-harness.json"
SUMMARY_PATH = PROOF_DIR / "summary.json"
FIXTURE_VIDEO_PATH = PROOF_DIR / "fixture-video.avi"
FIXTURE_AUDIO_PATH = PROOF_DIR / "fixture-audio.mp3"
SNAPSHOT_INTERVAL_SECONDS = 0.2
RUN_TIMEOUT_SECONDS = 240.0
QUEUE_ITEM_COUNT = 3


class HarnessError(RuntimeError):
    pass


class SchedulerHarnessDownloader(QueueItemDownloader):
    def __init__(
        self,
        config: AppConfig,
        *,
        fixture_video_path: Path,
        fixture_audio_path: Path,
    ) -> None:
        super().__init__(config)
        self._fixture_video_path = fixture_video_path
        self._fixture_audio_path = fixture_audio_path
        self._download_barrier = threading.Barrier(QUEUE_ITEM_COUNT, timeout=20)

    def _download_selected_media(
        self,
        item: QueueItem,
        plan: Any,
        temp_dir: Path,
    ) -> DownloadedMedia:
        del item, plan
        video_path = temp_dir / self._fixture_video_path.name
        audio_path = temp_dir / self._fixture_audio_path.name
        shutil.copy2(self._fixture_video_path, video_path)
        shutil.copy2(self._fixture_audio_path, audio_path)
        try:
            self._download_barrier.wait()
        except threading.BrokenBarrierError as error:
            raise DownloadPipelineError(
                JobStep.DOWNLOADING,
                "Scheduler harness could not align queued items before post-processing.",
            ) from error
        return DownloadedMedia(video_path=video_path, audio_path=audio_path)


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


def run_command(command: list[str], *, timeout: int = 300, check: bool = True) -> dict[str, Any]:
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


def build_fixture_media(ffmpeg_path: Path) -> list[dict[str, Any]]:
    commands = [
        run_command(
            [
                str(ffmpeg_path),
                "-y",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=size=1280x720:rate=30",
                "-t",
                "18",
                "-c:v",
                "mpeg4",
                "-q:v",
                "4",
                str(FIXTURE_VIDEO_PATH),
            ],
            timeout=300,
        ),
        run_command(
            [
                str(ffmpeg_path),
                "-y",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=880:sample_rate=48000",
                "-t",
                "18",
                "-c:a",
                "libmp3lame",
                "-b:a",
                "192k",
                str(FIXTURE_AUDIO_PATH),
            ],
            timeout=300,
        ),
    ]
    if not FIXTURE_VIDEO_PATH.exists() or not FIXTURE_AUDIO_PATH.exists():
        raise HarnessError("Fixture media generation did not produce the expected files.")
    return commands


def build_probe() -> ProbeResult:
    return ProbeResult(
        source_url="https://example.invalid/scheduler-harness",
        title="Scheduler harness title",
        channel="Scheduler harness channel",
        thumbnail="",
        duration=18,
        video_formats=[
            FormatOption(
                format_id="fixture-video",
                quality_label="720p | avi | video-only | fmt fixture-video",
                ext="avi",
                note="video-only",
            )
        ],
        audio_formats=[
            FormatOption(
                format_id="fixture-audio",
                quality_label="192 kbps | mp3 | audio-only | fmt fixture-audio",
                ext="mp3",
                note="audio-only",
            )
        ],
    )


def build_queue_items() -> list[QueueItem]:
    probe = build_probe()
    return [
        QueueItem(
            id=f"tz-pipe-sched-02-item-{index + 1}",
            source_url=f"{probe.source_url}?item={index + 1}",
            title=f"Scheduler harness item {index + 1}",
            mode=DownloadMode.VIDEO,
            quality=probe.video_formats[0].quality_label,
            probe=probe,
            selected_format_id="fixture-video+fixture-audio",
        )
        for index in range(QUEUE_ITEM_COUNT)
    ]


def snapshot_ffmpeg_processes() -> list[dict[str, Any]]:
    script = (
        "$items = @(Get-CimInstance Win32_Process -Filter \"Name = 'ffmpeg.exe'\" "
        "| Select-Object ProcessId, CommandLine); "
        "if ($items.Count -eq 0) { '[]' } else { $items | ConvertTo-Json -Compress }"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise HarnessError(
            f"Failed to snapshot ffmpeg processes.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    payload = json.loads(result.stdout or "[]")
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        raise HarnessError(f"Unexpected ffmpeg snapshot payload: {payload!r}")

    normalized: list[dict[str, Any]] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        normalized.append(
            {
                "pid": int(entry.get("ProcessId", 0) or 0),
                "command_line": str(entry.get("CommandLine", "") or ""),
            }
        )
    return normalized


def summarize_state(controller: AppController) -> dict[str, Any]:
    state = controller.get_state().to_dict()
    return {
        "status_message": state["status_message"],
        "selected_item_id": state["selected_item_id"],
        "queue": [
            {
                "id": item["id"],
                "status": item["status"],
                "processing_step": item["processing_step"],
                "status_detail": item["status_detail"],
                "output_path": item["output_path"],
                "error_message": item["error_message"],
            }
            for item in state["queue"]
        ],
    }


def run_harness() -> int:
    prepare_runtime_dirs()
    summary: dict[str, Any] = {
        "task_id": TASK_ID,
        "canonical_command": "poetry run python scripts/validation/tz_pipe_sched_02_harness.py",
        "proof_dir": str(PROOF_DIR),
        "output_dir": str(OUTPUT_DIR),
        "temp_dir": str(TEMP_DIR),
        "state_file": str(STATE_FILE),
        "fixture_video_path": str(FIXTURE_VIDEO_PATH),
        "fixture_audio_path": str(FIXTURE_AUDIO_PATH),
        "queue_item_count": QUEUE_ITEM_COUNT,
        "commands": [],
        "process_snapshots": [],
        "errors": [],
        "harness_completed": False,
    }
    exit_code = 0

    try:
        config = build_config()
        controller = AppController(config)
        ffmpeg_resolution = controller.tool_resolver.resolve_ffmpeg()
        if not ffmpeg_resolution.path:
            raise HarnessError("ffmpeg is not available; scheduler harness cannot run.")

        summary["commands"].extend(build_fixture_media(ffmpeg_resolution.path))

        harness_downloader = SchedulerHarnessDownloader(
            config,
            fixture_video_path=FIXTURE_VIDEO_PATH,
            fixture_audio_path=FIXTURE_AUDIO_PATH,
        )
        controller = AppController(config, downloader=harness_downloader)
        bridge = AppBridgeApi(controller)
        items = build_queue_items()
        controller.save_queue_state(items, selected_item_id=items[0].id)

        runtime_before = bridge.get_runtime_info()
        start_payload = bridge.start_all_downloads()
        if not start_payload["ok"] or not start_payload["data"].get("accepted"):
            raise HarnessError(f"start_all_downloads was not accepted: {start_payload}")
        if len(start_payload["data"].get("started_item_ids", [])) != QUEUE_ITEM_COUNT:
            raise HarnessError(f"Expected {QUEUE_ITEM_COUNT} started items, got {start_payload}")

        started_at = time.monotonic()
        max_ffmpeg_count = 0
        max_heavy_transcode_count = 0
        max_active_download_count = 0
        saw_waiting_slot = False
        saw_transcoding = False

        while True:
            state_snapshot = summarize_state(controller)
            runtime_snapshot = bridge.get_runtime_info()
            processes = snapshot_ffmpeg_processes()
            heavy_processes = [
                process
                for process in processes
                if "libx264" in process["command_line"] and "-c:a aac" in process["command_line"]
            ]

            max_ffmpeg_count = max(max_ffmpeg_count, len(processes))
            max_heavy_transcode_count = max(max_heavy_transcode_count, len(heavy_processes))
            max_active_download_count = max(
                max_active_download_count,
                int(runtime_snapshot["data"]["bridge"]["active_download_count"]),
            )
            saw_waiting_slot = saw_waiting_slot or any(
                item["status_detail"] == "Waiting for the video transcode slot."
                for item in state_snapshot["queue"]
            )
            saw_transcoding = saw_transcoding or any(
                item["status_detail"] == "Transcoding video into final mp4 output."
                for item in state_snapshot["queue"]
            )

            summary["process_snapshots"].append(
                {
                    "seconds_since_start": round(time.monotonic() - started_at, 3),
                    "bridge_active_download_count": runtime_snapshot["data"]["bridge"][
                        "active_download_count"
                    ],
                    "ffmpeg_count": len(processes),
                    "heavy_transcode_count": len(heavy_processes),
                    "ffmpeg_processes": processes,
                    "heavy_transcode_processes": heavy_processes,
                    "state": state_snapshot,
                }
            )

            if not runtime_snapshot["data"]["bridge"]["download_active"]:
                break
            if time.monotonic() - started_at > RUN_TIMEOUT_SECONDS:
                raise HarnessError("Scheduler harness timed out while downloads were still active.")
            time.sleep(SNAPSHOT_INTERVAL_SECONDS)

        final_state = summarize_state(controller)
        output_paths = [Path(item["output_path"]) for item in final_state["queue"] if item["output_path"]]
        if len(output_paths) != QUEUE_ITEM_COUNT:
            raise HarnessError(f"Expected {QUEUE_ITEM_COUNT} output paths, got {final_state}")
        if any(item["status"] != "completed" for item in final_state["queue"]):
            raise HarnessError(f"Expected all queue items to complete, got {final_state}")
        if any(not path.exists() or path.stat().st_size <= 0 for path in output_paths):
            raise HarnessError("One or more finalized outputs are missing or empty.")
        if max_heavy_transcode_count < 1:
            raise HarnessError("Did not observe any heavy libx264 transcode process in the scheduler harness.")
        if max_heavy_transcode_count > 1:
            raise HarnessError(
                f"Observed {max_heavy_transcode_count} simultaneous heavy transcodes; expected at most 1."
            )
        if not saw_waiting_slot or not saw_transcoding:
            raise HarnessError(
                "Scheduler harness did not observe the expected post-processing slot status details."
            )

        time.sleep(0.5)
        cleanup_snapshot = snapshot_ffmpeg_processes()
        if cleanup_snapshot:
            raise HarnessError(f"ffmpeg processes are still running after harness completion: {cleanup_snapshot}")

        summary.update(
            {
                "runtime_before": runtime_before,
                "start_all_payload": start_payload,
                "final_state": final_state,
                "output_paths": [str(path) for path in output_paths],
                "max_ffmpeg_count": max_ffmpeg_count,
                "max_heavy_transcode_count": max_heavy_transcode_count,
                "max_active_download_count": max_active_download_count,
                "saw_waiting_slot_detail": saw_waiting_slot,
                "saw_transcoding_detail": saw_transcoding,
                "cleanup_ffmpeg_processes": cleanup_snapshot,
                "harness_completed": True,
            }
        )
    except Exception as error:
        summary["errors"].append(str(error))
        summary["verdict"] = "execution_failed"
        exit_code = 1
    else:
        summary["verdict"] = "ok"
    finally:
        write_json(SUMMARY_PATH, summary)

    print(
        json.dumps(
            {
                "summary_path": str(SUMMARY_PATH),
                "verdict": summary.get("verdict"),
                "max_heavy_transcode_count": summary.get("max_heavy_transcode_count"),
                "max_active_download_count": summary.get("max_active_download_count"),
            },
            ensure_ascii=False,
        )
    )
    return exit_code


def main() -> int:
    return run_harness()


if __name__ == "__main__":
    raise SystemExit(main())
