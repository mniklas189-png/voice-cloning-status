"""Datentypen der Absichtserkennung."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:  # nur fuer Typpruefung - vermeidet einen Ringimport
    from .pattern import Pattern


@dataclass(slots=True)
class IntentSpec:
    """Beschreibung einer Absicht.

    ``templates`` sind Satzmuster (siehe :mod:`.pattern`), ``action`` ist der
    Name der ausfuehrenden Aktion. ``confirm`` traegt die Rueckfrage, wenn die
    Aktion kritisch ist - dann wird nichts ohne Zustimmung ausgefuehrt.
    """

    id: str
    action: str
    templates: Sequence[str]
    slots: dict[str, str] = field(default_factory=dict)   # Name -> Slot-Art
    defaults: dict[str, str] = field(default_factory=dict)
    confirm: str = ""
    priority: int = 0
    description: str = ""
    examples: tuple[str, ...] = ()

    # zur Laufzeit vorbereitet
    compiled: list["Pattern"] = field(default_factory=list, repr=False)


@dataclass(slots=True)
class IntentMatch:
    """Ein Treffer: welche Absicht, mit welchen Parametern, wie eindeutig."""

    spec: IntentSpec
    slots: dict[str, str]
    score: float
    text: str

    @property
    def id(self) -> str:
        return self.spec.id

    @property
    def action(self) -> str:
        return self.spec.action

    def slot(self, name: str, default: str = "") -> str:
        value = self.slots.get(name, "")
        if value:
            return value
        return self.spec.defaults.get(name, default)

    def __repr__(self) -> str:
        return f"<IntentMatch {self.spec.id} {self.slots} score={self.score:.2f}>"
