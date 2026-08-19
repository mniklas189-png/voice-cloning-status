"""Bruecke zwischen Absichtserkennung und Aktionen.

Ein einziger Befehl statt vieler: er fragt den Vergleicher aus
:mod:`local_ally.intents`, welche Absicht zum Satz passt, und laesst sie von
der zugehoerigen Aktion aus :mod:`local_ally.actions` ausfuehren. Neue
Faehigkeiten entstehen damit als Daten (Katalog) plus Funktion (Aktion) -
hier aendert sich nichts mehr.

Hier liegt auch die Reihenfolge bei kritischen Aktionen: erst klaeren,
*was* gemeint ist, dann fragen, ob es wirklich passieren soll.
"""

from __future__ import annotations

import logging

from ..actions import ActionContext, ActionRegistry, default_registry
from ..actions.backends import SystemBackend, create_backend
from ..actions.base import AssistantHooks
from ..app_index.models import AppEntry
from ..intents import IntentMatcher, default_matcher
from .base import (
    Command,
    CommandContext,
    CommandResult,
    Intent,
    PendingChoice,
    PendingConfirmation,
)

log = logging.getLogger(__name__)


class IntentCommand(Command):
    id = "intent"
    description = "Erkennt Absichten und führt die zugehörige Aktion aus"

    def __init__(
        self,
        matcher: IntentMatcher | None = None,
        actions: ActionRegistry | None = None,
        backend: SystemBackend | None = None,
        assistant: AssistantHooks | None = None,
        timers=None,
    ) -> None:
        self.matcher = matcher or default_matcher()
        self.actions = actions or default_registry()
        self.backend = backend or create_backend()
        self.assistant = assistant
        self.timers = timers

    # --- Erkennen ------------------------------------------------------
    def match(self, text: str, context: CommandContext) -> Intent | None:
        found = self.matcher.match(text)
        if found is None:
            return None
        return Intent(
            name=found.id,
            raw_text=text,
            slots=dict(found.slots),
            payload=found,
        )

    # --- Ausfuehren ----------------------------------------------------
    def execute(self, intent: Intent, context: CommandContext) -> CommandResult:
        found = intent.payload
        if found is None:
            return CommandResult.failure("Absicht ohne Inhalt.", intent)

        # Ein neuer Befehl hebt alles Offene auf. Ohne das wuerde ein "ja"
        # viel spaeter noch eine laengst vergessene Rueckfrage ausloesen.
        context.clear_pending()

        return self._start(intent, context, chosen_app=None)

    def _start(
        self, intent: Intent, context: CommandContext, chosen_app: AppEntry | None
    ) -> CommandResult:
        found = intent.payload
        if not found.spec.confirm or not getattr(context.settings, "confirm_critical", True):
            return self.run(intent, context, chosen_app=chosen_app)

        # Kritische Aktion: erst klaeren, worauf sie sich bezieht.
        entry, candidates = self._resolve(found, context, chosen_app)
        if entry is None and candidates:   # mehrdeutig - erst auswählen lassen
            context.pending_choice = PendingChoice(intent=intent)
            return CommandResult(
                ok=True,
                message="Welches Programm meinst du?",
                intent=intent,
                candidates=candidates,
                needs_choice=True,
            )

        # Auch wenn der Index nichts kennt, wird gefragt: das Programm kann
        # trotzdem laufen (dann greift die Aktion ueber den Prozessnamen).
        # Ohne Rueckfrage wuerde genau der Fall ungeschuetzt bleiben, den sie
        # abdecken soll.
        question = self._question(found, entry)
        context.pending_confirmation = PendingConfirmation(
            question=question, intent=intent, chosen_app=entry
        )
        return CommandResult(ok=True, message=question, intent=intent, needs_confirm=True)

    def run(
        self,
        intent: Intent,
        context: CommandContext,
        chosen_app: AppEntry | None = None,
    ) -> CommandResult:
        """Aktion ausfuehren - ohne weitere Rueckfrage."""
        found = intent.payload
        action_context = ActionContext(
            command=context,
            backend=self.backend,
            assistant=self.assistant,
            chosen_app=chosen_app,
            timers=self.timers,
        )
        outcome = self.actions.run(found, action_context)

        if outcome.needs_choice:
            # Die Aktion selbst ist unsicher - der urspruengliche Befehl
            # wird gemerkt, damit die Antwort dieselbe Absicht fortsetzt.
            context.pending_choice = PendingChoice(intent=intent)

        return CommandResult(
            ok=outcome.ok,
            message=outcome.message,
            intent=intent,
            app=outcome.app,
            candidates=list(outcome.candidates),
            needs_choice=outcome.needs_choice,
        )

    def continue_with(
        self, intent: Intent, context: CommandContext, app: AppEntry
    ) -> CommandResult:
        """Nach beantworteter Rueckfrage mit dem gewaehlten Programm weiter.

        Kritische Aktionen laufen dabei erneut durch die Bestaetigung - nur
        diesmal mit dem konkreten Namen in der Frage.
        """
        return self._start(intent, context, chosen_app=app)

    # --- Hilfen --------------------------------------------------------
    def _resolve(self, found, context: CommandContext, chosen_app: AppEntry | None):
        """Programm einer kritischen Absicht klaeren."""
        if chosen_app is not None:
            return chosen_app, []
        if "app" not in found.slots:
            return None, []

        from ..actions.apps import resolve_app

        action_context = ActionContext(
            command=context, backend=self.backend, assistant=self.assistant,
            timers=self.timers,
        )
        return resolve_app(found.slots["app"], action_context)

    @staticmethod
    def _question(found, entry: AppEntry | None) -> str:
        values = {**found.spec.defaults, **found.slots}
        if entry is not None:
            values["app"] = entry.name
        try:
            return found.spec.confirm.format(**values)
        except (KeyError, IndexError):
            return found.spec.confirm
