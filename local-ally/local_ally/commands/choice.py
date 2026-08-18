"""Befehle fuer die Rueckfrage bei mehrdeutigen Namen.

Wenn Local Ally nachfragt ("Meintest du Discord oder Discord Canary?"), kann
der Nutzer per Sprache antworten - mit einer Zahl, einer Ordnungszahl oder
indem er den Namen genauer wiederholt. Diese Befehle greifen nur, solange
eine Rueckfrage offen ist.
"""

from __future__ import annotations

from ..app_index.matching import find_matches, is_confident
from .base import Command, CommandContext, CommandResult, Intent
from .open_app import launch_match
from .phrases import OPEN_VERBS_PREFIX, OPEN_VERBS_SUFFIX, prepare, trim_filler

INTENT_CHOICE = "choose_candidate"
INTENT_CANCEL = "cancel"

# "die dritte" ist genauso gueltig wie "drei"
_ORDINALS: dict[str, int] = {
    "eins": 1, "ein": 1, "erste": 1, "erster": 1, "erstes": 1, "1": 1,
    "zwei": 2, "zweite": 2, "zweiter": 2, "zweites": 2, "2": 2,
    "drei": 3, "dritte": 3, "dritter": 3, "drittes": 3, "3": 3,
    "vier": 4, "vierte": 4, "vierter": 4, "viertes": 4, "4": 4,
    "fuenf": 5, "funf": 5, "fuenfte": 5, "funfte": 5, "fuenfter": 5, "5": 5,
}
_CHOICE_LEAD = frozenset({"nummer", "die", "der", "das", "den", "nimm", "waehle", "wahle"})
# Bestaetigung einer Rueckfrage mit genau einem Vorschlag
_CONFIRM_WORDS = frozenset({"ja", "genau", "richtig", "jap", "jo", "klar", "bestaetigen"})
_CANCEL_WORDS = frozenset({
    "abbrechen", "abbruch", "stopp", "stop", "nein", "keins", "keines",
    "vergiss", "egal", "nichts", "zurueck", "zuruck",
})


class ChoiceCommand(Command):
    id = INTENT_CHOICE
    description = "Beantwortet eine Rueckfrage bei mehreren Treffern"
    examples = ("Zwei", "Die dritte", "Nummer eins")

    def match(self, text: str, context: CommandContext) -> Intent | None:
        candidates = context.pending_candidates
        if not candidates:
            return None

        tokens = trim_filler(prepare(text))
        if not tokens:
            return None

        # Ein vollstaendiger neuer Befehl ("starte discord") ist keine Antwort
        # auf die Rueckfrage - er muss den Vorrang behalten.
        if tokens[0] in OPEN_VERBS_PREFIX or tokens[-1] in OPEN_VERBS_SUFFIX:
            return None

        if len(tokens) <= 2 and tokens[0] in _CONFIRM_WORDS:
            return Intent(INTENT_CHOICE, text, {"position": "1"})

        stripped = [token for token in tokens if token not in _CHOICE_LEAD]
        if not stripped:
            return None

        # Zahl- oder Ordnungsantwort ("zwei", "die dritte")
        if len(stripped) <= 2:
            for token in stripped:
                position = _ORDINALS.get(token)
                if position is not None:
                    return Intent(INTENT_CHOICE, text, {"position": str(position)})

        # Sonst nur dann, wenn der Text wirklich zu einem der Vorschlaege passt.
        spoken = " ".join(stripped)
        if find_matches(
            spoken,
            [candidate.app for candidate in candidates],
            threshold=context.settings.match_threshold,
            limit=1,
        ):
            return Intent(INTENT_CHOICE, text, {"name": spoken})
        return None

    def execute(self, intent: Intent, context: CommandContext) -> CommandResult:
        candidates = context.pending_candidates
        if not candidates:
            return CommandResult.failure("Es steht gerade keine Auswahl offen.", intent)

        position = intent.slot("position")
        if position:
            index = int(position) - 1
            if not 0 <= index < len(candidates):
                return CommandResult(
                    ok=False,
                    message=f"Es gibt nur {len(candidates)} Vorschläge.",
                    intent=intent,
                    candidates=candidates,
                    needs_choice=True,
                )
            return launch_match(candidates[index].app, context, intent)

        spoken = intent.slot("name")
        narrowed = find_matches(
            spoken,
            [candidate.app for candidate in candidates],
            threshold=context.settings.match_threshold,
            limit=len(candidates),
        )
        # Innerhalb der Vorschlagsliste genuegt ein klarer Vorsprung - der
        # Nutzer hat den Namen ja gerade praezisiert.
        if narrowed and is_confident(narrowed):
            return launch_match(narrowed[0].app, context, intent)

        return CommandResult(
            ok=True,
            message="Das war noch nicht eindeutig – welche Nummer?",
            intent=intent,
            candidates=narrowed or candidates,
            needs_choice=True,
        )


class CancelCommand(Command):
    id = INTENT_CANCEL
    description = "Bricht eine Rueckfrage ab"
    examples = ("Abbrechen", "Nein", "Egal")

    def match(self, text: str, context: CommandContext) -> Intent | None:
        tokens = trim_filler(prepare(text))
        if tokens and len(tokens) <= 2 and tokens[0] in _CANCEL_WORDS:
            return Intent(INTENT_CANCEL, text)
        return None

    def execute(self, intent: Intent, context: CommandContext) -> CommandResult:
        context.pending_candidates.clear()
        return CommandResult.success("Alles klar, abgebrochen.", intent=intent)
