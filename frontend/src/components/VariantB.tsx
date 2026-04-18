import { buildItemSubtitle } from "../view-model";
import { ActionBlock } from "./ActionBlock";
import { QueueRowTable, StatusSurface, Thumb } from "./Primitives";
import type { VariantProps } from "./variant-types";

export function VariantB(props: VariantProps) {
  const {
    queue,
    selectedItem,
    selectedItemId,
    controlsDisabled,
    selectionDisabled,
    onSelectItem,
    selectedStatus,
    buildItemStatus,
    queueSummary,
  } = props;

  return (
    <div className="workspace variant-b">
      <section className="panel queue-panel">
        <div className="panel-header">
          <h2>Operations</h2>
          <span className="summary">{queueSummary}</span>
        </div>

        {queue.length === 0 ? (
          <>
            <div className="table-head">
              <span>Title</span>
              <span>Status</span>
            </div>
            <div className="empty">
              <span className="empty-title">No operations queued</span>
              <span>Enter a YouTube link above to start.</span>
            </div>
          </>
        ) : (
          <>
            <div className="table-head">
              <span>Title</span>
              <span>Status</span>
            </div>
            <ul className="queue-list-table">
              {queue.map((item) => (
                <QueueRowTable
                  key={item.id}
                  disabled={selectionDisabled}
                  item={item}
                  onClick={() => onSelectItem(item.id)}
                  selected={item.id === selectedItemId}
                  status={buildItemStatus(item)}
                />
              ))}
            </ul>
          </>
        )}
      </section>

      <section className="panel dock">
        <div className="panel-header">
          <h2>Detail</h2>
        </div>
        {selectedItem ? (
          <div className="dock-body">
            <Thumb
              alt={selectedItem.title || "Selected media thumbnail"}
              src={selectedItem.probe?.thumbnail ?? ""}
            />

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
        ) : (
          <div className="empty">
            <span className="empty-title">No item selected</span>
            <span>Pick an operation from the list to inspect it.</span>
          </div>
        )}
      </section>
    </div>
  );
}
