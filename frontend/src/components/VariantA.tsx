import { buildItemSubtitle } from "../view-model";
import { ActionBlock } from "./ActionBlock";
import { QueueRowCard, StatusSurface, Thumb } from "./Primitives";
import type { VariantProps } from "./variant-types";

export function VariantA(props: VariantProps) {
  const {
    queue,
    selectedItem,
    selectedItemId,
    controlsDisabled,
    thumbnailLoaded,
    onThumbnailLoad,
    onSelectItem,
    selectedStatus,
    buildItemStatus,
    queueSummary,
  } = props;

  return (
    <div className="workspace variant-a">
      <section className="panel queue-panel">
        <div className="panel-header">
          <h2>Queue</h2>
          <span className="summary">{queueSummary}</span>
        </div>
        {queue.length === 0 ? (
          <div className="empty">
            <span className="empty-title">Queue is empty</span>
            <span>Paste a YouTube link above to add the first item.</span>
          </div>
        ) : (
          <ul className="queue-list panel-body scroll flush">
            {queue.map((item) => (
              <li key={item.id}>
                <QueueRowCard
                  disabled={controlsDisabled}
                  item={item}
                  onClick={() => onSelectItem(item.id)}
                  selected={item.id === selectedItemId}
                  status={buildItemStatus(item)}
                />
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel detail-panel">
        <div className="panel-header">
          <h2>Selected item</h2>
        </div>
        {selectedItem ? (
          <div className="detail-body">
            <div className="left-col">
              <Thumb
                alt={selectedItem.title || "Selected media thumbnail"}
                loaded={thumbnailLoaded}
                onLoad={onThumbnailLoad}
                src={selectedItem.probe?.thumbnail ?? ""}
              />
            </div>

            <div className="right-col">
              <div className="item-headline">
                <h3 title={selectedItem.title || selectedItem.source_url}>
                  {selectedItem.title || selectedItem.source_url}
                </h3>
                <span className="meta">{buildItemSubtitle(selectedItem)}</span>
              </div>

              <StatusSurface status={selectedStatus} variant="block" />

              <ActionBlock
                controlsDisabled={controlsDisabled}
                currentMode={props.currentMode}
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
          <div className="empty">
            <span className="empty-title">No item selected</span>
            <span>Select an item from the queue, or add a new link.</span>
          </div>
        )}
      </section>
    </div>
  );
}
