"""Lokaler Index startbarer Programme.

Aufbau:

* :mod:`.sources`    - plattformabhaengige Sammler (Startmenue, Registry, PATH, ...)
* :mod:`.indexer`    - fuehrt alle Quellen zusammen und schreibt in die Datenbank
* :mod:`.repository` - Lese-/Schreibzugriff auf die SQLite-Tabellen
* :mod:`.matching`   - unscharfe Suche nach gesprochenen Namen
* :mod:`.launcher`   - startet ein gefundenes Programm
"""

from .models import AppEntry, DiscoveredApp, MatchResult

__all__ = ["AppEntry", "DiscoveredApp", "MatchResult"]
