import {
  startTransition,
  useDeferredValue,
  useEffect,
  useEffectEvent,
  useRef,
  useState,
} from "react";

import { BridgeClientError, bridgeClient } from "./bridge";
import { DebugDrawer } from "./components/DebugDrawer";
import { VariantA } from "./components/VariantA";
import { VariantB } from "./components/VariantB";
import { VariantC } from "./components/VariantC";
import { useCompareMode } from "./components/VariantSwitcher";
import type { VariantProps } from "./components/variant-types";
import type {
  AppState,
  BridgeMeta,
  BridgeResponse,
  DownloadMode,
  GetAppStatePayload,
  InspectOutputPayload,
  RuntimeInfoPayload,
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
  const [runtimeInfo, setRuntimeInfo] = useState<RuntimeInfoPayload | null>(null);
  const [inspection, setInspection] = useState<BridgeResponse<InspectOutputPayload> | null>(null);
  const [bridgeError, setBridgeError] = useState("");
  const [actionBusy, setActionBusy] = useState(false);
  const [debugOpen, setDebugOpen] = useState(false);
  const [debugEventCount, setDebugEventCount] = useState(0);
  const [lastStateSyncAt, setLastStateSyncAt] = useState("");
  const [loadedThumbnailSrc, setLoadedThumbnailSrc] = useState("");
  const [compareMode] = useCompareMode();

  const isMountedRef = useRef(true);
  const cursorRef = useRef(0);
  const pollInFlightRef = useRef(false);
  const documentHiddenRef = useRef(typeof document !== "undefined" ? document.hidden : false);

  const queue = appState?.queue ?? [];
  const deferredQueue = useDeferredValue(queue);
  const selectedItem = appState?.selected_item ?? null;
  const selection = appState?.selection ?? null;
  const currentMode = selection?.mode ?? selectedItem?.mode ?? "video";
  const formatModel = buildFormatSelectionModel(selectedItem, currentMode, selection);
  const selectedFormatOption = formatModel.activeOption;
  const outputDir = appState?.runtime.output_dir ?? "";
  const progress = summarizeQueue(queue);
  const queuedItemCount = queue.filter((item) => item.status === "queued").length;
  const shellReady = connectionState === "ready";
  const controlsDisabled = actionBusy || !shellReady;
  const commandDisabled = actionBusy || !shellReady;
  const pasteDisabled = !shellReady;
  const openOutputDisabled = actionBusy || !shellReady || !outputDir;
  const selectedStatus = buildUnifiedStatus(selectedItem, bridgeError);
  const selectedThumbnailSrc = selectedItem?.probe?.thumbnail ?? "";
  const thumbnailLoaded =
    Boolean(selectedThumbnailSrc) && loadedThumbnailSrc === selectedThumbnailSrc;

  useEffect(() => {
    setLoadedThumbnailSrc("");
  }, [selectedItem?.id, selectedThumbnailSrc]);

  const applyStatePayload = useEffectEvent(
    (response: BridgeResponse<GetAppStatePayload> | BridgeResponse<{ state: AppState }>) => {
      if (!response.ok) {
        setBridgeError(response.error?.message ?? "Bridge request failed.");
        return;
      }

      cursorRef.current = response.meta.event_cursor;
      const nextState = "state" in response.data ? response.data.state ?? null : null;
      const events = "events" in response.data ? response.data.events : [];
      const nextSyncTime = nextState ? new Date().toLocaleTimeString() : lastStateSyncAt;

      startTransition(() => {
        setBridgeMeta(response.meta);
        setConnectionState("ready");
        setBridgeError("");
        setDebugEventCount(events.length);
        if (nextState) {
          setAppState(nextState);
          setLastStateSyncAt(nextSyncTime);
        }
      });
    },
  );

  const loadRuntimeInfo = useEffectEvent(async () => {
    const response = await bridgeClient.getRuntimeInfo();
    if (!isMountedRef.current) {
      return;
    }
    if (!response.ok) {
      setBridgeError(response.error?.message ?? "Failed to read runtime info.");
      return;
    }

    startTransition(() => {
      setRuntimeInfo(response.data);
    });
  });

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

  useEffect(() => {
    if (!debugOpen || connectionState !== "ready") {
      return;
    }
    void loadRuntimeInfo();
  }, [connectionState, debugOpen, loadRuntimeInfo]);

  async function runStateCommand(
    command: Promise<BridgeResponse<{ state: AppState }>>,
    options?: { resetUrl?: boolean; resetInspection?: boolean },
  ) {
    setActionBusy(true);
    try {
      const response = await command;
      if (!isMountedRef.current) {
        return;
      }
      applyStatePayload(response);
      if (options?.resetUrl && response.ok) {
        setUrlInput("");
      }
      if (options?.resetInspection) {
        setInspection(null);
      }
    } catch (error) {
      if (!isMountedRef.current) {
        return;
      }
      setBridgeError(formatError(error));
    } finally {
      if (isMountedRef.current) {
        setActionBusy(false);
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
      resetInspection: true,
      resetUrl: true,
    });
  }

  async function handleModeChange(mode: DownloadMode) {
    if (mode === selection?.mode || commandDisabled) {
      return;
    }
    await runStateCommand(bridgeClient.selectMode(mode), { resetInspection: true });
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
    await runStateCommand(bridgeClient.selectQuality(nextOption.option.quality_label), {
      resetInspection: true,
    });
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
    await runStateCommand(bridgeClient.selectQuality(nextOption.option.quality_label), {
      resetInspection: true,
    });
  }

  async function handleSelectItem(itemId: string) {
    if (itemId === appState?.selected_item_id || controlsDisabled) {
      return;
    }
    setLoadedThumbnailSrc("");
    await runStateCommand(bridgeClient.selectItem(itemId), {
      resetInspection: true,
    });
  }

  async function handleStartDownload() {
    if (!selectedItem || commandDisabled || selectedItem.status === "running") {
      return;
    }

    setActionBusy(true);
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
      setInspection(null);
      if (debugOpen) {
        await loadRuntimeInfo();
      }
    } catch (error) {
      if (isMountedRef.current) {
        setBridgeError(formatError(error));
      }
    } finally {
      if (isMountedRef.current) {
        setActionBusy(false);
      }
    }
  }

  async function handleStartAllDownloads() {
    if (!queuedItemCount || commandDisabled) {
      return;
    }

    setActionBusy(true);
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
      setInspection(null);
      if (debugOpen) {
        await loadRuntimeInfo();
      }
    } catch (error) {
      if (isMountedRef.current) {
        setBridgeError(formatError(error));
      }
    } finally {
      if (isMountedRef.current) {
        setActionBusy(false);
      }
    }
  }

  async function handleInspectOutput() {
    if (!selectedItem?.output_path || actionBusy || !shellReady) {
      return;
    }

    setActionBusy(true);
    try {
      const response = await bridgeClient.inspectOutput(selectedItem.output_path);
      if (!isMountedRef.current) {
        return;
      }
      startTransition(() => {
        setInspection(response);
      });
      if (!response.ok) {
        setBridgeError(response.error?.message ?? "Output inspection failed.");
        return;
      }
      setBridgeError("");
    } catch (error) {
      if (isMountedRef.current) {
        setBridgeError(formatError(error));
      }
    } finally {
      if (isMountedRef.current) {
        setActionBusy(false);
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

  async function handlePasteFromClipboard() {
    if (pasteDisabled) {
      return;
    }

    try {
      const clipboardText = await readClipboardText();
      if (!isMountedRef.current) {
        return;
      }
      if (!clipboardText) {
        setBridgeError("Clipboard does not contain text.");
        return;
      }
      setBridgeError("");
      setUrlInput(clipboardText);
    } catch (error) {
      if (isMountedRef.current) {
        setBridgeError(formatError(error));
      }
    }
  }

  const variantProps: VariantProps = {
    appState,
    queue: deferredQueue,
    selectedItem,
    selectedItemId: appState?.selected_item_id ?? "",
    currentMode,
    formatModel,
    selectedFormatOption,
    controlsDisabled,
    thumbnailLoaded,
    onThumbnailLoad: () => setLoadedThumbnailSrc(selectedThumbnailSrc),
    onSelectItem: (id) => void handleSelectItem(id),
    onModeChange: (mode) => void handleModeChange(mode),
    onQualityChange: (event) => void handleQualityChange(event),
    onFileFormatChange: (event) => void handleFileFormatChange(event),
    onStart: () => void handleStartDownload(),
    onStartAll: () => void handleStartAllDownloads(),
    queuedItemCount,
    selectedStatus,
    buildItemStatus: (item) => buildUnifiedStatus(item, ""),
    queueSummary: formatQueueSummary(progress),
  };

  return (
    <div className="app-root">
      <header className="topbar">
        <form className="url-form" onSubmit={handleAddUrl}>
          <div className="url-input-shell">
            <input
              aria-label="YouTube URL"
              className="url-input"
              disabled={!shellReady}
              id="youtube-link"
              onChange={(event) => setUrlInput(event.target.value)}
              placeholder="Paste a YouTube link..."
              value={urlInput}
            />
            <button
              className="btn sm clipboard-btn"
              disabled={pasteDisabled}
              onClick={() => void handlePasteFromClipboard()}
              type="button"
            >
              Paste
            </button>
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

        <span
          aria-label={`Bridge connection: ${connectionState}`}
          className={`conn-dot ${connectionState}`}
          title={`Bridge: ${connectionState}`}
        />
      </header>

      {bridgeError ? (
        <div className="bridge-error" role="alert">
          <span>{bridgeError}</span>
          <button className="btn sm" onClick={() => setBridgeError("")} type="button">
            Dismiss
          </button>
        </div>
      ) : null}

      <main className={`workspace-host${compareMode ? " compare-mode-host" : ""}`}>
        {compareMode ? (
          <CompareMode variantProps={variantProps} />
        ) : (
          <VariantC {...variantProps} />
        )}
      </main>

      <DebugDrawer
        actionBusy={actionBusy}
        appState={appState}
        bridgeMeta={bridgeMeta}
        connectionState={connectionState}
        debugEventCount={debugEventCount}
        inspection={inspection}
        lastStateSyncAt={lastStateSyncAt}
        onInspectOutput={() => void handleInspectOutput()}
        onRefreshRuntime={() => void loadRuntimeInfo()}
        onRefreshState={() => void pollAppState(0)}
        onToggle={() => setDebugOpen((current) => !current)}
        open={debugOpen}
        runtimeInfo={runtimeInfo}
        selectedItem={selectedItem}
      />
    </div>
  );
}

function CompareMode({ variantProps }: { variantProps: VariantProps }) {
  return (
    <div className="compare-mode">
      <section className="compare-copy panel">
        <div className="compare-copy-inner">
          <div>
            <span className="compare-kicker">Preview only</span>
            <h2>Variant compare mode</h2>
            <p>
              A, B, and C below are rendered together from the same live queue, selection, and
              bridge-backed state. The scaled stands are view-only previews; return to single mode
              for full-size interaction.
            </p>
          </div>
        </div>
      </section>

      <div className="compare-grid">
        <CompareStand label="A">
          <VariantA {...variantProps} />
        </CompareStand>
        <CompareStand label="B">
          <VariantB {...variantProps} />
        </CompareStand>
        <CompareStand label="C">
          <VariantC {...variantProps} />
        </CompareStand>
      </div>
    </div>
  );
}

function CompareStand({
  label,
  children,
}: {
  label: "A" | "B" | "C";
  children: React.ReactNode;
}) {
  return (
    <section aria-label={`Variant ${label} preview`} className="compare-card">
      <div className="compare-card-header">
        <span className="compare-card-label">Variant</span>
        <strong>{label}</strong>
      </div>

      <div className="compare-frame-shell">
        <div aria-hidden="true" className="compare-frame-chrome">
          <span />
          <span />
          <span />
        </div>
        <div className="compare-frame">
          <div className="compare-frame-canvas">{children}</div>
        </div>
      </div>
    </section>
  );
}

async function readClipboardText() {
  if (typeof navigator !== "undefined" && navigator.clipboard?.readText) {
    try {
      return (await navigator.clipboard.readText()).trim();
    } catch {
      // Fall back to the bridge when browser clipboard access is unavailable.
    }
  }

  const response = await bridgeClient.readClipboardText();
  if (!response.ok) {
    throw new BridgeClientError(response.error?.message ?? "Clipboard read failed.");
  }

  return response.data.text.trim();
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
