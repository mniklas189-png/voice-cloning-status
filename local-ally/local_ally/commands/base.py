"""Schnittstelle und Datentypen fuer Sprachbefehle."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Sequence

from ..app_index.models import AppEntry, MatchResult
from ..app_index.repository import AppRepository
from ..settings import Settings


@dataclass(slots=True)
class Intent:
    """Was der Nutzer wollte - noch ohne Ausfuehrung."""

    name: str                       # z.B. "app.open"
    raw_text: str
    slots: dict[str, str] = field(default_factory=dict)
    payload: object = None          # erkannte Absicht, siehe local_ally.intents

    def slot(self, key: str, default: str = "") -> str:
        return self.slots.get(key, default)


@dataclass(slots=True)
class CommandResult:
    """Ergebnis eines Befehls - genau das, was die UI anzeigt."""

    ok: bool
    message: str
    intent: Intent | None = None
    app: AppEntry | None = None
    candidates: list[MatchResult] = field(default_factory=list)
    needs_choice: bool = False      # True => Local Ally fragt nach, welches
    needs_confirm: bool = False     # True => Local Ally fragt: wirklich?

    @classmethod
    def failure(cls, message: str, intent: Intent | None = None) -> "CommandResult":
        return cls(ok=False, message=message, intent=intent)

    @classmethod
    def success(cls, message: str, **kwargs) -> "CommandResult":
        return cls(ok=True, message=message, **kwargs)


@dataclass(slots=True)
class PendingConfirmation:
    """Eine kritische Aktion, die auf Zustimmung wartet."""

    question: str
    intent: Intent
    chosen_app: AppEntry | None = None   # bereits geklaerte Mehrdeutigkeit


@dataclass(slots=True)
class PendingChoice:
    """Eine Rueckfrage, welches Programm gemeint ist.

    Der urspruengliche Befehl wird mitgefuehrt: nach der Auswahl laeuft
    *dieselbe* Absicht weiter. Sonst wuerde ein "schließ ..." nach dem
    Anklicken zu einem "starte ...".
    """

    intent: Intent


@dataclass(slots=True)
class CommandContext:
    """Alles, was ein Befehl zur Ausfuehrung braucht.

    Die Liste der Programme kommt als Funktion statt als Wert: der Controller
    haelt sie zwischengespeichert und erneuert sie nur nach einem Index-Lauf.
    """

    repository: AppRepository
    settings: Settings
    apps: Callable[[], Sequence[AppEntry]]
    pending_candidates: list[MatchResult] = field(default_factory=list)
    pending_confirmation: PendingConfirmation | None = None
    pending_choice: PendingChoice | None = None
    # Zuletzt betroffenes Programm - loest Fuerwoerter auf ("mach ihn zu").
    last_app: AppEntry | None = None

    def clear_pending(self) -> None:
        """Alles Offene verwerfen - ein neuer Befehl hebt Rueckfragen auf."""
        self.pending_candidates = []
        self.pending_confirmation = None
        self.pending_choice = None


class Command(ABC):
    """Ein Sprachbefehl.

    :meth:`match` prueft nur, ob der Satz zu diesem Befehl passt - ohne
    Nebenwirkungen. Erst :meth:`execute` handelt. Diese Trennung macht das
    Parsen einzeln testbar.
    """

    id: str = ""
    description: str = ""
    examples: tuple[str, ...] = ()

    @abstractmethod
    def match(self, text: str, context: CommandContext) -> Intent | None:
        """Absicht erkennen oder ``None``."""

    @abstractmethod
    def execute(self, intent: Intent, context: CommandContext) -> CommandResult:
        """Absicht ausfuehren."""
