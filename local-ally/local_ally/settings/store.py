"""Laden und Speichern der Einstellungen (JSON im Datenverzeichnis)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ..core.paths import settings_path
from .model import Settings

log = logging.getLogger(__name__)


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or settings_path()
        self._settings = self.load()

    @property
    def settings(self) -> Settings:
        return self._settings

    def load(self) -> Settings:
        if not self.path.exists():
            return Settings()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return Settings.from_dict(data)
        except (OSError, ValueError) as exc:
            # Eine kaputte Datei darf den Start nie verhindern.
            log.warning("Einstellungen konnten nicht gelesen werden (%s), nutze Vorgaben", exc)
            return Settings()

    def save(self, settings: Settings | None = None) -> None:
        if settings is not None:
            self._settings = settings
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(self._settings.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(self.path)  # atomar: nie eine halb geschriebene Datei

    def update(self, **changes: object) -> Settings:
        for key, value in changes.items():
            if hasattr(self._settings, key):
                setattr(self._settings, key, value)
        self.save()
        return self._settings
