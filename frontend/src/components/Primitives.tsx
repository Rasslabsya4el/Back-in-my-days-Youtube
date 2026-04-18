import { useLayoutEffect, useRef, useState } from "react";

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
  testIdPrefix,
}: {
  src: string;
  alt: string;
  size?: "default" | "tiny" | "mini";
  testIdPrefix?: string;
}) {
  const [loadedSrc, setLoadedSrc] = useState("");
  const [failedSrc, setFailedSrc] = useState("");
  const imageRef = useRef<HTMLImageElement | null>(null);
  const cls = `thumb${size === "tiny" ? " tiny" : size === "mini" ? " mini" : ""}`;
  const loaded = loadedSrc === src;
  const failed = failedSrc === src;

  useLayoutEffect(() => {
    const image = imageRef.current;
    if (!src || !image || !image.complete) {
      return;
    }

    if (image.naturalWidth > 0) {
      setLoadedSrc(src);
      setFailedSrc((current) => (current === src ? "" : current));
      return;
    }

    setFailedSrc(src);
    setLoadedSrc((current) => (current === src ? "" : current));
  }, [src]);

  if (!src || failed) {
    return (
      <div
        aria-hidden={size !== "default"}
        className={cls}
        data-testid={testIdPrefix}
      >
        <span
          className="placeholder"
          data-testid={testIdPrefix ? `${testIdPrefix}-placeholder` : undefined}
        >
          {size === "mini" ? "." : "No preview"}
        </span>
      </div>
    );
  }

  return (
    <div className={cls} data-testid={testIdPrefix}>
      <img
        alt={alt}
        className={loaded ? "loaded" : ""}
        decoding="async"
        key={src}
        loading="lazy"
        onError={() => {
          setFailedSrc(src);
          setLoadedSrc((current) => (current === src ? "" : current));
        }}
        onLoad={() => {
          setLoadedSrc(src);
          setFailedSrc((current) => (current === src ? "" : current));
        }}
        ref={imageRef}
        src={src}
        data-testid={testIdPrefix ? `${testIdPrefix}-image` : undefined}
      />
      {!loaded ? (
        <span
          className="placeholder"
          data-testid={testIdPrefix ? `${testIdPrefix}-placeholder` : undefined}
        >
          {size === "mini" ? "." : "Loading preview"}
        </span>
      ) : null}
    </div>
  );
}

export function StatusSurface({
  status,
  variant = "row",
  testIdPrefix,
  showDetail = true,
  showHeadline = true,
}: {
  status: UnifiedStatus;
  variant?: "row" | "block";
  testIdPrefix?: string;
  showDetail?: boolean;
  showHeadline?: boolean;
}) {
  const detail = showDetail ? status.detail : "";
  const headline = showHeadline ? status.headline : "";

  return (
    <div
      className={`status tone-${status.tone}${variant === "block" ? " block" : ""}`}
      data-testid={testIdPrefix}
      title={detail || headline || status.label}
    >
      <span className="status-label" data-testid={testIdPrefix ? `${testIdPrefix}-label` : undefined}>
        {status.label}
      </span>
      {variant === "block" ? (
        <>
          {headline ? <strong className="status-headline">{headline}</strong> : null}
          {detail ? (
            <span
              className={`status-detail${status.detailMono ? " mono" : ""}`}
              data-testid={testIdPrefix ? `${testIdPrefix}-detail` : undefined}
            >
              {detail}
            </span>
          ) : null}
        </>
      ) : detail ? (
        <span
          className="status-detail"
          data-testid={testIdPrefix ? `${testIdPrefix}-detail` : undefined}
        >
          {detail}
        </span>
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
      data-queue-item-id={item.id}
      data-testid="queue-row-rail"
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
