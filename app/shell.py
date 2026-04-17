from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .config import AppConfig
from .core import DownloadPipelineError, QueueItemDownloader, YoutubeProbeError, YoutubeProbeService
from .ffmpeg import MediaToolResolver
from .models import DownloadMode, FormatOption, ProbeErrorCode, ProbeResult, QueueItem
from .state_store import QueueStateStore


class AppShell:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.config.ensure_directories()
        self.store = QueueStateStore(config.state_file)
        self.items = self.store.load()
        self.tool_resolver = MediaToolResolver(config)
        self.probe_service = YoutubeProbeService()
        self.downloader = QueueItemDownloader(config, self.tool_resolver)
        self.ffmpeg = self.tool_resolver.resolve_ffmpeg()
        self.ffprobe = self.tool_resolver.resolve_ffprobe()
        self.root = tk.Tk()
        self.root.title("YT Downloader v1")
        self.root.geometry("980x700")
        self.root.minsize(880, 620)
        self.url_var = tk.StringVar()
        self.mode_var = tk.StringVar(value=DownloadMode.VIDEO.value)
        self.quality_var = tk.StringVar()
        self.status_var = tk.StringVar(
            value="Enter a YouTube URL to preload metadata and quality options."
        )
        self.details_var = tk.StringVar(value="No item selected.")
        self.paths_text = tk.StringVar()
        self.tools_text = tk.StringVar()
        self._build_ui()
        self._populate_runtime_info()

        if self.items:
            self._select_item_by_id(self.items[0].id)

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
            values=(DownloadMode.VIDEO.value, DownloadMode.AUDIO.value),
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

    def _populate_runtime_info(self) -> None:
        self.paths_text.set(
            "\n".join(
                [
                    f"Project root: {self.config.project_root}",
                    f"Runtime dir: {self.config.runtime_dir}",
                    f"Output dir: {self.config.output_dir}",
                    f"Temp dir: {self.config.temp_dir}",
                    f"Queue state: {self.config.state_file}",
                ]
            )
        )
        self._update_tools_text()
        self._refresh_queue_list()

    def _update_tools_text(self) -> None:
        self.tools_text.set(
            "\n".join(
                [
                    f"ffmpeg: {self._format_resolution(self.ffmpeg)}",
                    f"ffprobe: {self._format_resolution(self.ffprobe)}",
                    "",
                    f"Queue items loaded: {len(self.items)}",
                ]
            )
        )

    def _refresh_queue_list(self, select_id: str | None = None) -> None:
        self.queue_list.delete(0, tk.END)
        if not self.items:
            self.queue_list.insert(tk.END, "Queue is empty.")
            return

        for item in self.items:
            self.queue_list.insert(tk.END, self._queue_label(item))

        if select_id:
            self._select_item_by_id(select_id)

    @staticmethod
    def _queue_label(item: QueueItem) -> str:
        title = item.title or item.source_url
        video_count = len(item.probe.video_formats) if item.probe else 0
        audio_count = len(item.probe.audio_formats) if item.probe else 0
        return (
            f"{item.status}/{item.processing_step} | {item.mode} | {item.quality or '-'} | "
            f"{title} [video={video_count}, audio={audio_count}]"
        )

    def _handle_add_url(self, _event: object | None = None) -> None:
        url = self.url_var.get().strip()
        if not url:
            self.status_var.set("Probe skipped: the URL field is empty.")
            return

        try:
            item = self.enqueue_url(url)
        except YoutubeProbeError as error:
            self.status_var.set(f"Probe failed ({error.code.value}): {error}")
            self.details_var.set("No metadata loaded for the requested URL.")
            self.quality_var.set("")
            self.quality_combo.configure(values=(), state="disabled")
            return

        self.url_var.set("")
        self.status_var.set(
            "Metadata loaded without download: "
            f"{item.title} | video qualities={len(item.probe.video_formats) if item.probe else 0} "
            f"| audio qualities={len(item.probe.audio_formats) if item.probe else 0}"
        )
        self._select_item_by_id(item.id)

    def enqueue_url(self, url: str) -> QueueItem:
        mode = DownloadMode(self.mode_var.get())
        probe = self.probe_service.probe(url)
        selected_option = self._first_option_for_mode(probe, mode)

        item = QueueItem(
            source_url=probe.source_url,
            title=probe.title,
            mode=mode,
            quality=selected_option.quality_label,
            probe=probe,
            selected_format_id=selected_option.format_id,
        )
        self.items.append(item)
        self._save_items(select_id=item.id)
        return item

    def smoke_add_url(self, url: str) -> dict[str, object]:
        item = self.enqueue_url(url)
        self.root.update_idletasks()
        self.root.update()
        return {
            "item_id": item.id,
            "title": item.title,
            "selected_quality": self.quality_var.get(),
            "selected_format_id": item.selected_format_id,
            "quality_values": list(self.quality_combo.cget("values")),
            "video_options": len(item.probe.video_formats) if item.probe else 0,
            "audio_options": len(item.probe.audio_formats) if item.probe else 0,
        }

    def _handle_queue_select(self, _event: object | None = None) -> None:
        item = self._selected_item()
        if not item:
            return

        self.mode_var.set(item.mode.value)
        self._sync_item_selection(item, preferred_quality=item.quality, persist=False)
        self._update_details(item)

    def _handle_mode_change(self, _event: object | None = None) -> None:
        item = self._selected_item()
        if not item or not item.probe:
            return

        changed = self._sync_item_selection(item, preferred_quality=item.quality, persist=True)
        if changed:
            self.status_var.set(
                f"Selection updated for {item.title}: mode={item.mode.value}, quality={item.quality}"
            )

    def _handle_quality_change(self, _event: object | None = None) -> None:
        item = self._selected_item()
        if not item or not item.probe:
            return

        changed = self._sync_item_selection(
            item,
            preferred_quality=self.quality_var.get(),
            persist=True,
        )
        if changed:
            self.status_var.set(
                f"Selection updated for {item.title}: mode={item.mode.value}, quality={item.quality}"
            )

    def _handle_download_selected(self) -> None:
        item = self._selected_item()
        if not item:
            self.status_var.set("Download skipped: no queue item is selected.")
            return

        self.status_var.set(f"Running download pipeline for {item.title or item.source_url}.")
        self.root.update_idletasks()
        try:
            output_path = self.downloader.execute(item, on_update=self._handle_pipeline_update)
        except DownloadPipelineError:
            self.status_var.set(f"Download failed: {item.error_message or 'unknown pipeline error'}")
        else:
            self.status_var.set(f"Download completed: {output_path}")
        finally:
            self._save_items(select_id=item.id)
            self._update_details(item)

    def _handle_pipeline_update(self, item: QueueItem) -> None:
        self.ffmpeg = self.tool_resolver.resolve_ffmpeg()
        self.ffprobe = self.tool_resolver.resolve_ffprobe()
        self._save_items(select_id=item.id)
        self._update_details(item)
        self.root.update_idletasks()

    def _sync_item_selection(
        self,
        item: QueueItem,
        preferred_quality: str = "",
        persist: bool = False,
    ) -> bool:
        if not item.probe:
            self.quality_var.set("")
            self.quality_combo.configure(values=(), state="disabled")
            return False

        mode = DownloadMode(self.mode_var.get())
        options = item.probe.options_for_mode(mode)
        if not options:
            self.quality_var.set("")
            self.quality_combo.configure(values=(), state="disabled")
            if persist:
                self.status_var.set(f"No {mode.value} qualities are available for {item.title}.")
            return False

        values = tuple(option.quality_label for option in options)
        self.quality_combo.configure(values=values, state="readonly")

        selected_quality = preferred_quality if preferred_quality in values else values[0]
        selected_option = next(
            option for option in options if option.quality_label == selected_quality
        )
        self.quality_var.set(selected_quality)

        changed = (
            item.mode != mode
            or item.quality != selected_quality
            or item.selected_format_id != selected_option.format_id
        )
        if changed:
            item.mode = mode
            item.quality = selected_quality
            item.selected_format_id = selected_option.format_id
            item.touch()
            if persist:
                self._save_items(select_id=item.id)

        return changed

    def _update_details(self, item: QueueItem) -> None:
        base_lines = [
            f"Title: {item.title or 'unknown'}",
            f"URL: {item.source_url}",
            f"Status: {item.status.value}",
            f"Step: {item.processing_step.value}",
            f"Detail: {item.status_detail or 'n/a'}",
            f"Mode: {item.mode.value}",
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
    def _probe_details_lines(probe: ProbeResult) -> list[str]:
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

    def _save_items(self, select_id: str | None = None) -> None:
        self.store.save(self.items)
        self._update_tools_text()
        self._refresh_queue_list(select_id=select_id)

    def _selected_item(self) -> QueueItem | None:
        if not self.items:
            return None

        selection = self.queue_list.curselection()
        if not selection:
            return None

        index = selection[0]
        if index >= len(self.items):
            return None
        return self.items[index]

    def _select_item_by_id(self, item_id: str) -> None:
        for index, item in enumerate(self.items):
            if item.id != item_id:
                continue
            self.queue_list.selection_clear(0, tk.END)
            self.queue_list.selection_set(index)
            self.queue_list.activate(index)
            self.queue_list.see(index)
            self.mode_var.set(item.mode.value)
            self._sync_item_selection(item, preferred_quality=item.quality, persist=False)
            self._update_details(item)
            return

    @staticmethod
    def _first_option_for_mode(probe: ProbeResult, mode: DownloadMode) -> FormatOption:
        options = probe.options_for_mode(mode)
        if not options:
            raise YoutubeProbeError(
                code=ProbeErrorCode.UNAVAILABLE,
                message=f"No {mode.value} quality options are available for the video.",
            )
        return options[0]

    @staticmethod
    def _format_resolution(resolution: object) -> str:
        binary = resolution
        if getattr(binary, "path", None):
            return f"{binary.source}: {binary.path}"
        return "missing"

    def run(self) -> None:
        self.root.mainloop()

    def close(self) -> None:
        if self.root.winfo_exists():
            self.root.destroy()
