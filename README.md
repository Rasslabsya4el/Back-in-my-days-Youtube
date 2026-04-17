# YT Downloader

## Tech runbook

UI/runtime stack v1:
- Python 3.12
- Tkinter for desktop shell
- `yt-dlp` for YouTube metadata and formats probing
- stdlib (`dataclasses`, `enum`, `json`, `pathlib`) for config and queue state

## Poetry bootstrap

1. Ensure Python 3.12.x and Poetry are installed.
2. Install the locked environment:

```powershell
poetry install
```

Poetry is the source of truth for Python dependencies in this repository. `pyproject.toml` declares them and `poetry.lock` pins the resolved set.

## Local start

Run the desktop shell:

```powershell
poetry run python main.py
```

After you paste a YouTube URL into the shell and add it to the queue, the app probes metadata and stores the selected quality label plus `selected_format_id` in queue state. `Download Selected` then runs a real pipeline:
- `yt-dlp` downloads the saved selection into `temp/<queue-item-id>/`
- `ffmpeg` merges or converts the media into a deterministic final file in `output/`
- final output contract is `video -> .mp4`, `audio -> .m4a`

For video items, saved muxed formats are remuxed/transcoded into `mp4`. Saved video-only formats automatically pull the best saved companion audio format from the persisted probe state and merge both streams.

For audio-only items, the pipeline creates final `.m4a` output without embedding metadata or artwork.

Application start creates:
- `runtime/queue_state.json` on first real queue save
- `output/`
- `temp/`
- `app/bin/` as the bundled tools lookup root

## Smoke checks

UI startup smoke:

```powershell
poetry run python main.py --smoke-start
```

Queue state save/load smoke:

```powershell
poetry run python main.py --smoke-state
```

Probe smoke without download:

```powershell
poetry run python main.py --smoke-probe https://www.youtube.com/watch?v=Lm7-yFZ5fZQ
poetry run python main.py --smoke-probe https://example.com/watch?v=123
poetry run python main.py --smoke-probe https://www.youtube.com/watch?v=aaaaaaaaaaa
```

UI intake smoke with immediate quality dropdown population:

```powershell
poetry run python main.py --smoke-intake https://www.youtube.com/watch?v=Lm7-yFZ5fZQ
```

The state smokes write to `runtime/queue_state.smoke.json` and `runtime/queue_state.intake.smoke.json`.

Download smoke using a persisted queue item:

```powershell
poetry run python main.py --smoke-download https://www.youtube.com/watch?v=Lm7-yFZ5fZQ --smoke-download-mode video
poetry run python main.py --smoke-download https://www.youtube.com/watch?v=Lm7-yFZ5fZQ --smoke-download-mode audio
poetry run python main.py --smoke-download https://www.youtube.com/watch?v=Lm7-yFZ5fZQ --smoke-download-mode video --smoke-download-format-id 299
```

The third example forces a saved video-only format so the pipeline has to download separate streams and merge them.

Compile sanity check:

```powershell
poetry run python -m py_compile main.py app\models.py app\shell.py app\core\__init__.py app\core\youtube_probe.py app\core\downloader.py app\core\postprocess.py
```

## ffmpeg / ffprobe resolution order

The application resolves binaries in this order:
1. `FFMPEG_PATH` / `FFPROBE_PATH`
2. Bundled files under `app/bin/`, `tools/`, or `vendor/`
3. `PATH`

If `ffmpeg` is missing, the download pipeline stops before downloading media and writes a user-facing blocker into `QueueItem.error_message` instead of surfacing a stack trace. `ffprobe` is reused for smoke inspection when available.
