"""Gemeinsame Schnittstelle aller Index-Quellen."""

from __future__ import annotations

from typing import Iterable, Protocol, runtime_checkable

from ..models import DiscoveredApp


@runtime_checkable
class AppSource(Protocol):
    """Eine Fundstelle fuer startbare Programme.

    ``priority`` steuert, welcher Eintrag bei Dubletten gewinnt und geht als
    kleiner Bonus in die Namenssuche ein. Richtwerte:

    ===  ==========================================================
    45   Startmenue laut Windows selbst (inkl. Store-Apps)
    40   Verknuepfungen im Startmenue
    30   Registry "App Paths"
    20   Registry "Installierte Programme"
    10   ausfuehrbare Dateien im PATH
    ===  ==========================================================
    """

    id: str
    display_name: str
    priority: int

    def is_available(self) -> bool:
        """Laeuft diese Quelle auf dem aktuellen System ueberhaupt?"""

    def discover(self) -> Iterable[DiscoveredApp]:
        """Liefert gefundene Programme. Fehler einzelner Eintraege werden
        innerhalb der Quelle abgefangen - ein defekter Eintrag darf nie den
        gesamten Scan abbrechen."""


# Namen, die zwar im Startmenue stehen, aber keine Programme sind, die man
# per Sprache oeffnen moechte.
IGNORED_NAME_PARTS = (
    "uninstall", "deinstall", "entfernen", "readme", "liesmich", "lizenz",
    "license", "help", "hilfe", "handbuch", "manual", "dokumentation",
    "documentation", "website", "homepage", "support", "update", "repair",
    "reparieren", "modify", "aendern", "changelog", "release notes",
    "eula", "faq", "crash", "report", "debug", "safe mode", "abgesicherter",
)


def looks_like_noise(name: str) -> bool:
    """True, wenn der Eintrag eher Beiwerk als Programm ist."""
    lowered = name.casefold()
    return any(part in lowered for part in IGNORED_NAME_PARTS)
