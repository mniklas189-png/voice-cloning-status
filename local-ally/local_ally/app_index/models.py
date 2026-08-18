"""Datenmodelle des App-Index."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core import text

# Gewicht abgeleiteter Kurzformen gegenueber echten Namen
WEAK_ALIAS_WEIGHT = 0.88


@dataclass(slots=True)
class DiscoveredApp:
    """Rohtreffer einer Quelle - noch nicht in der Datenbank.

    ``launch_kind`` beschreibt, *wie* gestartet wird:

    ``path``    - ausfuehrbare Datei oder Verknuepfung (.exe/.lnk/.bat)
    ``shell``   - ueber die Windows-Shell, z.B. ``shell:AppsFolder\\...`` (Store-Apps)
    ``uri``     - Protokoll-Handler wie ``spotify:``
    ``command`` - fertige Kommandozeile
    """

    name: str
    launch_target: str
    source: str
    launch_kind: str = "path"
    arguments: str = ""
    working_dir: str = ""
    icon_path: str = ""
    priority: int = 0
    aliases: list[str] = field(default_factory=list)

    def dedupe_key(self) -> tuple[str, str, str]:
        return (self.launch_target.lower(), self.arguments.lower(), self.source)


@dataclass(slots=True)
class AppEntry:
    """Ein Programm, wie es in der Datenbank steht."""

    id: int
    name: str
    launch_target: str
    launch_kind: str = "path"
    arguments: str = ""
    working_dir: str = ""
    icon_path: str = ""
    source: str = ""
    priority: int = 0
    launch_count: int = 0
    aliases: list[str] = field(default_factory=list)
    # Abgeleitete Kurzformen (Akronyme). Sie sind praktisch ("vsc" fuer
    # Visual Studio Code), kollidieren aber leicht - "gi-inspect-typelib"
    # ergaebe sonst ein perfektes "git". Deshalb zaehlen sie schwaecher.
    weak_aliases: list[str] = field(default_factory=list)

    @property
    def normalized_name(self) -> str:
        return text.normalize(self.name)

    def all_names(self) -> list[str]:
        """Anzeigename plus alle Aliase, ohne Dubletten."""
        return [name for name, _weight in self.weighted_names()]

    def weighted_names(self) -> list[tuple[str, float]]:
        """Alle Namen mit ihrem Gewicht fuer die Suche."""
        seen: set[str] = set()
        names: list[tuple[str, float]] = []
        for candidate, weight in (
            [(self.name, 1.0)]
            + [(alias, 1.0) for alias in self.aliases]
            + [(alias, WEAK_ALIAS_WEIGHT) for alias in self.weak_aliases]
        ):
            key = text.normalize(candidate)
            if key and key not in seen:
                seen.add(key)
                names.append((candidate, weight))
        return names


@dataclass(slots=True)
class MatchResult:
    """Ein Treffer der unscharfen Suche."""

    app: AppEntry
    score: float
    matched_alias: str
    reason: str = ""

    def __repr__(self) -> str:  # kompakte Ausgabe in Logs und Tests
        return f"<Match {self.app.name!r} {self.score:.2f} via {self.matched_alias!r}>"
