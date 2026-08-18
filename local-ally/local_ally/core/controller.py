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
import time
from typing import Sequence

from ..app_index.indexer import AppIndexer
from ..app_index.models import AppEntry
from ..app_index.repository import AppRepository
from ..commands import CommandContext, CommandRegistry, default_registry
from ..database import Database
from ..hotkeys import ACTION_MUTE, ACTION_PTT, PRESS, RELEASE, HotkeyManager
from ..settings import Settings, SettingsStore
from ..speech import audio
from ..speech.registry import available_engines
from ..speech.service import RecognitionService
from ..speech.wakeword import WakeWordDetector
from .events import Event, EventBus, EventType
from .state import AppState, Status

log = logging.getLogger(__name__)

MAX_LISTED_APPS = 300  # mehr Zeilen bringt der Liste in der UI keinen Nutzen

# Nach dem Loslassen der PTT-Taste kommt das Endergebnis mit etwas Verzug.
# So lange gilt es weiterhin als Push-to-Talk und umgeht das Wake Word.
PTT_GRACE_SECONDS = 3.0


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
        self.hotkeys = HotkeyManager(self._on_hotkey)
        self.state = AppState()

        self._apps_cache: list[AppEntry] | None = None
        self._index_thread: threading.Thread | None = None
        self._speech_state = "idle"          # roher Zustand des Erkenners
        self._wake = WakeWordDetector(self.settings.wake_word)
        self._wake_armed_until = 0.0
        self._ptt_grace_until = 0.0
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
        self.apply_hotkeys()
        self._refresh_status()

        if self.state.app_count == 0 and self.settings.index_on_first_start:
            self.state.action_text = "Erster Start: ich suche installierte Programme ..."
            self.rebuild_index()

    def shutdown(self) -> None:
        self.hotkeys.stop()
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
        self._speech_state = "loading"
        self.speech.set_muted(self.state.muted)
        self.speech.start()
        self._refresh_status()

    def stop_listening(self) -> None:
        self.speech.stop()
        self.state.listening = False
        self.state.partial_text = ""
        self._speech_state = "idle"
        self._disarm_wake()
        self._refresh_status()

    # --- Stummschaltung ----------------------------------------------------
    def toggle_mute(self) -> None:
        self.set_muted(not self.state.muted)

    def set_muted(self, muted: bool) -> None:
        """Stumm heisst: kein Wake Word, kein Befehl, keine Verarbeitung."""
        if self.state.muted == muted:
            return
        self.state.muted = muted
        self.speech.set_muted(muted)
        self.state.level = 0.0
        self.state.partial_text = ""
        if muted:
            self._disarm_wake()
            self.state.wake_heard = ""
            self.state.action_ok = True
            self.state.action_text = "Mikrofon stummgeschaltet."
        else:
            self.state.action_text = "Mikrofon wieder aktiv."
        self._refresh_status()

    # --- Push-to-Talk ------------------------------------------------------
    def ptt_press(self) -> None:
        """PTT-Taste gedrueckt: zuhoeren, solange sie gehalten wird."""
        if self.state.muted:
            self.state.action_ok = False
            self.state.action_text = (
                "Mikrofon ist stummgeschaltet - Push-to-Talk wirkt nicht."
            )
            return
        self.state.ptt_active = True
        self._ptt_grace_until = 0.0
        self.state.wake_heard = ""
        if not self.speech.is_running:
            self.start_listening()
        self._refresh_status()

    def ptt_release(self) -> None:
        """PTT-Taste losgelassen: Aufnahme beenden und Befehl auswerten."""
        if not self.state.ptt_active:
            return
        self.state.ptt_active = False
        # Das Endergebnis kommt gleich aus dem Erkenner-Thread nach - bis
        # dahin gilt die Aeusserung weiterhin als Push-to-Talk.
        self._ptt_grace_until = time.monotonic() + PTT_GRACE_SECONDS
        self.stop_listening()

    # --- Wake Word ---------------------------------------------------------
    def _arm_wake(self) -> None:
        self.state.wake_armed = True
        self.state.wake_heard = ""
        self._wake_armed_until = time.monotonic() + max(self.settings.wake_word_timeout, 1.0)
        self.state.action_ok = True
        self.state.action_text = "Ich höre - sag jetzt deinen Befehl."
        self._refresh_status()

    def _disarm_wake(self) -> None:
        self.state.wake_armed = False
        self._wake_armed_until = 0.0

    def _expire_wake(self) -> bool:
        """Laeuft die Wartezeit nach dem Wake Word ab? Gibt True bei Aenderung."""
        if not self.state.wake_armed or not self._wake_armed_until:
            return False
        if time.monotonic() < self._wake_armed_until:
            return False
        self._disarm_wake()
        self.state.action_ok = True
        self.state.action_text = f"Kein Befehl gehört - sage wieder „{self.settings.wake_word}“."
        self._refresh_status()
        return True

    def _wake_bypassed(self) -> bool:
        """Push-to-Talk umgeht das Wake Word."""
        return self.state.ptt_active or time.monotonic() < self._ptt_grace_until

    # --- Globale Tastenkuerzel ---------------------------------------------
    def _on_hotkey(self, action: str, phase: str) -> None:
        """Aufruf aus dem Tastatur-Thread - nur in die Warteschlange legen."""
        self.bus.publish(EventType.HOTKEY, action=action, phase=phase)

    def apply_hotkeys(self) -> None:
        """Kuerzel aus den Einstellungen anmelden und Zustand uebernehmen."""
        settings = self.settings
        bindings: dict[str, str] = {ACTION_MUTE: settings.mute_hotkey}
        if settings.ptt_enabled:
            bindings[ACTION_PTT] = settings.ptt_hotkey

        status = self.hotkeys.apply(bindings, enabled=settings.hotkeys_enabled)
        self.state.hotkey_detail = status.detail
        self.state.hotkey_errors = list(status.errors)
        self.state.hotkeys_ok = status.ok

    # --- Einstellungen -----------------------------------------------------
    def update_settings(self, **changes) -> None:
        settings = self.settings_store.update(**changes)
        self._context.settings = settings
        touched = set(changes)

        # Erkennungsrelevante Aenderungen erfordern einen neuen Erkenner.
        if {"speech_engine", "language", "vosk_model_path", "whisper_model_size",
                "whisper_compute_type", "input_device"} & touched:
            self.speech.invalidate_engine()
            if self.speech.is_running:
                self.stop_listening()

        if "wake_word" in touched:
            self._wake = WakeWordDetector(settings.wake_word)
        if {"wake_word", "wake_word_enabled"} & touched:
            self._disarm_wake()
            self.state.wake_heard = ""

        if {"hotkeys_enabled", "mute_hotkey", "ptt_enabled", "ptt_hotkey"} & touched:
            self.apply_hotkeys()
            if "ptt_enabled" in touched and not settings.ptt_enabled and self.state.ptt_active:
                self.ptt_release()

        self.refresh_engines()
        self._refresh_status()

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
    def handle_text(self, text: str, *, bypass_wake: bool = False) -> None:
        """Erkannten Satz als Befehl auswerten.

        Bei aktivem Wake Word laeuft der Satz zuerst durch die Schleuse:
        ohne Wake Word passiert nichts, und das Wake Word selbst wird
        abgeschnitten, bevor der Befehl ausgewertet wird.
        """
        text = (text or "").strip()
        if not text:
            return

        # Doppelte Absicherung: stumm heisst stumm, egal woher der Text kam.
        if self.state.muted:
            return

        if self.settings.wake_word_enabled and not bypass_wake and not self._wake_bypassed():
            gated = self._pass_wake_gate(text)
            if gated is None:
                return
            text = gated

        self.state.recognized_text = text
        self.state.partial_text = ""
        self.state.wake_heard = ""

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

        # Nach einem ausgefuehrten Befehl ist wieder das Wake Word faellig -
        # ausser es steht noch eine Rueckfrage offen, die beantwortet werden
        # soll.
        if self.settings.wake_word_enabled:
            if result.needs_choice:
                self._arm_wake()      # Antwort darf ohne Wake Word kommen
            else:
                self._disarm_wake()
        self._refresh_status()

    def _pass_wake_gate(self, text: str) -> str | None:
        """Wake Word pruefen und abtrennen.

        Rueckgabe: der auszufuehrende Befehl, oder ``None``, wenn (noch)
        nichts auszufuehren ist.
        """
        match = self._wake.split(text)

        if not self.state.wake_armed:
            if match is None:
                # Ohne Wake Word wird nichts ausgefuehrt - was gehoert wurde,
                # zeigt die Startseite trotzdem an.
                self.state.wake_heard = text
                self.state.partial_text = ""
                return None
            if not match.has_command:
                self._arm_wake()
                return None
            self._disarm_wake()
            return match.command

        # Bereits scharf: ein erneut vorangestelltes Wake Word wird
        # abgeschnitten, damit es nie im Befehl landet.
        if match is not None:
            if not match.has_command:
                self._arm_wake()
                return None
            self._disarm_wake()
            return match.command

        self._disarm_wake()
        return text

    def _refresh_status(self) -> None:
        """Sichtbaren Zustand aus allen Einflussgroessen ableiten.

        Eine einzige Stelle statt verstreuter Zuweisungen - sonst
        widersprechen sich Stummschaltung, Wake Word und Erkennerzustand.
        """
        state = self.state
        if self._speech_state == "error":
            state.status = Status.ERROR
            return
        if state.muted:
            state.status = Status.MUTED
            state.status_detail = ""
            return
        if not state.listening:
            state.status = Status.IDLE
            state.status_detail = ""
            return
        if self._speech_state == "loading":
            state.status = Status.LOADING
            state.status_detail = ""
            return
        if self.settings.wake_word_enabled and not state.wake_armed and not state.ptt_active:
            state.status = Status.WAITING_WAKE
            state.status_detail = ""
            return
        state.status = Status.LISTENING
        state.status_detail = ""

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
        changed = False
        for event in self.bus.drain():
            self._handle_event(event)
            changed = True
        # Zeitablauf gehoert hierher: pump() laeuft im UI-Takt, damit
        # braucht es keinen eigenen Timer-Thread.
        if self._expire_wake():
            changed = True
        return changed

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

        elif event.type is EventType.HOTKEY:
            self._handle_hotkey(event.get("action", ""), event.get("phase", ""))

        elif event.type is EventType.ERROR:
            self.state.error = event.get("message", "")
            self.state.action_ok = False
            self.state.action_text = self.state.error

        elif event.type is EventType.NOTICE:
            self.state.action_text = event.get("message", "")

    def _handle_hotkey(self, action: str, phase: str) -> None:
        """Ein globales Tastenkuerzel wurde ausgeloest."""
        if action == ACTION_MUTE and phase == PRESS:
            self.toggle_mute()
        elif action == ACTION_PTT and phase == PRESS:
            self.ptt_press()
        elif action == ACTION_PTT and phase == RELEASE:
            self.ptt_release()

    def _on_speech_state(self, event: Event) -> None:
        """Rohzustand des Erkenners merken; die Anzeige wird abgeleitet."""
        state = event.get("state", "")
        if state == "muted":
            # Die Stummschaltung fuehrt die Anwendung selbst, der Erkenner
            # meldet sie nur zurueck.
            return
        self._speech_state = state
        self.state.listening = state in {"listening", "loading"}
        if state == "idle":
            self.state.level = 0.0
            self.state.ptt_active = False
        if state == "error":
            self.state.status_detail = event.get("detail", "")
        self._refresh_status()
