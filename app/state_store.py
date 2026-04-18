from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path

from .models import QueueItem


@dataclass(slots=True, frozen=True)
class PersistedQueueState:
    items: list[QueueItem]
    selected_item_id: str | None = None


class QueueStateStore:
    def __init__(self, state_file: Path) -> None:
        self.state_file = state_file
        self._lock = threading.Lock()

    def load(self) -> PersistedQueueState:
        with self._lock:
            if not self.state_file.exists():
                return PersistedQueueState(items=[], selected_item_id=None)

            payload = json.loads(self.state_file.read_text(encoding="utf-8"))
            selected_item_id = str(payload.get("selected_item_id", "")).strip() or None
            return PersistedQueueState(
                items=[QueueItem.from_dict(item) for item in payload.get("queue", [])],
                selected_item_id=selected_item_id,
            )

    def save(self, items: list[QueueItem], *, selected_item_id: str | None = None) -> None:
        with self._lock:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "queue": [item.to_dict() for item in items],
                "selected_item_id": selected_item_id or "",
            }
            self.state_file.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
