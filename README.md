# Battery Aging Load-Cycle Analyzer

Local desktop software for importing, plotting, sectioning, integrating, and reporting battery charge/discharge aging cycle data from CSV files.

The current implementation lives in `src/battery_cycle_analyzer` and uses PyQt6, PyQtGraph, pandas, NumPy, and SciPy. CSV data stays in backend pandas DataFrames; the UI uses Qt model/view tables and controller classes for plot interaction.

## Project Structure

```text
src/battery_cycle_analyzer/
  main.py                  # console entry point
  app.py                   # Qt application bootstrap and logging setup
  ui/
    main_window.py         # menus, start screen, workspace coordination
    import_wizard.py       # four-step CSV import workflow
    plot_panel.py          # plot widget, toolbar, cursor controls
    table_panel.py         # QAbstractTableModel-backed data table
    results_panel.py       # cursor, integration, statistics output
    dialogs.py             # export, range, and result dialogs
    workers.py             # cancellable background tasks
  core/
    csv_loader.py          # preview and selected-column CSV import
    data_model.py          # dataclasses for datasets, curves, dividers, sections
    analysis.py            # integration, diagnostics, section statistics
    sections.py            # pure divider/section boundary logic
    export.py              # section CSV and metadata export
    derived_metrics.py     # retention, efficiency, fade, smoothing, slope
    filtering.py           # processed data views and outlier filtering
    comparison.py          # multi-dataset comparison summaries
    project_state.py       # JSON project save/load
    report.py              # HTML aging report export
    units.py               # unit conversion helpers
  plotting/
    plot_controller.py     # plot orchestration
    cursor_controller.py   # trace cursor and readout lookup
    divider_controller.py  # movable divider lines
    section_overlay.py     # selected-section highlight overlay
  tests/
    sample_data/           # import fixtures
    test_*.py              # headless core and synchronization tests
```

`battery_aging_app/` remains in the repository as the original prototype package. The installed commands below launch the current `battery_cycle_analyzer` app.

## Installation

Python 3.11 or newer is required.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## Run

After installation:

```powershell
battery-cycle-analyzer
```

The compatibility command also launches the current app:

```powershell
battery-aging-analyzer
```

Without installing, run from the repository root:

```powershell
$env:PYTHONPATH = "src"
python -m battery_cycle_analyzer.main
```

## Basic Workflow

1. Start the app and choose **Import CSV**.
2. In the import wizard, select delimiter, decimal separator, encoding, parameter-label row, unit row, and first data row.
3. Map the time, discharge-energy, charge-energy, and optional additional columns. Duplicate or missing CSV labels can still be selected by column index.
4. Review validation warnings, then import.
5. Toggle charge/discharge curves, drag the trace cursor, or use the slider/spinbox to inspect synchronized plot and table values.
6. Add dividers from the cursor context menu or plot toolbar. Click a section to highlight its rows and update section statistics.
7. Right-click a selected section to save section data, integrate data, rename it, or add notes.
8. Save the project as JSON to restore import settings, visible curves, cursor position, dividers, section selection, annotations, filters, and derived metric settings later.

## Major Features

- CSV preview and import with user-selected rows, delimiter, decimal separator, encoding, and column mappings.
- Metadata preservation for original labels, units, selected rows, and source paths.
- Responsive plotting of charge/discharge energy versus time with legend, grid, zoom, pan, reset, export, and curve visibility toggles.
- Trace cursor synchronized with slider/spinbox, readout panel, and model/view data table.
- Divider and section handling with movable/renamable/removable dividers and selected-section table highlighting.
- Section CSV export with relative time starting at zero, original time, visible curves, metadata comments, and optional sidecar JSON.
- Trapezoidal integration over actual time values with warnings for non-monotonic time, duplicates, missing values, and too few points.
- Section statistics: start, end, delta, percent change, min, max, mean, median, standard deviation, slope, integral, valid points, and missing points.
- Derived aging metrics: discharge/charge retention, energy efficiency, energy loss, percent fade, rolling mean/std, slope over time, and cycle-to-cycle delta.
- Baseline selection from first point, first N-point mean, selected section, or manual values.
- Processed data views with time/cycle filtering, NaN removal, duplicate timestamp handling, outlier filtering, and smoothing.
- Multi-dataset comparison with retention overlays and combined comparison export.
- HTML aging report export with source files, settings, summary metrics, section statistics, plots, and notes.
- Background workers with progress/cancel support for import and heavier calculations.
- Application logging with user-friendly error dialogs and detailed tracebacks behind **Show Details**.

## Tests

Run the full suite:

```powershell
python -B -m pytest -p no:cacheprovider
```

The tests cover CSV import, mapping, malformed inputs, units, cursor lookup, interpolation, section ranges, integration, statistics, export, derived metrics, filtering, comparison, report generation, and project-state round trips.

## Packaging

Packaging remains separate from the app logic. Build a PyInstaller bundle from the repository root:

```powershell
pyinstaller packaging\battery_aging_analyzer.spec
```

The spec targets `src/battery_cycle_analyzer/main.py` and includes the sample data directory.
