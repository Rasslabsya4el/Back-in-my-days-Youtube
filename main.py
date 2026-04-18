from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import threading
import time
from pathlib import Path

from app.bridge import AppBridgeApi, BridgeHostError, PywebviewHost
from app.config import AppConfig, create_default_config
from app.controller import AppController
from app.core import DownloadPipelineError, MediaPostprocessError, YoutubeProbeError
from app.models import DownloadMode, FormatOption, JobStatus, JobStep, ProbeResult, QueueItem


SMOKE_INSPECTION_OK = "ok"
SMOKE_INSPECTION_UNAVAILABLE = "ffprobe_unavailable"
SMOKE_INSPECTION_FAILED = "failed"
SMOKE_INSPECTION_UNAVAILABLE_MESSAGE = (
    "Output inspection is unavailable because ffprobe is not available."
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="YT Downloader app shell")
    parser.add_argument(
        "--ui-shell",
        choices=("tk", "bridge"),
        default="bridge",
        help="Launch the React bridge shell or the legacy Tk diagnostic shell.",
    )
    parser.add_argument(
        "--bridge-start-url",
        help="Optional bridge host URL override; when set, it takes precedence over frontend/dist for --ui-shell bridge and --smoke-bridge-host.",
    )
    parser.add_argument(
        "--bridge-debug",
        action="store_true",
        help="Enable pywebview debug mode for the bridge shell.",
    )
    parser.add_argument(
        "--smoke-start",
        action="store_true",
        help="Initialize the UI shell and exit immediately.",
    )
    parser.add_argument(
        "--smoke-state",
        action="store_true",
        help="Create and persist a sample queue item, then reload it.",
    )
    parser.add_argument(
        "--smoke-probe",
        action="append",
        metavar="URL",
        help="Probe one or more YouTube URLs without downloading media.",
    )
    parser.add_argument(
        "--smoke-intake",
        metavar="URL",
        help="Run the add-to-queue intake flow without starting the main UI loop.",
    )
    parser.add_argument(
        "--smoke-download",
        metavar="URL",
        help="Probe a URL, persist a queue item, reload it, and run the real download pipeline.",
    )
    parser.add_argument(
        "--smoke-download-mode",
        choices=(DownloadMode.VIDEO.value, DownloadMode.AUDIO.value),
        default=DownloadMode.VIDEO.value,
        help="Mode for --smoke-download.",
    )
    parser.add_argument(
        "--smoke-download-format-id",
        help="Explicit saved format_id for --smoke-download. Video mode also accepts values like 137+140.",
    )
    parser.add_argument(
        "--smoke-bridge",
        metavar="URL",
        help="Run a headless JSON-safe bridge smoke without importing Tkinter.",
    )
    parser.add_argument(
        "--smoke-bridge-concurrency",
        action="store_true",
        help="Run a deterministic bridge concurrency smoke and save proof artifacts under runtime/ui-proof.",
    )
    parser.add_argument(
        "--smoke-bridge-host",
        action="store_true",
        help="Start the pywebview bridge host and auto-close it after a short startup probe.",
    )
    return parser


def create_smoke_config(state_file_name: str) -> AppConfig:
    config = create_default_config()
    return AppConfig(
        project_root=config.project_root,
        runtime_dir=config.runtime_dir,
        output_dir=config.output_dir,
        temp_dir=config.temp_dir,
        state_file=config.runtime_dir / state_file_name,
        bundled_tools_dir=config.bundled_tools_dir,
    )


def run_smoke_state() -> None:
    config = create_smoke_config("queue_state.smoke.json")
    if config.state_file.exists():
        config.state_file.unlink()
    controller = AppController(config)

    sample_probe = ProbeResult(
        source_url="https://www.youtube.com/watch?v=BaW_jenozKc",
        title="Smoke test item",
        channel="yt-dlp test suite",
        thumbnail="https://i.ytimg.com/vi/BaW_jenozKc/hqdefault.jpg",
        duration=10,
        video_formats=[
            FormatOption(
                format_id="137",
                quality_label="1080p | mp4 | video-only | fmt 137",
                ext="mp4",
                note="video-only",
            ),
            FormatOption(
                format_id="136",
                quality_label="720p | mp4 | video-only | fmt 136",
                ext="mp4",
                note="video-only",
            )
        ],
        audio_formats=[
            FormatOption(
                format_id="140",
                quality_label="128 kbps | m4a | audio-only | fmt 140",
                ext="m4a",
                note="audio-only",
            ),
            FormatOption(
                format_id="251",
                quality_label="160 kbps | webm | audio-only | fmt 251",
                ext="webm",
                note="audio-only",
            )
        ],
    )

    sample_item = QueueItem(
        source_url=sample_probe.source_url,
        mode=DownloadMode.VIDEO,
        quality=sample_probe.video_formats[0].quality_label,
        title=sample_probe.title,
        probe=sample_probe,
        selected_format_id="137",
    )
    secondary_item = QueueItem(
        source_url=f"{sample_probe.source_url}&list=smoke",
        mode=DownloadMode.VIDEO,
        quality=sample_probe.video_formats[1].quality_label,
        title="Smoke test item 2",
        probe=sample_probe,
        selected_format_id="136",
    )
    controller.save_queue_state([sample_item, secondary_item], selected_item_id=secondary_item.id)
    controller.select_item(secondary_item.id)
    controller.select_mode(DownloadMode.AUDIO)
    controller.select_quality(sample_probe.audio_formats[1].quality_label)

    persisted_payload = json.loads(config.state_file.read_text(encoding="utf-8"))
    reloaded_state = AppController(config).get_state()
    selected = reloaded_state.selected_item or reloaded_state.queue[0]
    print(
        " ".join(
            [
                f"queue_items={len(reloaded_state.queue)}",
                f"state_file={config.state_file}",
                f"persisted_selected_item_id={persisted_payload.get('selected_item_id', '')!r}",
                f"selected_item_id={reloaded_state.selected_item_id!r}",
                f"selected_item_title={selected.title!r}",
                f"mode={reloaded_state.selection.mode!r}",
                f"selected_quality={reloaded_state.selection.quality!r}",
                f"selected_format_id={reloaded_state.selection.selected_format_id!r}",
                f"queue_selected_mode={selected.mode!r}",
                f"queue_selected_quality={selected.quality!r}",
                f"queue_selected_format_id={selected.selected_format_id!r}",
                f"probe_title={selected.probe.title if selected.probe else 'missing'}",
                f"video_options={len(selected.probe.video_formats) if selected.probe else 0}",
                f"audio_options={len(selected.probe.audio_formats) if selected.probe else 0}",
            ]
        )
    )


def run_smoke_start() -> None:
    from app.shell import AppShell

    controller = AppController(create_default_config())
    app = AppShell(controller)
    app.root.update_idletasks()
    app.root.update()
    app.close()
    print("ui_smoke=ok")


def run_smoke_probe(urls: list[str]) -> None:
    controller = AppController(create_default_config())
    for url in urls:
        try:
            probe = controller.probe_url(url)
            print(
                " ".join(
                    [
                        f"url={url}",
                        "probe=ok",
                        f"normalized={probe.source_url}",
                        f"title={probe.title!r}",
                        f"video_options={len(probe.video_formats)}",
                        f"audio_options={len(probe.audio_formats)}",
                    ]
                )
            )
        except YoutubeProbeError as error:
            print(
                " ".join(
                    [
                        f"url={url}",
                        "probe=error",
                        f"code={error.code.value}",
                        f"message={error!s}",
                    ]
                )
            )


def run_smoke_intake(url: str) -> None:
    config = create_smoke_config("queue_state.intake.smoke.json")
    if config.state_file.exists():
        config.state_file.unlink()
    controller = AppController(config)
    try:
        state = controller.add_url(url)
    except YoutubeProbeError as error:
        print(
            " ".join(
                [
                    "intake=error",
                    f"code={error.code.value}",
                    f"message={error!s}",
                ]
            )
        )
        return

    item = state.selected_item
    if item is None:
        print("intake=error reason='no selected item after intake'")
        return

    print(
        " ".join(
            [
                "intake=ok",
                f"title={item.title!r}",
                f"selected_quality={state.selection.quality!r}",
                f"selected_format_id={state.selection.selected_format_id!r}",
                f"quality_values={list(state.selection.quality_options)!r}",
                f"video_options={len(item.probe.video_formats) if item.probe else 0}",
                f"audio_options={len(item.probe.audio_formats) if item.probe else 0}",
            ]
        )
    )


def run_smoke_download(url: str, mode: DownloadMode, format_id: str | None) -> None:
    smoke_suffix = re.sub(r"[^A-Za-z0-9_-]+", "_", format_id or "default").strip("_") or "default"
    config = create_smoke_config(f"queue_state.download.{mode.value}.{smoke_suffix}.smoke.json")
    config.ensure_directories()
    if config.state_file.exists():
        config.state_file.unlink()

    controller = AppController(config)
    try:
        probe = controller.probe_url(url)
    except YoutubeProbeError as error:
        print(
            " ".join(
                [
                    "download=error",
                    f"mode={mode.value}",
                    f"code={error.code.value}",
                    f"message={error!s}",
                ]
            )
        )
        return

    try:
        item = _build_smoke_download_item(probe=probe, mode=mode, format_id=format_id)
    except ValueError as error:
        print(f"download=error reason={error!s}")
        return

    controller.save_queue_state([item], selected_item_id=item.id)
    state = controller.load_queue_state()
    if not state.queue:
        print("download=error reason='failed to reload persisted queue item'")
        return

    try:
        state = controller.start_download(item.id)
    except DownloadPipelineError:
        state = controller.get_state()
        loaded_item = state.selected_item or state.queue[0]
        print(
            " ".join(
                [
                    "download=error",
                    f"mode={mode.value}",
                    f"selected_format_id={loaded_item.selected_format_id!r}",
                    f"status={loaded_item.status}",
                    f"step={loaded_item.processing_step}",
                    f"detail={loaded_item.status_detail!r}",
                    f"output_path={loaded_item.output_path!r}",
                    f"error={loaded_item.error_message!r}",
                ]
            )
        )
        return

    loaded_item = state.selected_item or state.queue[0]
    output_path = Path(loaded_item.output_path)
    try:
        inspection = controller.inspect_output(output_path)
    except MediaPostprocessError as error:
        inspection = None
        inspection_status = SMOKE_INSPECTION_FAILED
        inspection_message = str(error)
        format_name = ""
        stream_types = []
    else:
        if inspection is None:
            inspection_status = SMOKE_INSPECTION_UNAVAILABLE
            inspection_message = SMOKE_INSPECTION_UNAVAILABLE_MESSAGE
            format_name = ""
            stream_types = []
        else:
            inspection_status = SMOKE_INSPECTION_OK
            inspection_message = ""
            format_name = inspection["format_name"]
            stream_types = inspection["stream_types"]

    print(
        " ".join(
            [
                "download=ok",
                f"mode={mode.value}",
                f"selected_format_id={loaded_item.selected_format_id!r}",
                f"status={loaded_item.status}",
                f"step={loaded_item.processing_step}",
                f"detail={loaded_item.status_detail!r}",
                f"output_path={loaded_item.output_path!r}",
                f"suffix={output_path.suffix!r}",
                f"size={output_path.stat().st_size}",
                f"inspection_status={inspection_status!r}",
                f"inspection_message={inspection_message!r}",
                f"format_name={format_name!r}",
                f"stream_types={stream_types!r}",
                f"error={loaded_item.error_message!r}",
            ]
        )
    )


class _BridgeSmokeDownloader:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    def predict_output_path(
        self,
        item: QueueItem,
        *,
        output_dir: Path | None = None,
        reserved_paths: list[Path] | tuple[Path, ...] | None = None,
    ) -> Path:
        target_dir = output_dir or self.output_dir
        suffix = ".m4a" if item.mode == DownloadMode.AUDIO else ".mp4"
        safe_title = self._sanitize_filename(item.title or item.source_url or item.id)
        return self._resolve_output_collision(
            target_dir=target_dir,
            safe_title=safe_title,
            suffix=suffix,
            reserved_paths=reserved_paths,
        )

    def execute(
        self,
        item: QueueItem,
        *,
        on_update: object | None = None,
        output_dir: Path | None = None,
    ) -> Path:
        target_dir = output_dir or self.output_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        output_path = target_dir / f"{item.id}.bridge-smoke.mp4"
        self._update_item(
            item,
            status=JobStatus.RUNNING,
            step=JobStep.PREPARING,
            detail="bridge smoke preparing",
            on_update=on_update,
        )
        self._update_item(
            item,
            status=JobStatus.RUNNING,
            step=JobStep.DOWNLOADING,
            detail="bridge smoke downloading",
            on_update=on_update,
        )
        output_path.write_text("bridge smoke artifact", encoding="utf-8")
        item.output_path = str(output_path)
        item.error_message = ""
        self._update_item(
            item,
            status=JobStatus.COMPLETED,
            step=JobStep.COMPLETED,
            detail="bridge smoke completed",
            on_update=on_update,
        )
        return output_path

    def inspect_output(self, media_path: Path) -> dict[str, object] | None:
        if not media_path.exists():
            return None
        return {
            "format_name": "bridge-smoke",
            "stream_types": ["video"],
            "path": str(media_path),
        }

    @staticmethod
    def _update_item(
        item: QueueItem,
        *,
        status: JobStatus,
        step: JobStep,
        detail: str,
        on_update: object | None,
    ) -> None:
        item.status = status
        item.processing_step = step
        item.status_detail = detail
        item.touch()
        if callable(on_update):
            on_update(item)

    @staticmethod
    def _resolve_output_collision(
        *,
        target_dir: Path,
        safe_title: str,
        suffix: str,
        reserved_paths: list[Path] | tuple[Path, ...] | None = None,
    ) -> Path:
        reserved = {
            reserved_path.expanduser().resolve()
            for reserved_path in (reserved_paths or ())
        }
        candidate = target_dir / f"{safe_title}{suffix}"
        if not candidate.exists() and candidate.expanduser().resolve() not in reserved:
            return candidate

        collision_index = 2
        while True:
            candidate = target_dir / f"{safe_title} ({collision_index}){suffix}"
            if not candidate.exists() and candidate.expanduser().resolve() not in reserved:
                return candidate
            collision_index += 1

    @staticmethod
    def _sanitize_filename(value: str) -> str:
        collapsed = re.sub(r"\s+", " ", value).strip()
        cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", collapsed)
        cleaned = cleaned.rstrip(". ")
        if not cleaned:
            cleaned = "download"
        return cleaned[:80]


class _BridgeConcurrencySmokeDownloader(_BridgeSmokeDownloader):
    def __init__(self, output_dir: Path, overlap_target: int = 2) -> None:
        super().__init__(output_dir)
        self._barrier = threading.Barrier(overlap_target, timeout=5)

    def execute(
        self,
        item: QueueItem,
        *,
        on_update: object | None = None,
        output_dir: Path | None = None,
    ) -> Path:
        target_dir = output_dir or self.output_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        output_path = Path(item.output_path) if item.output_path else target_dir / f"{item.id}.bridge-smoke.mp4"
        self._update_item(
            item,
            status=JobStatus.RUNNING,
            step=JobStep.PREPARING,
            detail="bridge concurrency preparing",
            on_update=on_update,
        )
        time.sleep(0.1)
        self._update_item(
            item,
            status=JobStatus.RUNNING,
            step=JobStep.DOWNLOADING,
            detail="bridge concurrency overlap window",
            on_update=on_update,
        )
        try:
            self._barrier.wait()
        except threading.BrokenBarrierError as error:
            raise DownloadPipelineError(
                JobStep.DOWNLOADING,
                "Concurrency smoke did not reach a two-job overlap window.",
            ) from error
        time.sleep(0.35)
        output_path.write_text(f"bridge concurrency artifact for {item.id}", encoding="utf-8")
        item.output_path = str(output_path)
        item.error_message = ""
        self._update_item(
            item,
            status=JobStatus.COMPLETED,
            step=JobStep.COMPLETED,
            detail="bridge concurrency completed",
            on_update=on_update,
        )
        return output_path

    def inspect_output(self, media_path: Path) -> dict[str, object] | None:
        if not media_path.exists():
            return None
        return {
            "format_name": "bridge-concurrency-smoke",
            "stream_types": ["video"],
            "path": str(media_path),
        }

    @staticmethod
    def _update_item(
        item: QueueItem,
        *,
        status: JobStatus,
        step: JobStep,
        detail: str,
        on_update: object | None,
    ) -> None:
        item.status = status
        item.processing_step = step
        item.status_detail = detail
        item.touch()
        if callable(on_update):
            on_update(item)


def run_smoke_bridge(url: str) -> None:
    config = create_smoke_config("queue_state.bridge.smoke.json")
    if config.state_file.exists():
        config.state_file.unlink()
    for stale_artifact in config.output_dir.glob("*.bridge-smoke.mp4"):
        stale_artifact.unlink()

    controller = AppController(config, downloader=_BridgeSmokeDownloader(config.output_dir))
    bridge = AppBridgeApi(controller)

    runtime_payload = bridge.get_runtime_info()
    state_payload = bridge.get_app_state()
    intake_payload = bridge.add_url({"url": url})
    if not intake_payload["ok"]:
        print(
            " ".join(
                [
                    "bridge_smoke=error",
                    f"stage=add_url",
                    f"code={intake_payload['error']['code']!r}",
                    f"message={intake_payload['error']['message']!r}",
                ]
            )
        )
        return

    queue = intake_payload["data"]["state"]["queue"]
    selected_item_id = intake_payload["data"]["state"]["selected_item_id"]
    select_item_payload = bridge.select_item({"item_id": selected_item_id})
    audio_payload = bridge.select_mode({"mode": DownloadMode.AUDIO.value})
    audio_options = audio_payload["data"]["state"]["selection"]["quality_options"]
    quality_payload = bridge.select_quality({"quality": audio_options[0] if audio_options else ""})
    download_payload = bridge.start_download({"item_id": selected_item_id})
    if not download_payload["ok"]:
        print(
            " ".join(
                [
                    "bridge_smoke=error",
                    f"stage=start_download",
                    f"code={download_payload['error']['code']!r}",
                    f"message={download_payload['error']['message']!r}",
                ]
            )
        )
        return

    followup_payload = bridge.get_app_state({"since_event_id": state_payload["meta"]["event_cursor"]})
    deadline = time.monotonic() + 5
    while followup_payload["meta"]["download_active"] and time.monotonic() < deadline:
        time.sleep(0.05)
        followup_payload = bridge.get_app_state(
            {"since_event_id": followup_payload["meta"]["event_cursor"]}
        )

    inspection_payload = bridge.inspect_output()
    final_selected_item = (followup_payload["data"].get("state") or {}).get("selected_item") or {}

    for payload in (
        runtime_payload,
        state_payload,
        intake_payload,
        select_item_payload,
        audio_payload,
        quality_payload,
        download_payload,
        inspection_payload,
        followup_payload,
    ):
        json.dumps(payload, ensure_ascii=False)

    print(
        " ".join(
            [
                "bridge_smoke=ok",
                f"shell_module_loaded={'app.shell' in sys.modules}",
                f"tkinter_preloaded={'tkinter' in sys.modules}",
                f"queue_items={len(queue)}",
                f"selected_item_id={selected_item_id!r}",
                f"audio_quality_options={len(audio_options)}",
                f"download_status={final_selected_item.get('status', '')!r}",
                f"download_step={final_selected_item.get('processing_step', '')!r}",
                f"inspection_available={inspection_payload['data']['inspection'] is not None}",
                f"new_events={len(followup_payload['data']['events'])}",
            ]
        )
    )


def run_smoke_bridge_concurrency() -> int:
    base_config = create_default_config()
    proof_root = base_config.runtime_dir / "ui-proof" / "TZ-PIPE-CONCURRENCY-01"
    shutil.rmtree(proof_root, ignore_errors=True)
    output_dir = proof_root / "output"
    temp_dir = proof_root / "temp"
    state_file = proof_root / "queue_state.concurrency.smoke.json"
    proof_root.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    config = AppConfig(
        project_root=base_config.project_root,
        runtime_dir=proof_root,
        output_dir=output_dir,
        temp_dir=temp_dir,
        state_file=state_file,
        bundled_tools_dir=base_config.bundled_tools_dir,
    )
    controller = AppController(
        config,
        downloader=_BridgeConcurrencySmokeDownloader(output_dir),
    )

    sample_probe = ProbeResult(
        source_url="https://www.youtube.com/watch?v=BaW_jenozKc",
        title="Concurrent smoke title",
        channel="yt-dlp test suite",
        thumbnail="https://i.ytimg.com/vi/BaW_jenozKc/hqdefault.jpg",
        duration=10,
        video_formats=[
            FormatOption(
                format_id="137",
                quality_label="1080p | mp4 | video-only | fmt 137",
                ext="mp4",
                note="video-only",
            )
        ],
        audio_formats=[
            FormatOption(
                format_id="140",
                quality_label="128 kbps | m4a | audio-only | fmt 140",
                ext="m4a",
                note="audio-only",
            )
        ],
    )
    items = [
        QueueItem(
            source_url=f"{sample_probe.source_url}&concurrency={index}",
            title=sample_probe.title,
            mode=DownloadMode.VIDEO,
            quality=sample_probe.video_formats[0].quality_label,
            probe=sample_probe,
            selected_format_id="137",
        )
        for index in range(2)
    ]
    controller.save_queue_state(items, selected_item_id=items[0].id)
    bridge = AppBridgeApi(controller)

    initial_state = bridge.get_app_state()
    runtime_before = bridge.get_runtime_info()
    start_payload = bridge.start_all_downloads()

    overlap_payload: dict[str, object] | None = None
    overlap_runtime: dict[str, object] | None = None
    latest_payload = start_payload
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        time.sleep(0.05)
        latest_payload = bridge.get_app_state({"since_event_id": latest_payload["meta"]["event_cursor"]})
        current_state = latest_payload["data"].get("state") or {}
        running_items = [
            item for item in current_state.get("queue", []) if item.get("status") == JobStatus.RUNNING.value
        ]
        if (
            len(running_items) >= 2
            and latest_payload["meta"].get("active_download_count", 0) >= 2
        ):
            overlap_payload = latest_payload
            overlap_runtime = bridge.get_runtime_info()
            break

    final_payload = latest_payload
    while final_payload["meta"].get("download_active") and time.monotonic() < deadline:
        time.sleep(0.05)
        final_payload = bridge.get_app_state({"since_event_id": final_payload["meta"]["event_cursor"]})

    final_state = final_payload["data"].get("state") or controller.get_state().to_dict()
    output_paths = [str(item.get("output_path", "")) for item in final_state.get("queue", [])]
    artifact_path = proof_root / "bridge-concurrency-proof.json"
    artifact_payload = {
        "task_id": "TZ-PIPE-CONCURRENCY-01",
        "runtime_before": runtime_before,
        "initial_state": initial_state,
        "start_all_payload": start_payload,
        "overlap_payload": overlap_payload,
        "overlap_runtime": overlap_runtime,
        "final_payload": final_payload,
        "output_paths": output_paths,
        "state_file": str(state_file),
    }
    artifact_path.write_text(
        json.dumps(artifact_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    overlap_running = 0
    if overlap_payload is not None:
        overlap_running = sum(
            1
            for item in (overlap_payload["data"].get("state") or {}).get("queue", [])
            if item.get("status") == JobStatus.RUNNING.value
        )

    if overlap_running < 2:
        print(
            " ".join(
                [
                    "bridge_concurrency_smoke=error",
                    f"artifact={str(artifact_path)!r}",
                    f"overlap_running={overlap_running}",
                    f"active_download_count={latest_payload['meta'].get('active_download_count', 0)}",
                ]
            )
        )
        return 1

    unique_output_paths = {path for path in output_paths if path}
    print(
        " ".join(
            [
                "bridge_concurrency_smoke=ok",
                f"artifact={str(artifact_path)!r}",
                f"started={len(start_payload['data']['started_item_ids'])}",
                f"overlap_running={overlap_running}",
                f"active_download_count={overlap_runtime['data']['bridge']['active_download_count'] if overlap_runtime else 0}",
                f"unique_outputs={len(unique_output_paths)}",
            ]
        )
    )
    return 0


def _build_smoke_download_item(
    *,
    probe: ProbeResult,
    mode: DownloadMode,
    format_id: str | None,
) -> QueueItem:
    if mode == DownloadMode.AUDIO:
        selected_option = _find_option(probe.audio_formats, format_id) if format_id else None
        if selected_option is None:
            if not probe.audio_formats:
                raise ValueError("No saved audio formats are available for smoke download.")
            selected_option = probe.audio_formats[0]
        selected_format_id = format_id or selected_option.format_id
        quality = selected_option.quality_label
    else:
        selected_option = _find_video_option(probe, format_id)
        selected_format_id = format_id or selected_option.format_id
        quality = selected_option.quality_label

    return QueueItem(
        source_url=probe.source_url,
        title=probe.title,
        mode=mode,
        quality=quality,
        probe=probe,
        selected_format_id=selected_format_id,
    )


def _find_video_option(probe: ProbeResult, format_id: str | None) -> FormatOption:
    if not format_id:
        if not probe.video_formats:
            raise ValueError("No saved video formats are available for smoke download.")
        return probe.video_formats[0]

    main_format_id = next(
        (
            part.strip()
            for part in format_id.split("+")
            if _find_option(probe.video_formats, part.strip()) is not None
        ),
        "",
    )
    selected_option = _find_option(probe.video_formats, main_format_id)
    if selected_option is None:
        raise ValueError(f"Requested video format_id {format_id!r} is not present in the saved probe state.")
    return selected_option


def _find_option(options: list[FormatOption], format_id: str | None) -> FormatOption | None:
    if not format_id:
        return None
    for option in options:
        if option.format_id == format_id:
            return option
    return None


def run_bridge_shell(*, start_url: str | None, debug: bool) -> None:
    controller = AppController(create_default_config())
    bridge = AppBridgeApi(controller)
    PywebviewHost(bridge).run(start_url=start_url, debug=debug)


def run_smoke_bridge_host(*, start_url: str | None = None) -> None:
    controller = AppController(create_default_config())
    bridge = AppBridgeApi(controller)
    host = PywebviewHost(bridge)
    launch_target = host.resolve_launch_target(start_url=start_url)
    environment = host.run(
        start_url=start_url,
        debug=False,
        auto_close_after=1.0,
    )
    print(
        " ".join(
            [
                "bridge_host_smoke=ok",
                f"pywebview_version={environment.pywebview_version!r}",
                f"module_path={environment.module_path!r}",
                f"entrypoint={launch_target.kind!r}",
                f"entrypoint_value={launch_target.value!r}",
                "startup_path=entered",
                "auto_closed=True",
            ]
        )
    )


def _bridge_host_blocked(error: BridgeHostError) -> int:
    print(f"bridge_host=blocked message={error}", file=sys.stderr)
    return error.exit_code


def main() -> int:
    args = build_parser().parse_args()

    if args.smoke_state:
        run_smoke_state()
        return 0

    if args.smoke_start:
        run_smoke_start()
        return 0

    if args.smoke_probe:
        run_smoke_probe(args.smoke_probe)
        return 0

    if args.smoke_intake:
        run_smoke_intake(args.smoke_intake)
        return 0

    if args.smoke_download:
        run_smoke_download(
            url=args.smoke_download,
            mode=DownloadMode(args.smoke_download_mode),
            format_id=args.smoke_download_format_id,
        )
        return 0

    if args.smoke_bridge:
        run_smoke_bridge(args.smoke_bridge)
        return 0

    if args.smoke_bridge_concurrency:
        return run_smoke_bridge_concurrency()

    if args.smoke_bridge_host:
        try:
            run_smoke_bridge_host(start_url=args.bridge_start_url)
        except BridgeHostError as error:
            return _bridge_host_blocked(error)
        return 0

    if args.ui_shell == "bridge":
        try:
            run_bridge_shell(start_url=args.bridge_start_url, debug=args.bridge_debug)
        except BridgeHostError as error:
            return _bridge_host_blocked(error)
        return 0

    from app.shell import AppShell

    controller = AppController(create_default_config())
    AppShell(controller).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
