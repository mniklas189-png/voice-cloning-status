"""Duenne Huelle um :mod:`sqlite3`.

Warum SQLite statt einer JSON-Datei: der App-Index wird bei jedem Scan
komplett abgeglichen, waechst auf einige hundert bis tausend Eintraege und
soll spaeter noch Nutzungsstatistiken und benutzerdefinierte Aliase
aufnehmen. SQLite ist dafuer da, liegt der Standardbibliothek bei und
braucht keinen Server - also perfekt fuer eine rein lokale Anwendung.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path

from ..core.paths import database_path

log = logging.getLogger(__name__)

_SCHEMA_FILE = Path(__file__).with_name("schema.sql")


class Database:
    """Verbindung mit Schema-Initialisierung und einfachem Transaktionshelfer.

    ``check_same_thread=False`` plus eine Sperre: der Index-Scan laeuft in
    einem Hintergrundthread, die UI liest im Hauptthread. SQLite selbst ist
    threadsicher, die Python-Verbindung serialisieren wir hier selbst.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or database_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._create_schema()

    def _create_schema(self) -> None:
        with self._lock:
            self._conn.executescript(_SCHEMA_FILE.read_text(encoding="utf-8"))
            self._conn.commit()

    @property
    def lock(self) -> threading.RLock:
        return self._lock

    def execute(self, sql: str, params: tuple | dict = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    def executemany(self, sql: str, seq) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.executemany(sql, seq)

    def query(self, sql: str, params: tuple | dict = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def query_one(self, sql: str, params: tuple | dict = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def commit(self) -> None:
        with self._lock:
            self._conn.commit()

    def transaction(self):
        """Kontextmanager: ``with db.transaction(): ...``"""
        return _Transaction(self)

    # --- Metadaten ---------------------------------------------------------
    def get_meta(self, key: str, default: str | None = None) -> str | None:
        row = self.query_one("SELECT value FROM meta WHERE key = ?", (key,))
        return row["value"] if row else default

    def set_meta(self, key: str, value: str) -> None:
        self.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()


class _Transaction:
    def __init__(self, db: Database) -> None:
        self._db = db

    def __enter__(self) -> Database:
        self._db._lock.acquire()
        return self._db

    def __exit__(self, exc_type, exc, tb) -> bool:
        try:
            if exc_type is None:
                self._db._conn.commit()
            else:
                self._db._conn.rollback()
        finally:
            self._db._lock.release()
        return False
