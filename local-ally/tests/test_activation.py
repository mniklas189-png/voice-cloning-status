"""Aktivierung: Wake Word, Stummschaltung und Push-to-Talk im Zusammenspiel."""

import time
from unittest import mock

from tests.support import TempDataDirTestCase, unittest  # noqa: F401

from local_ally.app_index.launcher import LaunchResult
from local_ally.app_index.models import DiscoveredApp
from local_ally.core.controller import Controller
from local_ally.core.events import EventType
from local_ally.core.state import Status
from local_ally.hotkeys import ACTION_MUTE, ACTION_PTT, PRESS, RELEASE
from local_ally.settings import SettingsStore


class ActivationTests(TempDataDirTestCase):
    def setUp(self):
        super().setUp()
        store = SettingsStore()
        store.settings.index_on_first_start = False
        store.settings.hotkeys_enabled = False   # kein echter Tastatur-Zuhörer im Test
        self.controller = Controller(settings_store=store)
        self.controller.repository.replace_all([
            DiscoveredApp(name="Discord", launch_target="C:/Discord.exe",
                          source="start_menu", priority=40),
            DiscoveredApp(name="Lunar Client", launch_target="C:/Lunar.exe",
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

    def enable_wake(self, phrase="Hey Ally", timeout=8.0):
        self.controller.update_settings(
            wake_word_enabled=True, wake_word=phrase, wake_word_timeout=timeout
        )

    def launched(self):
        return None if not self.launch.called else self.launch.call_args.args[0].name

    # --- Wake Word ------------------------------------------------------
    def test_without_wake_word_commands_run_directly(self):
        self.controller.handle_text("öffne discord")
        self.assertEqual(self.launched(), "Discord")

    def test_with_wake_word_a_bare_command_is_ignored(self):
        self.enable_wake()
        self.controller.handle_text("öffne discord")
        self.launch.assert_not_called()
        self.assertEqual(self.controller.state.wake_heard, "öffne discord")

    def test_wake_word_and_command_in_one_utterance(self):
        self.enable_wake()
        self.controller.handle_text("hey ally öffne discord")
        self.assertEqual(self.launched(), "Discord")

    def test_wake_word_alone_arms_and_the_next_sentence_runs(self):
        self.enable_wake()
        self.controller.handle_text("hey ally")
        self.assertTrue(self.controller.state.wake_armed)
        self.launch.assert_not_called()

        self.controller.handle_text("öffne lunar client")
        self.assertEqual(self.launched(), "Lunar Client")

    def test_after_a_command_the_wake_word_is_required_again(self):
        self.enable_wake()
        self.controller.handle_text("hey ally öffne discord")
        self.assertFalse(self.controller.state.wake_armed)
        self.launch.reset_mock()
        self.controller.handle_text("öffne lunar client")
        self.launch.assert_not_called()

    def test_the_wake_word_never_reaches_the_command(self):
        self.enable_wake()
        self.controller.handle_text("hey ally öffne discord")
        self.assertEqual(self.controller.state.recognized_text, "oeffne discord")
        self.assertNotIn("ally", self.controller.state.recognized_text)

    def test_arming_expires_after_the_timeout(self):
        self.enable_wake(timeout=1.0)
        self.controller.handle_text("hey ally")
        self.assertTrue(self.controller.state.wake_armed)

        self.controller._wake_armed_until = time.monotonic() - 0.01   # Zeit vorspulen
        self.assertTrue(self.controller.pump())
        self.assertFalse(self.controller.state.wake_armed)

        self.controller.handle_text("öffne discord")
        self.launch.assert_not_called()

    def test_a_question_may_be_answered_without_the_wake_word(self):
        self.controller.repository.replace_all([
            DiscoveredApp(name="Grafik Tool A", launch_target="C:/A.exe",
                          source="start_menu", priority=40),
            DiscoveredApp(name="Grafik Tool B", launch_target="C:/B.exe",
                          source="start_menu", priority=40),
        ])
        self.controller.refresh_apps()
        self.enable_wake()
        self.controller.handle_text("hey ally öffne grafik tool")
        self.assertTrue(self.controller.state.awaiting_choice)
        self.controller.handle_text("zwei")           # ohne erneutes Wake Word
        self.assertIsNotNone(self.launched())

    def test_custom_wake_word_is_applied_immediately(self):
        self.enable_wake(phrase="Computer")
        self.controller.handle_text("hey ally öffne discord")
        self.launch.assert_not_called()
        self.controller.handle_text("computer öffne discord")
        self.assertEqual(self.launched(), "Discord")

    def test_both_engine_writing_styles_pass_the_gate(self):
        self.enable_wake()
        # Vosk: klein, ohne Satzzeichen
        self.controller.handle_text("hey ally öffne discord")
        self.assertEqual(self.launched(), "Discord")
        self.launch.reset_mock()
        # faster-whisper: Grossschreibung und Satzzeichen
        self.controller.handle_text("Hey Ally, öffne Lunar Client.")
        self.assertEqual(self.launched(), "Lunar Client")

    # --- Stummschaltung -------------------------------------------------
    def test_muted_blocks_commands_and_wake_words(self):
        self.controller.set_muted(True)
        self.controller.handle_text("öffne discord")
        self.launch.assert_not_called()

        self.enable_wake()
        self.controller.handle_text("hey ally öffne discord")
        self.launch.assert_not_called()
        self.assertFalse(self.controller.state.wake_armed)

    def test_mute_is_visible_in_the_status(self):
        self.controller.start_listening()
        self.controller.set_muted(True)
        self.assertIs(self.controller.state.status, Status.MUTED)
        self.controller.set_muted(False)
        self.assertIsNot(self.controller.state.status, Status.MUTED)

    def test_mute_reaches_the_recognition_service(self):
        self.controller.set_muted(True)
        self.assertTrue(self.controller.speech.is_muted)
        self.controller.set_muted(False)
        self.assertFalse(self.controller.speech.is_muted)

    def test_unmuting_works_again_afterwards(self):
        self.controller.set_muted(True)
        self.controller.set_muted(False)
        self.controller.handle_text("öffne discord")
        self.assertEqual(self.launched(), "Discord")

    # --- Push-to-Talk ---------------------------------------------------
    def test_ptt_bypasses_the_wake_word(self):
        self.enable_wake()
        with mock.patch.object(self.controller.speech, "start"):
            self.controller.ptt_press()
            self.assertTrue(self.controller.state.ptt_active)
            self.controller.handle_text("öffne discord")
        self.assertEqual(self.launched(), "Discord")

    def test_ptt_release_still_accepts_the_late_result(self):
        # Das Endergebnis kommt erst nach dem Loslassen aus dem Erkenner.
        self.enable_wake()
        with mock.patch.object(self.controller.speech, "start"), \
             mock.patch.object(self.controller.speech, "stop"):
            self.controller.ptt_press()
            self.controller.ptt_release()
            self.assertFalse(self.controller.state.ptt_active)
            self.controller.handle_text("öffne discord")
        self.assertEqual(self.launched(), "Discord")

    def test_ptt_does_nothing_while_muted(self):
        self.controller.set_muted(True)
        with mock.patch.object(self.controller.speech, "start") as start:
            self.controller.ptt_press()
        start.assert_not_called()
        self.assertFalse(self.controller.state.ptt_active)
        self.assertFalse(self.controller.state.action_ok)
        self.assertIn("stumm", self.controller.state.action_text.lower())

    def test_ptt_starts_and_stops_listening(self):
        with mock.patch.object(self.controller.speech, "start") as start, \
             mock.patch.object(self.controller.speech, "stop") as stop:
            self.controller.ptt_press()
            start.assert_called_once()
            self.controller.ptt_release()
            stop.assert_called_once()

    # --- Hotkey-Ereignisse ----------------------------------------------
    def test_hotkey_events_are_handled_in_the_ui_thread(self):
        self.controller.bus.publish(EventType.HOTKEY, action=ACTION_MUTE, phase=PRESS)
        self.assertFalse(self.controller.state.muted, "erst pump() wertet aus")
        self.controller.pump()
        self.assertTrue(self.controller.state.muted)

        self.controller.bus.publish(EventType.HOTKEY, action=ACTION_MUTE, phase=PRESS)
        self.controller.pump()
        self.assertFalse(self.controller.state.muted)

    def test_ptt_hotkey_press_and_release(self):
        with mock.patch.object(self.controller.speech, "start"), \
             mock.patch.object(self.controller.speech, "stop"):
            self.controller.bus.publish(EventType.HOTKEY, action=ACTION_PTT, phase=PRESS)
            self.controller.pump()
            self.assertTrue(self.controller.state.ptt_active)

            self.controller.bus.publish(EventType.HOTKEY, action=ACTION_PTT, phase=RELEASE)
            self.controller.pump()
            self.assertFalse(self.controller.state.ptt_active)

    # --- Einstellungen ---------------------------------------------------
    def test_settings_are_stored_and_reloaded(self):
        self.controller.update_settings(
            wake_word_enabled=True, wake_word="Computer",
            ptt_enabled=True, ptt_hotkey="ctrl+alt+space",
            mute_hotkey="ctrl+alt+m", hotkeys_enabled=True,
        )
        reloaded = SettingsStore().settings
        self.assertTrue(reloaded.wake_word_enabled)
        self.assertEqual(reloaded.wake_word, "Computer")
        self.assertTrue(reloaded.ptt_enabled)
        self.assertEqual(reloaded.ptt_hotkey, "ctrl+alt+space")

    def test_text_mode_bypasses_the_wake_word(self):
        # "python -m local_ally --say ..." soll auch mit aktivem Wake Word
        # funktionieren - der Befehl ist ja schon eingetippt.
        self.enable_wake()
        self.controller.handle_text("öffne discord", bypass_wake=True)
        self.assertEqual(self.launched(), "Discord")

    def test_conflicting_hotkeys_are_reported_in_the_state(self):
        self.controller.update_settings(
            hotkeys_enabled=True, ptt_enabled=True,
            mute_hotkey="ctrl+alt+m", ptt_hotkey="ctrl+alt+m",
        )
        self.assertFalse(self.controller.state.hotkeys_ok)
        self.assertTrue(self.controller.state.hotkey_errors)
        self.assertIn("mehrfach vergeben", self.controller.state.hotkey_errors[0])

    def test_invalid_hotkey_is_reported_in_the_state(self):
        self.controller.update_settings(hotkeys_enabled=True, mute_hotkey="m")
        self.assertTrue(self.controller.state.hotkey_errors)
        self.assertIn("Strg", self.controller.state.hotkey_errors[0])


if __name__ == "__main__":
    unittest.main()
