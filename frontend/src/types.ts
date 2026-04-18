export type DownloadMode = "video" | "audio";

export type JobStatus = "queued" | "running" | "completed" | "failed" | "cancelled";

export type JobStep =
  | "queued"
  | "preparing"
  | "downloading"
  | "postprocessing"
  | "completed"
  | "failed";

export interface FormatOptionSnapshot {
  format_id: string;
  quality_label: string;
  ext: string;
  note: string;
}

export interface ProbeSnapshot {
  source_url: string;
  title: string;
  channel: string;
  thumbnail: string;
  duration: number;
  video_formats: FormatOptionSnapshot[];
  audio_formats: FormatOptionSnapshot[];
}

export interface QueueItemSnapshot {
  id: string;
  source_url: string;
  title: string;
  mode: DownloadMode;
  quality: string;
  status: JobStatus;
  processing_step: JobStep;
  status_detail: string;
  output_path: string;
  error_message: string;
  selected_format_id: string;
  created_at: string;
  updated_at: string;
  probe: ProbeSnapshot | null;
}

export interface SelectionState {
  selected_item_id: string;
  mode: DownloadMode;
  quality: string;
  selected_format_id: string;
  quality_options: string[];
}

export interface ToolStatus {
  name: string;
  path: string;
  source: string;
  is_available: boolean;
}

export interface RuntimeSnapshot {
  project_root: string;
  runtime_dir: string;
  output_dir: string;
  temp_dir: string;
  state_file: string;
  queue_items_loaded: number;
  ffmpeg: ToolStatus;
  ffprobe: ToolStatus;
}

export interface AppState {
  status_message: string;
  queue: QueueItemSnapshot[];
  selected_item_id: string;
  selected_item: QueueItemSnapshot | null;
  selection: SelectionState;
  runtime: RuntimeSnapshot;
}

export interface BridgeEvent {
  event_id: number;
  event_type: string;
  emitted_at_unix_ms: number;
  state: AppState;
}

export interface BridgeMeta {
  api_version: string;
  event_cursor: number;
  download_active: boolean;
  active_download_item_id: string;
  active_download_count: number;
  active_download_item_ids: string[];
  events_truncated?: boolean;
}

export interface BridgeErrorPayload {
  code: string;
  message: string;
}

export interface BridgeResponse<TData> {
  ok: boolean;
  data: TData;
  error: BridgeErrorPayload | null;
  meta: BridgeMeta;
}

export interface AppStatePayload {
  state: AppState;
}

export interface GetAppStatePayload {
  state_changed: boolean;
  events: BridgeEvent[];
  state?: AppState;
}

export interface RuntimeBridgeInfo {
  api_version: string;
  download_active: boolean;
  active_download_item_id: string;
  active_download_count: number;
  active_download_item_ids: string[];
  active_downloads: Array<{
    item_id: string;
    thread_name: string;
  }>;
  update_model: {
    kind: string;
    state_method: string;
    cursor_arg: string;
    event_shape: string;
    max_retained_events: number;
  };
  command_model: {
    start_download_async: boolean;
    start_all_downloads_async: boolean;
    mutations_blocked_while_downloading: boolean;
    concurrent_downloads: boolean;
  };
  shells: {
    tkinter_fallback: boolean;
    pywebview_bootstrap: boolean;
  };
}

export interface RuntimeInfoPayload {
  runtime: RuntimeSnapshot;
  bridge: RuntimeBridgeInfo;
}

export interface StartDownloadPayload extends AppStatePayload {
  accepted: boolean;
  item_id: string;
}

export interface StartAllDownloadsPayload extends AppStatePayload {
  accepted: boolean;
  started_item_ids: string[];
  queued_item_ids: string[];
}

export interface ClearQueuePayload extends AppStatePayload {
  cleared: boolean;
}

export interface ClipboardTextPayload {
  text: string;
}

export interface OpenOutputDirPayload {
  opened: boolean;
  output_dir: string;
}

export interface InspectOutputPayload {
  output_path: string;
  inspection: Record<string, unknown> | null;
}
