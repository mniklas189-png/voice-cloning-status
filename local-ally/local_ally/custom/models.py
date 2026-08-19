"""Datentypen und Register der Aktionsarten."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from ..core import text as textutil

MIN_PHRASE_CHARS = 3
MAX_PHRASE_CHARS = 60


@dataclass(slots=True)
class CustomCommand:
    """Eine vom Nutzer angelegte Funktion."""

    id: int = 0
    phrase: str = ""            # was gesagt wird
    action: str = "app"         # Id der Aktionsart
    target: str = ""            # Programm, URL, Befehl, Pfad, Text, Tasten
    enabled: bool = True
    use_count: int = 0

    @property
    def normalized(self) -> str:
        return textutil.normalize(self.phrase)

    @property
    def phonetic(self) -> str:
        return textutil.phonetic_key(self.phrase)


@dataclass(frozen=True, slots=True)
class CustomActionType:
    """Eine Art von Aktion, die eine eigene Funktion ausfuehren kann."""

    id: str
    label: str               # "App öffnen"
    short_label: str         # "App" - fuer die Auswahl in der Oberflaeche
    config_label: str        # Beschriftung des Konfigurationsfelds
    placeholder: str
    hint: str = ""
    picks_app: bool = False  # bietet die Oberflaeche eine Programmauswahl an?
    validate: Callable[[str], str] = field(default=lambda value: "")


# --- Pruefungen --------------------------------------------------------
def _require(value: str, what: str) -> str:
    return "" if value.strip() else f"{what} fehlt."


def _validate_url(value: str) -> str:
    value = value.strip()
    if not value:
        return "Adresse fehlt."
    if " " in value:
        return "Eine Adresse enthält keine Leerzeichen."
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", value) and "." not in value:
        return "Das sieht nicht nach einer Adresse aus."
    return ""


def _validate_keys(value: str) -> str:
    from ..hotkeys.keys import Hotkey, HotkeyError

    try:
        Hotkey.parse(value)
    except HotkeyError as exc:
        return str(exc)
    return ""


ACTION_TYPES: tuple[CustomActionType, ...] = (
    CustomActionType(
        id="app",
        label="App öffnen",
        short_label="App",
        config_label="Programm",
        placeholder="Name eingeben und auswählen",
        hint="aus dem Programm-Index",
        picks_app=True,
        validate=lambda value: _require(value, "Programm"),
    ),
    CustomActionType(
        id="website",
        label="Website öffnen",
        short_label="Website",
        config_label="Adresse",
        placeholder="https://www.youtube.com",
        hint="öffnet sich im Standardbrowser",
        validate=_validate_url,
    ),
    CustomActionType(
        id="command",
        label="CMD-Befehl ausführen",
        short_label="CMD",
        config_label="Befehl",
        placeholder="ipconfig /flushdns",
        hint="läuft im Hintergrund, ohne Konsolenfenster",
        validate=lambda value: _require(value, "Befehl"),
    ),
    CustomActionType(
        id="folder",
        label="Ordner öffnen",
        short_label="Ordner",
        config_label="Pfad",
        placeholder=r"C:\Users\Ich\Projekte",
        hint="öffnet sich im Explorer",
        validate=lambda value: _require(value, "Pfad"),
    ),
    CustomActionType(
        id="text",
        label="Text tippen",
        short_label="Text",
        config_label="Text",
        placeholder="max.mustermann@example.com",
        hint="wird ins aktive Fenster geschrieben",
        validate=lambda value: _require(value, "Text"),
    ),
    CustomActionType(
        id="keys",
        label="Tastenkombination senden",
        short_label="Tasten",
        config_label="Tasten",
        placeholder="ctrl+shift+n",
        hint="z. B. für einen Kurzbefehl im Vordergrundprogramm",
        validate=_validate_keys,
    ),
)


def action_type(action_id: str) -> CustomActionType:
    """Aktionsart nachschlagen - faellt auf die erste zurueck."""
    for entry in ACTION_TYPES:
        if entry.id == action_id:
            return entry
    return ACTION_TYPES[0]


def _reserved_words() -> frozenset[str]:
    """Woerter, die Local Ally selbst braucht.

    Antworten auf Rueckfragen werden vor den eigenen Funktionen geprueft -
    ein Befehl "ja" wuerde also nie ausloesen. Statt ihn stillschweigend
    wirkungslos zu speichern, wird er hier abgelehnt.
    """
    from ..commands.choice import _CANCEL_WORDS
    from ..commands.confirm import NO_WORDS, YES_WORDS

    return frozenset(YES_WORDS | NO_WORDS | _CANCEL_WORDS)


def validate(command: CustomCommand, existing_normalized: set[str] | None = None) -> str:
    """Prueft eine Funktion vor dem Speichern. Leer heisst: in Ordnung."""
    phrase = command.phrase.strip()
    if not phrase:
        return "Der Befehl fehlt."
    normalized = command.normalized
    if len(normalized) < MIN_PHRASE_CHARS:
        return f"Der Befehl braucht mindestens {MIN_PHRASE_CHARS} Buchstaben."
    if len(phrase) > MAX_PHRASE_CHARS:
        return "Der Befehl ist zu lang."
    if normalized in _reserved_words():
        return f"„{phrase}“ braucht Local Ally für Rückfragen."
    if existing_normalized and normalized in existing_normalized:
        return f"„{phrase}“ ist schon vergeben."
    return action_type(command.action).validate(command.target)
