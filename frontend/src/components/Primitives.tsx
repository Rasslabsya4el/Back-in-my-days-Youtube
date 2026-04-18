import type { QueueItemSnapshot } from "../types";
import {
  buildItemSubtitle,
  describeQueueStatus,
  formatDuration,
  formatModeLabel,
  resolveStatusTone,
  type Tone,
  type UnifiedStatus,
} from "../view-model";

export function Thumb({
  src,
  alt,
  size,
  loaded,
  onLoad,
}: {
  src: string;
  alt: string;
  size?: "default" | "tiny" | "mini";
  loaded: boolean;
  onLoad: () => void;
}) {
  const cls = `thumb${size === "tiny" ? " tiny" : size === "mini" ? " mini" : ""}`;

  if (!src) {
    return (
      <div aria-hidden={size !== "default"} className={cls}>
        <span className="placeholder">No preview</span>
      </div>
    );
  }

  return (
    <div className={cls}>
      <img
        alt={alt}
        className={loaded ? "loaded" : ""}
        decoding="async"
        loading="lazy"
        onLoad={onLoad}
        src={src}
      />
      {!loaded ? (
        <span className="placeholder">{size === "mini" ? "." : "Loading preview"}</span>
      ) : null}
    </div>
  );
}

export function StatusSurface({
  status,
  variant = "row",
}: {
  status: UnifiedStatus;
  variant?: "row" | "block";
}) {
  return (
    <div
      className={`status tone-${status.tone}${variant === "block" ? " block" : ""}`}
      title={status.detail || status.headline}
    >
      <span className="status-label">{status.label}</span>
      {variant === "block" ? (
        <>
          {status.headline ? <strong className="status-headline">{status.headline}</strong> : null}
          {status.detail ? (
            <span className={`status-detail${status.detailMono ? " mono" : ""}`}>
              {status.detail}
            </span>
          ) : null}
        </>
      ) : status.detail ? (
        <span className="status-detail">{status.detail}</span>
      ) : null}
    </div>
  );
}

export function QueueRowCard({
  item,
  selected,
  status,
  onClick,
  disabled,
}: {
  item: QueueItemSnapshot;
  selected: boolean;
  status: UnifiedStatus;
  onClick: () => void;
  disabled: boolean;
}) {
  return (
    <button
      aria-pressed={selected}
      className={`queue-row card${selected ? " selected" : ""}`}
      disabled={disabled}
      onClick={onClick}
      type="button"
    >
      <span className="qr-title" title={item.title || item.source_url}>
        {item.title || item.source_url}
      </span>
      <span className="qr-sub">{buildItemSubtitle(item)}</span>
      <StatusSurface status={status} variant="row" />
    </button>
  );
}

export function QueueRowTable({
  item,
  selected,
  status,
  onClick,
  disabled,
}: {
  item: QueueItemSnapshot;
  selected: boolean;
  status: UnifiedStatus;
  onClick: () => void;
  disabled: boolean;
}) {
  return (
    <li>
      <button
        aria-pressed={selected}
        className={`queue-row table-row${selected ? " selected" : ""}`}
        disabled={disabled}
        onClick={onClick}
        type="button"
      >
        <span className="qr-main">
          <span className="qr-title" title={item.title || item.source_url}>
            {item.title || item.source_url}
          </span>
          <span className="qr-sub">{buildItemSubtitle(item)}</span>
        </span>
        <StatusSurface status={status} variant="row" />
      </button>
    </li>
  );
}

export function QueueRowRail({
  item,
  selected,
  onClick,
  disabled,
}: {
  item: QueueItemSnapshot;
  selected: boolean;
  onClick: () => void;
  disabled: boolean;
}) {
  const tone: Tone = resolveStatusTone(item, "");
  const duration = item.probe?.duration ? formatDuration(item.probe.duration) : "";
  const subtitle = [describeQueueStatus(item), duration].filter(Boolean).join(" / ");

  return (
    <button
      aria-pressed={selected}
      className={`queue-row rail${selected ? " selected" : ""}`}
      disabled={disabled}
      onClick={onClick}
      title={`${item.title || item.source_url} - ${describeQueueStatus(item)}`}
      type="button"
    >
      <div aria-hidden="true" className="thumb mini">
        {item.probe?.thumbnail ? (
          <img alt="" className="loaded" decoding="async" loading="lazy" src={item.probe.thumbnail} />
        ) : (
          <span className="placeholder">.</span>
        )}
      </div>
      <span className="qr-main">
        <span className="qr-title-row">
          <span className="qr-title">{item.title || item.source_url}</span>
          <span className="queue-kind">{formatModeLabel(item.mode)}</span>
        </span>
        <span className="qr-sub">{subtitle}</span>
      </span>
      <span className={`status-dot tone-${tone}`} />
    </button>
  );
}
