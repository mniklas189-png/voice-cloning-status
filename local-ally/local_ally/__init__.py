"""Local Ally - ein lokaler Sprachassistent fuer Windows.

Das Paket ist bewusst in klar getrennte Teilbereiche aufgeteilt:

* :mod:`local_ally.core`      - Zustand, Ereignisse, Controller (Anwendungslogik)
* :mod:`local_ally.settings`  - Nutzereinstellungen (JSON, lokal)
* :mod:`local_ally.database`  - SQLite-Verbindung und Schema
* :mod:`local_ally.app_index` - Erkennung, Speicherung und Suche installierter Programme
* :mod:`local_ally.speech`    - Mikrofon-Aufnahme und lokale Spracherkennung
* :mod:`local_ally.commands`  - Sprachbefehle (Text -> Absicht -> Aktion)
* :mod:`local_ally.ui`        - Slint-Oberflaeche und Bruecke zur Anwendungslogik

Kein Modul ausserhalb von :mod:`local_ally.ui` kennt Slint, und kein Modul
ausserhalb von :mod:`local_ally.speech` kennt Vosk oder faster-whisper.
Dadurch bleiben UI und Erkennungs-Backends austauschbar.
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
