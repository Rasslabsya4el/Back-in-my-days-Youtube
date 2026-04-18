from __future__ import annotations

import argparse
import ctypes
import json
import subprocess
import time
from pathlib import Path
from typing import Any

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
WM_CLOSE = 0x0010
SW_RESTORE = 9


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)


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


def _window_exists(handle: int) -> bool:
    if not handle:
        return False
    return bool(user32.IsWindow(handle))


def _window_rect(handle: int) -> RECT:
    rect = RECT()
    if not user32.GetWindowRect(handle, ctypes.byref(rect)):
        raise RuntimeError(f"Failed to read bounds for window handle={handle}.")
    return rect


def _window_text(handle: int) -> str:
    length = int(user32.GetWindowTextLengthW(handle))
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(handle, buffer, len(buffer))
    return buffer.value.strip()


def _window_class_name(handle: int) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(handle, buffer, len(buffer))
    return buffer.value.strip()


def _window_process_id(handle: int) -> int:
    process_id = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(handle, ctypes.byref(process_id))
    return int(process_id.value)


def _tasklist_process_names_by_pid() -> dict[int, str]:
    try:
        result = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            encoding="utf-8",
            check=False,
            timeout=20,
        )
    except Exception:
        return {}

    process_names: dict[int, str] = {}
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line.startswith('"'):
            continue
        parts = [part.strip('"') for part in line.split('","')]
        if len(parts) < 2:
            continue
        try:
            process_id = int(parts[1])
        except ValueError:
            continue
        process_names[process_id] = parts[0]
    return process_names


def _process_name(process_id: int) -> str:
    return _tasklist_process_names_by_pid().get(process_id, "")


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


def focus_window_handle(handle: int) -> None:
    if not _window_exists(handle):
        raise RuntimeError(f"Window handle={handle} is not available.")
    user32.ShowWindow(handle, SW_RESTORE)
    try:
        user32.SetForegroundWindow(handle)
    except Exception:
        return


def capture_window(title: str, output_path: Path, *, timeout: float) -> None:
    _set_dpi_aware()
    handle = find_window(title, timeout=timeout)
    capture_window_handle(handle, output_path)


def capture_window_handle(handle: int, output_path: Path) -> None:
    _set_dpi_aware()
    if not _window_exists(handle):
        raise RuntimeError(f"Window handle={handle} is not available for capture.")
    rect = _window_rect(handle)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    width = int(rect.right - rect.left)
    height = int(rect.bottom - rect.top)
    escaped_output_path = str(output_path).replace("'", "''")
    powershell_command = (
        "Add-Type @\""
        "\nusing System.Runtime.InteropServices;"
        "\npublic static class NativeMethods {"
        "\n    [DllImport(\"user32.dll\")] public static extern bool SetProcessDPIAware();"
        "\n    [DllImport(\"user32.dll\")] public static extern bool PrintWindow(System.IntPtr hwnd, System.IntPtr hdcBlt, uint nFlags);"
        "\n}"
        "\n\"@; "
        "[void][NativeMethods]::SetProcessDPIAware(); "
        "Add-Type -AssemblyName System.Drawing; "
        f"$bitmap = New-Object System.Drawing.Bitmap {width}, {height}; "
        "$graphics = [System.Drawing.Graphics]::FromImage($bitmap); "
        "$hdc = $graphics.GetHdc(); "
        f"$printOk = [NativeMethods]::PrintWindow([intptr]{handle}, $hdc, 2); "
        "if (-not $printOk) { "
        f"  $null = [NativeMethods]::PrintWindow([intptr]{handle}, $hdc, 0); "
        "} "
        "$graphics.ReleaseHdc($hdc); "
        f"$bitmap.Save('{escaped_output_path}', [System.Drawing.Imaging.ImageFormat]::Png); "
        "$graphics.Dispose(); "
        "$bitmap.Dispose()"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", powershell_command],
        capture_output=True,
        encoding="utf-8",
        check=False,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"PowerShell screenshot capture failed for handle={handle}: {result.stderr or result.stdout}"
        )
    if not output_path.exists():
        raise RuntimeError(f"Expected screenshot output is missing: {output_path}")


def wait_pid_exit(pid: int, *, timeout: float) -> None:
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    SYNCHRONIZE = 0x00100000
    access_mask = PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        handle = kernel32.OpenProcess(access_mask, False, pid)
        if not handle:
            return
        wait_result = kernel32.WaitForSingleObject(handle, 0)
        kernel32.CloseHandle(handle)
        if wait_result == 0:
            return
        time.sleep(0.2)
    raise RuntimeError(f"PID {pid} did not exit within {timeout:.1f}s.")


def close_window_handle(handle: int, *, timeout: float) -> None:
    if not _window_exists(handle):
        return
    user32.PostMessageW(handle, WM_CLOSE, 0, 0)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _window_exists(handle) or not user32.IsWindowVisible(handle):
            return
        time.sleep(0.2)
    raise RuntimeError(f"Window handle={handle} did not close within {timeout:.1f}s.")


def list_windows() -> list[dict[str, Any]]:
    windows: list[dict[str, Any]] = []
    process_names_by_pid = _tasklist_process_names_by_pid()

    @WNDENUMPROC
    def callback(raw_handle: int, _lparam: int) -> bool:
        handle = int(raw_handle)
        if not user32.IsWindowVisible(handle):
            return True
        title = _window_text(handle)
        if not title:
            return True
        try:
            rect = _window_rect(handle)
        except RuntimeError:
            return True
        width = int(rect.right - rect.left)
        height = int(rect.bottom - rect.top)
        if width <= 0 or height <= 0:
            return True
        process_id = _window_process_id(handle)
        windows.append(
            {
                "handle": handle,
                "title": title,
                "class_name": _window_class_name(handle),
                "process_id": process_id,
                "process_name": process_names_by_pid.get(process_id, ""),
                "rect": {
                    "left": int(rect.left),
                    "top": int(rect.top),
                    "right": int(rect.right),
                    "bottom": int(rect.bottom),
                    "width": width,
                    "height": height,
                },
            }
        )
        return True

    user32.EnumWindows(callback, 0)
    return windows


def main() -> int:
    parser = argparse.ArgumentParser(description="System-level screenshot and process helpers.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    capture_parser = subparsers.add_parser("capture-window")
    capture_parser.add_argument("title")
    capture_parser.add_argument("output_path")
    capture_parser.add_argument("--timeout", type=float, default=20.0)

    capture_handle_parser = subparsers.add_parser("capture-window-handle")
    capture_handle_parser.add_argument("handle", type=int)
    capture_handle_parser.add_argument("output_path")

    close_parser = subparsers.add_parser("wait-window-closed")
    close_parser.add_argument("title")
    close_parser.add_argument("--timeout", type=float, default=20.0)

    close_handle_parser = subparsers.add_parser("close-window-handle")
    close_handle_parser.add_argument("handle", type=int)
    close_handle_parser.add_argument("--timeout", type=float, default=20.0)

    focus_handle_parser = subparsers.add_parser("focus-window-handle")
    focus_handle_parser.add_argument("handle", type=int)

    pid_parser = subparsers.add_parser("wait-pid-exit")
    pid_parser.add_argument("pid", type=int)
    pid_parser.add_argument("--timeout", type=float, default=20.0)

    list_parser = subparsers.add_parser("list-windows")
    list_parser.add_argument("--indent", type=int, default=2)

    args = parser.parse_args()
    if args.command == "capture-window":
        capture_window(args.title, Path(args.output_path), timeout=args.timeout)
        return 0
    if args.command == "capture-window-handle":
        capture_window_handle(args.handle, Path(args.output_path))
        return 0
    if args.command == "wait-window-closed":
        wait_window_closed(args.title, timeout=args.timeout)
        return 0
    if args.command == "close-window-handle":
        close_window_handle(args.handle, timeout=args.timeout)
        return 0
    if args.command == "focus-window-handle":
        focus_window_handle(args.handle)
        return 0
    if args.command == "wait-pid-exit":
        wait_pid_exit(args.pid, timeout=args.timeout)
        return 0
    if args.command == "list-windows":
        print(json.dumps(list_windows(), indent=args.indent, ensure_ascii=True))
        return 0

    raise RuntimeError(f"Unsupported helper command {args.command!r}.")


if __name__ == "__main__":
    raise SystemExit(main())
