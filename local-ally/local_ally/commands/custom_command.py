"""Selbst angelegte Sprachbefehle ausfuehren.

Eigene Funktionen sind Daten, keine Programmierung: der Nutzer legt in der
Oberflaeche einen Satz und eine Aktionsart an, beides landet in der
Datenbank. Dieser Befehl schlaegt jeden gesprochenen Satz dort nach und
laesst :mod:`local_ally.custom.runner` die passende Aktion ausfuehren.

Der Vorrang ist Absicht: eigene Funktionen werden *vor* dem Absichtskatalog
geprueft. Wer "Musik" auf ein eigenes Programm legt, meint sein Programm -
nicht die eingebaute Medienwiedergabe. Offene Rueckfragen behalten aber
ihren Vorrang, damit ein "ja" nicht zur eigenen Funktion wird.
"""

from __future__ import annotations

import logging
from typing import Callable, Sequence

from ..actions.backends import SystemBackend, create_backend
from ..actions.base import ActionContext, AssistantHooks
from ..app_index.models import AppEntry
from ..custom.matching import find_command
from ..custom.models import CustomCommand
from ..custom.repository import CustomCommandRepository
from ..custom.runner import run as run_custom
from .base import Command, CommandContext, CommandResult, Intent, PendingChoice

log = logging.getLogger(__name__)

INTENT_CUSTOM = "custom"


class CustomCommandRunner(Command):
    """Vergleicht gesprochene Saetze mit den eigenen Funktionen."""

    id = INTENT_CUSTOM
    description = "Führt selbst angelegte Funktionen aus"

    def __init__(
        self,
        repository: CustomCommandRepository | None = None,
        provider: Callable[[], Sequence[CustomCommand]] | None = None,
        backend: SystemBackend | None = None,
        assistant: AssistantHooks | None = None,
        timers=None,
    ) -> None:
        self.repository = repository
        self.backend = backend or create_backend()
        self.assistant = assistant
        self.timers = timers
        # Die Liste wird zwischengespeichert: sonst laege bei jedem Satz eine
        # Datenbankabfrage im Weg. Der Controller ruft nach jeder Aenderung
        # :meth:`refresh` auf.
        self._provider = provider
        self._cache: list[CustomCommand] | None = None

    # --- Bestand -------------------------------------------------------
    def refresh(self) -> None:
        """Zwischenspeicher verwerfen - nach Anlegen, Aendern, Loeschen."""
        self._cache = None

    def commands(self) -> list[CustomCommand]:
        if self._cache is None:
            if self._provider is not None:
                self._cache = list(self._provider())
            elif self.repository is not None:
                self._cache = self.repository.all(only_enabled=True)
            else:
                self._cache = []
        return self._cache

    # --- Erkennen ------------------------------------------------------
    def match(self, text: str, context: CommandContext) -> Intent | None:
        commands = self.commands()
        if not commands:
            return None
        found = find_command(text, commands)
        if found is None:
            return None
        command, score = found
        log.debug("Eigene Funktion %r erkannt (%.2f)", command.phrase, score)
        return Intent(
            name=f"{INTENT_CUSTOM}.{command.action}",
            raw_text=text,
            slots={"phrase": command.phrase, "action": command.action},
            payload=command,
        )

    # --- Ausfuehren ----------------------------------------------------
    def execute(self, intent: Intent, context: CommandContext) -> CommandResult:
        command = intent.payload
        if not isinstance(command, CustomCommand):
            return CommandResult.failure("Eigene Funktion ohne Inhalt.", intent)

        # Ein neuer Befehl hebt alles Offene auf - genau wie im Katalog.
        context.clear_pending()
        return self._run(intent, context, chosen_app=None)

    def continue_with(
        self, intent: Intent, context: CommandContext, app: AppEntry
    ) -> CommandResult:
        """Nach beantworteter Rueckfrage mit dem gewaehlten Programm weiter."""
        return self._run(intent, context, chosen_app=app)

    def _run(
        self, intent: Intent, context: CommandContext, chosen_app: AppEntry | None
    ) -> CommandResult:
        command: CustomCommand = intent.payload
        action_context = ActionContext(
            command=context,
            backend=self.backend,
            assistant=self.assistant,
            chosen_app=chosen_app,
            timers=self.timers,
        )
        outcome = run_custom(command, action_context)

        if outcome.needs_choice:
            # Die Antwort setzt *diese* Funktion fort, nicht den Katalog.
            context.pending_choice = PendingChoice(intent=intent, handler=self)
        elif outcome.ok and self.repository is not None and command.id:
            try:
                self.repository.note_use(command.id)
            except Exception:      # Statistik darf nie einen Befehl kosten
                log.debug("Zaehler für %r nicht gespeichert", command.phrase)

        return CommandResult(
            ok=outcome.ok,
            message=outcome.message,
            intent=intent,
            app=outcome.app,
            candidates=list(outcome.candidates),
            needs_choice=outcome.needs_choice,
        )
