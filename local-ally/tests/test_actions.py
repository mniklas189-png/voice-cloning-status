"""Aktionen: was loesen sie am System aus?"""

from tests.fakes import FakeAssistant, FakeBackend
from tests.support import TempDataDirTestCase, unittest  # noqa: F401

from local_ally.actions import ActionContext, default_registry
from local_ally.app_index.models import DiscoveredApp
from local_ally.app_index.repository import AppRepository
from local_ally.commands.base import CommandContext
from local_ally.database import Database
from local_ally.intents import default_matcher
from local_ally.settings import Settings


class ActionTestCase(TempDataDirTestCase):
    """Basis: echter Programm-Index, Attrappe fuers Betriebssystem."""

    def setUp(self):
        super().setUp()
        self.db = Database()
        self.repo = AppRepository(self.db)
        self.repo.replace_all([
            DiscoveredApp(name="Discord", launch_target="C:/Discord/Discord.exe",
                          source="start_menu", priority=40),
            DiscoveredApp(name="Spotify", launch_target="C:/Spotify/Spotify.exe",
                          source="start_menu", priority=40),
            DiscoveredApp(name="Lunar Client", launch_target="C:/Lunar/LunarClient.exe",
                          source="start_menu", priority=40),
        ])
        self.backend = FakeBackend(processes=["explorer.exe", "Spotify.exe"])
        self.assistant = FakeAssistant()
        self.settings = Settings()
        self.command_context = CommandContext(
            repository=self.repo, settings=self.settings, apps=lambda: self.repo.all_apps()
        )
        self.context = ActionContext(
            command=self.command_context, backend=self.backend, assistant=self.assistant
        )
        self.registry = default_registry()
        self.matcher = default_matcher()

    def tearDown(self):
        self.db.close()
        super().tearDown()

    def run_sentence(self, sentence: str):
        found = self.matcher.match(sentence)
        self.assertIsNotNone(found, f"{sentence!r} wurde nicht erkannt")
        return self.registry.run(found, self.context)


class AudioActionTests(ActionTestCase):
    def test_volume_up_and_down(self):
        self.assertTrue(self.run_sentence("mach es lauter").ok)
        self.assertTrue(self.backend.called("volume_up"))
        self.run_sentence("mach es leiser")
        self.assertTrue(self.backend.called("volume_down"))

    def test_degree_changes_the_step_width(self):
        self.run_sentence("mach es etwas lauter")
        small = self.backend.call("volume_up")[1]
        self.backend.calls.clear()
        self.run_sentence("mach es deutlich lauter")
        large = self.backend.call("volume_up")[1]
        self.assertLess(small, large)

    def test_setting_an_exact_volume(self):
        result = self.run_sentence("stell die lautstärke auf 60 prozent")
        self.assertTrue(result.ok)
        self.assertEqual(self.backend.call("volume_set"), ("volume_set", 60))
        self.assertIn("60", result.message)

    def test_mute_and_unmute(self):
        self.run_sentence("mute meinen pc")
        self.assertEqual(self.backend.call("volume_mute"), ("volume_mute", True))
        self.backend.calls.clear()
        self.run_sentence("ton wieder an")
        self.assertEqual(self.backend.call("volume_mute"), ("volume_mute", False))

    def test_microphone_uses_the_assistants_own_mute(self):
        result = self.run_sentence("mach mein mikro aus")
        self.assertTrue(result.ok)
        self.assertTrue(self.assistant.muted)
        # Der Hinweis muss den Rueckweg nennen - sonst hoert niemand mehr zu.
        self.assertIn("Aufheben", result.message)

        self.run_sentence("mikro wieder an")
        self.assertFalse(self.assistant.muted)

    def test_audio_device_by_name(self):
        result = self.run_sentence("wechsle auf kopfhörer")
        self.assertTrue(result.ok)
        self.assertIn("Kopfhörer", result.message)

    def test_audio_device_without_name_lists_options(self):
        result = self.run_sentence("wechsle das audiogerät")
        self.assertTrue(result.ok)
        self.assertIn("Kopfhörer", result.message)


class SystemActionTests(ActionTestCase):
    def test_power_actions(self):
        for sentence, call in [
            ("sperr den pc", "lock"),
            ("fahr den pc herunter", "shutdown"),
            ("starte den pc neu", "restart"),
            ("energiesparmodus", "sleep"),
            ("mach den bildschirm aus", "screen_off"),
        ]:
            with self.subTest(sentence=sentence):
                self.backend.calls.clear()
                self.assertTrue(self.run_sentence(sentence).ok)
                self.assertTrue(self.backend.called(call))

    def test_settings_pages(self):
        self.run_sentence("öffne wlan")
        self.assertEqual(self.backend.call("open_settings"), ("open_settings", "wifi"))
        self.backend.calls.clear()
        self.run_sentence("öffne bluetooth")
        self.assertEqual(self.backend.call("open_settings"), ("open_settings", "bluetooth"))

    def test_task_manager(self):
        self.assertTrue(self.run_sentence("öffne den task manager").ok)
        self.assertTrue(self.backend.called("open_task_manager"))

    def test_brightness(self):
        self.run_sentence("mach den bildschirm heller")
        self.assertGreater(self.backend.call("brightness_step")[1], 0)
        self.backend.calls.clear()
        self.run_sentence("stell die helligkeit auf 30 prozent")
        self.assertEqual(self.backend.call("brightness_set"), ("brightness_set", 30))

    def test_display_mode_is_read_from_the_sentence(self):
        self.run_sentence("bildschirme erweitern")
        self.assertEqual(self.backend.call("display_mode"), ("display_mode", "extend"))

    def test_unsupported_functions_explain_themselves(self):
        self.backend.unsupported.add("lock")
        result = self.run_sentence("sperr den pc")
        self.assertFalse(result.ok)
        self.assertIn("nicht unterstützt", result.message)


class WindowActionTests(ActionTestCase):
    def test_window_actions(self):
        for sentence, call in [
            ("wechsle das fenster", "window_switch"),
            ("minimier das fenster", "window_minimize"),
            ("maximier das fenster", "window_maximize"),
            ("mach das fenster zu", "window_close"),
        ]:
            with self.subTest(sentence=sentence):
                self.backend.calls.clear()
                self.assertTrue(self.run_sentence(sentence).ok)
                self.assertTrue(self.backend.called(call))


class MediaActionTests(ActionTestCase):
    def test_media_commands(self):
        for sentence, command in [
            ("mach die musik weiter", "playpause"),
            ("nächster titel", "next"),
            ("vorheriger titel", "previous"),
        ]:
            with self.subTest(sentence=sentence):
                self.backend.calls.clear()
                self.assertTrue(self.run_sentence(sentence).ok)
                self.assertEqual(self.backend.call("media"), ("media", command))


class FileActionTests(ActionTestCase):
    def test_known_folder_is_resolved_and_opened(self):
        result = self.run_sentence("zeig mir meine downloads")
        self.assertTrue(result.ok)
        self.assertEqual(self.backend.call("known_folder"), ("known_folder", "downloads"))
        self.assertTrue(self.backend.called("open_path"))
        self.assertIn("Downloads", result.message)

    def test_file_search_passes_the_term(self):
        result = self.run_sentence("suche nach urlaub 2024")
        self.assertTrue(result.ok)
        self.assertEqual(self.backend.call("search_files")[1], "urlaub 2024")


class AppActionTests(ActionTestCase):
    def test_close_a_running_program(self):
        result = self.run_sentence("schließ spotify")
        self.assertTrue(result.ok)
        self.assertEqual(self.backend.call("close_process"), ("close_process", "Spotify.exe"))

    def test_closing_something_that_is_not_running(self):
        result = self.run_sentence("schließ discord")
        self.assertFalse(result.ok)
        self.assertIn("läuft gerade nicht", result.message)

    def test_running_check(self):
        self.assertIn("Ja", self.run_sentence("läuft spotify").message)
        self.assertIn("Nein", self.run_sentence("läuft discord").message)

    def test_switch_to_a_program(self):
        result = self.run_sentence("wechsle zu spotify")
        self.assertTrue(result.ok)
        self.assertTrue(self.backend.called("focus_process"))

    def test_switch_fails_when_the_program_is_closed(self):
        self.backend.focus_result = False
        result = self.run_sentence("wechsle zu discord")
        self.assertFalse(result.ok)

    def test_unknown_program_is_reported(self):
        result = self.run_sentence("schließ bildbearbeitung xyz")
        self.assertFalse(result.ok)
        self.assertIn("kein Programm", result.message)

    def test_ambiguous_program_asks_instead_of_acting(self):
        self.repo.replace_all([
            DiscoveredApp(name="Grafik Tool A", launch_target="C:/A.exe",
                          source="start_menu", priority=40),
            DiscoveredApp(name="Grafik Tool B", launch_target="C:/B.exe",
                          source="start_menu", priority=40),
        ])
        result = self.run_sentence("schließ grafik tool")
        self.assertTrue(result.needs_choice)
        self.assertEqual(len(result.candidates), 2)
        self.assertFalse(self.backend.called("close_process"))


if __name__ == "__main__":
    unittest.main()
