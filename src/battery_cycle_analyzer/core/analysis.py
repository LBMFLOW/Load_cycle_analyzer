from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
from scipy.integrate import trapezoid

from battery_cycle_analyzer.core.data_model import (
    IntegrationResult,
    LoadedDataset,
    Section,
    SectionStatistics,
)
from battery_cycle_analyzer.core.sections import SectionManager

MissingValuePolicy = Literal["drop", "interpolate", "cancel"]
TimeOrderPolicy = Literal["continue", "sort"]
DuplicateTimePolicy = Literal["continue", "aggregate", "keep_first", "keep_last"]


@dataclass(frozen=True, slots=True)
class AnalysisOptions:
    missing_value_policy: MissingValuePolicy = "drop"
    time_order_policy: TimeOrderPolicy = "continue"
    duplicate_time_policy: DuplicateTimePolicy = "continue"


@dataclass(frozen=True, slots=True)
class SelectionDiagnostics:
    time_not_monotonic: bool = False
    duplicate_timestamps: bool = False
    missing_values: bool = False
    selected_points: int = 0


@dataclass(slots=True)
class PreparedCurveData:
    x: np.ndarray
    y: np.ndarray
    missing_points: int
    warnings: list[str]


class AnalysisService:
    """Numerical battery-aging analysis operations."""

    def integrate(
        self,
        dataset: LoadedDataset,
        curve_columns: list[str],
        section: Section | None = None,
        *,
        axis_values=None,
        axis_unit: str | None = None,
        options: AnalysisOptions | None = None,
        curve_names: dict[str, str] | None = None,
    ) -> list[IntegrationResult]:
        options = options or AnalysisOptions()
        frame = dataset.frame
        mask, axis = self._selection_mask_and_axis(dataset, section, axis_values)
        time_unit = self._time_unit(dataset, axis_values=axis_values, axis_unit=axis_unit)
        results: list[IntegrationResult] = []

        for column in curve_columns:
            if column == dataset.time_column or column not in frame:
                continue
            prepared = self._prepare_curve(
                axis[mask],
                pd.to_numeric(frame.loc[mask, column], errors="coerce").to_numpy(dtype=float),
                options,
            )
            if prepared.x.size < 2:
                continue
            results.append(
                IntegrationResult(
                    curve_name=(curve_names or {}).get(column, column),
                    curve_unit=dataset.metadata.units.get(column, ""),
                    time_unit=time_unit,
                    start_time=float(prepared.x[0]),
                    end_time=float(prepared.x[-1]),
                    point_count=int(prepared.x.size),
                    value=float(trapezoid(prepared.y, prepared.x)),
                    warnings=prepared.warnings,
                )
            )
        return results

    def section_statistics(
        self,
        dataset: LoadedDataset,
        curve_columns: list[str],
        section: Section | None = None,
        *,
        axis_values=None,
        axis_unit: str | None = None,
        options: AnalysisOptions | None = None,
        curve_names: dict[str, str] | None = None,
    ) -> list[SectionStatistics]:
        options = options or AnalysisOptions()
        frame = dataset.frame
        mask, axis = self._selection_mask_and_axis(dataset, section, axis_values)
        time_unit = self._time_unit(dataset, axis_values=axis_values, axis_unit=axis_unit)
        stats: list[SectionStatistics] = []

        for column in curve_columns:
            if column == dataset.time_column or column not in frame:
                continue
            prepared = self._prepare_curve(
                axis[mask],
                pd.to_numeric(frame.loc[mask, column], errors="coerce").to_numpy(dtype=float),
                options,
            )
            if prepared.y.size == 0:
                continue
            stats.append(
                self._statistics_for_curve(
                    prepared,
                    curve_name=(curve_names or {}).get(column, column),
                    curve_unit=dataset.metadata.units.get(column, ""),
                    time_unit=time_unit,
                )
            )
        return stats

    def selection_diagnostics(
        self,
        dataset: LoadedDataset,
        curve_columns: list[str],
        section: Section | None = None,
        *,
        axis_values=None,
    ) -> SelectionDiagnostics:
        frame = dataset.frame
        mask, axis = self._selection_mask_and_axis(dataset, section, axis_values)
        selected_axis = axis[mask]
        selected_points = int(selected_axis.size)
        valid_axis = selected_axis[~np.isnan(selected_axis)]
        time_not_monotonic = bool(
            valid_axis.size > 1 and np.any(np.diff(valid_axis) < 0)
        )
        duplicate_timestamps = bool(
            valid_axis.size > 1 and pd.Series(valid_axis).duplicated().any()
        )
        missing_values = bool(np.isnan(selected_axis).any())
        for column in curve_columns:
            if column not in frame:
                continue
            values = pd.to_numeric(frame.loc[mask, column], errors="coerce")
            missing_values = missing_values or bool(values.isna().any())
        return SelectionDiagnostics(
            time_not_monotonic=time_not_monotonic,
            duplicate_timestamps=duplicate_timestamps,
            missing_values=missing_values,
            selected_points=selected_points,
        )

    def energy_retention(self, series: pd.Series) -> pd.Series:
        numeric = pd.to_numeric(series, errors="coerce")
        baseline = numeric.dropna().iloc[0] if not numeric.dropna().empty else np.nan
        return (numeric / baseline * 100.0).rename(f"{series.name} retention")

    def energy_efficiency(self, discharge: pd.Series, charge: pd.Series) -> pd.Series:
        efficiency = pd.to_numeric(discharge, errors="coerce") / pd.to_numeric(
            charge, errors="coerce"
        )
        return efficiency.replace([np.inf, -np.inf], np.nan).rename("energy_efficiency")

    def rolling_average(self, series: pd.Series, window: int) -> pd.Series:
        return pd.to_numeric(series, errors="coerce").rolling(
            window=window, center=True, min_periods=1
        ).mean()

    def _selection_mask_and_axis(
        self,
        dataset: LoadedDataset,
        section: Section | None,
        axis_values,
    ) -> tuple[np.ndarray, np.ndarray]:
        axis = (
            np.asarray(axis_values, dtype=float)
            if axis_values is not None
            else self._time_values(dataset.frame[dataset.time_column])
        )
        mask_source = axis_values if axis_values is not None else dataset.frame[dataset.time_column]
        mask = SectionManager().mask(mask_source, section)
        return mask, axis

    def _prepare_curve(
        self,
        x_values: np.ndarray,
        y_values: np.ndarray,
        options: AnalysisOptions,
    ) -> PreparedCurveData:
        x = np.asarray(x_values, dtype=float)
        y = np.asarray(y_values, dtype=float)
        warnings: list[str] = []

        missing_x = np.isnan(x)
        missing_y = np.isnan(y)
        missing_points = int((missing_x | missing_y).sum())
        if missing_points:
            if options.missing_value_policy == "cancel":
                return PreparedCurveData(
                    np.array([], dtype=float),
                    np.array([], dtype=float),
                    missing_points,
                    ["Missing values were found; integration was cancelled."],
                )
            if options.missing_value_policy == "interpolate":
                warnings.append("Missing y values were interpolated where possible.")
                x, y = self._interpolate_missing_y(x, y)
            else:
                warnings.append("Rows with missing x or y values were dropped.")
                valid = ~(missing_x | missing_y)
                x = x[valid]
                y = y[valid]

        duplicate_timestamps = self._has_duplicates(x)
        if duplicate_timestamps:
            x, y = self._handle_duplicates(x, y, options.duplicate_time_policy)
            if options.duplicate_time_policy == "aggregate":
                warnings.append("Duplicate timestamps were aggregated by mean.")
            elif options.duplicate_time_policy == "keep_first":
                warnings.append("Duplicate timestamps were reduced by keeping first values.")
            elif options.duplicate_time_policy == "keep_last":
                warnings.append("Duplicate timestamps were reduced by keeping last values.")
            else:
                warnings.append("Duplicate timestamps are present.")

        if self._is_not_monotonic(x):
            if options.time_order_policy == "sort":
                order = np.argsort(x, kind="mergesort")
                x = x[order]
                y = y[order]
                warnings.append("Time values were sorted before analysis.")
            else:
                warnings.append("Time values are not monotonic.")

        if x.size < 2:
            warnings.append("Fewer than 2 valid points are available.")
        return PreparedCurveData(x, y, missing_points, warnings)

    def _statistics_for_curve(
        self,
        prepared: PreparedCurveData,
        *,
        curve_name: str,
        curve_unit: str,
        time_unit: str,
    ) -> SectionStatistics:
        x = prepared.x
        y = prepared.y
        start_value = float(y[0])
        end_value = float(y[-1])
        delta = end_value - start_value
        percent_change = (
            float(delta / start_value * 100.0)
            if start_value not in (0.0, -0.0) and not np.isnan(start_value)
            else float("nan")
        )
        slope = float(np.polyfit(x, y, 1)[0]) if x.size >= 2 else float("nan")
        integral = float(trapezoid(y, x)) if x.size >= 2 else float("nan")
        return SectionStatistics(
            curve_name=curve_name,
            curve_unit=curve_unit,
            time_unit=time_unit,
            start_time=float(x[0]),
            end_time=float(x[-1]),
            start_value=start_value,
            end_value=end_value,
            delta=float(delta),
            percent_change=percent_change,
            minimum=float(np.min(y)),
            maximum=float(np.max(y)),
            mean=float(np.mean(y)),
            median=float(np.median(y)),
            standard_deviation=float(pd.Series(y).std()) if y.size > 1 else 0.0,
            slope=slope,
            integral=integral,
            valid_points=int(y.size),
            missing_points=prepared.missing_points,
            warnings=prepared.warnings,
        )

    def _interpolate_missing_y(
        self,
        x: np.ndarray,
        y: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        valid_x = ~np.isnan(x)
        x = x[valid_x]
        y = y[valid_x]
        if y.size == 0:
            return x, y
        series = pd.Series(y)
        if int(series.notna().sum()) >= 2:
            y = series.interpolate(limit_direction="both").to_numpy(dtype=float)
        valid = ~np.isnan(y)
        return x[valid], y[valid]

    def _handle_duplicates(
        self,
        x: np.ndarray,
        y: np.ndarray,
        policy: DuplicateTimePolicy,
    ) -> tuple[np.ndarray, np.ndarray]:
        if policy == "continue":
            return x, y
        frame = pd.DataFrame({"x": x, "y": y})
        grouped = frame.groupby("x", sort=False, as_index=False)
        if policy == "aggregate":
            reduced = grouped.mean(numeric_only=True)
        elif policy == "keep_last":
            reduced = grouped.last()
        else:
            reduced = grouped.first()
        return reduced["x"].to_numpy(dtype=float), reduced["y"].to_numpy(dtype=float)

    def _has_duplicates(self, values: np.ndarray) -> bool:
        if values.size < 2:
            return False
        valid = values[~np.isnan(values)]
        return bool(pd.Series(valid).duplicated().any())

    def _is_not_monotonic(self, values: np.ndarray) -> bool:
        valid = values[~np.isnan(values)]
        return bool(valid.size > 1 and np.any(np.diff(valid) < 0))

    def _time_values(self, series: pd.Series) -> np.ndarray:
        if pd.api.types.is_datetime64_any_dtype(series):
            datetime = pd.to_datetime(series, errors="coerce")
            valid = datetime.dropna()
            if valid.empty:
                return np.full(len(series), np.nan, dtype=float)
            return (datetime - valid.iloc[0]).dt.total_seconds().to_numpy(dtype=float)
        return pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)

    def _time_unit(
        self,
        dataset: LoadedDataset,
        *,
        axis_values,
        axis_unit: str | None,
    ) -> str:
        if axis_values is not None:
            return axis_unit or "x"
        time_column = dataset.time_column
        if pd.api.types.is_datetime64_any_dtype(dataset.frame[time_column]):
            return "s"
        return dataset.metadata.units.get(time_column, "") or axis_unit or "s"
