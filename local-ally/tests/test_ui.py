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
            self.assertTrue(len(ui_store.engine_names) >= 2)
            self.assertEqual(ui_store.engine_value, "Vosk")
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
            self.assertEqual(bridge.window.Store.engine_value, "faster-whisper")
            bridge.window.Actions.set_auto_execute(False)
            self.assertFalse(controller.settings.auto_execute)
        finally:
            controller.shutdown()


if __name__ == "__main__":
    unittest.main()
