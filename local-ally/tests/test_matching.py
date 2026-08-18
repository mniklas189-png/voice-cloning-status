"""Unscharfe Namenssuche."""

from tests.support import unittest  # noqa: F401

from local_ally.app_index.matching import find_matches, is_confident
from local_ally.app_index.models import AppEntry


def app(app_id: int, name: str, aliases=(), weak=(), priority: int = 40) -> AppEntry:
    return AppEntry(
        id=app_id,
        name=name,
        launch_target=f"C:/Programme/{name}.exe",
        source="start_menu",
        priority=priority,
        aliases=list(aliases),
        weak_aliases=list(weak),
    )


APPS = [
    app(1, "Lunar Client", ["client"]),
    app(2, "Discord"),
    app(3, "Discord Canary", ["canary"]),
    app(4, "Spotify"),
    app(5, "Visual Studio Code", ["code"], weak=["vsc"]),
    app(6, "Adobe Photoshop 2024", ["photoshop", "adobe photoshop"]),
    app(7, "gi-inspect-typelib", weak=["git"]),
    app(8, "git", priority=10),
]


class MatchingTests(unittest.TestCase):
    def best(self, spoken: str):
        matches = find_matches(spoken, APPS, threshold=0.68)
        return matches[0].app.name if matches else None

    def test_exact_name(self):
        self.assertEqual(self.best("lunar client"), "Lunar Client")

    def test_misheard_name_still_matches(self):
        self.assertEqual(self.best("lunar klient"), "Lunar Client")
        self.assertEqual(self.best("fotoshop"), "Adobe Photoshop 2024")

    def test_alias_and_short_form(self):
        self.assertEqual(self.best("code"), "Visual Studio Code")
        self.assertEqual(self.best("vs code"), "Visual Studio Code")

    def test_unknown_name_matches_nothing(self):
        self.assertEqual(find_matches("völliger unsinn xyz", APPS, threshold=0.68), [])

    def test_exact_match_wins_over_acronym(self):
        # "gi-inspect-typelib" ergibt das Akronym "git" - der echte Befehl
        # "git" muss trotzdem eindeutig gewinnen.
        matches = find_matches("git", APPS, threshold=0.68)
        self.assertEqual(matches[0].app.name, "git")
        self.assertTrue(is_confident(matches))

    def test_ambiguous_names_are_not_confident(self):
        matches = find_matches("discord", APPS, threshold=0.68)
        self.assertEqual(matches[0].app.name, "Discord")
        self.assertTrue(is_confident(matches), "eindeutiger Name muss gewinnen")

        similar = [app(1, "Grafiktool A"), app(2, "Grafiktool B")]
        matches = find_matches("grafiktool", similar, threshold=0.68)
        self.assertEqual(len(matches), 2)
        self.assertFalse(is_confident(matches), "Gleichstand muss zur Rueckfrage fuehren")

    def test_short_words_do_not_collide_phonetically(self):
        short = [app(1, "bash"), app(2, "bc"), app(3, "ps")]
        matches = find_matches("bash", short, threshold=0.68)
        self.assertEqual(matches[0].app.name, "bash")
        self.assertTrue(is_confident(matches))

    def test_frequently_used_apps_win_a_tie(self):
        rarely = app(1, "Notizen")
        often = app(2, "Notizen")
        often.launch_count = 20
        matches = find_matches("notizen", [rarely, often], threshold=0.68)
        self.assertEqual(matches[0].app.id, 2)


if __name__ == "__main__":
    unittest.main()
