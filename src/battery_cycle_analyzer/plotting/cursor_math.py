from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True, slots=True)
class AxisData:
    values: np.ndarray
    display_values: pd.Series
    label_suffix: str = ""


def axis_values(series: pd.Series, *, normalize: bool = False) -> AxisData:
    """Return numeric x-axis values suitable for plotting and cursor lookup.

    Datetime columns are converted to elapsed seconds internally. Numeric
    columns may optionally be normalized to start at zero.
    """

    display = series.reset_index(drop=True)
    if pd.api.types.is_datetime64_any_dtype(series):
        datetime = pd.to_datetime(series, errors="coerce")
        valid = datetime.dropna()
        if valid.empty:
            numeric = np.full(len(series), np.nan, dtype=float)
        else:
            numeric = (datetime - valid.iloc[0]).dt.total_seconds().to_numpy(dtype=float)
        return AxisData(numeric, display, "elapsed s")

    numeric_series = pd.to_numeric(series, errors="coerce")
    numeric = numeric_series.to_numpy(dtype=float)
    if normalize:
        valid = numeric[~np.isnan(numeric)]
        if valid.size:
            numeric = numeric - float(valid[0])
        return AxisData(numeric, display, "relative")
    return AxisData(numeric, display)


def nearest_row_index(axis: np.ndarray, cursor_value: float) -> int:
    """Find nearest row using binary search on monotonic sorted x values."""

    values = np.asarray(axis, dtype=float)
    valid_mask = ~np.isnan(values)
    if not valid_mask.any():
        return -1

    valid_indexes = np.flatnonzero(valid_mask)
    valid_values = values[valid_mask]
    order = np.argsort(valid_values)
    sorted_values = valid_values[order]
    sorted_indexes = valid_indexes[order]

    position = int(np.searchsorted(sorted_values, float(cursor_value), side="left"))
    if position <= 0:
        return int(sorted_indexes[0])
    if position >= sorted_values.size:
        return int(sorted_indexes[-1])

    before = sorted_values[position - 1]
    after = sorted_values[position]
    if abs(float(cursor_value) - before) <= abs(after - float(cursor_value)):
        return int(sorted_indexes[position - 1])
    return int(sorted_indexes[position])


def linear_interpolate(axis: np.ndarray, values: np.ndarray, cursor_value: float) -> float:
    x = np.asarray(axis, dtype=float)
    y = np.asarray(values, dtype=float)
    valid = ~(np.isnan(x) | np.isnan(y))
    if not valid.any():
        return float("nan")
    xv = x[valid]
    yv = y[valid]
    order = np.argsort(xv)
    xv = xv[order]
    yv = yv[order]
    unique_x, unique_indexes = np.unique(xv, return_index=True)
    unique_y = yv[unique_indexes]
    if unique_x.size == 1:
        return float(unique_y[0])
    return float(np.interp(float(cursor_value), unique_x, unique_y))
