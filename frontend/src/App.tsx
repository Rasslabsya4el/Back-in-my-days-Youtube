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
  RuntimeInfoPayload,
} from "./types";
import {
  buildPrimaryStatusMessage,
  buildFormatSelectionModel,
  buildItemSubtitle,
  compactPath,
  describeQueueStatus,
  formatDuration,
  formatConnectionState,
  formatFinalFileFormat,
  formatModeLabel,
  formatPrimaryStatusHeadline,
  formatToolStatus,
  nextStepGuidance,
  pickFriendlyFormatOption,
  readableSource,
  resolveStatusTone,
  summarizeQueue,
  type Tone,
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
  const [thumbnailLoaded, setThumbnailLoaded] = useState(false);

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
  const bridgeBusy = bridgeMeta?.download_active ?? false;
  const controlsDisabled = actionBusy || bridgeBusy || connectionState !== "ready";
  const statusTone = resolveStatusTone(selectedItem, bridgeError);
  const primaryStatusMessage = buildPrimaryStatusMessage(
    selectedItem,
    bridgeError,
    appState?.status_message ?? "",
  );
  const currentChannel = selectedItem
    ? selectedItem.probe?.channel || readableSource(selectedItem.source_url)
    : "";
  const currentDuration = selectedItem ? formatDuration(selectedItem.probe?.duration ?? 0) : "";
  const finalFileFormatLabel =
    formatModel.fileFormatChoices[0]?.label ?? formatFinalFileFormat(currentMode);
  const qualityLabel =
    selectedFormatOption?.qualityLabel ?? formatModel.qualityChoices[0]?.label ?? "Quality pending";
  const guidanceValue =
    bridgeError || selectedItem?.error_message
      ? "Open Show debug for technical details, then retry this item."
      : nextStepGuidance(selectedItem);

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
      resetInspection: true,
      resetUrl: true,
    });
  }

  async function handleModeChange(mode: DownloadMode) {
    if (mode === selection?.mode) {
      return;
    }
    await runStateCommand(bridgeClient.selectMode(mode), { resetInspection: true });
  }

  async function handleQualityChange(event: React.ChangeEvent<HTMLSelectElement>) {
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

  async function handlePickOutputDir() {
    await runStateCommand(bridgeClient.pickOutputDir());
  }

  return (
    <div className="shell">
      <main className="workspace panel">
        <section className="workspace-strip">
          <form className="strip-block strip-form" onSubmit={handleAddUrl}>
            <div className="strip-field">
              <label htmlFor="youtube-link">YouTube link</label>
              <input
                aria-label="YouTube URL"
                className="url-input"
                disabled={controlsDisabled}
                id="youtube-link"
                onChange={(event) => setUrlInput(event.target.value)}
                placeholder="https://www.youtube.com/watch?v=..."
                value={urlInput}
              />
            </div>
            <button
              className="primary-button"
              disabled={controlsDisabled || !urlInput.trim()}
              type="submit"
            >
              Add to queue
            </button>
          </form>

          <section className="strip-block strip-folder">
            <div className="strip-field">
              <span className="field-label">Save to</span>
              <div className="path-chip" title={outputDir || "Waiting for runtime state"}>
                {outputDir ? compactPath(outputDir, 4) : "Waiting for runtime state"}
              </div>
            </div>
            <button
              className="secondary-button"
              disabled={controlsDisabled}
              onClick={() => void handlePickOutputDir()}
              type="button"
            >
              Browse
            </button>
          </section>
        </section>

        <div className="workspace-flow">
          <aside className="workspace-block queue-block">
            <div className="section-heading">
              <div>
                <h2>Queue</h2>
                <p className="section-note">{formatQueueSummary(progress)}</p>
              </div>
            </div>
            {deferredQueue.length === 0 ? (
              <div className="empty-state">Queue is empty. Add a link to load your first item.</div>
            ) : (
              <ul className="queue-list">
                {deferredQueue.map((item) => {
                  const isSelected = item.id === appState?.selected_item_id;
                  const itemTone = resolveStatusTone(item, "");
                  return (
                    <li key={item.id}>
                      <button
                        aria-pressed={isSelected}
                        className={`queue-row${isSelected ? " selected" : ""}`}
                        disabled={controlsDisabled}
                        onClick={() => void handleSelectItem(item.id)}
                        type="button"
                      >
                        <div className="queue-row-header">
                          <strong className="queue-row-title">{item.title || item.source_url}</strong>
                          <span className={`queue-status-chip tone-${itemTone}`}>
                            {describeQueueStatus(item)}
                          </span>
                        </div>
                        <span className="queue-row-subtitle">{buildItemSubtitle(item)}</span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </aside>

          <section className="workspace-block current-block">
            <div className="section-heading">
              <div>
                <h2>Current item</h2>
                <p className="section-note">Review the selected queue item, then start the download.</p>
              </div>
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
                    <div className="selected-heading-row">
                      <h3>{selectedItem.title || "Untitled queue item"}</h3>
                      <span className={`queue-status-chip tone-${statusTone}`}>
                        {describeQueueStatus(selectedItem)}
                      </span>
                    </div>
                    <p className="section-note">
                      Selected from the queue. Update the download settings on this panel only.
                    </p>
                  </div>
                </div>

                <div className="detail-summary-grid">
                  <SurfaceValue label="Channel" value={currentChannel || "Channel pending"} />
                  <SurfaceValue label="Duration" value={currentDuration} />
                </div>

                <div className="current-controls">
                  <div className="field">
                    <span className="field-label">Download as</span>
                    <div aria-label="Download as" className="toggle-group" role="group">
                      {(["video", "audio"] as DownloadMode[]).map((mode) => (
                        <button
                          key={mode}
                          className={`toggle-chip${currentMode === mode ? " active" : ""}`}
                          disabled={controlsDisabled}
                          onClick={() => void handleModeChange(mode)}
                          type="button"
                        >
                          {formatModeLabel(mode)}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="field-grid">
                    {formatModel.qualityChoices.length > 1 ? (
                      <SelectField
                        disabled={controlsDisabled || !formatModel.qualityChoices.length}
                        id="quality-select"
                        label="Quality"
                        onChange={(event) => void handleQualityChange(event)}
                        options={formatModel.qualityChoices}
                        value={selectedFormatOption?.qualityValue ?? ""}
                      />
                    ) : (
                      <StaticField label="Quality" value={qualityLabel} />
                    )}

                    {formatModel.fileFormatChoices.length > 1 ? (
                      <SelectField
                        disabled={controlsDisabled || !formatModel.fileFormatChoices.length}
                        id="file-format-select"
                        label="Final file"
                        onChange={(event) => void handleFileFormatChange(event)}
                        options={formatModel.fileFormatChoices}
                        value={selectedFormatOption?.fileFormatValue ?? ""}
                      />
                    ) : (
                      <StaticField label="Final file" value={finalFileFormatLabel} />
                    )}
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
                </div>

                <div className="current-status-panel">
                  <div className={`status-banner tone-${statusTone}`}>
                    <strong>{formatPrimaryStatusHeadline(selectedItem, bridgeError)}</strong>
                    <p>{primaryStatusMessage}</p>
                  </div>
                  <div className="status-grid">
                    <SurfaceValue label="Status" value={describeQueueStatus(selectedItem)} />
                    <SurfaceValue
                      label="Save to"
                      mono
                      title={outputDir}
                      value={outputDir ? compactPath(outputDir, 4) : "Waiting for runtime state"}
                    />
                    <SurfaceValue
                      label="Saved file"
                      mono
                      title={selectedItem.output_path ?? ""}
                      value={
                        selectedItem.output_path
                          ? compactPath(selectedItem.output_path, 4)
                          : "No file saved yet."
                      }
                    />
                    <SurfaceValue
                      label={bridgeError || selectedItem.error_message ? "Need help?" : "Next step"}
                      tone={bridgeError || selectedItem.error_message ? "error" : "idle"}
                      value={guidanceValue}
                    />
                  </div>
                </div>
              </>
            ) : (
              <div className="empty-state">
                Paste a link to load the first queue item, then review it here before downloading.
              </div>
            )}
          </section>
        </div>
      </main>

      <section className="panel debug-shell">
        <div className="debug-toggle-row">
          <div>
            <p className="section-label">Debug</p>
            <h2>Runtime details</h2>
            <p className="section-note">
              Hidden from the main download workspace unless you need inspect or runtime data.
            </p>
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
              <span className="debug-summary">
                {`Connection ${formatConnectionState(connectionState)} • cursor ${bridgeMeta?.event_cursor ?? 0} • last response events ${debugEventCount} • last sync ${lastStateSyncAt || "pending"} • API ${runtimeInfo?.bridge.api_version ?? bridgeMeta?.api_version ?? "pending"}`}
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
                  <Detail label="Project root" mono value={appState?.runtime.project_root ?? "pending"} />
                  <Detail label="Output dir" mono value={appState?.runtime.output_dir ?? "pending"} />
                  <Detail label="State file" mono value={appState?.runtime.state_file ?? "pending"} />
                  <Detail label="Last status" value={appState?.status_message ?? "pending"} />
                  <Detail label="Item detail" value={selectedItem?.status_detail || "pending"} />
                  <Detail label="Item error" value={selectedItem?.error_message || "none"} />
                  <Detail label="ffmpeg" value={formatToolStatus(appState?.runtime.ffmpeg)} />
                  <Detail label="ffprobe" value={formatToolStatus(appState?.runtime.ffprobe)} />
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

function SelectField({
  disabled,
  id,
  label,
  onChange,
  options,
  value,
}: {
  disabled: boolean;
  id: string;
  label: string;
  onChange: (event: React.ChangeEvent<HTMLSelectElement>) => void;
  options: Array<{ label: string; value: string }>;
  value: string;
}) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <select
        className="select-control"
        disabled={disabled}
        id={id}
        onChange={onChange}
        value={value}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function StaticField({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="field">
      <span className="field-label">{label}</span>
      <div className="static-control">{value}</div>
    </div>
  );
}

function SurfaceValue({
  label,
  mono,
  title,
  tone,
  value,
}: {
  label: string;
  mono?: boolean;
  title?: string;
  tone?: Tone;
  value: string;
}) {
  return (
    <div className={`surface-value${tone ? ` tone-${tone}` : ""}`} title={title || value}>
      <span>{label}</span>
      <strong className={mono ? "mono" : ""}>{value}</strong>
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
    return "No items yet.";
  }

  const parts = [];
  if (progress.running) {
    parts.push(`${progress.running} downloading`);
  }
  if (progress.queued) {
    parts.push(`${progress.queued} ready`);
  }
  if (progress.completed) {
    parts.push(`${progress.completed} saved`);
  }
  if (progress.failed) {
    parts.push(`${progress.failed} need attention`);
  }

  return parts.length
    ? `${progress.total} item${progress.total === 1 ? "" : "s"} in queue. ${parts.join(", ")}.`
    : `${progress.total} item${progress.total === 1 ? "" : "s"} in queue.`;
}

export default App;
