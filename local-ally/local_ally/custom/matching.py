"""Gesprochenes einer eigenen Funktion zuordnen.

Verglichen wird derselbe Weg wie bei Programmnamen - so verzeiht auch eine
selbst angelegte Funktion Verhoerer ("lernen" / "lehrnen"). Die Schwelle
liegt allerdings deutlich hoeher: eine eigene Funktion geht den eingebauten
Befehlen vor, deshalb darf sie nicht bei entfernter Aehnlichkeit ausloesen.
"""

from __future__ import annotations

from ..app_index.matching import similarity
from ..commands.phrases import prepare, strip_polite_prefix
from .models import CustomCommand

MIN_SCORE = 0.85


def find_command(
    spoken: str, commands: list[CustomCommand], threshold: float = MIN_SCORE
) -> tuple[CustomCommand, float] | None:
    """Beste passende eigene Funktion - oder ``None``."""
    text = " ".join(strip_polite_prefix(prepare(spoken)))
    if not text:
        return None

    best: tuple[CustomCommand, float] | None = None
    for command in commands:
        if not command.enabled:
            continue
        score = similarity(text, command.phrase)
        if score >= threshold and (best is None or score > best[1]):
            best = (command, score)
    return best
