"""Unscharfe Suche nach gesprochenen Programmnamen.

Warum eigener Code statt einer Fuzzy-Bibliothek: der Abgleich muss genau die
Fehler verzeihen, die eine *deutsche* Spracherkennung macht. Reine
Zeichenaehnlichkeit (Levenshtein) reicht dafuer nicht - "klient" und "client"
liegen zeichenweise auseinander, klingen aber identisch.

Deshalb kombiniert der Vergleich mehrere Signale:

1. exakte Uebereinstimmung der normalisierten Form
2. Wortweise Teilmengen ("discord" in "Discord Inc.")
3. Zeichenaehnlichkeit (``difflib``, Standardbibliothek)
4. phonetische Uebereinstimmung (Koelner Phonetik, siehe ``core.text``)

Zusaetzlich fliessen Quellenprioritaet und bisherige Nutzungshaeufigkeit als
kleiner Bonus ein - bei zwei gleich guten Namenstreffern gewinnt das
Programm, das der Nutzer tatsaechlich startet.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable, Sequence

from ..core import text
from .models import AppEntry, MatchResult

# Ab diesem Abstand zum Zweitplatzierten gilt ein Treffer als eindeutig.
DEFAULT_MARGIN = 0.06

# Unterhalb dieser Aehnlichkeit ist ein rein phonetischer Treffer wertlos.
_PHONETIC_MIN_RATIO = 0.86

# Schutz vor Zufallstreffern bei sehr kurzen Namen
_MIN_PREFIX_CHARS = 3
_MIN_PREFIX_COVERAGE = 0.4
_MIN_PHONETIC_CHARS = 4
_MIN_PHONETIC_CODE = 3


@dataclass(slots=True)
class _Query:
    """Vorberechnete Formen des gesuchten Begriffs."""

    raw: str
    normalized: str
    compact: str
    tokens: tuple[str, ...]
    phonetic: str

    @classmethod
    def build(cls, spoken: str) -> "_Query":
        normalized = " ".join(text.significant_tokens(spoken))
        return cls(
            raw=spoken,
            normalized=normalized,
            compact=normalized.replace(" ", ""),
            tokens=tuple(normalized.split()),
            phonetic=text.phonetic_key(normalized),
        )


def _ratio(a: str, b: str) -> float:
    """Zeichenaehnlichkeit mit gueniger Vorabpruefung."""
    if not a or not b:
        return 0.0
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if len(shorter) / len(longer) < 0.45:
        return 0.0  # zu unterschiedlich lang, difflib kann hier nicht helfen
    matcher = SequenceMatcher(None, a, b)
    if matcher.real_quick_ratio() < 0.5:
        return 0.0
    return matcher.ratio()


def score_alias(query: _Query, alias: str) -> tuple[float, str]:
    """Bewertet einen einzelnen Namen gegen die Anfrage (0.0 - 1.0)."""
    alias_norm = " ".join(text.significant_tokens(alias))
    if not alias_norm or not query.normalized:
        return 0.0, ""

    alias_compact = alias_norm.replace(" ", "")
    alias_tokens = tuple(alias_norm.split())

    if alias_norm == query.normalized:
        return 1.0, "exakt"
    if alias_compact == query.compact:
        return 0.97, "exakt (ohne Leerzeichen)"

    best, reason = 0.0, ""

    # Alle gesprochenen Woerter kommen im Namen vor ("discord" -> "Discord Inc")
    if query.tokens and set(query.tokens) <= set(alias_tokens):
        coverage = len(query.compact) / max(len(alias_compact), 1)
        best, reason = 0.80 + 0.15 * coverage, "Wortteilmenge"

    # Namensanfang ("photoshop" -> "Photoshop Elements")
    if alias_compact.startswith(query.compact) or query.compact.startswith(alias_compact):
        shorter = min(len(query.compact), len(alias_compact))
        coverage = shorter / max(len(query.compact), len(alias_compact), 1)
        # Ohne Mindestlaenge und Mindestabdeckung wuerde ein einzelner
        # Buchstabe zu jedem beliebigen Namen passen.
        if shorter >= _MIN_PREFIX_CHARS and coverage >= _MIN_PREFIX_COVERAGE:
            candidate = 0.72 + 0.25 * coverage
            if candidate > best:
                best, reason = candidate, "Namensanfang"

    # Zeichenaehnlichkeit
    char_score = max(_ratio(query.compact, alias_compact), _ratio(query.normalized, alias_norm))
    if char_score > best:
        best, reason = char_score, "Schreibweise ähnlich"

    # Phonetik - fuer Verhoerer wie "klient"/"client"
    alias_phon = text.phonetic_key(alias_norm)
    if alias_phon and query.phonetic:
        # Kurze Woerter teilen sich schnell einen Klangcode ("bash"/"bc"),
        # deshalb zaehlt Gleichklang erst ab einer gewissen Laenge.
        long_enough = (
            min(len(query.compact), len(alias_compact)) >= _MIN_PHONETIC_CHARS
            and len(query.phonetic.replace(" ", "")) >= _MIN_PHONETIC_CODE
        )
        if alias_phon == query.phonetic and long_enough:
            if 0.95 > best:
                best, reason = 0.95, "gleicher Klang"
        elif alias_phon == query.phonetic:
            pass  # zu kurz - Zeichenaehnlichkeit oben entscheidet
        else:
            # Phonetische Codes bestehen nur aus Ziffern - zwei voellig
            # verschiedene Woerter erreichen dabei schnell 60% Aehnlichkeit.
            # Nur sehr hohe Werte zaehlen, und dann gedaempft.
            raw = _ratio(query.phonetic.replace(" ", ""), alias_phon.replace(" ", ""))
            if raw >= _PHONETIC_MIN_RATIO:
                phon_score = 0.62 + (raw - _PHONETIC_MIN_RATIO) / (
                    1.0 - _PHONETIC_MIN_RATIO
                ) * 0.28
                if phon_score > best:
                    best, reason = phon_score, "ähnlicher Klang"

    return min(best, 1.0), reason


def score_app(query: _Query, app: AppEntry) -> MatchResult | None:
    """Bester Namenstreffer eines Programms, inklusive kleiner Boni."""
    best_score, best_alias, best_reason = 0.0, "", ""
    for alias, weight in app.weighted_names():
        score, reason = score_alias(query, alias)
        score *= weight
        if score > best_score:
            best_score, best_alias, best_reason = score, alias, reason

    if best_score <= 0.0:
        return None

    # Boni bewusst klein: sie entscheiden nur bei nahezu gleichwertigen Namen.
    # Bewusst *nicht* auf 1.0 gedeckelt - sonst waeren ein exakter Treffer und
    # ein guter Teiltreffer nach dem Bonus gleichauf, und Local Ally wuerde
    # unnoetig nachfragen. Die UI zeigt den Wert ohnehin gerundet an.
    bonus = min(app.priority, 40) * 0.0015          # Quelle (max. +0.06)
    bonus += min(app.launch_count, 20) * 0.002      # Nutzung (max. +0.04)
    return MatchResult(
        app=app,
        score=best_score + bonus,
        matched_alias=best_alias,
        reason=best_reason,
    )


def find_matches(
    spoken: str,
    apps: Iterable[AppEntry],
    *,
    threshold: float = 0.68,
    limit: int = 5,
) -> list[MatchResult]:
    """Alle Programme oberhalb der Schwelle, bestes Ergebnis zuerst."""
    query = _Query.build(spoken)
    if not query.normalized:
        return []

    results = [match for match in (score_app(query, app) for app in apps) if match]
    results = [match for match in results if match.score >= threshold]
    results.sort(key=lambda m: (-m.score, len(m.app.name), m.app.name.lower()))
    return results[:limit]


def is_confident(results: Sequence[MatchResult], margin: float = DEFAULT_MARGIN) -> bool:
    """Eindeutig, wenn es genau einen Treffer gibt oder der beste klar fuehrt.

    Local Ally startet lieber nichts, als das falsche Programm zu starten -
    bei Gleichstand fragt es nach.
    """
    if not results:
        return False
    if len(results) == 1:
        return True
    return (results[0].score - results[1].score) >= margin
