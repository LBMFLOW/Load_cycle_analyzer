from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

from battery_cycle_analyzer.core.data_model import LoadedDataset, Section
from battery_cycle_analyzer.core.sections import SectionManager

BaselineMode = Literal["first", "mean_first_n", "section", "manual"]
CycleEstimationMode = Literal["row_number", "event_structure"]


@dataclass(frozen=True, slots=True)
class BaselineConfig:
    mode: BaselineMode = "first"
    first_n: int = 5
    manual_value: float | None = None


@dataclass(frozen=True, slots=True)
class DerivedMetricOptions:
    discharge_column: str | None = None
    charge_column: str | None = None
    time_column: str | None = None
    cycle_column: str | None = None
    baseline: BaselineConfig = field(default_factory=BaselineConfig)
    rolling_window: int = 5
    cycle_estimation: CycleEstimationMode = "row_number"


@dataclass(slots=True)
class DerivedMetricResult:
    frame: pd.DataFrame
    warnings: list[str] = field(default_factory=list)
    baseline_values: dict[str, float] = field(default_factory=dict)
    created_columns: list[str] = field(default_factory=list)
    cycle_column: str | None = None


class DerivedMetricsService:
    """Pure battery-aging derived metrics calculations."""

    def compute(
        self,
        dataset: LoadedDataset,
        options: DerivedMetricOptions | None = None,
        *,
        baseline_section: Section | None = None,
        axis_values=None,
    ) -> DerivedMetricResult:
        options = options or DerivedMetricOptions()
        frame = dataset.frame.copy()
        warnings: list[str] = []
        created: list[str] = []
        baseline_values: dict[str, float] = {}

        time_column = options.time_column or dataset.time_column
        discharge = options.discharge_column or dataset.discharge_energy_column
        charge = options.charge_column or dataset.charge_energy_column
        cycle_column = self.resolve_cycle_column(
            frame,
            options.cycle_column,
            mode=options.cycle_estimation,
            charge_column=charge,
            discharge_column=discharge,
        )
        if cycle_column not in frame:
            frame[cycle_column] = self.estimate_cycle_index(
                frame,
                mode=options.cycle_estimation,
                charge_column=charge,
                discharge_column=discharge,
            )
            created.append(cycle_column)

        for source_column, prefix in [(discharge, "discharge"), (charge, "charge")]:
            if source_column is None or source_column not in frame:
                continue
            series = pd.to_numeric(frame[source_column], errors="coerce")
            baseline = self.baseline_value(
                series,
                options.baseline,
                section=baseline_section,
                axis_values=axis_values,
                time_values=frame[time_column] if time_column in frame else None,
            )
            baseline_values[source_column] = baseline

            retention = f"{prefix}_energy_retention_pct"
            fade = f"{prefix}_percent_energy_fade"
            rolling_mean = f"{prefix}_rolling_mean"
            rolling_std = f"{prefix}_rolling_std"
            slope = f"{prefix}_slope_over_time"
            delta = f"{prefix}_cycle_delta"
            frame[retention] = self.energy_retention(series, baseline)
            frame[fade] = self.percent_fade(series, baseline)
            frame[rolling_mean] = self.rolling_mean(series, options.rolling_window)
            frame[rolling_std] = self.rolling_std(series, options.rolling_window)
            frame[slope] = self.derivative_over_time(
                series,
                frame[time_column] if time_column in frame else pd.Series(frame.index),
            )
            frame[delta] = self.cycle_to_cycle_delta(series)
            created.extend([retention, fade, rolling_mean, rolling_std, slope, delta])

        if discharge and charge and discharge in frame and charge in frame:
            frame["energy_efficiency"] = self.energy_efficiency(
                frame[discharge],
                frame[charge],
            )
            frame["energy_loss"] = self.energy_loss(frame[discharge], frame[charge])
            created.extend(["energy_efficiency", "energy_loss"])
            efficiency = pd.to_numeric(frame["energy_efficiency"], errors="coerce")
            suspicious = int((efficiency > 1.0).sum())
            if suspicious:
                warnings.append(
                    f"{suspicious} efficiency values are greater than 100%."
                )

        return DerivedMetricResult(
            frame=frame,
            warnings=warnings,
            baseline_values=baseline_values,
            created_columns=self._unique(created),
            cycle_column=cycle_column,
        )

    def baseline_value(
        self,
        series: pd.Series,
        config: BaselineConfig,
        *,
        section: Section | None = None,
        axis_values=None,
        time_values: pd.Series | None = None,
    ) -> float:
        numeric = pd.to_numeric(series, errors="coerce")
        if config.mode == "manual":
            return float(config.manual_value) if config.manual_value is not None else np.nan
        if config.mode == "mean_first_n":
            count = max(1, int(config.first_n))
            return float(numeric.dropna().iloc[:count].mean())
        if config.mode == "section" and section is not None:
            mask_source = axis_values if axis_values is not None else time_values
            if mask_source is not None:
                mask = SectionManager().mask(mask_source, section)
                values = numeric.loc[mask].dropna()
                return float(values.mean()) if not values.empty else np.nan
        valid = numeric.dropna()
        return float(valid.iloc[0]) if not valid.empty else np.nan

    def energy_retention(self, series: pd.Series, baseline: float) -> pd.Series:
        numeric = pd.to_numeric(series, errors="coerce")
        if baseline == 0 or np.isnan(baseline):
            return pd.Series(np.nan, index=series.index, name="energy_retention_pct")
        return (numeric / baseline * 100.0).rename("energy_retention_pct")

    def percent_fade(self, series: pd.Series, baseline: float) -> pd.Series:
        retention = self.energy_retention(series, baseline)
        return (100.0 - retention).rename("percent_energy_fade")

    def energy_efficiency(self, discharge: pd.Series, charge: pd.Series) -> pd.Series:
        efficiency = pd.to_numeric(discharge, errors="coerce") / pd.to_numeric(
            charge, errors="coerce"
        )
        return efficiency.replace([np.inf, -np.inf], np.nan).rename("energy_efficiency")

    def energy_loss(self, discharge: pd.Series, charge: pd.Series) -> pd.Series:
        return (
            pd.to_numeric(charge, errors="coerce")
            - pd.to_numeric(discharge, errors="coerce")
        ).rename("energy_loss")

    def rolling_mean(self, series: pd.Series, window: int) -> pd.Series:
        return pd.to_numeric(series, errors="coerce").rolling(
            max(1, int(window)),
            center=True,
            min_periods=1,
        ).mean()

    def rolling_std(self, series: pd.Series, window: int) -> pd.Series:
        return pd.to_numeric(series, errors="coerce").rolling(
            max(1, int(window)),
            center=True,
            min_periods=1,
        ).std()

    def derivative_over_time(self, series: pd.Series, time_values: pd.Series) -> pd.Series:
        y = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
        x = self._numeric_time_values(time_values)
        output = np.full(len(series), np.nan, dtype=float)
        valid = ~(np.isnan(x) | np.isnan(y))
        if int(valid.sum()) < 2:
            return pd.Series(output, index=series.index, name="slope_over_time")
        valid_indexes = np.flatnonzero(valid)
        xv = x[valid]
        yv = y[valid]
        if np.unique(xv).size < 2:
            return pd.Series(output, index=series.index, name="slope_over_time")
        output[valid_indexes] = np.gradient(yv, xv)
        return pd.Series(output, index=series.index, name="slope_over_time")

    def cycle_to_cycle_delta(self, series: pd.Series) -> pd.Series:
        return pd.to_numeric(series, errors="coerce").diff().rename("cycle_delta")

    def resolve_cycle_column(
        self,
        frame: pd.DataFrame,
        cycle_column: str | None,
        *,
        mode: CycleEstimationMode,
        charge_column: str | None = None,
        discharge_column: str | None = None,
    ) -> str:
        if cycle_column and cycle_column in frame:
            return cycle_column
        for column in frame.columns:
            label = str(column).casefold()
            if "cycle" in label and pd.api.types.is_numeric_dtype(frame[column]):
                return str(column)
        return "estimated_cycle_index"

    def estimate_cycle_index(
        self,
        frame: pd.DataFrame,
        *,
        mode: CycleEstimationMode = "row_number",
        charge_column: str | None = None,
        discharge_column: str | None = None,
    ) -> pd.Series:
        if mode == "event_structure":
            source_column = discharge_column if discharge_column in frame else charge_column
            if source_column in frame:
                values = pd.to_numeric(frame[source_column], errors="coerce")
                direction = np.sign(values.diff().fillna(0.0).to_numpy(dtype=float))
                changes = np.r_[False, direction[1:] * direction[:-1] < 0]
                cycle = np.cumsum(changes).astype(int) + 1
                return pd.Series(cycle, index=frame.index, name="estimated_cycle_index")
        return pd.Series(np.arange(1, len(frame) + 1), index=frame.index, name="estimated_cycle_index")

    def _numeric_time_values(self, series: pd.Series) -> np.ndarray:
        if pd.api.types.is_datetime64_any_dtype(series):
            datetime = pd.to_datetime(series, errors="coerce")
            valid = datetime.dropna()
            if valid.empty:
                return np.full(len(series), np.nan, dtype=float)
            return (datetime - valid.iloc[0]).dt.total_seconds().to_numpy(dtype=float)
        return pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)

    def _unique(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        output: list[str] = []
        for value in values:
            if value not in seen:
                seen.add(value)
                output.append(value)
        return output
