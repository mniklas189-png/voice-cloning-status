"""Quelle: XDG-Desktop-Dateien (Linux).

Local Ally ist fuer Windows gedacht. Diese Quelle existiert, damit sich die
gesamte Kette - Index, Suche, Befehl, Start - auch auf einem Linux-Rechner
entwickeln und testen laesst, ohne den Windows-Code zu veraendern.
"""

from __future__ import annotations

import logging
import os
import re
import shlex
from pathlib import Path
from typing import Iterator

from ..models import DiscoveredApp
from .base import looks_like_noise

log = logging.getLogger(__name__)

_FIELD_CODES = re.compile(r"%[fFuUdDnNickvm]")


def desktop_dirs() -> list[Path]:
    dirs: list[str] = []
    data_home = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local/share")
    dirs.append(data_home)
    dirs.extend((os.environ.get("XDG_DATA_DIRS") or "/usr/share:/usr/local/share").split(":"))
    result = []
    for base in dirs:
        candidate = Path(base) / "applications"
        if candidate.is_dir() and candidate not in result:
            result.append(candidate)
    return result


class DesktopEntrySource:
    id = "desktop_entry"
    display_name = "Desktop-Dateien (Linux)"
    priority = 40

    def is_available(self) -> bool:
        return bool(desktop_dirs())

    def discover(self) -> Iterator[DiscoveredApp]:
        for directory in desktop_dirs():
            for path in sorted(directory.glob("*.desktop")):
                app = self._parse(path)
                if app:
                    yield app

    def _parse(self, path: Path) -> DiscoveredApp | None:
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

        entry: dict[str, str] = {}
        in_section = False
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("["):
                in_section = line == "[Desktop Entry]"
                continue
            if not in_section or "=" not in line or line.startswith("#"):
                continue
            key, _, value = line.partition("=")
            entry.setdefault(key.strip(), value.strip())

        name = entry.get("Name", "") or path.stem
        exec_line = entry.get("Exec", "")
        if not exec_line or entry.get("NoDisplay", "").lower() == "true":
            return None
        if entry.get("Type", "Application") != "Application" or looks_like_noise(name):
            return None

        command = _FIELD_CODES.sub("", exec_line).strip()
        try:
            binary = shlex.split(command)[0]
        except ValueError:
            return None

        aliases = [Path(binary).name, path.stem]
        generic = entry.get("GenericName")
        if generic:
            aliases.append(generic)

        return DiscoveredApp(
            name=name,
            launch_target=command,
            launch_kind="command",
            source=self.id,
            priority=self.priority,
            working_dir=entry.get("Path", ""),
            icon_path=entry.get("Icon", ""),
            aliases=aliases,
        )
