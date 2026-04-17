from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .config import AppConfig
from .ffmpeg import MediaToolResolver
from .state_store import QueueStateStore


class AppShell:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.config.ensure_directories()
        self.store = QueueStateStore(config.state_file)
        self.tool_resolver = MediaToolResolver(config)
        self.root = tk.Tk()
        self.root.title("YT Downloader v1")
        self.root.geometry("920x520")
        self.root.minsize(800, 420)
        self._build_ui()
        self._populate_runtime_info()

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        frame = ttk.Frame(self.root, padding=16)
        frame.grid(sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(4, weight=1)

        title = ttk.Label(
            frame,
            text="YT Downloader v1 shell",
            font=("Segoe UI", 18, "bold"),
        )
        title.grid(row=0, column=0, columnspan=2, sticky="w")

        subtitle = ttk.Label(
            frame,
            text="Baseline UI/runtime stack: Python 3.12 + Tkinter + stdlib JSON state.",
        )
        subtitle.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 16))

        self.paths_label = ttk.Label(frame, justify="left")
        self.paths_label.grid(row=2, column=0, sticky="nw", padx=(0, 24))

        self.tools_label = ttk.Label(frame, justify="left")
        self.tools_label.grid(row=2, column=1, sticky="nw")

        queue_header = ttk.Label(frame, text="Queue snapshot", font=("Segoe UI", 12, "bold"))
        queue_header.grid(row=3, column=0, columnspan=2, sticky="w", pady=(24, 8))

        self.queue_list = tk.Listbox(frame, height=12)
        self.queue_list.grid(row=4, column=0, columnspan=2, sticky="nsew")

    def _populate_runtime_info(self) -> None:
        items = self.store.load()
        ffmpeg = self.tool_resolver.resolve_ffmpeg()
        ffprobe = self.tool_resolver.resolve_ffprobe()

        paths_text = "\n".join(
            [
                f"Project root: {self.config.project_root}",
                f"Runtime dir: {self.config.runtime_dir}",
                f"Output dir: {self.config.output_dir}",
                f"Temp dir: {self.config.temp_dir}",
                f"Queue state: {self.config.state_file}",
            ]
        )
        self.paths_label.configure(text=paths_text)

        tools_text = "\n".join(
            [
                f"ffmpeg: {self._format_resolution(ffmpeg)}",
                f"ffprobe: {self._format_resolution(ffprobe)}",
                "",
                f"Queue items loaded: {len(items)}",
            ]
        )
        self.tools_label.configure(text=tools_text)

        self.queue_list.delete(0, tk.END)
        if not items:
            self.queue_list.insert(tk.END, "Queue is empty.")
            return

        for item in items:
            self.queue_list.insert(
                tk.END,
                f"{item.status} | {item.mode} | {item.quality} | {item.source_url}",
            )

    @staticmethod
    def _format_resolution(resolution: object) -> str:
        binary = resolution
        if getattr(binary, "path", None):
            return f"{binary.source}: {binary.path}"
        return "missing"

    def run(self) -> None:
        self.root.mainloop()

    def close(self) -> None:
        self.root.destroy()
