"""Eigene Funktionen: anlegen, speichern, erkennen, ausfuehren.

Geprueft wird die ganze Kette - vom Formular ueber die Datenbank bis zu dem,
was am System tatsaechlich ausgeloest wird.
"""

from unittest import mock

from tests.fakes import FakeBackend
from tests.support import TempDataDirTestCase, unittest  # noqa: F401

from local_ally.app_index.launcher import LaunchResult
from local_ally.app_index.models import DiscoveredApp
from local_ally.app_index.repository import AppRepository
from local_ally.commands import CommandContext, default_registry
from local_ally.commands.custom_command import CustomCommandRunner
from local_ally.custom.models import (
    ACTION_TYPES,
    CustomCommand,
    action_type,
    validate,
)
from local_ally.custom.repository import CustomCommandRepository
from local_ally.database import Database
from local_ally.settings import Settings, SettingsStore


class CustomTestCase(TempDataDirTestCase):
    def setUp(self):
        super().setUp()
        self.db = Database()
        self.apps = AppRepository(self.db)
        self.apps.replace_all([
            DiscoveredApp(name="Anki", launch_target="C:/Anki/anki.exe",
                          source="start_menu", priority=40),
            DiscoveredApp(name="Discord", launch_target="C:/Discord.exe",
                          source="start_menu", priority=40),
            DiscoveredApp(name="Discord Canary", launch_target="C:/Canary.exe",
                          source="start_menu", priority=40),
        ])
        self.custom = CustomCommandRepository(self.db)
        self.backend = FakeBackend()
        self.registry = default_registry(
            backend=self.backend, custom_repository=self.custom
        )
        self.context = CommandContext(
            repository=self.apps, settings=Settings(), apps=lambda: self.apps.all_apps()
        )

    def tearDown(self):
        self.db.close()
        super().tearDown()

    def add(self, phrase: str, action: str, target: str) -> CustomCommand:
        saved = self.custom.save(
            CustomCommand(phrase=phrase, action=action, target=target)
        )
        runner = self.registry.get("custom")
        runner.refresh()
        return saved

    def handle(self, sentence: str):
        return self.registry.handle(sentence, self.context)


# --- Datenhaltung ------------------------------------------------------
class RepositoryTests(CustomTestCase):
    def test_save_read_update_delete(self):
        saved = self.add("lernen", "app", "Anki")
        self.assertTrue(saved.id)

        stored = self.custom.get(saved.id)
        self.assertEqual(stored.phrase, "lernen")
        self.assertEqual(stored.action, "app")
        self.assertEqual(stored.target, "Anki")
        self.assertTrue(stored.enabled)

        stored.target = "Discord"
        self.custom.save(stored)
        self.assertEqual(self.custom.get(saved.id).target, "Discord")

        self.assertTrue(self.custom.delete(saved.id))
        self.assertIsNone(self.custom.get(saved.id))

    def test_functions_survive_a_restart(self):
        self.add("videos", "website", "https://youtube.com")
        self.db.close()

        # Neue Verbindung auf dieselbe Datei - wie nach einem Neustart.
        again = Database()
        try:
            stored = CustomCommandRepository(again).all()
            self.assertEqual([entry.phrase for entry in stored], ["videos"])
            self.assertEqual(stored[0].target, "https://youtube.com")
        finally:
            again.close()
            self.db = again

    def test_disabled_functions_stay_but_are_not_offered(self):
        saved = self.add("lernen", "app", "Anki")
        self.custom.set_enabled(saved.id, False)
        self.assertEqual(len(self.custom.all()), 1)
        self.assertEqual(self.custom.all(only_enabled=True), [])

    def test_use_count_is_incremented(self):
        saved = self.add("tippen", "text", "Hallo")
        self.custom.note_use(saved.id)
        self.custom.note_use(saved.id)
        self.assertEqual(self.custom.get(saved.id).use_count, 2)


# --- Pruefungen --------------------------------------------------------
class ValidationTests(CustomTestCase):
    def test_every_action_type_has_a_label_and_a_check(self):
        ids = [entry.id for entry in ACTION_TYPES]
        self.assertEqual(len(ids), len(set(ids)))
        for entry in ACTION_TYPES:
            with self.subTest(action=entry.id):
                self.assertTrue(entry.label)
                self.assertTrue(entry.short_label)
                self.assertTrue(entry.config_label)
                self.assertTrue(entry.validate(""))   # leeres Ziel faellt auf

    def test_the_three_requested_types_exist(self):
        ids = {entry.id for entry in ACTION_TYPES}
        self.assertLessEqual({"app", "command", "website"}, ids)

    def test_short_phrases_are_refused(self):
        problem = validate(CustomCommand(phrase="yt", action="website", target="yt.de"))
        self.assertIn("mindestens", problem)

    def test_duplicate_phrases_are_refused(self):
        self.add("lernen", "app", "Anki")
        problem = validate(
            CustomCommand(phrase="Lernen", action="app", target="Discord"),
            self.custom.taken_phrases(),
        )
        self.assertIn("vergeben", problem)

    def test_editing_keeps_its_own_phrase(self):
        saved = self.add("lernen", "app", "Anki")
        saved.target = "Discord"
        self.assertEqual(
            validate(saved, self.custom.taken_phrases(except_id=saved.id)), ""
        )

    def test_reserved_answers_are_refused(self):
        # Antworten auf Rueckfragen werden vorher geprueft - ein Befehl
        # "abbrechen" wuerde nie ausloesen und wird deshalb abgelehnt.
        problem = validate(CustomCommand(phrase="abbrechen", action="text", target="x"))
        self.assertIn("Rückfragen", problem)

    def test_addresses_are_checked(self):
        self.assertIn(
            "Leerzeichen",
            validate(CustomCommand(phrase="video", action="website", target="kein url")),
        )
        self.assertEqual(
            validate(CustomCommand(phrase="video", action="website", target="youtube.com")),
            "",
        )

    def test_single_keys_are_refused(self):
        problem = validate(CustomCommand(phrase="neu", action="keys", target="t"))
        self.assertTrue(problem)
        self.assertEqual(
            validate(CustomCommand(phrase="neu", action="keys", target="ctrl+shift+n")), ""
        )

    def test_unknown_action_falls_back_to_the_first(self):
        self.assertEqual(action_type("gibtsnicht").id, ACTION_TYPES[0].id)


# --- Erkennung ---------------------------------------------------------
class MatchingTests(CustomTestCase):
    def test_saved_phrase_is_recognised(self):
        self.add("videos", "website", "https://youtube.com")
        result = self.handle("videos")
        self.assertTrue(result.ok, result.message)
        self.assertEqual(self.backend.call("open_path"), ("open_path", "https://youtube.com"))

    def test_polite_forms_still_match(self):
        self.add("videos", "website", "https://youtube.com")
        self.assertTrue(self.handle("bitte videos").ok)

    def test_small_mishearings_are_forgiven(self):
        self.add("lernen", "website", "https://ankiweb.net")
        self.assertTrue(self.handle("lehrnen").ok)

    def test_unrelated_sentences_do_not_trigger(self):
        self.add("videos", "website", "https://youtube.com")
        self.assertIsNone(self.handle("mach das licht an"))
        self.assertFalse(self.backend.called("open_path"))

    def test_disabled_functions_do_not_trigger(self):
        # Ein Satz ohne eingebaute Entsprechung: so bleibt nach dem
        # Ausschalten wirklich nichts uebrig, was ihn auffangen koennte.
        saved = self.add("kaffeepause", "website", "https://youtube.com")
        self.custom.set_enabled(saved.id, False)
        self.registry.get("custom").refresh()
        self.assertIsNone(self.handle("kaffeepause"))

    def test_custom_functions_win_over_built_in_intents(self):
        # "sperren" ist eingebaut (Bildschirm sperren) - der eigene Befehl
        # geht vor, sonst waere eine Belegung nicht ueberschreibbar.
        self.add("sperren", "website", "https://example.org")
        result = self.handle("sperren")
        self.assertTrue(result.ok, result.message)
        self.assertTrue(self.backend.called("open_path"))
        self.assertFalse(self.backend.called("lock"))

    def test_built_in_intents_still_work_next_to_custom_ones(self):
        self.add("videos", "website", "https://youtube.com")
        result = self.handle("sperr den bildschirm")
        self.assertTrue(result.ok, result.message)
        self.assertTrue(self.backend.called("lock"))

    def test_an_open_question_keeps_priority(self):
        # Waehrend eine Rueckfrage laeuft, bleibt "ja" die Antwort - auch
        # wenn ein aehnlicher eigener Befehl existiert.
        self.add("jaja doch", "website", "https://example.org")
        with mock.patch(
            "local_ally.app_index.launcher.launch",
            side_effect=lambda app: LaunchResult(True, f"{app.name} startet."),
        ):
            question = self.handle("schließ discord")
            self.assertTrue(question.needs_choice or question.needs_confirm)
            answer = self.handle("ja")
            self.assertNotEqual(answer.intent.name, "custom.website")

    def test_the_use_count_is_noted(self):
        saved = self.add("videos", "website", "https://youtube.com")
        self.handle("videos")
        self.assertEqual(self.custom.get(saved.id).use_count, 1)


# --- Ausfuehrung -------------------------------------------------------
class ExecutionTests(CustomTestCase):
    def test_app_action_launches_the_program(self):
        self.add("lernen", "app", "Anki")
        with mock.patch(
            "local_ally.app_index.launcher.launch",
            side_effect=lambda app: LaunchResult(True, f"{app.name} wird gestartet."),
        ) as launch:
            result = self.handle("lernen")
        self.assertTrue(result.ok, result.message)
        self.assertEqual(launch.call_args.args[0].name, "Anki")

    def test_website_action_adds_the_scheme(self):
        self.add("videos", "website", "youtube.com")
        self.handle("videos")
        self.assertEqual(self.backend.call("open_path"), ("open_path", "https://youtube.com"))

    def test_command_action_runs_a_shell_command(self):
        self.add("netz neu", "command", "ipconfig /flushdns")
        self.assertTrue(self.handle("netz neu").ok)
        self.assertEqual(
            self.backend.call("run_shell"), ("run_shell", "ipconfig /flushdns")
        )

    def test_folder_action_opens_a_path(self):
        self.add("projekte", "folder", "C:/Projekte")
        self.assertTrue(self.handle("projekte").ok)
        self.assertEqual(self.backend.call("open_path"), ("open_path", "C:/Projekte"))

    def test_text_action_types(self):
        self.add("meine mail", "text", "ich@example.org")
        self.assertTrue(self.handle("meine mail").ok)
        self.assertEqual(self.backend.call("type_text"), ("type_text", "ich@example.org"))

    def test_keys_action_sends_the_combination(self):
        self.add("neuer tab", "keys", "ctrl+t")
        self.assertTrue(self.handle("neuer tab").ok)
        self.assertEqual(self.backend.call("send_keys"), ("send_keys", "ctrl+t"))

    def test_unsupported_actions_report_plainly(self):
        self.backend.unsupported.add("run_shell")
        self.add("netz neu", "command", "ipconfig")
        result = self.handle("netz neu")
        self.assertFalse(result.ok)
        self.assertIn("unterstützt", result.message)

    def test_a_removed_program_is_reported(self):
        self.add("lernen", "app", "Gibt Es Nicht Mehr")
        result = self.handle("lernen")
        self.assertFalse(result.ok)
        self.assertIn("Programm-Index", result.message)

    def test_an_ambiguous_program_asks_and_continues_as_the_custom_function(self):
        # "Grafik Tool" passt auf zwei Eintraege - Local Ally fragt nach.
        # Die Antwort muss *dieselbe* eigene Funktion fortsetzen und darf
        # nicht im Absichtskatalog landen.
        self.apps.replace_all([
            DiscoveredApp(name="Grafik Tool A", launch_target="C:/A.exe",
                          source="start_menu", priority=40),
            DiscoveredApp(name="Grafik Tool B", launch_target="C:/B.exe",
                          source="start_menu", priority=40),
        ])
        self.add("zeichnen", "app", "Grafik Tool")
        with mock.patch(
            "local_ally.app_index.launcher.launch",
            side_effect=lambda app: LaunchResult(True, f"{app.name} wird gestartet."),
        ) as launch:
            question = self.handle("zeichnen")
            self.assertTrue(question.needs_choice, question.message)
            self.assertEqual(
                [match.app.name for match in question.candidates],
                ["Grafik Tool A", "Grafik Tool B"],
            )

            self.context.pending_candidates = list(question.candidates)
            answer = self.handle("zwei")
        self.assertTrue(answer.ok, answer.message)
        self.assertEqual(answer.intent.name, "custom.app")
        self.assertEqual(launch.call_args.args[0].name, "Grafik Tool B")


# --- Formular und Oberflaeche -----------------------------------------
class ControllerTests(TempDataDirTestCase):
    def setUp(self):
        super().setUp()
        from local_ally.core.controller import Controller

        store = SettingsStore()
        store.settings.index_on_first_start = False
        self.controller = Controller(settings_store=store, backend=FakeBackend())
        self.controller.repository.replace_all([
            DiscoveredApp(name="Anki", launch_target="C:/Anki/anki.exe",
                          source="start_menu", priority=40),
            DiscoveredApp(name="Ankiweb Helfer", launch_target="C:/Helper.exe",
                          source="start_menu", priority=10),
        ])
        self.controller.startup()

    def tearDown(self):
        self.controller.shutdown()
        super().tearDown()

    def test_the_example_from_the_request_works_end_to_end(self):
        state = self.controller.state
        self.controller.custom_set_phrase("lernen")
        self.controller.custom_set_action("app")
        self.controller.custom_search_apps("Ank")
        self.assertIn("Anki", [app.name for app in state.custom_app_matches])
        self.controller.custom_pick_app("Anki")
        self.assertTrue(self.controller.custom_save())
        self.assertEqual([row.phrase for row in state.custom_commands], ["lernen"])

        with mock.patch(
            "local_ally.app_index.launcher.launch",
            side_effect=lambda app: LaunchResult(True, f"{app.name} wird gestartet."),
        ) as launch:
            self.controller.handle_text("lernen", bypass_wake=True)
        self.assertTrue(state.action_ok, state.action_text)
        self.assertEqual(launch.call_args.args[0].name, "Anki")

    def test_the_form_reports_problems_instead_of_saving(self):
        state = self.controller.state
        self.controller.custom_set_phrase("yt")
        self.controller.custom_set_action("website")
        self.controller.custom_set_target("youtube.com")
        self.assertFalse(self.controller.custom_save())
        self.assertIn("mindestens", state.custom_error)
        self.assertEqual(state.custom_commands, [])

    def test_switching_the_action_clears_the_target(self):
        self.controller.custom_set_phrase("test eins")
        self.controller.custom_set_target("Anki")
        self.controller.custom_set_action("website")
        self.assertEqual(self.controller.state.custom_target, "")

    def test_editing_loads_and_replaces(self):
        state = self.controller.state
        self.controller.custom_set_phrase("videos")
        self.controller.custom_set_action("website")
        self.controller.custom_set_target("youtube.com")
        self.assertTrue(self.controller.custom_save())
        saved_id = state.custom_commands[0].id

        self.controller.custom_edit(saved_id)
        self.assertEqual(state.custom_edit_id, saved_id)
        self.assertEqual(state.custom_phrase, "videos")
        self.assertEqual(state.custom_action, "website")

        self.controller.custom_set_target("vimeo.com")
        self.assertTrue(self.controller.custom_save())
        self.assertEqual(len(state.custom_commands), 1)
        self.assertEqual(state.custom_commands[0].target, "vimeo.com")
        self.assertEqual(state.custom_edit_id, 0)

    def test_editing_keeps_the_disabled_state(self):
        state = self.controller.state
        self.controller.custom_set_phrase("videos")
        self.controller.custom_set_action("website")
        self.controller.custom_set_target("youtube.com")
        self.controller.custom_save()
        saved_id = state.custom_commands[0].id
        self.controller.custom_set_enabled(saved_id, False)

        self.controller.custom_edit(saved_id)
        self.controller.custom_set_target("vimeo.com")
        self.controller.custom_save()
        self.assertFalse(state.custom_commands[0].enabled)

    def test_deleting_removes_it_from_the_list_and_the_recognition(self):
        state = self.controller.state
        self.controller.custom_set_phrase("kaffeepause")
        self.controller.custom_set_action("website")
        self.controller.custom_set_target("youtube.com")
        self.controller.custom_save()
        saved_id = state.custom_commands[0].id

        self.controller.custom_delete(saved_id)
        self.assertEqual(state.custom_commands, [])
        self.controller.handle_text("kaffeepause", bypass_wake=True)
        self.assertFalse(state.action_ok)

    def test_running_from_the_ui_takes_the_same_path(self):
        state = self.controller.state
        self.controller.custom_set_phrase("meine mail")
        self.controller.custom_set_action("text")
        self.controller.custom_set_target("ich@example.org")
        self.controller.custom_save()
        self.controller.custom_run(state.custom_commands[0].id)
        self.assertTrue(state.action_ok, state.action_text)
        self.assertEqual(
            self.controller.backend.call("type_text"), ("type_text", "ich@example.org")
        )

    def test_the_form_revision_only_changes_on_a_real_switch(self):
        state = self.controller.state
        before = state.custom_form_revision
        self.controller.custom_set_phrase("lernen")
        self.controller.custom_set_target("Anki")
        self.assertEqual(state.custom_form_revision, before)
        self.controller.custom_set_action("website")
        self.assertGreater(state.custom_form_revision, before)


class RunnerCacheTests(CustomTestCase):
    def test_new_functions_are_seen_after_a_refresh(self):
        runner = CustomCommandRunner(repository=self.custom, backend=self.backend)
        self.assertEqual(runner.commands(), [])
        self.custom.save(CustomCommand(phrase="videos", action="website", target="x.de"))
        self.assertEqual(runner.commands(), [])   # noch der alte Stand
        runner.refresh()
        self.assertEqual([entry.phrase for entry in runner.commands()], ["videos"])
