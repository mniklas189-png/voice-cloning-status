"""Globale Tastenkuerzel - Stummschaltung und Push-to-Talk.

* :mod:`.keys`    - Tastenkombinationen lesen, pruefen, vergleichen
* :mod:`.tracker` - Zustandsautomat: welche Kombination ist gerade gedrueckt?
* :mod:`.manager` - Anbindung an das Betriebssystem (pynput)

Die Trennung ist Absicht: der Zustandsautomat kennt nur Tastennamen als
Zeichenketten und laesst sich damit ohne echte Tastatur testen.
"""

from .keys import Hotkey, HotkeyError
from .manager import HotkeyManager, HotkeyStatus
from .tracker import PRESS, RELEASE

# Aktionsnamen. Sie tauchen in Fehlermeldungen auf und sind deshalb gleich
# die Bezeichnungen, die der Nutzer in den Einstellungen sieht.
ACTION_MUTE = "Stummschaltung"
ACTION_PTT = "Push-to-Talk"

__all__ = [
    "Hotkey", "HotkeyError", "HotkeyManager", "HotkeyStatus",
    "ACTION_MUTE", "ACTION_PTT", "PRESS", "RELEASE",
]
