import type {
  AppStatePayload,
  BridgeResponse,
  ClearQueuePayload,
  GetAppStatePayload,
  InspectOutputPayload,
  RuntimeInfoPayload,
  StartAllDownloadsPayload,
  StartDownloadPayload,
} from "./types";

const PYWEBVIEW_READY_EVENT = "pywebviewready";
const BRIDGE_READY_TIMEOUT_MS = 10000;

type BridgeMethodName =
  | "get_app_state"
  | "add_url"
  | "read_clipboard_text"
  | "select_item"
  | "select_mode"
  | "select_quality"
  | "clear_queue"
  | "pick_output_dir"
  | "open_output_dir"
  | "start_download"
  | "start_all_downloads"
  | "get_runtime_info"
  | "inspect_output";

export interface AppBridgeApiSurface {
  get_app_state(payload?: { since_event_id?: number } | number | string): Promise<unknown>;
  add_url(payload?: { url: string } | string): Promise<unknown>;
  read_clipboard_text(): Promise<unknown>;
  select_item(payload?: { item_id?: string } | string): Promise<unknown>;
  select_mode(payload?: { mode: "video" | "audio" } | string): Promise<unknown>;
  select_quality(payload?: { quality: string } | string): Promise<unknown>;
  clear_queue(): Promise<unknown>;
  pick_output_dir(): Promise<unknown>;
  open_output_dir(): Promise<unknown>;
  start_download(payload?: { item_id?: string } | string): Promise<unknown>;
  start_all_downloads(): Promise<unknown>;
  get_runtime_info(): Promise<unknown>;
  inspect_output(payload?: { output_path?: string } | string): Promise<unknown>;
}

export class BridgeClientError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "BridgeClientError";
  }
}

class BridgeClient {
  async waitUntilReady(timeoutMs = BRIDGE_READY_TIMEOUT_MS): Promise<void> {
    await this.resolveApi(timeoutMs);
  }

  getAppState(payload?: { since_event_id?: number } | number | string) {
    return this.call<GetAppStatePayload>("get_app_state", payload);
  }

  addUrl(url: string) {
    return this.call<AppStatePayload>("add_url", { url });
  }

  readClipboardText() {
    return this.call<{ text: string }>("read_clipboard_text");
  }

  selectItem(itemId: string) {
    return this.call<AppStatePayload>("select_item", { item_id: itemId });
  }

  selectMode(mode: "video" | "audio") {
    return this.call<AppStatePayload>("select_mode", { mode });
  }

  selectQuality(quality: string) {
    return this.call<AppStatePayload>("select_quality", { quality });
  }

  clearQueue() {
    return this.call<ClearQueuePayload>("clear_queue");
  }

  pickOutputDir() {
    return this.call<AppStatePayload>("pick_output_dir");
  }

  openOutputDir() {
    return this.call<{ opened: boolean; output_dir: string }>("open_output_dir");
  }

  startDownload(itemId?: string) {
    return this.call<StartDownloadPayload>(
      "start_download",
      itemId ? { item_id: itemId } : undefined,
    );
  }

  startAllDownloads() {
    return this.call<StartAllDownloadsPayload>("start_all_downloads");
  }

  getRuntimeInfo() {
    return this.call<RuntimeInfoPayload>("get_runtime_info");
  }

  inspectOutput(outputPath?: string) {
    return this.call<InspectOutputPayload>(
      "inspect_output",
      outputPath ? { output_path: outputPath } : undefined,
    );
  }

  private async call<TData>(
    methodName: BridgeMethodName,
    payload?: unknown,
  ): Promise<BridgeResponse<TData>> {
    const api = await this.resolveApi();
    const method = api[methodName] as (payload?: unknown) => Promise<unknown>;
    if (typeof method !== "function") {
      throw new BridgeClientError(
        `Bridge method ${methodName} is not exposed by pywebview.`,
      );
    }

    return method(payload) as Promise<BridgeResponse<TData>>;
  }

  private async resolveApi(
    timeoutMs = BRIDGE_READY_TIMEOUT_MS,
  ): Promise<AppBridgeApiSurface> {
    if (window.pywebview?.api) {
      return window.pywebview.api;
    }

    return new Promise<AppBridgeApiSurface>((resolve, reject) => {
      const timeoutId = window.setTimeout(() => {
        cleanup();
        reject(
          new BridgeClientError(
            "pywebview bridge API is not ready. Start the UI through `poetry run python main.py --ui-shell bridge` or use `--bridge-start-url` for the Vite dev server.",
          ),
        );
      }, timeoutMs);

      const intervalId = window.setInterval(() => {
        if (window.pywebview?.api) {
          cleanup();
          resolve(window.pywebview.api);
        }
      }, 50);

      const onReady = () => {
        if (window.pywebview?.api) {
          cleanup();
          resolve(window.pywebview.api);
        }
      };

      const cleanup = () => {
        window.clearTimeout(timeoutId);
        window.clearInterval(intervalId);
        window.removeEventListener(PYWEBVIEW_READY_EVENT, onReady);
      };

      window.addEventListener(PYWEBVIEW_READY_EVENT, onReady);
    });
  }
}

export const bridgeClient = new BridgeClient();
