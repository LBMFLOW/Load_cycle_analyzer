from __future__ import annotations

import pandas as pd
from PyQt6.QtCore import Qt

from battery_cycle_analyzer.ui.table_panel import DataFrameTableModel


def test_highlighted_table_rows_use_dark_foreground() -> None:
    model = DataFrameTableModel(pd.DataFrame({"time_s": [0, 1], "energy_wh": [10, 9]}))
    model.set_highlighted_rows([0])

    foreground = model.data(model.index(0, 0), Qt.ItemDataRole.ForegroundRole)

    assert foreground.name() == "#111827"


def test_current_table_row_uses_dark_foreground() -> None:
    model = DataFrameTableModel(pd.DataFrame({"time_s": [0, 1], "energy_wh": [10, 9]}))
    model.set_current_row(1)

    foreground = model.data(model.index(1, 0), Qt.ItemDataRole.ForegroundRole)

    assert foreground.name() == "#111827"
