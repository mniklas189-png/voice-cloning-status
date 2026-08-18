"""Datenbankzugriff fuer den App-Index."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable, Sequence

from ..core import text
from ..database import Database
from .models import AppEntry, DiscoveredApp

log = logging.getLogger(__name__)

META_LAST_INDEX = "app_index.last_run"

# Firmen- und Rechtsformzusaetze taugen nicht als Zweitname.
VENDOR_WORDS = frozenset(
    {"inc", "gmbh", "ltd", "corp", "llc", "company", "software", "technologies",
     "systems", "group", "labs", "studios", "interactive", "entertainment"}
)


def _now() -> str:
    """Zeitstempel eines Scans.

    Mikrosekunden sind Absicht: ``replace_all`` erkennt verschwundene
    Programme daran, dass ihr ``last_seen`` nicht dem aktuellen Scan
    entspricht. Auf Sekunden gerundet wuerden zwei kurz aufeinander folgende
    Laeufe denselben Wert tragen - und nichts wuerde mehr aufgeraeumt.
    """
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class AppRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    # --- Lesen -------------------------------------------------------------
    def count(self) -> int:
        row = self.db.query_one("SELECT COUNT(*) AS n FROM apps")
        return int(row["n"]) if row else 0

    def all_apps(self, limit: int | None = None) -> list[AppEntry]:
        sql = "SELECT * FROM apps ORDER BY launch_count DESC, name COLLATE NOCASE ASC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        rows = self.db.query(sql)
        return self._with_aliases([self._row_to_entry(r) for r in rows])

    def get(self, app_id: int) -> AppEntry | None:
        row = self.db.query_one("SELECT * FROM apps WHERE id = ?", (app_id,))
        if not row:
            return None
        return self._with_aliases([self._row_to_entry(row)])[0]

    def search_prefix(self, needle: str, limit: int = 50) -> list[AppEntry]:
        """Einfache Textsuche fuer die Programmliste in der UI."""
        needle = text.normalize(needle)
        if not needle:
            return self.all_apps(limit=limit)
        pattern = f"%{needle}%"
        rows = self.db.query(
            "SELECT DISTINCT a.* FROM apps a "
            "LEFT JOIN app_aliases al ON al.app_id = a.id "
            "WHERE a.normalized_name LIKE ? OR al.normalized LIKE ? "
            "ORDER BY a.launch_count DESC, a.name COLLATE NOCASE ASC LIMIT ?",
            (pattern, pattern, limit),
        )
        return self._with_aliases([self._row_to_entry(r) for r in rows])

    def last_index_time(self) -> str | None:
        return self.db.get_meta(META_LAST_INDEX)

    # --- Schreiben ---------------------------------------------------------
    def replace_all(self, apps: Iterable[DiscoveredApp]) -> int:
        """Ergebnis eines vollstaendigen Scans uebernehmen.

        Bewusst kein "alles loeschen und neu schreiben": bestehende Zeilen
        werden aktualisiert, damit ``launch_count`` (die Nutzungshaeufigkeit)
        einen Neuaufbau des Index ueberlebt. Eintraege, die der aktuelle Scan
        nicht mehr gesehen hat, verschwinden anschliessend.
        """
        stamp = _now()
        written = 0
        with self.db.transaction() as db:
            for app in apps:
                app_id = self._upsert(app, stamp)
                self._write_aliases(app_id, app)
                written += 1
            db.execute("DELETE FROM apps WHERE last_seen <> ?", (stamp,))
        self.db.set_meta(META_LAST_INDEX, stamp)
        log.info("App-Index aktualisiert: %d Programme", written)
        return written

    def _upsert(self, app: DiscoveredApp, stamp: str) -> int:
        self.db.execute(
            """
            INSERT INTO apps (name, normalized_name, launch_target, launch_kind,
                              arguments, working_dir, icon_path, source, priority, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(launch_target, arguments, source) DO UPDATE SET
                name            = excluded.name,
                normalized_name = excluded.normalized_name,
                launch_kind     = excluded.launch_kind,
                working_dir     = excluded.working_dir,
                icon_path       = excluded.icon_path,
                priority        = excluded.priority,
                last_seen       = excluded.last_seen
            """,
            (
                app.name,
                text.normalize(app.name),
                app.launch_target,
                app.launch_kind,
                app.arguments,
                app.working_dir,
                app.icon_path,
                app.source,
                app.priority,
                stamp,
            ),
        )
        row = self.db.query_one(
            "SELECT id FROM apps WHERE launch_target = ? AND arguments = ? AND source = ?",
            (app.launch_target, app.arguments, app.source),
        )
        return int(row["id"])

    def _write_aliases(self, app_id: int, app: DiscoveredApp) -> None:
        candidates = generate_aliases(app.name, app.aliases, app.launch_target)
        # Nur automatisch erzeugte Aliase erneuern - vom Nutzer vergebene
        # Namen (kind = 'user') ueberleben jeden Neuaufbau des Index.
        self.db.execute(
            "DELETE FROM app_aliases WHERE app_id = ? AND kind IN ('auto', 'acronym')",
            (app_id,),
        )
        self.db.executemany(
            "INSERT OR IGNORE INTO app_aliases (app_id, alias, normalized, phonetic, kind) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (app_id, alias, text.normalize(alias), text.phonetic_key(alias), kind)
                for alias, kind in candidates
            ],
        )

    def add_user_alias(self, app_id: int, alias: str) -> None:
        """Vom Nutzer vergebener Zweitname - ueberlebt jeden Neuaufbau."""
        self.db.execute(
            "INSERT OR IGNORE INTO app_aliases (app_id, alias, normalized, phonetic, kind) "
            "VALUES (?, ?, ?, ?, 'user')",
            (app_id, alias, text.normalize(alias), text.phonetic_key(alias)),
        )
        self.db.commit()

    def note_launch(self, app_id: int) -> None:
        self.db.execute(
            "UPDATE apps SET launch_count = launch_count + 1 WHERE id = ?", (app_id,)
        )
        self.db.commit()

    # --- Hilfen ------------------------------------------------------------
    @staticmethod
    def _row_to_entry(row) -> AppEntry:
        return AppEntry(
            id=int(row["id"]),
            name=row["name"],
            launch_target=row["launch_target"],
            launch_kind=row["launch_kind"],
            arguments=row["arguments"],
            working_dir=row["working_dir"],
            icon_path=row["icon_path"],
            source=row["source"],
            priority=int(row["priority"]),
            launch_count=int(row["launch_count"]),
        )

    def _with_aliases(self, entries: Sequence[AppEntry]) -> list[AppEntry]:
        if not entries:
            return []
        by_id = {entry.id: entry for entry in entries}
        placeholders = ",".join("?" * len(by_id))
        rows = self.db.query(
            f"SELECT app_id, alias, kind FROM app_aliases WHERE app_id IN ({placeholders})",
            tuple(by_id),
        )
        for row in rows:
            entry = by_id[int(row["app_id"])]
            if row["kind"] == "acronym":
                entry.weak_aliases.append(row["alias"])
            else:
                entry.aliases.append(row["alias"])
        return list(entries)


def generate_aliases(
    name: str, extra: Sequence[str], launch_target: str
) -> list[tuple[str, str]]:
    """Zweitnamen ableiten, unter denen ein Programm angesprochen werden kann.

    Beispiel "Visual Studio Code (64-bit)":
    -> "visual studio code" (bereinigt), "code" (Dateiname), "vsc" (Akronym)

    Rueckgabe sind Paare ``(Alias, Art)``. Akronyme bekommen die Art
    ``acronym`` und zaehlen bei der Suche schwaecher - sie entstehen
    automatisch und kollidieren sonst mit echten Programmnamen.
    """
    from pathlib import PurePath, PureWindowsPath

    candidates: list[tuple[str, str]] = [(name, "auto")]
    candidates += [(alias, "auto") for alias in extra]

    cleaned = " ".join(text.significant_tokens(name))
    if cleaned:
        candidates.append((cleaned, "auto"))

    parts = [word for word in cleaned.split() if word[0].isalpha()]
    if len(parts) >= 2:
        acronym = "".join(word[0] for word in parts)
        if len(acronym) >= 3:  # "vsc" ja, "23" nein
            candidates.append((acronym, "acronym"))
        # Das letzte Wort ist meist das kennzeichnende ("Adobe Photoshop").
        last = parts[-1]
        if len(last) >= 4 and last not in VENDOR_WORDS:
            candidates.append((last, "auto"))

    # Der Dateiname des Ziels ist oft der gesprochene Name ("Code.exe").
    # Bei Shell- und URI-Zielen gibt es keinen sinnvollen Dateinamen.
    target = launch_target.strip('"')
    if target and not target.lower().startswith("shell:") and "://" not in target:
        stem = (PureWindowsPath(target) if "\\" in target else PurePath(target)).stem
        if stem:
            candidates.append((stem, "auto"))

    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for candidate, kind in candidates:
        normalized = text.normalize(candidate)
        if len(normalized) < 2 or normalized in seen:
            continue
        seen.add(normalized)
        result.append((candidate.strip(), kind))
    return result
