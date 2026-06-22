from __future__ import annotations

import weakref

import pytest

from battery_cycle_analyzer.core.tasks import CancellationToken, TaskCancelled, report_progress


def test_cancellation_token_only_raises_after_cancel() -> None:
    token = CancellationToken.create()

    token.raise_if_cancelled()

    token.cancel()
    with pytest.raises(TaskCancelled):
        token.raise_if_cancelled()


def test_cancellation_token_supports_weak_references_for_qt_connections() -> None:
    token = CancellationToken.create()

    assert weakref.ref(token)() is token


def test_report_progress_clamps_percent() -> None:
    calls: list[tuple[int, str]] = []

    report_progress(lambda percent, message: calls.append((percent, message)), 125, "done")
    report_progress(lambda percent, message: calls.append((percent, message)), -10, "start")

    assert calls == [(100, "done"), (0, "start")]
