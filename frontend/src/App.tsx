import {
  startTransition,
  useDeferredValue,
  useEffect,
  useEffectEvent,
  useRef,
  useState,
} from "react";

import { BridgeClientError, bridgeClient } from "./bridge";
import type {
  AppState,
  BridgeMeta,
  BridgeResponse,
  DownloadMode,
  GetAppStatePayload,
  InspectOutputPayload,
  QueueItemSnapshot,
  RuntimeInfoPayload,
} from "./types";

import "./styles.css";

type ConnectionState = "connecting" | "ready" | "error";
type Tone = "connecting" | "ready" | "error" | "busy" | "idle";

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
  const [thumbnailLoaded, setThumbnailLoaded] = useState(false);

  const isMountedRef = useRef(true);
  const cursorRef = useRef(0);
  const pollInFlightRef = useRef(false);
  const documentHiddenRef = useRef(typeof document !== "undefined" ? document.hidden : false);

  const queue = appState?.queue ?? [];
  const deferredQueue = useDeferredValue(queue);
  const selectedItem = appState?.selected_item ?? null;
  const selection = appState?.selection ?? null;
  const progress = summarizeQueue(queue);
  const bridgeBusy = bridgeMeta?.download_active ?? false;
  const controlsDisabled = actionBusy || bridgeBusy || connectionState !== "ready";
  const statusTone = resolveStatusTone(selectedItem, bridgeError);
  const shellMessage =
    bridgeError || appState?.status_message || "Waiting for bridge state from the desktop host.";

  useEffect(() => {
    setThumbnailLoaded(false);
  }, [selectedItem?.id, selectedItem?.probe?.thumbnail]);

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
    if (!normalized) {
      return;
    }
    await runStateCommand(bridgeClient.addUrl(normalized), {
      resetUrl: true,
      resetInspection: true,
    });
  }

  async function handleModeChange(mode: DownloadMode) {
    if (mode === selection?.mode) {
      return;
    }
    await runStateCommand(bridgeClient.selectMode(mode), { resetInspection: true });
  }

  async function handleQualityChange(event: React.ChangeEvent<HTMLSelectElement>) {
    await runStateCommand(bridgeClient.selectQuality(event.target.value), {
      resetInspection: true,
    });
  }

  async function handleSelectItem(itemId: string) {
    if (itemId === appState?.selected_item_id) {
      return;
    }
    await runStateCommand(bridgeClient.selectItem(itemId), {
      resetInspection: true,
    });
  }

  async function handleStartDownload() {
    if (!selectedItem) {
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

  async function handleInspectOutput() {
    if (!selectedItem?.output_path) {
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

  return (
    <div className="shell">
      <header className="topbar panel">
        <div className="topbar-copy">
          <p className="eyebrow">Desktop Shell</p>
          <h1>YouTube Downloader</h1>
          <p className="hero-copy">
            Paste a link, choose video or audio, then start the saved selection when you are ready.
          </p>
        </div>
        <dl className="status-cluster">
          <Metric
            label="Connection"
            value={formatConnectionState(connectionState)}
            tone={connectionState}
          />
          <Metric label="Queue" value={`${progress.total} item${progress.total === 1 ? "" : "s"}`} />
          <Metric
            label="Activity"
            value={bridgeBusy ? "Download running" : "Idle"}
            tone={bridgeBusy ? "busy" : "idle"}
          />
          <Metric
            label="Last Sync"
            value={lastStateSyncAt || "Pending"}
            tone={lastStateSyncAt ? "ready" : "connecting"}
          />
        </dl>
      </header>

      <main className="layout">
        <section className="primary-column">
          <section className="panel intake-panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Intake</p>
                <h2>Add a YouTube link</h2>
              </div>
              <StatusBadge tone={connectionState} value={formatConnectionState(connectionState)} />
            </div>
            <form className="stack" onSubmit={handleAddUrl}>
              <div className="intake-row">
                <input
                  aria-label="YouTube URL"
                  className="url-input"
                  disabled={controlsDisabled}
                  onChange={(event) => setUrlInput(event.target.value)}
                  placeholder="https://www.youtube.com/watch?v=..."
                  value={urlInput}
                />
                <button
                  className="primary-button"
                  disabled={controlsDisabled || !urlInput.trim()}
                  type="submit"
                >
                  Add to queue
                </button>
              </div>
              <p className="support-copy">
                Metadata is loaded first. The real download starts only after you press Start download.
              </p>
            </form>
          </section>

          <section className="panel queue-panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Queue</p>
                <h2>Ready to test</h2>
              </div>
              <span className="section-note">
                {bridgeBusy ? "Queue is locked while a download is active." : "Selectable items"}
              </span>
            </div>
            <div className="queue-stats">
              <StatChip label="Queued" value={String(progress.queued)} />
              <StatChip label="Running" value={String(progress.running)} tone={progress.running ? "busy" : "idle"} />
              <StatChip label="Completed" value={String(progress.completed)} tone={progress.completed ? "ready" : "idle"} />
              <StatChip label="Failed" value={String(progress.failed)} tone={progress.failed ? "error" : "idle"} />
            </div>
            {deferredQueue.length === 0 ? (
              <div className="empty-state">
                Queue is empty. Add a URL to load probe metadata and unlock selection controls.
              </div>
            ) : (
              <ul className="queue-list">
                {deferredQueue.map((item) => {
                  const isSelected = item.id === appState?.selected_item_id;
                  return (
                    <li key={item.id}>
                      <button
                        className={`queue-row${isSelected ? " selected" : ""}`}
                        disabled={controlsDisabled}
                        onClick={() => void handleSelectItem(item.id)}
                        type="button"
                      >
                        <div className="queue-row-top">
                          <StatusBadge tone={statusToneFromJob(item.status)} value={item.status} />
                          <span className="queue-row-step">{formatStepLabel(item.processing_step)}</span>
                        </div>
                        <strong className="queue-row-title">{item.title || item.source_url}</strong>
                        <span className="queue-row-subtitle">
                          {item.probe?.channel || readableSource(item.source_url)}
                        </span>
                        <span className="queue-row-meta">
                          {item.mode} | {item.quality || "quality pending"} |{" "}
                          {formatDuration(item.probe?.duration ?? 0)}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </section>

        <section className="secondary-column">
          <section className="panel selection-panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Selection</p>
                <h2>Current item</h2>
              </div>
              {selectedItem ? (
                <StatusBadge tone={statusToneFromJob(selectedItem.status)} value={selectedItem.status} />
              ) : null}
            </div>
            {selectedItem ? (
              <>
                <div className="selected-shell">
                  <div className="thumbnail-frame">
                    {selectedItem.probe?.thumbnail ? (
                      <img
                        alt={selectedItem.title || "Selected media thumbnail"}
                        className={`thumbnail${thumbnailLoaded ? " is-ready" : ""}`}
                        decoding="async"
                        loading="lazy"
                        onLoad={() => setThumbnailLoaded(true)}
                        src={selectedItem.probe.thumbnail}
                      />
                    ) : (
                      <div className="thumbnail-placeholder">No thumbnail</div>
                    )}
                  </div>
                  <div className="selected-copy">
                    <h3>{selectedItem.title || "Untitled queue item"}</h3>
                    <p className="selected-meta">
                      {selectedItem.probe?.channel || readableSource(selectedItem.source_url)}
                    </p>
                    <p className="selected-meta">
                      {formatDuration(selectedItem.probe?.duration ?? 0)} | updated{" "}
                      {formatTimestamp(selectedItem.updated_at)}
                    </p>
                  </div>
                </div>

                <div className="field-grid">
                  <div className="field">
                    <label htmlFor="mode-toggle">Mode</label>
                    <div className="toggle-group" id="mode-toggle">
                      {(["video", "audio"] as DownloadMode[]).map((mode) => (
                        <button
                          key={mode}
                          className={`toggle-chip${selection?.mode === mode ? " active" : ""}`}
                          disabled={controlsDisabled}
                          onClick={() => void handleModeChange(mode)}
                          type="button"
                        >
                          {mode}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="field">
                    <label htmlFor="quality-select">Quality</label>
                    <select
                      id="quality-select"
                      className="quality-select"
                      disabled={controlsDisabled || !selection?.quality_options.length}
                      onChange={(event) => void handleQualityChange(event)}
                      value={selection?.quality ?? ""}
                    >
                      {selection?.quality_options.map((quality) => (
                        <option key={quality} value={quality}>
                          {quality}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="detail-grid compact">
                  <Detail label="Saved format" value={selectedItem.selected_format_id || "pending"} mono />
                  <Detail label="Source" value={selectedItem.source_url} mono />
                </div>

                <div className="action-row">
                  <button
                    className="primary-button"
                    disabled={controlsDisabled}
                    onClick={() => void handleStartDownload()}
                    type="button"
                  >
                    Start download
                  </button>
                </div>
              </>
            ) : (
              <div className="empty-state">Select or add an item to unlock controls.</div>
            )}
          </section>

          <section className="panel status-panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Status</p>
                <h2>Download and output</h2>
              </div>
              <StatusBadge tone={statusTone} value={bridgeError ? "attention" : "current"} />
            </div>

            <div className={`status-banner tone-${statusTone}`}>
              <strong>{selectedItem ? formatStepLabel(selectedItem.processing_step) : "Waiting for input"}</strong>
              <p>{shellMessage}</p>
            </div>

            <div className="detail-grid">
              <Detail
                label="Item detail"
                value={
                  selectedItem?.status_detail ||
                  "The backend has not emitted a detailed status message for this item yet."
                }
              />
              <Detail
                label="Output path"
                value={selectedItem?.output_path || "No file has been written yet."}
                mono
              />
              <Detail
                label="Error"
                value={bridgeError || selectedItem?.error_message || "None"}
              />
            </div>
          </section>
        </section>
      </main>

      <section className="panel debug-shell">
        <div className="debug-toggle-row">
          <div>
            <p className="eyebrow">Debug</p>
            <h2>Runtime details</h2>
          </div>
          <button
            className="secondary-button"
            onClick={() => setDebugOpen((current) => !current)}
            type="button"
          >
            {debugOpen ? "Hide debug" : "Show debug"}
          </button>
        </div>

        {debugOpen ? (
          <div className="debug-layout">
            <div className="debug-toolbar">
              <span className="section-note">
                Cursor {bridgeMeta?.event_cursor ?? 0} | last response events {debugEventCount} | API{" "}
                {runtimeInfo?.bridge.api_version ?? bridgeMeta?.api_version ?? "pending"}
              </span>
              <div className="debug-actions">
                <button
                  className="secondary-button"
                  disabled={actionBusy || connectionState !== "ready"}
                  onClick={() => void pollAppState(0)}
                  type="button"
                >
                  Refresh state
                </button>
                <button
                  className="secondary-button"
                  disabled={actionBusy || connectionState !== "ready"}
                  onClick={() => void loadRuntimeInfo()}
                  type="button"
                >
                  Refresh runtime
                </button>
                <button
                  className="secondary-button"
                  disabled={actionBusy || !selectedItem?.output_path}
                  onClick={() => void handleInspectOutput()}
                  type="button"
                >
                  Inspect output
                </button>
              </div>
            </div>

            <div className="debug-grid">
              <section className="debug-card">
                <h3>Runtime</h3>
                <dl className="detail-grid compact">
                  <Detail
                    label="Project root"
                    value={appState?.runtime.project_root ?? "pending"}
                    mono
                  />
                  <Detail
                    label="Output dir"
                    value={appState?.runtime.output_dir ?? "pending"}
                    mono
                  />
                  <Detail
                    label="State file"
                    value={appState?.runtime.state_file ?? "pending"}
                    mono
                  />
                  <Detail
                    label="ffmpeg"
                    value={formatToolStatus(appState?.runtime.ffmpeg)}
                  />
                  <Detail
                    label="ffprobe"
                    value={formatToolStatus(appState?.runtime.ffprobe)}
                  />
                  <Detail
                    label="Update model"
                    value={
                      runtimeInfo
                        ? `${runtimeInfo.bridge.update_model.kind} via ${runtimeInfo.bridge.update_model.state_method}`
                        : "pending"
                    }
                  />
                  <Detail
                    label="Mutation lock"
                    value={
                      runtimeInfo?.bridge.command_model.mutations_blocked_while_downloading
                        ? "enabled"
                        : "pending"
                    }
                  />
                  <Detail
                    label="Shells"
                    value={
                      runtimeInfo
                        ? `bridge=${runtimeInfo.bridge.shells.pywebview_bootstrap ? "yes" : "no"} / tk=${runtimeInfo.bridge.shells.tkinter_fallback ? "yes" : "no"}`
                        : "pending"
                    }
                  />
                </dl>
              </section>

              <section className="debug-card">
                <h3>Inspect output</h3>
                <pre className="json-block">
                  {inspection
                    ? JSON.stringify(
                        inspection.ok ? inspection.data.inspection : inspection.error,
                        null,
                        2,
                      )
                    : "Inspect output stays hidden until you request it."}
                </pre>
              </section>
            </div>
          </div>
        ) : null}
      </section>
    </div>
  );
}

function Metric({
  label,
  tone,
  value,
}: {
  label: string;
  tone?: Tone;
  value: string;
}) {
  return (
    <div className={`metric${tone ? ` tone-${tone}` : ""}`}>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function StatusBadge({ tone, value }: { tone: Tone; value: string }) {
  return <span className={`status-badge tone-${tone}`}>{value}</span>;
}

function StatChip({
  label,
  tone,
  value,
}: {
  label: string;
  tone?: Tone;
  value: string;
}) {
  return (
    <div className={`stat-chip${tone ? ` tone-${tone}` : ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Detail({
  label,
  mono,
  value,
}: {
  label: string;
  mono?: boolean;
  value: string;
}) {
  return (
    <div className="detail-row">
      <dt>{label}</dt>
      <dd className={mono ? "mono" : ""}>{value}</dd>
    </div>
  );
}

function summarizeQueue(queue: QueueItemSnapshot[]) {
  let queued = 0;
  let running = 0;
  let completed = 0;
  let failed = 0;

  for (const item of queue) {
    switch (item.status) {
      case "queued":
        queued += 1;
        break;
      case "running":
        running += 1;
        break;
      case "completed":
        completed += 1;
        break;
      case "failed":
      case "cancelled":
        failed += 1;
        break;
      default:
        break;
    }
  }

  return {
    queued,
    running,
    completed,
    failed,
    total: queue.length,
  };
}

function formatDuration(durationSeconds: number) {
  if (!durationSeconds) {
    return "unknown duration";
  }
  const hours = Math.floor(durationSeconds / 3600);
  const minutes = Math.floor((durationSeconds % 3600) / 60);
  const seconds = durationSeconds % 60;
  if (hours) {
    return `${hours.toString().padStart(2, "0")}:${minutes
      .toString()
      .padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
  }
  return `${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
}

function formatTimestamp(rawValue: string) {
  if (!rawValue) {
    return "unknown";
  }
  const timestamp = new Date(rawValue);
  if (Number.isNaN(timestamp.getTime())) {
    return rawValue;
  }
  return timestamp.toLocaleString();
}

function formatToolStatus(
  tool?: {
    is_available: boolean;
    path: string;
    source: string;
  },
) {
  if (!tool) {
    return "pending";
  }
  if (!tool.is_available) {
    return "missing";
  }
  return tool.path ? `${tool.source}: ${tool.path}` : tool.source;
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

function formatConnectionState(state: ConnectionState) {
  switch (state) {
    case "ready":
      return "Connected";
    case "error":
      return "Error";
    default:
      return "Connecting";
  }
}

function resolveStatusTone(selectedItem: QueueItemSnapshot | null, bridgeError: string): Tone {
  if (bridgeError) {
    return "error";
  }
  if (!selectedItem) {
    return "idle";
  }
  return statusToneFromJob(selectedItem.status);
}

function statusToneFromJob(status: QueueItemSnapshot["status"]): Tone {
  switch (status) {
    case "completed":
      return "ready";
    case "running":
      return "busy";
    case "failed":
    case "cancelled":
      return "error";
    default:
      return "idle";
  }
}

function formatStepLabel(step: string) {
  switch (step) {
    case "queued":
      return "Queued";
    case "preparing":
      return "Preparing";
    case "downloading":
      return "Downloading";
    case "postprocessing":
      return "Postprocessing";
    case "completed":
      return "Completed";
    case "failed":
      return "Failed";
    default:
      return step;
  }
}

function readableSource(sourceUrl: string) {
  try {
    const parsed = new URL(sourceUrl);
    return parsed.host.replace(/^www\./, "");
  } catch {
    return sourceUrl;
  }
}

export default App;
