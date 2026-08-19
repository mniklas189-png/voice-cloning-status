"""Die beste passende Absicht zu einem Satz bestimmen."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

from ..commands.phrases import prepare, strip_polite_prefix
from .catalog import all_specs
from .model import IntentMatch, IntentSpec
from .pattern import compile_pattern
from .slots import BOUNDED_KINDS, DEGREE_WORDS, SlotReader, default_readers

log = logging.getLogger(__name__)

# Woerter ohne eigene Bedeutung. Sie werden vor dem Vergleich entfernt -
# dadurch braucht kein Muster Varianten wie "mach mir mal bitte das ...".
FILLER = frozenset({
    "bitte", "mal", "jetzt", "doch", "eben", "schnell", "endlich", "einfach",
    "mir", "mich", "uns", "dir", "danke",
    "hey", "hallo", "ally", "local", "localally",
    "das", "die", "der", "den", "dem", "des",
    "ein", "eine", "einen", "einem", "einer",
    "mein", "meine", "meinen", "meinem", "meiner", "meins",
    "wieder", "nochmal", "gerade", "grad",
})


@dataclass(slots=True)
class Normalized:
    """Ein Satz in Vergleichsform."""

    tokens: tuple[str, ...]
    degree: str = ""          # "small" | "large" - aus Woertern wie "etwas"
    original: str = ""


class IntentMatcher:
    """Vergleicht einen Satz mit allen Absichten des Katalogs."""

    def __init__(
        self,
        specs: Iterable[IntentSpec] | None = None,
        readers: dict[str, SlotReader] | None = None,
    ) -> None:
        self.readers = readers or default_readers()
        self.specs: list[IntentSpec] = []
        for spec in specs if specs is not None else all_specs():
            self.register(spec)

    def register(self, spec: IntentSpec) -> IntentSpec:
        """Eine Absicht aufnehmen - dabei werden ihre Muster uebersetzt."""
        spec.compiled = [compile_pattern(template) for template in spec.templates]
        for pattern in spec.compiled:
            unknown = set(pattern.slot_kinds.values()) - set(self.readers)
            if unknown:
                raise ValueError(
                    f"Absicht {spec.id}: unbekannte Parameterart {sorted(unknown)}"
                )
        self.specs.append(spec)
        return spec

    # --- Vergleich -----------------------------------------------------
    def normalize(self, text: str) -> Normalized:
        tokens = strip_polite_prefix(prepare(text))
        degree = ""
        kept: list[str] = []
        for token in tokens:
            if token in DEGREE_WORDS:
                degree = degree or DEGREE_WORDS[token]
                continue
            if token in FILLER:
                continue
            kept.append(token)
        return Normalized(tokens=tuple(kept), degree=degree, original=text)

    def matches(self, text: str) -> list[IntentMatch]:
        """Alle passenden Absichten, beste zuerst."""
        normalized = self.normalize(text)
        if not normalized.tokens:
            return []

        found: list[IntentMatch] = []
        for spec in self.specs:
            best = self._match_spec(spec, normalized)
            if best is not None:
                found.append(best)

        found.sort(key=lambda match: -match.score)
        return found

    def match(self, text: str) -> IntentMatch | None:
        """Die beste Absicht - oder ``None``, wenn keine passt."""
        found = self.matches(text)
        return found[0] if found else None

    def _match_spec(self, spec: IntentSpec, normalized: Normalized) -> IntentMatch | None:
        best: IntentMatch | None = None
        for pattern in spec.compiled:
            slots = pattern.match(normalized.tokens, self.readers)
            if slots is None:
                continue
            bounded = sum(
                1 for kind in pattern.slot_kinds.values() if kind in BOUNDED_KINDS
            )
            # Je mehr woertlich getroffen wurde, desto sicherer die Absicht.
            # Selbstpruefende Parameter (Zahl, Ordner) zaehlen mit, freie
            # Parameter wie Programmnamen nicht - die passen immer.
            score = pattern.literal_words + 0.5 * bounded + spec.priority
            if normalized.degree:
                slots = {**slots, "degree": normalized.degree}
            if best is None or score > best.score:
                best = IntentMatch(
                    spec=spec, slots=slots, score=score, text=normalized.original
                )
        return best

    def describe(self) -> list[tuple[str, str]]:
        """Alle Absichten mit Beschreibung - fuer Hilfe und Dokumentation."""
        return [(spec.id, spec.description) for spec in self.specs]


_default: IntentMatcher | None = None


def default_matcher() -> IntentMatcher:
    """Gemeinsamer Vergleicher. Die Muster werden nur einmal uebersetzt."""
    global _default
    if _default is None:
        _default = IntentMatcher()
    return _default
