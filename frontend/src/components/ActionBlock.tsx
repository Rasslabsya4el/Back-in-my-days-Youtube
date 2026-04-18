import type { DownloadMode, QueueItemSnapshot } from "../types";
import {
  buildPrimaryActionLabel,
  formatFinalFileFormat,
  formatModeLabel,
  type FormatSelectionModel,
  type FriendlyFormatOption,
} from "../view-model";

export function ActionBlock({
  selectedItem,
  currentMode,
  formatModel,
  selectedFormatOption,
  controlsDisabled,
  onModeChange,
  onQualityChange,
  onFileFormatChange,
  onStart,
  onStartAll,
  queuedItemCount,
}: {
  selectedItem: QueueItemSnapshot | null;
  currentMode: DownloadMode;
  formatModel: FormatSelectionModel;
  selectedFormatOption: FriendlyFormatOption | null;
  controlsDisabled: boolean;
  onModeChange: (mode: DownloadMode) => void;
  onQualityChange: (event: React.ChangeEvent<HTMLSelectElement>) => void;
  onFileFormatChange: (event: React.ChangeEvent<HTMLSelectElement>) => void;
  onStart: () => void;
  onStartAll: () => void;
  queuedItemCount: number;
}) {
  const finalFileFormatLabel =
    formatModel.fileFormatChoices[0]?.label ?? formatFinalFileFormat(currentMode);
  const qualityLabel =
    selectedFormatOption?.qualityLabel ?? formatModel.qualityChoices[0]?.label ?? "Pending";
  const primaryLabel = buildPrimaryActionLabel(selectedItem);
  const startAllLabel =
    queuedItemCount > 0 ? `Download all queued (${queuedItemCount})` : "Download all queued";
  const selectionSummary = `${formatModeLabel(currentMode)} / ${qualityLabel} / ${finalFileFormatLabel}`;
  const actionHint = selectedItem
    ? `Final output saves as ${finalFileFormatLabel}.`
    : "Select an item to configure the output.";
  const selectedItemRunning = selectedItem?.status === "running";

  return (
    <div className="action-block">
      <div className="action-head">
        <div className="action-head-copy">
          <span className="action-kicker">Download setup</span>
          <h4>Choose the saved output</h4>
        </div>
        <span className="action-summary">{selectionSummary}</span>
      </div>

      <div className="action-grid">
        <div className="action-row">
          <span className="action-label">Mode</span>
          <div aria-label="Download as" className="toggle-group" role="group">
            {(["video", "audio"] as DownloadMode[]).map((mode) => (
              <button
                key={mode}
                className={`toggle-chip${currentMode === mode ? " active" : ""}`}
                disabled={controlsDisabled || !selectedItem || selectedItemRunning}
                onClick={() => onModeChange(mode)}
                type="button"
              >
                {formatModeLabel(mode)}
              </button>
            ))}
          </div>
        </div>

        <div className="action-row">
          <span className="action-label">Quality</span>
          {formatModel.qualityChoices.length > 1 ? (
            <select
              aria-label="Quality"
              disabled={controlsDisabled || !selectedItem || selectedItemRunning}
              onChange={onQualityChange}
              value={selectedFormatOption?.qualityValue ?? ""}
            >
              {formatModel.qualityChoices.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          ) : (
            <span className="static-value">{qualityLabel}</span>
          )}
        </div>

        <div className="action-row">
          <span className="action-label">File</span>
          {formatModel.fileFormatChoices.length > 1 ? (
            <select
              aria-label="Final file"
              disabled={controlsDisabled || !selectedItem || selectedItemRunning}
              onChange={onFileFormatChange}
              value={selectedFormatOption?.fileFormatValue ?? ""}
            >
              {formatModel.fileFormatChoices.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          ) : (
            <span className="static-value">{finalFileFormatLabel}</span>
          )}
        </div>
      </div>

      <div className="action-footer">
        <span className="action-hint">{actionHint}</span>
        <div className="action-buttons">
          <button
            className="btn"
            disabled={controlsDisabled || queuedItemCount === 0}
            onClick={onStartAll}
            type="button"
          >
            {startAllLabel}
          </button>
          <button
            className="btn primary lg"
            disabled={controlsDisabled || !selectedItem || selectedItemRunning}
            onClick={onStart}
            type="button"
          >
            {primaryLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
