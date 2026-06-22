from __future__ import annotations

import numpy as np
import pandas as pd

from battery_aging_app.models import ImportedDataset, ImportWarning


def analyze_data_quality(dataset: ImportedDataset) -> list[ImportWarning]:
    frame = dataset.frame
    warnings: list[ImportWarning] = []

    for column in frame.columns:
        missing = int(frame[column].isna().sum())
        if missing:
            warnings.append(
                ImportWarning(
                    code="missing_values",
                    message=f"{missing} missing values in {column}.",
                    column=column,
                )
            )

    time_column = dataset.time_column
    if time_column not in frame:
        warnings.append(
            ImportWarning(
                code="missing_time_column",
                message="The selected time column is not present after import.",
                severity="error",
            )
        )
        return warnings

    time = frame[time_column].to_numpy(dtype=float)
    valid_time = time[~np.isnan(time)]
    if valid_time.size < 2:
        warnings.append(
            ImportWarning(
                code="insufficient_time_values",
                message="Fewer than two valid time values are available.",
                column=time_column,
                severity="error",
            )
        )
        return warnings

    duplicated = int(pd.Series(valid_time).duplicated().sum())
    if duplicated:
        warnings.append(
            ImportWarning(
                code="duplicate_timestamps",
                message=f"{duplicated} duplicate timestamps were found.",
                column=time_column,
            )
        )

    diff = np.diff(valid_time)
    non_monotonic = int(np.sum(diff < 0))
    if non_monotonic:
        warnings.append(
            ImportWarning(
                code="non_monotonic_time",
                message=f"{non_monotonic} backward time steps were found.",
                column=time_column,
            )
        )

    zero_steps = int(np.sum(diff == 0))
    if zero_steps:
        warnings.append(
            ImportWarning(
                code="duplicate_time_steps",
                message=f"{zero_steps} zero-length time steps were found.",
                column=time_column,
            )
        )

    positive_steps = diff[diff > 0]
    if positive_steps.size:
        median_step = float(np.median(positive_steps))
        if median_step > 0:
            large_gaps = int(np.sum(positive_steps > 5.0 * median_step))
            if large_gaps:
                warnings.append(
                    ImportWarning(
                        code="large_time_gaps",
                        message=(
                            f"{large_gaps} time gaps exceed five times the "
                            "median positive step."
                        ),
                        column=time_column,
                    )
                )
            if positive_steps.size > 2:
                spread = float(np.std(positive_steps) / median_step)
                if spread > 0.25:
                    warnings.append(
                        ImportWarning(
                            code="irregular_time_gaps",
                            message=(
                                "Time spacing is irregular; integration will use "
                                "actual time values."
                            ),
                            column=time_column,
                            severity="info",
                        )
                    )
    return warnings
