"""Die Slint-Oberflaeche und ihre Bruecke zu Python.

Diese Tests brauchen das Paket ``slint``. Fehlt es, werden sie
uebersprungen - der Rest der Testsuite laeuft ohne jede Abhaengigkeit.

Sie oeffnen bewusst kein Fenster: geprueft werden nur das Uebersetzen der
.slint-Dateien und das Uebertragen des Zustands. Genau dort entstehen die
Fehler, die man sonst erst beim Start bemerkt.
"""

from tests.support import TempDataDirTestCase, unittest  # noqa: F401

try:
    import slint  # noqa: F401

    SLINT_AVAILABLE = True
except Exception:  # pragma: no cover - haengt von der Installation ab
    SLINT_AVAILABLE = False


@unittest.skipUnless(SLINT_AVAILABLE, "Paket 'slint' ist nicht installiert")
class UiTests(TempDataDirTestCase):
    def test_ui_compiles_and_exposes_the_expected_api(self):
        from local_ally.ui.bridge import _UI_FILE

        module = slint.load_file(str(_UI_FILE))
        for name in ("MainWindow", "AppRow", "CandidateRow", "CustomRow",
                     "CustomForm", "EngineRow"):
            self.assertTrue(hasattr(module, name), f"{name} fehlt in der UI")

    def test_bridge_transfers_the_state(self):
        from local_ally.app_index.models import DiscoveredApp
        from local_ally.core.controller import Controller
        from local_ally.settings import SettingsStore
        from local_ally.ui.bridge import UiBridge

        store = SettingsStore()
        store.settings.index_on_first_start = False
        controller = Controller(settings_store=store)
        try:
            controller.repository.replace_all([
                DiscoveredApp(
                    name="Lunar Client",
                    launch_target="C:/Lunar.exe",
                    source="start_menu",
                    priority=40,
                )
            ])
            controller.startup()
            controller.handle_text("wie spät ist es")

            bridge = UiBridge(controller)
            bridge.render()

            ui_store = bridge.window.Store
            self.assertEqual(ui_store.app_count, 1)
            self.assertEqual(len(ui_store.apps), 1)
            self.assertEqual(ui_store.apps[0].name, "Lunar Client")
            self.assertEqual(ui_store.status, "idle")
            self.assertFalse(ui_store.action_ok)
            self.assertTrue(len(ui_store.engines) >= 2)
            self.assertEqual(ui_store.engine_id, "vosk")
            self.assertTrue(len(ui_store.input_devices) >= 1)
        finally:
            controller.shutdown()

    def test_ui_actions_reach_the_controller(self):
        from local_ally.core.controller import Controller
        from local_ally.settings import SettingsStore
        from local_ally.ui.bridge import UiBridge

        store = SettingsStore()
        store.settings.index_on_first_start = False
        controller = Controller(settings_store=store)
        try:
            bridge = UiBridge(controller)
            bridge.render()
            # Auswahl eines anderen Erkenners ueber die Oberflaeche
            bridge.window.Actions.select_engine("faster-whisper")
            self.assertEqual(controller.settings.speech_engine, "faster_whisper")
            self.assertEqual(bridge.window.Store.engine_id, "faster_whisper")
            bridge.window.Actions.set_auto_execute(False)
            self.assertFalse(controller.settings.auto_execute)
        finally:
            controller.shutdown()

    def test_activation_controls_reach_the_controller(self):
        from local_ally.core.controller import Controller
        from local_ally.settings import SettingsStore
        from local_ally.ui.bridge import UiBridge

        store = SettingsStore()
        store.settings.index_on_first_start = False
        store.settings.hotkeys_enabled = False
        controller = Controller(settings_store=store)
        try:
            bridge = UiBridge(controller)
            bridge.render()
            ui_store = bridge.window.Store

            self.assertFalse(ui_store.wake_enabled)
            self.assertEqual(ui_store.wake_word, "Hey Ally")

            bridge.window.Actions.set_wake_enabled(True)
            bridge.window.Actions.set_wake_word("Computer")
            self.assertTrue(controller.settings.wake_word_enabled)
            self.assertEqual(controller.settings.wake_word, "Computer")
            self.assertEqual(ui_store.wake_word, "Computer")

            bridge.window.Actions.toggle_mute()
            self.assertTrue(controller.state.muted)
            self.assertTrue(ui_store.muted)
            self.assertEqual(ui_store.status, "muted")

            bridge.window.Actions.toggle_mute()
            self.assertFalse(ui_store.muted)
        finally:
            controller.shutdown()

    def test_hotkeys_are_shown_readable_and_errors_surface(self):
        from local_ally.core.controller import Controller
        from local_ally.settings import SettingsStore
        from local_ally.ui.bridge import UiBridge

        store = SettingsStore()
        store.settings.index_on_first_start = False
        controller = Controller(settings_store=store)
        try:
            bridge = UiBridge(controller)
            bridge.render()
            ui_store = bridge.window.Store

            # Eingabe wird vereinheitlicht und lesbar angezeigt
            bridge.window.Actions.set_mute_hotkey("STRG + ALT + M")
            self.assertEqual(controller.settings.mute_hotkey, "ctrl+alt+m")
            self.assertEqual(ui_store.mute_hotkey, "Strg + Alt + M")

            # Fehleingabe bleibt stehen und wird erklärt
            bridge.window.Actions.set_mute_hotkey("m")
            self.assertEqual(ui_store.mute_hotkey, "m")
            self.assertIn("Strg", ui_store.hotkey_error)
            self.assertFalse(ui_store.hotkeys_ok)

            # Kollision wird gemeldet
            bridge.window.Actions.set_mute_hotkey("ctrl+alt+m")
            bridge.window.Actions.set_ptt_enabled(True)
            bridge.window.Actions.set_ptt_hotkey("ctrl+alt+m")
            self.assertIn("mehrfach vergeben", ui_store.hotkey_error)
        finally:
            controller.shutdown()

    def test_confirmation_is_shown_and_answered_from_the_ui(self):
        from tests.fakes import FakeBackend

        from local_ally.core.controller import Controller
        from local_ally.settings import SettingsStore
        from local_ally.ui.bridge import UiBridge

        store = SettingsStore()
        store.settings.index_on_first_start = False
        store.settings.hotkeys_enabled = False
        backend = FakeBackend()
        controller = Controller(settings_store=store, backend=backend)
        try:
            bridge = UiBridge(controller)
            controller.handle_text("fahr den pc herunter")
            bridge.render()

            ui_store = bridge.window.Store
            self.assertTrue(ui_store.awaiting_confirm)
            self.assertIn("wirklich", ui_store.action_text)
            self.assertFalse(backend.called("shutdown"))

            bridge.window.Actions.confirm_pending()
            self.assertTrue(backend.called("shutdown"))
            self.assertFalse(ui_store.awaiting_confirm)

            # und der Schalter wirkt sofort
            bridge.window.Actions.set_confirm_critical(False)
            self.assertFalse(controller.settings.confirm_critical)
        finally:
            controller.shutdown()

    def test_theme_switch_reaches_the_ui(self):
        from local_ally.core.controller import Controller
        from local_ally.settings import SettingsStore
        from local_ally.ui.bridge import UiBridge

        store = SettingsStore()
        store.settings.index_on_first_start = False
        controller = Controller(settings_store=store)
        try:
            bridge = UiBridge(controller)
            bridge.render()
            self.assertTrue(bridge.window.Theme.dark, "Vorgabe ist das dunkle Schema")

            bridge.window.Actions.select_theme("light")
            self.assertEqual(controller.settings.theme, "light")
            self.assertFalse(bridge.window.Theme.dark)
            # und die Einstellung ueberlebt einen Neustart
            self.assertEqual(SettingsStore().settings.theme, "light")

            bridge.window.Actions.select_theme("dark")
            self.assertTrue(bridge.window.Theme.dark)
        finally:
            controller.shutdown()


    def test_custom_functions_can_be_managed_from_the_ui(self):
        from unittest import mock

        from tests.fakes import FakeBackend

        from local_ally.app_index.launcher import LaunchResult
        from local_ally.app_index.models import DiscoveredApp
        from local_ally.core.controller import Controller
        from local_ally.settings import SettingsStore
        from local_ally.ui.bridge import UiBridge

        store = SettingsStore()
        store.settings.index_on_first_start = False
        store.settings.hotkeys_enabled = False
        controller = Controller(settings_store=store, backend=FakeBackend())
        try:
            controller.repository.replace_all([
                DiscoveredApp(name="Anki", launch_target="C:/anki.exe",
                              source="start_menu", priority=40),
            ])
            controller.startup()
            bridge = UiBridge(controller)
            bridge.render()
            ui_store = bridge.window.Store
            actions = bridge.window.Actions

            # Die Aktionsarten stehen zur Auswahl bereit ...
            self.assertIn("App", list(ui_store.custom_actions))
            self.assertIn("Website", list(ui_store.custom_actions))
            self.assertIn("CMD", list(ui_store.custom_actions))
            # ... und das Formular ist genau einmal vorhanden.
            self.assertEqual(len(ui_store.custom_form), 1)
            self.assertTrue(ui_store.custom_form[0].picks_app)

            # Das Beispiel aus der Anforderung: "lernen" oeffnet Anki.
            actions.custom_set_phrase("lernen")
            actions.custom_set_target("Ank")
            self.assertIn("Anki", list(ui_store.custom_app_matches))
            actions.custom_pick_app("Anki")
            self.assertEqual(ui_store.custom_form[0].target, "Anki")
            actions.custom_save()

            self.assertEqual(len(ui_store.custom_commands), 1)
            self.assertEqual(ui_store.custom_commands[0].phrase, "lernen")
            self.assertEqual(ui_store.custom_commands[0].action_short, "App")
            self.assertIn("gespeichert", ui_store.custom_hint)

            with mock.patch(
                "local_ally.app_index.launcher.launch",
                side_effect=lambda app: LaunchResult(True, f"{app.name} startet."),
            ) as launch:
                controller.handle_text("lernen", bypass_wake=True)
            self.assertEqual(launch.call_args.args[0].name, "Anki")

            # Aktionswechsel tauscht das Konfigurationsfeld aus.
            actions.custom_select_action("Website")
            self.assertEqual(ui_store.custom_form[0].config_label, "Adresse")
            self.assertFalse(ui_store.custom_form[0].picks_app)
            self.assertEqual(ui_store.custom_form[0].target, "")

            # Fehleingaben werden erklaert, statt still zu scheitern.
            actions.custom_set_phrase("videos")
            actions.custom_set_target("kein url")
            actions.custom_save()
            self.assertIn("Leerzeichen", ui_store.custom_error)
            self.assertEqual(len(ui_store.custom_commands), 1)

            # Bearbeiten, ausschalten, loeschen
            saved_id = ui_store.custom_commands[0].id
            actions.custom_edit(saved_id)
            self.assertEqual(ui_store.custom_form[0].phrase, "lernen")
            actions.custom_set_enabled(saved_id, False)
            self.assertFalse(ui_store.custom_commands[0].enabled)
            actions.custom_delete(saved_id)
            self.assertEqual(len(ui_store.custom_commands), 0)
        finally:
            controller.shutdown()


    def test_lists_survive_a_garbage_collection(self):
        """Regression: Slint haelt Listenmodelle nur schwach.

        Ohne eigene Referenz in der Bruecke raeumte die Speicherbereinigung
        sie weg - im laufenden Programm waren dann ploetzlich Programmliste,
        Erkennerliste und Vorschlaege leer.
        """
        import gc

        from local_ally.app_index.models import DiscoveredApp
        from local_ally.core.controller import Controller
        from local_ally.settings import SettingsStore
        from local_ally.ui.bridge import UiBridge

        store = SettingsStore()
        store.settings.index_on_first_start = False
        store.settings.hotkeys_enabled = False
        controller = Controller(settings_store=store)
        try:
            controller.repository.replace_all([
                DiscoveredApp(name="Anki", launch_target="C:/anki.exe",
                              source="start_menu", priority=40),
            ])
            controller.startup()
            bridge = UiBridge(controller)
            bridge.render()
            ui_store = bridge.window.Store

            self.assertEqual(len(ui_store.apps), 1)
            gc.collect()

            self.assertEqual(len(ui_store.apps), 1)
            self.assertTrue(len(ui_store.engines) >= 2)
            self.assertTrue(len(ui_store.input_devices) >= 1)
            self.assertEqual(len(ui_store.custom_form), 1)
            self.assertTrue(len(ui_store.custom_actions) >= 3)
        finally:
            controller.shutdown()


if __name__ == "__main__":
    unittest.main()
