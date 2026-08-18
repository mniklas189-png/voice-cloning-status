"""Absichtserkennung: Formulierungen, Parameter, Abgrenzung."""

from tests.support import unittest  # noqa: F401

from local_ally.actions import default_registry as action_registry
from local_ally.intents import default_matcher
from local_ally.intents.catalog import all_specs
from local_ally.intents.pattern import compile_pattern
from local_ally.intents.slots import default_readers, parse_number, read_folder, read_level


class PatternTests(unittest.TestCase):
    """Die Mustersprache selbst."""

    def setUp(self):
        self.readers = default_readers()

    def match(self, template: str, sentence: str):
        return compile_pattern(template).match(tuple(sentence.split()), self.readers)

    def test_alternatives(self):
        self.assertIsNotNone(self.match("(mach|dreh) lauter", "mach lauter"))
        self.assertIsNotNone(self.match("(mach|dreh) lauter", "dreh lauter"))
        self.assertIsNone(self.match("(mach|dreh) lauter", "stell lauter"))

    def test_multi_word_alternatives(self):
        self.assertIsNotNone(self.match("(task manager|taskmanager)", "task manager"))
        self.assertIsNotNone(self.match("(task manager|taskmanager)", "taskmanager"))

    def test_optional_part(self):
        self.assertIsNotNone(self.match("lautstaerke auf {level} [prozent]", "lautstaerke auf 60"))
        self.assertIsNotNone(
            self.match("lautstaerke auf {level} [prozent]", "lautstaerke auf 60 prozent")
        )

    def test_any_words(self):
        self.assertIsNotNone(self.match("mach * lauter", "mach lauter"))
        self.assertIsNotNone(self.match("mach * lauter", "mach das ganze etwas lauter"))

    def test_slot_backtracks_when_words_follow(self):
        # Der freie Parameter darf nicht alles verschlucken.
        found = self.match("(check|pruef) ob {app} laeuft", "check ob steam laeuft")
        self.assertEqual(found, {"app": "steam"})

    def test_full_sentence_must_be_consumed(self):
        self.assertIsNone(self.match("mach lauter", "mach lauter bitte gleich jetzt sofort noch"))


class SlotTests(unittest.TestCase):
    def test_digits_and_words(self):
        self.assertEqual(parse_number(["60"]), (1, 60))
        self.assertEqual(parse_number(["vierzig"]), (1, 40))
        self.assertEqual(parse_number(["fuenfundvierzig"]), (1, 45))
        self.assertEqual(parse_number(["hundert"]), (1, 100))
        self.assertIsNone(parse_number(["lauter"]))

    def test_level_takes_percent_along(self):
        self.assertIn((2, "60"), read_level(["60", "prozent"]))
        self.assertEqual(read_level(["150"]), [])

    def test_known_folders(self):
        self.assertEqual(read_folder(["downloads"]), [(1, "downloads")])
        self.assertEqual(read_folder(["schreibtisch"]), [(1, "desktop")])
        self.assertEqual(read_folder(["quatsch"]), [])


class CatalogTests(unittest.TestCase):
    def test_every_intent_has_an_action(self):
        registry = action_registry()
        missing = [spec.id for spec in all_specs() if registry.get(spec.action) is None]
        self.assertEqual(missing, [], "Absichten ohne Aktion")

    def test_every_action_is_reachable(self):
        used = {spec.action for spec in all_specs()}
        unused = sorted(set(action_registry().names()) - used)
        self.assertEqual(unused, [], "Aktionen, die keine Absicht auslöst")

    def test_ids_are_unique(self):
        ids = [spec.id for spec in all_specs()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_intent_is_documented(self):
        for spec in all_specs():
            with self.subTest(intent=spec.id):
                self.assertTrue(spec.description, "Beschreibung fehlt")
                self.assertTrue(spec.templates, "Muster fehlen")


class RecognitionTests(unittest.TestCase):
    """Formulierungen aus dem Alltag."""

    def setUp(self):
        self.matcher = default_matcher()

    def assert_intent(self, sentence: str, expected: str, **slots):
        found = self.matcher.match(sentence)
        self.assertIsNotNone(found, f"{sentence!r} wurde nicht erkannt")
        self.assertEqual(found.id, expected, f"{sentence!r} -> {found.id}")
        for name, value in slots.items():
            self.assertEqual(found.slot(name), value, f"{sentence!r}: Parameter {name}")

    def test_the_examples_from_the_specification(self):
        cases = [
            ("Mach es etwas lauter", "audio.volume.up"),
            ("Stell die Lautstärke auf 60 Prozent", "audio.volume.set"),
            ("Mute meinen PC", "audio.mute"),
            ("Mach mein Mikro aus", "audio.mic.mute"),
            ("Öffne Discord", "app.open"),
            ("Schließ Spotify", "app.close"),
            ("Zeig mir meine Downloads", "files.folder"),
            ("Mach den Bildschirm aus", "system.screen_off"),
            ("Sperr meinen PC", "system.lock"),
            ("Mach die Musik weiter", "media.playpause"),
        ]
        for sentence, expected in cases:
            with self.subTest(sentence=sentence):
                self.assert_intent(sentence, expected)

    def test_many_phrasings_reach_the_same_intent(self):
        for sentence in ("mach es lauter", "lauter", "dreh mal lauter",
                         "erhöhe die lautstärke", "lautstärke hoch"):
            with self.subTest(sentence=sentence):
                self.assert_intent(sentence, "audio.volume.up")

        for sentence in ("mach es leiser", "leiser", "lautstärke runter",
                         "reduziere die lautstärke"):
            with self.subTest(sentence=sentence):
                self.assert_intent(sentence, "audio.volume.down")

    def test_volume_values_in_digits_and_words(self):
        self.assert_intent("stell die lautstärke auf 60 prozent", "audio.volume.set", level="60")
        self.assert_intent("lautstärke auf vierzig prozent", "audio.volume.set", level="40")
        self.assert_intent("lautstärke auf null", "audio.volume.set", level="0")
        self.assert_intent("mach die lautstärke auf hundert", "audio.volume.set", level="100")

    def test_degree_words_are_captured(self):
        found = self.matcher.match("mach es etwas lauter")
        self.assertEqual(found.slot("degree"), "small")
        found = self.matcher.match("mach es deutlich lauter")
        self.assertEqual(found.slot("degree"), "large")

    def test_program_names_are_extracted(self):
        self.assert_intent("öffne lunar client", "app.open", app="lunar client")
        self.assert_intent("starte discord", "app.open", app="discord")
        self.assert_intent("spotify öffnen", "app.open", app="spotify")
        self.assert_intent("schließ spotify", "app.close", app="spotify")
        self.assert_intent("läuft discord", "app.running", app="discord")
        self.assert_intent("wechsle zu steam", "app.switch", app="steam")

    def test_windows_control(self):
        self.assert_intent("sperr den pc", "system.lock")
        self.assert_intent("fahr den rechner herunter", "system.shutdown")
        self.assert_intent("starte den pc neu", "system.restart")
        self.assert_intent("energiesparmodus", "system.sleep")
        self.assert_intent("öffne die einstellungen", "system.settings")
        self.assert_intent("öffne den task manager", "system.taskmanager")
        self.assert_intent("öffne wlan", "system.wifi")
        self.assert_intent("öffne bluetooth", "system.bluetooth")

    def test_windows_and_media(self):
        self.assert_intent("wechsle das fenster", "window.switch")
        self.assert_intent("minimier das fenster", "window.minimize")
        self.assert_intent("maximier das fenster", "window.maximize")
        self.assert_intent("mach das fenster zu", "window.close")
        self.assert_intent("pause", "media.playpause")
        self.assert_intent("spiel weiter", "media.playpause")
        self.assert_intent("nächster titel", "media.next")
        self.assert_intent("vorheriger titel", "media.previous")

    def test_files_and_folders(self):
        self.assert_intent("zeig mir meine downloads", "files.folder", folder="downloads")
        self.assert_intent("öffne die dokumente", "files.folder", folder="documents")
        self.assert_intent("desktop öffnen", "files.folder", folder="desktop")
        self.assert_intent("suche nach rechnung", "files.search", query="rechnung")

    def test_a_known_folder_beats_a_program_name(self):
        found = self.matcher.match("öffne downloads")
        self.assertEqual(found.id, "files.folder")

    def test_a_window_beats_a_program_name(self):
        found = self.matcher.match("schließ das fenster")
        self.assertEqual(found.id, "window.close")

    def test_microphone_beats_general_muting(self):
        self.assert_intent("mach das mikro aus", "audio.mic.mute")
        self.assert_intent("mach den ton aus", "audio.mute")

    def test_everyday_sentences_are_not_commands(self):
        for sentence in ("wie spät ist es", "hallo", "das war gut",
                         "erzähl mir einen witz", ""):
            with self.subTest(sentence=sentence):
                self.assertIsNone(self.matcher.match(sentence))

    def test_critical_intents_carry_a_question(self):
        for intent_id in ("system.shutdown", "system.restart", "app.close", "window.close"):
            with self.subTest(intent=intent_id):
                spec = next(s for s in all_specs() if s.id == intent_id)
                self.assertTrue(spec.confirm, "Rückfrage fehlt")


if __name__ == "__main__":
    unittest.main()
