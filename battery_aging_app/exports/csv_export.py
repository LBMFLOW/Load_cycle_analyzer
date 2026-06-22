from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from battery_aging_app.analysis.sections import section_mask
from battery_aging_app.models import ImportedDataset, Section


def section_dataframe(
    dataset: ImportedDataset,
    section: Section,
    *,
    curves: list[str],
) -> pd.DataFrame:
    frame = dataset.frame
    time_column = dataset.time_column
    mask = section_mask(frame[time_column].to_numpy(dtype=float), section)
    section_frame = frame.loc[mask].copy()
    if section_frame.empty:
        return pd.DataFrame(columns=["relative_time", time_column, *curves])

    columns = [time_column]
    for curve in curves:
        if curve != time_column and curve in section_frame and curve not in columns:
            columns.append(curve)
    exported = section_frame[columns].copy()
    exported.insert(
        0,
        "relative_time",
        exported[time_column].astype(float) - float(exported[time_column].iloc[0]),
    )
    return exported.reset_index(drop=True)


def export_section_csv(
    dataset: ImportedDataset,
    section: Section,
    path: str | Path,
    *,
    curves: list[str],
    metadata_sidecar: bool = True,
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    exported = section_dataframe(dataset, section, curves=curves)
    exported.to_csv(output_path, index=False)
    if metadata_sidecar:
        sidecar_path = output_path.with_suffix(output_path.suffix + ".metadata.json")
        with sidecar_path.open("w", encoding="utf-8") as handle:
            json.dump(
                {
                    "source_file": dataset.metadata.source_file,
                    "units": {
                        column: dataset.metadata.units.get(column, "")
                        for column in exported.columns
                    },
                    "selected_rows": dataset.metadata.selected_rows,
                    "section": section.to_dict(),
                    "exported_columns": exported.columns.tolist(),
                    "export_timestamp": datetime.now(timezone.utc).isoformat(),
                },
                handle,
                indent=2,
            )
    return output_path


def export_processed_dataset(
    frame: pd.DataFrame,
    path: str | Path,
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_path, index=False)
    return output_path
