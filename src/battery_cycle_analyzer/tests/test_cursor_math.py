from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from battery_cycle_analyzer.plotting.cursor_math import (
    axis_values,
    linear_interpolate,
    nearest_row_index,
)


def test_nearest_row_lookup_uses_binary_search() -> None:
    axis = np.array([0.0, 10.0, 20.0, 30.0])

    assert nearest_row_index(axis, 12.0) == 1
    assert nearest_row_index(axis, 18.0) == 2
    assert nearest_row_index(axis, -1.0) == 0
    assert nearest_row_index(axis, 100.0) == 3


def test_linear_interpolation() -> None:
    axis = np.array([0.0, 10.0, 20.0])
    values = np.array([100.0, 90.0, 70.0])

    assert linear_interpolate(axis, values, 15.0) == pytest.approx(80.0)


def test_row_selection_from_cursor_movement() -> None:
    axis = np.array([0.0, 5.0, 15.0, 30.0])
    cursor_position = 14.0

    selected_row = nearest_row_index(axis, cursor_position)

    assert selected_row == 2


def test_time_normalization_for_numeric_axis() -> None:
    axis = axis_values(pd.Series([100.0, 110.0, 125.0]), normalize=True)

    assert axis.values.tolist() == [0.0, 10.0, 25.0]
    assert axis.label_suffix == "relative"


def test_datetime_axis_converts_to_elapsed_seconds() -> None:
    series = pd.Series(pd.to_datetime(["2026-01-01 00:00:00", "2026-01-01 00:01:30"]))

    axis = axis_values(series)

    assert axis.values.tolist() == [0.0, 90.0]
    assert axis.label_suffix == "elapsed s"
