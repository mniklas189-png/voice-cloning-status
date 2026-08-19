"""Schnittstelle und Verzeichnis der Aktionen."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from ..app_index.models import AppEntry, MatchResult
    from ..commands.base import CommandContext
    from ..intents.model import IntentMatch
    from .backends.base import SystemBackend

log = logging.getLogger(__name__)


@dataclass(slots=True)
class ActionResult:
    """Was die Aktion bewirkt hat - genau das, was die UI anzeigt."""

    ok: bool
    message: str
    candidates: list["MatchResult"] = field(default_factory=list)
    needs_choice: bool = False
    app: "AppEntry | None" = None      # was tatsaechlich betroffen war

    @classmethod
    def done(cls, message: str) -> "ActionResult":
        return cls(ok=True, message=message)

    @classmethod
    def failed(cls, message: str) -> "ActionResult":
        return cls(ok=False, message=message)


class AssistantHooks(Protocol):
    """Was eine Aktion vom laufenden Assistenten braucht.

    Bewusst winzig gehalten: nur die eigene Stummschaltung, damit
    "Mach mein Mikro aus" wirkt, ohne dass die Aktionen den Controller
    kennen muessen.
    """

    def set_mic_muted(self, muted: bool) -> None: ...

    def is_mic_muted(self) -> bool: ...


@dataclass(slots=True)
class ActionContext:
    """Alles, was eine Aktion zur Ausfuehrung braucht."""

    command: "CommandContext"       # Programm-Index, Einstellungen, Rueckfragen
    backend: "SystemBackend"        # Zugriff auf das Betriebssystem
    assistant: AssistantHooks | None = None
    # Aus einer beantworteten Rueckfrage: dieses Programm ist gemeint.
    # Damit entfaellt jede weitere Namenssuche - und die Aktion fuehrt aus,
    # statt erneut zu fragen.
    chosen_app: "AppEntry | None" = None

    @property
    def settings(self):
        return self.command.settings


ActionHandler = Callable[["IntentMatch", ActionContext], ActionResult]


class ActionRegistry:
    """Name -> Aktion."""

    def __init__(self) -> None:
        self._handlers: dict[str, ActionHandler] = {}

    def add(self, name: str, handler: ActionHandler) -> None:
        if name in self._handlers:
            raise ValueError(f"Aktion {name} ist bereits vergeben")
        self._handlers[name] = handler

    def get(self, name: str) -> ActionHandler | None:
        return self._handlers.get(name)

    def names(self) -> list[str]:
        return sorted(self._handlers)

    def run(self, match: "IntentMatch", context: ActionContext) -> ActionResult:
        handler = self._handlers.get(match.action)
        if handler is None:
            log.error("Keine Aktion für %s", match.action)
            return ActionResult.failed(f"Für „{match.id}“ fehlt noch die Aktion.")
        from .backends.base import NotSupported

        try:
            return handler(match, context)
        except NotSupported as exc:
            return ActionResult.failed(str(exc))
        except Exception as exc:  # eine Aktion darf die Anwendung nie stoppen
            log.exception("Aktion %s fehlgeschlagen", match.action)
            return ActionResult.failed(f"Das hat nicht geklappt: {exc}")


_registry = ActionRegistry()


def default_registry() -> ActionRegistry:
    """Das gemeinsame Verzeichnis - beim ersten Zugriff vollstaendig geladen."""
    _load_modules()
    return _registry


def register(name: str) -> Callable[[ActionHandler], ActionHandler]:
    """Dekorator: Funktion als Aktion eintragen."""

    def decorate(handler: ActionHandler) -> ActionHandler:
        _registry.add(name, handler)
        return handler

    return decorate


_loaded = False


def _load_modules() -> None:
    """Alle Aktionsmodule einmalig importieren."""
    global _loaded
    if _loaded:
        return
    _loaded = True
    from . import apps, audio, files, media, system, window  # noqa: F401
