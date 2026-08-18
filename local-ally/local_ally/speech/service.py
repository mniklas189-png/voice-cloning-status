"""Aufnahme und Erkennung in einem Hintergrundthread.

Der Dienst kennt weder UI noch Befehle - er meldet ausschliesslich Ereignisse
an den :class:`~local_ally.core.events.EventBus`. Dadurch laesst er sich
einzeln testen und spaeter z.B. durch ein Aktivierungswort ("Hey Ally")
ergaenzen, ohne dass andere Module davon wissen muessen.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable

from ..core.events import EventBus, EventType
from ..settings import Settings
from .audio import AudioError, Microphone
from .base import SpeechEngine
from .registry import create_engine
from .vad import VoiceActivityDetector

log = logging.getLogger(__name__)

SettingsProvider = Callable[[], Settings]


class RecognitionService:
    """Startet und stoppt die Spracherkennung.

    Der Erkenner wird zwischen zwei Laeufen im Speicher gehalten: das Laden
    eines Modells dauert Sekunden, das Starten der Aufnahme soll sich aber
    sofort anfuehlen.
    """

    def __init__(self, bus: EventBus, settings_provider: SettingsProvider) -> None:
        self._bus = bus
        self._settings_provider = settings_provider
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        # Stumm heisst: das Mikrofon bleibt offen, aber kein einziger Block
        # erreicht den Erkenner. So kann weder ein Wake Word noch ein Befehl
        # entstehen, und das Aufheben der Stummschaltung wirkt sofort.
        self._muted = threading.Event()
        self._engine: SpeechEngine | None = None
        self._engine_key: tuple | None = None

    # --- Steuerung ---------------------------------------------------------
    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="local-ally-speech", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    @property
    def is_muted(self) -> bool:
        return self._muted.is_set()

    def set_muted(self, muted: bool) -> None:
        if muted:
            self._muted.set()
        else:
            self._muted.clear()

    def shutdown(self, timeout: float = 3.0) -> None:
        self.stop()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)
        if self._engine is not None:
            self._engine.stop()
            self._engine = None

    def invalidate_engine(self) -> None:
        """Nach Aenderungen in den Einstellungen den Erkenner neu aufbauen."""
        self._engine_key = None

    # --- Thread ------------------------------------------------------------
    def _run(self) -> None:
        settings = self._settings_provider()
        microphone: Microphone | None = None

        try:
            engine = self._ensure_engine(settings)
        except Exception as exc:
            log.exception("Spracherkennung konnte nicht gestartet werden")
            self._publish_state("error", str(exc))
            self._bus.publish(EventType.ERROR, message=str(exc))
            return

        try:
            microphone = Microphone(settings.input_device)
            microphone.start()
        except AudioError as exc:
            self._publish_state("error", str(exc))
            self._bus.publish(EventType.ERROR, message=str(exc))
            return

        self._publish_state("listening", "Ich höre zu ...")
        meter = VoiceActivityDetector()

        was_muted = False
        try:
            while not self._stop_event.is_set():
                pcm = microphone.read(timeout=0.25)
                if not pcm:
                    continue

                if self._muted.is_set():
                    if not was_muted:
                        # angefangene Aeusserung verwerfen, nicht aufheben
                        engine.reset()
                        was_muted = True
                        self._bus.publish(EventType.SPEECH_LEVEL, level=0.0)
                        self._publish_state("muted", "Mikrofon stumm")
                    continue

                if was_muted:
                    was_muted = False
                    engine.reset()
                    self._publish_state("listening", "")

                self._bus.publish(EventType.SPEECH_LEVEL, level=meter.level_indicator(pcm))
                self._emit(engine.feed(pcm))

            if not self._muted.is_set():
                self._emit(engine.flush())
        except Exception as exc:  # Erkennerfehler duerfen die App nicht beenden
            log.exception("Fehler in der Spracherkennung")
            self._bus.publish(EventType.ERROR, message=f"Spracherkennung abgebrochen: {exc}")
        finally:
            if microphone is not None:
                microphone.stop()
            engine.reset()
            self._publish_state("idle", "Bereit")

    def _emit(self, results) -> None:
        for result in results:
            if not result.text:
                continue
            if result.is_final:
                log.info("Erkannt: %r", result.text)
                self._bus.publish(
                    EventType.SPEECH_FINAL, text=result.text, confidence=result.confidence
                )
            else:
                self._bus.publish(EventType.SPEECH_PARTIAL, text=result.text)

    def _ensure_engine(self, settings: Settings) -> SpeechEngine:
        key = (
            settings.speech_engine,
            settings.language,
            settings.vosk_model_path,
            settings.whisper_model_size,
            settings.whisper_compute_type,
        )
        if self._engine is not None and self._engine_key == key:
            self._engine.start()  # nur Zustand zuruecksetzen, Modell bleibt geladen
            return self._engine

        if self._engine is not None:
            self._engine.stop()

        self._publish_state("loading", "Modell wird geladen ...")
        engine = create_engine(settings)
        engine.start()
        self._engine, self._engine_key = engine, key
        return engine

    def _publish_state(self, state: str, detail: str = "") -> None:
        self._bus.publish(EventType.SPEECH_STATE, state=state, detail=detail)
