"""Quellen fuer den App-Index.

Jede Quelle ist ein eigenes Modul und implementiert :class:`AppSource`.
Eine neue Quelle wird ergaenzt, indem sie hier in :func:`default_sources`
eingetragen wird - der Rest der Anwendung bleibt unveraendert.
"""

from __future__ import annotations

import sys

from .base import AppSource

IS_WINDOWS = sys.platform.startswith("win")


def default_sources(*, include_path: bool = True) -> list[AppSource]:
    """Alle fuer dieses Betriebssystem sinnvollen Quellen.

    Die Reihenfolge ist egal - jede Quelle traegt ihre eigene ``priority``,
    die bei doppelten Programmen entscheidet, welcher Eintrag gewinnt.
    """
    sources: list[AppSource] = []

    if IS_WINDOWS:
        from .windows_start_apps import StartAppsSource
        from .windows_start_menu import StartMenuSource
        from .windows_registry import AppPathsSource, UninstallSource

        sources += [
            StartAppsSource(),   # Startmenue inkl. Store-Apps (PowerShell)
            StartMenuSource(),   # .lnk-Dateien im Startmenue
            AppPathsSource(),    # Registry: App Paths
            UninstallSource(),   # Registry: installierte Programme
        ]
    else:
        # Entwicklungs- und Testumgebung: Local Ally bleibt auf Linux/macOS
        # lauffaehig, damit sich alles ausserhalb von Windows testen laesst.
        from .linux_desktop import DesktopEntrySource

        sources.append(DesktopEntrySource())

    if include_path:
        from .path_executables import PathExecutablesSource

        sources.append(PathExecutablesSource())

    return [source for source in sources if source.is_available()]


__all__ = ["AppSource", "default_sources"]
