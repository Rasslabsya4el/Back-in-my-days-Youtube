import type {
  AppStatePayload,
  BridgeResponse,
  GetAppStatePayload,
  InspectOutputPayload,
  RuntimeInfoPayload,
  StartDownloadPayload,
} from "./types";

const PYWEBVIEW_READY_EVENT = "pywebviewready";
const BRIDGE_READY_TIMEOUT_MS = 10000;

type BridgeMethodName =
  | "get_app_state"
  | "add_url"
  | "select_item"
  | "select_mode"
  | "select_quality"
  | "start_download"
  | "get_runtime_info"
  | "inspect_output";

export interface AppBridgeApiSurface {
  get_app_state(payload?: { since_event_id?: number } | number | string): Promise<unknown>;
  add_url(payload?: { url: string } | string): Promise<unknown>;
  select_item(payload?: { item_id?: string } | string): Promise<unknown>;
  select_mode(payload?: { mode: "video" | "audio" } | string): Promise<unknown>;
  select_quality(payload?: { quality: string } | string): Promise<unknown>;
  start_download(payload?: { item_id?: string } | string): Promise<unknown>;
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

  selectItem(itemId: string) {
    return this.call<AppStatePayload>("select_item", { item_id: itemId });
  }

  selectMode(mode: "video" | "audio") {
    return this.call<AppStatePayload>("select_mode", { mode });
  }

  selectQuality(quality: string) {
    return this.call<AppStatePayload>("select_quality", { quality });
  }

  startDownload(itemId?: string) {
    return this.call<StartDownloadPayload>(
      "start_download",
      itemId ? { item_id: itemId } : undefined,
    );
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
