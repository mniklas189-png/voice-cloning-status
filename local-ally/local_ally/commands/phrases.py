"""Deutsche Satzbausteine fuer die Befehlserkennung.

Gesammelt an einer Stelle, damit neue Formulierungen ergaenzt werden koennen,
ohne die Befehle selbst anzufassen. Alle Eintraege stehen in der Form, die
:func:`local_ally.core.text.strip_accents` erzeugt ("oeffne" statt "öffne").
"""

from __future__ import annotations

import re

from ..core.text import strip_accents

# Verben am Satzanfang: "starte discord"
OPEN_VERBS_PREFIX = frozenset({
    "offne", "oeffne", "oeffnen", "offnen", "open",
    "starte", "start", "starten", "startest",
    "fuehre", "fuhre", "ausfuehren", "lade", "aktiviere",
    "zeig", "zeige", "mach", "mache", "ruf", "rufe", "hol", "hole",
})

# Verben am Satzende: "discord starten"
OPEN_VERBS_SUFFIX = frozenset({
    "offnen", "oeffnen", "starten", "aufmachen", "ausfuehren", "starte", "oeffne",
})

# Woerter, die am Rand eines Programmnamens stehen koennen, aber nicht dazugehoeren.
FILLER_WORDS = frozenset({
    "bitte", "mal", "jetzt", "doch", "mir", "mich", "uns", "danke",
    "hey", "hallo", "ally", "local", "localally",
    "das", "die", "der", "den", "dem", "des", "ein", "eine", "einen", "einem",
    "programm", "programme", "app", "anwendung", "software", "spiel", "game",
    "auf", "aus", "an", "los", "endlich", "kurz", "schnell",
})

# Einleitungen wie "kannst du bitte ..." - werden vorne abgeschnitten.
POLITE_PREFIXES = (
    "kannst du", "koenntest du", "konntest du", "kannste", "wuerdest du",
    "wurdest du", "wuerdest du bitte", "ich moechte", "ich mochte", "ich will",
    "ich haette gern", "ich hatte gern", "bitte", "hey ally", "ally",
)

_PUNCTUATION = re.compile(r"[^\w\s]+", re.UNICODE)


def prepare(text: str) -> list[str]:
    """Satz in vergleichbare Tokens zerlegen (klein, ohne Umlaute/Satzzeichen)."""
    cleaned = _PUNCTUATION.sub(" ", strip_accents(text).lower())
    return cleaned.split()


def strip_polite_prefix(tokens: list[str]) -> list[str]:
    """Hoefliche Einleitung entfernen ("kannst du bitte" -> "")."""
    joined = " ".join(tokens)
    changed = True
    while changed:
        changed = False
        for prefix in POLITE_PREFIXES:
            if joined == prefix:
                return []
            if joined.startswith(prefix + " "):
                joined = joined[len(prefix) + 1 :]
                changed = True
    return joined.split()


def trim_filler(tokens: list[str]) -> list[str]:
    """Fuellwoerter an beiden Raendern entfernen."""
    start, end = 0, len(tokens)
    while start < end and tokens[start] in FILLER_WORDS:
        start += 1
    while end > start and tokens[end - 1] in FILLER_WORDS:
        end -= 1
    return tokens[start:end]
