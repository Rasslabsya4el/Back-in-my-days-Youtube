from __future__ import annotations

import threading
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

from ..controller import AppController, AppState
from ..controller.contracts import to_json_safe_payload
from ..core import DownloadPipelineError, MediaPostprocessError, YoutubeProbeError
from ..models import DownloadMode

BRIDGE_API_VERSION = "bridge.v1"
DEFAULT_EVENT_HISTORY = 64


class AppBridgeApi:
    def __init__(
        self,
        controller: AppController,
        *,
        max_events: int = DEFAULT_EVENT_HISTORY,
    ) -> None:
        self.controller = controller
        self.max_events = max(1, max_events)
        self._controller_lock = threading.Lock()
        self._event_lock = threading.Lock()
        self._download_lock = threading.Lock()
        self._events: list[dict[str, Any]] = []
        self._event_cursor = 0
        self._latest_state: dict[str, Any] = {}
        self._active_download_thread: threading.Thread | None = None
        self._active_download_item_id = ""
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
        if self._download_is_active():
            return self._error_response(
                code="download_in_progress",
                message="Bridge mutations are blocked while a download is running.",
            )

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

    def select_item(self, payload: dict[str, Any] | str | None = None) -> dict[str, Any]:
        if self._download_is_active():
            return self._error_response(
                code="download_in_progress",
                message="Bridge mutations are blocked while a download is running.",
            )

        try:
            item_id = self._read_optional_string(payload, "item_id")
        except ValueError as error:
            return self._error_response(code="invalid_request", message=str(error))
        state = self._call_controller(self.controller.select_item, item_id or None)
        return self._state_response(state)

    def select_mode(self, payload: dict[str, Any] | str | None = None) -> dict[str, Any]:
        if self._download_is_active():
            return self._error_response(
                code="download_in_progress",
                message="Bridge mutations are blocked while a download is running.",
            )

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
        if self._download_is_active():
            return self._error_response(
                code="download_in_progress",
                message="Bridge mutations are blocked while a download is running.",
            )

        try:
            quality = self._read_required_string(payload, "quality")
        except ValueError as error:
            return self._error_response(code="invalid_request", message=str(error))
        state = self._call_controller(self.controller.select_quality, quality)
        return self._state_response(state)

    def start_download(self, payload: dict[str, Any] | str | None = None) -> dict[str, Any]:
        if self._download_is_active():
            return self._error_response(
                code="download_in_progress",
                message="A download is already running. Poll get_app_state for progress updates.",
            )

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

        if selected_item_id not in {str(item.get("id", "")) for item in state.get("queue", [])}:
            return self._error_response(
                code="unknown_item",
                message=f"Queue item {selected_item_id!r} is not available in the current bridge state.",
            )

        if item_id and selected_item_id != str(state.get("selected_item_id", "")):
            self._call_controller(self.controller.select_item, selected_item_id)

        worker = threading.Thread(
            target=self._run_download,
            kwargs={"item_id": selected_item_id},
            name=f"bridge-download-{selected_item_id}",
            daemon=True,
        )
        with self._download_lock:
            self._active_download_thread = worker
            self._active_download_item_id = selected_item_id
        worker.start()
        return self._response(
            data={
                "accepted": True,
                "item_id": selected_item_id,
                "state": self._latest_state_copy(),
            },
        )

    def get_runtime_info(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        del payload
        state = self._latest_state_copy()
        return self._response(
            data={
                "runtime": deepcopy(state.get("runtime", {})),
                "bridge": {
                    "api_version": BRIDGE_API_VERSION,
                    "download_active": self._download_is_active(),
                    "active_download_item_id": self._active_download_item_id_copy(),
                    "update_model": {
                        "kind": "polling",
                        "state_method": "get_app_state",
                        "cursor_arg": "since_event_id",
                        "event_shape": "full_state_snapshot",
                        "max_retained_events": self.max_events,
                    },
                    "command_model": {
                        "start_download_async": True,
                        "mutations_blocked_while_downloading": True,
                    },
                    "shells": {
                        "tkinter_fallback": True,
                        "pywebview_bootstrap": True,
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

        return self._response(
            data={
                "output_path": output_path,
                "inspection": to_json_safe_payload(inspection),
            },
        )

    def _run_download(self, *, item_id: str) -> None:
        try:
            self._call_controller(self.controller.start_download, item_id)
        except DownloadPipelineError:
            return
        finally:
            with self._download_lock:
                self._active_download_thread = None
                self._active_download_item_id = ""

    def _call_controller(self, callback: Any, *args: Any) -> Any:
        with self._controller_lock:
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
        response_meta = {
            "api_version": BRIDGE_API_VERSION,
            "event_cursor": self._current_event_cursor(),
            "download_active": self._download_is_active(),
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
                "download_active": self._download_is_active(),
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

    def _download_is_active(self) -> bool:
        with self._download_lock:
            return self._active_download_thread is not None and self._active_download_thread.is_alive()

    def _active_download_item_id_copy(self) -> str:
        with self._download_lock:
            return self._active_download_item_id

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
