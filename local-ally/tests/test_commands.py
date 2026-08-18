"""Befehlserkennung und -ausfuehrung (ohne echte Prozesse zu starten)."""

from unittest import mock

from tests.support import TempDataDirTestCase, unittest  # noqa: F401

from local_ally.app_index.launcher import LaunchResult
from local_ally.app_index.models import AppEntry, DiscoveredApp
from local_ally.app_index.repository import AppRepository
from local_ally.commands import CommandContext, default_registry
from local_ally.commands.open_app import OpenAppCommand
from local_ally.database import Database
from local_ally.settings import Settings


def entry(app_id: int, name: str, aliases=(), weak=()) -> AppEntry:
    return AppEntry(
        id=app_id,
        name=name,
        launch_target=f"C:/Programme/{name}.exe",
        source="start_menu",
        priority=40,
        aliases=list(aliases),
        weak_aliases=list(weak),
    )


class ParsingTests(unittest.TestCase):
    """`match` darf nichts ausfuehren - hier wird nur der Satzbau geprueft."""

    def setUp(self):
        self.command = OpenAppCommand()
        self.context = CommandContext(
            repository=None, settings=Settings(), apps=lambda: []
        )

    def parse(self, sentence: str):
        intent = self.command.match(sentence, self.context)
        return None if intent is None else intent.slot("app")

    def test_common_german_phrasings(self):
        cases = {
            "Öffne Lunar Client": "lunar client",
            "öffne lunar client": "lunar client",
            "Starte Discord": "discord",
            "Spotify öffnen": "spotify",
            "Discord starten": "discord",
            "Kannst du bitte Discord öffnen": "discord",
            "mach mal Spotify auf": "spotify",
            "starte bitte das Programm Steam": "steam",
            "Öffne mir Visual Studio Code": "visual studio code",
        }
        for sentence, expected in cases.items():
            with self.subTest(sentence=sentence):
                self.assertEqual(self.parse(sentence), expected)

    def test_non_commands_are_ignored(self):
        for sentence in ["wie spät ist es", "hallo", "das war gut", ""]:
            with self.subTest(sentence=sentence):
                self.assertIsNone(self.parse(sentence))

    def test_verb_without_name_is_recognised_but_empty(self):
        self.assertEqual(self.parse("öffne"), "")


class ExecutionTests(TempDataDirTestCase):
    def setUp(self):
        super().setUp()
        self.db = Database()
        self.repo = AppRepository(self.db)
        self.repo.replace_all([
            DiscoveredApp(name="Discord", launch_target="C:/Discord.exe", source="start_menu", priority=40),
            DiscoveredApp(name="Discord Canary", launch_target="C:/Canary.exe", source="start_menu", priority=40),
            DiscoveredApp(name="Lunar Client", launch_target="C:/Lunar.exe", source="start_menu", priority=40),
            DiscoveredApp(name="Grafik Tool A", launch_target="C:/A.exe", source="start_menu", priority=40),
            DiscoveredApp(name="Grafik Tool B", launch_target="C:/B.exe", source="start_menu", priority=40),
        ])
        self.registry = default_registry()
        self.context = CommandContext(
            repository=self.repo,
            settings=Settings(),
            apps=lambda: self.repo.all_apps(),
        )
        patcher = mock.patch(
            "local_ally.app_index.launcher.launch",
            side_effect=lambda app: LaunchResult(True, f"{app.name} wird gestartet."),
        )
        self.launch = patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.db.close()
        super().tearDown()

    def handle(self, sentence: str):
        return self.registry.handle(sentence, self.context)

    def test_clear_match_is_launched(self):
        result = self.handle("öffne lunar client")
        self.assertTrue(result.ok)
        self.assertFalse(result.needs_choice)
        self.assertEqual(self.launch.call_args.args[0].name, "Lunar Client")

    def test_misheard_name_still_launches(self):
        result = self.handle("starte lunar klient")
        self.assertEqual(self.launch.call_args.args[0].name, "Lunar Client")
        self.assertTrue(result.ok)

    def test_ambiguous_names_ask_instead_of_launching(self):
        result = self.handle("öffne grafik tool")
        self.assertTrue(result.needs_choice)
        self.assertEqual(len(result.candidates), 2)
        self.launch.assert_not_called()

    def test_unknown_program_reports_failure(self):
        result = self.handle("öffne bildbearbeitung xyz")
        self.assertFalse(result.ok)
        self.launch.assert_not_called()

    def test_no_command_returns_none(self):
        self.assertIsNone(self.handle("wie spät ist es"))

    def test_choice_by_number(self):
        first = self.handle("öffne grafik tool")
        self.context.pending_candidates = first.candidates
        result = self.handle("die zweite")
        self.assertTrue(result.ok)
        self.assertEqual(self.launch.call_args.args[0].name, first.candidates[1].app.name)

    def test_choice_by_name(self):
        first = self.handle("öffne grafik tool")
        self.context.pending_candidates = first.candidates
        result = self.handle("grafik tool b")
        self.assertTrue(result.ok)
        self.assertEqual(self.launch.call_args.args[0].name, "Grafik Tool B")

    def test_new_command_beats_open_question(self):
        first = self.handle("öffne grafik tool")
        self.context.pending_candidates = first.candidates
        self.handle("starte discord")
        self.assertEqual(self.launch.call_args.args[0].name, "Discord")

    def test_cancel_clears_the_question(self):
        first = self.handle("öffne grafik tool")
        self.context.pending_candidates = first.candidates
        result = self.handle("abbrechen")
        self.assertTrue(result.ok)
        self.assertEqual(self.context.pending_candidates, [])
        self.launch.assert_not_called()

    def test_confirmation_launches_single_suggestion(self):
        settings = Settings(auto_execute=False)
        self.context.settings = settings
        first = self.handle("öffne lunar client")
        self.assertTrue(first.needs_choice)
        self.context.pending_candidates = first.candidates
        result = self.handle("ja")
        self.assertTrue(result.ok)
        self.assertEqual(self.launch.call_args.args[0].name, "Lunar Client")

    def test_launch_is_counted(self):
        self.handle("öffne discord")
        launched = [app for app in self.repo.all_apps() if app.name == "Discord"][0]
        self.assertEqual(launched.launch_count, 1)


if __name__ == "__main__":
    unittest.main()
