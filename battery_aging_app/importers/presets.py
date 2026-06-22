from __future__ import annotations

import json
from pathlib import Path

from battery_aging_app.models import ColumnMapping


class MappingPresetStore:
    """JSON-backed column-mapping preset storage."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else self.default_path()

    @staticmethod
    def default_path() -> Path:
        return (
            Path.home()
            / ".battery_aging_analyzer"
            / "column_mapping_presets.json"
        )

    def load_all(self) -> dict[str, ColumnMapping]:
        if not self.path.exists():
            return {}
        with self.path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        return {name: ColumnMapping.from_dict(data) for name, data in raw.items()}

    def save(self, name: str, mapping: ColumnMapping) -> None:
        presets = self.load_all()
        clone = ColumnMapping.from_dict(mapping.to_dict())
        clone.preset_name = name
        presets[name] = clone
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(
                {key: value.to_dict() for key, value in presets.items()},
                handle,
                indent=2,
            )
