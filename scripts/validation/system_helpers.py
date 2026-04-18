from __future__ import annotations

import argparse
import ctypes
import time
from pathlib import Path

import psutil
from PIL import ImageGrab


user32 = ctypes.windll.user32


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


def _set_dpi_aware() -> None:
    try:
        user32.SetProcessDPIAware()
    except Exception:
        return


def _find_window_handle(title: str) -> int:
    handle = user32.FindWindowW(None, title)
    if handle and user32.IsWindowVisible(handle):
        return int(handle)
    return 0


def find_window(title: str, *, timeout: float) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        handle = _find_window_handle(title)
        if handle:
            return handle
        time.sleep(0.2)
    raise RuntimeError(f"Visible window {title!r} was not found within {timeout:.1f}s.")


def wait_window_closed(title: str, *, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _find_window_handle(title):
            return
        time.sleep(0.2)
    raise RuntimeError(f"Window {title!r} stayed visible for longer than {timeout:.1f}s.")


def capture_window(title: str, output_path: Path, *, timeout: float) -> None:
    _set_dpi_aware()
    handle = find_window(title, timeout=timeout)
    user32.ShowWindow(handle, 9)
    try:
        user32.SetForegroundWindow(handle)
    except Exception:
        pass
    time.sleep(0.35)

    rect = RECT()
    if not user32.GetWindowRect(handle, ctypes.byref(rect)):
        raise RuntimeError(f"Failed to read bounds for window {title!r}.")

    bbox = (rect.left, rect.top, rect.right, rect.bottom)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ImageGrab.grab(bbox=bbox, all_screens=True).save(output_path)


def wait_pid_exit(pid: int, *, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not psutil.pid_exists(pid):
            return
        time.sleep(0.2)
    raise RuntimeError(f"PID {pid} did not exit within {timeout:.1f}s.")


def main() -> int:
    parser = argparse.ArgumentParser(description="System-level screenshot and process helpers.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    capture_parser = subparsers.add_parser("capture-window")
    capture_parser.add_argument("title")
    capture_parser.add_argument("output_path")
    capture_parser.add_argument("--timeout", type=float, default=20.0)

    close_parser = subparsers.add_parser("wait-window-closed")
    close_parser.add_argument("title")
    close_parser.add_argument("--timeout", type=float, default=20.0)

    pid_parser = subparsers.add_parser("wait-pid-exit")
    pid_parser.add_argument("pid", type=int)
    pid_parser.add_argument("--timeout", type=float, default=20.0)

    args = parser.parse_args()
    if args.command == "capture-window":
        capture_window(args.title, Path(args.output_path), timeout=args.timeout)
        return 0
    if args.command == "wait-window-closed":
        wait_window_closed(args.title, timeout=args.timeout)
        return 0
    if args.command == "wait-pid-exit":
        wait_pid_exit(args.pid, timeout=args.timeout)
        return 0

    raise RuntimeError(f"Unsupported helper command {args.command!r}.")


if __name__ == "__main__":
    raise SystemExit(main())
