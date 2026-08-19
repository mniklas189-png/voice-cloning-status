"""Eigene Funktionen - vom Nutzer angelegte Sprachbefehle.

"Befehl: lernen, Aktion: App öffnen, App: Anki" - und "lernen" startet Anki.

* :mod:`.models`     - Datentypen und das Register der Aktionsarten
* :mod:`.repository` - dauerhaft in derselben SQLite-Datei wie der App-Index
* :mod:`.runner`     - fuehrt eine eigene Funktion aus

Eine neue Aktionsart braucht einen Eintrag in :data:`models.ACTION_TYPES`
und eine Funktion in :mod:`.runner` - sonst nichts. Die Oberflaeche baut
ihre Auswahl aus demselben Register auf.
"""

from .models import ACTION_TYPES, CustomActionType, CustomCommand, action_type
from .repository import CustomCommandRepository

__all__ = [
    "ACTION_TYPES",
    "CustomActionType",
    "CustomCommand",
    "action_type",
    "CustomCommandRepository",
]
