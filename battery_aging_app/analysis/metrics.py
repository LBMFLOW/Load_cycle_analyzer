from __future__ import annotations

import numpy as np
import pandas as pd


def energy_retention(series: pd.Series, baseline: float | None = None) -> pd.Series:
    base = _baseline(series, baseline)
    if base == 0 or np.isnan(base):
        return pd.Series(np.nan, index=series.index, name=f"{series.name} retention")
    return (series.astype(float) / base * 100.0).rename(f"{series.name} retention")


def energy_efficiency(
    discharge_energy: pd.Series, charge_energy: pd.Series
) -> pd.Series:
    efficiency = discharge_energy.astype(float) / charge_energy.astype(float)
    return efficiency.replace([np.inf, -np.inf], np.nan).rename("Energy efficiency")


def percent_fade(series: pd.Series, baseline: float | None = None) -> pd.Series:
    retention = energy_retention(series, baseline)
    return (100.0 - retention).rename(f"{series.name} percent fade")


def estimate_cycle_index(
    frame: pd.DataFrame,
    cycle_column: str | None = None,
    samples_per_cycle: int | None = None,
) -> pd.Series:
    if cycle_column and cycle_column in frame:
        return pd.to_numeric(frame[cycle_column], errors="coerce").rename("Cycle")
    if samples_per_cycle and samples_per_cycle > 1:
        values = np.floor(np.arange(len(frame)) / samples_per_cycle) + 1
    else:
        values = np.arange(1, len(frame) + 1)
    return pd.Series(values.astype(int), index=frame.index, name="Cycle")


def rolling_average(series: pd.Series, window: int) -> pd.Series:
    if window <= 1:
        return series.astype(float).copy()
    return series.astype(float).rolling(window=window, center=True, min_periods=1).mean()


def derivative_over_time(values: pd.Series, time: pd.Series) -> pd.Series:
    y = values.to_numpy(dtype=float)
    x = time.to_numpy(dtype=float)
    derivative = np.full_like(y, np.nan, dtype=float)
    valid = ~(np.isnan(x) | np.isnan(y))
    if int(valid.sum()) >= 2:
        derivative[valid] = np.gradient(y[valid], x[valid])
    return pd.Series(derivative, index=values.index, name=f"{values.name} slope")


def section_statistics(values: pd.Series, time: pd.Series | None = None) -> dict[str, float]:
    numeric = values.astype(float).dropna()
    stats = {
        "min": float(numeric.min()) if not numeric.empty else np.nan,
        "max": float(numeric.max()) if not numeric.empty else np.nan,
        "mean": float(numeric.mean()) if not numeric.empty else np.nan,
        "median": float(numeric.median()) if not numeric.empty else np.nan,
        "std": float(numeric.std(ddof=1)) if len(numeric) > 1 else np.nan,
        "start": float(numeric.iloc[0]) if not numeric.empty else np.nan,
        "end": float(numeric.iloc[-1]) if not numeric.empty else np.nan,
    }
    stats["delta"] = stats["end"] - stats["start"]
    if time is not None and len(numeric) >= 2:
        aligned_time = time.loc[numeric.index].astype(float)
        dt = float(aligned_time.iloc[-1] - aligned_time.iloc[0])
        stats["slope"] = stats["delta"] / dt if dt != 0 else np.nan
    else:
        stats["slope"] = np.nan
    return stats


def add_standard_metrics(
    frame: pd.DataFrame,
    *,
    time_column: str,
    discharge_column: str | None,
    charge_column: str | None,
    smoothing_window: int = 5,
) -> pd.DataFrame:
    enriched = frame.copy()
    if discharge_column and discharge_column in enriched:
        enriched[f"{discharge_column} retention (%)"] = energy_retention(
            enriched[discharge_column]
        )
        enriched[f"{discharge_column} fade (%)"] = percent_fade(enriched[discharge_column])
        enriched[f"{discharge_column} rolling avg"] = rolling_average(
            enriched[discharge_column], smoothing_window
        )
        enriched[f"{discharge_column} slope"] = derivative_over_time(
            enriched[discharge_column], enriched[time_column]
        )
    if charge_column and charge_column in enriched:
        enriched[f"{charge_column} retention (%)"] = energy_retention(
            enriched[charge_column]
        )
        enriched[f"{charge_column} fade (%)"] = percent_fade(enriched[charge_column])
        enriched[f"{charge_column} rolling avg"] = rolling_average(
            enriched[charge_column], smoothing_window
        )
        enriched[f"{charge_column} slope"] = derivative_over_time(
            enriched[charge_column], enriched[time_column]
        )
    if discharge_column and charge_column and {discharge_column, charge_column} <= set(
        enriched.columns
    ):
        enriched["Energy efficiency"] = energy_efficiency(
            enriched[discharge_column], enriched[charge_column]
        )
    if "Cycle" not in enriched:
        enriched["Cycle"] = estimate_cycle_index(enriched)
    return enriched


def _baseline(series: pd.Series, baseline: float | None) -> float:
    if baseline is not None:
        return float(baseline)
    numeric = series.astype(float).dropna()
    return float(numeric.iloc[0]) if not numeric.empty else np.nan
