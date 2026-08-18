#!/usr/bin/env python3
"""Startet Local Ally.

Praktisch fuer eine Verknuepfung auf dem Desktop:
``pythonw run.py`` startet unter Windows ohne Konsolenfenster.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from local_ally.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
