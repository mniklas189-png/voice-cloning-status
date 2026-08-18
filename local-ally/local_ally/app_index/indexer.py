"""Aufbau des App-Index: alle Quellen einsammeln, zusammenfuehren, speichern."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable, Iterable, Sequence

from ..core import text
from .models import DiscoveredApp
from .repository import AppRepository
from .sources import default_sources
from .sources.base import AppSource

log = logging.getLogger(__name__)

ProgressCallback = Callable[[str, int, int], None]  # Quelle, Nummer, Gesamtzahl


def merge_discovered(apps: Iterable[DiscoveredApp]) -> list[DiscoveredApp]:
    """Dubletten zusammenfuehren.

    Dasselbe Programm taucht regelmaessig mehrfach auf - als Verknuepfung im
    Startmenue, als Registry-Eintrag und als Datei im PATH. Es soll aber nur
    *einmal* im Index stehen, sonst fragt Local Ally staendig nach, welches
    "Discord" gemeint ist.

    Zusammengefuehrt wird ueber den normalisierten Namen und ueber identische
    Startziele. Es gewinnt die Quelle mit der hoechsten Prioritaet; die Namen
    der unterlegenen Eintraege bleiben als Aliase erhalten.
    """
    by_name: dict[str, DiscoveredApp] = {}

    def absorb(bucket: dict[str, DiscoveredApp], key: str, app: DiscoveredApp) -> None:
        existing = bucket.get(key)
        if existing is None:
            bucket[key] = app
            return
        winner, loser = (existing, app) if existing.priority >= app.priority else (app, existing)
        aliases = list(winner.aliases)
        for candidate in [loser.name, *loser.aliases]:
            if candidate and candidate not in aliases:
                aliases.append(candidate)
        winner.aliases = aliases
        bucket[key] = winner

    for app in apps:
        if not app.name.strip() or not app.launch_target.strip():
            continue
        absorb(by_name, text.normalize(app.name) or app.launch_target.lower(), app)

    by_target: dict[str, DiscoveredApp] = {}
    for app in by_name.values():
        target = app.launch_target.strip('"').lower()
        if app.launch_kind == "path":
            target = str(Path(target))
        absorb(by_target, f"{app.launch_kind}:{target}", app)

    return sorted(by_target.values(), key=lambda a: a.name.lower())


class AppIndexer:
    """Fuehrt einen vollstaendigen Scan durch und schreibt ihn in die Datenbank."""

    def __init__(
        self,
        repository: AppRepository,
        sources: Sequence[AppSource] | None = None,
        *,
        include_path_executables: bool = True,
    ) -> None:
        self.repository = repository
        self._sources = list(sources) if sources is not None else None
        self._include_path = include_path_executables

    @property
    def sources(self) -> list[AppSource]:
        if self._sources is None:
            self._sources = default_sources(include_path=self._include_path)
        return self._sources

    def rebuild(self, on_progress: ProgressCallback | None = None) -> int:
        """Index neu aufbauen. Gibt die Anzahl gespeicherter Programme zurueck."""
        started = time.perf_counter()
        sources = self.sources
        discovered: list[DiscoveredApp] = []

        for number, source in enumerate(sources, start=1):
            if on_progress:
                on_progress(source.display_name, number, len(sources))
            try:
                found = list(source.discover())
            except Exception:  # eine defekte Quelle darf den Scan nicht stoppen
                log.exception("Quelle %s fehlgeschlagen", source.id)
                continue
            log.info("Quelle %-22s: %4d Eintraege", source.id, len(found))
            discovered.extend(found)

        merged = merge_discovered(discovered)
        written = self.repository.replace_all(merged)
        log.info(
            "Index fertig: %d Rohtreffer -> %d Programme in %.1fs",
            len(discovered), written, time.perf_counter() - started,
        )
        return written
