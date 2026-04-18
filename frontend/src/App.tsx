import { startTransition, useEffect, useEffectEvent, useRef, useState } from "react";

import { BridgeClientError, bridgeClient } from "./bridge";
import { VariantC } from "./components/VariantC";
import type { VariantProps } from "./components/variant-types";
import type {
  AppState,
  BridgeMeta,
  BridgeResponse,
  DownloadMode,
  GetAppStatePayload,
} from "./types";
import {
  buildFormatSelectionModel,
  buildUnifiedStatus,
  compactPath,
  pickFriendlyFormatOption,
  summarizeQueue,
} from "./view-model";

import "./styles.css";

type ConnectionState = "connecting" | "ready" | "error";

const POLL_INTERVAL_MS = 1500;

function App() {
  const [urlInput, setUrlInput] = useState("");
  const [connectionState, setConnectionState] = useState<ConnectionState>("connecting");
  const [appState, setAppState] = useState<AppState | null>(null);
  const [bridgeMeta, setBridgeMeta] = useState<BridgeMeta | null>(null);
  const [bridgeError, setBridgeError] = useState("");
  const [mutationBusy, setMutationBusy] = useState(false);

  const isMountedRef = useRef(true);
  const cursorRef = useRef(0);
  const pollInFlightRef = useRef(false);
  const documentHiddenRef = useRef(typeof document !== "undefined" ? document.hidden : false);

  const queue = appState?.queue ?? [];
  const selectedItem = appState?.selected_item ?? null;
  const selection = appState?.selection ?? null;
  const currentMode = selection?.mode ?? selectedItem?.mode ?? "video";
  const formatModel = buildFormatSelectionModel(selectedItem, currentMode, selection);
  const selectedFormatOption = formatModel.activeOption;
  const outputDir = appState?.runtime.output_dir ?? "";
  const progress = summarizeQueue(queue);
  const queuedItemCount = queue.filter((item) => item.status === "queued").length;
  const activeDownloadCount =
    bridgeMeta?.active_download_count ?? queue.filter((item) => item.status === "running").length;
  const downloadActive =
    activeDownloadCount > 0 || queue.some((item) => item.status === "running");
  const shellReady = connectionState === "ready";
  const controlsDisabled = mutationBusy || !shellReady;
  const selectionDisabled = !shellReady;
  const commandDisabled = mutationBusy || !shellReady;
  const openOutputDisabled = !shellReady || !outputDir;
  const clearQueueDisabled = mutationBusy || !shellReady || !queue.length || downloadActive;
  const clearQueueReason = downloadActive
    ? "Finish active downloads before clearing the queue."
    : queue.length
      ? "Remove every item from the current queue."
      : "Queue is already empty.";
  const selectedStatus = buildUnifiedStatus(selectedItem, bridgeError);

  const applyStatePayload = useEffectEvent(
    (response: BridgeResponse<GetAppStatePayload> | BridgeResponse<{ state: AppState }>) => {
      if (response.meta.event_cursor < cursorRef.current) {
        return;
      }

      if (!response.ok) {
        setBridgeError(response.error?.message ?? "Bridge request failed.");
        return;
      }

      cursorRef.current = response.meta.event_cursor;
      const nextState = "state" in response.data ? response.data.state ?? null : null;

      startTransition(() => {
        setBridgeMeta(response.meta);
        setConnectionState("ready");
        setBridgeError("");
        if (nextState) {
          setAppState(nextState);
        }
      });
    },
  );

  const pollAppState = useEffectEvent(async (sinceEventId?: number) => {
    if (pollInFlightRef.current) {
      return;
    }

    pollInFlightRef.current = true;
    try {
      const response = await bridgeClient.getAppState({
        since_event_id: sinceEventId ?? cursorRef.current,
      });
      if (!isMountedRef.current) {
        return;
      }
      applyStatePayload(response);
    } catch (error) {
      if (!isMountedRef.current) {
        return;
      }
      setConnectionState("error");
      setBridgeError(formatError(error));
    } finally {
      pollInFlightRef.current = false;
    }
  });

  const bootstrap = useEffectEvent(async () => {
    try {
      await bridgeClient.waitUntilReady();
      if (!isMountedRef.current) {
        return;
      }
      await pollAppState(0);
    } catch (error) {
      if (!isMountedRef.current) {
        return;
      }
      setConnectionState("error");
      setBridgeError(formatError(error));
    }
  });

  useEffect(() => {
    isMountedRef.current = true;
    void bootstrap();

    return () => {
      isMountedRef.current = false;
    };
  }, [bootstrap]);

  useEffect(() => {
    const handleVisibilityChange = () => {
      documentHiddenRef.current = document.hidden;
      if (!document.hidden && connectionState === "ready") {
        void pollAppState(cursorRef.current);
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [connectionState, pollAppState]);

  useEffect(() => {
    if (connectionState !== "ready" || documentHiddenRef.current) {
      return;
    }

    const intervalId = window.setInterval(() => {
      if (!document.hidden) {
        void pollAppState(cursorRef.current);
      }
    }, POLL_INTERVAL_MS);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [connectionState, pollAppState]);

  async function runStateCommand(
    command: Promise<BridgeResponse<{ state: AppState }>>,
    options?: { resetUrl?: boolean; trackBusy?: boolean },
  ) {
    const trackBusy = options?.trackBusy ?? true;
    if (trackBusy) {
      setMutationBusy(true);
    }
    try {
      const response = await command;
      if (!isMountedRef.current) {
        return;
      }
      applyStatePayload(response);
      if (options?.resetUrl && response.ok) {
        setUrlInput("");
      }
    } catch (error) {
      if (!isMountedRef.current) {
        return;
      }
      setBridgeError(formatError(error));
    } finally {
      if (trackBusy && isMountedRef.current) {
        setMutationBusy(false);
      }
    }
  }

  async function handleAddUrl(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = urlInput.trim();
    if (!normalized || commandDisabled) {
      return;
    }
    await runStateCommand(bridgeClient.addUrl(normalized), {
      resetUrl: true,
    });
  }

  async function handleModeChange(mode: DownloadMode) {
    if (mode === selection?.mode || commandDisabled) {
      return;
    }
    await runStateCommand(bridgeClient.selectMode(mode));
  }

  async function handleQualityChange(event: React.ChangeEvent<HTMLSelectElement>) {
    if (commandDisabled) {
      return;
    }
    const nextOption = pickFriendlyFormatOption(formatModel.options, {
      fileFormatValue: selectedFormatOption?.fileFormatValue ?? "",
      qualityValue: event.target.value,
    });
    if (!nextOption || nextOption.option.quality_label === selection?.quality) {
      return;
    }
    await runStateCommand(bridgeClient.selectQuality(nextOption.option.quality_label));
  }

  async function handleFileFormatChange(event: React.ChangeEvent<HTMLSelectElement>) {
    if (commandDisabled) {
      return;
    }
    const nextOption = pickFriendlyFormatOption(formatModel.options, {
      fileFormatValue: event.target.value,
      qualityValue: selectedFormatOption?.qualityValue ?? "",
    });
    if (!nextOption || nextOption.option.quality_label === selection?.quality) {
      return;
    }
    await runStateCommand(bridgeClient.selectQuality(nextOption.option.quality_label));
  }

  async function handleSelectItem(itemId: string) {
    if (itemId === appState?.selected_item_id || selectionDisabled) {
      return;
    }
    await runStateCommand(bridgeClient.selectItem(itemId), {
      trackBusy: false,
    });
  }

  async function handleStartDownload() {
    if (!selectedItem || commandDisabled || selectedItem.status === "running") {
      return;
    }

    setMutationBusy(true);
    try {
      const response = await bridgeClient.startDownload(selectedItem.id);
      if (!isMountedRef.current) {
        return;
      }
      if (!response.ok) {
        setBridgeError(response.error?.message ?? "Download start failed.");
        return;
      }
      applyStatePayload(response);
    } catch (error) {
      if (isMountedRef.current) {
        setBridgeError(formatError(error));
      }
    } finally {
      if (isMountedRef.current) {
        setMutationBusy(false);
      }
    }
  }

  async function handleStartAllDownloads() {
    if (!queuedItemCount || commandDisabled) {
      return;
    }

    setMutationBusy(true);
    try {
      const response = await bridgeClient.startAllDownloads();
      if (!isMountedRef.current) {
        return;
      }
      if (!response.ok) {
        setBridgeError(response.error?.message ?? "Queue start failed.");
        return;
      }
      applyStatePayload(response);
    } catch (error) {
      if (isMountedRef.current) {
        setBridgeError(formatError(error));
      }
    } finally {
      if (isMountedRef.current) {
        setMutationBusy(false);
      }
    }
  }

  async function handlePickOutputDir() {
    if (commandDisabled) {
      return;
    }
    await runStateCommand(bridgeClient.pickOutputDir());
  }

  async function handleOpenOutputDir() {
    if (openOutputDisabled) {
      return;
    }

    try {
      const response = await bridgeClient.openOutputDir();
      if (!isMountedRef.current) {
        return;
      }
      if (!response.ok) {
        setBridgeError(response.error?.message ?? "Output folder could not be opened.");
        return;
      }
      setBridgeError("");
    } catch (error) {
      if (isMountedRef.current) {
        setBridgeError(formatError(error));
      }
    }
  }

  async function handleClearQueue() {
    if (clearQueueDisabled) {
      return;
    }
    await runStateCommand(bridgeClient.clearQueue());
  }

  const variantProps: VariantProps = {
    appState,
    queue,
    selectedItem,
    selectedItemId: appState?.selected_item_id ?? "",
    currentMode,
    formatModel,
    selectedFormatOption,
    controlsDisabled,
    selectionDisabled,
    onSelectItem: (id) => void handleSelectItem(id),
    onModeChange: (mode) => void handleModeChange(mode),
    onQualityChange: (event) => void handleQualityChange(event),
    onFileFormatChange: (event) => void handleFileFormatChange(event),
    onStart: () => void handleStartDownload(),
    onStartAll: () => void handleStartAllDownloads(),
    onClearQueue: () => void handleClearQueue(),
    queuedItemCount,
    clearQueueDisabled,
    clearQueueReason,
    selectedStatus,
    buildItemStatus: (item) => buildUnifiedStatus(item, ""),
    queueSummary: formatQueueSummary(progress),
  };

  return (
    <div className="app-root">
      <header className="topbar" data-testid="topbar">
        <form className="url-form" data-testid="url-form" onSubmit={handleAddUrl}>
          <div className="url-input-shell">
            <input
              aria-label="YouTube URL"
              className="url-input"
              disabled={!shellReady}
              id="youtube-link"
              onChange={(event) => setUrlInput(event.target.value)}
              placeholder="Enter a YouTube link..."
              value={urlInput}
            />
          </div>
          <button
            className="btn primary"
            disabled={commandDisabled || !urlInput.trim()}
            type="submit"
          >
            Add to queue
          </button>
        </form>

        <div className="save-to" title={outputDir || "Waiting for runtime state"}>
          <span className="save-to-label">Save to</span>
          <span className="save-to-path">{outputDir ? compactPath(outputDir, 4) : "pending"}</span>
        </div>

        <button
          className="btn"
          disabled={commandDisabled}
          onClick={() => void handlePickOutputDir()}
          type="button"
        >
          Browse
        </button>

        <button
          className="btn"
          disabled={openOutputDisabled}
          onClick={() => void handleOpenOutputDir()}
          type="button"
        >
          Open
        </button>
      </header>

      {bridgeError ? (
        <div className="bridge-error" role="alert">
          <span>{bridgeError}</span>
          <button className="btn sm" onClick={() => setBridgeError("")} type="button">
            Dismiss
          </button>
        </div>
      ) : null}

      <main className="workspace-host">
        <VariantC {...variantProps} />
      </main>
    </div>
  );
}

function formatError(error: unknown) {
  if (error instanceof BridgeClientError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Unknown bridge error.";
}

function formatQueueSummary(progress: {
  completed: number;
  failed: number;
  queued: number;
  running: number;
  total: number;
}) {
  if (progress.total === 0) {
    return "0 items";
  }

  const parts: string[] = [];
  if (progress.running) {
    parts.push(`${progress.running} running`);
  }
  if (progress.queued) {
    parts.push(`${progress.queued} ready`);
  }
  if (progress.completed) {
    parts.push(`${progress.completed} done`);
  }
  if (progress.failed) {
    parts.push(`${progress.failed} failed`);
  }

  return parts.length ? `${progress.total} | ${parts.join(" | ")}` : `${progress.total}`;
}

export default App;
