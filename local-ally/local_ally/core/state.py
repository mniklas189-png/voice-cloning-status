"""Der gesamte sichtbare Zustand von Local Ally an einer Stelle.

Die UI liest ausschliesslich aus diesem Objekt und schreibt nie hinein. Das
haelt die Slint-Bruecke duenn und macht die Anwendungslogik ohne UI testbar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ..app_index.models import AppEntry, MatchResult
from ..speech.base import EngineInfo


class Status(str, Enum):
    IDLE = "idle"                  # bereit, hoert nicht zu
    LOADING = "loading"            # Modell wird geladen
    WAITING_WAKE = "waiting_wake"  # hoert mit, wartet aber auf das Wake Word
    LISTENING = "listening"        # nimmt Befehle entgegen
    MUTED = "muted"                # Mikrofon stummgeschaltet
    WORKING = "working"            # Befehl wird ausgefuehrt
    ERROR = "error"


STATUS_LABELS: dict[Status, str] = {
    Status.IDLE: "Bereit",
    Status.LOADING: "Modell wird geladen ...",
    Status.WAITING_WAKE: "Warte auf Wake Word",
    Status.LISTENING: "Ich höre zu",
    Status.MUTED: "Mikrofon stumm",
    Status.WORKING: "Einen Moment ...",
    Status.ERROR: "Fehler",
}


@dataclass
class AppState:
    # Spracherkennung
    status: Status = Status.IDLE
    status_detail: str = ""
    listening: bool = False
    level: float = 0.0
    partial_text: str = ""
    recognized_text: str = ""

    # Aktivierung
    muted: bool = False
    wake_armed: bool = False      # Wake Word erkannt, Befehl darf folgen
    wake_heard: str = ""          # zuletzt gehoert, aber ohne Wake Word verworfen
    ptt_active: bool = False      # PTT-Taste wird gerade gehalten

    # Ergebnis des letzten Befehls
    action_text: str = ""
    action_ok: bool = True
    candidates: list[MatchResult] = field(default_factory=list)
    awaiting_choice: bool = False
    awaiting_confirm: bool = False   # kritische Aktion wartet auf Zustimmung
    confirm_question: str = ""

    # Timer (Restzeit als fertige Beschriftung)
    timers: list[str] = field(default_factory=list)

    # App-Index
    apps: list[AppEntry] = field(default_factory=list)   # gefilterte Ansicht
    app_count: int = 0
    app_filter: str = ""
    indexing: bool = False
    index_detail: str = ""
    last_index: str = ""

    # Einstellungen / Umgebung
    engines: list[EngineInfo] = field(default_factory=list)
    input_devices: list[str] = field(default_factory=list)
    hotkey_detail: str = ""             # Klartext zum Zustand der Kuerzel
    hotkey_errors: list[str] = field(default_factory=list)
    hotkeys_ok: bool = False
    error: str = ""

    # Aenderungszaehler: die UI baut Listenmodelle nur neu, wenn noetig.
    apps_revision: int = 0
    candidates_revision: int = 0

    @property
    def status_label(self) -> str:
        return self.status_detail or STATUS_LABELS.get(self.status, "")
