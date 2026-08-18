"""Zentrale Ablageorte fuer Daten, Modelle und Logs.

Alles liegt bewusst im Benutzerprofil und nicht im Programmverzeichnis:
Local Ally soll ohne Adminrechte und ohne Cloud funktionieren.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path, PurePath, PureWindowsPath

APP_NAME = "LocalAlly"


def is_windows() -> bool:
    return sys.platform.startswith("win")


def data_dir() -> Path:
    """Basisverzeichnis fuer alle lokal gespeicherten Daten.

    Windows: ``%LOCALAPPDATA%\\LocalAlly``
    Sonst:   ``$XDG_DATA_HOME/local-ally`` bzw. ``~/.local/share/local-ally``

    Ueber ``LOCAL_ALLY_DATA_DIR`` laesst sich der Ort ueberschreiben - das
    nutzen die Tests, damit sie nie echte Nutzerdaten anfassen.
    """
    override = os.environ.get("LOCAL_ALLY_DATA_DIR")
    if override:
        base = Path(override)
    elif is_windows():
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / APP_NAME
    else:
        xdg = os.environ.get("XDG_DATA_HOME")
        base = Path(xdg) / "local-ally" if xdg else Path.home() / ".local" / "share" / "local-ally"
    base.mkdir(parents=True, exist_ok=True)
    return base


def database_path() -> Path:
    return data_dir() / "local_ally.sqlite3"


def settings_path() -> Path:
    return data_dir() / "settings.json"


def models_dir() -> Path:
    path = data_dir() / "models"
    path.mkdir(parents=True, exist_ok=True)
    return path


def vosk_models_dir() -> Path:
    path = models_dir() / "vosk"
    path.mkdir(parents=True, exist_ok=True)
    return path


def whisper_models_dir() -> Path:
    path = models_dir() / "whisper"
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_path() -> Path:
    return data_dir() / "local_ally.log"


def target_stem(target: str) -> str:
    """Dateiname eines Startziels ohne Endung - unabhaengig vom Betriebssystem.

    Startziele stammen aus Windows-Quellen und enthalten Backslashes.
    ``Path(...).stem`` wuerde sie ausserhalb von Windows nicht zerlegen und
    den ganzen Pfad zurueckgeben. Fuer Shell- und URI-Ziele gibt es keinen
    sinnvollen Dateinamen.
    """
    value = (target or "").strip().strip('"')
    if not value or value.lower().startswith("shell:") or "://" in value:
        return ""
    parser = PureWindowsPath if "\\" in value else PurePath
    return parser(value).stem
