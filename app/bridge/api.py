from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

from ..controller import AppController, AppState
from ..controller.contracts import to_json_safe_payload
from ..core import DownloadPipelineError, MediaPostprocessError, YoutubeProbeError
from ..models import DownloadMode
from ..paths import resolve_webview2_runtime_dir

BRIDGE_API_VERSION = "bridge.v1"
DEFAULT_EVENT_HISTORY = 64
INSPECTION_OK_STATUS = "ok"
INSPECTION_UNAVAILABLE_STATUS = "ffprobe_unavailable"
INSPECTION_UNAVAILABLE_MESSAGE = "Output inspection is unavailable because ffprobe is not available."


class AppBridgeApi:
    def __init__(
        self,
        controller: AppController,
        *,
        max_events: int = DEFAULT_EVENT_HISTORY,
    ) -> None:
        self.controller = controller
        self.max_events = max(1, max_events)
        self._event_lock = threading.Lock()
        self._download_lock = threading.Lock()
        self._events: list[dict[str, Any]] = []
        self._event_cursor = 0
        self._latest_state: dict[str, Any] = {}
        self._active_downloads: dict[str, threading.Thread] = {}
        self.controller.subscribe(self._record_state_event)
        self._record_state_event(self.controller.get_state(), event_type="bootstrap")

    def get_app_state(self, payload: dict[str, Any] | int | str | None = None) -> dict[str, Any]:
        try:
            since_event_id = self._read_event_cursor(payload)
        except ValueError as error:
            return self._error_response(code="invalid_request", message=str(error))
        with self._event_lock:
            current_cursor = self._event_cursor
            has_updates = since_event_id < current_cursor
            oldest_event_id = self._events[0]["event_id"] if self._events else current_cursor
            if not has_updates:
                events: list[dict[str, Any]] = []
                current_state: dict[str, Any] | None = None
            else:
                current_state = deepcopy(self._latest_state)
                events = [
                    deepcopy(event) for event in self._events if event["event_id"] > since_event_id
                ]
        return self._response(
            data={
                "state": current_state,
                "state_changed": has_updates,
                "events": events,
            },
            meta={
                "event_cursor": current_cursor,
                "events_truncated": bool(since_event_id and since_event_id < max(oldest_event_id - 1, 0)),
            },
        )

    def add_url(self, payload: dict[str, Any] | str | None = None) -> dict[str, Any]:
        try:
            url = self._read_required_string(payload, "url")
            state = self._call_controller(self.controller.add_url, url)
        except ValueError as error:
            return self._error_response(code="invalid_request", message=str(error))
        except YoutubeProbeError as error:
            return self._error_response(
                code=f"probe_{error.code.value}",
                message=str(error),
            )
        return self._state_response(state)

    def read_clipboard_text(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        del payload
        try:
            text = self._read_clipboard_text()
        except RuntimeError as error:
            return self._error_response(code="clipboard_unavailable", message=str(error))
        return self._response(data={"text": text})

    def select_item(self, payload: dict[str, Any] | str | None = None) -> dict[str, Any]:
        try:
            item_id = self._read_optional_string(payload, "item_id")
        except ValueError as error:
            return self._error_response(code="invalid_request", message=str(error))
        state = self._call_controller(self.controller.select_item, item_id or None)
        return self._state_response(state)

    def select_mode(self, payload: dict[str, Any] | str | None = None) -> dict[str, Any]:
        try:
            mode = self._read_required_string(payload, "mode")
        except ValueError as error:
            return self._error_response(code="invalid_request", message=str(error))

        try:
            normalized_mode = DownloadMode(mode).value
        except ValueError:
            return self._error_response(
                code="invalid_mode",
                message=f"Unsupported mode {mode!r}. Expected one of {[item.value for item in DownloadMode]}.",
            )
        state = self._call_controller(self.controller.select_mode, normalized_mode)
        return self._state_response(state)

    def select_quality(self, payload: dict[str, Any] | str | None = None) -> dict[str, Any]:
        try:
            quality = self._read_required_string(payload, "quality")
        except ValueError as error:
            return self._error_response(code="invalid_request", message=str(error))
        state = self._call_controller(self.controller.select_quality, quality)
        return self._state_response(state)

    def clear_queue(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        del payload
        if self._active_download_item_ids_copy():
            return self._error_response(
                code="downloads_active",
                message="Finish active downloads before clearing the queue.",
            )

        state = self._call_controller(self.controller.clear_queue)
        return self._response(
            data={
                "cleared": True,
                "state": state.to_dict(),
            }
        )

    def pick_output_dir(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        del payload
        current_output_dir = str(self._latest_state_copy().get("runtime", {}).get("output_dir", ""))
        try:
            selected_dir = self._open_output_dir_dialog(current_output_dir)
        except RuntimeError as error:
            return self._error_response(code="output_dir_dialog_failed", message=str(error))

        if not selected_dir:
            return self._response(
                data={
                    "cancelled": True,
                    "state": self._latest_state_copy(),
                }
            )

        state = self._call_controller(self.controller.set_output_dir, Path(selected_dir))
        return self._response(
            data={
                "cancelled": False,
                "state": state.to_dict(),
            }
        )

    def open_output_dir(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        del payload
        output_dir = str(self._latest_state_copy().get("runtime", {}).get("output_dir", "")).strip()
        if not output_dir:
            return self._error_response(
                code="output_dir_unavailable",
                message="Current output folder is not available yet.",
            )

        target_dir = Path(output_dir).expanduser().resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._open_directory(target_dir)
        except RuntimeError as error:
            return self._error_response(code="open_output_dir_failed", message=str(error))

        return self._response(
            data={
                "opened": True,
                "output_dir": str(target_dir),
            }
        )

    def start_download(self, payload: dict[str, Any] | str | None = None) -> dict[str, Any]:
        try:
            item_id = self._read_optional_string(payload, "item_id")
        except ValueError as error:
            return self._error_response(code="invalid_request", message=str(error))

        state = self._latest_state_copy()
        selected_item_id = item_id or str(state.get("selected_item_id", ""))
        if not selected_item_id:
            return self._response(
                data={
                    "accepted": False,
                    "item_id": "",
                    "state": state,
                },
            )

        queue_ids = {str(item.get("id", "")) for item in state.get("queue", [])}
        if selected_item_id not in queue_ids:
            return self._error_response(
                code="unknown_item",
                message=f"Queue item {selected_item_id!r} is not available in the current bridge state.",
            )
        if not self._spawn_download_job(selected_item_id):
            return self._error_response(
                code="download_in_progress",
                message=f"Queue item {selected_item_id!r} is already running.",
            )

        return self._response(
            data={
                "accepted": True,
                "item_id": selected_item_id,
                "state": self._latest_state_copy(),
            },
        )

    def start_all_downloads(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        del payload
        state = self._latest_state_copy()
        queued_item_ids = [
            str(item.get("id", ""))
            for item in state.get("queue", [])
            if str(item.get("status", "")) == "queued"
        ]
        if not queued_item_ids:
            return self._response(
                data={
                    "accepted": False,
                    "started_item_ids": [],
                    "queued_item_ids": [],
                    "state": state,
                }
            )

        started_item_ids = [
            item_id for item_id in queued_item_ids if item_id and self._spawn_download_job(item_id)
        ]
        return self._response(
            data={
                "accepted": bool(started_item_ids),
                "started_item_ids": started_item_ids,
                "queued_item_ids": queued_item_ids,
                "state": self._latest_state_copy(),
            }
        )

    def get_runtime_info(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        del payload
        state = self._latest_state_copy()
        active_download_item_ids = self._active_download_item_ids_copy()
        active_downloads = self._active_downloads_copy()
        webview2_runtime_source, webview2_runtime_path = resolve_webview2_runtime_dir()
        return self._response(
            data={
                "runtime": deepcopy(state.get("runtime", {})),
                "bridge": {
                    "api_version": BRIDGE_API_VERSION,
                    "download_active": bool(active_download_item_ids),
                    "active_download_item_id": active_download_item_ids[0] if active_download_item_ids else "",
                    "active_download_count": len(active_download_item_ids),
                    "active_download_item_ids": active_download_item_ids,
                    "active_downloads": active_downloads,
                    "update_model": {
                        "kind": "polling",
                        "state_method": "get_app_state",
                        "cursor_arg": "since_event_id",
                        "event_shape": "full_state_snapshot",
                        "max_retained_events": self.max_events,
                    },
                    "command_model": {
                        "start_download_async": True,
                        "start_all_downloads_async": True,
                        "mutations_blocked_while_downloading": False,
                        "concurrent_downloads": True,
                    },
                    "shells": {
                        "tkinter_fallback": True,
                        "pywebview_bootstrap": True,
                        "webview2_runtime": {
                            "source": webview2_runtime_source or "system",
                            "path": str(webview2_runtime_path) if webview2_runtime_path else "",
                        },
                    },
                },
            },
        )

    def inspect_output(self, payload: dict[str, Any] | str | None = None) -> dict[str, Any]:
        try:
            requested_path = self._read_optional_string(payload, "output_path")
        except ValueError as error:
            return self._error_response(code="invalid_request", message=str(error))
        output_path = requested_path or self._selected_output_path()
        if not output_path:
            return self._response(
                data={
                    "output_path": "",
                    "inspection": None,
                },
            )

        try:
            inspection = self._call_controller(self.controller.inspect_output, Path(output_path))
        except MediaPostprocessError as error:
            return self._error_response(code="inspect_failed", message=str(error))

        if inspection is None:
            return self._response(
                data={
                    "output_path": output_path,
                    "inspection": None,
                    "inspection_status": INSPECTION_UNAVAILABLE_STATUS,
                    "message": INSPECTION_UNAVAILABLE_MESSAGE,
                },
            )

        return self._response(
            data={
                "output_path": output_path,
                "inspection": to_json_safe_payload(inspection),
                "inspection_status": INSPECTION_OK_STATUS,
                "message": "",
            },
        )

    def _run_download(self, *, item_id: str) -> None:
        try:
            self._call_controller(self.controller.start_download, item_id)
        except DownloadPipelineError:
            return
        finally:
            with self._download_lock:
                self._cleanup_finished_downloads_locked()
                self._active_downloads.pop(item_id, None)

    def _spawn_download_job(self, item_id: str) -> bool:
        worker = threading.Thread(
            target=self._run_download,
            kwargs={"item_id": item_id},
            name=f"bridge-download-{item_id}",
            daemon=True,
        )
        with self._download_lock:
            self._cleanup_finished_downloads_locked()
            existing_worker = self._active_downloads.get(item_id)
            if existing_worker is not None and existing_worker.is_alive():
                return False
            self._active_downloads[item_id] = worker
        worker.start()
        return True

    def _call_controller(self, callback: Any, *args: Any) -> Any:
        return callback(*args)

    def _record_state_event(self, state: AppState, event_type: str = "state_changed") -> None:
        payload = state.to_dict()
        with self._event_lock:
            self._event_cursor += 1
            event = {
                "event_id": self._event_cursor,
                "event_type": event_type,
                "emitted_at_unix_ms": int(time.time() * 1000),
                "state": payload,
            }
            self._events.append(event)
            if len(self._events) > self.max_events:
                self._events = self._events[-self.max_events :]
            self._latest_state = payload

    def _state_response(self, state: AppState) -> dict[str, Any]:
        return self._response(data={"state": state.to_dict()})

    def _response(
        self,
        *,
        data: dict[str, Any] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        active_download_item_ids = self._active_download_item_ids_copy()
        response_meta = {
            "api_version": BRIDGE_API_VERSION,
            "event_cursor": self._current_event_cursor(),
            "download_active": bool(active_download_item_ids),
            "active_download_item_id": active_download_item_ids[0] if active_download_item_ids else "",
            "active_download_count": len(active_download_item_ids),
            "active_download_item_ids": active_download_item_ids,
        }
        if meta:
            response_meta.update(meta)
        return {
            "ok": True,
            "data": data or {},
            "error": None,
            "meta": response_meta,
        }

    def _error_response(self, *, code: str, message: str) -> dict[str, Any]:
        active_download_item_ids = self._active_download_item_ids_copy()
        return {
            "ok": False,
            "data": {},
            "error": {
                "code": code,
                "message": message,
            },
            "meta": {
                "api_version": BRIDGE_API_VERSION,
                "event_cursor": self._current_event_cursor(),
                "download_active": bool(active_download_item_ids),
                "active_download_item_id": active_download_item_ids[0] if active_download_item_ids else "",
                "active_download_count": len(active_download_item_ids),
                "active_download_item_ids": active_download_item_ids,
            },
        }

    def _current_event_cursor(self) -> int:
        with self._event_lock:
            return self._event_cursor

    def _latest_state_copy(self) -> dict[str, Any]:
        with self._event_lock:
            return deepcopy(self._latest_state)

    def _selected_output_path(self) -> str:
        state = self._latest_state_copy()
        selected_item = state.get("selected_item")
        if not isinstance(selected_item, dict):
            return ""
        return str(selected_item.get("output_path", ""))

    def _active_download_item_ids_copy(self) -> list[str]:
        with self._download_lock:
            self._cleanup_finished_downloads_locked()
            return list(self._active_downloads.keys())

    def _active_downloads_copy(self) -> list[dict[str, str]]:
        with self._download_lock:
            self._cleanup_finished_downloads_locked()
            return [
                {
                    "item_id": item_id,
                    "thread_name": worker.name,
                }
                for item_id, worker in self._active_downloads.items()
            ]

    def _cleanup_finished_downloads_locked(self) -> None:
        finished_item_ids = [
            item_id for item_id, worker in self._active_downloads.items() if not worker.is_alive()
        ]
        for item_id in finished_item_ids:
            self._active_downloads.pop(item_id, None)

    @staticmethod
    def _read_required_string(payload: dict[str, Any] | str | None, field_name: str) -> str:
        value = AppBridgeApi._read_optional_string(payload, field_name)
        if not value:
            raise ValueError(f"Expected non-empty {field_name!r} string payload.")
        return value

    @staticmethod
    def _read_optional_string(payload: dict[str, Any] | str | None, field_name: str) -> str:
        if isinstance(payload, str):
            return payload.strip()
        if payload is None:
            return ""
        if not isinstance(payload, dict):
            raise ValueError(
                f"Expected {field_name!r} as a string or object payload, got {type(payload).__name__}."
            )
        return str(payload.get(field_name, "")).strip()

    @staticmethod
    def _read_event_cursor(payload: dict[str, Any] | int | str | None) -> int:
        if payload is None:
            return 0
        if isinstance(payload, int):
            return max(0, payload)
        if isinstance(payload, str):
            return int(payload) if payload.strip() else 0
        if not isinstance(payload, dict):
            raise ValueError(f"Unsupported get_app_state payload type {type(payload).__name__}.")
        raw_value = payload.get("since_event_id", 0)
        try:
            return max(0, int(raw_value))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _open_output_dir_dialog(initial_dir: str) -> str:
        dialog_error: Exception | None = None

        try:
            import webview

            window = next(iter(getattr(webview, "windows", [])), None)
            if window is not None:
                folder_dialog = getattr(getattr(webview, "FileDialog", None), "FOLDER", None)
                if folder_dialog is None:
                    folder_dialog = getattr(webview, "FOLDER_DIALOG", None)
                result = window.create_file_dialog(
                    dialog_type=folder_dialog,
                    directory=initial_dir,
                )
                return AppBridgeApi._normalize_dialog_selection(result)
        except Exception as error:  # pragma: no cover - dialog backend depends on GUI runtime
            dialog_error = error

        try:
            from tkinter import Tk, filedialog

            root = Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            try:
                selected_dir = filedialog.askdirectory(
                    initialdir=initial_dir or "",
                    title="Choose output folder",
                    parent=root,
                )
            finally:
                root.destroy()
            return str(selected_dir).strip()
        except Exception as error:  # pragma: no cover - dialog backend depends on GUI runtime
            if dialog_error is not None:
                raise RuntimeError(
                    f"Unable to open an output folder picker ({dialog_error}; {error})."
                ) from error
            raise RuntimeError(f"Unable to open an output folder picker ({error}).") from error

    @staticmethod
    def _normalize_dialog_selection(result: object) -> str:
        if not result:
            return ""
        if isinstance(result, (list, tuple)):
            return str(result[0]).strip() if result else ""
        return str(result).strip()

    @staticmethod
    def _open_directory(target_dir: Path) -> None:
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(target_dir))
                return
            if sys.platform == "darwin":
                subprocess.run(["open", str(target_dir)], check=True)
                return
            subprocess.run(["xdg-open", str(target_dir)], check=True)
        except Exception as error:
            raise RuntimeError(f"Unable to open the output folder ({error}).") from error

    @staticmethod
    def _read_clipboard_text() -> str:
        try:
            from tkinter import TclError, Tk

            root = Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            try:
                return str(root.clipboard_get()).strip()
            except TclError:
                return ""
            finally:
                root.destroy()
        except Exception as error:
            raise RuntimeError(f"Unable to read clipboard text ({error}).") from error
