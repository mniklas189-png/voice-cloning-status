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
    match_threshold: float = 0.68        # ab hier gilt ein Name als Treffer
    max_candidates: int = 5              # Rueckfrage-Liste bei Mehrdeutigkeit

    # App-Index
    index_on_first_start: bool = True
    include_path_executables: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Settings":
        """Unbekannte Schluessel werden ignoriert, fehlende bekommen Vorgaben."""
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
