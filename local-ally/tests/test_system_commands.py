"""PC-Steuerung im Zusammenspiel: Absicht, Rückfrage, Ausführung."""

from unittest import mock

from tests.fakes import FakeBackend
from tests.support import TempDataDirTestCase, unittest  # noqa: F401

from local_ally.app_index.launcher import LaunchResult
from local_ally.app_index.models import DiscoveredApp
from local_ally.core.controller import Controller
from local_ally.settings import SettingsStore


class SystemCommandTests(TempDataDirTestCase):
    def setUp(self):
        super().setUp()
        store = SettingsStore()
        store.settings.index_on_first_start = False
        store.settings.hotkeys_enabled = False
        self.backend = FakeBackend(processes=["explorer.exe", "Spotify.exe"])
        self.controller = Controller(settings_store=store, backend=self.backend)
        self.controller.repository.replace_all([
            DiscoveredApp(name="Discord", launch_target="C:/Discord/Discord.exe",
                          source="start_menu", priority=40),
            DiscoveredApp(name="Spotify", launch_target="C:/Spotify/Spotify.exe",
                          source="start_menu", priority=40),
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

    def say(self, sentence: str):
        self.controller.handle_text(sentence)
        return self.controller.state

    # --- Alltag ---------------------------------------------------------
    def test_volume_commands_reach_the_system(self):
        state = self.say("mach es lauter")
        self.assertTrue(state.action_ok)
        self.assertTrue(self.backend.called("volume_up"))

    def test_setting_a_volume_value(self):
        self.say("stell die lautstärke auf 60 prozent")
        self.assertEqual(self.backend.call("volume_set"), ("volume_set", 60))

    def test_folders_and_media(self):
        self.say("zeig mir meine downloads")
        self.assertTrue(self.backend.called("open_path"))
        self.say("nächster titel")
        self.assertEqual(self.backend.call("media"), ("media", "next"))

    def test_opening_a_program_still_works(self):
        state = self.say("öffne discord")
        self.assertTrue(state.action_ok)
        self.assertEqual(self.launch.call_args.args[0].name, "Discord")

    def test_an_ordinary_sentence_is_still_no_command(self):
        state = self.say("wie spät ist es")
        self.assertFalse(state.action_ok)
        self.assertIn("Befehl", state.action_text)

    # --- Rueckfrage bei kritischen Aktionen -----------------------------
    def test_shutdown_asks_first(self):
        state = self.say("fahr den pc herunter")
        self.assertTrue(state.awaiting_confirm)
        self.assertIn("wirklich", state.confirm_question)
        self.assertFalse(self.backend.called("shutdown"), "ohne Zustimmung ausgeführt")

    def test_yes_carries_the_action_out(self):
        self.say("fahr den pc herunter")
        state = self.say("ja")
        self.assertTrue(self.backend.called("shutdown"))
        self.assertFalse(state.awaiting_confirm)

    def test_no_discards_the_action(self):
        self.say("starte den pc neu")
        state = self.say("nein")
        self.assertFalse(self.backend.called("restart"))
        self.assertFalse(state.awaiting_confirm)
        self.assertIn("lasse", state.action_text.lower())

    def test_closing_a_program_asks_with_its_name(self):
        state = self.say("schließ spotify")
        self.assertTrue(state.awaiting_confirm)
        self.assertIn("spotify", state.confirm_question.lower())
        self.assertFalse(self.backend.called("close_process"))

        self.say("ja")
        self.assertEqual(self.backend.call("close_process"), ("close_process", "Spotify.exe"))

    def test_the_ui_buttons_confirm_and_decline(self):
        self.say("fahr den pc herunter")
        self.controller.confirm_pending()
        self.assertTrue(self.backend.called("shutdown"))

        self.backend.calls.clear()
        self.say("starte den pc neu")
        self.controller.decline_pending()
        self.assertFalse(self.backend.called("restart"))

    def test_confirmation_can_be_switched_off(self):
        self.controller.update_settings(confirm_critical=False)
        state = self.say("fahr den pc herunter")
        self.assertFalse(state.awaiting_confirm)
        self.assertTrue(self.backend.called("shutdown"))

    def test_a_new_command_replaces_an_open_question(self):
        self.say("fahr den pc herunter")
        self.say("mach es lauter")
        self.assertTrue(self.backend.called("volume_up"))
        self.assertFalse(self.backend.called("shutdown"))

    def test_uncritical_actions_run_immediately(self):
        state = self.say("sperr den pc")
        self.assertFalse(state.awaiting_confirm)
        self.assertTrue(self.backend.called("lock"))

    # --- Zusammenspiel mit Wake Word und Stummschaltung -----------------
    def test_the_answer_needs_no_wake_word(self):
        self.controller.update_settings(wake_word_enabled=True)
        self.say("hey ally fahr den pc herunter")
        self.assertTrue(self.controller.state.awaiting_confirm)
        self.say("ja")           # ohne erneutes Wake Word
        self.assertTrue(self.backend.called("shutdown"))

    def test_system_commands_need_the_wake_word_too(self):
        self.controller.update_settings(wake_word_enabled=True)
        self.say("mach es lauter")
        self.assertFalse(self.backend.called("volume_up"))
        self.say("hey ally mach es lauter")
        self.assertTrue(self.backend.called("volume_up"))

    def test_muted_blocks_system_commands(self):
        self.controller.set_muted(True)
        self.say("fahr den pc herunter")
        self.assertFalse(self.controller.state.awaiting_confirm)
        self.assertFalse(self.backend.called("shutdown"))

    def test_the_microphone_command_mutes_the_assistant(self):
        self.say("mach mein mikro aus")
        self.assertTrue(self.controller.state.muted)
        self.controller.set_muted(False)
        self.assertFalse(self.controller.state.muted)


if __name__ == "__main__":
    unittest.main()
