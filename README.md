# YT Downloader

## Tech runbook

UI/runtime stack v1:
- Python 3.12
- Tkinter as a temporary diagnostic shell over a UI-agnostic Python controller layer
- `pywebview` in the Poetry environment for the future `React + pywebview` desktop shell
- a JSON-safe Python bridge for the future `React + pywebview` desktop shell
- `yt-dlp` for YouTube metadata and formats probing
- stdlib (`dataclasses`, `enum`, `json`, `pathlib`) for config and queue state

## Poetry bootstrap

1. Ensure Python 3.12.x and Poetry are installed.
2. Install the locked environment:

```powershell
poetry install
```

Poetry is the source of truth for Python dependencies in this repository. `pyproject.toml` declares them and `poetry.lock` pins the resolved set.
`poetry install` now also brings in `pywebview` for the bridge-host bootstrap.

## Local start

Run the desktop shell:

```powershell
poetry run python main.py
```

Run the bridge-shell bootstrap instead of Tkinter:

```powershell
poetry run python main.py --ui-shell bridge
```

To point the host at a future React dev server:

```powershell
poetry run python main.py --ui-shell bridge --bridge-start-url http://localhost:5173
```

If the local `pywebview` backend cannot start, the command exits cleanly with `bridge_host=blocked ...` on stderr and exit code `2` instead of printing a traceback.

After you paste a YouTube URL into the shell and add it to the queue, the app probes metadata and stores the selected quality label plus `selected_format_id` in queue state. `Download Selected` then runs a real pipeline:
- `yt-dlp` downloads the saved selection into `temp/<queue-item-id>/`
- `ffmpeg` merges or converts the media into a deterministic final file in `output/`
- final output contract is `video -> .mp4`, `audio -> .m4a`

The orchestration and state mutations now live in `app/controller/`. `app/shell.py` only binds controller state to Tkinter widgets, and `app/bridge/` exposes the same controller via JSON-safe payloads for `pywebview` JS calls, so the backend stays reusable across both shells.

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

Headless bridge contract smoke:

```powershell
poetry run python main.py --smoke-bridge https://www.youtube.com/watch?v=Lm7-yFZ5fZQ
```

This smoke proves the bridge can:
- build JSON-safe payloads without Python dataclass knowledge on the JS side
- call `get_runtime_info`, `get_app_state`, `add_url`, `select_item`, `select_mode`, `select_quality`, `start_download`, and `inspect_output`
- operate without importing `app.shell` on the backend path

Bridge host startup smoke:

```powershell
poetry run python main.py --smoke-bridge-host
```

This smoke starts the actual `pywebview` host bootstrap, waits for startup, and auto-closes the window after a short probe. It is the narrow readiness check for the desktop host path that `ТЗ-OBS-FE-REACT-03` will reuse.

Download smoke using a persisted queue item:

```powershell
poetry run python main.py --smoke-download https://www.youtube.com/watch?v=Lm7-yFZ5fZQ --smoke-download-mode video
poetry run python main.py --smoke-download https://www.youtube.com/watch?v=Lm7-yFZ5fZQ --smoke-download-mode audio
poetry run python main.py --smoke-download https://www.youtube.com/watch?v=Lm7-yFZ5fZQ --smoke-download-mode video --smoke-download-format-id 299
```

The third example forces a saved video-only format so the pipeline has to download separate streams and merge them.

Compile sanity check:

```powershell
poetry run python -m py_compile app\__init__.py main.py app\shell.py app\bridge\__init__.py app\bridge\api.py app\bridge\host.py app\controller\__init__.py app\controller\app_controller.py app\controller\contracts.py app\core\__init__.py app\core\youtube_probe.py app\core\downloader.py app\core\postprocess.py
```

## Bridge contract notes

The `pywebview` bridge exposes these Python methods for JS:
- `get_app_state`
- `add_url`
- `select_item`
- `select_mode`
- `select_quality`
- `start_download`
- `get_runtime_info`
- `inspect_output`

`get_app_state` is the refresh primitive. The future web UI should poll it with `since_event_id` and consume the returned `events` array of full state snapshots. `start_download` is async in the bridge layer: it returns an immediate acceptance payload, then the controller emits progress/status updates into the retained event queue while the background worker is running.

The bridge shell bootstrap intentionally stays minimal. In the locked Poetry environment it should be runnable. If the local `pywebview` runtime or GUI backend is unavailable, `main.py --ui-shell bridge` fails fast with a short `bridge_host=blocked` message instead of silently falling back to Tkinter or surfacing a traceback.

## ffmpeg / ffprobe resolution order

The application resolves binaries in this order:
1. `FFMPEG_PATH` / `FFPROBE_PATH`
2. Bundled files under `app/bin/`, `tools/`, or `vendor/`
3. `PATH`

If `ffmpeg` is missing, the download pipeline stops before downloading media and writes a user-facing blocker into `QueueItem.error_message` instead of surfacing a stack trace. `ffprobe` is reused for smoke inspection when available.
