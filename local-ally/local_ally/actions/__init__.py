"""Aktionen: was Local Ally tatsaechlich tut.

Getrennt von der Absichtserkennung (:mod:`local_ally.intents`) und von der
Bedienung: eine Aktion bekommt eine erkannte Absicht und fuehrt sie aus.

* :mod:`.base`     - Schnittstelle, Ergebnis, Verzeichnis
* :mod:`.backends` - plattformabhaengige Umsetzung (Windows, Linux, keine)
* die uebrigen Module bringen je einen Themenbereich mit und tragen sich
  beim Import in das Verzeichnis ein.

Eine neue Faehigkeit braucht eine Funktion mit ``@register("bereich.name")``
und einen Eintrag im Absichtskatalog - sonst nichts.
"""

from .base import ActionContext, ActionRegistry, ActionResult, default_registry, register

__all__ = [
    "ActionContext",
    "ActionRegistry",
    "ActionResult",
    "default_registry",
    "register",
]
