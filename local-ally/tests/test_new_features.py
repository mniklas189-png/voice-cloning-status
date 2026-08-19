"""Fenster gezielt, Timer, Diktat, mehrere Befehle, Kontextbezug."""

import time
from unittest import mock

from tests.fakes import FakeBackend
from tests.support import TempDataDirTestCase, unittest  # noqa: F401

from local_ally.app_index.launcher import LaunchResult
from local_ally.app_index.models import DiscoveredApp
from local_ally.core.controller import Controller
from local_ally.core.timers import TimerService, format_clock, format_duration
from local_ally.intents import default_matcher
from local_ally.intents.sequence import split_commands
from local_ally.settings import SettingsStore


class FeatureTestCase(TempDataDirTestCase):
    def setUp(self):
        super().setUp()
        store = SettingsStore()
        store.settings.index_on_first_start = False
        store.settings.hotkeys_enabled = False
        self.backend = FakeBackend(processes=["Discord.exe", "Spotify.exe"])
        self.controller = Controller(settings_store=store, backend=self.backend)
        self.controller.repository.replace_all([
            DiscoveredApp(name="Discord", launch_target="C:/Discord.exe",
                          source="start_menu", priority=40),
            DiscoveredApp(name="Spotify", launch_target="C:/Spotify.exe",
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


class TargetedWindowTests(FeatureTestCase):
    """Fenster eines bestimmten Programms."""

    def test_minimize_a_named_program(self):
        state = self.say("minimier discord")
        self.assertTrue(state.action_ok)
        self.assertEqual(self.backend.call("window_minimize"), ("window_minimize", "Discord"))

    def test_maximize_a_named_program(self):
        self.say("maximier spotify")
        self.assertEqual(self.backend.call("window_maximize"), ("window_maximize", "Spotify"))

    def test_without_a_name_the_active_window_is_meant(self):
        self.say("minimier das fenster")
        self.assertEqual(self.backend.call("window_minimize"), ("window_minimize", ""))

    def test_an_unknown_program_is_reported(self):
        state = self.say("minimier gibtsnicht")
        self.assertFalse(state.action_ok)
        self.assertFalse(self.backend.called("window_minimize"))

    def test_the_generic_wording_wins_over_a_program_name(self):
        found = default_matcher().match("mach das fenster zu")
        self.assertEqual(found.id, "window.close")


class TimerTests(FeatureTestCase):
    def test_starting_a_timer(self):
        state = self.say("stell einen timer auf 10 minuten")
        self.assertTrue(state.action_ok)
        self.assertEqual(self.controller.timers.count, 1)
        self.assertIn("10 Minuten", state.action_text)

    def test_various_phrasings(self):
        for sentence in ("timer 5 minuten", "weck mich in 20 minuten",
                         "erinner mich in 90 sekunden", "stell einen wecker auf eine stunde"):
            with self.subTest(sentence=sentence):
                self.controller.timers.cancel()
                self.say(sentence)
                self.assertEqual(self.controller.timers.count, 1, sentence)

    def test_listing_and_cancelling(self):
        self.say("timer 10 minuten")
        state = self.say("welche timer laufen")
        self.assertIn("10", state.action_text)
        state = self.say("timer abbrechen")
        self.assertEqual(self.controller.timers.count, 0)
        self.assertIn("abgebrochen", state.action_text)

    def test_a_due_timer_reports_and_beeps(self):
        self.controller.timers.add(0)
        self.assertTrue(self.controller.pump())
        self.assertIn("abgelaufen", self.controller.state.action_text)
        self.assertTrue(self.backend.called("beep"))
        self.assertEqual(self.controller.timers.count, 0)

    def test_the_display_only_changes_by_the_second(self):
        self.say("timer 10 minuten")
        self.controller.pump()
        first = list(self.controller.state.timers)
        self.assertTrue(first)
        # Unmittelbar danach hat sich die Anzeige nicht geändert - sonst
        # würde die Oberfläche im UI-Takt neu zeichnen.
        self.assertFalse(self.controller.pump())
        self.assertEqual(self.controller.state.timers, first)

    def test_a_missing_duration_is_reported(self):
        state = self.say("stell einen timer")
        self.assertFalse(state.action_ok)

    def test_formatting(self):
        self.assertEqual(format_duration(45), "45 Sekunden")
        self.assertEqual(format_duration(60), "1 Minute")
        self.assertEqual(format_duration(600), "10 Minuten")
        self.assertEqual(format_duration(90), "1:30 Minuten")
        self.assertEqual(format_duration(3600), "1 Stunde")
        self.assertEqual(format_clock(58), "00:58")
        self.assertEqual(format_clock(600), "10:00")

    def test_the_service_keeps_them_in_order(self):
        service = TimerService()
        late = service.add(600)
        early = service.add(5)
        self.assertEqual([timer.id for timer in service.active()], [early.id, late.id])
        self.assertEqual(service.cancel(early.id), 1)
        self.assertEqual(service.count, 1)

    def test_due_timers_are_taken_only_once(self):
        service = TimerService()
        service.add(0)
        self.assertEqual(len(service.take_due()), 1)
        self.assertEqual(service.take_due(), [])


class DictationTests(FeatureTestCase):
    def test_typing_keeps_the_original_wording(self):
        state = self.say("Schreib mir bitte Hallo Welt")
        self.assertTrue(state.action_ok)
        # Umlaute, Groß- und Kleinschreibung bleiben erhalten - der
        # normalisierte Parameter wäre dafür unbrauchbar.
        self.assertEqual(self.backend.call("type_text"), ("type_text", "Hallo Welt"))

    def test_umlauts_survive(self):
        self.say("tippe Grüße aus München")
        self.assertEqual(self.backend.call("type_text")[1], "Grüße aus München")

    def test_a_leading_folgendes_is_dropped(self):
        self.say("schreib folgendes: Das ist ein Test")
        self.assertEqual(self.backend.call("type_text")[1], "Das ist ein Test")

    def test_nothing_to_type_is_reported(self):
        state = self.say("schreib")
        self.assertFalse(state.action_ok)
        self.assertFalse(self.backend.called("type_text"))


class SequenceTests(FeatureTestCase):
    def test_two_commands_in_one_sentence(self):
        state = self.say("mach es leiser und öffne spotify")
        self.assertTrue(self.backend.called("volume_down"))
        self.assertEqual(self.launch.call_args.args[0].name, "Spotify")
        self.assertIn("·", state.action_text)

    def test_three_commands(self):
        self.say("mach es leiser dann öffne discord und minimier spotify")
        self.assertTrue(self.backend.called("volume_down"))
        self.assertTrue(self.backend.called("window_minimize"))

    def test_a_program_name_containing_und_stays_whole(self):
        # "Rot und Blau" darf nicht in zwei Befehle zerfallen.
        self.assertEqual(
            split_commands("öffne rot und blau", default_matcher()),
            ["öffne rot und blau"],
        )

    def test_a_sentence_without_conjunction_is_untouched(self):
        self.assertEqual(split_commands("mach es lauter", default_matcher()), ["mach es lauter"])

    def test_a_question_stops_the_chain(self):
        state = self.say("mach es leiser und fahr den pc herunter")
        self.assertTrue(self.backend.called("volume_down"))
        self.assertTrue(state.awaiting_confirm)
        self.assertFalse(self.backend.called("shutdown"))

    def test_half_understood_sentences_do_nothing(self):
        # Getrennt wird nur, wenn jeder Teil ein Befehl ist. Sonst könnte ein
        # verhörtes Satzende die erste Hälfte fälschlich auslösen - lieber
        # gar nichts tun und das sagen.
        state = self.say("mach es leiser und quatsch mit soße")
        self.assertFalse(self.backend.called("volume_down"))
        self.assertFalse(state.action_ok)
        self.assertIn("nicht als Befehl", state.action_text)


class ContextTests(FeatureTestCase):
    """Fürwörter beziehen sich auf das zuletzt betroffene Programm."""

    def test_close_it_after_opening(self):
        self.say("öffne discord")
        state = self.say("mach ihn zu")
        self.assertTrue(state.awaiting_confirm)
        self.assertIn("Discord", state.confirm_question)
        self.say("ja")
        self.assertEqual(self.backend.call("close_process"), ("close_process", "Discord.exe"))

    def test_minimize_it(self):
        self.say("öffne spotify")
        self.say("minimier ihn")
        self.assertEqual(self.backend.call("window_minimize"), ("window_minimize", "Spotify"))

    def test_the_reference_follows_the_latest_program(self):
        self.say("öffne discord")
        self.say("öffne spotify")
        self.say("minimier ihn")
        self.assertEqual(self.backend.call("window_minimize"), ("window_minimize", "Spotify"))

    def test_without_a_previous_program_it_says_so(self):
        state = self.say("minimier ihn")
        self.assertFalse(state.action_ok)

    def test_es_and_sie_work_too(self):
        self.say("öffne spotify")
        self.say("läuft es")
        self.assertIn("Spotify", self.controller.state.action_text)


if __name__ == "__main__":
    unittest.main()
