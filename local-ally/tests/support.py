"""Gemeinsame Hilfen fuer die Tests.

Alle Tests laufen mit einem eigenen Datenverzeichnis, damit sie niemals die
echte Konfiguration oder Datenbank des Nutzers anfassen. Die Tests kommen
ohne externe Pakete aus (nur ``unittest`` aus der Standardbibliothek), damit
sie auch ohne installierte Spracherkennung durchlaufen.
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Erwartete Fehlerpfade werden in den Tests bewusst ausgeloest - ihre
# Protokollausgabe wuerde das Testergebnis nur unleserlich machen.
logging.getLogger("local_ally").setLevel(logging.CRITICAL)


class TempDataDirTestCase(unittest.TestCase):
    """Basisklasse mit eigenem, wegwerfbarem Datenverzeichnis."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._previous = os.environ.get("LOCAL_ALLY_DATA_DIR")
        os.environ["LOCAL_ALLY_DATA_DIR"] = self._tmp.name
        self.data_dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        if self._previous is None:
            os.environ.pop("LOCAL_ALLY_DATA_DIR", None)
        else:
            os.environ["LOCAL_ALLY_DATA_DIR"] = self._previous
        self._tmp.cleanup()
