from __future__ import annotations

from dataclasses import dataclass
from threading import Event
from typing import Callable

ProgressCallback = Callable[[int, str], None]


class TaskCancelled(RuntimeError):
    """Raised when a cancellable background task is stopped by the user."""


@dataclass(slots=True)
class CancellationToken:
    _event: Event

    @classmethod
    def create(cls) -> "CancellationToken":
        return cls(Event())

    def cancel(self) -> None:
        self._event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled:
            raise TaskCancelled("Operation cancelled.")


def report_progress(
    callback: ProgressCallback | None,
    percent: int,
    message: str,
) -> None:
    if callback is not None:
        callback(max(0, min(100, int(percent))), message)
