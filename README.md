# YT Downloader

## Tech runbook

UI/runtime stack v1:
- Python 3.12
- React + TypeScript + Vite for the primary desktop-shell UI surface
- Tkinter as a fallback diagnostic shell over the same UI-agnostic Python controller layer
- `pywebview` in the Poetry environment for the desktop shell host
- a JSON-safe Python bridge consumed by both shells
- `yt-dlp` for YouTube metadata and formats probing
- stdlib (`dataclasses`, `enum`, `json`, `pathlib`) for config and queue state

## Poetry bootstrap

1. Ensure Python 3.12.x and Poetry are installed.
2. Install the locked environment:

```powershell
poetry install
```

Poetry is the source of truth for Python dependencies in this repository. `pyproject.toml` declares them and `poetry.lock` pins the resolved set.
`poetry install` also brings in `pywebview` for the bridge host.

## Frontend bootstrap

Install the frontend workspace once from the repository root:

```powershell
npm install
```

Run the Vite dev server:

```powershell
npm run dev
```

Build the React shell into `frontend/dist`:

```powershell
npm run build
```

## Local start

Run the desktop shell:

```powershell
poetry run python main.py
```

The bridge host resolves its launch target in this order:
1. `--bridge-start-url`, when provided for `--ui-shell bridge` or `--smoke-bridge-host`
2. `frontend/dist/index.html`, when the build exists
3. a lightweight inline HTML fallback with build instructions plus an optional debug details section

Run the bridge shell explicitly:

```powershell
poetry run python main.py --ui-shell bridge
```

Point the bridge shell at a Vite dev server instead of built assets:

```powershell
poetry run python main.py --ui-shell bridge --bridge-start-url http://localhost:5173
```

Run the Tk diagnostic shell explicitly:

```powershell
poetry run python main.py --ui-shell tk
```

If the local `pywebview` backend cannot start, the command exits cleanly with `bridge_host=blocked ...` on stderr and exit code `2` instead of printing a traceback.

After you paste a YouTube URL into the shell and add it to the queue, the bridge shell keeps the primary screen focused on the user flow:
- intake URL
- output folder picker for the current app session
- current item with `Quality` and `File format` selectors
- queue selection
- start one item or `Download all queued`
- status, error, and output path surface

Runtime and inspection diagnostics stay behind an explicit debug toggle that is closed by default.

`Start download` runs a real pipeline:
- `yt-dlp` downloads the saved selection into `temp/<queue-item-id>/`
- `ffmpeg` merges or converts the media into a deterministic final file in `output/`
- final output contract is `video -> .mp4`, `audio -> .m4a`

The queue runtime is concurrent: multiple queued items can be started together, the bridge keeps separate worker threads per queue item, and the shell can show multiple `running` items at the same time. Output-path reservation happens before each run so two concurrent items with the same title do not overwrite each other.

The orchestration and state mutations live in `app/controller/`. `app/shell.py` only binds controller state to Tkinter widgets, `frontend/` renders the first React shell iteration, and `app/bridge/` exposes the same controller via JSON-safe payloads for `pywebview` JS calls, so the backend stays reusable across both shells.

For video items, saved muxed formats are remuxed/transcoded into `mp4`. Saved video-only formats automatically pull the best saved companion audio format from the persisted probe state and merge both streams.

For audio-only items, the pipeline creates final `.m4a` output with embedded `title`/`artist` metadata and attempts to attach the YouTube thumbnail as cover art. Missing `channel` or thumbnail data does not fail the pipeline.

Application start creates:
- `runtime/queue_state.json` on first real queue save
- `output/`
- `temp/`
- `app/bin/` as the bundled tools lookup root

The persisted queue state stores both the `queue` payload and top-level `selected_item_id`. Each saved queue item keeps its own `mode`, `quality`, `selected_format_id`, and persisted probe snapshot so the same selection can be restored after restart. If the app restarts after an interrupted concurrent run, transient `running` items are normalized back to `queued` instead of staying stuck in an impossible active state.

## Smoke checks

Tk startup smoke:

```powershell
poetry run python main.py --smoke-start
```

Queue state save/load smoke:

```powershell
poetry run python main.py --smoke-state
```

This smoke now proves a full restart contract for a temporary state file: selected queue item, `mode`, `quality`, and `selected_format_id` are saved, reloaded, and kept aligned between the active selection snapshot and the persisted queue item.

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

Deterministic bridge concurrency smoke with proof artifact:

```powershell
poetry run python main.py --smoke-bridge-concurrency
```

This smoke starts two queued items through `start_all_downloads`, waits for a real overlap window with two `running` items at once, and writes the captured bridge/runtime snapshots to `runtime/ui-proof/TZ-PIPE-CONCURRENCY-01/bridge-concurrency-proof.json`.

Bridge host startup smoke:

```powershell
poetry run python main.py --smoke-bridge-host
```

This smoke starts the actual `pywebview` host bootstrap, waits for startup, and auto-closes the window after a short probe. It uses the same launch-target resolution as the normal bridge shell: `--bridge-start-url` first, then `frontend/dist/index.html`, then the lightweight fallback HTML.

Download smoke using a persisted queue item:

```powershell
poetry run python main.py --smoke-download https://www.youtube.com/watch?v=Lm7-yFZ5fZQ --smoke-download-mode video
poetry run python main.py --smoke-download https://www.youtube.com/watch?v=Lm7-yFZ5fZQ --smoke-download-mode audio
poetry run python main.py --smoke-download https://www.youtube.com/watch?v=Lm7-yFZ5fZQ --smoke-download-mode video --smoke-download-format-id 299
```

The third example forces a saved video-only format so the pipeline has to download separate streams and merge them.

Compile sanity check:

```powershell
poetry run python -m py_compile app\__init__.py main.py app\shell.py app\bridge\__init__.py app\bridge\api.py app\bridge\host.py app\controller\__init__.py app\controller\app_controller.py app\controller\contracts.py app\core\__init__.py app\core\audio_metadata.py app\core\youtube_probe.py app\core\downloader.py app\core\postprocess.py
```

## Bridge contract notes

The `pywebview` bridge exposes these Python methods for JS:
- `get_app_state`
- `add_url`
- `select_item`
- `select_mode`
- `select_quality`
- `pick_output_dir`
- `start_download`
- `start_all_downloads`
- `get_runtime_info`
- `inspect_output`

`frontend/src/bridge.ts` wraps these methods in a typed TS client. `get_app_state` is the refresh primitive: the React shell polls it with `since_event_id`. When the cursor has not advanced, the bridge returns `state_changed=false` with no full-state payload, so the shell can avoid redundant rerenders. The shell also pauses interval polling while the window is hidden and performs a one-shot refresh when focus returns.

The React shell keeps format internals inside the bridge/frontend layer. The user sees separate `Quality` and `File format` dropdowns, while the saved `selected_format_id` contract still drives the Python pipeline under the hood.

`start_download` and `start_all_downloads` are async in the bridge layer: they return immediate acceptance payloads, then the controller emits progress and status updates into the retained event queue while background workers are running. Bridge meta/runtime payloads expose aggregate activity through `download_active`, `active_download_count`, and `active_download_item_ids`.

The React shell intentionally stays coarse in its progress surface: it renders queue-item statuses and steps, not simulated byte progress that the backend does not expose yet.

The bridge shell bootstrap intentionally stays minimal. In the locked Poetry environment it should be runnable. If the local `pywebview` runtime or GUI backend is unavailable, `main.py --ui-shell bridge` fails fast with a short `bridge_host=blocked` message instead of silently falling back to Tkinter or surfacing a traceback.

## ffmpeg / ffprobe resolution order

The application resolves binaries in this order:
1. `FFMPEG_PATH` / `FFPROBE_PATH`
2. Bundled files under `app/bin/`, then `tools/`, then `vendor/`
3. `PATH`

Within each bundled root the resolver probes `<root>/<tool>`, `<root>/bin/<tool>`, `<root>/ffmpeg/<tool>`, `<root>/ffmpeg/bin/<tool>`, and `<root>/win-x64/<tool>` with the platform executable suffix when needed.

If `ffmpeg` is missing, the download pipeline stops before downloading media and writes a user-facing blocker into `QueueItem.error_message` instead of surfacing a stack trace. `ffprobe` is reused for smoke inspection when available.
