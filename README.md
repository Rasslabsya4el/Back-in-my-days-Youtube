# YT Downloader

## Tech runbook

UI/runtime stack v1:
- Python 3.12
- Tkinter for desktop shell
- stdlib (`dataclasses`, `enum`, `json`, `pathlib`) for config and queue state

## Local start

1. Ensure Python 3.12+ is installed.
2. Install runtime requirements:

```powershell
python -m pip install -r requirements.txt
```

3. Run the desktop shell:

```powershell
python main.py
```

Application start creates:
- `runtime/queue_state.json` on first real queue save
- `output/`
- `temp/`
- `app/bin/` as the bundled tools lookup root

## Smoke checks

UI startup smoke:

```powershell
python main.py --smoke-start
```

Queue state save/load smoke:

```powershell
python main.py --smoke-state
```

The smoke writes to `runtime/queue_state.smoke.json`.

## ffmpeg / ffprobe resolution order

The application resolves binaries in this order:
1. `FFMPEG_PATH` / `FFPROBE_PATH`
2. Bundled files under `app/bin/`, `tools/`, or `vendor/`
3. `PATH`
