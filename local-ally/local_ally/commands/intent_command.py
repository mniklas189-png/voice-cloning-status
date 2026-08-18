"""Bruecke zwischen Absichtserkennung und Aktionen.

Ein einziger Befehl statt vieler: er fragt den Vergleicher aus
:mod:`local_ally.intents`, welche Absicht zum Satz passt, und laesst sie von
der zugehoerigen Aktion aus :mod:`local_ally.actions` ausfuehren. Neue
Faehigkeiten entstehen damit als Daten (Katalog) plus Funktion (Aktion) -
hier aendert sich nichts mehr.
"""

from __future__ import annotations

import logging

from ..actions import ActionContext, ActionRegistry, default_registry
from ..actions.backends import SystemBackend, create_backend
from ..actions.base import AssistantHooks
from ..intents import IntentMatcher, default_matcher
from .base import Command, CommandContext, CommandResult, Intent, PendingConfirmation

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
    ) -> None:
        self.matcher = matcher or default_matcher()
        self.actions = actions or default_registry()
        self.backend = backend or create_backend()
        self.assistant = assistant

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

        question = self._confirmation_question(found, context)
        if question:
            context.pending_confirmation = PendingConfirmation(question=question, intent=intent)
            return CommandResult(
                ok=True, message=question, intent=intent, needs_confirm=True
            )

        return self.run(intent, context)

    def run(self, intent: Intent, context: CommandContext) -> CommandResult:
        """Aktion ohne weitere Rueckfrage ausfuehren."""
        found = intent.payload
        action_context = ActionContext(
            command=context, backend=self.backend, assistant=self.assistant
        )
        outcome = self.actions.run(found, action_context)
        return CommandResult(
            ok=outcome.ok,
            message=outcome.message,
            intent=intent,
            candidates=list(outcome.candidates),
            needs_choice=outcome.needs_choice,
        )

    @staticmethod
    def _confirmation_question(found, context: CommandContext) -> str:
        """Rueckfrage einer kritischen Aktion - oder leer."""
        if not found.spec.confirm:
            return ""
        if not getattr(context.settings, "confirm_critical", True):
            return ""

        values = {**found.spec.defaults, **found.slots}
        if "app" in values:
            values["app"] = _display_name(values["app"], context)
        try:
            return found.spec.confirm.format(**values)
        except (KeyError, IndexError):
            return found.spec.confirm


def _display_name(spoken: str, context: CommandContext) -> str:
    """Den Namen nennen, den der Nutzer im Programm-Index sieht.

    "Soll ich Spotify schließen?" liest sich besser als der gesprochene
    Wortlaut - und zeigt zugleich, welches Programm gemeint ist.
    """
    from ..app_index.matching import find_matches, is_confident

    try:
        found = find_matches(
            spoken, context.apps(),
            threshold=context.settings.match_threshold, limit=2,
        )
    except Exception:  # ohne Index bleibt der gesprochene Name
        return spoken
    if found and is_confident(found):
        return found[0].app.name
    return spoken
