"""Parameter aus dem Satz gewinnen.

Jeder Leser bekommt die restlichen Woerter eines Satzes und meldet, wieviele
davon er verbraucht und welchen Wert er daraus liest. Damit koennen Muster
Angaben wie "auf 60 Prozent", "vierzig", "meine Downloads" oder einen
Programmnamen aufnehmen, ohne dass dafuer eigene Regeln noetig waeren.
"""

from __future__ import annotations

from typing import Callable, Sequence

# Zahlwoerter. Der Text ist zu diesem Zeitpunkt bereits ohne Umlaute
# ("fuenfzig", "dreissig") - siehe local_ally.core.text.
_UNITS = {
    "null": 0, "ein": 1, "eins": 1, "eine": 1, "zwei": 2, "drei": 3, "vier": 4,
    "fuenf": 5, "sechs": 6, "sieben": 7, "acht": 8, "neun": 9,
}
_TEENS = {
    "zehn": 10, "elf": 11, "zwoelf": 12, "dreizehn": 13, "vierzehn": 14,
    "fuenfzehn": 15, "sechzehn": 16, "siebzehn": 17, "achtzehn": 18, "neunzehn": 19,
}
_TENS = {
    "zwanzig": 20, "dreissig": 30, "vierzig": 40, "fuenfzig": 50,
    "sechzig": 60, "siebzig": 70, "achtzig": 80, "neunzig": 90,
}
_HUNDRED = {"hundert": 100, "einhundert": 100}

# Bekannte Ordner. Der Wert ist der Schluessel, den die Aktion aufloest.
FOLDER_ALIASES: dict[tuple[str, ...], str] = {
    ("downloads",): "downloads",
    ("download", "ordner"): "downloads",
    ("dokumente",): "documents",
    ("dokumenten", "ordner"): "documents",
    ("desktop",): "desktop",
    ("schreibtisch",): "desktop",
    ("bilder",): "pictures",
    ("fotos",): "pictures",
    ("musik",): "music",
    ("videos",): "videos",
    ("papierkorb",): "recycle_bin",
    ("benutzerordner",): "home",
    ("home", "ordner"): "home",
    ("persoenlicher", "ordner"): "home",
}

# Steigerungswoerter: sie veraendern die Schrittweite, nicht die Absicht.
DEGREE_WORDS = {
    "etwas": "small", "bisschen": "small", "leicht": "small", "kurz": "small",
    "deutlich": "large", "viel": "large", "ordentlich": "large",
    "richtig": "large", "stark": "large", "ganz": "large",
}


def parse_number(tokens: Sequence[str]) -> tuple[int, int] | None:
    """Liest eine Zahl. Rueckgabe ``(verbrauchte Woerter, Wert)``."""
    if not tokens:
        return None
    first = tokens[0]

    if first.isdigit():
        return 1, int(first)

    value = _word_to_number(first)
    if value is not None:
        return 1, value

    # ueber die Wortgrenze verteilt: "ein hundert"
    if len(tokens) >= 2:
        combined = _word_to_number(tokens[0] + tokens[1])
        if combined is not None:
            return 2, combined
    return None


def _word_to_number(word: str) -> int | None:
    for table in (_HUNDRED, _TENS, _TEENS, _UNITS):
        if word in table:
            return table[word]

    # Zusammengesetzt: "fuenfundvierzig"
    if "und" in word:
        unit, _, tens = word.partition("und")
        if unit in _UNITS and tens in _TENS:
            return _TENS[tens] + _UNITS[unit]
    return None


def read_level(tokens: Sequence[str]) -> list[tuple[int, str]]:
    """Prozent- oder Zahlenangabe: ``auf 60 prozent`` -> ``"60"``."""
    parsed = parse_number(tokens)
    if parsed is None:
        return []
    used, value = parsed
    if not 0 <= value <= 100:
        return []
    if len(tokens) > used and tokens[used] in {"prozent", "%"}:
        # Mit und ohne "prozent" anbieten - welche Variante passt, entscheidet
        # das Muster selbst.
        return [(used + 1, str(value)), (used, str(value))]
    return [(used, str(value))]


def read_folder(tokens: Sequence[str]) -> list[tuple[int, str]]:
    """Bekannter Ordnername."""
    found = []
    for length in (2, 1):
        if length > len(tokens):
            continue
        window = tuple(tokens[:length])
        if window in FOLDER_ALIASES:
            found.append((length, FOLDER_ALIASES[window]))
    return found


def read_rest(tokens: Sequence[str]) -> list[tuple[int, str]]:
    """Freier Text - Programmname, Suchbegriff, Geraetename.

    Angeboten wird zuerst der ganze Rest, dann immer kuerzere Stuecke. So
    passt auch ein Muster, in dem nach dem Parameter noch Woerter stehen:
    "check ob {app} laeuft".
    """
    return [
        (length, " ".join(tokens[:length]))
        for length in range(len(tokens), 0, -1)
    ]


# Gattungswoerter vor einem Programmnamen: "starte das Programm Steam".
APP_PREFIXES = frozenset({"programm", "programme", "anwendung", "app", "software", "spiel", "game"})


def read_app(tokens: Sequence[str]) -> list[tuple[int, str]]:
    """Programmname - ohne vorangestellte Gattungswoerter.

    Verbraucht werden trotzdem alle Woerter; nur der *Wert* wird bereinigt,
    damit der Abgleich mit dem Programm-Index sauber bleibt.
    """
    options = []
    for length, value in read_rest(tokens):
        words = value.split()
        while len(words) > 1 and words[0] in APP_PREFIXES:
            words.pop(0)
        if words:
            options.append((length, " ".join(words)))
    return options


def read_word(tokens: Sequence[str]) -> list[tuple[int, str]]:
    """Genau ein Wort."""
    return [(1, tokens[0])] if tokens else []


# Ein Leser bietet alle Lesarten an, die er fuer moeglich haelt - als Paare
# aus verbrauchten Woertern und Wert. Das Muster probiert sie der Reihe nach.
SlotReader = Callable[[Sequence[str]], "list[tuple[int, str]]"]


def default_readers() -> dict[str, SlotReader]:
    """Alle Parameter-Arten, die Muster verwenden duerfen."""
    return {
        "level": read_level,
        "folder": read_folder,
        "rest": read_rest,
        "app": read_app,
        "query": read_rest,
        "device": read_rest,
        "word": read_word,
    }


# Parameter, die selbst pruefen, ob sie passen - sie machen ein Muster
# treffsicherer und zaehlen deshalb bei der Bewertung mit.
BOUNDED_KINDS = frozenset({"level", "folder", "word"})
