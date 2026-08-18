"""Textnormalisierung fuer den Abgleich gesprochener Programmnamen.

Die Spracherkennung liefert Kleinschreibung, keine Sonderzeichen und
gelegentlich abweichende Schreibweisen ("lunar klient" statt "Lunar Client").
Hier landet alles, was Namen vergleichbar macht - bewusst ohne externe
Bibliothek, damit Local Ally offline lauffaehig bleibt.
"""

from __future__ import annotations

import re
import unicodedata

_UMLAUTS = {
    "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
    "Ä": "ae", "Ö": "oe", "Ü": "ue",
}

# Zusaetze, die in Programmnamen stehen, aber nie mitgesprochen werden.
_NOISE_TOKENS = {
    "64", "32", "bit", "x64", "x86", "x86_64", "win64", "win32",
    "edition", "version", "setup", "installer", "uninstall", "deinstallieren",
    "launcher", "beta", "alpha", "release", "stable", "portable",
    "the", "der", "die", "das", "app", "application", "programm", "program",
}

_VERSION_RE = re.compile(r"\bv?\d+(?:[._]\d+)+\b")
_BRACKETS_RE = re.compile(r"[\(\[\{].*?[\)\]\}]")
_NON_WORD_RE = re.compile(r"[^a-z0-9]+")
_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def strip_accents(value: str) -> str:
    """Umlaute ausschreiben, uebrige Akzente entfernen."""
    for src, dst in _UMLAUTS.items():
        value = value.replace(src, dst)
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize(value: str) -> str:
    """Kanonische Form eines Namens: klein, ohne Sonderzeichen, ein Leerzeichen."""
    if not value:
        return ""
    value = _CAMEL_RE.sub(" ", value)
    value = strip_accents(value).lower()
    value = _BRACKETS_RE.sub(" ", value)
    value = _VERSION_RE.sub(" ", value)
    value = _NON_WORD_RE.sub(" ", value)
    return " ".join(value.split())


def tokens(value: str) -> list[str]:
    return normalize(value).split()


def significant_tokens(value: str) -> list[str]:
    """Tokens ohne generische Fuellwoerter und ohne reine Zahlen.

    Reine Zahlen sind fast immer Jahres- oder Versionsangaben ("Photoshop
    2024") und werden beim Sprechen weggelassen. Faellt nie auf eine leere
    Liste zurueck - notfalls bleiben die Originaltokens stehen.
    """
    parts = tokens(value)
    filtered = [t for t in parts if t not in _NOISE_TOKENS and not t.isdigit()]
    return filtered or parts


def compact(value: str) -> str:
    """Normalisierte Form ohne Leerzeichen ("vs code" -> "vscode")."""
    return normalize(value).replace(" ", "")


# --- Koelner Phonetik ---------------------------------------------------------
# Der Soundex fuer die deutsche Sprache. Er faengt genau die Fehler ab, die eine
# deutsche Spracherkennung typischerweise macht: "klient"/"client", "fotoshop"/
# "photoshop", "ai tunes"/"iTunes". Fuer Local Ally ist das wertvoller als eine
# rein zeichenbasierte Aehnlichkeit und kostet keine zusaetzliche Abhaengigkeit.

_VOWELS = frozenset("aeiouy")
# Mengen statt Strings: "" in "csz" waere True und wuerde Buchstaben am
# Wortende faelschlich ueberspringen.
_C_SZ = frozenset("csz")
_C_START_HARD = frozenset("ahkloqrux")
_C_INNER_HARD = frozenset("ahkoqux")
_CKQ = frozenset("ckq")


def koelner_phonetik(value: str) -> str:
    """Phonetischer Code eines Wortes nach Postel (1969)."""
    word = _NON_WORD_RE.sub("", strip_accents(value).lower())
    if not word:
        return ""

    codes: list[str] = []
    for index, char in enumerate(word):
        prev = word[index - 1] if index > 0 else ""
        nxt = word[index + 1] if index + 1 < len(word) else ""

        if char in _VOWELS or char == "j":
            code = "0"
        elif char == "b" or (char == "p" and nxt != "h"):
            code = "1"
        elif char in "dt":
            code = "8" if nxt in _C_SZ else "2"
        elif char in "fvw" or (char == "p" and nxt == "h"):
            code = "3"
        elif char in "gkq":
            code = "4"
        elif char == "c":
            if index == 0:
                code = "4" if nxt in _C_START_HARD else "8"
            elif prev in "sz":
                code = "8"
            else:
                code = "4" if nxt in _C_INNER_HARD else "8"
        elif char == "x":
            code = "8" if prev in _CKQ else "48"
        elif char == "l":
            code = "5"
        elif char in "mn":
            code = "6"
        elif char == "r":
            code = "7"
        elif char in "sz":
            code = "8"
        else:  # h und alles Uebrige sind stumm
            continue
        codes.append(code)

    # Gleiche Codes direkt hintereinander werden zusammengefasst ...
    deduped: list[str] = []
    for code in "".join(codes):
        if not deduped or deduped[-1] != code:
            deduped.append(code)
    if not deduped:  # z.B. reine Zahlen oder nur stumme Buchstaben
        return ""
    # ... und Nullen (Vokale) ausser am Wortanfang entfernen.
    return deduped[0] + "".join(c for c in deduped[1:] if c != "0")


def phonetic_key(value: str) -> str:
    """Phonetischer Schluessel einer ganzen Bezeichnung."""
    return " ".join(koelner_phonetik(token) for token in significant_tokens(value)).strip()
