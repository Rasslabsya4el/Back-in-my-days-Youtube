import type {
  AppState,
  BridgeMeta,
  BridgeResponse,
  InspectOutputPayload,
  QueueItemSnapshot,
  RuntimeInfoPayload,
} from "../types";
import { formatConnectionState, formatToolStatus } from "../view-model";

type ConnectionState = "connecting" | "ready" | "error";

export function DebugDrawer({
  open,
  onToggle,
  appState,
  bridgeMeta,
  runtimeInfo,
  selectedItem,
  inspection,
  connectionState,
  debugEventCount,
  lastStateSyncAt,
  actionBusy,
  onRefreshState,
  onRefreshRuntime,
  onInspectOutput,
}: {
  open: boolean;
  onToggle: () => void;
  appState: AppState | null;
  bridgeMeta: BridgeMeta | null;
  runtimeInfo: RuntimeInfoPayload | null;
  selectedItem: QueueItemSnapshot | null;
  inspection: BridgeResponse<InspectOutputPayload> | null;
  connectionState: ConnectionState;
  debugEventCount: number;
  lastStateSyncAt: string;
  actionBusy: boolean;
  onRefreshState: () => void;
  onRefreshRuntime: () => void;
  onInspectOutput: () => void;
}) {
  const summary = `Connection ${formatConnectionState(connectionState)} | cursor ${
    bridgeMeta?.event_cursor ?? 0
  } | events ${debugEventCount} | sync ${lastStateSyncAt || "pending"} | API ${
    runtimeInfo?.bridge.api_version ?? bridgeMeta?.api_version ?? "pending"
  }`;

  return (
    <div className={`debug-drawer${open ? " open" : ""}`}>
      <div className="debug-handle">
        <button aria-expanded={open} onClick={onToggle} type="button">
          <span className="chev" />
          <span>{open ? "Hide debug" : "Show debug"}</span>
        </button>
        <span>{summary}</span>
      </div>
      {open ? (
        <div className="debug-body">
          <section className="debug-card">
            <h3>Runtime</h3>
            <div className="actions">
              <button
                className="btn sm"
                disabled={actionBusy || connectionState !== "ready"}
                onClick={onRefreshState}
                type="button"
              >
                Refresh state
              </button>
              <button
                className="btn sm"
                disabled={actionBusy || connectionState !== "ready"}
                onClick={onRefreshRuntime}
                type="button"
              >
                Refresh runtime
              </button>
              <button
                className="btn sm"
                disabled={actionBusy || !selectedItem?.output_path}
                onClick={onInspectOutput}
                type="button"
              >
                Inspect output
              </button>
            </div>
            <dl className="detail-grid">
              <dt>Project root</dt>
              <dd>{appState?.runtime.project_root ?? "pending"}</dd>
              <dt>Output dir</dt>
              <dd>{appState?.runtime.output_dir ?? "pending"}</dd>
              <dt>State file</dt>
              <dd>{appState?.runtime.state_file ?? "pending"}</dd>
              <dt>Status msg</dt>
              <dd>{appState?.status_message || "pending"}</dd>
              <dt>Item detail</dt>
              <dd>{selectedItem?.status_detail || "pending"}</dd>
              <dt>Item error</dt>
              <dd>{selectedItem?.error_message || "none"}</dd>
              <dt>ffmpeg</dt>
              <dd>{formatToolStatus(appState?.runtime.ffmpeg)}</dd>
              <dt>ffprobe</dt>
              <dd>{formatToolStatus(appState?.runtime.ffprobe)}</dd>
              <dt>Update model</dt>
              <dd>
                {runtimeInfo
                  ? `${runtimeInfo.bridge.update_model.kind} via ${runtimeInfo.bridge.update_model.state_method}`
                  : "pending"}
              </dd>
              <dt>Mutation lock</dt>
              <dd>
                {runtimeInfo?.bridge.command_model.mutations_blocked_while_downloading
                  ? "enabled"
                  : "pending"}
              </dd>
              <dt>Shells</dt>
              <dd>
                {runtimeInfo
                  ? `bridge=${runtimeInfo.bridge.shells.pywebview_bootstrap ? "yes" : "no"} | tk=${
                      runtimeInfo.bridge.shells.tkinter_fallback ? "yes" : "no"
                    }`
                  : "pending"}
              </dd>
            </dl>
          </section>

          <section className="debug-card">
            <h3>Inspect output</h3>
            <pre className="json-block">
              {inspection
                ? JSON.stringify(inspection.ok ? inspection.data.inspection : inspection.error, null, 2)
                : "Inspect output stays hidden until you request it."}
            </pre>
          </section>
        </div>
      ) : null}
    </div>
  );
}
