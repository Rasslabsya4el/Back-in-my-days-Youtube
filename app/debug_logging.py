from __future__ import annotations

import atexit
import ctypes
import logging
import os
import sys
import tempfile
import threading
import traceback
from pathlib import Path

from .paths import (
    APP_NAME,
    LOGGER_NAMESPACE,
    is_frozen,
    is_installed_build,
    resolve_debug_log_path,
    writable_app_root,
)

_BOOTSTRAPPED = False
_ACTIVE_LOG_PATH: Path | None = None
_STREAM_TEES: list["_StreamTee"] = []


class _StreamTee:
    def __init__(
        self,
        *,
        stream_name: str,
        original_stream: object | None,
        logger: logging.Logger,
        level: int,
    ) -> None:
        self.stream_name = stream_name
        self._original_stream = original_stream
        self._logger = logger
        self._level = level
        self._buffer = ""
        self._logging_guard = False
        self.encoding = getattr(original_stream, "encoding", "utf-8")
        self.errors = getattr(original_stream, "errors", "replace")

    def write(self, value: str) -> int:
        text = str(value)
        original = self._original_stream
        if original is not None and hasattr(original, "write"):
            original.write(text)
        self._buffer += text
        self._drain_complete_lines()
        return len(text)

    def flush(self) -> None:
        original = self._original_stream
        if original is not None and hasattr(original, "flush"):
            original.flush()
        if self._buffer:
            self._emit_log_line(self._buffer)
            self._buffer = ""

    def isatty(self) -> bool:
        original = self._original_stream
        if original is not None and hasattr(original, "isatty"):
            return bool(original.isatty())
        return False

    def fileno(self) -> int:
        original = self._original_stream
        if original is None or not hasattr(original, "fileno"):
            raise OSError(f"{self.stream_name} does not have a file descriptor")
        return int(original.fileno())

    def _drain_complete_lines(self) -> None:
        while True:
            newline_index = self._buffer.find("\n")
            if newline_index < 0:
                return
            line = self._buffer[: newline_index + 1]
            self._buffer = self._buffer[newline_index + 1 :]
            self._emit_log_line(line)

    def _emit_log_line(self, raw_line: str) -> None:
        line = raw_line.rstrip("\r\n")
        if not line or self._logging_guard:
            return
        self._logging_guard = True
        try:
            self._logger.log(self._level, "[%s] %s", self.stream_name, line)
        finally:
            self._logging_guard = False


def bootstrap_debug_logging() -> Path:
    global _BOOTSTRAPPED, _ACTIVE_LOG_PATH

    if _BOOTSTRAPPED and _ACTIVE_LOG_PATH is not None:
        return _ACTIVE_LOG_PATH

    log_path = _select_log_path()
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(threadName)s %(name)s | %(message)s"))

    root_logger = logging.getLogger()
    root_logger.setLevel(min(root_logger.level, logging.INFO) if root_logger.level else logging.INFO)
    root_logger.addHandler(handler)
    logging.captureWarnings(True)

    _install_exception_hooks()
    _install_stream_tees()
    atexit.register(_flush_stream_tees)

    _BOOTSTRAPPED = True
    _ACTIVE_LOG_PATH = log_path

    logger = logging.getLogger(f"{LOGGER_NAMESPACE}.startup")
    logger.info("=== session start ===")
    logger.info(
        "pid=%s executable=%r cwd=%r frozen=%s installed_build=%s writable_root=%r debug_log=%r argv=%r",
        os.getpid(),
        sys.executable,
        os.getcwd(),
        is_frozen(),
        is_installed_build(),
        str(writable_app_root()),
        str(log_path),
        sys.argv,
    )
    return log_path


def active_debug_log_path() -> Path:
    return _ACTIVE_LOG_PATH or bootstrap_debug_logging()


def log_exception(message: str) -> None:
    logging.getLogger(LOGGER_NAMESPACE).exception(message)


def show_fatal_error_dialog(message: str, *, title: str = APP_NAME) -> None:
    if os.name != "nt":
        return
    if os.environ.get("BACK_IN_MY_DAYS_YOUTUBE_SUPPRESS_FATAL_DIALOG", "").strip() == "1":
        return
    try:
        ctypes.windll.user32.MessageBoxW(None, message, title, 0x10)
    except Exception:
        return


def build_startup_error_message(reason: str) -> str:
    return (
        f"{APP_NAME} could not start.\n\n"
        f"{reason}\n\n"
        f"Debug log:\n{active_debug_log_path()}"
    )


def _select_log_path() -> Path:
    candidates = [
        resolve_debug_log_path(),
        writable_app_root() / "runtime" / "debug.log",
        Path(tempfile.gettempdir()) / APP_NAME / "debug.log",
    ]
    seen: set[Path] = set()
    for candidate in candidates:
        normalized = candidate.expanduser().resolve()
        if normalized in seen:
            continue
        seen.add(normalized)
        try:
            normalized.parent.mkdir(parents=True, exist_ok=True)
            with normalized.open("a", encoding="utf-8"):
                pass
        except OSError:
            continue
        return normalized
    raise RuntimeError("Unable to create a writable debug log file.")


def _install_stream_tees() -> None:
    if _STREAM_TEES:
        return
    stdout_logger = logging.getLogger(f"{LOGGER_NAMESPACE}.stdout")
    stderr_logger = logging.getLogger(f"{LOGGER_NAMESPACE}.stderr")
    stdout_tee = _StreamTee(
        stream_name="stdout",
        original_stream=sys.stdout,
        logger=stdout_logger,
        level=logging.INFO,
    )
    stderr_tee = _StreamTee(
        stream_name="stderr",
        original_stream=sys.stderr,
        logger=stderr_logger,
        level=logging.ERROR,
    )
    sys.stdout = stdout_tee
    sys.stderr = stderr_tee
    _STREAM_TEES.extend((stdout_tee, stderr_tee))


def _flush_stream_tees() -> None:
    for stream in _STREAM_TEES:
        try:
            stream.flush()
        except Exception:
            continue


def _install_exception_hooks() -> None:
    previous_sys_hook = sys.excepthook
    previous_thread_hook = getattr(threading, "excepthook", None)

    def _sys_excepthook(exc_type, exc_value, exc_traceback) -> None:  # type: ignore[no-untyped-def]
        logging.getLogger(f"{LOGGER_NAMESPACE}.crash").critical(
            "Unhandled exception\n%s",
            "".join(traceback.format_exception(exc_type, exc_value, exc_traceback)),
        )
        if previous_sys_hook is not None:
            previous_sys_hook(exc_type, exc_value, exc_traceback)

    def _thread_excepthook(args: threading.ExceptHookArgs) -> None:
        logging.getLogger(f"{LOGGER_NAMESPACE}.crash").critical(
            "Unhandled thread exception thread=%r\n%s",
            args.thread.name if args.thread else "",
            "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)),
        )
        if previous_thread_hook is not None:
            previous_thread_hook(args)

    sys.excepthook = _sys_excepthook
    if previous_thread_hook is not None:
        threading.excepthook = _thread_excepthook
