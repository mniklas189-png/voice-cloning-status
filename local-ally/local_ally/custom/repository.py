"""Eigene Funktionen dauerhaft speichern."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from ..database import Database
from .models import CustomCommand

log = logging.getLogger(__name__)


class CustomCommandRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    # --- Lesen -------------------------------------------------------------
    def all(self, only_enabled: bool = False) -> list[CustomCommand]:
        sql = "SELECT * FROM custom_commands"
        if only_enabled:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY phrase COLLATE NOCASE ASC"
        return [self._to_command(row) for row in self.db.query(sql)]

    def get(self, command_id: int) -> CustomCommand | None:
        row = self.db.query_one("SELECT * FROM custom_commands WHERE id = ?", (command_id,))
        return self._to_command(row) if row else None

    def count(self) -> int:
        row = self.db.query_one("SELECT COUNT(*) AS n FROM custom_commands")
        return int(row["n"]) if row else 0

    def taken_phrases(self, except_id: int = 0) -> set[str]:
        """Belegte Befehle - fuer die Pruefung auf Dubletten."""
        rows = self.db.query(
            "SELECT normalized FROM custom_commands WHERE id <> ?", (except_id,)
        )
        return {row["normalized"] for row in rows}

    # --- Schreiben ---------------------------------------------------------
    def save(self, command: CustomCommand) -> CustomCommand:
        """Anlegen oder aktualisieren. Gibt den gespeicherten Stand zurueck."""
        if command.id:
            self.db.execute(
                """
                UPDATE custom_commands
                   SET phrase = ?, normalized = ?, phonetic = ?, action = ?,
                       target = ?, enabled = ?
                 WHERE id = ?
                """,
                (command.phrase.strip(), command.normalized, command.phonetic,
                 command.action, command.target.strip(), int(command.enabled), command.id),
            )
            self.db.commit()
            log.info("Eigene Funktion aktualisiert: %r", command.phrase)
            return self.get(command.id) or command

        cursor = self.db.execute(
            """
            INSERT INTO custom_commands
                (phrase, normalized, phonetic, action, target, enabled, created)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (command.phrase.strip(), command.normalized, command.phonetic,
             command.action, command.target.strip(), int(command.enabled),
             datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        self.db.commit()
        command.id = int(cursor.lastrowid)
        log.info("Eigene Funktion angelegt: %r", command.phrase)
        return command

    def delete(self, command_id: int) -> bool:
        cursor = self.db.execute("DELETE FROM custom_commands WHERE id = ?", (command_id,))
        self.db.commit()
        return cursor.rowcount > 0

    def set_enabled(self, command_id: int, enabled: bool) -> None:
        self.db.execute(
            "UPDATE custom_commands SET enabled = ? WHERE id = ?",
            (int(enabled), command_id),
        )
        self.db.commit()

    def note_use(self, command_id: int) -> None:
        self.db.execute(
            "UPDATE custom_commands SET use_count = use_count + 1 WHERE id = ?",
            (command_id,),
        )
        self.db.commit()

    # --- Hilfen ------------------------------------------------------------
    @staticmethod
    def _to_command(row) -> CustomCommand:
        return CustomCommand(
            id=int(row["id"]),
            phrase=row["phrase"],
            action=row["action"],
            target=row["target"],
            enabled=bool(row["enabled"]),
            use_count=int(row["use_count"]),
        )
