from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from ..config import AppConfig
from ..core import DownloadPipelineError, QueueItemDownloader, YoutubeProbeError, YoutubeProbeService
from ..ffmpeg import MediaToolResolver
from ..models import DownloadMode, FormatOption, ProbeErrorCode, ProbeResult, QueueItem
from ..state_store import QueueStateStore
from .contracts import AppState, QueueItemSnapshot, RuntimeSnapshot, SelectionState, ToolStatus

DEFAULT_STATUS_MESSAGE = "Add a YouTube link to start your queue."

StateListener = Callable[[AppState], None]


@dataclass(slots=True, frozen=True)
class _SelectionComputation:
    selected_quality: str
    selected_format_id: str
    quality_options: tuple[str, ...]
    selected_option: FormatOption | None


class AppController:
    def __init__(
        self,
        config: AppConfig,
        *,
        store: QueueStateStore | None = None,
        tool_resolver: MediaToolResolver | None = None,
        probe_service: YoutubeProbeService | None = None,
        downloader: QueueItemDownloader | None = None,
    ) -> None:
        self.config = config
        self.config.ensure_directories()
        self.store = store or QueueStateStore(config.state_file)
        self.tool_resolver = tool_resolver or MediaToolResolver(config)
        self.probe_service = probe_service or YoutubeProbeService()
        self.downloader = downloader or QueueItemDownloader(config, self.tool_resolver)
        self._listeners: list[StateListener] = []
        self._items: list[QueueItem] = []
        self._selected_item_id: str | None = None
        self._current_mode = DownloadMode.VIDEO
        self._current_quality = ""
        self._session_output_dir = config.output_dir
        self._status_message = DEFAULT_STATUS_MESSAGE
        self.load_queue_state()

    def subscribe(self, listener: StateListener) -> None:
        self._listeners.append(listener)

    def get_state(self) -> AppState:
        return self._build_state()

    def get_runtime_snapshot(self) -> RuntimeSnapshot:
        return self._build_runtime_snapshot()

    def probe_url(self, url: str) -> ProbeResult:
        return self.probe_service.probe(url)

    def inspect_output(self, media_path: Path) -> dict[str, object] | None:
        return self.downloader.inspect_output(media_path)

    def load_queue_state(self) -> AppState:
        persisted_state = self.store.load()
        self._items = persisted_state.items
        self._selected_item_id = persisted_state.selected_item_id
        selected_item, did_normalize = self._restore_selected_item_state()

        if selected_item is not None:
            self._status_message = "Queue restored. Select an item or start the download."
        else:
            self._current_quality = ""
            self._status_message = DEFAULT_STATUS_MESSAGE

        if did_normalize or persisted_state.selected_item_id != self._selected_item_id:
            self.store.save(self._items, selected_item_id=self._selected_item_id)
        return self._emit_state()

    def save_queue_state(
        self,
        items: Sequence[QueueItem] | None = None,
        *,
        selected_item_id: str | None = None,
    ) -> AppState:
        if items is not None:
            self._items = list(items)
        if selected_item_id is not None:
            self._selected_item_id = selected_item_id
        self._restore_selected_item_state()
        self.store.save(self._items, selected_item_id=self._selected_item_id)
        return self._emit_state()

    def add_url(self, url: str) -> AppState:
        normalized = url.strip()
        if not normalized:
            self._status_message = "Add a YouTube link to continue."
            return self._emit_state()

        try:
            probe = self.probe_url(normalized)
            selected_option = self._first_option_for_mode(probe, self._current_mode)
        except YoutubeProbeError as error:
            self._status_message = f"Probe failed ({error.code.value}): {error}"
            self._emit_state()
            raise

        item = QueueItem(
            source_url=probe.source_url,
            title=probe.title,
            mode=self._current_mode,
            quality=selected_option.quality_label,
            probe=probe,
            selected_format_id=selected_option.format_id,
        )
        self._items.append(item)
        self._selected_item_id = item.id
        self._current_mode = item.mode
        self._current_quality = item.quality
        self._status_message = f"Ready to download {item.title}."
        return self.save_queue_state(selected_item_id=item.id)

    def select_item(self, item_id: str | None) -> AppState:
        previous_selected_item_id = self._selected_item_id
        item = self._find_item(item_id) if item_id else None
        self._selected_item_id = item.id if item else None
        if item is not None:
            self._current_mode = item.mode
            selection = self._compute_selection(
                item=item,
                mode=item.mode,
                preferred_quality=item.quality,
                preferred_format_id=item.selected_format_id,
            )
            self._current_quality = selection.selected_quality
            did_change = self._apply_selection_to_item(
                item=item,
                mode=self._current_mode,
                selection=selection,
            )
            self._status_message = f"Selected {item.title or item.source_url}."
            if did_change or previous_selected_item_id != self._selected_item_id:
                return self.save_queue_state(selected_item_id=item.id)
        else:
            self._current_quality = ""
            self._status_message = DEFAULT_STATUS_MESSAGE
            if previous_selected_item_id is not None:
                return self.save_queue_state(selected_item_id=None)
        return self._emit_state()

    def select_mode(self, mode: DownloadMode | str) -> AppState:
        self._current_mode = DownloadMode(mode)
        item = self._selected_item()
        if item is None or item.probe is None:
            return self._emit_state()

        selection = self._compute_selection(
            item=item,
            mode=self._current_mode,
            preferred_quality=item.quality,
            preferred_format_id=item.selected_format_id,
        )
        self._current_quality = selection.selected_quality
        if not selection.quality_options or selection.selected_option is None:
            self._status_message = f"No {self._current_mode.value} options are available for {item.title}."
            return self._emit_state()

        changed = (
            item.mode != self._current_mode
            or item.quality != selection.selected_quality
            or item.selected_format_id != selection.selected_format_id
        )
        if not changed:
            return self._emit_state()

        item.mode = self._current_mode
        item.quality = selection.selected_quality
        item.selected_format_id = selection.selected_format_id
        item.touch()
        self._status_message = f"Download option updated for {item.title}."
        return self.save_queue_state(selected_item_id=item.id)

    def select_quality(self, quality: str) -> AppState:
        item = self._selected_item()
        if item is None or item.probe is None:
            return self._emit_state()

        selection = self._compute_selection(
            item=item,
            mode=self._current_mode,
            preferred_quality=quality,
            preferred_format_id="",
        )
        self._current_quality = selection.selected_quality
        if not selection.quality_options or selection.selected_option is None:
            return self._emit_state()

        changed = (
            item.mode != self._current_mode
            or item.quality != selection.selected_quality
            or item.selected_format_id != selection.selected_format_id
        )
        if not changed:
            return self._emit_state()

        item.mode = self._current_mode
        item.quality = selection.selected_quality
        item.selected_format_id = selection.selected_format_id
        item.touch()
        self._status_message = f"Download option updated for {item.title}."
        return self.save_queue_state(selected_item_id=item.id)

    def set_output_dir(self, output_dir: Path | str) -> AppState:
        resolved_output_dir = Path(output_dir).expanduser().resolve()
        resolved_output_dir.mkdir(parents=True, exist_ok=True)
        self._session_output_dir = resolved_output_dir
        self._status_message = f"Downloads will be saved to {resolved_output_dir}."
        return self._emit_state()

    def start_download(self, item_id: str | None = None) -> AppState:
        item = self._find_item(item_id) if item_id else self._selected_item()
        if item is None:
            self._status_message = "Choose an item before starting the download."
            return self._emit_state()

        self._selected_item_id = item.id
        self._status_message = f"Starting download for {item.title or item.source_url}."
        self._emit_state()
        try:
            output_path = self.downloader.execute(
                item,
                on_update=self._handle_pipeline_update,
                output_dir=self._session_output_dir,
            )
        except DownloadPipelineError:
            self._status_message = item.error_message or "Download failed."
            self.save_queue_state(selected_item_id=item.id)
            raise

        self._status_message = f"Download finished. Saved to {output_path.name}."
        return self.save_queue_state(selected_item_id=item.id)

    def _handle_pipeline_update(self, item: QueueItem) -> None:
        self._selected_item_id = item.id
        self.save_queue_state(selected_item_id=item.id)

    def _build_state(self) -> AppState:
        selected_item = self._selected_item()
        selection = self._compute_selection(
            item=selected_item,
            mode=self._current_mode,
            preferred_quality=self._current_quality,
            preferred_format_id=selected_item.selected_format_id if selected_item else "",
        )
        return AppState(
            status_message=self._status_message,
            queue=tuple(QueueItemSnapshot.from_item(item) for item in self._items),
            selected_item_id=self._selected_item_id or "",
            selected_item=QueueItemSnapshot.from_item(selected_item) if selected_item else None,
            selection=SelectionState(
                selected_item_id=self._selected_item_id or "",
                mode=self._current_mode.value,
                quality=selection.selected_quality,
                selected_format_id=selection.selected_format_id,
                quality_options=selection.quality_options,
            ),
            runtime=self._build_runtime_snapshot(),
        )

    def _build_runtime_snapshot(self) -> RuntimeSnapshot:
        return RuntimeSnapshot(
            project_root=str(self.config.project_root),
            runtime_dir=str(self.config.runtime_dir),
            output_dir=str(self._session_output_dir),
            temp_dir=str(self.config.temp_dir),
            state_file=str(self.config.state_file),
            queue_items_loaded=len(self._items),
            ffmpeg=ToolStatus.from_resolution(self.tool_resolver.resolve_ffmpeg()),
            ffprobe=ToolStatus.from_resolution(self.tool_resolver.resolve_ffprobe()),
        )

    def _compute_selection(
        self,
        *,
        item: QueueItem | None,
        mode: DownloadMode,
        preferred_quality: str,
        preferred_format_id: str,
    ) -> _SelectionComputation:
        if item is None or item.probe is None:
            return _SelectionComputation(
                selected_quality="",
                selected_format_id="",
                quality_options=(),
                selected_option=None,
            )

        options = item.probe.options_for_mode(mode)
        if not options:
            return _SelectionComputation(
                selected_quality="",
                selected_format_id="",
                quality_options=(),
                selected_option=None,
            )

        quality_options = tuple(option.quality_label for option in options)
        selected_option = self._find_option_by_format_id(options, preferred_format_id)
        if selected_option is None:
            selected_option = next(
                (option for option in options if option.quality_label == preferred_quality),
                None,
            )
        if selected_option is None:
            selected_option = self._find_option_by_format_id(options, item.selected_format_id)
        if selected_option is None:
            fallback_quality = item.quality if item.quality in quality_options else quality_options[0]
            selected_option = next(
                option for option in options if option.quality_label == fallback_quality
            )

        return _SelectionComputation(
            selected_quality=selected_option.quality_label,
            selected_format_id=selected_option.format_id,
            quality_options=quality_options,
            selected_option=selected_option,
        )

    def _restore_selected_item_state(self) -> tuple[QueueItem | None, bool]:
        selected_item = self._selected_item()
        if selected_item is None and self._items:
            selected_item = self._items[0]
            self._selected_item_id = selected_item.id
        elif selected_item is None:
            self._selected_item_id = None
            self._current_quality = ""
            return None, False

        self._current_mode = selected_item.mode
        selection = self._compute_selection(
            item=selected_item,
            mode=self._current_mode,
            preferred_quality=selected_item.quality,
            preferred_format_id=selected_item.selected_format_id,
        )
        self._current_quality = selection.selected_quality
        did_change = self._apply_selection_to_item(
            item=selected_item,
            mode=self._current_mode,
            selection=selection,
        )
        return selected_item, did_change

    @staticmethod
    def _apply_selection_to_item(
        *,
        item: QueueItem,
        mode: DownloadMode,
        selection: _SelectionComputation,
    ) -> bool:
        if selection.selected_option is None:
            return False

        did_change = (
            item.mode != mode
            or item.quality != selection.selected_quality
            or item.selected_format_id != selection.selected_format_id
        )
        if not did_change:
            return False

        item.mode = mode
        item.quality = selection.selected_quality
        item.selected_format_id = selection.selected_format_id
        item.touch()
        return True

    @staticmethod
    def _find_option_by_format_id(
        options: Sequence[FormatOption],
        format_id: str,
    ) -> FormatOption | None:
        if not format_id:
            return None
        return next((option for option in options if option.format_id == format_id), None)

    def _selected_item(self) -> QueueItem | None:
        return self._find_item(self._selected_item_id)

    def _find_item(self, item_id: str | None) -> QueueItem | None:
        if not item_id:
            return None
        for item in self._items:
            if item.id == item_id:
                return item
        return None

    def _emit_state(self) -> AppState:
        state = self._build_state()
        for listener in list(self._listeners):
            listener(state)
        return state

    @staticmethod
    def _first_option_for_mode(probe: ProbeResult, mode: DownloadMode) -> FormatOption:
        options = probe.options_for_mode(mode)
        if not options:
            raise YoutubeProbeError(
                code=ProbeErrorCode.UNAVAILABLE,
                message=f"No {mode.value} quality options are available for the video.",
            )
        return options[0]
