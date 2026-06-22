from __future__ import annotations

from typing import Sequence


def run(argv: Sequence[str] | None = None) -> int:
    """Start the PyQt desktop application."""
    from PyQt6.QtWidgets import QApplication

    from battery_aging_app.ui.main_window import MainWindow

    app = QApplication(list(argv or []))
    app.setApplicationName("Battery Aging Load-Cycle Analyzer")
    app.setOrganizationName("Battery Aging Analyzer")

    window = MainWindow()
    window.resize(1440, 900)
    window.show()
    return app.exec()
