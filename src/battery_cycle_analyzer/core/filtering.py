from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

OutlierMethod = Literal["none", "zscore", "iqr"]


@dataclass(frozen=True, slots=True)
class DataFilterOptions:
    time_column: str
    cycle_column: str | None = None
    time_min: float | None = None
    time_max: float | None = None
    cycle_min: float | None = None
    cycle_max: float | None = None
    remove_nan_rows: bool = False
    remove_duplicate_timestamps: bool = False
    duplicate_keep: Literal["first", "last"] = "first"
    outlier_method: OutlierMethod = "none"
    outlier_columns: tuple[str, ...] = ()
    zscore_threshold: float = 3.0
    iqr_multiplier: float = 1.5
    smoothing_window: int = 1
    smoothing_columns: tuple[str, ...] = ()
    preserve_raw: bool = True


@dataclass(slots=True)
class DataFilterResult:
    frame: pd.DataFrame
    raw_frame: pd.DataFrame | None = None
    removed_rows: int = 0
    warnings: list[str] = field(default_factory=list)


class DataFilterService:
    """Creates processed analysis views without mutating the source frame."""

    def apply(self, frame: pd.DataFrame, options: DataFilterOptions) -> DataFilterResult:
        processed = frame.copy()
        original_count = len(processed)
        warnings: list[str] = []

        if options.time_column in processed:
            time = pd.to_numeric(processed[options.time_column], errors="coerce")
            if options.time_min is not None:
                processed = processed.loc[time >= options.time_min]
                time = pd.to_numeric(processed[options.time_column], errors="coerce")
            if options.time_max is not None:
                processed = processed.loc[time <= options.time_max]
        else:
            warnings.append(f"Time column {options.time_column!r} is not available.")

        if options.cycle_column and options.cycle_column in processed:
            cycle = pd.to_numeric(processed[options.cycle_column], errors="coerce")
            if options.cycle_min is not None:
                processed = processed.loc[cycle >= options.cycle_min]
                cycle = pd.to_numeric(processed[options.cycle_column], errors="coerce")
            if options.cycle_max is not None:
                processed = processed.loc[cycle <= options.cycle_max]

        if options.remove_nan_rows:
            before = len(processed)
            processed = processed.dropna()
            if len(processed) != before:
                warnings.append(f"Removed {before - len(processed)} rows containing NaN.")

        if options.remove_duplicate_timestamps and options.time_column in processed:
            before = len(processed)
            processed = processed.drop_duplicates(
                subset=[options.time_column],
                keep=options.duplicate_keep,
            )
            if len(processed) != before:
                warnings.append(f"Removed {before - len(processed)} duplicate timestamps.")

        if options.outlier_method != "none":
            outlier_columns = [
                column for column in options.outlier_columns if column in processed
            ]
            if outlier_columns:
                mask = self._outlier_mask(processed, outlier_columns, options)
                removed = int(mask.sum())
                processed = processed.loc[~mask]
                if removed:
                    warnings.append(
                        f"Removed {removed} rows using {options.outlier_method} outlier detection."
                    )

        if options.smoothing_window > 1:
            for column in options.smoothing_columns:
                if column not in processed:
                    continue
                processed[f"{column}_smoothed"] = pd.to_numeric(
                    processed[column],
                    errors="coerce",
                ).rolling(
                    int(options.smoothing_window),
                    center=True,
                    min_periods=1,
                ).mean()

        return DataFilterResult(
            frame=processed.reset_index(drop=True),
            raw_frame=frame.copy() if options.preserve_raw else None,
            removed_rows=original_count - len(processed),
            warnings=warnings,
        )

    def _outlier_mask(
        self,
        frame: pd.DataFrame,
        columns: list[str],
        options: DataFilterOptions,
    ) -> pd.Series:
        mask = pd.Series(False, index=frame.index)
        for column in columns:
            values = pd.to_numeric(frame[column], errors="coerce")
            if options.outlier_method == "zscore":
                std = values.std()
                if std and not np.isnan(std):
                    mask |= ((values - values.mean()).abs() / std) > options.zscore_threshold
            elif options.outlier_method == "iqr":
                q1 = values.quantile(0.25)
                q3 = values.quantile(0.75)
                iqr = q3 - q1
                lower = q1 - options.iqr_multiplier * iqr
                upper = q3 + options.iqr_multiplier * iqr
                mask |= (values < lower) | (values > upper)
        return mask
