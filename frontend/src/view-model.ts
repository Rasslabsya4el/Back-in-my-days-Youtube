import type {
  AppState,
  DownloadMode,
  FormatOptionSnapshot,
  QueueItemSnapshot,
} from "./types";

export type Tone = "connecting" | "ready" | "error" | "busy" | "idle";

export type FriendlyFormatOption = {
  option: FormatOptionSnapshot;
  fileFormatLabel: string;
  fileFormatValue: string;
  qualityLabel: string;
  qualityValue: string;
};

export type FormatSelectionModel = {
  activeOption: FriendlyFormatOption | null;
  fileFormatChoices: Array<{ label: string; value: string }>;
  options: FriendlyFormatOption[];
  qualityChoices: Array<{ label: string; value: string }>;
};

export function summarizeQueue(queue: QueueItemSnapshot[]) {
  let queued = 0;
  let running = 0;
  let completed = 0;
  let failed = 0;

  for (const item of queue) {
    switch (item.status) {
      case "queued":
        queued += 1;
        break;
      case "running":
        running += 1;
        break;
      case "completed":
        completed += 1;
        break;
      case "failed":
      case "cancelled":
        failed += 1;
        break;
      default:
        break;
    }
  }

  return {
    completed,
    failed,
    queued,
    running,
    total: queue.length,
  };
}

export function buildFormatSelectionModel(
  selectedItem: QueueItemSnapshot | null,
  mode: DownloadMode,
  selection: AppState["selection"] | null,
): FormatSelectionModel {
  const rawOptions =
    mode === "audio"
      ? selectedItem?.probe?.audio_formats ?? []
      : selectedItem?.probe?.video_formats ?? [];

  const options = rawOptions.map((option) => toFriendlyFormatOption(option, mode));
  const activeOption = resolveActiveFormatOption(
    options,
    selection?.selected_format_id || selectedItem?.selected_format_id || "",
    selection?.quality || selectedItem?.quality || "",
  );
  const qualityChoices = dedupeChoices(
    options.map((option) => ({
      label: option.qualityLabel,
      value: option.qualityValue,
    })),
  );
  const finalFileFormat = formatFinalFileFormat(mode);

  return {
    activeOption,
    fileFormatChoices: [{ label: finalFileFormat, value: finalFileFormat.toLowerCase() }],
    options,
    qualityChoices,
  };
}

export function pickFriendlyFormatOption(
  options: FriendlyFormatOption[],
  nextSelection: { fileFormatValue: string; qualityValue: string },
) {
  return (
    options.find(
      (option) =>
        option.qualityValue === nextSelection.qualityValue &&
        option.fileFormatValue === nextSelection.fileFormatValue,
    ) ||
    options.find((option) => option.qualityValue === nextSelection.qualityValue) ||
    options.find((option) => option.fileFormatValue === nextSelection.fileFormatValue) ||
    null
  );
}

export function resolveQueueFormatOption(item: QueueItemSnapshot) {
  return buildFormatSelectionModel(
    item,
    item.mode,
    {
      mode: item.mode,
      quality: item.quality,
      quality_options: [],
      selected_format_id: item.selected_format_id,
      selected_item_id: item.id,
    },
  ).activeOption;
}

export function buildItemSubtitle(item: QueueItemSnapshot) {
  return [item.probe?.channel || readableSource(item.source_url), formatDuration(item.probe?.duration ?? 0)]
    .filter(Boolean)
    .join(" / ");
}

export function compactPath(pathValue: string, keepSegments = 3) {
  if (!pathValue) {
    return "";
  }

  const normalized = pathValue.replace(/\//g, "\\");
  const parts = normalized.split("\\").filter(Boolean);
  if (parts.length <= keepSegments) {
    return normalized;
  }
  return `...\\${parts.slice(-keepSegments).join("\\")}`;
}

export function formatDuration(durationSeconds: number) {
  if (!durationSeconds) {
    return "unknown duration";
  }

  const hours = Math.floor(durationSeconds / 3600);
  const minutes = Math.floor((durationSeconds % 3600) / 60);
  const seconds = durationSeconds % 60;

  if (hours) {
    return `${hours.toString().padStart(2, "0")}:${minutes
      .toString()
      .padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
  }

  return `${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
}

export function formatToolStatus(
  tool?: {
    is_available: boolean;
    path: string;
    source: string;
  },
) {
  if (!tool) {
    return "pending";
  }
  if (!tool.is_available) {
    return "missing";
  }
  return tool.path ? `${tool.source}: ${tool.path}` : tool.source;
}

export function formatConnectionState(state: "connecting" | "ready" | "error") {
  switch (state) {
    case "ready":
      return "ready";
    case "error":
      return "error";
    default:
      return "connecting";
  }
}

export function formatModeLabel(mode: DownloadMode) {
  return mode === "audio" ? "Audio" : "Video";
}

export function formatFinalFileFormat(mode: DownloadMode) {
  return mode === "audio" ? "M4A" : "MP4";
}

export function formatPrimaryStatusHeadline(
  selectedItem: QueueItemSnapshot | null,
  bridgeError: string,
) {
  if (bridgeError) {
    return "Something needs attention";
  }
  if (!selectedItem) {
    return "Ready for your first link";
  }

  switch (selectedItem.status) {
    case "running":
      return "Download in progress";
    case "completed":
      return "Download complete";
    case "failed":
    case "cancelled":
      return "Download stopped";
    default:
      return "Ready to download";
  }
}

export function buildPrimaryStatusMessage(
  selectedItem: QueueItemSnapshot | null,
  bridgeError: string,
  statusMessage: string,
) {
  if (bridgeError) {
    return "The app cannot reach the desktop bridge right now. Open Show debug for technical details.";
  }
  if (!selectedItem) {
    return "Paste a YouTube link, confirm where to save it, then add it to the queue.";
  }

  switch (selectedItem.status) {
    case "running":
      return "The selected item is downloading. This panel updates automatically while it runs.";
    case "completed":
      return selectedItem.output_path
        ? `Saved as ${pathLeaf(selectedItem.output_path)}.`
        : "The download finished and the file is ready.";
    case "failed":
    case "cancelled":
      return "This item did not finish. Review the selection and retry, or open Show debug for technical details.";
    default:
      return sanitizePrimaryStatus(statusMessage) || "Review the current item, then start the download.";
  }
}

export function nextStepGuidance(selectedItem: QueueItemSnapshot | null) {
  if (!selectedItem) {
    return "Add a link to load video details.";
  }

  switch (selectedItem.status) {
    case "running":
      return "Wait for the current download to finish.";
    case "completed":
      return "Review the saved file in the chosen output folder.";
    case "failed":
    case "cancelled":
      return "Pick another option or retry the download.";
    default:
      return "Review the selection, then start the download.";
  }
}

export function resolveStatusTone(
  selectedItem: QueueItemSnapshot | null,
  bridgeError: string,
): Tone {
  if (bridgeError) {
    return "error";
  }
  if (!selectedItem) {
    return "idle";
  }
  return statusToneFromJob(selectedItem.status);
}

export function describeQueueStatus(item: QueueItemSnapshot) {
  switch (item.processing_step) {
    case "preparing":
      return "Preparing download";
    case "downloading":
      return "Downloading";
    case "postprocessing":
      return "Finishing file";
    case "completed":
      return "Completed";
    case "failed":
      return "Failed";
    default:
      return item.status === "queued" ? "Ready" : item.status;
  }
}

export function readableSource(sourceUrl: string) {
  try {
    const parsed = new URL(sourceUrl);
    return parsed.host.replace(/^www\./, "");
  } catch {
    return sourceUrl;
  }
}

function toFriendlyFormatOption(
  option: FormatOptionSnapshot,
  mode: DownloadMode,
): FriendlyFormatOption {
  const [primaryLabel] = option.quality_label.split("|");
  const qualityLabel = normalizePrimaryFormatLabel(primaryLabel, mode);
  const fileFormatLabel = normalizeFileFormatLabel(mode);

  return {
    fileFormatLabel,
    fileFormatValue: fileFormatLabel.toLowerCase(),
    option,
    qualityLabel,
    qualityValue: qualityLabel.toLowerCase(),
  };
}

function dedupeChoices(choices: Array<{ label: string; value: string }>) {
  const seen = new Set<string>();
  const deduped: Array<{ label: string; value: string }> = [];

  for (const choice of choices) {
    if (seen.has(choice.value)) {
      continue;
    }
    seen.add(choice.value);
    deduped.push(choice);
  }

  return deduped;
}

function resolveActiveFormatOption(
  options: FriendlyFormatOption[],
  selectedFormatId: string,
  selectedQuality: string,
) {
  const selectedIds = new Set(
    selectedFormatId
      .split("+")
      .map((value) => value.trim())
      .filter(Boolean),
  );

  return (
    options.find((option) => selectedIds.has(option.option.format_id)) ||
    options.find((option) => option.option.quality_label === selectedQuality) ||
    options[0] ||
    null
  );
}

function normalizePrimaryFormatLabel(label: string, mode: DownloadMode) {
  const trimmed = label.trim();
  if (!trimmed || trimmed.toLowerCase() === "audio" || trimmed.toLowerCase() === "video") {
    return mode === "audio" ? "Best audio" : "Best video";
  }
  return trimmed;
}

function normalizeFileFormatLabel(mode: DownloadMode) {
  return formatFinalFileFormat(mode);
}

function statusToneFromJob(status: QueueItemSnapshot["status"]): Tone {
  switch (status) {
    case "completed":
      return "ready";
    case "running":
      return "busy";
    case "failed":
    case "cancelled":
      return "error";
    default:
      return "idle";
  }
}

function sanitizePrimaryStatus(message: string) {
  const normalized = message.trim();
  if (!normalized) {
    return "";
  }

  const lowered = normalized.toLowerCase();
  if (
    lowered.includes("selected_format_id") ||
    lowered.includes("video-only") ||
    lowered.includes("audio-only") ||
    lowered.includes("muxed") ||
    lowered.includes("resolver status") ||
    lowered.includes("fmt ")
  ) {
    return "Technical details stay in Show debug so the main workspace can stay focused on the download flow.";
  }

  return normalized;
}

function pathLeaf(pathValue: string) {
  const normalized = pathValue.replace(/\//g, "\\");
  const parts = normalized.split("\\").filter(Boolean);
  return parts[parts.length - 1] ?? normalized;
}
