import type { AppState, DownloadMode, QueueItemSnapshot } from "../types";
import type {
  FormatSelectionModel,
  FriendlyFormatOption,
  UnifiedStatus,
} from "../view-model";

export type VariantProps = {
  appState: AppState | null;
  queue: QueueItemSnapshot[];
  selectedItem: QueueItemSnapshot | null;
  selectedItemId: string;
  currentMode: DownloadMode;
  formatModel: FormatSelectionModel;
  selectedFormatOption: FriendlyFormatOption | null;
  controlsDisabled: boolean;
  selectionDisabled: boolean;
  onSelectItem: (id: string) => void;
  onModeChange: (mode: DownloadMode) => void;
  onQualityChange: (event: React.ChangeEvent<HTMLSelectElement>) => void;
  onFileFormatChange: (event: React.ChangeEvent<HTMLSelectElement>) => void;
  onStart: () => void;
  onStartAll: () => void;
  onClearQueue: () => void;
  queuedItemCount: number;
  clearQueueDisabled: boolean;
  clearQueueReason: string;
  selectedStatus: UnifiedStatus;
  buildItemStatus: (item: QueueItemSnapshot) => UnifiedStatus;
  queueSummary: string;
};
