import {
  buildItemSubtitle,
  formatFinalFileFormat,
  formatModeLabel,
  readableSource,
} from "../view-model";
import { ActionBlock } from "./ActionBlock";
import { QueueRowRail, StatusSurface, Thumb } from "./Primitives";
import type { VariantProps } from "./variant-types";

export function VariantC(props: VariantProps) {
  const {
    queue,
    selectedItem,
    selectedItemId,
    controlsDisabled,
    selectionDisabled,
    onSelectItem,
    selectedStatus,
    queueSummary,
    currentMode,
  } = props;
  const startAllLabel =
    props.queuedItemCount > 0
      ? `Download all queued (${props.queuedItemCount})`
      : "Download all queued";
  const showClearQueueNote = Boolean(
    queue.length && props.clearQueueDisabled && props.clearQueueReason,
  );

  return (
    <div className="workspace variant-c">
      <section className="panel rail-panel">
        <div className="panel-header rail-header">
          <div className="panel-header-copy">
            <h2>Queue</h2>
            <span className="queue-summary">{queueSummary}</span>
          </div>
          <div className="queue-header-actions" data-testid="queue-header-actions">
            <button
              className="btn sm"
              data-testid="queue-start-all"
              disabled={controlsDisabled || props.queuedItemCount === 0}
              onClick={props.onStartAll}
              type="button"
            >
              {startAllLabel}
            </button>
            <button
              className="btn sm"
              data-testid="queue-clear"
              disabled={props.clearQueueDisabled}
              onClick={props.onClearQueue}
              title={props.clearQueueReason}
              type="button"
            >
              Clear queue
            </button>
          </div>
        </div>
        {showClearQueueNote ? <div className="queue-header-note">{props.clearQueueReason}</div> : null}
        {queue.length === 0 ? (
          <div className="empty rail-empty">
            <span className="empty-title">Empty</span>
            <span>Add a YouTube link above to create the first queued item.</span>
          </div>
        ) : (
          <ul className="queue-list panel-body scroll flush">
            {queue.map((item) => (
              <li key={item.id}>
                <QueueRowRail
                  disabled={selectionDisabled}
                  item={item}
                  onClick={() => onSelectItem(item.id)}
                  selected={item.id === selectedItemId}
                />
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel focus-panel">
        {selectedItem ? (
          <div className="focus-body">
            <aside className="focus-side">
              <div className="focus-preview-card">
                <div className="focus-preview-copy">
                  <span className="eyebrow">Preview</span>
                  <span className="preview-caption">
                    {selectedItem.probe?.channel || readableSource(selectedItem.source_url)}
                  </span>
                </div>
                <Thumb
                  alt={selectedItem.title || "Selected media thumbnail"}
                  src={selectedItem.probe?.thumbnail ?? ""}
                  testIdPrefix="selected-preview"
                />
              </div>
            </aside>

            <div className="focus-main">
              <div className="focus-copy">
                <span className="eyebrow">Selected item</span>
                <div className="item-headline">
                  <h3 title={selectedItem.title || selectedItem.source_url}>
                    {selectedItem.title || selectedItem.source_url}
                  </h3>
                  <span className="meta">{buildItemSubtitle(selectedItem)}</span>
                </div>

                <dl className="focus-facts" aria-label="Selection facts">
                  <div>
                    <dt>Mode</dt>
                    <dd>{formatModeLabel(currentMode)}</dd>
                  </div>
                  <div>
                    <dt>Source</dt>
                    <dd>{readableSource(selectedItem.source_url)}</dd>
                  </div>
                  <div>
                    <dt>Final file</dt>
                    <dd>{formatFinalFileFormat(currentMode)}</dd>
                  </div>
                </dl>
              </div>

              <StatusSurface status={selectedStatus} testIdPrefix="selected-status" variant="block" />

              <ActionBlock
                controlsDisabled={controlsDisabled}
                currentMode={currentMode}
                formatModel={props.formatModel}
                onFileFormatChange={props.onFileFormatChange}
                onModeChange={props.onModeChange}
                onQualityChange={props.onQualityChange}
                onStart={props.onStart}
                selectedFormatOption={props.selectedFormatOption}
                selectedItem={selectedItem}
              />
            </div>
          </div>
        ) : (
          <div className="empty focus-empty">
            <span className="empty-title">Nothing selected</span>
            <span>Pick an item from the queue rail to review its preview and download setup.</span>
          </div>
        )}
      </section>
    </div>
  );
}
