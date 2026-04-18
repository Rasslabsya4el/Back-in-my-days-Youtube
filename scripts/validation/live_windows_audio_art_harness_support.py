from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from app.bridge import AppBridgeApi, PywebviewHost

WINDOW_TITLE = PywebviewHost.title


def run_live_windows_audio_art_harness(
    *,
    bridge_api: AppBridgeApi,
    start_url: str | None,
    debug: bool,
    config_path: Path,
) -> int:
    import webview

    run_config = json.loads(config_path.read_text(encoding="utf-8"))
    proof_dir = Path(run_config["proof_dir"])
    proof_dir.mkdir(parents=True, exist_ok=True)

    host = PywebviewHost(bridge_api)
    environment = host.probe_environment()
    launch_target = host.resolve_launch_target(start_url=start_url)
    summary_path = proof_dir / "bridge-session-summary.json"
    initial_screenshot_path = proof_dir / "bridge-shell-initial.png"
    final_screenshot_path = proof_dir / "bridge-shell-final.png"

    summary: dict[str, Any] = {
        "task_id": run_config["task_id"],
        "run_id": run_config["run_id"],
        "proof_dir": str(proof_dir),
        "source_url": run_config["source_url"],
        "default_launch_command": run_config["default_launch_command"],
        "pywebview_environment": {
            "pywebview_version": environment.pywebview_version,
            "module_path": environment.module_path,
        },
        "launch_target": {
            "kind": launch_target.kind,
            "value": launch_target.value,
        },
        "artifacts": {
            "summary_json": str(summary_path),
            "initial_bridge_screenshot": str(initial_screenshot_path),
            "final_bridge_screenshot": str(final_screenshot_path),
        },
        "steps": [],
        "errors": [],
    }

    if launch_target.kind not in {"url", "file"}:
        summary["errors"].append(
            "Frontend build is missing. Run npm run build before the live Windows artwork harness."
        )
        _write_summary(summary_path, summary)
        return 1

    result_holder: dict[str, int] = {"exit_code": 1}
    window = webview.create_window(
        WINDOW_TITLE,
        url=launch_target.value,
        js_api=bridge_api,
        width=1180,
        height=820,
    )

    def automation() -> None:
        try:
            _wait_for_dom_ready(window)
            _capture_window(initial_screenshot_path)
            summary["steps"].append({"step": "bridge_dom_ready", "status": "ok"})

            _submit_url(window, run_config["source_url"])
            queued_state = _wait_for_queue_item(bridge_api, timeout=120.0)
            selected_item = _selected_item_from_state(queued_state)
            if selected_item is None:
                raise RuntimeError("Queue item was added but selected item is missing in bridge state.")
            summary["steps"].append(
                {
                    "step": "url_submitted",
                    "status": "ok",
                    "selected_item_id": selected_item.get("id", ""),
                    "selected_title": selected_item.get("title", ""),
                }
            )

            _click_audio_mode(window)
            audio_state = _wait_for_audio_selection(bridge_api, timeout=20.0)
            audio_item = _selected_item_from_state(audio_state)
            summary["steps"].append(
                {
                    "step": "audio_mode_selected",
                    "status": "ok",
                    "selection_mode": (audio_state.get("selection") or {}).get("mode", ""),
                    "item_mode": audio_item.get("mode", "") if audio_item else "",
                }
            )

            _click_primary_download(window)
            completed_state = _wait_for_download_terminal(bridge_api, timeout=240.0)
            completed_item = _selected_item_from_state(completed_state)
            _capture_window(final_screenshot_path)
            summary["steps"].append(
                {
                    "step": "download_completed",
                    "status": "ok",
                    "final_status": completed_item.get("status", "") if completed_item else "",
                    "final_step": completed_item.get("processing_step", "") if completed_item else "",
                }
            )

            output_path = str(completed_item.get("output_path", "") if completed_item else "").strip()
            inspection_payload = bridge_api.inspect_output({"output_path": output_path}) if output_path else {}
            summary["selected_item"] = completed_item
            summary["final_state"] = {
                "selected_item_id": completed_state.get("selected_item_id", ""),
                "status_message": completed_state.get("status_message", ""),
                "queue_count": len(completed_state.get("queue") or []),
                "runtime": completed_state.get("runtime") or {},
                "selection": completed_state.get("selection") or {},
            }
            summary["inspection_payload"] = inspection_payload
            summary["output_path"] = output_path
            summary["output_exists"] = bool(output_path and Path(output_path).exists())
            summary["harness_completed"] = bool(
                completed_item
                and completed_item.get("status") == "completed"
                and output_path
                and Path(output_path).exists()
            )
            result_holder["exit_code"] = 0 if summary["harness_completed"] else 1
        except Exception as error:  # pragma: no cover - real GUI/runtime failures are environment-specific
            summary["errors"].append(str(error))
            summary["harness_completed"] = False
            result_holder["exit_code"] = 1
        finally:
            _write_summary(summary_path, summary)
            try:
                window.destroy()
            except Exception:
                pass

    webview.start(automation, debug=debug)
    return int(result_holder["exit_code"])


def _write_summary(summary_path: Path, summary: dict[str, Any]) -> None:
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _capture_window(output_path: Path) -> None:
    _run_system_helper("capture-window", WINDOW_TITLE, str(output_path), "--timeout", "20")


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


def _wait_for_dom_ready(window: Any, *, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ready = window.evaluate_js(
            """
            (function () {
              const form = document.querySelector('[data-testid="url-form"]');
              const input = document.querySelector('#youtube-link');
              const topbar = document.querySelector('[data-testid="topbar"]');
              return Boolean(form && input && topbar && window.pywebview && window.pywebview.api);
            })();
            """
        )
        if ready:
            return
        time.sleep(0.2)
    raise RuntimeError("Bridge DOM did not become ready in time.")


def _submit_url(window: Any, source_url: str) -> None:
    submitted = window.evaluate_js(
        f"""
        (function () {{
          const input = document.querySelector('#youtube-link');
          const form = document.querySelector('[data-testid="url-form"]');
          if (!input || !form) {{
            return false;
          }}
          const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
          if (typeof setter !== 'function') {{
            return false;
          }}
          setter.call(input, {json.dumps(source_url)});
          input.dispatchEvent(new Event('input', {{ bubbles: true }}));
          if (typeof form.requestSubmit === 'function') {{
            form.requestSubmit();
          }} else {{
            form.dispatchEvent(new Event('submit', {{ bubbles: true, cancelable: true }}));
          }}
          return true;
        }})();
        """
    )
    if not submitted:
        raise RuntimeError("Failed to submit the YouTube URL through the bridge shell.")


def _click_audio_mode(window: Any) -> None:
    clicked = window.evaluate_js(
        """
        (function () {
          const buttons = Array.from(document.querySelectorAll('.toggle-chip'));
          const target = buttons.find((button) => (button.textContent || '').trim() === 'Audio');
          if (!target || target.disabled) {
            return false;
          }
          target.click();
          return true;
        })();
        """
    )
    if not clicked:
        raise RuntimeError("Failed to click the Audio mode toggle.")


def _click_primary_download(window: Any) -> None:
    clicked = window.evaluate_js(
        """
        (function () {
          const target = document.querySelector('.action-buttons .btn.primary');
          if (!target || target.disabled) {
            return false;
          }
          target.click();
          return true;
        })();
        """
    )
    if not clicked:
        raise RuntimeError("Failed to click the primary download button.")


def _wait_for_queue_item(bridge_api: AppBridgeApi, *, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_state: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        state = _current_state(bridge_api)
        last_state = state
        queue = state.get("queue") or []
        if len(queue) >= 1 and _selected_item_from_state(state):
            return state
        time.sleep(0.25)
    raise RuntimeError(
        f"Timed out waiting for the queued item after URL submit. Last state: {json.dumps(last_state, ensure_ascii=False)}"
    )


def _wait_for_audio_selection(bridge_api: AppBridgeApi, *, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_state: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        state = _current_state(bridge_api)
        last_state = state
        selection = state.get("selection") or {}
        selected_item = _selected_item_from_state(state) or {}
        if selection.get("mode") == "audio" and selected_item.get("mode") == "audio":
            return state
        time.sleep(0.2)
    raise RuntimeError(
        f"Timed out waiting for audio mode selection. Last state: {json.dumps(last_state, ensure_ascii=False)}"
    )


def _wait_for_download_terminal(bridge_api: AppBridgeApi, *, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_state: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        state = _current_state(bridge_api)
        last_state = state
        selected_item = _selected_item_from_state(state) or {}
        status = str(selected_item.get("status", ""))
        if status == "completed" and str(selected_item.get("output_path", "")).strip():
            return state
        if status in {"failed", "cancelled"}:
            raise RuntimeError(
                f"Download reached terminal status={status!r}: {json.dumps(selected_item, ensure_ascii=False)}"
            )
        time.sleep(0.5)
    raise RuntimeError(
        f"Timed out waiting for completed audio download. Last state: {json.dumps(last_state, ensure_ascii=False)}"
    )


def _current_state(bridge_api: AppBridgeApi) -> dict[str, Any]:
    payload = bridge_api.get_app_state({"since_event_id": 0})
    if not payload.get("ok"):
        raise RuntimeError(
            f"Bridge get_app_state failed: {payload.get('error', {}).get('message', 'unknown error')}"
        )
    state = payload.get("data", {}).get("state")
    if not isinstance(state, dict):
        raise RuntimeError("Bridge state payload is missing the state object.")
    return state


def _selected_item_from_state(state: dict[str, Any]) -> dict[str, Any] | None:
    selected_item = state.get("selected_item")
    return selected_item if isinstance(selected_item, dict) else None
