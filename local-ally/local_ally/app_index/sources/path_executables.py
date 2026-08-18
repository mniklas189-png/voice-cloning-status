"""Quelle: ausfuehrbare Dateien im PATH.

Faengt Werkzeuge ohne Startmenue-Eintrag ab (git, python, ffmpeg, ...).
Niedrige Prioritaet, weil hier viele Hilfsprogramme liegen, die niemand
per Sprache oeffnen will.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterator

from ..models import DiscoveredApp

_WINDOWS_SUFFIXES = {".exe", ".bat", ".cmd", ".com"}
_MAX_PER_DIRECTORY = 400  # Schutz vor riesigen Sammelverzeichnissen


class PathExecutablesSource:
    id = "path"
    display_name = "Programme im Suchpfad (PATH)"
    priority = 10

    def is_available(self) -> bool:
        return bool(os.environ.get("PATH"))

    def discover(self) -> Iterator[DiscoveredApp]:
        is_windows = sys.platform.startswith("win")
        seen: set[str] = set()

        for raw in os.environ.get("PATH", "").split(os.pathsep):
            directory = raw.strip('"').strip()
            if not directory:
                continue
            path = Path(directory)
            if not path.is_dir():
                continue

            count = 0
            try:
                entries = sorted(os.scandir(path), key=lambda e: e.name.lower())
            except OSError:
                continue

            for entry in entries:
                if count >= _MAX_PER_DIRECTORY:
                    break
                try:
                    if not entry.is_file(follow_symlinks=True):
                        continue
                    item = Path(entry.path)
                    if is_windows:
                        if item.suffix.lower() not in _WINDOWS_SUFFIXES:
                            continue
                    elif not os.access(entry.path, os.X_OK):
                        continue
                except OSError:
                    continue

                key = item.stem.lower()
                if key in seen or len(key) < 2:
                    continue
                seen.add(key)
                count += 1
                yield DiscoveredApp(
                    name=item.stem,
                    launch_target=str(item),
                    source=self.id,
                    priority=self.priority,
                )
