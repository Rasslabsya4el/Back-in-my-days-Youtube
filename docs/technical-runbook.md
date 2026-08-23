# Technical runbook

This file is for building, packaging, and validating the app.
The user-facing overview stays in [README.md](../README.md).

## Stack

- Python 3.12
- Poetry for Python dependencies
- React + TypeScript + Vite for the main desktop UI
- `pywebview` for the desktop host
- Tkinter as a fallback diagnostic shell
- `yt-dlp` for probing and downloading media
- `yt-dlp-ejs` plus a bundled Node.js runtime for current YouTube JavaScript challenges
- `ffmpeg` / `ffprobe` for post-processing and inspection

## Bootstrap

Install Python dependencies:

```powershell
poetry install
```

Install the frontend dependencies from the repository root:

```powershell
npm install
```

Build the frontend shell into `frontend/dist`:

```powershell
npm run build
```

## Supported Windows release path

The supported public Windows release is the installer.

Build it with:

```powershell
poetry install --with packaging
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows_installer.ps1
```

The build expects `BACK_IN_MY_DAYS_YOUTUBE_PORTABLE_MEDIA_TOOLS_DIR` to point at an FFmpeg bundle root that contains both `ffmpeg.exe` and `ffprobe.exe`.
Supported layouts under that root are:

- `<root>\<tool>.exe`
- `<root>\bin\<tool>.exe`
- `<root>\ffmpeg\<tool>.exe`
- `<root>\ffmpeg\bin\<tool>.exe`
- `<root>\win-x64\<tool>.exe`

Example:

```powershell
$env:BACK_IN_MY_DAYS_YOUTUBE_PORTABLE_MEDIA_TOOLS_DIR = 'C:\tools\ffmpeg-8.1-essentials_build'
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows_installer.ps1
```

The final installer is:

```text
dist\Back in my days Youtube Setup.exe
```

The installer payload bundles:

- `frontend/dist`
- app icons and assets
- bundled `ffmpeg` and `ffprobe`
- a fixed `WebView2 Runtime`
- Node.js runtime for yt-dlp YouTube extraction

The build machine must have Node.js 22 or newer available as `node.exe`. The release
copies only `node.exe` into the installer payload; end users do not need to install
Node.js separately.

## Portable scripts

Portable build scripts still exist in the repo for internal packaging work, but portable is not the supported public release format right now.
Do not point end users at the portable flow unless that decision changes.

## Local start

Start the desktop shell:

```powershell
poetry run python main.py
```

Start the bridge shell explicitly:

```powershell
poetry run python main.py --ui-shell bridge
```

Point the bridge shell at a Vite dev server instead of built assets:

```powershell
poetry run python main.py --ui-shell bridge --bridge-start-url http://localhost:5173
```

Start the Tk diagnostic shell:

```powershell
poetry run python main.py --ui-shell tk
```

Bridge launch target order:

1. `--bridge-start-url`, if provided
2. `frontend/dist/index.html`, if the build exists
3. a small inline fallback page with build instructions

If `pywebview` cannot start, the command exits with `bridge_host=blocked ...` and exit code `2` instead of dumping a traceback into the UI path.

## UI behavior

The main screen is built around one simple loop:

1. paste a YouTube URL
2. add it to the queue
3. choose the output folder for the current session
4. select the queue item you want to work on
5. choose `Audio` or `Video`
6. choose quality
7. start one item or the whole queue

The queue can run items concurrently.
If two items would produce the same output name, the app reserves output paths before each run so they do not overwrite each other.

Final file contract:

- video -> `.mp4`
- audio -> `.m4a`

Audio output keeps `title` and `artist` metadata.
The app also tries to embed the YouTube thumbnail as cover art when that data is available.

## Runtime layout

Installer builds write user data under `%LOCALAPPDATA%\Back in my days Youtube`.

Important paths:

- output: `%LOCALAPPDATA%\Back in my days Youtube\output`
- runtime state: `%LOCALAPPDATA%\Back in my days Youtube\runtime`
- temp work: `%LOCALAPPDATA%\Back in my days Youtube\temp`
- startup/install log: `C:\ProgramData\Back in my days Youtube\logs\debug.log`

The installed app folder also contains `debug-log-path.txt`, which points at the active log file on that machine.

## Smoke checks

Startup smoke:

```powershell
poetry run python main.py --smoke-start
```

Queue persistence smoke:

```powershell
poetry run python main.py --smoke-state
```

Probe smoke:

```powershell
poetry run python main.py --smoke-probe https://www.youtube.com/watch?v=Lm7-yFZ5fZQ
```

Bridge smoke:

```powershell
poetry run python main.py --smoke-bridge https://www.youtube.com/watch?v=Lm7-yFZ5fZQ
```

Bridge host startup smoke:

```powershell
poetry run python main.py --smoke-bridge-host
```

Download smoke:

```powershell
poetry run python main.py --smoke-download https://www.youtube.com/watch?v=Lm7-yFZ5fZQ --smoke-download-mode audio
```

Compile sanity:

```powershell
poetry run python -m py_compile app\__init__.py main.py app\shell.py app\bridge\__init__.py app\bridge\api.py app\bridge\host.py app\controller\__init__.py app\controller\app_controller.py app\controller\contracts.py app\core\__init__.py app\core\audio_metadata.py app\core\youtube_probe.py app\core\downloader.py app\core\postprocess.py
```

## Bridge notes

The JS side calls these Python bridge methods:

- `get_app_state`
- `add_url`
- `select_item`
- `select_mode`
- `select_quality`
- `pick_output_dir`
- `open_output_dir`
- `clear_queue`
- `start_download`
- `start_all_downloads`
- `get_runtime_info`
- `inspect_output`

`frontend/src/bridge.ts` wraps them in a typed client.
`get_app_state` is the refresh primitive. The UI polls it with `since_event_id`, so unchanged state does not trigger a full rerender payload every time.

## ffmpeg / ffprobe resolution

Binary lookup order:

1. `FFMPEG_PATH` / `FFPROBE_PATH`
2. bundled files under `app/bin/`, then `tools/`, then `vendor/`
3. `PATH`

Within each bundled root the resolver probes:

- `<root>/<tool>`
- `<root>/bin/<tool>`
- `<root>/ffmpeg/<tool>`
- `<root>/ffmpeg/bin/<tool>`
- `<root>/win-x64/<tool>`

Installer packaging is supposed to end with bundled tools, not `PATH` fallbacks.
If `ffmpeg` is missing, the app stops before the media run and surfaces a short user-facing error instead of a traceback.

## YouTube download recovery

The app refreshes YouTube extraction for every format attempt and retries the saved
format before falling back through the other compatible audio/video formats from the
probe result. This matters because YouTube media URLs can be rejected after probing
with HTTP 403. A retry no longer repeats only the same stale request.
