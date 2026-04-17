from __future__ import annotations

import argparse

from app import AppConfig, AppShell, QueueItem, QueueStateStore, create_default_config
from app.core import YoutubeProbeError, YoutubeProbeService
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

    config = create_default_config()
    AppShell(config).run()


if __name__ == "__main__":
    main()
