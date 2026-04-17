import { startTransition, useEffect, useEffectEvent, useRef, useState } from "react";

import { BridgeClientError, bridgeClient } from "./bridge";
import type {
  AppState,
  BridgeEvent,
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

const POLL_INTERVAL_MS = 900;

function App() {
  const [urlInput, setUrlInput] = useState("");
  const [connectionState, setConnectionState] = useState<ConnectionState>("connecting");
  const [appState, setAppState] = useState<AppState | null>(null);
  const [bridgeMeta, setBridgeMeta] = useState<BridgeMeta | null>(null);
  const [recentEvents, setRecentEvents] = useState<BridgeEvent[]>([]);
  const [runtimeInfo, setRuntimeInfo] = useState<RuntimeInfoPayload | null>(null);
  const [inspection, setInspection] = useState<BridgeResponse<InspectOutputPayload> | null>(null);
  const [bridgeError, setBridgeError] = useState("");
  const [actionBusy, setActionBusy] = useState(false);

  const isMountedRef = useRef(true);
  const cursorRef = useRef(0);

  const selectedItem = appState?.selected_item ?? null;
  const selection = appState?.selection;
  const queue = appState?.queue ?? [];
  const progress = summarizeQueue(queue);
  const bridgeBusy = bridgeMeta?.download_active ?? false;
  const controlsDisabled = actionBusy || bridgeBusy || connectionState !== "ready";

  const applyStatePayload = useEffectEvent(
    (response: BridgeResponse<GetAppStatePayload> | BridgeResponse<{ state: AppState }>) => {
      if (!response.ok) {
        setBridgeError(response.error?.message ?? "Bridge request failed.");
        return;
      }

      cursorRef.current = response.meta.event_cursor;
      startTransition(() => {
        setAppState(response.data.state);
        setBridgeMeta(response.meta);
        setRecentEvents("events" in response.data ? response.data.events : []);
        setConnectionState("ready");
        setBridgeError("");
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
    }
  });

  const bootstrap = useEffectEvent(async () => {
    try {
      await bridgeClient.waitUntilReady();
      if (!isMountedRef.current) {
        return;
      }
      setConnectionState("ready");
      await Promise.all([loadRuntimeInfo(), pollAppState(0)]);
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
    if (connectionState !== "ready") {
      return;
    }

    const intervalId = window.setInterval(() => {
      void pollAppState(cursorRef.current);
    }, POLL_INTERVAL_MS);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [connectionState, pollAppState]);

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

  async function handleQualityChange(
    event: React.ChangeEvent<HTMLSelectElement>,
  ) {
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
      cursorRef.current = response.meta.event_cursor;
      startTransition(() => {
        setAppState(response.data.state);
        setBridgeMeta(response.meta);
        setInspection(null);
        setBridgeError("");
      });
      await loadRuntimeInfo();
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
      <header className="hero panel">
        <div>
          <p className="eyebrow">Desktop Bridge Shell</p>
          <h1>YT Downloader React shell</h1>
          <p className="hero-copy">
            Minimal first-pass UX over the existing Python bridge. Intake,
            queue selection, mode and quality switching, download start, and
            runtime inspection all stay on the current bridge contract.
          </p>
        </div>
        <dl className="hero-stats">
          <Metric label="Connection" value={connectionState} tone={connectionState} />
          <Metric
            label="Bridge API"
            value={runtimeInfo?.bridge.api_version ?? bridgeMeta?.api_version ?? "pending"}
          />
          <Metric label="Cursor" value={String(bridgeMeta?.event_cursor ?? 0)} />
          <Metric
            label="Download active"
            value={bridgeBusy ? "yes" : "no"}
            tone={bridgeBusy ? "busy" : "idle"}
          />
        </dl>
      </header>

      <main className="layout">
        <section className="left-column">
          <form className="panel intake-form" onSubmit={handleAddUrl}>
            <div className="section-heading">
              <div>
                <p className="eyebrow">Intake</p>
                <h2>Add a YouTube URL</h2>
              </div>
            </div>
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
            <p className="status-line">
              {appState?.status_message || bridgeError || "Waiting for bridge state."}
            </p>
          </form>

          <section className="panel queue-progress">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Queue Surface</p>
                <h2>Coarse progress only</h2>
              </div>
              <span className="queue-total">{progress.total} items</span>
            </div>
            <div className="progress-bar" aria-label="Queue progress surface">
              <span
                className="segment completed"
                style={{ width: `${progress.completedPercent}%` }}
              />
              <span
                className="segment running"
                style={{ width: `${progress.runningPercent}%` }}
              />
              <span
                className="segment queued"
                style={{ width: `${progress.queuedPercent}%` }}
              />
              <span
                className="segment failed"
                style={{ width: `${progress.failedPercent}%` }}
              />
            </div>
            <div className="progress-stats">
              <Metric label="Queued" value={String(progress.queued)} tone="idle" />
              <Metric
                label="Running"
                value={String(progress.running)}
                tone={progress.running ? "busy" : "idle"}
              />
              <Metric
                label="Completed"
                value={String(progress.completed)}
                tone="ready"
              />
              <Metric
                label="Failed/Cancelled"
                value={String(progress.failed)}
                tone={progress.failed ? "error" : "idle"}
              />
            </div>
          </section>

          <section className="panel queue-panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Queue</p>
                <h2>Snapshot</h2>
              </div>
              <span className="queue-total">{recentEvents.length} new events</span>
            </div>
            {queue.length === 0 ? (
              <div className="empty-state">
                Queue is empty. Add a URL to load probe metadata.
              </div>
            ) : (
              <ul className="queue-list">
                {queue.map((item) => {
                  const isSelected = item.id === appState?.selected_item_id;
                  return (
                    <li key={item.id}>
                      <button
                        className={`queue-item${isSelected ? " selected" : ""}`}
                        disabled={controlsDisabled}
                        onClick={() => void handleSelectItem(item.id)}
                        type="button"
                      >
                        <div className="queue-item-topline">
                          <span className={`pill pill-${item.status}`}>{item.status}</span>
                          <span className="queue-item-step">{item.processing_step}</span>
                        </div>
                        <strong>{item.title || item.source_url}</strong>
                        <span className="queue-item-meta">
                          {item.mode} | {item.quality || "no quality selected"}
                        </span>
                        <span className="queue-item-meta">
                          {item.probe
                            ? `${item.probe.video_formats.length} video / ${item.probe.audio_formats.length} audio options`
                            : "metadata pending"}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </section>

        <section className="right-column">
          <section className="panel selection-panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Selection</p>
                <h2>Current item</h2>
              </div>
            </div>
            {selectedItem ? (
              <>
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

                <div className="action-row">
                  <button
                    className="primary-button"
                    disabled={actionBusy || bridgeBusy}
                    onClick={() => void handleStartDownload()}
                    type="button"
                  >
                    Start download
                  </button>
                  <button
                    className="secondary-button"
                    disabled={actionBusy || !selectedItem.output_path}
                    onClick={() => void handleInspectOutput()}
                    type="button"
                  >
                    Inspect output
                  </button>
                </div>
              </>
            ) : (
              <div className="empty-state">
                Select or add an item to unlock controls.
              </div>
            )}
          </section>

          <section className="panel details-panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Details</p>
                <h2>Selected item payload</h2>
              </div>
            </div>
            {selectedItem ? (
              <>
                {selectedItem.probe?.thumbnail ? (
                  <img
                    alt={selectedItem.title || "Selected media thumbnail"}
                    className="thumbnail"
                    src={selectedItem.probe.thumbnail}
                  />
                ) : null}
                <dl className="detail-grid">
                  <Detail label="Title" value={selectedItem.title || "unknown"} />
                  <Detail label="URL" value={selectedItem.source_url} mono />
                  <Detail label="Status" value={selectedItem.status} />
                  <Detail label="Step" value={selectedItem.processing_step} />
                  <Detail label="Mode" value={selectedItem.mode} />
                  <Detail label="Quality" value={selectedItem.quality || "n/a"} />
                  <Detail
                    label="Format ID"
                    value={selectedItem.selected_format_id || "n/a"}
                    mono
                  />
                  <Detail
                    label="Updated"
                    value={formatTimestamp(selectedItem.updated_at)}
                  />
                  <Detail
                    label="Output"
                    value={selectedItem.output_path || "n/a"}
                    mono
                  />
                  <Detail
                    label="Error"
                    value={selectedItem.error_message || "n/a"}
                  />
                  <Detail
                    label="Channel"
                    value={selectedItem.probe?.channel || "unknown"}
                  />
                  <Detail
                    label="Duration"
                    value={formatDuration(selectedItem.probe?.duration ?? 0)}
                  />
                </dl>
                <div className="detail-callout">
                  {selectedItem.status_detail ||
                    "The backend has not emitted a detailed status message for this item yet."}
                </div>
              </>
            ) : (
              <div className="empty-state">No item selected.</div>
            )}
          </section>

          <section className="panel runtime-panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Runtime</p>
                <h2>Bridge and tool status</h2>
              </div>
            </div>
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
                  runtimeInfo?.bridge.command_model
                    .mutations_blocked_while_downloading
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
            <div className="inspection-block">
              <div className="inspection-header">
                <strong>inspect_output</strong>
                <span>
                  {inspection?.ok
                    ? inspection.data.output_path || "no output yet"
                    : "not requested"}
                </span>
              </div>
              <pre>
                {inspection
                  ? JSON.stringify(
                      inspection.ok ? inspection.data.inspection : inspection.error,
                      null,
                      2,
                    )
                  : "Run inspect_output after a completed download to inspect ffprobe output."}
              </pre>
            </div>
          </section>
        </section>
      </main>

      {bridgeError ? <div className="toast toast-error">{bridgeError}</div> : null}
    </div>
  );
}

function Metric({
  label,
  tone,
  value,
}: {
  label: string;
  tone?: "connecting" | "ready" | "error" | "busy" | "idle";
  value: string;
}) {
  return (
    <div className={`metric${tone ? ` tone-${tone}` : ""}`}>
      <dt>{label}</dt>
      <dd>{value}</dd>
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

  const total = queue.length || 1;
  return {
    queued,
    running,
    completed,
    failed,
    total: queue.length,
    queuedPercent: (queued / total) * 100,
    runningPercent: (running / total) * 100,
    completedPercent: (completed / total) * 100,
    failedPercent: (failed / total) * 100,
  };
}

function formatDuration(durationSeconds: number) {
  if (!durationSeconds) {
    return "unknown";
  }
  const hours = Math.floor(durationSeconds / 3600);
  const minutes = Math.floor((durationSeconds % 3600) / 60);
  const seconds = durationSeconds % 60;
  if (hours) {
    return `${hours.toString().padStart(2, "0")}:${minutes
      .toString()
      .padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
  }
  return `${minutes.toString().padStart(2, "0")}:${seconds
    .toString()
    .padStart(2, "0")}`;
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

export default App;
