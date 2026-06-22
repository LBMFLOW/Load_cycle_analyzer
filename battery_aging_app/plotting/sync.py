from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from battery_aging_app.models import InterpolationMode


@dataclass(frozen=True, slots=True)
class TraceReadout:
    cursor_time: float
    row_index: int
    values: dict[str, float]
    mode: InterpolationMode


def nearest_index(time_values: np.ndarray | pd.Series, cursor_time: float) -> int:
    time = np.asarray(time_values, dtype=float)
    if time.size == 0:
        raise ValueError("Cannot find a trace index in an empty time array.")
    valid = ~np.isnan(time)
    if not valid.any():
        raise ValueError("Cannot find a trace index without valid time values.")
    valid_indexes = np.flatnonzero(valid)
    nearest_valid = int(np.argmin(np.abs(time[valid] - float(cursor_time))))
    return int(valid_indexes[nearest_valid])


def trace_values(
    frame: pd.DataFrame,
    *,
    time_column: str,
    value_columns: list[str],
    cursor_time: float,
    mode: InterpolationMode = "nearest",
) -> TraceReadout:
    row_index = nearest_index(frame[time_column], cursor_time)
    if mode == "nearest":
        values = {
            column: _float_or_nan(frame[column].iloc[row_index])
            for column in value_columns
            if column in frame
        }
        values[time_column] = _float_or_nan(frame[time_column].iloc[row_index])
        return TraceReadout(float(cursor_time), row_index, values, mode)

    values = {
        column: linear_interpolate(frame[time_column], frame[column], cursor_time)
        for column in value_columns
        if column in frame
    }
    values[time_column] = float(cursor_time)
    return TraceReadout(float(cursor_time), row_index, values, mode)


def linear_interpolate(
    time_values: np.ndarray | pd.Series,
    values: np.ndarray | pd.Series,
    cursor_time: float,
) -> float:
    x = np.asarray(time_values, dtype=float)
    y = np.asarray(values, dtype=float)
    valid = ~(np.isnan(x) | np.isnan(y))
    if int(valid.sum()) == 0:
        return np.nan
    xv = x[valid]
    yv = y[valid]
    order = np.argsort(xv)
    xv = xv[order]
    yv = yv[order]
    unique_x, unique_indexes = np.unique(xv, return_index=True)
    unique_y = yv[unique_indexes]
    if unique_x.size == 1:
        return float(unique_y[0])
    return float(np.interp(float(cursor_time), unique_x, unique_y))


def centered_table_window(
    *,
    row_count: int,
    selected_row: int,
    visible_rows: int,
) -> tuple[int, int]:
    if row_count <= 0 or visible_rows <= 0:
        return (0, 0)
    half = visible_rows // 2
    start = max(0, min(selected_row - half, row_count - visible_rows))
    end = min(row_count, start + visible_rows)
    return (int(start), int(end))


def _float_or_nan(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan
