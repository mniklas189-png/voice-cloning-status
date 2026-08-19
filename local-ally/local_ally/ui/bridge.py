"""Bruecke zwischen Slint-Oberflaeche und :class:`~local_ally.core.controller.Controller`.

Das ist das einzige Modul, das Slint kennt. Es tut genau zwei Dinge:

1. Es verbindet die Callbacks aus ``Actions`` mit Methoden des Controllers.
2. Es kopiert den Zustand des Controllers in die Slint-Eigenschaften.

Der Takt kommt von einem ``slint.Timer``: er leert regelmaessig die
Ereigniswarteschlange der Hintergrundthreads (siehe
:mod:`local_ally.core.events`) und zeichnet bei Aenderungen neu. So beruehrt
kein Hintergrundthread jemals ein Slint-Objekt.
"""

from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path

import slint

from .. import __version__
from ..core.controller import Controller
from ..custom.models import ACTION_TYPES, action_type
from ..hotkeys import Hotkey
from ..speech.engines.whisper_engine import MODEL_SIZES
from .store import UiStore

log = logging.getLogger(__name__)

_UI_FILE = Path(__file__).parent / "slint" / "app-window.slint"
_TICK = dt.timedelta(milliseconds=60)
_DEFAULT_DEVICE_LABEL = "Standardmikrofon (System)"

# Sprechende Namen fuer die Quellen im Index
SOURCE_LABELS = {
    "start_apps": "Startmenü (Windows)",
    "start_menu": "Startmenü-Verknüpfung",
    "registry_app_paths": "Registry (App Paths)",
    "registry_uninstall": "Registry (Programme)",
    "path": "Suchpfad (PATH)",
    "desktop_entry": "Desktop-Datei",
}


class UiBridge:
    def __init__(self, controller: Controller) -> None:
        self.controller = controller
        # Ohne Stilvorgabe: die Oberflaeche bringt ihre Bedienelemente selbst
        # mit. Der Stil der Standard-Widgets steht beim Uebersetzen fest und
        # liesse sich zur Laufzeit nicht zwischen hell und dunkel umschalten.
        self.ui = slint.load_file(str(_UI_FILE))
        self.window = self.ui.MainWindow()
        # Alle Schreibzugriffe laufen ueber diese Huelle - sie haelt die
        # Listenmodelle fest und faengt unbekannte Namen ab. Siehe ui/store.py.
        self.store = UiStore(self.window.Store)
        self._timer = slint.Timer()
        self._apps_revision = -1
        self._candidates_revision = -1
        self._engines_signature: tuple | None = None
        self._custom_revision = -1
        self._custom_form_revision = -1
        self._custom_matches_revision = -1
        self._device_labels: list[str] | None = None
        self._timer_labels: list[str] | None = None
        self._connect()

    # --- Aufbau ------------------------------------------------------------
    def _connect(self) -> None:
        actions = self.window.Actions
        controller = self.controller

        actions.toggle_listening = self._wrap(controller.toggle_listening)
        actions.rebuild_index = self._wrap(controller.rebuild_index)
        actions.filter_apps = self._wrap(controller.apply_app_filter)
        actions.launch_app = self._wrap(lambda app_id: controller.launch_app_id(int(app_id)))
        actions.choose_candidate = self._wrap(lambda index: controller.choose_candidate(int(index)))
        actions.dismiss_candidates = self._wrap(controller.clear_candidates)
        actions.select_engine = self._wrap(self._on_select_engine)
        actions.select_whisper_size = self._wrap(self._on_select_whisper_size)
        actions.select_input_device = self._wrap(self._on_select_device)
        actions.confirm_pending = self._wrap(controller.confirm_pending)
        actions.decline_pending = self._wrap(controller.decline_pending)
        actions.set_confirm_critical = self._wrap(
            lambda value: controller.update_settings(confirm_critical=bool(value))
        )
        actions.toggle_mute = self._wrap(controller.toggle_mute)
        actions.set_wake_enabled = self._wrap(
            lambda value: controller.update_settings(wake_word_enabled=bool(value))
        )
        actions.set_wake_word = self._wrap(
            lambda value: controller.update_settings(wake_word=str(value).strip())
        )
        actions.set_ptt_enabled = self._wrap(
            lambda value: controller.update_settings(ptt_enabled=bool(value))
        )
        actions.set_hotkeys_enabled = self._wrap(
            lambda value: controller.update_settings(hotkeys_enabled=bool(value))
        )
        actions.set_mute_hotkey = self._wrap(
            lambda value: controller.update_settings(mute_hotkey=_clean_hotkey(value))
        )
        actions.set_ptt_hotkey = self._wrap(
            lambda value: controller.update_settings(ptt_hotkey=_clean_hotkey(value))
        )
        actions.select_theme = self._wrap(
            lambda value: controller.update_settings(theme=str(value))
        )
        actions.set_vosk_model_path = self._wrap(
            lambda value: controller.update_settings(vosk_model_path=str(value).strip())
        )
        actions.set_auto_execute = self._wrap(
            lambda value: controller.update_settings(auto_execute=bool(value))
        )
        actions.set_include_path = self._wrap(
            lambda value: controller.update_settings(include_path_executables=bool(value))
        )

        # Eigene Funktionen
        actions.custom_new = self._wrap(controller.custom_new)
        actions.custom_edit = self._wrap(lambda cid: controller.custom_edit(int(cid)))
        actions.custom_delete = self._wrap(lambda cid: controller.custom_delete(int(cid)))
        actions.custom_run = self._wrap(lambda cid: controller.custom_run(int(cid)))
        actions.custom_set_enabled = self._wrap(
            lambda cid, value: controller.custom_set_enabled(int(cid), bool(value))
        )
        actions.custom_set_phrase = self._wrap(
            lambda value: controller.custom_set_phrase(str(value))
        )
        actions.custom_select_action = self._wrap(self._on_select_custom_action)
        actions.custom_set_target = self._wrap(self._on_custom_target)
        actions.custom_pick_app = self._wrap(
            lambda value: controller.custom_pick_app(str(value))
        )
        actions.custom_save = self._wrap(controller.custom_save)

    def _wrap(self, handler):
        """Nach jeder Nutzeraktion sofort neu zeichnen.

        Ohne das wuerde die Oberflaeche erst beim naechsten Timer-Takt mit
        Ereignis reagieren - Klicks fuehlten sich dann traege an.
        """

        def invoke(*args):
            # Eine Ausnahme, die bis in den Slint-Timer bzw. das Callback
            # zurueckschlaegt, beendet das Programm hart (Rust-Panic).
            # Deshalb faengt die Bruecke hier alles ab.
            try:
                handler(*args)
            except Exception:
                log.exception("Aktion fehlgeschlagen")
            try:
                self.render()
            except Exception:
                log.exception("Oberflaeche konnte nicht aktualisiert werden")

        return invoke

    def _on_select_engine(self, display_name) -> None:
        for info in self.controller.state.engines:
            if info.display_name == str(display_name):
                self.controller.update_settings(speech_engine=info.id)
                return

    def _on_select_whisper_size(self, size) -> None:
        if str(size) in MODEL_SIZES:
            self.controller.update_settings(whisper_model_size=str(size))

    def _on_select_custom_action(self, short_label) -> None:
        """Die Oberflaeche waehlt ueber den Kurznamen - hier wird er zur Id."""
        for entry in ACTION_TYPES:
            if entry.short_label == str(short_label):
                self.controller.custom_set_action(entry.id)
                return

    def _on_custom_target(self, value) -> None:
        """Ziel uebernehmen - bei der Programmauswahl zugleich Vorschlaege suchen."""
        text = str(value)
        self.controller.custom_set_target(text)
        if action_type(self.controller.state.custom_action).picks_app:
            self.controller.custom_search_apps(text)

    def _on_select_device(self, label) -> None:
        # Der erste Eintrag steht fuer "Standardgeraet des Systems" und wird
        # als leerer Wert gespeichert.
        name = "" if str(label) == _DEFAULT_DEVICE_LABEL else str(label)
        self.controller.update_settings(input_device=name)

    # --- Ablauf ------------------------------------------------------------
    def run(self) -> None:
        self.controller.startup()
        self.render()
        self._timer.start(slint.TimerMode.Repeated, _TICK, self._tick)
        self.window.show()
        self.window.run()

    def _tick(self) -> None:
        # Siehe _wrap: im Timer-Callback darf niemals eine Ausnahme entkommen.
        try:
            if self.controller.pump():
                self.render()
        except Exception:
            log.exception("Fehler beim Verarbeiten von Ereignissen")

    # --- Zustand -> UI -----------------------------------------------------
    def render(self) -> None:
        state = self.controller.state
        settings = self.controller.settings
        store = self.store

        # Farbschema zuerst: alle uebrigen Farben haengen davon ab.
        self.window.Theme.dark = settings.theme != "light"

        store.version = __version__
        store.status = state.status.value
        store.status_label = state.status_label
        store.listening = state.listening
        store.level = float(state.level)
        store.partial_text = state.partial_text
        store.recognized_text = state.recognized_text
        store.action_text = state.action_text
        store.action_ok = state.action_ok
        store.awaiting_choice = state.awaiting_choice
        store.awaiting_confirm = state.awaiting_confirm
        store.confirm_critical = settings.confirm_critical
        store.error = state.error

        # Nur bei echter Aenderung neu bauen - die Restzeit springt
        # sekundenweise, nicht im UI-Takt.
        if state.timers != self._timer_labels:
            self._timer_labels = list(state.timers)
            store.timers = list(state.timers)

        store.app_count = state.app_count
        store.indexing = state.indexing
        store.index_detail = state.index_detail
        store.last_index = _format_timestamp(state.last_index)

        store.muted = state.muted
        store.wake_enabled = settings.wake_word_enabled
        store.wake_word = settings.wake_word
        store.wake_armed = state.wake_armed
        store.wake_heard = state.wake_heard
        store.ptt_enabled = settings.ptt_enabled
        store.ptt_active = state.ptt_active
        store.hotkeys_enabled = settings.hotkeys_enabled
        store.mute_hotkey = _display_hotkey(settings.mute_hotkey)
        store.ptt_hotkey = _display_hotkey(settings.ptt_hotkey)
        store.hotkey_detail = state.hotkey_detail
        store.hotkey_error = " ".join(state.hotkey_errors)
        store.hotkeys_ok = state.hotkeys_ok

        store.auto_execute = settings.auto_execute
        store.include_path = settings.include_path_executables
        store.vosk_model_path = settings.vosk_model_path
        store.whisper_value = settings.whisper_model_size

        self._render_engines(state, settings)
        self._render_devices(state, settings)
        self._render_custom(state)

        if state.apps_revision != self._apps_revision:
            self._apps_revision = state.apps_revision
            store.apps = [
                self.ui.AppRow(
                    id=app.id,
                    name=app.name,
                    detail=app.launch_target,
                    source=SOURCE_LABELS.get(app.source, app.source),
                    aliases=", ".join(app.aliases[:4]),
                )
                for app in state.apps
            ]

        if state.candidates_revision != self._candidates_revision:
            self._candidates_revision = state.candidates_revision
            store.candidates = [
                self.ui.CandidateRow(
                    index=position,
                    name=match.app.name,
                    detail=match.app.launch_target,
                    score=f"{min(match.score, 1.0) * 100:.0f} %",
                    reason=match.reason,
                )
                for position, match in enumerate(state.candidates, start=1)
            ]

    def _render_custom(self, state) -> None:
        """Eigene Funktionen in die Oberflaeche kopieren.

        Das Formular wird nur bei einem *Wechsel* neu gebaut (siehe
        ``custom_form_revision``): ein Neubau bei jedem Tastendruck wuerde
        die Schreibmarke zuruecksetzen.
        """
        store = self.store
        store.custom_error = state.custom_error
        store.custom_hint = state.custom_hint

        if self._custom_revision < 0:
            store.custom_actions = [entry.short_label for entry in ACTION_TYPES]

        if state.custom_revision != self._custom_revision:
            self._custom_revision = state.custom_revision
            store.custom_commands = [
                self.ui.CustomRow(
                    id=command.id,
                    phrase=command.phrase,
                    action=command.action,
                    action_label=action_type(command.action).label,
                    action_short=action_type(command.action).short_label,
                    target=command.target,
                    enabled=command.enabled,
                    uses=f"{command.use_count} ×" if command.use_count else "",
                )
                for command in state.custom_commands
            ]

        if state.custom_form_revision != self._custom_form_revision:
            self._custom_form_revision = state.custom_form_revision
            kind = action_type(state.custom_action)
            store.custom_form = [
                self.ui.CustomForm(
                    edit_id=state.custom_edit_id,
                    phrase=state.custom_phrase,
                    action=kind.id,
                    action_short=kind.short_label,
                    config_label=kind.config_label,
                    placeholder=kind.placeholder,
                    hint=kind.hint,
                    picks_app=kind.picks_app,
                    target=state.custom_target,
                )
            ]

        if state.custom_matches_revision != self._custom_matches_revision:
            self._custom_matches_revision = state.custom_matches_revision
            store.custom_app_matches = [app.name for app in state.custom_app_matches]

    def _render_engines(self, state, settings) -> None:
        signature = tuple(
            (info.id, info.display_name, info.available, info.detail) for info in state.engines
        )
        store = self.store
        if signature != self._engines_signature:
            self._engines_signature = signature
            store.engines = [
                self.ui.EngineRow(
                    id=info.id,
                    name=info.display_name,
                    description=info.description,
                    available=info.available,
                    detail=info.detail,
                )
                for info in state.engines
            ]
        store.engine_id = settings.speech_engine

    def _render_devices(self, state, settings) -> None:
        store = self.store
        labels = [_DEFAULT_DEVICE_LABEL, *state.input_devices]
        # Nur bei echter Aenderung ein neues Listenmodell: render() laeuft im
        # UI-Takt, und ein Neubau wuerde die Auswahl jedes Mal zuruecksetzen.
        if labels != self._device_labels:
            self._device_labels = labels
            store.input_devices = labels
        store.input_device_value = settings.input_device or _DEFAULT_DEVICE_LABEL


def _clean_hotkey(value) -> str:
    """Eingabe vereinheitlichen, Fehleingaben aber unveraendert lassen.

    Nur so sieht der Nutzer in der Oberflaeche noch, was er getippt hat -
    zusammen mit der Meldung, was daran nicht stimmt.
    """
    text = str(value).strip()
    hotkey = Hotkey.parse_or_none(text)
    return hotkey.normalized() if hotkey else text


def _display_hotkey(value: str) -> str:
    """Lesbare Schreibweise fuer die Oberflaeche, z.B. ``Strg + Alt + M``."""
    hotkey = Hotkey.parse_or_none(value)
    return hotkey.display() if hotkey else value


def _format_timestamp(value: str) -> str:
    """ISO-Zeitstempel (UTC) in lokale Zeit umwandeln."""
    if not value:
        return ""
    try:
        moment = dt.datetime.fromisoformat(value)
    except ValueError:
        return value
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.timezone.utc)
    return moment.astimezone().strftime("%d.%m.%Y %H:%M")


def run_ui(controller: Controller | None = None) -> None:
    """Startet die Oberflaeche und blockiert bis zum Schliessen des Fensters."""
    owned = controller is None
    controller = controller or Controller()
    bridge = UiBridge(controller)
    try:
        bridge.run()
    finally:
        if owned:
            controller.shutdown()
