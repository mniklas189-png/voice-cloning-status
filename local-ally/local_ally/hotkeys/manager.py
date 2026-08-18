"""Globale Tastenkuerzel ueber ``pynput``.

Warum pynput: es hoert systemweit mit - also auch, wenn Local Ally nicht im
Vordergrund ist - meldet Druecken **und** Loslassen (fuer Push-to-Talk
noetig) und braucht unter Windows keine Administratorrechte. Die Alternative
``keyboard`` verlangt unter Linux root und meldet nur einzelne Ereignisse.

Fehlt das Paket oder laesst sich kein Zuhoerer starten, bleibt Local Ally
vollstaendig bedienbar - die Einstellungsseite sagt dann, was fehlt.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any

from .keys import Hotkey, HotkeyError, find_conflicts
from .tracker import ComboTracker, EventCallback

log = logging.getLogger(__name__)


@dataclass(slots=True)
class HotkeyStatus:
    """Was die Einstellungsseite ueber die Tastenkuerzel anzeigt."""

    available: bool = False          # System-Anbindung nutzbar?
    active: bool = False             # laeuft gerade ein Zuhoerer?
    detail: str = ""                 # Klartext zum Zustand
    errors: list[str] = field(default_factory=list)   # fehlerhafte Eingaben

    @property
    def ok(self) -> bool:
        return self.available and self.active and not self.errors


def backend_available() -> tuple[bool, str]:
    """Ist die Systemanbindung nutzbar?"""
    try:
        from pynput import keyboard  # noqa: F401
    except Exception as exc:  # ImportError, aber auch fehlende X11-Anbindung
        return False, f"pynput nicht verfügbar ({exc.__class__.__name__}) – Installation: pip install pynput"
    return True, "bereit"


def canonical_key(key: Any) -> str | None:
    """Eine pynput-Taste in unseren Namensraum uebersetzen."""
    from pynput import keyboard

    if isinstance(key, keyboard.Key):
        name = key.name
        for prefix in ("ctrl", "alt", "shift", "cmd"):
            if name.startswith(prefix):
                return "cmd" if prefix == "cmd" else prefix
        if name == "esc":
            return "escape"
        return name

    if isinstance(key, keyboard.KeyCode):
        char = key.char
        if char and char.isprintable() and not char.isspace():
            return char.lower()
        # Bei gedruecktem Strg liefert Windows Steuerzeichen statt Buchstaben -
        # dann hilft der virtuelle Tastencode weiter.
        vk = getattr(key, "vk", None)
        if vk is not None:
            if 0x30 <= vk <= 0x5A:            # 0-9 und A-Z
                return chr(vk).lower()
            if 0x60 <= vk <= 0x69:            # Ziffernblock 0-9
                return chr(vk - 0x30)
            return f"vk{vk}"
    return None


class HotkeyManager:
    """Meldet globale Tastenkuerzel an und wieder ab.

    ``on_event`` wird aus dem Zuhoerer-Thread aufgerufen. Der Controller
    reicht die Ereignisse deshalb ueber den Ereignisbus weiter, genau wie die
    Spracherkennung - Anwendungslogik laeuft nur in einem Thread.
    """

    def __init__(self, on_event: EventCallback) -> None:
        self._on_event = on_event
        self._lock = threading.Lock()
        self._listener = None
        self._tracker: ComboTracker | None = None
        self._status = HotkeyStatus(detail="nicht eingerichtet")

    @property
    def status(self) -> HotkeyStatus:
        return self._status

    def apply(self, bindings: dict[str, str], *, enabled: bool = True) -> HotkeyStatus:
        """Kombinationen setzen. ``bindings`` bildet Aktion -> Eingabetext ab."""
        parsed: dict[str, Hotkey] = {}
        errors: list[str] = []

        for action, value in bindings.items():
            if not (value or "").strip():
                continue
            try:
                parsed[action] = Hotkey.parse(value)
            except HotkeyError as exc:
                errors.append(f"{action}: {exc}")

        errors.extend(find_conflicts(parsed))

        if not enabled:
            self.stop()
            self._status = HotkeyStatus(
                available=backend_available()[0], active=False,
                detail="ausgeschaltet", errors=errors,
            )
            return self._status

        if errors:
            # Bei fehlerhafter Eingabe lieber gar nichts anmelden, als eine
            # halbe Belegung zu aktivieren.
            self.stop()
            available, _ = backend_available()
            self._status = HotkeyStatus(
                available=available, active=False,
                detail="nicht aktiv – bitte Eingabe korrigieren", errors=errors,
            )
            return self._status

        available, detail = backend_available()
        if not available:
            self.stop()
            self._status = HotkeyStatus(available=False, active=False, detail=detail)
            return self._status

        if not parsed:
            self.stop()
            self._status = HotkeyStatus(available=True, active=False, detail="keine Kürzel vergeben")
            return self._status

        try:
            self._start(parsed)
        except Exception as exc:
            log.exception("Tastenkürzel konnten nicht angemeldet werden")
            self._status = HotkeyStatus(
                available=True, active=False,
                detail=f"konnte nicht angemeldet werden: {exc}",
            )
            return self._status

        combos = ", ".join(hotkey.display() for hotkey in parsed.values())
        self._status = HotkeyStatus(available=True, active=True, detail=f"aktiv: {combos}")
        return self._status

    def _start(self, bindings: dict[str, Hotkey]) -> None:
        from pynput import keyboard

        self.stop()
        with self._lock:
            tracker = ComboTracker(bindings, self._on_event)

            def on_press(key):
                name = canonical_key(key)
                if name:
                    tracker.press(name)

            def on_release(key):
                name = canonical_key(key)
                if name:
                    tracker.release(name)

            listener = keyboard.Listener(on_press=on_press, on_release=on_release)
            listener.daemon = True
            listener.start()
            self._tracker, self._listener = tracker, listener
        log.info("Tastenkürzel angemeldet: %s", {k: str(v) for k, v in bindings.items()})

    def stop(self) -> None:
        with self._lock:
            listener, self._listener = self._listener, None
            tracker, self._tracker = self._tracker, None
        if tracker is not None:
            tracker.reset()
        if listener is not None:
            try:
                listener.stop()
            except Exception:  # beim Herunterfahren nicht eskalieren
                log.debug("Zuhörer ließ sich nicht sauber stoppen", exc_info=True)
