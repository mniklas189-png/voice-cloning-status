"""Zustandsautomat fuer gedrueckte Tastenkombinationen.

Er kennt nur Tastennamen als Zeichenketten und weiss nichts vom
Betriebssystem - dadurch laesst sich das Verhalten (auch Push-to-Talk mit
Druecken und Loslassen) ohne echte Tastatur testen.
"""

from __future__ import annotations

import logging
from typing import Callable

from .keys import Hotkey

log = logging.getLogger(__name__)

# (Aktion, "press" | "release")
EventCallback = Callable[[str, str], None]

PRESS = "press"
RELEASE = "release"


class ComboTracker:
    def __init__(self, bindings: dict[str, Hotkey], on_event: EventCallback) -> None:
        self._bindings = dict(bindings)
        self._on_event = on_event
        self._pressed: set[str] = set()
        self._active: set[str] = set()

    @property
    def pressed(self) -> set[str]:
        return set(self._pressed)

    @property
    def active(self) -> set[str]:
        return set(self._active)

    def press(self, key: str) -> None:
        if not key or key in self._pressed:
            return  # Tastenwiederholung ignorieren
        self._pressed.add(key)
        for action, hotkey in self._bindings.items():
            if action not in self._active and hotkey.matches(self._pressed):
                self._active.add(action)
                self._emit(action, PRESS)

    def release(self, key: str) -> None:
        if not key:
            return
        self._pressed.discard(key)
        for action in sorted(self._active):
            if not self._bindings[action].matches(self._pressed):
                self._active.discard(action)
                self._emit(action, RELEASE)

    def reset(self) -> None:
        """Alles loslassen - z.B. wenn die Anwendung den Fokus verliert."""
        for action in sorted(self._active):
            self._emit(action, RELEASE)
        self._pressed.clear()
        self._active.clear()

    def _emit(self, action: str, phase: str) -> None:
        try:
            self._on_event(action, phase)
        except Exception:  # ein Fehler im Empfaenger darf die Tastatur nicht blockieren
            log.exception("Hotkey-Empfänger für %s (%s) fehlgeschlagen", action, phase)
