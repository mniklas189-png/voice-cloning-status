"""Wake-Word-Erkennung."""

from tests.support import unittest  # noqa: F401

from local_ally.speech.wakeword import DEFAULT_WAKE_WORD, WakeWordDetector


class WakeWordTests(unittest.TestCase):
    def setUp(self):
        self.detector = WakeWordDetector(DEFAULT_WAKE_WORD)

    def command_of(self, text):
        match = self.detector.split(text)
        return None if match is None else match.command

    def test_wake_word_alone_arms_without_command(self):
        match = self.detector.split("Hey Ally")
        self.assertIsNotNone(match)
        self.assertFalse(match.has_command)

    def test_wake_word_is_stripped_from_the_command(self):
        self.assertEqual(self.command_of("Hey Ally öffne Discord"), "oeffne discord")

    def test_misheard_variants_still_trigger(self):
        for spoken in ("hey alli starte spotify", "heyally starte spotify",
                       "hey alley starte spotify", "hey ali starte spotify"):
            with self.subTest(spoken=spoken):
                self.assertEqual(self.command_of(spoken), "starte spotify")

    def test_filler_before_the_wake_word_is_tolerated(self):
        self.assertEqual(self.command_of("ähm hey ally öffne steam"), "oeffne steam")

    def test_without_wake_word_nothing_matches(self):
        for spoken in ("öffne discord", "starte steam", "wie spät ist es", ""):
            with self.subTest(spoken=spoken):
                self.assertIsNone(self.detector.split(spoken))

    def test_similar_but_different_phrases_do_not_trigger(self):
        for spoken in ("hey alaska", "heute alles gut", "allianz öffnen"):
            with self.subTest(spoken=spoken):
                self.assertIsNone(self.detector.split(spoken))

    def test_custom_wake_word(self):
        detector = WakeWordDetector("Computer")
        self.assertEqual(detector.split("computer öffne discord").command, "oeffne discord")
        self.assertEqual(detector.split("komputer starte steam").command, "starte steam")
        self.assertIsNone(detector.split("öffne discord"))

    def test_umlauts_in_the_wake_word(self):
        detector = WakeWordDetector("Hör zu")
        self.assertIsNotNone(detector.split("hör zu öffne discord"))
        self.assertEqual(detector.split("hoer zu öffne discord").command, "oeffne discord")

    def test_too_short_wake_word_is_refused(self):
        detector = WakeWordDetector("ok")
        self.assertFalse(detector.is_usable)
        self.assertIsNone(detector.split("ok öffne discord"))

    def test_empty_setting_falls_back_to_the_default(self):
        self.assertEqual(WakeWordDetector("").phrase, DEFAULT_WAKE_WORD)
        self.assertEqual(WakeWordDetector("   ").phrase, DEFAULT_WAKE_WORD)

    def test_works_for_both_engine_writing_styles(self):
        # Vosk liefert Kleinschreibung ohne Satzzeichen, faster-whisper
        # ganze Saetze mit Grossschreibung und Komma. Beides muss durch
        # dieselbe Schleuse passen.
        vosk_style = "hey ally öffne lunar client"
        whisper_style = "Hey Ally, öffne Lunar Client."
        self.assertEqual(self.command_of(vosk_style), "oeffne lunar client")
        self.assertEqual(self.command_of(whisper_style), "oeffne lunar client")


if __name__ == "__main__":
    unittest.main()
