"""Datenmodell der Einstellungen.

Bewusst ein flaches Dataclass mit Vorgabewerten: neue Optionen lassen sich
ergaenzen, ohne alte Konfigurationsdateien ungueltig zu machen.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any


@dataclass(slots=True)
class Settings:
    # Spracherkennung
    speech_engine: str = "vosk"          # Id aus local_ally.speech.registry
    language: str = "de"                 # Deutsch ist die Vorgabe
    vosk_model_path: str = ""            # leer => Automatik im Modellordner
    whisper_model_size: str = "small"    # tiny|base|small|medium|large-v3
    whisper_compute_type: str = "int8"   # int8 laeuft auf jeder CPU
    input_device: str = ""               # leer => Standardmikrofon des Systems

    # Aktivierung
    wake_word_enabled: bool = False      # Vorgabe aus: sonst reagiert nach
                                         # dem Update plötzlich nichts mehr
    wake_word: str = "Hey Ally"
    wake_word_timeout: float = 8.0       # Sekunden, in denen der Befehl folgen darf

    # Globale Tastenkuerzel
    hotkeys_enabled: bool = True
    mute_hotkey: str = "ctrl+alt+m"
    ptt_enabled: bool = False
    ptt_hotkey: str = "ctrl+alt+space"

    # Darstellung
    theme: str = "dark"                  # "dark" oder "light"

    # Verhalten
    auto_execute: bool = True            # Treffer sofort starten
    confirm_critical: bool = True        # vor Herunterfahren, Neustart, Schließen fragen
    match_threshold: float = 0.68        # ab hier gilt ein Name als Treffer
    max_candidates: int = 5              # Rueckfrage-Liste bei Mehrdeutigkeit

    # App-Index
    index_on_first_start: bool = True
    include_path_executables: bool = True

    def __post_init__(self) -> None:
        """Werte in sinnvolle Grenzen bringen.

        Die Datei ist von Hand editierbar und ueberlebt Programmversionen -
        ein unsinniger Wert darf den Start nicht verhindern.
        """
        self.match_threshold = min(max(float(self.match_threshold), 0.1), 1.0)
        self.max_candidates = max(int(self.max_candidates), 1)
        self.wake_word_timeout = min(max(float(self.wake_word_timeout), 1.0), 120.0)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Settings":
        """Bekannte Schluessel uebernehmen - mit passendem Typ.

        Unbekannte Schluessel werden ignoriert, fehlende und unbrauchbare
        bekommen die Vorgabe. Sonst reicht ein von Hand eingetragenes
        "acht" statt 8, um das Programm zum Absturz zu bringen.
        """
        values: dict[str, Any] = {}
        for field_info in fields(cls):
            if field_info.name not in data:
                continue
            coerced = _coerce(data[field_info.name], str(field_info.type), field_info.default)
            values[field_info.name] = coerced
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_TRUE = {"true", "ja", "yes", "1", "an", "on"}
_FALSE = {"false", "nein", "no", "0", "aus", "off"}


def _coerce(raw: Any, type_name: str, default: Any) -> Any:
    """Einen gelesenen Wert auf den erwarteten Typ bringen."""
    try:
        if type_name == "bool":
            if isinstance(raw, bool):
                return raw
            if isinstance(raw, (int, float)):
                return bool(raw)
            if isinstance(raw, str):
                lowered = raw.strip().lower()
                if lowered in _TRUE:
                    return True
                if lowered in _FALSE:
                    return False
            return default
        if type_name == "int":
            if isinstance(raw, bool):
                return default
            return int(raw)
        if type_name == "float":
            if isinstance(raw, bool):
                return default
            return float(raw)
        if type_name == "str":
            return raw if isinstance(raw, str) else default
    except (TypeError, ValueError):
        return default
    return raw
