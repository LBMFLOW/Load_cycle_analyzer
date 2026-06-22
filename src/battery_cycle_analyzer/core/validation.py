from __future__ import annotations

import numpy as np
import pandas as pd

from battery_cycle_analyzer.core.data_model import LoadedDataset, ValidationIssue
from battery_cycle_analyzer.core.units import get_unit


class DatasetValidator:
    """Validates loaded numeric time-series data."""

    def validate(self, dataset: LoadedDataset) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        frame = dataset.frame
        for column in frame.columns:
            missing = int(frame[column].isna().sum())
            if missing:
                issues.append(
                    ValidationIssue(
                        "missing_values",
                        f"{missing} missing values in {column}.",
                        column=column,
                    )
                )
        issues.extend(self._validate_units(dataset))
        issues.extend(self._validate_time(frame[dataset.time_column], dataset.time_column))
        return issues

    def _validate_units(self, dataset: LoadedDataset) -> list[ValidationIssue]:
        allowed_freeform = {"", "%", "ratio", "cycle", "cycles", "relative"}
        issues: list[ValidationIssue] = []
        for column, unit in dataset.metadata.units.items():
            normalized = (unit or "").strip()
            if normalized in allowed_freeform:
                continue
            if get_unit(normalized) is None:
                issues.append(
                    ValidationIssue(
                        "unknown_unit",
                        f"Unit {normalized!r} on column {column} is not recognized.",
                        "warning",
                        column,
                    )
                )
        return issues

    def _validate_time(self, series: pd.Series, column: str) -> list[ValidationIssue]:
        if pd.api.types.is_datetime64_any_dtype(series):
            numeric_time = series.dropna().astype("int64").to_numpy(dtype=float)
            if numeric_time.size < 2:
                return [
                    ValidationIssue(
                        "insufficient_time",
                        "At least two valid time values are required.",
                        "error",
                        column,
                    )
                ]
            return self._validate_numeric_time(numeric_time, column)

        time = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
        valid = time[~np.isnan(time)]
        if valid.size < 2:
            return [
                ValidationIssue(
                    "insufficient_time",
                    "At least two valid time values are required.",
                    "error",
                    column,
                )
            ]

        return self._validate_numeric_time(valid, column)

    def _validate_numeric_time(
        self, valid: np.ndarray, column: str
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        duplicates = int(pd.Series(valid).duplicated().sum())
        if duplicates:
            issues.append(
                ValidationIssue(
                    "duplicate_timestamps",
                    f"{duplicates} duplicate timestamps were found.",
                    column=column,
                )
            )
        diff = np.diff(valid)
        if np.any(diff < 0):
            issues.append(
                ValidationIssue(
                    "non_monotonic_time",
                    "Time values are not monotonic.",
                    column=column,
                )
            )
        positive = diff[diff > 0]
        if positive.size:
            median = float(np.median(positive))
            if median > 0 and np.any(positive > 5.0 * median):
                issues.append(
                    ValidationIssue(
                        "large_time_gap",
                        "Large gaps were detected in the time column.",
                        "info",
                        column,
                    )
                )
        return issues
