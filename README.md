# Battery Aging Load-Cycle Analyzer

A local Python desktop app for analyzing battery aging charge/discharge cycling CSV files. It uses PyQt6 for the UI, PyQtGraph for interactive plotting, pandas for import and tabular data, and NumPy/SciPy for analysis.

## Project Structure

```text
battery_aging_app/
  app.py                    # Qt application entry
  models.py                 # shared dataclasses
  importers/                # CSV preview, parsing, mapping presets
  analysis/                 # cleaning warnings, units, sections, metrics, integration
  plotting/                 # cursor/table synchronization logic
  exports/                  # CSV and HTML reporting
  session.py                # project/session JSON state
  ui/                       # PyQt6 windows, dialogs, table model, plot widget
sample_data/                # minimal CSV files
tests/                      # pytest suite for headless core behavior
packaging/                  # PyInstaller spec
```

## Install

Python 3.11 or newer is required.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## Run

```powershell
battery-aging-analyzer
```

or:

```powershell
python -m battery_aging_app
```

## Basic Usage

1. Choose **File > Open CSV**.
2. In the import dialog, set delimiter, decimal separator, encoding, label row, unit row, and first data row.
3. Select the time, discharge-energy, charge-energy, and optional additional columns.
4. Use the curve list to toggle plotted curves.
5. Drag the vertical cursor or use the slider/spinbox to inspect synchronized plot and table values.
6. Right-click the slider or plot to add dividers. Click plot sections to highlight rows and update integration results.
7. Right-click a section to export section data, integrate, rename, show statistics, or remove bordering dividers.

Column names are never assumed by the importer. All semantic roles come from the user-selected mapping.

## Analysis Features

- Data-cleaning warnings for missing values, non-numeric cells, duplicate timestamps, non-monotonic time, irregular gaps, and large gaps.
- Unit conversion helpers for time, energy, power, current, voltage, and capacity.
- Derived metrics for energy retention, energy efficiency, percent fade, cycle index estimation, rolling average, and slope.
- Trapezoidal integration over actual time values with integration-specific warnings.
- Section-level statistics: min, max, mean, median, standard deviation, start, end, delta, and slope.

## Export

- Selected section CSV with a relative time column and sidecar metadata JSON.
- Full processed dataset CSV.
- Plot PNG/SVG from the plot toolbar.
- HTML analysis report.
- Project/session JSON with loaded paths, mappings, dividers, visible curves, units, and settings.

## Tests

```powershell
pytest
```

The tests cover CSV import, section creation, integration, CSV export, unit conversion, trace synchronization, metrics, and session round-tripping.

## Packaging

Packaging is intentionally separate from the core app:

```powershell
pyinstaller packaging\battery_aging_analyzer.spec
```

This creates a desktop executable bundle without changing application logic.
