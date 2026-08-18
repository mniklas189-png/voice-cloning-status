"""Quellen: Windows-Registry.

Zwei Schluesselbereiche sind interessant:

``App Paths``
    Was Windows startet, wenn man einen Namen in "Ausfuehren" eingibt.
    Kurz, sauber und praktisch immer ein direkt startbares Programm.

``Uninstall``
    Die Liste "Apps & Features". Sie ist vollstaendiger, enthaelt aber auch
    Treiber, Laufzeitumgebungen und Updates - deshalb wird gefiltert und die
    Prioritaet niedriger angesetzt.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Iterator

from ..models import DiscoveredApp
from .base import looks_like_noise

log = logging.getLogger(__name__)

if sys.platform.startswith("win"):  # pragma: no cover - nur auf Windows
    import winreg
else:  # pragma: no cover - Platzhalter fuer Entwicklung auf anderen Systemen
    winreg = None  # type: ignore[assignment]

_APP_PATHS_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
_UNINSTALL_KEYS = (
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
)
# Nur echte Anwendungen: Laufzeiten und Updates soll niemand per Sprache oeffnen.
_UNINSTALL_BLOCKLIST = (
    "redistributable", "runtime", "driver", "treiber", "sdk", "update for",
    "sicherheitsupdate", "security update", "hotfix", "language pack",
    "sprachpaket", "microsoft visual c++", ".net framework",
)


def _read_value(key, name: str = "") -> str:
    try:
        value, _ = winreg.QueryValueEx(key, name)
    except OSError:
        return ""
    return str(value).strip() if value else ""


def _iter_subkeys(root, path: str) -> Iterator[tuple[str, object]]:
    for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        try:
            base = winreg.OpenKey(root, path, 0, winreg.KEY_READ | view)
        except OSError:
            continue
        with base:
            index = 0
            while True:
                try:
                    name = winreg.EnumKey(base, index)
                except OSError:
                    break
                index += 1
                try:
                    with winreg.OpenKey(base, name, 0, winreg.KEY_READ | view) as sub:
                        yield name, sub
                except OSError:
                    continue


class AppPathsSource:
    id = "registry_app_paths"
    display_name = "Registry: App Paths"
    priority = 30

    def is_available(self) -> bool:
        return winreg is not None

    def discover(self) -> Iterator[DiscoveredApp]:
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for key_name, key in _iter_subkeys(root, _APP_PATHS_KEY):
                target = _read_value(key).strip('"')
                if not target or not Path(target).exists():
                    continue
                name = Path(key_name).stem
                if looks_like_noise(name):
                    continue
                yield DiscoveredApp(
                    name=name,
                    launch_target=target,
                    source=self.id,
                    priority=self.priority,
                    working_dir=_read_value(key, "Path"),
                    aliases=[Path(target).stem],
                )


class UninstallSource:
    id = "registry_uninstall"
    display_name = "Registry: Installierte Programme"
    priority = 20

    def is_available(self) -> bool:
        return winreg is not None

    def discover(self) -> Iterator[DiscoveredApp]:
        seen: set[str] = set()
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for path in _UNINSTALL_KEYS:
                for _key_name, key in _iter_subkeys(root, path):
                    app = self._to_app(key)
                    if app and app.launch_target.lower() not in seen:
                        seen.add(app.launch_target.lower())
                        yield app

    def _to_app(self, key) -> DiscoveredApp | None:
        name = _read_value(key, "DisplayName")
        if not name or looks_like_noise(name):
            return None
        lowered = name.casefold()
        if any(part in lowered for part in _UNINSTALL_BLOCKLIST):
            return None
        if _read_value(key, "SystemComponent") == "1":
            return None

        executable = self._find_executable(key, name)
        if not executable:
            return None
        return DiscoveredApp(
            name=name,
            launch_target=str(executable),
            source=self.id,
            priority=self.priority,
            working_dir=str(executable.parent),
            aliases=[executable.stem],
        )

    @staticmethod
    def _find_executable(key, name: str) -> Path | None:
        """Aus dem Uninstall-Eintrag die Hauptanwendung ableiten."""
        icon = _read_value(key, "DisplayIcon").split(",")[0].strip('" ')
        if icon.lower().endswith(".exe") and Path(icon).exists():
            return Path(icon)

        location = _read_value(key, "InstallLocation").strip('"')
        if not location or not Path(location).is_dir():
            return None

        folder = Path(location)
        try:
            executables = [
                item for item in folder.glob("*.exe") if not looks_like_noise(item.stem)
            ]
        except OSError:
            return None
        if not executables:
            return None

        # Bevorzugt die .exe, deren Name dem Programmnamen am naechsten kommt.
        from ...core import text

        wanted = text.compact(name)
        executables.sort(key=lambda item: (0 if text.compact(item.stem) in wanted else 1, len(item.stem)))
        return executables[0]
