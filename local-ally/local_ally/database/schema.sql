-- Schema des lokalen App-Index.
--
-- Ein Programm kann unter mehreren Namen bekannt sein (Startmenue-Eintrag,
-- Registry-Anzeigename, Dateiname, Abkuerzung). Deshalb liegen Namen in einer
-- eigenen Tabelle "app_aliases" statt in einer Textspalte - so laesst sich
-- jeder Name einzeln indizieren und gewichten.

CREATE TABLE IF NOT EXISTS apps (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL,          -- Anzeigename
    normalized_name TEXT    NOT NULL,          -- klein, ohne Sonderzeichen
    launch_target   TEXT    NOT NULL,          -- Pfad oder Startbefehl
    launch_kind     TEXT    NOT NULL DEFAULT 'path',  -- path|shell|uri|command
    arguments       TEXT    NOT NULL DEFAULT '',
    working_dir     TEXT    NOT NULL DEFAULT '',
    icon_path       TEXT    NOT NULL DEFAULT '',
    source          TEXT    NOT NULL,          -- start_menu|registry|path|...
    priority        INTEGER NOT NULL DEFAULT 0,-- hoehere Quelle gewinnt bei Gleichstand
    last_seen       TEXT    NOT NULL,          -- ISO-Zeitstempel des letzten Scans
    launch_count    INTEGER NOT NULL DEFAULT 0,-- haeufig genutzt => bevorzugt
    UNIQUE (launch_target, arguments, source)
);

CREATE INDEX IF NOT EXISTS idx_apps_normalized ON apps (normalized_name);
CREATE INDEX IF NOT EXISTS idx_apps_source     ON apps (source);

CREATE TABLE IF NOT EXISTS app_aliases (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    app_id       INTEGER NOT NULL REFERENCES apps (id) ON DELETE CASCADE,
    alias        TEXT    NOT NULL,   -- Originalschreibweise
    normalized   TEXT    NOT NULL,   -- Vergleichsform
    phonetic     TEXT    NOT NULL DEFAULT '',  -- Koelner Phonetik
    kind         TEXT    NOT NULL DEFAULT 'auto', -- auto|user|file|acronym
    UNIQUE (app_id, normalized)
);

CREATE INDEX IF NOT EXISTS idx_alias_normalized ON app_aliases (normalized);
CREATE INDEX IF NOT EXISTS idx_alias_phonetic   ON app_aliases (phonetic);
CREATE INDEX IF NOT EXISTS idx_alias_app        ON app_aliases (app_id);

-- Schluessel/Wert-Ablage fuer Metadaten (z.B. Zeitpunkt des letzten Scans).
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Vom Nutzer angelegte Sprachbefehle ("Eigene Funktionen").
--
-- Sie liegen in derselben Datenbank wie der Programm-Index: beides gehoert
-- zum lokalen Wissen ueber diesen Rechner, und ein zweiter Speicherort
-- waere eine zusaetzliche Fehlerquelle beim Sichern.

CREATE TABLE IF NOT EXISTS custom_commands (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    phrase     TEXT    NOT NULL,           -- gesprochener Befehl
    normalized TEXT    NOT NULL,           -- Vergleichsform
    phonetic   TEXT    NOT NULL DEFAULT '',-- Koelner Phonetik
    action     TEXT    NOT NULL,           -- app|website|command|folder|text|keys
    target     TEXT    NOT NULL DEFAULT '',-- was die Aktion braucht
    enabled    INTEGER NOT NULL DEFAULT 1,
    created    TEXT    NOT NULL,
    use_count  INTEGER NOT NULL DEFAULT 0,
    UNIQUE (normalized)
);

CREATE INDEX IF NOT EXISTS idx_custom_normalized ON custom_commands (normalized);
