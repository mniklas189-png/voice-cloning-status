"""Die Mustersprache der Absichtserkennung.

Ein Muster ist eine Wortfolge mit vier Sonderformen:

===============  =========================================================
``(a|b|c)``      eine der Alternativen; mehrwortig moeglich: ``(task manager|taskmanager)``
``[wort]``       darf fehlen
``*``            beliebig viele Woerter (auch keine)
``{name}``       Parameter; wie er gelesen wird, steht in :mod:`.slots`
===============  =========================================================

Verglichen wird auf Wortebene, nicht mit einem grossen regulaeren Ausdruck:
So laesst sich sagen, *wieviel* eines Satzes woertlich getroffen wurde -
und daran entscheidet sich, welche Absicht bei mehreren Treffern gewinnt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Sequence

# Ein Parameter-Leser bekommt die restlichen Woerter und bietet alle
# Lesarten an, die er fuer moeglich haelt: Paare aus verbrauchten Woertern
# und Wert, beste zuerst. Eine leere Liste heisst: passt nicht.
SlotReader = Callable[[Sequence[str]], "list[tuple[int, str]]"]

_TOKEN_RE = re.compile(r"\([^)]*\)|\[[^\]]*\]|\{[^}]*\}|\*|\S+")


@dataclass(slots=True)
class _Literal:
    """Eine oder mehrere Wortfolgen, von denen eine passen muss."""

    alternatives: tuple[tuple[str, ...], ...]


@dataclass(slots=True)
class _Optional:
    tokens: tuple[str, ...]


@dataclass(slots=True)
class _AnyWords:
    """``*`` - beliebig viele Woerter, moeglichst wenige."""

    max_words: int = 4


@dataclass(slots=True)
class _Slot:
    name: str
    kind: str


Element = _Literal | _Optional | _AnyWords | _Slot


@dataclass(slots=True)
class Pattern:
    """Ein uebersetztes Muster."""

    source: str
    elements: tuple[Element, ...]
    literal_words: int = 0
    slot_kinds: dict[str, str] = field(default_factory=dict)

    def match(self, tokens: Sequence[str], readers: dict[str, SlotReader]) -> dict[str, str] | None:
        """Passt das Muster auf die Wortliste? Liefert die Parameter."""
        result: dict[str, str] = {}
        if _walk(self.elements, 0, tokens, 0, readers, result):
            return result
        return None


def compile_pattern(source: str) -> Pattern:
    """Liest ein Muster ein."""
    elements: list[Element] = []
    literal_words = 0
    slot_kinds: dict[str, str] = {}

    for raw in _TOKEN_RE.findall(source.strip()):
        if raw == "*":
            elements.append(_AnyWords())
        elif raw.startswith("(") :
            alternatives = tuple(
                tuple(option.split()) for option in raw[1:-1].split("|") if option.strip()
            )
            if not alternatives:
                continue
            elements.append(_Literal(alternatives))
            literal_words += min(len(option) for option in alternatives)
        elif raw.startswith("["):
            tokens = tuple(raw[1:-1].split())
            if tokens:
                elements.append(_Optional(tokens))
        elif raw.startswith("{"):
            body = raw[1:-1]
            name, _, kind = body.partition(":")
            name = name.strip()
            kind = (kind or name).strip()
            elements.append(_Slot(name=name, kind=kind))
            slot_kinds[name] = kind
        else:
            elements.append(_Literal(((raw,),)))
            literal_words += 1

    return Pattern(
        source=source,
        elements=tuple(elements),
        literal_words=literal_words,
        slot_kinds=slot_kinds,
    )


def _walk(
    elements: Sequence[Element],
    index: int,
    tokens: Sequence[str],
    position: int,
    readers: dict[str, SlotReader],
    result: dict[str, str],
) -> bool:
    """Rekursiver Vergleich mit Ruecksetzen.

    Die Muster sind kurz (unter zehn Elementen), deshalb genuegt einfaches
    Backtracking - das bleibt lesbar und ist schnell genug.
    """
    if index == len(elements):
        return position == len(tokens)

    element = elements[index]

    if isinstance(element, _Literal):
        for option in element.alternatives:
            end = position + len(option)
            if tuple(tokens[position:end]) == option:
                if _walk(elements, index + 1, tokens, end, readers, result):
                    return True
        return False

    if isinstance(element, _Optional):
        end = position + len(element.tokens)
        if tuple(tokens[position:end]) == element.tokens:
            if _walk(elements, index + 1, tokens, end, readers, result):
                return True
        return _walk(elements, index + 1, tokens, position, readers, result)

    if isinstance(element, _AnyWords):
        limit = min(len(tokens), position + element.max_words)
        for end in range(position, limit + 1):
            if _walk(elements, index + 1, tokens, end, readers, result):
                return True
        return False

    # _Slot: jede angebotene Lesart durchprobieren
    reader = readers.get(element.kind)
    if reader is None:
        return False
    saved = result.get(element.name)
    for length, value in reader(tokens[position:]):
        if length <= 0 or position + length > len(tokens):
            continue
        result[element.name] = value
        if _walk(elements, index + 1, tokens, position + length, readers, result):
            return True
    if saved is None:
        result.pop(element.name, None)
    else:
        result[element.name] = saved
    return False
