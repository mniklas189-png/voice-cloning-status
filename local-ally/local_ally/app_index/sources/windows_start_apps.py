"""Quelle: ``Get-StartApps`` (PowerShell).

Diese Quelle liefert genau die Liste, die Windows selbst im Startmenue
anzeigt - inklusive Store-/UWP-Apps wie Spotify oder WhatsApp, die es weder
als .lnk noch in der Uninstall-Registry gibt.

Der Start erfolgt ueber ``shell:AppsFolder\\<AppID>``. Das ist der offizielle
Weg, eine App unabhaengig von ihrem Typ zu starten, und funktioniert fuer
Win32- und Store-Apps gleichermassen - ohne COM-Abhaengigkeit.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from typing import Iterator

from ..models import DiscoveredApp
from .base import looks_like_noise

log = logging.getLogger(__name__)

# ConvertTo-Json macht aus einem einzelnen Objekt kein Array - @() erzwingt es.
_PS_COMMAND = (
    "@(Get-StartApps | Select-Object Name, AppID) | ConvertTo-Json -Compress"
)
_TIMEOUT_SECONDS = 25


class StartAppsSource:
    id = "start_apps"
    display_name = "Startmenue (Windows-Liste, inkl. Store-Apps)"
    priority = 45

    def is_available(self) -> bool:
        return sys.platform.startswith("win")

    def discover(self) -> Iterator[DiscoveredApp]:
        payload = self._run_powershell()
        for entry in payload:
            name = str(entry.get("Name", "")).strip()
            app_id = str(entry.get("AppID", "")).strip()
            if not name or not app_id or looks_like_noise(name):
                continue
            yield DiscoveredApp(
                name=name,
                launch_target=f"shell:AppsFolder\\{app_id}",
                launch_kind="shell",
                source=self.id,
                priority=self.priority,
                aliases=self._aliases(app_id),
            )

    @staticmethod
    def _aliases(app_id: str) -> list[str]:
        # Beispiel: "SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify" -> "Spotify"
        tail = app_id.split("!")[-1]
        return [tail] if tail and tail != app_id else []

    def _run_powershell(self) -> list[dict]:
        try:
            completed = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy", "Bypass",
                    "-Command", _PS_COMMAND,
                ],
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_SECONDS,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError) as exc:
            log.warning("Get-StartApps nicht verfuegbar: %s", exc)
            return []

        if completed.returncode != 0 or not completed.stdout.strip():
            log.warning("Get-StartApps lieferte kein Ergebnis: %s", completed.stderr.strip()[:200])
            return []

        try:
            data = json.loads(completed.stdout)
        except ValueError:
            log.warning("Antwort von Get-StartApps war kein gueltiges JSON")
            return []
        return data if isinstance(data, list) else [data]
