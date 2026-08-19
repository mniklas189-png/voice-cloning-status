"""Starthelfer fuer Programme.

Das Erkennen von "Öffne <Programm>" liegt inzwischen im Absichtskatalog
(:mod:`local_ally.intents.catalog`), das Ausfuehren in
:mod:`local_ally.actions.apps`. Hier bleibt die gemeinsame Funktion, die ein
Programm startet und die Nutzung mitzaehlt - sie wird auch von der
Rueckfrage-Liste und aus der Oberflaeche heraus verwendet.
"""

from __future__ import annotations

import logging

from ..app_index import launcher
from .base import CommandContext, CommandResult, Intent

log = logging.getLogger(__name__)


def launch_match(app, context: CommandContext, intent: Intent | None = None) -> CommandResult:
    """Startet ein Programm und vermerkt die Nutzung im Index."""
    result = launcher.launch(app)
    if result.ok:
        context.repository.note_launch(app.id)
        return CommandResult.success(result.message, intent=intent, app=app)
    return CommandResult.failure(result.message, intent)


def continue_choice(app, context: CommandContext, intent: Intent | None = None,
                    runner=None) -> CommandResult:
    """Eine beantwortete Rueckfrage fortsetzen.

    Entscheidend ist, *welche* Absicht die Rueckfrage ausgeloest hat: nach
    "schließ ..." muss die Auswahl schliessen, nicht starten. Nur wenn keine
    Absicht gemerkt ist (etwa bei einem Klick in der Programmliste), wird
    gestartet.
    """
    pending = context.pending_choice
    context.pending_choice = None
    context.pending_candidates = []

    if pending is None:
        return launch_match(app, context, intent)

    # Wer die Rueckfrage gestellt hat, fuehrt sie auch fort - eine eigene
    # Funktion darf nicht im Absichtskatalog landen.
    if pending.handler is not None:
        return pending.handler.continue_with(pending.intent, context, app)

    if runner is None:
        from .intent_command import IntentCommand

        runner = IntentCommand()
    return runner.continue_with(pending.intent, context, app)
