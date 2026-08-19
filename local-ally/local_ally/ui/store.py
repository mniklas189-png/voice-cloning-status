"""Schreibender Zugriff auf die Slint-Eigenschaften.

Warum diese Zwischenschicht - zwei Eigenheiten der Slint-Anbindung, die
beide *stumm* sind und deshalb keine Disziplin, sondern eine Schranke
brauchen:

1. **Von einem in Python erzeugten Listenmodell haelt Slint nur eine
   schwache Referenz.** Ein ``slint.ListModel``, das nur an einer
   Eigenschaft haengt, verschwindet bei einer Sammlung der
   Speicherbereinigung - ohne Ausnahme, ohne Meldung in der Anwendung. Die
   Liste in der Oberflaeche ist danach einfach leer, auch waehrend sie
   angezeigt wird. Weil das Modell einen Zyklus auf sich selbst hat, greift
   die Referenzzaehlung nicht: es passiert zeitversetzt und wirkt zufaellig.

2. **Ein unbekannter Eigenschaftsname wird beim Schreiben verschluckt.**
   ``Store.gibtEsNicht = 1`` loest nichts aus. Wer eine Eigenschaft in
   ``state.slint`` umbenennt und die Bruecke vergisst, sieht keinen Fehler,
   sondern eine Anzeige, die sich nie mehr aendert.

Deshalb schreibt die Bruecke ihre Listen als gewoehnliche Python-Listen
hierher. Diese Klasse baut das Modell, haelt es fest und prueft den Namen -
``slint.ListModel`` kommt im uebrigen Anwendungscode nicht mehr vor.
``tests/test_ui_store.py`` haelt beides fest.
"""

from __future__ import annotations

import logging

import slint

log = logging.getLogger(__name__)


class UiStore:
    """Huelle um ein Slint-Global mit Namenspruefung und Modellhaltung."""

    # __slots__ statt eines Woerterbuchs: sonst liefe jede eigene Zuweisung
    # ueber __setattr__ und landete in der Namenspruefung.
    __slots__ = ("_target", "_names", "_models")

    def __init__(self, target) -> None:
        object.__setattr__(self, "_target", target)
        object.__setattr__(
            self, "_names", frozenset(n for n in dir(target) if not n.startswith("_"))
        )
        # Die einzige starke Referenz auf die Listenmodelle. Nach
        # Eigenschaftsnamen abgelegt und damit von Natur aus begrenzt: ein
        # neues Modell loest das alte ab, statt sich anzusammeln.
        object.__setattr__(self, "_models", {})

        # Eine Eigenschaft der Oberflaeche darf nicht heissen wie ein Teil
        # dieser Klasse - sonst laese man beim Zugriff stillschweigend das
        # Falsche. Lieber sofort scheitern als still danebenliegen.
        shadowed = sorted(name for name in self._names if hasattr(type(self), name))
        if shadowed:
            raise AttributeError(
                f"Diese Eigenschaften verdecken Teile von UiStore: {shadowed}. "
                "Bitte in state.slint umbenennen."
            )

    def __setattr__(self, name: str, value) -> None:
        if name not in self._names:
            raise AttributeError(
                f"„{name}“ gibt es in der Oberfläche nicht. "
                f"Bekannt sind u.a.: {', '.join(sorted(self._names)[:6])} ..."
            )

        if isinstance(value, (list, tuple)):
            value = slint.ListModel(list(value))
        if isinstance(value, slint.ListModel):
            self._models[name] = value
        setattr(self._target, name, value)

    def __getattr__(self, name: str):
        # Nur fuer Namen, die nicht in __slots__ stehen - also fuer Lesezugriffe
        # auf die Eigenschaften des Globals.
        return getattr(self._target, name)

    # --- Fuer Tests und Fehlersuche ------------------------------------
    @property
    def property_names(self) -> frozenset[str]:
        return self._names

    @property
    def held_models(self) -> dict[str, slint.ListModel]:
        return dict(self._models)
