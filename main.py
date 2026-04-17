from __future__ import annotations

import argparse
import re
from pathlib import Path

from app import AppConfig, AppShell, QueueItem, QueueStateStore, create_default_config
from app.core import (
    DownloadPipelineError,
    MediaPostprocessError,
    QueueItemDownloader,
    YoutubeProbeError,
    YoutubeProbeService,
)
from app.models import DownloadMode, FormatOption, ProbeResult, QualityOption


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="YT Downloader app shell")
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
    config = create_default_config()
    config.ensure_directories()
    smoke_state_file = config.runtime_dir / "queue_state.smoke.json"
    store = QueueStateStore(smoke_state_file)
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

    sample_item = QueueItem(
        source_url=sample_probe.source_url,
        mode=DownloadMode.VIDEO,
        quality=QualityOption.BEST,
        title=sample_probe.title,
        probe=sample_probe,
        selected_format_id="137",
    )
    store.save([sample_item])
    loaded = store.load()
    print(
        " ".join(
            [
                f"queue_items={len(loaded)}",
                f"state_file={smoke_state_file}",
                f"probe_title={loaded[0].probe.title if loaded and loaded[0].probe else 'missing'}",
                f"video_options={len(loaded[0].probe.video_formats) if loaded and loaded[0].probe else 0}",
                f"audio_options={len(loaded[0].probe.audio_formats) if loaded and loaded[0].probe else 0}",
            ]
        )
    )


def run_smoke_start() -> None:
    config = create_default_config()
    app = AppShell(config)
    app.root.update_idletasks()
    app.root.update()
    app.close()
    print("ui_smoke=ok")


def run_smoke_probe(urls: list[str]) -> None:
    service = YoutubeProbeService()
    for url in urls:
        try:
            probe = service.probe(url)
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
    app = AppShell(config)
    try:
        result = app.smoke_add_url(url)
        print(
            " ".join(
                [
                    "intake=ok",
                    f"title={result['title']!r}",
                    f"selected_quality={result['selected_quality']!r}",
                    f"selected_format_id={result['selected_format_id']!r}",
                    f"quality_values={result['quality_values']!r}",
                    f"video_options={result['video_options']}",
                    f"audio_options={result['audio_options']}",
                ]
            )
        )
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
    finally:
        app.close()


def run_smoke_download(url: str, mode: DownloadMode, format_id: str | None) -> None:
    smoke_suffix = re.sub(r"[^A-Za-z0-9_-]+", "_", format_id or "default").strip("_") or "default"
    config = create_smoke_config(f"queue_state.download.{mode.value}.{smoke_suffix}.smoke.json")
    config.ensure_directories()
    if config.state_file.exists():
        config.state_file.unlink()

    service = YoutubeProbeService()
    store = QueueStateStore(config.state_file)
    try:
        probe = service.probe(url)
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
    store.save([item])
    loaded = store.load()
    if not loaded:
        print("download=error reason='failed to reload persisted queue item'")
        return

    loaded_item = loaded[0]
    downloader = QueueItemDownloader(config)

    try:
        output_path = downloader.execute(loaded_item)
    except DownloadPipelineError:
        store.save([loaded_item])
        print(
            " ".join(
                [
                    "download=error",
                    f"mode={mode.value}",
                    f"selected_format_id={loaded_item.selected_format_id!r}",
                    f"status={loaded_item.status.value}",
                    f"step={loaded_item.processing_step.value}",
                    f"detail={loaded_item.status_detail!r}",
                    f"output_path={loaded_item.output_path!r}",
                    f"error={loaded_item.error_message!r}",
                ]
            )
        )
        return

    store.save([loaded_item])
    try:
        inspection = downloader.inspect_output(Path(output_path))
    except MediaPostprocessError as error:
        inspection = None
        format_name = f"ffprobe-error:{error}"
        stream_types = []
    else:
        format_name = inspection["format_name"] if inspection else "unavailable"
        stream_types = inspection["stream_types"] if inspection else []
    print(
        " ".join(
            [
                "download=ok",
                f"mode={mode.value}",
                f"selected_format_id={loaded_item.selected_format_id!r}",
                f"status={loaded_item.status.value}",
                f"step={loaded_item.processing_step.value}",
                f"detail={loaded_item.status_detail!r}",
                f"output_path={loaded_item.output_path!r}",
                f"suffix={Path(output_path).suffix!r}",
                f"size={Path(output_path).stat().st_size}",
                f"format_name={format_name!r}",
                f"stream_types={stream_types!r}",
                f"error={loaded_item.error_message!r}",
            ]
        )
    )


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


def main() -> None:
    args = build_parser().parse_args()

    if args.smoke_state:
        run_smoke_state()
        return

    if args.smoke_start:
        run_smoke_start()
        return

    if args.smoke_probe:
        run_smoke_probe(args.smoke_probe)
        return

    if args.smoke_intake:
        run_smoke_intake(args.smoke_intake)
        return

    if args.smoke_download:
        run_smoke_download(
            url=args.smoke_download,
            mode=DownloadMode(args.smoke_download_mode),
            format_id=args.smoke_download_format_id,
        )
        return

    config = create_default_config()
    AppShell(config).run()


if __name__ == "__main__":
    main()
