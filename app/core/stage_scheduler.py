from __future__ import annotations

import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, Iterator


DEFAULT_HEAVY_VIDEO_TRANSCODE_LIMIT = 1


@dataclass(slots=True, frozen=True)
class StageConcurrencyPolicy:
    heavy_video_transcode_limit: int = DEFAULT_HEAVY_VIDEO_TRANSCODE_LIMIT

    def __post_init__(self) -> None:
        if self.heavy_video_transcode_limit < 1:
            raise ValueError("heavy_video_transcode_limit must be >= 1.")


class DownloadStageScheduler:
    def __init__(self, policy: StageConcurrencyPolicy | None = None) -> None:
        self.policy = policy or StageConcurrencyPolicy()
        self._heavy_video_transcode_gate = _StageGate(self.policy.heavy_video_transcode_limit)

    @contextmanager
    def acquire_heavy_video_transcode_slot(
        self,
        *,
        on_wait: Callable[[], None] | None = None,
        on_acquired: Callable[[], None] | None = None,
    ) -> Iterator[None]:
        with self._heavy_video_transcode_gate.acquire(
            on_wait=on_wait,
            on_acquired=on_acquired,
        ):
            yield


class _StageGate:
    def __init__(self, limit: int) -> None:
        self._limit = max(1, limit)
        self._condition = threading.Condition()
        self._active = 0
        self._next_ticket = 0
        self._ticket_cursor = 0

    @contextmanager
    def acquire(
        self,
        *,
        on_wait: Callable[[], None] | None = None,
        on_acquired: Callable[[], None] | None = None,
    ) -> Iterator[None]:
        waited = False
        with self._condition:
            ticket = self._ticket_cursor
            self._ticket_cursor += 1
            while ticket != self._next_ticket or self._active >= self._limit:
                if not waited and on_wait is not None:
                    waited = True
                    on_wait()
                self._condition.wait()
            self._active += 1
            self._next_ticket += 1
            self._condition.notify_all()

        if on_acquired is not None:
            on_acquired()

        try:
            yield
        finally:
            with self._condition:
                self._active -= 1
                self._condition.notify_all()
