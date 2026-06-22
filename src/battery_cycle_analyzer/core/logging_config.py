from __future__ import annotations

import logging
from pathlib import Path


def default_log_path() -> Path:
    home = Path.home()
    return home / ".battery_cycle_analyzer" / "logs" / "application.log"


def configure_logging(*, debug: bool = False, log_path: Path | None = None) -> Path:
    path = log_path or default_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if debug else logging.INFO
    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        root.removeHandler(handler)
    file_handler = logging.FileHandler(path, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s",
            "%Y-%m-%d %H:%M:%S",
        )
    )
    root.addHandler(file_handler)
    return path
