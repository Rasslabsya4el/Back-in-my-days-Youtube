import { buildItemSubtitle } from "../view-model";
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
  } = props;

  return (
    <div className="workspace variant-c">
      <section className="panel rail-panel">
        <div className="panel-header">
          <h2>Queue</h2>
          <span className="summary">{queueSummary}</span>
        </div>
        {queue.length === 0 ? (
          <div className="empty">
            <span className="empty-title">Empty</span>
            <span>Add a link above.</span>
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
            <div className="focus-left">
              <Thumb
                alt={selectedItem.title || "Selected media thumbnail"}
                loaded={thumbnailLoaded}
                onLoad={onThumbnailLoad}
                src={selectedItem.probe?.thumbnail ?? ""}
              />
            </div>

            <div className="focus-right">
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
            <span className="empty-title">Nothing selected</span>
            <span>Pick an item from the rail on the left.</span>
          </div>
        )}
      </section>
    </div>
  );
}
