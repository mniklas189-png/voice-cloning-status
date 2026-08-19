"""Rueckfrage bei kritischen Aktionen.

Herunterfahren, Neustarten oder das Schliessen eines Programms koennen
Ungespeichertes kosten. Diese Aktionen laufen deshalb nie sofort: sie warten
auf ein klares Ja - per Sprache oder per Klick.
"""

from __future__ import annotations

from .base import Command, CommandContext, CommandResult, Intent
from .phrases import prepare, trim_filler

INTENT_CONFIRM = "confirm"
INTENT_DECLINE = "decline"

YES_WORDS = frozenset({
    "ja", "jap", "jo", "jawohl", "genau", "richtig", "klar", "sicher",
    "bestaetigen", "bestaetige", "mach", "machs", "tu", "tus", "los", "okay", "ok",
})
NO_WORDS = frozenset({
    "nein", "ne", "noe", "nicht", "abbrechen", "abbruch", "stopp", "stop",
    "lass", "vergiss", "doch", "warte", "halt",
})


class ConfirmCommand(Command):
    """Beantwortet eine offene Rueckfrage mit Ja oder Nein."""

    id = "confirm"
    description = "Bestätigt oder verwirft eine kritische Aktion"
    examples = ("Ja", "Nein", "Abbrechen")

    def __init__(self, runner=None) -> None:
        # Ausgefuehrt wird ueber denselben Befehl, der die Rueckfrage
        # ausgeloest hat - so gibt es nur einen Weg in die Aktionen.
        self._runner = runner

    def match(self, text: str, context: CommandContext) -> Intent | None:
        if context.pending_confirmation is None:
            return None

        tokens = trim_filler(prepare(text))
        # Nur kurze, reine Ja/Nein-Antworten. Sonst wuerde "mach es lauter"
        # als Zustimmung gelesen, weil es mit "mach" beginnt.
        if not tokens or len(tokens) > 2:
            return None
        if all(token in NO_WORDS for token in tokens):
            return Intent(INTENT_DECLINE, text)
        if all(token in YES_WORDS for token in tokens):
            return Intent(INTENT_CONFIRM, text)
        return None

    def execute(self, intent: Intent, context: CommandContext) -> CommandResult:
        pending = context.pending_confirmation
        context.pending_confirmation = None
        if pending is None:
            return CommandResult.failure("Es steht gerade keine Rückfrage offen.", intent)

        if intent.name == INTENT_DECLINE:
            return CommandResult.success("Alles klar, ich lasse es.", intent=intent)

        runner = self._runner
        if runner is None:
            from .intent_command import IntentCommand

            runner = IntentCommand()
        return runner.run(pending.intent, context, chosen_app=pending.chosen_app)
