"""Startet ein Programm aus dem App-Index.

Der Start ist bewusst von der Suche getrennt: die Suche liefert einen
:class:`AppEntry`, der Launcher entscheidet nur noch *wie* gestartet wird.
So kommen spaeter weitere Startarten (Store-Apps, URIs, Skripte) dazu, ohne
dass Befehle oder UI angepasst werden muessen.
"""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .models import AppEntry

log = logging.getLogger(__name__)

IS_WINDOWS = sys.platform.startswith("win")


@dataclass(slots=True)
class LaunchResult:
    ok: bool
    message: str


def _popen_kwargs() -> dict:
    """Der gestartete Prozess soll Local Ally ueberleben."""
    if IS_WINDOWS:
        flags = 0
        flags |= getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
        return {"creationflags": flags, "close_fds": True}
    return {"start_new_session": True, "close_fds": True}


def _split_arguments(arguments: str) -> list[str]:
    if not arguments.strip():
        return []
    # posix=False laesst Windows-Pfade mit Backslashes unangetastet.
    return shlex.split(arguments, posix=not IS_WINDOWS)


def launch(entry: AppEntry) -> LaunchResult:
    """Startet den Eintrag und meldet das Ergebnis in Klartext zurueck."""
    target = entry.launch_target
    working_dir = entry.working_dir or None
    if working_dir and not Path(working_dir).is_dir():
        working_dir = None

    try:
        if entry.launch_kind == "shell":
            # Store-/UWP-Apps: ueber die Shell, z.B. shell:AppsFolder\<AppID>
            if IS_WINDOWS:
                subprocess.Popen(["explorer.exe", target], **_popen_kwargs())
            else:
                return LaunchResult(False, "Store-Apps lassen sich nur unter Windows starten.")

        elif entry.launch_kind == "uri":
            _open_with_system(target)

        elif entry.launch_kind == "command":
            args = _split_arguments(target)
            subprocess.Popen(args or target, cwd=working_dir, **_popen_kwargs())

        else:  # "path"
            path = Path(target)
            if not path.exists() and not IS_WINDOWS:
                return LaunchResult(False, f"Datei nicht gefunden: {target}")
            arguments = _split_arguments(entry.arguments)
            if IS_WINDOWS and not arguments:
                # startfile kennt Verknuepfungen (.lnk), Dokumente und .url-Dateien
                os.startfile(target)  # type: ignore[attr-defined]
            else:
                subprocess.Popen([target, *arguments], cwd=working_dir, **_popen_kwargs())

    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        log.exception("Start fehlgeschlagen: %s", entry.name)
        return LaunchResult(False, f"{entry.name} konnte nicht gestartet werden: {exc}")

    log.info("Gestartet: %s (%s)", entry.name, entry.launch_target)
    return LaunchResult(True, f"{entry.name} wird gestartet.")


def _open_with_system(target: str) -> None:
    if IS_WINDOWS:
        os.startfile(target)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", target], **_popen_kwargs())
    else:
        subprocess.Popen(["xdg-open", target], **_popen_kwargs())
