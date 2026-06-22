# Battery Cycle Analyzer Architecture

This skeleton uses a strict layer boundary:

- `core`: owns pandas DataFrames, numerical analysis, validation, units, exports, and project state. It has no Qt imports.
- `plotting`: owns PyQtGraph coordination and interactivity controllers. It depends on `core`, but `core` never depends on it.
- `ui`: owns widgets, menus, dialogs, Qt models, and screen layout. It depends on `core` and `plotting`.
- `main.py` and `app.py`: application startup only.

## Module Responsibilities

### Project Root

- `pyproject.toml`: build metadata, runtime dependencies, pytest configuration, console entry points.
- `README.md`: installation and user-facing usage notes.
- `ARCHITECTURE.md`: engineering architecture and module responsibilities.

### `src/battery_cycle_analyzer`

- `__init__.py`: package metadata.
- `main.py`: console entry point that delegates to `app.run`.
- `app.py`: creates `QApplication`, applies application metadata, opens `MainWindow`.

### `src/battery_cycle_analyzer/ui`

- `main_window.py`: top-level shell, menu actions, panel composition, import command routing.
- `import_wizard.py`: import workflow UI for file path, delimiter, encoding, row choices, and column mapping.
- `plot_panel.py`: Qt widget containing the PyQtGraph canvas and plot toolbar.
- `table_panel.py`: `QAbstractTableModel` and `QTableView` wrapper for large pandas DataFrames.
- `results_panel.py`: bottom panel for integration results, warnings, and section statistics.
- `dialogs.py`: small reusable dialogs for errors, integration results, and section metadata.

### `src/battery_cycle_analyzer/core`

- `data_model.py`: shared dataclasses for loaded datasets, curves, dividers, sections, integration results, and project state.
- `import_config.py`: dataclasses for import settings and high-level import presets.
- `column_mapping.py`: column-role mapping model and resolution helpers from user-selected CSV columns to semantic roles.
- `csv_loader.py`: pandas CSV preview/load service. Produces `LoadedDataset`; does not import Qt.
- `units.py`: unit categories, conversion factors, compatibility checks, and conversion functions.
- `validation.py`: data-quality validation for missing values, non-numeric values, duplicate/non-monotonic time, and gaps.
- `analysis.py`: numerical analysis service for integration, retention, efficiency, rolling averages, slopes, and section statistics.
- `sections.py`: divider storage, section generation, section masks, and row-index lookup.
- `export.py`: CSV, metadata JSON, processed dataset, summary, and report export interfaces.
- `project_state.py`: JSON serialization/deserialization of sessions and project files.

### `src/battery_cycle_analyzer/plotting`

- `plot_controller.py`: connects loaded datasets and visible curves to PyQtGraph items.
- `cursor_controller.py`: owns trace cursor movement, nearest/linear lookup coordination, and row synchronization signals.
- `divider_controller.py`: owns movable divider graphics and divider context actions.
- `section_overlay.py`: owns section highlight overlays and plot-section hit testing.

### `src/battery_cycle_analyzer/tests`

- `sample_data/`: small CSV fixtures for architecture-level tests.
- `test_csv_loader.py`: CSV loading and mapping tests.
- `test_analysis.py`: integration and metric tests.
- `test_sections.py`: divider/section tests.
- `test_export.py`: export service tests.
- `test_units.py`: unit conversion tests.
