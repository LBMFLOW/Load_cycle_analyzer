from __future__ import annotations

from collections.abc import Sequence


def run(argv: Sequence[str] | None = None) -> int:
    """Start the desktop application."""
    from PyQt6.QtWidgets import QApplication

    from battery_cycle_analyzer.core.logging_config import configure_logging
    from battery_cycle_analyzer.ui.main_window import MainWindow

    args = list(argv or [])
    debug = "--debug" in args
    configure_logging(debug=debug)

    app = QApplication(args)
    app.setApplicationName("Battery Cycle Analyzer")
    app.setOrganizationName("Battery Cycle Analyzer")

    window = MainWindow()
    window.resize(1400, 900)
    window.show()
    return app.exec()
