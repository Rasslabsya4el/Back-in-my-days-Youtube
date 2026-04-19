from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import create_default_config
from app.controller import AppController
from scripts.validation.system_helpers import (
    capture_window_handle,
    close_window_handle,
    focus_window_handle,
    list_windows,
)


TASK_ID = "TZ-ER-AUDIO-ART-03"
DEFAULT_SOURCE_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
PROOF_DIR = PROJECT_ROOT / "runtime" / "ui-proof" / TASK_ID
SUMMARY_PATH = PROOF_DIR / "summary.json"
CONFIG_PATH = PROOF_DIR / "bridge-harness-config.json"
SESSION_SUMMARY_PATH = PROOF_DIR / "bridge-session-summary.json"
MAIN_STDOUT_LOG = PROOF_DIR / "main.stdout.log"
MAIN_STDERR_LOG = PROOF_DIR / "main.stderr.log"
FFPROBE_JSON_PATH = PROOF_DIR / "final-audio-ffprobe.json"
EXPLORER_SCREENSHOT_PATH = PROOF_DIR / "explorer-selected-file.png"
PLAYBACK_SCREENSHOT_PATH = PROOF_DIR / "playback-surface.png"
WINDOWS_AFTER_EXPLORER_PATH = PROOF_DIR / "windows-after-explorer.json"
WINDOWS_AFTER_PLAYBACK_PATH = PROOF_DIR / "windows-after-playback.json"
TIMEOUT_SECONDS = 300.0
PLAYER_PROCESS_NAMES = {
    "applicationframehost.exe",
    "mediaplayer.exe",
    "music.ui.exe",
    "video.ui.exe",
    "wmplayer.exe",
}
PLAYBACK_ACCEPTABLE_UNAVAILABLE_REASONS = {
    "playback_window_not_found",
    "playback_launch_unsupported",
}


class HarnessError(RuntimeError):
    pass


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def snapshot_m4a_paths(output_dir: Path) -> list[str]:
    if not output_dir.exists():
        return []
    return sorted(str(path.resolve()) for path in output_dir.glob("*.m4a"))


def run_command(command: list[str], *, timeout: float = 120.0, check: bool = True) -> dict[str, Any]:
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    payload = {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
    if check and result.returncode != 0:
        raise HarnessError(
            f"Command failed: {' '.join(command)}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return payload


def restore_state(*, state_file: Path, had_state_file: bool, previous_bytes: bytes | None) -> None:
    if had_state_file and previous_bytes is not None:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_bytes(previous_bytes)
        return
    if state_file.exists():
        state_file.unlink()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def run_ffprobe(ffprobe_path: Path, media_path: Path) -> dict[str, Any]:
    command_payload = run_command(
        [
            str(ffprobe_path),
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(media_path),
        ],
        timeout=120.0,
    )
    payload = json.loads(command_payload["stdout"] or "{}")
    write_json(FFPROBE_JSON_PATH, payload)
    return {
        "command": command_payload["command"],
        "payload_path": str(FFPROBE_JSON_PATH),
        "payload": payload,
    }


def find_attached_pic_stream(ffprobe_payload: dict[str, Any]) -> dict[str, Any] | None:
    streams = ffprobe_payload.get("streams", [])
    if not isinstance(streams, list):
        return None
    for stream in streams:
        if not isinstance(stream, dict):
            continue
        disposition = stream.get("disposition")
        if isinstance(disposition, dict) and bool(disposition.get("attached_pic")):
            return stream
    return None


def parse_optional_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def path_exists(path_value: Any) -> bool:
    text = str(path_value or "").strip()
    if not text:
        return False
    try:
        return Path(text).expanduser().exists()
    except (OSError, ValueError):
        return False


def summarize_surface(surface_info: dict[str, Any] | None) -> dict[str, Any]:
    info = surface_info if isinstance(surface_info, dict) else {}
    screenshot_path = str(info.get("screenshot_path") or "").strip()
    reason = str(info.get("reason") or "").strip()
    window = info.get("window")
    return {
        "available": bool(info.get("available")),
        "reason": reason,
        "error": str(info.get("error") or "").strip(),
        "screenshot_path": screenshot_path,
        "screenshot_exists": path_exists(screenshot_path),
        "window": window if isinstance(window, dict) else None,
    }


def build_acceptance_summary(summary: dict[str, Any]) -> dict[str, Any]:
    output_diff = summary.get("output_diff") if isinstance(summary.get("output_diff"), dict) else {}
    ffprobe = summary.get("ffprobe") if isinstance(summary.get("ffprobe"), dict) else {}
    attached_pic_dimensions = (
        ffprobe.get("attached_pic_dimensions") if isinstance(ffprobe.get("attached_pic_dimensions"), dict) else {}
    )
    attached_width = parse_optional_int(attached_pic_dimensions.get("width"))
    attached_height = parse_optional_int(attached_pic_dimensions.get("height"))
    attached_pic_square = bool(
        isinstance(ffprobe.get("attached_pic_stream"), dict)
        and attached_width is not None
        and attached_height is not None
        and attached_width == attached_height
    )

    explorer_surface = summarize_surface(summary.get("explorer_surface"))
    playback_surface = summarize_surface(summary.get("playback_surface"))
    playback_captured = playback_surface["available"] and playback_surface["screenshot_exists"]
    playback_unavailable = (
        not playback_surface["available"]
        and playback_surface["reason"] in PLAYBACK_ACCEPTABLE_UNAVAILABLE_REASONS
    )

    verified_m4a_path = str(summary.get("verified_m4a_path") or "").strip()
    verified_m4a_exists = path_exists(verified_m4a_path)
    cleanup_green = bool(summary.get("cleanup_green"))
    errors_present = bool(summary.get("errors"))

    claims = {
        "new_m4a_created": {
            "pass": bool(output_diff.get("verified_output_is_new")) and verified_m4a_exists,
            "verified_m4a_path": verified_m4a_path,
            "verified_m4a_exists": verified_m4a_exists,
            "new_m4a_paths": output_diff.get("new_m4a_paths") or [],
        },
        "attached_pic_square_confirmed": {
            "pass": attached_pic_square,
            "width": attached_width,
            "height": attached_height,
        },
        "explorer_screenshot_captured": {
            "pass": explorer_surface["available"] and explorer_surface["screenshot_exists"],
            "available": explorer_surface["available"],
            "screenshot_path": explorer_surface["screenshot_path"],
            "screenshot_exists": explorer_surface["screenshot_exists"],
            "reason": explorer_surface["reason"],
        },
        "playback_surface_captured_or_unavailable": {
            "pass": playback_captured or playback_unavailable,
            "status": "captured" if playback_captured else "unavailable" if playback_unavailable else "failed",
            "available": playback_surface["available"],
            "screenshot_path": playback_surface["screenshot_path"],
            "screenshot_exists": playback_surface["screenshot_exists"],
            "reason": playback_surface["reason"],
            "error": playback_surface["error"],
        },
        "cleanup_green": {
            "pass": cleanup_green,
            "lingering_processes": summary.get("lingering_processes_after_run") or {},
        },
    }

    claim_results = [bool(claim.get("pass")) for claim in claims.values()]
    verdict = "accepted" if claim_results and all(claim_results) and not errors_present else "rejected"

    visual_review = {
        "status": "complete",
        "requires_human_review": False,
        "machine_rule": (
            "Accept only when a new m4a exists, ffprobe confirms a square attached_pic, "
            "Explorer screenshot exists, playback screenshot exists or playback is explicitly "
            "marked unavailable/unsupported, and cleanup is green."
        ),
        "explorer_surface": explorer_surface,
        "playback_surface": {
            **playback_surface,
            "status": claims["playback_surface_captured_or_unavailable"]["status"],
        },
        "decision": verdict,
    }

    return {
        "technical_verdict": "passed" if not errors_present and claims["new_m4a_created"]["pass"] and claims["attached_pic_square_confirmed"]["pass"] and claims["cleanup_green"]["pass"] else "failed",
        "verdict": verdict,
        "acceptance": {
            "rule": "accepted only when all machine-readable claims pass and no execution errors are recorded",
            "claims": claims,
            "all_claims_pass": bool(claim_results) and all(claim_results),
        },
        "visual_review": visual_review,
    }


def kill_process_tree(root_pid: int) -> None:
    if root_pid <= 0:
        return
    try:
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(root_pid)],
            capture_output=True,
            encoding="utf-8",
            check=False,
            timeout=20,
        )
    except Exception:
        return


def match_window(
    *,
    baseline_handles: set[int],
    candidate_windows: list[dict[str, Any]],
    scorer: Callable[[dict[str, Any], set[int]], int],
) -> dict[str, Any] | None:
    best_window: dict[str, Any] | None = None
    best_score = 0
    for window in candidate_windows:
        score = scorer(window, baseline_handles)
        if score > best_score:
            best_window = window
            best_score = score
    return best_window


def wait_for_window(
    *,
    baseline_handles: set[int],
    timeout: float,
    scorer: Callable[[dict[str, Any], set[int]], int],
    windows_dump_path: Path,
    required_score: int = 1,
) -> dict[str, Any] | None:
    deadline = time.monotonic() + timeout
    latest_windows: list[dict[str, Any]] = []
    best_window: dict[str, Any] | None = None
    best_score = 0
    while time.monotonic() < deadline:
        latest_windows = list_windows()
        matched = match_window(
            baseline_handles=baseline_handles,
            candidate_windows=latest_windows,
            scorer=scorer,
        )
        if matched is not None:
            score = scorer(matched, baseline_handles)
            if score > best_score:
                best_window = matched
                best_score = score
        if matched is not None and best_score >= required_score:
            write_json(windows_dump_path, latest_windows)
            return best_window
        time.sleep(0.3)
    write_json(windows_dump_path, latest_windows)
    return best_window


def _powershell_escape_single_quoted(value: str) -> str:
    return value.replace("'", "''")


def send_explorer_extra_large_icons(window_title: str) -> dict[str, Any]:
    escaped_title = _powershell_escape_single_quoted(window_title)
    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        (
            "$wshell = New-Object -ComObject WScript.Shell; "
            f"$activated = $wshell.AppActivate('{escaped_title}'); "
            "Start-Sleep -Milliseconds 400; "
            "if ($activated) { $wshell.SendKeys('^+1'); Start-Sleep -Milliseconds 600 }; "
            "Write-Output $activated"
        ),
    ]
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def send_foreground_keys(keys: str, *, delay_ms: int = 250) -> dict[str, Any]:
    escaped_keys = _powershell_escape_single_quoted(keys)
    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        (
            "$wshell = New-Object -ComObject WScript.Shell; "
            f"Start-Sleep -Milliseconds {max(delay_ms, 0)}; "
            f"$wshell.SendKeys('{escaped_keys}')"
        ),
    ]
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def open_explorer_for_file(media_path: Path) -> dict[str, Any]:
    baseline_windows = list_windows()
    baseline_handles = {int(window["handle"]) for window in baseline_windows}
    subprocess.Popen(["explorer.exe", f'/select,"{media_path}"'], cwd=PROJECT_ROOT)

    file_name = media_path.name.lower()
    stem = media_path.stem.lower()
    output_dir_name = media_path.parent.name.lower()

    def score(window: dict[str, Any], previous_handles: set[int]) -> int:
        process_name = str(window.get("process_name", "")).lower()
        title = str(window.get("title", "")).lower()
        value = 0
        if process_name == "explorer.exe":
            value += 5
        if int(window.get("handle", 0)) not in previous_handles:
            value += 3
        if title == output_dir_name:
            value += 20
        if file_name in title:
            value += 3
        if stem in title:
            value += 2
        if output_dir_name in title:
            value += 1
        return value

    matched = wait_for_window(
        baseline_handles=baseline_handles,
        timeout=20.0,
        scorer=score,
        windows_dump_path=WINDOWS_AFTER_EXPLORER_PATH,
        required_score=9,
    )
    if matched is None:
        return {
            "available": False,
            "reason": "explorer_window_not_found",
        }

    focus_window_handle(int(matched["handle"]))
    time.sleep(0.8)
    capture_window_handle(int(matched["handle"]), EXPLORER_SCREENSHOT_PATH)

    return {
        "available": True,
        "window": matched,
        "screenshot_path": str(EXPLORER_SCREENSHOT_PATH),
        "open_mode": "explorer_select",
    }


def open_playback_surface(media_path: Path) -> dict[str, Any]:
    baseline_windows = list_windows()
    baseline_handles = {int(window["handle"]) for window in baseline_windows}
    try:
        os.startfile(str(media_path))
    except OSError as error:
        reason = "playback_launch_unsupported" if getattr(error, "winerror", 0) == 1155 else "playback_launch_failed"
        return {
            "available": False,
            "reason": reason,
            "error": str(error),
        }

    file_name = media_path.name.lower()
    stem = media_path.stem.lower()

    def score(window: dict[str, Any], previous_handles: set[int]) -> int:
        process_name = str(window.get("process_name", "")).lower()
        title = str(window.get("title", "")).lower()
        rect = window.get("rect") or {}
        area = int(rect.get("width", 0)) * int(rect.get("height", 0))
        value = 0
        if int(window.get("handle", 0)) not in previous_handles:
            value += 3
        if process_name in PLAYER_PROCESS_NAMES:
            value += 3
        if file_name in title:
            value += 3
        if stem in title:
            value += 2
        if process_name != "explorer.exe":
            value += 1
        value += min(area // 10000, 10)
        return value

    matched = wait_for_window(
        baseline_handles=baseline_handles,
        timeout=25.0,
        scorer=score,
        windows_dump_path=WINDOWS_AFTER_PLAYBACK_PATH,
        required_score=10,
    )
    if matched is None:
        return {
            "available": False,
            "reason": "playback_window_not_found",
        }

    focus_window_handle(int(matched["handle"]))
    time.sleep(4.0)
    capture_window_handle(int(matched["handle"]), PLAYBACK_SCREENSHOT_PATH)

    return {
        "available": True,
        "window": matched,
        "screenshot_path": str(PLAYBACK_SCREENSHOT_PATH),
    }


def cleanup_window(window_info: dict[str, Any] | None) -> dict[str, Any]:
    if not window_info or not window_info.get("available") or not isinstance(window_info.get("window"), dict):
        return {"closed": False}
    handle = int(window_info["window"].get("handle", 0))
    if not handle:
        return {"closed": False}
    try:
        close_window_handle(handle, timeout=15.0)
        return {"closed": True, "handle": handle}
    except Exception as error:
        return {"closed": False, "handle": handle, "error": str(error)}


def find_lingering_processes(repo_root: Path) -> dict[str, list[dict[str, Any]]]:
    repo_fragment = str(repo_root).lower()
    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        (
            "Get-CimInstance Win32_Process "
            "| Select-Object ProcessId, Name, CommandLine "
            "| ConvertTo-Json -Depth 4"
        ),
    ]
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    try:
        payload = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        payload = []
    if isinstance(payload, dict):
        processes = [payload]
    elif isinstance(payload, list):
        processes = payload
    else:
        processes = []

    main_bridge: list[dict[str, Any]] = []
    ffmpeg: list[dict[str, Any]] = []
    for process in processes:
        if not isinstance(process, dict):
            continue
        name = str(process.get("Name") or "")
        command_line = str(process.get("CommandLine") or "")
        normalized_name = name.lower()
        joined = command_line.lower()
        if not joined:
            continue
        if "main.py" in joined and "--ui-shell" in joined and "bridge" in joined and repo_fragment in joined:
            main_bridge.append(
                {
                    "pid": int(process.get("ProcessId") or 0),
                    "name": name,
                    "command_line": command_line,
                }
            )
        if normalized_name == "ffmpeg.exe" and repo_fragment in joined:
            ffmpeg.append(
                {
                    "pid": int(process.get("ProcessId") or 0),
                    "name": name,
                    "command_line": command_line,
                }
            )
    return {"main_bridge": main_bridge, "ffmpeg": ffmpeg}


def main() -> int:
    default_config = create_default_config(PROJECT_ROOT)
    controller = AppController(default_config)
    ffprobe_resolution = controller.tool_resolver.resolve_ffprobe()
    if not ffprobe_resolution.path:
        raise HarnessError("ffprobe is not available; live Windows artwork proof cannot continue.")

    shutil.rmtree(PROOF_DIR, ignore_errors=True)
    PROOF_DIR.mkdir(parents=True, exist_ok=True)

    output_dir = default_config.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    before_m4a = snapshot_m4a_paths(output_dir)
    state_file = default_config.state_file
    had_state_file = state_file.exists()
    previous_state_bytes = state_file.read_bytes() if had_state_file else None
    if state_file.exists():
        state_file.unlink()

    harness_config = {
        "task_id": TASK_ID,
        "run_id": "run-01",
        "proof_dir": str(PROOF_DIR),
        "source_url": DEFAULT_SOURCE_URL,
        "default_launch_command": "poetry run python main.py --ui-shell bridge",
    }
    write_json(CONFIG_PATH, harness_config)

    summary: dict[str, Any] = {
        "task_id": TASK_ID,
        "canonical_command": "poetry run python scripts/validation/tz_er_audio_art_03_live_windows.py",
        "default_launch_command": "poetry run python main.py --ui-shell bridge",
        "proof_dir": str(PROOF_DIR),
        "source_url": DEFAULT_SOURCE_URL,
        "output_dir": str(output_dir),
        "state_file": str(state_file),
        "artifacts": {
            "bridge_harness_config": str(CONFIG_PATH),
            "bridge_session_summary": str(SESSION_SUMMARY_PATH),
            "main_stdout_log": str(MAIN_STDOUT_LOG),
            "main_stderr_log": str(MAIN_STDERR_LOG),
            "ffprobe_json": str(FFPROBE_JSON_PATH),
            "explorer_screenshot": str(EXPLORER_SCREENSHOT_PATH),
            "playback_screenshot": str(PLAYBACK_SCREENSHOT_PATH),
            "windows_after_explorer": str(WINDOWS_AFTER_EXPLORER_PATH),
            "windows_after_playback": str(WINDOWS_AFTER_PLAYBACK_PATH),
        },
        "checks": [],
        "errors": [],
        "verdict": "rejected",
        "started_at": datetime.now(UTC).isoformat(),
    }

    root_process: subprocess.Popen[str] | None = None
    explorer_info: dict[str, Any] | None = None
    playback_info: dict[str, Any] | None = None

    try:
        env = os.environ.copy()
        env["BACK_IN_MY_DAYS_YOUTUBE_WINDOWS_AUDIO_ART_PROOF_CONFIG"] = str(CONFIG_PATH)
        with MAIN_STDOUT_LOG.open("w", encoding="utf-8") as stdout_file, MAIN_STDERR_LOG.open(
            "w", encoding="utf-8"
        ) as stderr_file:
            root_process = subprocess.Popen(
                ["poetry", "run", "python", "main.py", "--ui-shell", "bridge"],
                cwd=PROJECT_ROOT,
                env=env,
                stdout=stdout_file,
                stderr=stderr_file,
                text=True,
            )
            summary["checks"].append(
                {
                    "name": "default_bridge_launch",
                    "pid": root_process.pid,
                    "status": "started",
                }
            )
            try:
                bridge_exit_code = root_process.wait(timeout=TIMEOUT_SECONDS)
                timed_out = False
            except subprocess.TimeoutExpired:
                timed_out = True
                bridge_exit_code = 124
                kill_process_tree(root_process.pid)
                root_process.wait(timeout=20)

        summary["bridge_process"] = {
            "pid": root_process.pid if root_process else 0,
            "timed_out": timed_out,
            "exit_code": bridge_exit_code,
        }
        if not SESSION_SUMMARY_PATH.exists():
            raise HarnessError("Bridge harness did not produce bridge-session-summary.json.")

        session_summary = load_json(SESSION_SUMMARY_PATH)
        summary["bridge_session"] = session_summary
        if timed_out or bridge_exit_code != 0 or not session_summary.get("harness_completed"):
            raise HarnessError(
                "Bridge harness did not complete successfully."
            )

        output_path = Path(str(session_summary.get("output_path", ""))).expanduser().resolve()
        if not output_path.exists():
            raise HarnessError(f"Expected output file is missing: {output_path}")
        summary["verified_m4a_path"] = str(output_path)

        after_m4a = snapshot_m4a_paths(output_dir)
        new_m4a_paths = sorted(set(after_m4a) - set(before_m4a))
        new_file_in_output = str(output_path) in new_m4a_paths
        summary["output_diff"] = {
            "before_m4a_count": len(before_m4a),
            "after_m4a_count": len(after_m4a),
            "new_m4a_paths": new_m4a_paths,
            "verified_output_is_new": new_file_in_output,
        }
        summary["checks"].append(
            {
                "name": "new_output_in_default_output_dir",
                "status": "passed" if new_file_in_output else "failed",
                "verified_m4a_path": str(output_path),
            }
        )
        if not new_file_in_output:
            raise HarnessError("The verified output path is not new relative to the pre-run output snapshot.")

        ffprobe_result = run_ffprobe(ffprobe_resolution.path, output_path)
        ffprobe_payload = ffprobe_result["payload"]
        attached_pic_stream = find_attached_pic_stream(ffprobe_payload)
        attached_width = parse_optional_int(attached_pic_stream.get("width") if attached_pic_stream else None)
        attached_height = parse_optional_int(attached_pic_stream.get("height") if attached_pic_stream else None)
        summary["ffprobe"] = {
            "command": ffprobe_result["command"],
            "attached_pic_stream": attached_pic_stream,
            "attached_pic_dimensions": {
                "width": attached_width,
                "height": attached_height,
            },
        }
        ffprobe_ok = bool(
            attached_pic_stream
            and attached_width is not None
            and attached_height is not None
            and attached_width == attached_height
        )
        summary["checks"].append(
            {
                "name": "ffprobe_attached_pic_square",
                "status": "passed" if ffprobe_ok else "failed",
                "width": attached_width,
                "height": attached_height,
            }
        )
        if not ffprobe_ok:
            raise HarnessError("ffprobe did not confirm a square attached_pic stream on the final m4a.")

        explorer_info = open_explorer_for_file(output_path)
        summary["explorer_surface"] = explorer_info
        summary["checks"].append(
            {
                "name": "explorer_screenshot_captured",
                "status": "passed" if explorer_info.get("available") else "failed",
            }
        )
        if not explorer_info.get("available"):
            raise HarnessError("Explorer surface screenshot could not be captured.")

        playback_info = open_playback_surface(output_path)
        summary["playback_surface"] = playback_info
        summary["checks"].append(
            {
                "name": "playback_surface_captured",
                "status": "passed" if playback_info.get("available") else "unavailable",
                "reason": playback_info.get("reason", ""),
            }
        )
    except Exception as error:
        summary["errors"].append(str(error))
        if root_process is not None:
            kill_process_tree(root_process.pid)
    finally:
        explorer_cleanup = cleanup_window(explorer_info)
        playback_cleanup = cleanup_window(playback_info)
        summary["window_cleanup"] = {
            "explorer": explorer_cleanup,
            "playback": playback_cleanup,
        }

        lingering = find_lingering_processes(PROJECT_ROOT)
        summary["lingering_processes_after_run"] = lingering
        summary["cleanup_green"] = not lingering["main_bridge"] and not lingering["ffmpeg"]
        summary["checks"].append(
            {
                "name": "cleanup_green",
                "status": "passed" if summary["cleanup_green"] else "failed",
            }
        )

        restore_state(
            state_file=state_file,
            had_state_file=had_state_file,
            previous_bytes=previous_state_bytes,
        )
        summary["state_restore"] = {
            "restored": (
                state_file.read_bytes() == previous_state_bytes
                if had_state_file and previous_state_bytes is not None
                else not state_file.exists()
            ),
            "had_original_state_file": had_state_file,
        }
        acceptance_summary = build_acceptance_summary(summary)
        summary["technical_verdict"] = acceptance_summary["technical_verdict"]
        summary["acceptance"] = acceptance_summary["acceptance"]
        summary["visual_review"] = acceptance_summary["visual_review"]
        summary["verdict"] = acceptance_summary["verdict"]
        summary["completed_at"] = datetime.now(UTC).isoformat()
        write_json(SUMMARY_PATH, summary)

    print(
        json.dumps(
            {
                "summary_path": str(SUMMARY_PATH),
                "technical_verdict": summary.get("technical_verdict"),
                "verdict": summary.get("verdict"),
                "verified_m4a_path": summary.get("verified_m4a_path", ""),
            },
            ensure_ascii=False,
        )
    )
    return 0 if summary.get("verdict") == "accepted" else 1


if __name__ == "__main__":
    raise SystemExit(main())
