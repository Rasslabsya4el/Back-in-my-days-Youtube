from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .controller import AppController, AppState, ProbeSnapshot, QueueItemSnapshot, ToolStatus
from .core import DownloadPipelineError, YoutubeProbeError


class AppShell:
    def __init__(self, controller: AppController) -> None:
        self.controller = controller
        self.root = tk.Tk()
        self.root.title("YT Downloader v1")
        self.root.geometry("980x700")
        self.root.minsize(880, 620)
        self.url_var = tk.StringVar()
        self.mode_var = tk.StringVar(value="video")
        self.quality_var = tk.StringVar()
        self.status_var = tk.StringVar()
        self.details_var = tk.StringVar(value="No item selected.")
        self.paths_text = tk.StringVar()
        self.tools_text = tk.StringVar()
        self._queue_ids: list[str] = []
        self._is_rendering = False
        self._build_ui()
        self.controller.subscribe(self._render_state)
        self._render_state(self.controller.get_state())

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        frame = ttk.Frame(self.root, padding=16)
        frame.grid(sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(6, weight=1)

        title = ttk.Label(
            frame,
            text="YT Downloader v1 shell",
            font=("Segoe UI", 18, "bold"),
        )
        title.grid(row=0, column=0, columnspan=2, sticky="w")

        subtitle = ttk.Label(
            frame,
            text="YouTube intake preloads metadata and saved media selection before download starts.",
        )
        subtitle.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 16))

        controls = ttk.LabelFrame(frame, text="Add YouTube URL", padding=12)
        controls.grid(row=2, column=0, columnspan=2, sticky="nsew")
        controls.columnconfigure(1, weight=1)
        controls.columnconfigure(3, weight=1)

        ttk.Label(controls, text="URL").grid(row=0, column=0, sticky="w")
        self.url_entry = ttk.Entry(controls, textvariable=self.url_var)
        self.url_entry.grid(row=0, column=1, columnspan=3, sticky="ew", padx=(8, 8))
        self.url_entry.bind("<Return>", self._handle_add_url)

        add_button = ttk.Button(controls, text="Add To Queue", command=self._handle_add_url)
        add_button.grid(row=0, column=4, sticky="e")

        ttk.Label(controls, text="Mode").grid(row=1, column=0, sticky="w", pady=(12, 0))
        self.mode_combo = ttk.Combobox(
            controls,
            textvariable=self.mode_var,
            state="readonly",
            values=("video", "audio"),
        )
        self.mode_combo.grid(row=1, column=1, sticky="ew", padx=(8, 24), pady=(12, 0))
        self.mode_combo.bind("<<ComboboxSelected>>", self._handle_mode_change)

        ttk.Label(controls, text="Quality").grid(row=1, column=2, sticky="w", pady=(12, 0))
        self.quality_combo = ttk.Combobox(
            controls,
            textvariable=self.quality_var,
            state="disabled",
        )
        self.quality_combo.grid(row=1, column=3, columnspan=2, sticky="ew", pady=(12, 0))
        self.quality_combo.bind("<<ComboboxSelected>>", self._handle_quality_change)

        status_label = ttk.Label(
            controls,
            textvariable=self.status_var,
            wraplength=820,
            justify="left",
        )
        status_label.grid(row=2, column=0, columnspan=5, sticky="w", pady=(12, 0))

        info_frame = ttk.Frame(frame)
        info_frame.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(16, 0))
        info_frame.columnconfigure(0, weight=1)
        info_frame.columnconfigure(1, weight=1)

        self.paths_label = ttk.Label(info_frame, justify="left", textvariable=self.paths_text)
        self.paths_label.grid(row=0, column=0, sticky="nw", padx=(0, 24))

        self.tools_label = ttk.Label(info_frame, justify="left", textvariable=self.tools_text)
        self.tools_label.grid(row=0, column=1, sticky="nw")

        details_frame = ttk.LabelFrame(frame, text="Selected Item", padding=12)
        details_frame.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(16, 0))
        details_frame.columnconfigure(0, weight=1)

        self.details_label = ttk.Label(
            details_frame,
            textvariable=self.details_var,
            justify="left",
            wraplength=880,
        )
        self.details_label.grid(row=0, column=0, sticky="w")

        self.download_button = ttk.Button(
            details_frame,
            text="Download Selected",
            command=self._handle_download_selected,
        )
        self.download_button.grid(row=1, column=0, sticky="w", pady=(12, 0))

        queue_header = ttk.Label(frame, text="Queue snapshot", font=("Segoe UI", 12, "bold"))
        queue_header.grid(row=5, column=0, columnspan=2, sticky="w", pady=(24, 8))

        self.queue_list = tk.Listbox(frame, height=14)
        self.queue_list.grid(row=6, column=0, columnspan=2, sticky="nsew")
        self.queue_list.bind("<<ListboxSelect>>", self._handle_queue_select)

    def _handle_add_url(self, _event: object | None = None) -> None:
        url = self.url_var.get().strip()
        try:
            self.controller.add_url(url)
        except YoutubeProbeError:
            return
        if url:
            self.url_var.set("")

    def _handle_queue_select(self, _event: object | None = None) -> None:
        if self._is_rendering:
            return

        selection = self.queue_list.curselection()
        if not selection:
            return

        index = selection[0]
        if index >= len(self._queue_ids):
            return

        self.controller.select_item(self._queue_ids[index])

    def _handle_mode_change(self, _event: object | None = None) -> None:
        if self._is_rendering:
            return
        self.controller.select_mode(self.mode_var.get())

    def _handle_quality_change(self, _event: object | None = None) -> None:
        if self._is_rendering:
            return
        self.controller.select_quality(self.quality_var.get())

    def _handle_download_selected(self) -> None:
        try:
            self.controller.start_download()
        except DownloadPipelineError:
            return

    def _render_state(self, state: AppState) -> None:
        self._is_rendering = True
        try:
            self.status_var.set(state.status_message)
            self._render_runtime(state)
            self._render_queue(state)
            self._render_selection(state)
            self._render_details(state.selected_item)
            self.download_button.configure(
                state="normal" if state.selected_item is not None else "disabled"
            )
        finally:
            self._is_rendering = False
        self.root.update_idletasks()

    def _render_runtime(self, state: AppState) -> None:
        runtime = state.runtime
        self.paths_text.set(
            "\n".join(
                [
                    f"Project root: {runtime.project_root}",
                    f"Runtime dir: {runtime.runtime_dir}",
                    f"Output dir: {runtime.output_dir}",
                    f"Temp dir: {runtime.temp_dir}",
                    f"Queue state: {runtime.state_file}",
                ]
            )
        )
        self.tools_text.set(
            "\n".join(
                [
                    f"ffmpeg: {self._format_resolution(runtime.ffmpeg)}",
                    f"ffprobe: {self._format_resolution(runtime.ffprobe)}",
                    "",
                    f"Queue items loaded: {runtime.queue_items_loaded}",
                ]
            )
        )

    def _render_queue(self, state: AppState) -> None:
        self._queue_ids = [item.id for item in state.queue]
        self.queue_list.delete(0, tk.END)
        if not state.queue:
            self.queue_list.insert(tk.END, "Queue is empty.")
            return

        for item in state.queue:
            self.queue_list.insert(tk.END, self._queue_label(item))

        if not state.selected_item_id:
            return

        try:
            index = self._queue_ids.index(state.selected_item_id)
        except ValueError:
            return

        self.queue_list.selection_clear(0, tk.END)
        self.queue_list.selection_set(index)
        self.queue_list.activate(index)
        self.queue_list.see(index)

    def _render_selection(self, state: AppState) -> None:
        self.mode_var.set(state.selection.mode)
        self.quality_var.set(state.selection.quality)
        combo_state = "readonly" if state.selection.quality_options else "disabled"
        self.quality_combo.configure(values=state.selection.quality_options, state=combo_state)

    @staticmethod
    def _queue_label(item: QueueItemSnapshot) -> str:
        title = item.title or item.source_url
        video_count = len(item.probe.video_formats) if item.probe else 0
        audio_count = len(item.probe.audio_formats) if item.probe else 0
        return (
            f"{item.status}/{item.processing_step} | {item.mode} | {item.quality or '-'} | "
            f"{title} [video={video_count}, audio={audio_count}]"
        )

    def _render_details(self, item: QueueItemSnapshot | None) -> None:
        if item is None:
            self.details_var.set("No item selected.")
            return

        base_lines = [
            f"Title: {item.title or 'unknown'}",
            f"URL: {item.source_url}",
            f"Status: {item.status}",
            f"Step: {item.processing_step}",
            f"Detail: {item.status_detail or 'n/a'}",
            f"Mode: {item.mode}",
            f"Quality: {item.quality or 'n/a'}",
            f"Selected format_id: {item.selected_format_id or 'n/a'}",
            f"Output: {item.output_path or 'n/a'}",
            f"Error: {item.error_message or 'n/a'}",
        ]
        if not item.probe:
            self.details_var.set("\n".join([*base_lines, "Metadata: not loaded"]))
            return

        self.details_var.set("\n".join([*base_lines, "", *self._probe_details_lines(item.probe)]))

    @staticmethod
    def _probe_details_lines(probe: ProbeSnapshot) -> list[str]:
        return [
            f"Probe title: {probe.title}",
            f"Channel: {probe.channel or 'unknown'}",
            f"Duration: {AppShell._format_duration(probe.duration)}",
            f"Thumbnail: {probe.thumbnail or 'n/a'}",
            f"Source: {probe.source_url}",
            f"Video qualities: {len(probe.video_formats)}",
            f"Audio qualities: {len(probe.audio_formats)}",
        ]

    @staticmethod
    def _format_duration(duration_seconds: int) -> str:
        if duration_seconds <= 0:
            return "unknown"
        hours, remainder = divmod(duration_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours:02}:{minutes:02}:{seconds:02}"
        return f"{minutes:02}:{seconds:02}"

    @staticmethod
    def _format_resolution(resolution: ToolStatus) -> str:
        if resolution.is_available and resolution.path:
            return f"{resolution.source}: {resolution.path}"
        return "missing"

    def run(self) -> None:
        self.root.mainloop()

    def close(self) -> None:
        if self.root.winfo_exists():
            self.root.destroy()
