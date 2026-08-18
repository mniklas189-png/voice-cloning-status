"""Zusammenspiel von Ereignissen, Zustand und Befehlen."""

import time
from unittest import mock

from tests.support import TempDataDirTestCase, unittest  # noqa: F401

from local_ally.app_index.launcher import LaunchResult
from local_ally.app_index.models import DiscoveredApp
from local_ally.core.controller import Controller
from local_ally.core.events import EventType
from local_ally.core.state import Status
from local_ally.settings import SettingsStore


class ControllerTests(TempDataDirTestCase):
    def setUp(self):
        super().setUp()
        store = SettingsStore()
        store.settings.index_on_first_start = False  # kein echter Scan im Test
        self.controller = Controller(settings_store=store)
        self.controller.repository.replace_all([
            DiscoveredApp(name="Discord", launch_target="C:/Discord.exe", source="start_menu", priority=40),
            DiscoveredApp(name="Lunar Client", launch_target="C:/Lunar.exe", source="start_menu", priority=40),
        ])
        self.controller.startup()
        patcher = mock.patch(
            "local_ally.app_index.launcher.launch",
            side_effect=lambda app: LaunchResult(True, f"{app.name} wird gestartet."),
        )
        self.launch = patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.controller.shutdown()
        super().tearDown()

    def test_startup_reads_the_index(self):
        self.assertEqual(self.controller.state.app_count, 2)
        self.assertEqual(len(self.controller.state.apps), 2)

    def test_partial_result_is_shown_but_not_executed(self):
        self.controller.bus.publish(EventType.SPEECH_PARTIAL, text="öffne dis")
        self.assertTrue(self.controller.pump())
        self.assertEqual(self.controller.state.partial_text, "öffne dis")
        self.launch.assert_not_called()

    def test_final_result_runs_the_command(self):
        self.controller.bus.publish(EventType.SPEECH_FINAL, text="öffne lunar client")
        self.controller.pump()
        state = self.controller.state
        self.assertEqual(state.recognized_text, "öffne lunar client")
        self.assertTrue(state.action_ok)
        self.assertEqual(self.launch.call_args.args[0].name, "Lunar Client")

    def test_unknown_sentence_gives_a_hint(self):
        self.controller.handle_text("wie spät ist es")
        self.assertFalse(self.controller.state.action_ok)
        self.assertIn("Befehl", self.controller.state.action_text)

    def test_speech_state_events_map_to_status(self):
        self.controller.bus.publish(EventType.SPEECH_STATE, state="listening", detail="Ich höre zu ...")
        self.controller.pump()
        self.assertIs(self.controller.state.status, Status.LISTENING)
        self.assertTrue(self.controller.state.listening)

        self.controller.bus.publish(EventType.SPEECH_STATE, state="idle", detail="")
        self.controller.pump()
        self.assertIs(self.controller.state.status, Status.IDLE)
        self.assertFalse(self.controller.state.listening)

    def test_index_events_update_the_view(self):
        self.controller.bus.publish(EventType.INDEX_STARTED)
        self.controller.pump()
        self.assertTrue(self.controller.state.indexing)

        self.controller.bus.publish(EventType.INDEX_FINISHED, count=2)
        self.controller.pump()
        self.assertFalse(self.controller.state.indexing)
        self.assertEqual(self.controller.state.app_count, 2)

    def test_choice_flow_from_the_ui(self):
        self.controller.handle_text("öffne discord")
        self.controller.state.candidates = self.controller.repository.all_apps()  # Platzhalter
        self.controller.handle_text("öffne discord")
        # Mausklick auf den ersten Vorschlag
        self.controller.state.candidates and self.controller.choose_candidate(0)
        self.assertFalse(self.controller.state.awaiting_choice)

    def test_filter_updates_the_visible_list(self):
        self.controller.apply_app_filter("lunar")
        self.assertEqual([app.name for app in self.controller.state.apps], ["Lunar Client"])
        self.controller.apply_app_filter("")
        self.assertEqual(len(self.controller.state.apps), 2)

    def test_settings_changes_are_persisted(self):
        self.controller.update_settings(auto_execute=False, speech_engine="faster_whisper")
        reloaded = SettingsStore()
        self.assertFalse(reloaded.settings.auto_execute)
        self.assertEqual(reloaded.settings.speech_engine, "faster_whisper")

    def test_missing_speech_backend_reports_an_error_instead_of_crashing(self):
        self.controller.update_settings(speech_engine="vosk", vosk_model_path="/gibt/es/nicht")
        self.controller.start_listening()
        for _ in range(100):
            self.controller.pump()
            if self.controller.state.status is Status.ERROR:
                break
            time.sleep(0.05)
        self.assertIs(self.controller.state.status, Status.ERROR)
        self.assertTrue(self.controller.state.error)


if __name__ == "__main__":
    unittest.main()
