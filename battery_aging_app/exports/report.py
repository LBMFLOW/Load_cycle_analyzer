from __future__ import annotations

from html import escape
from pathlib import Path

from battery_aging_app.analysis.integration import IntegrationResult
from battery_aging_app.models import ImportedDataset, Section


def write_html_report(
    dataset: ImportedDataset,
    path: str | Path,
    *,
    selected_section: Section | None,
    integration_results: list[IntegrationResult],
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = "\n".join(
        "<tr>"
        f"<td>{escape(result.curve_name)}</td>"
        f"<td>{result.time_start:.6g} to {result.time_end:.6g}</td>"
        f"<td>{result.point_count}</td>"
        f"<td>{result.integral_value:.8g} {escape(result.integral_unit)}</td>"
        "</tr>"
        for result in integration_results
    )
    section_name = selected_section.name if selected_section else "Whole dataset"
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Battery Aging Analysis Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 32px; color: #202124; }}
    h1 {{ font-size: 24px; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 16px; }}
    th, td {{ border: 1px solid #c7ccd1; padding: 8px 10px; text-align: left; }}
    th {{ background: #eef2f5; }}
  </style>
</head>
<body>
  <h1>Battery Aging Analysis Report</h1>
  <p><strong>Source:</strong> {escape(dataset.metadata.source_file)}</p>
  <p><strong>Section:</strong> {escape(section_name)}</p>
  <h2>Integration Results</h2>
  <table>
    <thead>
      <tr><th>Curve</th><th>Time Range</th><th>Points</th><th>Integral</th></tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
</body>
</html>
"""
    output_path.write_text(html, encoding="utf-8")
    return output_path
