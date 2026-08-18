"""Gemeinsame Schnittstelle aller Spracherkenner.

Ein Erkenner bekommt rohe PCM-Bloecke und liefert Ergebnisse zurueck. Ob er
dabei streamt (Vosk) oder erst am Ende einer Aeusserung rechnet (Whisper),
bleibt seine Sache - die uebrige Anwendung sieht nur
:class:`SpeechResult`-Objekte.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

# 16 kHz, mono, 16 Bit signed - das erwarten sowohl Vosk als auch Whisper.
SAMPLE_RATE = 16_000
CHANNELS = 1
SAMPLE_WIDTH = 2
BLOCK_SIZE = 4_000  # Samples pro Block (250 ms)


@dataclass(slots=True)
class SpeechResult:
    """Ein Erkennungsergebnis.

    ``is_final`` unterscheidet Zwischenergebnisse (nur Anzeige) von fertigen
    Aeusserungen (werden als Befehl ausgewertet).
    """

    text: str
    is_final: bool = False
    confidence: float = 0.0


@dataclass(slots=True)
class EngineInfo:
    """Beschreibung eines Backends fuer die Einstellungsseite."""

    id: str
    display_name: str
    description: str
    available: bool
    detail: str = ""  # Grund, falls nicht verfuegbar (z.B. fehlendes Modell)


class SpeechEngine(ABC):
    """Basisklasse fuer alle Erkenner."""

    id: str = ""
    display_name: str = ""

    @abstractmethod
    def start(self) -> None:
        """Modell laden und Zustand zuruecksetzen. Darf laenger dauern."""

    @abstractmethod
    def feed(self, pcm: bytes) -> list[SpeechResult]:
        """Einen PCM-Block verarbeiten."""

    def flush(self) -> list[SpeechResult]:
        """Aufnahme beendet - noch offene Aeusserungen abschliessen."""
        return []

    def stop(self) -> None:
        """Ressourcen freigeben. Das Modell darf im Speicher bleiben."""

    def reset(self) -> None:
        """Zustand zwischen zwei Aeusserungen zuruecksetzen."""
