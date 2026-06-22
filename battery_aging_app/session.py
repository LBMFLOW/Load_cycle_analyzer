from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from battery_aging_app.models import AnalysisSettings, ColumnMapping, Divider


@dataclass(slots=True)
class ProjectSession:
    loaded_file_paths: list[str] = field(default_factory=list)
    mappings: dict[str, ColumnMapping] = field(default_factory=dict)
    dividers: list[Divider] = field(default_factory=list)
    selected_section_id: str | None = None
    visible_curves: list[str] = field(default_factory=list)
    units: dict[str, str] = field(default_factory=dict)
    analysis_settings: AnalysisSettings = field(default_factory=AnalysisSettings)
    divider_notes: dict[str, str] = field(default_factory=dict)
    section_notes: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "loaded_file_paths": self.loaded_file_paths,
            "mappings": {
                path: mapping.to_dict() for path, mapping in self.mappings.items()
            },
            "dividers": [divider.to_dict() for divider in self.dividers],
            "selected_section_id": self.selected_section_id,
            "visible_curves": self.visible_curves,
            "units": self.units,
            "analysis_settings": self.analysis_settings.to_dict(),
            "divider_notes": self.divider_notes,
            "section_notes": self.section_notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectSession":
        return cls(
            loaded_file_paths=list(data.get("loaded_file_paths", [])),
            mappings={
                path: ColumnMapping.from_dict(mapping)
                for path, mapping in data.get("mappings", {}).items()
            },
            dividers=[
                Divider.from_dict(divider) for divider in data.get("dividers", [])
            ],
            selected_section_id=data.get("selected_section_id"),
            visible_curves=list(data.get("visible_curves", [])),
            units=dict(data.get("units", {})),
            analysis_settings=AnalysisSettings.from_dict(
                data.get("analysis_settings", {})
            ),
            divider_notes=dict(data.get("divider_notes", {})),
            section_notes=dict(data.get("section_notes", {})),
        )

    def save(self, path: str | Path) -> Path:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return output_path

    @classmethod
    def load(cls, path: str | Path) -> "ProjectSession":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
