from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal
from PyQt6.QtWidgets import QProgressDialog, QWidget

from battery_cycle_analyzer.core.tasks import CancellationToken, TaskCancelled


class WorkerSignals(QObject):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(object)
    failed = pyqtSignal(object)
    cancelled = pyqtSignal()


class FunctionWorker(QRunnable):
    def __init__(
        self,
        function: Callable[..., Any],
        *,
        cancel_token: CancellationToken | None = None,
    ) -> None:
        super().__init__()
        self.function = function
        self.cancel_token = cancel_token or CancellationToken.create()
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            result = self.function(
                progress_callback=self.signals.progress.emit,
                cancel_token=self.cancel_token,
            )
        except TaskCancelled:
            self.signals.cancelled.emit()
        except BaseException as exc:
            logging.getLogger(__name__).exception("Background task failed")
            self.signals.failed.emit(exc)
        else:
            self.signals.finished.emit(result)


class ProgressTask:
    """Owns a worker and cancellable progress dialog."""

    def __init__(
        self,
        parent: QWidget,
        title: str,
        label: str,
        function: Callable[..., Any],
    ) -> None:
        self.cancel_token = CancellationToken.create()
        self.worker = FunctionWorker(function, cancel_token=self.cancel_token)
        self.dialog = QProgressDialog(label, "Cancel", 0, 100, parent)
        self.dialog.setWindowTitle(title)
        self.dialog.setAutoClose(False)
        self.dialog.setAutoReset(False)
        self.dialog.canceled.connect(self.cancel_token.cancel)
        self.worker.signals.progress.connect(self._progress)
        self.worker.signals.finished.connect(self.dialog.close)
        self.worker.signals.failed.connect(self.dialog.close)
        self.worker.signals.cancelled.connect(self.dialog.close)

    def start(self) -> WorkerSignals:
        self.dialog.show()
        QThreadPool.globalInstance().start(self.worker)
        return self.worker.signals

    def _progress(self, value: int, message: str) -> None:
        self.dialog.setValue(value)
        self.dialog.setLabelText(message)
