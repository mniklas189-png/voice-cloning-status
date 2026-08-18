"""Der Controller verbindet Spracherkennung, Befehle und App-Index.

Er ist die einzige Stelle, an der alle Teile zusammenlaufen - und er kennt
keine UI. Die Slint-Bruecke ruft nur Methoden auf und liest
:class:`~local_ally.core.state.AppState`.

Threading-Modell
----------------
* Spracherkennung: eigener Thread (:mod:`local_ally.speech.service`)
* Index-Aufbau: eigener Thread, gestartet in :meth:`rebuild_index`
* alles Uebrige, inklusive Befehlsausfuehrung: der Thread, der
  :meth:`pump` aufruft - in der laufenden Anwendung der UI-Thread.

Damit gibt es genau einen Ort, an dem der Zustand veraendert wird.
"""

from __future__ import annotations

import logging
import threading
from typing import Sequence

from ..app_index.indexer import AppIndexer
from ..app_index.models import AppEntry
from ..app_index.repository import AppRepository
from ..commands import CommandContext, CommandRegistry, default_registry
from ..database import Database
from ..settings import Settings, SettingsStore
from ..speech import audio
from ..speech.registry import available_engines
from ..speech.service import RecognitionService
from .events import Event, EventBus, EventType
from .state import AppState, Status

log = logging.getLogger(__name__)

MAX_LISTED_APPS = 300  # mehr Zeilen bringt der Liste in der UI keinen Nutzen


class Controller:
    def __init__(
        self,
        *,
        database: Database | None = None,
        settings_store: SettingsStore | None = None,
        registry: CommandRegistry | None = None,
    ) -> None:
        self.bus = EventBus()
        self.settings_store = settings_store or SettingsStore()
        self.database = database or Database()
        self.repository = AppRepository(self.database)
        self.commands = registry or default_registry()
        self.speech = RecognitionService(self.bus, lambda: self.settings)
        self.state = AppState()

        self._apps_cache: list[AppEntry] | None = None
        self._index_thread: threading.Thread | None = None
        # Die Liste der Erkenner haengt nicht vom Start ab und wird sofort
        # gefuellt, damit die Einstellungsseite nie leer erscheint.
        self.refresh_engines()
        self._context = CommandContext(
            repository=self.repository,
            settings=self.settings,
            apps=self._all_apps,
        )

    # --- Zugriffe ----------------------------------------------------------
    @property
    def settings(self) -> Settings:
        return self.settings_store.settings

    def _all_apps(self) -> Sequence[AppEntry]:
        """Programmliste fuer die Suche - wird nach jedem Index-Lauf verworfen."""
        if self._apps_cache is None:
            self._apps_cache = self.repository.all_apps()
        return self._apps_cache

    # --- Lebenszyklus ------------------------------------------------------
    def startup(self) -> None:
        """Nach dem Programmstart aufrufen."""
        self.refresh_engines()
        self.refresh_devices()
        self.refresh_apps()

        if self.state.app_count == 0 and self.settings.index_on_first_start:
            self.state.action_text = "Erster Start: ich suche installierte Programme ..."
            self.rebuild_index()

    def shutdown(self) -> None:
        self.speech.shutdown()
        self.database.close()

    # --- Spracherkennung ---------------------------------------------------
    def toggle_listening(self) -> None:
        if self.speech.is_running:
            self.stop_listening()
        else:
            self.start_listening()

    def start_listening(self) -> None:
        if self.speech.is_running:
            return
        self.state.partial_text = ""
        self.state.error = ""
        self.state.listening = True
        self.state.status = Status.LOADING
        self.state.status_detail = ""
        self.speech.start()

    def stop_listening(self) -> None:
        self.speech.stop()
        self.state.listening = False
        self.state.partial_text = ""
        self.state.status = Status.IDLE
        self.state.status_detail = ""

    # --- Einstellungen -----------------------------------------------------
    def update_settings(self, **changes) -> None:
        settings = self.settings_store.update(**changes)
        self._context.settings = settings
        # Erkennungsrelevante Aenderungen erfordern einen neuen Erkenner.
        if {"speech_engine", "language", "vosk_model_path", "whisper_model_size",
                "whisper_compute_type", "input_device"} & set(changes):
            self.speech.invalidate_engine()
            if self.speech.is_running:
                self.stop_listening()
        self.refresh_engines()

    def refresh_engines(self) -> None:
        self.state.engines = available_engines(self.settings)

    def refresh_devices(self) -> None:
        self.state.input_devices = [device.name for device in audio.list_input_devices()]

    # --- App-Index ---------------------------------------------------------
    def refresh_apps(self) -> None:
        """Programmliste und Filteransicht neu aus der Datenbank lesen."""
        self._apps_cache = None
        self.state.app_count = self.repository.count()
        self.state.last_index = self.repository.last_index_time() or ""
        self.apply_app_filter(self.state.app_filter)

    def apply_app_filter(self, needle: str) -> None:
        self.state.app_filter = needle
        self.state.apps = self.repository.search_prefix(needle, limit=MAX_LISTED_APPS)
        self.state.apps_revision += 1

    def rebuild_index(self) -> None:
        """Index in einem Hintergrundthread neu aufbauen."""
        if self._index_thread is not None and self._index_thread.is_alive():
            return

        indexer = AppIndexer(
            self.repository,
            include_path_executables=self.settings.include_path_executables,
        )

        def worker() -> None:
            self.bus.publish(EventType.INDEX_STARTED)
            try:
                count = indexer.rebuild(
                    lambda name, number, total: self.bus.publish(
                        EventType.INDEX_PROGRESS, source=name, number=number, total=total
                    )
                )
                self.bus.publish(EventType.INDEX_FINISHED, count=count)
            except Exception as exc:
                log.exception("Index-Aufbau fehlgeschlagen")
                self.bus.publish(EventType.INDEX_FINISHED, count=0, error=str(exc))

        self._index_thread = threading.Thread(target=worker, name="local-ally-index", daemon=True)
        self._index_thread.start()

    # --- Befehle -----------------------------------------------------------
    def handle_text(self, text: str) -> None:
        """Erkannten Satz als Befehl auswerten."""
        text = (text or "").strip()
        if not text:
            return

        self.state.recognized_text = text
        self.state.partial_text = ""

        result = self.commands.handle(text, self._context)
        if result is None:
            self.state.action_ok = False
            self.state.action_text = (
                "Das habe ich nicht als Befehl erkannt. Versuche es mit „Öffne <Programm>“."
            )
            return

        self.state.action_ok = result.ok
        self.state.action_text = result.message
        self.state.awaiting_choice = result.needs_choice
        self.state.candidates = list(result.candidates)
        self.state.candidates_revision += 1
        self._context.pending_candidates = self.state.candidates if result.needs_choice else []

        if result.app is not None:
            self._apps_cache = None  # launch_count hat sich geaendert

    def choose_candidate(self, index: int) -> None:
        """Auswahl per Mausklick aus der Rueckfrage-Liste."""
        candidates = self.state.candidates
        if not 0 <= index < len(candidates):
            return
        from ..commands.open_app import launch_match

        result = launch_match(candidates[index].app, self._context)
        self.state.action_ok = result.ok
        self.state.action_text = result.message
        self.clear_candidates()
        self._apps_cache = None

    def launch_app_id(self, app_id: int) -> None:
        """Start aus der Programmliste heraus (Mausklick)."""
        entry = self.repository.get(app_id)
        if entry is None:
            return
        from ..commands.open_app import launch_match

        result = launch_match(entry, self._context)
        self.state.action_ok = result.ok
        self.state.action_text = result.message
        self._apps_cache = None

    def clear_candidates(self) -> None:
        self.state.candidates = []
        self.state.awaiting_choice = False
        self.state.candidates_revision += 1
        self._context.pending_candidates = []

    # --- Ereignisse --------------------------------------------------------
    def pump(self) -> bool:
        """Ereignisse der Hintergrundthreads verarbeiten.

        Rueckgabe: ``True``, wenn sich der Zustand geaendert hat und die UI
        neu gezeichnet werden sollte.
        """
        events = self.bus.drain()
        if not events:
            return False
        for event in events:
            self._handle_event(event)
        return True

    def _handle_event(self, event: Event) -> None:
        if event.type is EventType.SPEECH_STATE:
            self._on_speech_state(event)

        elif event.type is EventType.SPEECH_PARTIAL:
            self.state.partial_text = event.get("text", "")

        elif event.type is EventType.SPEECH_FINAL:
            self.handle_text(event.get("text", ""))

        elif event.type is EventType.SPEECH_LEVEL:
            self.state.level = float(event.get("level", 0.0))

        elif event.type is EventType.INDEX_STARTED:
            self.state.indexing = True
            self.state.index_detail = "Suche startet ..."

        elif event.type is EventType.INDEX_PROGRESS:
            self.state.index_detail = (
                f"{event.get('source', '')} ({event.get('number', 0)}/{event.get('total', 0)})"
            )

        elif event.type is EventType.INDEX_FINISHED:
            self.state.indexing = False
            error = event.get("error")
            if error:
                self.state.index_detail = f"Fehlgeschlagen: {error}"
                self.state.error = error
            else:
                count = event.get("count", 0)
                self.state.index_detail = f"{count} Programme gefunden"
                self.state.action_text = f"Programm-Index aktualisiert: {count} Einträge."
                self.state.action_ok = True
            self.refresh_apps()

        elif event.type is EventType.ERROR:
            self.state.error = event.get("message", "")
            self.state.action_ok = False
            self.state.action_text = self.state.error

        elif event.type is EventType.NOTICE:
            self.state.action_text = event.get("message", "")

    def _on_speech_state(self, event: Event) -> None:
        state = event.get("state", "")
        detail = event.get("detail", "")
        mapping = {
            "idle": Status.IDLE,
            "loading": Status.LOADING,
            "listening": Status.LISTENING,
            "error": Status.ERROR,
        }
        self.state.status = mapping.get(state, Status.IDLE)
        self.state.status_detail = detail
        self.state.listening = state in {"listening", "loading"}
        if state == "idle":
            self.state.level = 0.0
