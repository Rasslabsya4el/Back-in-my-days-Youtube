from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.parse
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.config import create_default_config
from app.controller import AppController
from app.models import DownloadMode, FormatOption, JobStatus, JobStep, ProbeResult, QueueItem


TASK_ID = "TZ-OBS-UI-HARNESS-01"
WINDOW_TITLE = "YT Downloader bridge shell"
DEFAULT_RUNS = 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Canonical live UI harness for the default bridge shell.")
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = REPO_ROOT
    config = create_default_config(repo_root)
    proof_root = config.runtime_dir / "ui-proof" / TASK_ID
    state_file = config.state_file

    shutil.rmtree(proof_root, ignore_errors=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    backup_bytes = state_file.read_bytes() if state_file.exists() else None
    had_state_file = state_file.exists()

    overall_summary: dict[str, Any] = {
        "task_id": TASK_ID,
        "canonical_command": "poetry run python scripts/validation/tz_obs_ui_harness.py",
        "default_launch_command": "poetry run python main.py --ui-shell bridge",
        "requested_runs": args.runs,
        "runs": [],
        "state_restore": {},
    }

    exit_code = 0
    try:
        for run_index in range(1, args.runs + 1):
            run_id = f"run-{run_index:02d}"
            run_dir = proof_root / run_id
            run_dir.mkdir(parents=True, exist_ok=True)

            items = build_fixture_items()
            AppController(config).save_queue_state(items, selected_item_id=items[0].id)

            harness_config = {
                "task_id": TASK_ID,
                "run_id": run_id,
                "proof_dir": str(run_dir),
                "default_launch_command": "poetry run python main.py --ui-shell bridge",
                "expected_queue_ready_count": sum(1 for item in items if item.status == JobStatus.QUEUED),
                "items": [
                    {
                        "id": item.id,
                        "key": item.title.rsplit(" ", 1)[-1],
                        "title": item.title,
                    }
                    for item in items
                ],
            }
            config_path = run_dir / "harness-config.json"
            config_path.write_text(
                json.dumps(harness_config, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            run_result = _run_single_session(
                repo_root=repo_root,
                config_path=config_path,
                run_dir=run_dir,
                timeout_seconds=args.timeout_seconds,
            )
            overall_summary["runs"].append(run_result)
            if run_result["exit_code"] != 0:
                exit_code = 1
    finally:
        restore_runtime_state(state_file=state_file, previous_bytes=backup_bytes, had_state_file=had_state_file)
        restored_bytes = state_file.read_bytes() if state_file.exists() else None
        overall_summary["state_restore"] = {
            "state_file": str(state_file),
            "restored": restored_bytes == backup_bytes if had_state_file else not state_file.exists(),
            "had_original_state_file": had_state_file,
        }
        overall_summary["repeatability"] = build_repeatability_summary(overall_summary["runs"])
        overall_summary["overall_pass"] = all(run["exit_code"] == 0 for run in overall_summary["runs"])
        overall_summary["completed_at"] = datetime.now(UTC).isoformat()
        summary_path = proof_root / "summary.json"
        summary_path.write_text(
            json.dumps(overall_summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    return exit_code


def _run_single_session(
    *,
    repo_root: Path,
    config_path: Path,
    run_dir: Path,
    timeout_seconds: float,
) -> dict[str, Any]:
    env = os.environ.copy()
    env["YT_UI_HARNESS_CONFIG"] = str(config_path)
    stdout_path = run_dir / "main.stdout.log"
    stderr_path = run_dir / "main.stderr.log"
    command = ["poetry", "run", "python", "main.py", "--ui-shell", "bridge"]
    started_at = datetime.now(UTC).isoformat()

    with stdout_path.open("w", encoding="utf-8") as stdout_file, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr_file:
        process = subprocess.Popen(
            command,
            cwd=repo_root,
            env=env,
            stdout=stdout_file,
            stderr=stderr_file,
        )
        timed_out = False
        try:
            exit_code = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            exit_code = 124
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(process.pid)],
                capture_output=True,
                encoding="utf-8",
                check=False,
            )
            process.wait(timeout=10)

    _run_system_helper("wait-pid-exit", str(process.pid), "--timeout", "20")
    _run_system_helper("wait-window-closed", WINDOW_TITLE, "--timeout", "20")

    child_summary_path = run_dir / "summary.json"
    child_summary = (
        json.loads(child_summary_path.read_text(encoding="utf-8"))
        if child_summary_path.exists()
        else None
    )

    return {
        "run_id": run_dir.name,
        "command": " ".join(command),
        "started_at": started_at,
        "completed_at": datetime.now(UTC).isoformat(),
        "timeout_seconds": timeout_seconds,
        "timed_out": timed_out,
        "exit_code": exit_code,
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "child_summary_path": str(child_summary_path),
        "failed_assertions": child_summary.get("failed_assertions", []) if child_summary else [],
        "overall_pass": child_summary.get("overall_pass", False) if child_summary else False,
    }


def build_repeatability_summary(runs: list[dict[str, Any]]) -> dict[str, Any]:
    failure_sets = {tuple(run.get("failed_assertions", [])) for run in runs}
    exit_codes = {run.get("exit_code") for run in runs}
    return {
        "runs_completed": len(runs),
        "same_failure_set_across_runs": len(failure_sets) == 1,
        "same_exit_code_across_runs": len(exit_codes) == 1,
    }


def restore_runtime_state(*, state_file: Path, previous_bytes: bytes | None, had_state_file: bool) -> None:
    if had_state_file and previous_bytes is not None:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_bytes(previous_bytes)
        return
    if state_file.exists():
        state_file.unlink()


def build_fixture_items() -> list[QueueItem]:
    shared_video_formats = [
        FormatOption(
            format_id="137",
            quality_label="1080p | mp4 | video-only | fmt 137",
            ext="mp4",
            note="video-only",
        )
    ]
    shared_audio_formats = [
        FormatOption(
            format_id="140",
            quality_label="128 kbps | m4a | audio-only | fmt 140",
            ext="m4a",
            note="audio-only",
        )
    ]

    probes = [
        ProbeResult(
            source_url="https://example.invalid/harness/a",
            title="Harness item A",
            channel="Harness channel A",
            thumbnail=svg_data_url("A", "#c04d2d"),
            duration=61,
            video_formats=shared_video_formats,
            audio_formats=shared_audio_formats,
        ),
        ProbeResult(
            source_url="https://example.invalid/harness/b",
            title="Harness item B",
            channel="Harness channel B",
            thumbnail=svg_data_url("B", "#1f6f8b"),
            duration=62,
            video_formats=shared_video_formats,
            audio_formats=shared_audio_formats,
        ),
        ProbeResult(
            source_url="https://example.invalid/harness/c",
            title="Harness item C",
            channel="Harness channel C",
            thumbnail=svg_data_url("C", "#577590"),
            duration=63,
            video_formats=shared_video_formats,
            audio_formats=shared_audio_formats,
        ),
    ]

    return [
        QueueItem(
            id="tz-obs-ui-harness-a",
            source_url=probes[0].source_url,
            title=probes[0].title,
            mode=DownloadMode.VIDEO,
            quality=shared_video_formats[0].quality_label,
            probe=probes[0],
            selected_format_id="137",
            status=JobStatus.QUEUED,
            processing_step=JobStep.QUEUED,
            status_detail="",
        ),
        QueueItem(
            id="tz-obs-ui-harness-b",
            source_url=probes[1].source_url,
            title=probes[1].title,
            mode=DownloadMode.VIDEO,
            quality=shared_video_formats[0].quality_label,
            probe=probes[1],
            selected_format_id="137",
            status=JobStatus.COMPLETED,
            processing_step=JobStep.COMPLETED,
            status_detail="",
            output_path=r"C:\Harness\proof\item-b.mp4",
        ),
        QueueItem(
            id="tz-obs-ui-harness-c",
            source_url=probes[2].source_url,
            title=probes[2].title,
            mode=DownloadMode.VIDEO,
            quality=shared_video_formats[0].quality_label,
            probe=probes[2],
            selected_format_id="137",
            status=JobStatus.QUEUED,
            processing_step=JobStep.QUEUED,
            status_detail=r"Saved as C:\Harness\proof\item-c.mp4",
        ),
    ]


def svg_data_url(label: str, background: str) -> str:
    svg = f"""
    <svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360">
      <rect width="640" height="360" fill="{background}" rx="32" />
      <text
        x="50%"
        y="50%"
        dominant-baseline="middle"
        text-anchor="middle"
        font-family="Segoe UI"
        font-size="112"
        fill="#ffffff"
      >
        {label}
      </text>
    </svg>
    """.strip()
    return "data:image/svg+xml;charset=utf-8," + urllib.parse.quote(svg, safe="")


def _run_system_helper(*args: str) -> subprocess.CompletedProcess[str]:
    helper_path = Path(__file__).resolve().with_name("system_helpers.py")
    launchers = (("py", "-3"), ("python",))
    last_error: Exception | None = None
    for launcher in launchers:
        command = [*launcher, str(helper_path), *args]
        try:
            return subprocess.run(
                command,
                capture_output=True,
                check=True,
                encoding="utf-8",
                timeout=30,
            )
        except Exception as error:
            last_error = error
    raise RuntimeError(f"System helper failed for args={args!r}: {last_error}")


if __name__ == "__main__":
    raise SystemExit(main())
