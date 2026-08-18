"""Ereignisse und ein schlanker, threadsicherer Ereignisbus.

Architekturentscheidung
-----------------------
Mikrofonaufnahme und Spracherkennung laufen in eigenen Threads, die Slint-UI
laeuft im Hauptthread. Die Python-Anbindung von Slint bietet (Stand 1.9) kein
``invoke_from_event_loop``, mit dem ein Hintergrundthread direkt in den
UI-Thread springen koennte.

Deshalb kommunizieren alle Threads ausschliesslich ueber eine
``queue.Queue``. Der UI-Thread leert sie in einem Slint-Timer (siehe
:mod:`local_ally.ui.bridge`). Vorteile: keine Sperren im UI-Code, keine
Slint-Objekte in Hintergrundthreads, und die gesamte Anwendungslogik laeuft
deterministisch in genau einem Thread.
"""

from __future__ import annotations

import queue
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventType(str, Enum):
    # Spracherkennung
    SPEECH_STATE = "speech_state"          # Engine gestartet/gestoppt/Fehler
    SPEECH_PARTIAL = "speech_partial"      # Zwischenergebnis (nur Anzeige)
    SPEECH_FINAL = "speech_final"          # Endergebnis -> wird zum Befehl
    SPEECH_LEVEL = "speech_level"          # Aussteuerung des Mikrofons (0..1)

    # App-Index
    INDEX_STARTED = "index_started"
    INDEX_PROGRESS = "index_progress"
    INDEX_FINISHED = "index_finished"

    # Allgemein
    ERROR = "error"
    NOTICE = "notice"


@dataclass(slots=True)
class Event:
    """Ein Ereignis aus einem Hintergrundthread an die Anwendungslogik."""

    type: EventType
    payload: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.payload.get(key, default)


class EventBus:
    """Sehr kleine Warteschlange - absichtlich ohne Callback-Registrierung.

    Hintergrundthreads rufen nur :meth:`publish`, der UI-Thread nur
    :meth:`drain`. Damit ist die Richtung des Datenflusses im Code sichtbar.
    """

    def __init__(self) -> None:
        self._queue: "queue.Queue[Event]" = queue.Queue()

    def publish(self, event_type: EventType, **payload: Any) -> None:
        self._queue.put(Event(event_type, payload))

    def drain(self, limit: int = 64) -> list[Event]:
        """Holt bis zu ``limit`` Ereignisse ab, ohne zu blockieren."""
        events: list[Event] = []
        for _ in range(limit):
            try:
                events.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return events
