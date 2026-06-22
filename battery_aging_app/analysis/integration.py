from __future__ import annotations

from dataclasses import dataclass

import numpy as np

try:
    from scipy.integrate import trapezoid
except Exception:  # pragma: no cover - scipy is a declared dependency.
    trapezoid = np.trapz

from battery_aging_app.analysis.sections import section_mask
from battery_aging_app.models import ImportedDataset, ImportWarning, Section


@dataclass(frozen=True, slots=True)
class IntegrationResult:
    curve_name: str
    curve_unit: str
    time_unit: str
    time_start: float
    time_end: float
    point_count: int
    integral_value: float

    @property
    def integral_unit(self) -> str:
        if self.curve_unit and self.time_unit:
            return f"{self.curve_unit}*{self.time_unit}"
        return self.curve_unit or "curve*time"


def integrate_visible_curves(
    dataset: ImportedDataset,
    *,
    visible_curves: list[str],
    section: Section | None = None,
) -> tuple[list[IntegrationResult], list[ImportWarning]]:
    frame = dataset.frame
    time_column = dataset.time_column
    time = frame[time_column].to_numpy(dtype=float)

    mask = ~np.isnan(time)
    if section is not None:
        mask &= section_mask(time, section)

    warnings = validate_time_for_integration(time[mask], time_column)
    results: list[IntegrationResult] = []
    time_unit = dataset.metadata.units.get(time_column, "")

    for curve_name in visible_curves:
        if curve_name == time_column or curve_name not in frame:
            continue
        values = frame[curve_name].to_numpy(dtype=float)
        curve_mask = mask & ~np.isnan(values)
        if int(curve_mask.sum()) < 2:
            warnings.append(
                ImportWarning(
                    code="integration_insufficient_points",
                    message=f"Not enough valid points to integrate {curve_name}.",
                    column=curve_name,
                )
            )
            continue
        x = time[curve_mask]
        y = values[curve_mask]
        results.append(
            IntegrationResult(
                curve_name=curve_name,
                curve_unit=dataset.metadata.units.get(curve_name, ""),
                time_unit=time_unit,
                time_start=float(x[0]),
                time_end=float(x[-1]),
                point_count=int(x.size),
                integral_value=float(trapezoid(y, x)),
            )
        )
    return results, warnings


def validate_time_for_integration(
    time_values: np.ndarray, column_name: str = "time"
) -> list[ImportWarning]:
    time = np.asarray(time_values, dtype=float)
    warnings: list[ImportWarning] = []
    if time.size < 2:
        return [
            ImportWarning(
                code="integration_insufficient_time",
                message="Integration needs at least two valid time values.",
                column=column_name,
                severity="error",
            )
        ]
    if np.isnan(time).any():
        warnings.append(
            ImportWarning(
                code="integration_missing_time",
                message="Missing time values were ignored during integration.",
                column=column_name,
            )
        )
    diff = np.diff(time[~np.isnan(time)])
    if np.any(diff < 0):
        warnings.append(
            ImportWarning(
                code="integration_non_monotonic_time",
                message="Time is not monotonic; trapezoidal integration follows row order.",
                column=column_name,
            )
        )
    if np.any(diff == 0):
        warnings.append(
            ImportWarning(
                code="integration_duplicate_time",
                message="Duplicate time values can overweight repeated samples.",
                column=column_name,
            )
        )
    positive = diff[diff > 0]
    if positive.size:
        median = float(np.median(positive))
        if median > 0 and np.any(positive > 5.0 * median):
            warnings.append(
                ImportWarning(
                    code="integration_large_gaps",
                    message="Large time gaps were detected in the integration range.",
                    column=column_name,
                )
            )
        if median > 0 and positive.size > 2 and float(np.std(positive) / median) > 0.25:
            warnings.append(
                ImportWarning(
                    code="integration_irregular_gaps",
                    message="Time spacing is irregular; actual time values were used.",
                    column=column_name,
                    severity="info",
                )
            )
    return warnings
