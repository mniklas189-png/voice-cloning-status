"""Mehrere Befehle in einem Satz.

"Mach es leiser und öffne Spotify" sind zwei Absichten. Getrennt wird nur
dann, wenn **jeder** Teil fuer sich eine Absicht ergibt - sonst bliebe von
"Öffne Rot und Blau" ein Programmname auf der Strecke.
"""

from __future__ import annotations

import re

# Bindewoerter, an denen getrennt werden darf. Die laengsten zuerst, damit
# "und dann" nicht als "und" plus Rest zerfaellt.
_SPLIT = re.compile(
    r"\s+(?:und\s+dann|und\s+danach|und\s+ausserdem|und\s+auch|und|danach|dann|ausserdem|sowie)\s+",
    re.IGNORECASE,
)

MAX_PARTS = 3


def split_commands(text: str, matcher, max_parts: int = MAX_PARTS) -> list[str]:
    """Satz in einzelne Befehle zerlegen - oder unveraendert lassen."""
    if not text or not text.strip():
        return []

    parts = [part.strip() for part in _SPLIT.split(text) if part.strip()]
    if not 2 <= len(parts) <= max_parts:
        return [text]

    # Nur trennen, wenn wirklich jeder Teil ein Befehl ist.
    if all(matcher.match(part) is not None for part in parts):
        return parts
    return [text]
