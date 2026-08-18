"""Normalisierung und deutsche Phonetik."""

from tests.support import ROOT, unittest  # noqa: F401  (setzt sys.path)

from local_ally.core import text


class NormalizeTests(unittest.TestCase):
    def test_umlauts_and_case(self):
        self.assertEqual(text.normalize("Öffne Größe"), "oeffne groesse")

    def test_removes_versions_and_brackets(self):
        self.assertEqual(text.normalize("Visual Studio Code (64-bit) v1.85.2"), "visual studio code")

    def test_camel_case_is_split(self):
        self.assertEqual(text.normalize("LunarClient"), "lunar client")

    def test_significant_tokens_drop_noise_and_numbers(self):
        self.assertEqual(text.significant_tokens("Adobe Photoshop 2024"), ["adobe", "photoshop"])

    def test_significant_tokens_never_empty(self):
        self.assertEqual(text.significant_tokens("64 bit"), ["64", "bit"])

    def test_compact(self):
        self.assertEqual(text.compact("Visual Studio Code"), "visualstudiocode")


class PhoneticTests(unittest.TestCase):
    def test_typical_german_misspellings_share_a_code(self):
        pairs = [("client", "klient"), ("photoshop", "fotoshop"), ("word", "wort")]
        for left, right in pairs:
            with self.subTest(pair=(left, right)):
                self.assertEqual(text.koelner_phonetik(left), text.koelner_phonetik(right))

    def test_different_words_differ(self):
        self.assertNotEqual(text.koelner_phonetik("discord"), text.koelner_phonetik("spotify"))

    def test_letters_at_word_end_are_not_skipped(self):
        # Regression: eine Pruefung auf "" in "csz" ist immer wahr und hat
        # den letzten Buchstaben verschluckt.
        self.assertTrue(text.koelner_phonetik("discord").endswith("2"))

    def test_digits_only_gives_empty_code(self):
        self.assertEqual(text.koelner_phonetik("2024"), "")

    def test_phonetic_key_uses_all_tokens(self):
        self.assertEqual(text.phonetic_key("Lunar Client"), text.phonetic_key("lunar klient"))


if __name__ == "__main__":
    unittest.main()
