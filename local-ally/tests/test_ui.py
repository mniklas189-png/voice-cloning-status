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
        for name in ("MainWindow", "AppRow", "CandidateRow", "EngineRow"):
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


if __name__ == "__main__":
    unittest.main()
