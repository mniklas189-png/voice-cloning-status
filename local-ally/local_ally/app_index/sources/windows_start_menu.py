"""Quelle: Verknuepfungen im Windows-Startmenue.

Das Startmenue ist die verlaesslichste Liste dessen, was ein Nutzer
tatsaechlich startet - es enthaelt genau die Programme, die ein Installer
sichtbar machen wollte.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Iterable, Iterator

from ..models import DiscoveredApp
from .base import looks_like_noise
from .lnk import parse as parse_lnk

log = logging.getLogger(__name__)

SOURCE_ID = "start_menu"
_SUFFIXES = {".lnk", ".url", ".appref-ms"}
_MAX_DEPTH = 6


def start_menu_dirs() -> list[Path]:
    """Startmenue des Nutzers und des Systems."""
    candidates: list[Path] = []
    appdata = os.environ.get("APPDATA")
    programdata = os.environ.get("PROGRAMDATA")
    if appdata:
        candidates.append(Path(appdata) / "Microsoft/Windows/Start Menu/Programs")
    if programdata:
        candidates.append(Path(programdata) / "Microsoft/Windows/Start Menu/Programs")
    candidates.append(Path.home() / "Desktop")
    return [path for path in candidates if path.is_dir()]


class StartMenuSource:
    id = SOURCE_ID
    display_name = "Windows-Startmenue"
    priority = 40

    def __init__(self, directories: Iterable[Path] | None = None) -> None:
        self._directories = list(directories) if directories is not None else None

    def is_available(self) -> bool:
        if self._directories is not None:
            return True
        return sys.platform.startswith("win") and bool(start_menu_dirs())

    def discover(self) -> Iterator[DiscoveredApp]:
        directories = self._directories if self._directories is not None else start_menu_dirs()
        for directory in directories:
            yield from self._scan(directory)

    def _scan(self, directory: Path) -> Iterator[DiscoveredApp]:
        for path in _walk(directory, _MAX_DEPTH):
            if path.suffix.lower() not in _SUFFIXES:
                continue
            name = path.stem
            if looks_like_noise(name):
                continue
            try:
                yield self._to_app(path, name)
            except OSError as exc:  # einzelne kaputte Verknuepfung ueberspringen
                log.debug("Verknuepfung %s uebersprungen: %s", path, exc)

    def _to_app(self, path: Path, name: str) -> DiscoveredApp:
        aliases: list[str] = []
        working_dir = ""
        icon = ""

        if path.suffix.lower() == ".lnk":
            link = parse_lnk(path)
            if link:
                working_dir = link.working_dir
                icon = link.icon_location
                if link.target:
                    # Der Dateiname des Ziels ist oft der Name, den Nutzer sagen
                    # ("code.exe" -> "code"), deshalb als Alias aufnehmen.
                    aliases.append(Path(link.target).stem)

        # Gestartet wird immer die Verknuepfung selbst: Windows loest dabei
        # Argumente, Arbeitsverzeichnis und Kompatibilitaetsflags korrekt auf.
        return DiscoveredApp(
            name=name,
            launch_target=str(path),
            launch_kind="path",
            working_dir=working_dir,
            icon_path=icon,
            source=SOURCE_ID,
            priority=self.priority,
            aliases=aliases,
        )


def _walk(directory: Path, max_depth: int) -> Iterator[Path]:
    """Rekursiver Durchlauf ohne Symlink-Schleifen."""
    stack: list[tuple[Path, int]] = [(directory, 0)]
    while stack:
        current, depth = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    if depth < max_depth:
                        stack.append((Path(entry.path), depth + 1))
                elif entry.is_file(follow_symlinks=False):
                    yield Path(entry.path)
            except OSError:
                continue
