from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from app.bridge import AppBridgeApi, PywebviewHost


WINDOW_TITLE = PywebviewHost.title
FORBIDDEN_STATUS_SNIPPETS = (
    "File ready.",
    "Waiting to start.",
    "Saved as",
)


def run_live_ui_harness(
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

    summary: dict[str, Any] = {
        "task_id": run_config["task_id"],
        "run_id": run_config["run_id"],
        "proof_dir": str(proof_dir),
        "default_launch_command": run_config["default_launch_command"],
        "launch_target": {
            "kind": launch_target.kind,
            "value": launch_target.value,
        },
        "pywebview_environment": {
            "pywebview_version": environment.pywebview_version,
            "module_path": environment.module_path,
        },
        "artifacts": {},
        "assertions": {},
        "steps": [],
        "errors": [],
    }
    summary_path = proof_dir / "summary.json"
    dom_snapshot_path = proof_dir / "dom-snapshot.html"
    image_state_path = proof_dir / "image-state.json"
    screenshot_paths = {
        "item-a": proof_dir / "screenshot-item-a.png",
        "item-b": proof_dir / "screenshot-item-b.png",
        "item-c": proof_dir / "screenshot-item-c.png",
    }
    summary["artifacts"]["summary_json"] = str(summary_path)
    summary["artifacts"]["dom_snapshot"] = str(dom_snapshot_path)
    summary["artifacts"]["image_state"] = str(image_state_path)
    summary["artifacts"]["screenshots"] = {key: str(path) for key, path in screenshot_paths.items()}

    if launch_target.kind not in {"url", "file"}:
        summary["errors"].append(
            "Frontend build is missing. Run npm run build before the live UI harness."
        )
        _finalize_summary(
            summary=summary,
            summary_path=summary_path,
            dom_snapshot_path=dom_snapshot_path,
            image_state_path=image_state_path,
            dom_html="",
            image_states=[],
        )
        return 1

    result_holder: dict[str, Any] = {"exit_code": 1}
    window = webview.create_window(
        WINDOW_TITLE,
        url=launch_target.value,
        js_api=bridge_api,
        width=1180,
        height=820,
    )

    def automation() -> None:
        dom_html = ""
        image_states: list[dict[str, Any]] = []
        try:
            initial_snapshot = _wait_for_shell_ready(window, expected_count=len(run_config["items"]))
            summary["initial_snapshot"] = initial_snapshot

            item_results: list[dict[str, Any]] = []
            for index, item in enumerate(run_config["items"]):
                _click_queue_item(window, item["id"])
                step_snapshot = _wait_for_selected_item(window, item["id"], item["title"])
                screenshot_key = f"item-{item['key'].lower()}"
                _capture_window(screenshot_paths[screenshot_key])
                step_snapshot["screenshot"] = str(screenshot_paths[screenshot_key])
                item_results.append(step_snapshot)
                image_states.append(
                    {
                        "item_id": item["id"],
                        "item_key": item["key"],
                        "title": item["title"],
                        "preview": step_snapshot["preview"],
                    }
                )
                if index == len(run_config["items"]) - 1:
                    dom_html = step_snapshot["html"]

            summary["steps"] = item_results
            summary["assertions"] = _build_assertions(
                initial_snapshot=initial_snapshot,
                item_results=item_results,
                expected_queue_ready_count=run_config["expected_queue_ready_count"],
            )
            summary["overall_pass"] = all(summary["assertions"].values())
            summary["failed_assertions"] = [
                key for key, value in summary["assertions"].items() if not value
            ]
            result_holder["exit_code"] = 0 if summary["overall_pass"] else 1
        except Exception as error:  # pragma: no cover - real GUI failures are environment-specific
            summary["errors"].append(str(error))
            summary["overall_pass"] = False
            summary["failed_assertions"] = ["harness_runtime_error"]
            result_holder["exit_code"] = 1
        finally:
            _finalize_summary(
                summary=summary,
                summary_path=summary_path,
                dom_snapshot_path=dom_snapshot_path,
                image_state_path=image_state_path,
                dom_html=dom_html,
                image_states=image_states,
            )
            try:
                window.destroy()
            except Exception:
                pass

    webview.start(automation, debug=debug)
    return int(result_holder["exit_code"])


def _wait_for_shell_ready(window: Any, *, expected_count: int) -> dict[str, Any]:
    deadline = time.monotonic() + 20.0
    last_snapshot: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        snapshot = _dom_snapshot(window)
        last_snapshot = snapshot
        if snapshot["queue_count"] == expected_count and snapshot["selected_title"]:
            return snapshot
        time.sleep(0.2)
    raise RuntimeError(
        f"Live harness shell did not become ready in time. Last snapshot: {json.dumps(last_snapshot, ensure_ascii=False)}"
    )


def _wait_for_selected_item(window: Any, item_id: str, title: str) -> dict[str, Any]:
    deadline = time.monotonic() + 6.0
    last_snapshot: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        snapshot = _dom_snapshot(window)
        last_snapshot = snapshot
        selected_row = next(
            (row for row in snapshot["queue_rows"] if row["item_id"] == item_id and row["selected"]),
            None,
        )
        preview = snapshot["preview"]
        if (
            selected_row
            and snapshot["selected_title"] == title
            and preview["img_exists"]
            and preview["current_src"]
            and preview["complete"]
            and preview["natural_width"] > 0
        ):
            return snapshot
        time.sleep(0.15)
    if last_snapshot is None:
        raise RuntimeError(f"No DOM snapshot was collected for item {title!r}.")
    return last_snapshot


def _build_assertions(
    *,
    initial_snapshot: dict[str, Any],
    item_results: list[dict[str, Any]],
    expected_queue_ready_count: int,
) -> dict[str, bool]:
    preview_states = [step["preview"] for step in item_results]
    status_states = [step["selected_status"] for step in item_results]
    action_states = [step["action_block"] for step in item_results]

    current_srcs = [state["current_src"] for state in preview_states]
    status_texts = [state["surface_text"] for state in status_states]
    action_texts = [state["text"] for state in action_states]

    return {
        "preview_img_current_src_present": all(bool(value) for value in current_srcs),
        "preview_img_complete": all(bool(state["complete"]) for state in preview_states),
        "preview_img_natural_width_positive": all(
            int(state["natural_width"]) > 0 for state in preview_states
        ),
        "preview_current_src_changes_a_to_b_to_c": len(set(current_srcs)) == len(preview_states),
        "preview_not_stuck_loading_after_ready": all(
            not (state["placeholder_visible"] and state["complete"] and state["natural_width"] > 0)
            for state in preview_states
        ),
        "selected_status_label_present": all(bool(state["label"]) for state in status_states),
        "selected_status_secondary_detail_absent": all(
            not state["detail_exists"] and not state["detail"] for state in status_states
        ),
        "selected_status_no_file_ready": all("File ready." not in text for text in status_texts),
        "selected_status_no_waiting_to_start": all(
            "Waiting to start." not in text for text in status_texts
        ),
        "selected_status_no_saved_as": all("Saved as" not in text for text in status_texts),
        "selected_status_no_path_fragments": all(
            not _contains_path_fragment(text) for text in status_texts
        ),
        "action_block_no_final_output_helper": all(
            "Final output saves as" not in text for text in action_texts
        ),
        "top_bar_queue_header_no_paste": "Paste" not in initial_snapshot["all_text"],
        "top_bar_queue_header_no_green_ready_dot": not initial_snapshot["header_has_ready_dot"],
        "top_bar_queue_header_no_persisted_session_items": (
            "Persisted session items" not in initial_snapshot["all_text"]
        ),
        "queue_header_has_download_all": any(
            button["text"] == f"Download all queued ({expected_queue_ready_count})"
            for button in initial_snapshot["queue_header"]["buttons"]
        ),
        "queue_header_has_clear_queue": any(
            button["text"] == "Clear queue" for button in initial_snapshot["queue_header"]["buttons"]
        ),
    }


def _dom_snapshot(window: Any) -> dict[str, Any]:
    snapshot = _evaluate_js(
        window,
        """
        const clean = (value) => (value || "").trim().replace(/\\s+/g, " ");
        const byTestId = (value) => document.querySelector(`[data-testid="${value}"]`);
        const buttonText = (button) => clean(button?.innerText || button?.textContent || "");
        const queueHeader = document.querySelector(".rail-header");
        const selectedImage = byTestId("selected-preview-image");
        const selectedPlaceholder = byTestId("selected-preview-placeholder");
        return {
          all_text: clean(document.body?.innerText || ""),
          selected_title: clean(document.querySelector(".focus-main .item-headline h3")?.innerText || ""),
          queue_count: document.querySelectorAll('[data-testid="queue-row-rail"]').length,
          queue_rows: [...document.querySelectorAll('[data-testid="queue-row-rail"]')].map((button) => ({
            item_id: button.getAttribute("data-queue-item-id") || "",
            selected: button.classList.contains("selected"),
            text: buttonText(button),
          })),
          preview: {
            img_exists: !!selectedImage,
            current_src: selectedImage?.currentSrc || "",
            complete: !!selectedImage?.complete,
            natural_width: selectedImage?.naturalWidth || 0,
            placeholder_visible: !!selectedPlaceholder,
            placeholder_text: clean(selectedPlaceholder?.innerText || ""),
          },
          selected_status: {
            label: clean(byTestId("selected-status-label")?.innerText || ""),
            detail: clean(byTestId("selected-status-detail")?.innerText || ""),
            detail_exists: !!byTestId("selected-status-detail"),
            surface_text: clean(byTestId("selected-status")?.innerText || ""),
          },
          action_block: {
            hint: clean(byTestId("action-block-hint")?.innerText || ""),
            text: clean(byTestId("action-block")?.innerText || ""),
          },
          topbar: {
            text: clean(byTestId("topbar")?.innerText || ""),
            buttons: [...(byTestId("topbar")?.querySelectorAll("button") || [])].map((button) => ({
              text: buttonText(button),
              disabled: !!button.disabled,
            })),
          },
          queue_header: {
            text: clean(queueHeader?.innerText || ""),
            buttons: [...(byTestId("queue-header-actions")?.querySelectorAll("button") || [])].map((button) => ({
              text: buttonText(button),
              disabled: !!button.disabled,
              title: clean(button.getAttribute("title") || ""),
            })),
          },
          header_has_ready_dot: !!document.querySelector(
            '.topbar .conn-dot, .topbar .ready-dot, .topbar .status-dot, .rail-header .conn-dot, .rail-header .ready-dot, .rail-header .status-dot'
          ),
          html: document.documentElement.outerHTML,
        };
        """,
    )
    return snapshot


def _click_queue_item(window: Any, item_id: str) -> None:
    _evaluate_js(
        window,
        f"""
        const target = document.querySelector('[data-testid="queue-row-rail"][data-queue-item-id="{item_id}"]');
        if (!target) {{
          throw new Error('Queue item not found for harness item_id={item_id}.');
        }}
        target.click();
        return true;
        """,
    )


def _evaluate_js(window: Any, script: str) -> Any:
    return window.evaluate_js(f"(function(){{{script}}})()")


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
        except Exception as error:  # pragma: no cover - system python differences are environment-specific
            last_error = error
    raise RuntimeError(f"System helper failed for args={args!r}: {last_error}")


def _contains_path_fragment(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    return bool(re.search(r"[A-Za-z]:\\|\\\\|/[^ ]+", normalized))


def _finalize_summary(
    *,
    summary: dict[str, Any],
    summary_path: Path,
    dom_snapshot_path: Path,
    image_state_path: Path,
    dom_html: str,
    image_states: list[dict[str, Any]],
) -> None:
    dom_snapshot_path.write_text(dom_html, encoding="utf-8")
    image_state_path.write_text(
        json.dumps({"image_states": image_states}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
