from __future__ import annotations

import argparse

from app import AppShell, QueueItem, QueueStateStore, create_default_config
from app.models import DownloadMode, QualityOption


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
    return parser


def run_smoke_state() -> None:
    config = create_default_config()
    config.ensure_directories()
    smoke_state_file = config.runtime_dir / "queue_state.smoke.json"
    store = QueueStateStore(smoke_state_file)

    sample_item = QueueItem(
        source_url="https://example.com/watch?v=demo",
        mode=DownloadMode.VIDEO,
        quality=QualityOption.BEST,
        title="Smoke test item",
    )
    store.save([sample_item])
    loaded = store.load()
    print(f"queue_items={len(loaded)} state_file={smoke_state_file}")


def run_smoke_start() -> None:
    config = create_default_config()
    app = AppShell(config)
    app.root.update_idletasks()
    app.root.update()
    app.close()
    print("ui_smoke=ok")


def main() -> None:
    args = build_parser().parse_args()

    if args.smoke_state:
        run_smoke_state()
        return

    if args.smoke_start:
        run_smoke_start()
        return

    config = create_default_config()
    AppShell(config).run()


if __name__ == "__main__":
    main()
