from __future__ import annotations

import json
from pathlib import Path

from .models import QueueItem


class QueueStateStore:
    def __init__(self, state_file: Path) -> None:
        self.state_file = state_file

    def load(self) -> list[QueueItem]:
        if not self.state_file.exists():
            return []

        payload = json.loads(self.state_file.read_text(encoding="utf-8"))
        return [QueueItem.from_dict(item) for item in payload.get("queue", [])]

    def save(self, items: list[QueueItem]) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "queue": [item.to_dict() for item in items],
        }
        self.state_file.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
