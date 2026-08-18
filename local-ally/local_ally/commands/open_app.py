"""Befehl: "Oeffne <Programm>".

Es gibt bewusst *keinen* Eintrag pro Programm. Der Befehl erkennt nur das
Muster "<Verb> <Name>" und ueberlaesst alles Weitere dem App-Index. Ein neu
installiertes Programm ist damit nach dem naechsten Index-Lauf automatisch
per Sprache startbar.
"""

from __future__ import annotations

import logging

from ..app_index import launcher
from ..app_index.matching import find_matches, is_confident
from .base import Command, CommandContext, CommandResult, Intent
from .phrases import (
    OPEN_VERBS_PREFIX,
    OPEN_VERBS_SUFFIX,
    prepare,
    strip_polite_prefix,
    trim_filler,
)

log = logging.getLogger(__name__)

INTENT_OPEN_APP = "open_app"


class OpenAppCommand(Command):
    id = INTENT_OPEN_APP
    description = "Startet ein installiertes Programm"
    examples = ("Oeffne Lunar Client", "Starte Discord", "Spotify oeffnen")

    def match(self, text: str, context: CommandContext) -> Intent | None:
        tokens = trim_filler(strip_polite_prefix(prepare(text)))
        if not tokens:
            return None

        name_tokens: list[str] | None = None

        if tokens[0] in OPEN_VERBS_PREFIX:
            name_tokens = tokens[1:]
        elif len(tokens) > 1 and tokens[-1] in OPEN_VERBS_SUFFIX:
            name_tokens = tokens[:-1]

        if name_tokens is None:
            return None

        name_tokens = trim_filler(name_tokens)
        # Auch ohne Namen wird der Befehl erkannt - dann fragt Local Ally nach,
        # statt den Satz still zu verwerfen.
        return Intent(
            name=INTENT_OPEN_APP,
            raw_text=text,
            slots={"app": " ".join(name_tokens)},
        )

    def execute(self, intent: Intent, context: CommandContext) -> CommandResult:
        spoken = intent.slot("app").strip()
        if not spoken:
            return CommandResult.failure("Welches Programm soll ich öffnen?", intent)

        apps = context.apps()
        if not apps:
            return CommandResult.failure(
                "Der Programm-Index ist noch leer. Bitte einmal aktualisieren.", intent
            )

        settings = context.settings
        matches = find_matches(
            spoken,
            apps,
            threshold=settings.match_threshold,
            limit=max(settings.max_candidates, 1),
        )

        if not matches:
            return CommandResult.failure(f"Ich habe kein Programm namens „{spoken}“ gefunden.", intent)

        # Lieber nachfragen als das falsche Programm starten.
        if not is_confident(matches) or not settings.auto_execute:
            reason = (
                "Welches Programm meinst du?"
                if not is_confident(matches)
                else f"Soll ich „{matches[0].app.name}“ starten?"
            )
            return CommandResult(
                ok=True,
                message=reason,
                intent=intent,
                candidates=matches,
                needs_choice=True,
            )

        return launch_match(matches[0].app, context, intent)


def launch_match(app, context: CommandContext, intent: Intent | None = None) -> CommandResult:
    """Startet ein Programm und vermerkt die Nutzung im Index."""
    result = launcher.launch(app)
    if result.ok:
        context.repository.note_launch(app.id)
        return CommandResult.success(result.message, intent=intent, app=app)
    return CommandResult.failure(result.message, intent)
