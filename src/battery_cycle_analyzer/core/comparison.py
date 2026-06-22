from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from battery_cycle_analyzer.core.data_model import LoadedDataset
from battery_cycle_analyzer.core.derived_metrics import (
    BaselineConfig,
    DerivedMetricOptions,
    DerivedMetricsService,
)


@dataclass(slots=True)
class ComparisonDataset:
    name: str
    dataset: LoadedDataset
    metrics_frame: pd.DataFrame | None = None


@dataclass(slots=True)
class ComparisonResult:
    overlay_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    warnings: list[str] = field(default_factory=list)


class ComparisonService:
    """Builds multi-file retention overlays and summaries."""

    def compare_discharge_retention(
        self,
        datasets: list[ComparisonDataset],
        *,
        baseline: BaselineConfig | None = None,
    ) -> ComparisonResult:
        service = DerivedMetricsService()
        overlay_parts: list[pd.DataFrame] = []
        summary_rows: list[dict[str, object]] = []
        warnings: list[str] = []

        for item in datasets:
            discharge = item.dataset.discharge_energy_column
            charge = item.dataset.charge_energy_column
            if discharge is None or discharge not in item.dataset.frame:
                warnings.append(f"{item.name}: no discharge energy column is mapped.")
                continue
            result = service.compute(
                item.dataset,
                DerivedMetricOptions(
                    discharge_column=discharge,
                    charge_column=charge,
                    baseline=baseline or BaselineConfig(),
                ),
            )
            metrics = item.metrics_frame if item.metrics_frame is not None else result.frame
            cycle_column = result.cycle_column or "estimated_cycle_index"
            retention_column = "discharge_energy_retention_pct"
            overlay_parts.append(
                pd.DataFrame(
                    {
                        "dataset": item.name,
                        "cycle_index": metrics[cycle_column],
                        "discharge_energy_retention_pct": metrics[retention_column],
                    }
                )
            )
            retention = pd.to_numeric(metrics[retention_column], errors="coerce")
            efficiency = (
                pd.to_numeric(metrics["energy_efficiency"], errors="coerce")
                if "energy_efficiency" in metrics
                else pd.Series(dtype=float)
            )
            valid_retention = retention.dropna()
            cycle = pd.to_numeric(metrics[cycle_column], errors="coerce")
            fade_rate = self._fade_rate(cycle, retention)
            summary_rows.append(
                {
                    "dataset": item.name,
                    "source_file": str(item.dataset.metadata.source_path),
                    "points": len(metrics),
                    "cycles": int(cycle.nunique(dropna=True)),
                    "final_retention_pct": (
                        float(valid_retention.iloc[-1]) if not valid_retention.empty else np.nan
                    ),
                    "estimated_fade_rate_pct_per_cycle": fade_rate,
                    "mean_efficiency": (
                        float(efficiency.mean()) if not efficiency.empty else np.nan
                    ),
                }
            )
            warnings.extend(f"{item.name}: {warning}" for warning in result.warnings)

        overlay = (
            pd.concat(overlay_parts, ignore_index=True)
            if overlay_parts
            else pd.DataFrame(
                columns=["dataset", "cycle_index", "discharge_energy_retention_pct"]
            )
        )
        return ComparisonResult(
            overlay_frame=overlay,
            summary_frame=pd.DataFrame(summary_rows),
            warnings=warnings,
        )

    def _fade_rate(self, cycle: pd.Series, retention: pd.Series) -> float:
        frame = pd.DataFrame({"cycle": cycle, "retention": retention}).dropna()
        if len(frame) < 2 or frame["cycle"].nunique() < 2:
            return float("nan")
        return float(np.polyfit(frame["cycle"], frame["retention"], 1)[0])
