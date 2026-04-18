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
    thumbnailLoaded,
    onThumbnailLoad,
    onSelectItem,
    selectedStatus,
    queueSummary,
    currentMode,
  } = props;

  return (
    <div className="workspace variant-c">
      <section className="panel rail-panel">
        <div className="panel-header rail-header">
          <div className="panel-header-copy">
            <h2>Queue</h2>
            <span className="panel-caption">
              {queue.length ? "Persisted session items" : "Waiting for the first item"}
            </span>
          </div>
          <span className="summary">{queueSummary}</span>
        </div>
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
                  disabled={controlsDisabled}
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
                  key={`${selectedItem.id}:${selectedItem.probe?.thumbnail ?? ""}`}
                  alt={selectedItem.title || "Selected media thumbnail"}
                  loaded={thumbnailLoaded}
                  onLoad={onThumbnailLoad}
                  src={selectedItem.probe?.thumbnail ?? ""}
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

              <StatusSurface status={selectedStatus} variant="block" />

              <ActionBlock
                controlsDisabled={controlsDisabled}
                currentMode={currentMode}
                formatModel={props.formatModel}
                onFileFormatChange={props.onFileFormatChange}
                onModeChange={props.onModeChange}
                onQualityChange={props.onQualityChange}
                onStart={props.onStart}
                onStartAll={props.onStartAll}
                queuedItemCount={props.queuedItemCount}
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
