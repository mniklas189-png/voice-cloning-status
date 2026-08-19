"""Schnittstelle zum Betriebssystem.

Alles, was Local Ally am Rechner tut, laeuft ueber diese eine Schnittstelle.
Das haelt die Aktionen frei von Plattformdetails und macht sie testbar: in
den Tests steht hier eine Attrappe, die nur mitschreibt.

Die Grundfassung kann nichts und sagt das auch - jede Plattform ueberschreibt
davon, was sie unterstuetzt. So gibt es nie einen stillen Fehlschlag,
sondern immer einen verstaendlichen Satz.
"""

from __future__ import annotations

import sys


class NotSupported(RuntimeError):
    """Diese Funktion gibt es auf dem laufenden System nicht."""


class SystemBackend:
    """Grundfassung: meldet fuer jede Faehigkeit, dass sie fehlt."""

    id = "none"
    display_name = "kein Systemzugriff"

    # --- Hilfen --------------------------------------------------------
    def _unsupported(self, what: str) -> "NotSupported":
        return NotSupported(f"{what} wird auf diesem System nicht unterstützt.")

    # --- Audio ---------------------------------------------------------
    def volume_up(self, steps: int = 1) -> None:
        raise self._unsupported("Lautstärke ändern")

    def volume_down(self, steps: int = 1) -> None:
        raise self._unsupported("Lautstärke ändern")

    def volume_set(self, percent: int) -> None:
        raise self._unsupported("Lautstärke setzen")

    def volume_mute(self, muted: bool) -> None:
        raise self._unsupported("Stummschalten")

    def audio_devices(self) -> list[str]:
        raise self._unsupported("Audiogeräte auflisten")

    def set_audio_device(self, name: str) -> str:
        raise self._unsupported("Audiogerät wechseln")

    # --- Medien --------------------------------------------------------
    def media(self, command: str) -> None:
        """``playpause`` | ``next`` | ``previous``"""
        raise self._unsupported("Mediensteuerung")

    # --- System --------------------------------------------------------
    def lock(self) -> None:
        raise self._unsupported("Sperren")

    def shutdown(self) -> None:
        raise self._unsupported("Herunterfahren")

    def restart(self) -> None:
        raise self._unsupported("Neustarten")

    def sleep(self) -> None:
        raise self._unsupported("Energiesparmodus")

    def screen_off(self) -> None:
        raise self._unsupported("Bildschirm ausschalten")

    def open_settings(self, page: str = "") -> None:
        raise self._unsupported("Einstellungen öffnen")

    def open_task_manager(self) -> None:
        raise self._unsupported("Task-Manager öffnen")

    def brightness_step(self, delta: int) -> int:
        raise self._unsupported("Helligkeit ändern")

    def brightness_set(self, percent: int) -> None:
        raise self._unsupported("Helligkeit setzen")

    def display_mode(self, mode: str) -> None:
        """``switch`` | ``extend`` | ``duplicate`` | ``internal`` | ``external``"""
        raise self._unsupported("Anzeige umschalten")

    # --- Fenster -------------------------------------------------------
    # ``process`` leer heisst: das aktive Fenster. Ist ein Prozessname
    # angegeben, wird dessen Fenster gesucht ("minimier Discord").
    def window_switch(self) -> None:
        raise self._unsupported("Fenster wechseln")

    def window_minimize(self, process: str = "") -> None:
        raise self._unsupported("Fenster minimieren")

    def window_maximize(self, process: str = "") -> None:
        raise self._unsupported("Fenster maximieren")

    def window_close(self, process: str = "") -> None:
        raise self._unsupported("Fenster schließen")

    # --- Prozesse ------------------------------------------------------
    def running_processes(self) -> list[str]:
        raise self._unsupported("Laufende Programme ermitteln")

    def close_process(self, name: str) -> int:
        """Beendet freundlich; Rueckgabe: Anzahl beendeter Prozesse."""
        raise self._unsupported("Programme schließen")

    def focus_process(self, name: str) -> bool:
        raise self._unsupported("Zu einem Programm wechseln")

    # --- Eingabe -------------------------------------------------------
    def type_text(self, text: str) -> None:
        """Text in das aktive Fenster tippen."""
        raise self._unsupported("Text eingeben")

    def beep(self) -> None:
        """Kurzes Signal - fuer abgelaufene Timer."""
        raise self._unsupported("Signalton")

    # --- Dateien -------------------------------------------------------
    def known_folder(self, key: str) -> str:
        raise self._unsupported("Ordner öffnen")

    def open_path(self, path: str) -> None:
        raise self._unsupported("Ordner öffnen")

    def search_files(self, query: str) -> None:
        raise self._unsupported("Dateisuche")


def create_backend() -> SystemBackend:
    """Passendes Backend fuer das laufende System."""
    if sys.platform.startswith("win"):
        from .windows import WindowsBackend

        return WindowsBackend()
    if sys.platform.startswith("linux"):
        from .linux import LinuxBackend

        return LinuxBackend()
    return SystemBackend()
