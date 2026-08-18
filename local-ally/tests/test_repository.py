"""App-Index: Speichern, Zusammenfuehren, Suchen."""

from tests.support import TempDataDirTestCase, unittest  # noqa: F401

from local_ally.app_index.indexer import AppIndexer, merge_discovered
from local_ally.app_index.models import DiscoveredApp
from local_ally.app_index.repository import AppRepository, generate_aliases
from local_ally.database import Database


class FakeSource:
    id = "fake"
    display_name = "Testquelle"
    priority = 40

    def __init__(self, apps):
        self._apps = apps

    def is_available(self):
        return True

    def discover(self):
        return list(self._apps)


class BrokenSource(FakeSource):
    id = "broken"

    def discover(self):
        raise RuntimeError("kaputt")


def discovered(name, target, source="start_menu", priority=40, **kwargs):
    return DiscoveredApp(
        name=name, launch_target=target, source=source, priority=priority, **kwargs
    )


class AliasTests(unittest.TestCase):
    def test_acronyms_are_marked_weak(self):
        aliases = dict(generate_aliases("Visual Studio Code", [], "C:/Code.exe"))
        self.assertEqual(aliases.get("vsc"), "acronym")
        self.assertEqual(aliases.get("code"), "auto")

    def test_shell_targets_do_not_produce_path_aliases(self):
        aliases = [alias for alias, _kind in generate_aliases("Spotify", [], "shell:AppsFolder\\X!Y")]
        self.assertEqual(aliases, ["Spotify"])


class MergeTests(unittest.TestCase):
    def test_same_name_from_two_sources_is_merged(self):
        merged = merge_discovered([
            discovered("Discord", "C:/Users/x/Discord.lnk", "start_menu", 40),
            discovered("Discord", "C:/Programme/Discord/Discord.exe", "registry_uninstall", 20),
        ])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].source, "start_menu")  # hoehere Prioritaet gewinnt

    def test_identical_targets_are_merged(self):
        merged = merge_discovered([
            discovered("Discord", "C:/App/Discord.exe", "registry_app_paths", 30),
            discovered("Discord Client", "C:/App/Discord.exe", "path", 10),
        ])
        self.assertEqual(len(merged), 1)
        self.assertIn("Discord Client", merged[0].aliases)

    def test_different_programs_stay_separate(self):
        merged = merge_discovered([
            discovered("Discord", "C:/A/Discord.exe"),
            discovered("Discord Canary", "C:/B/DiscordCanary.exe"),
        ])
        self.assertEqual(len(merged), 2)

    def test_entries_without_target_are_dropped(self):
        self.assertEqual(merge_discovered([discovered("Leer", "")]), [])


class RepositoryTests(TempDataDirTestCase):
    def setUp(self):
        super().setUp()
        self.db = Database()
        self.repo = AppRepository(self.db)

    def tearDown(self):
        self.db.close()
        super().tearDown()

    def test_replace_all_writes_apps_and_aliases(self):
        self.repo.replace_all([discovered("Visual Studio Code", "C:/Code.exe")])
        apps = self.repo.all_apps()
        self.assertEqual(len(apps), 1)
        self.assertIn("code", apps[0].aliases)
        self.assertIn("vsc", apps[0].weak_aliases)

    def test_second_run_removes_vanished_apps(self):
        self.repo.replace_all([discovered("Alt", "C:/Alt.exe"), discovered("Neu", "C:/Neu.exe")])
        self.repo.replace_all([discovered("Neu", "C:/Neu.exe")])
        self.assertEqual([app.name for app in self.repo.all_apps()], ["Neu"])

    def test_launch_count_survives_reindex(self):
        self.repo.replace_all([discovered("Discord", "C:/Discord.exe")])
        app_id = self.repo.all_apps()[0].id
        self.repo.note_launch(app_id)
        self.repo.replace_all([discovered("Discord", "C:/Discord.exe")])
        self.assertEqual(self.repo.all_apps()[0].launch_count, 1)

    def test_user_alias_survives_reindex(self):
        self.repo.replace_all([discovered("Visual Studio Code", "C:/Code.exe")])
        app_id = self.repo.all_apps()[0].id
        self.repo.add_user_alias(app_id, "Editor")
        self.repo.replace_all([discovered("Visual Studio Code", "C:/Code.exe")])
        self.assertIn("Editor", self.repo.all_apps()[0].aliases)

    def test_search_finds_by_alias(self):
        self.repo.replace_all([discovered("Visual Studio Code", "C:/Code.exe")])
        self.assertEqual(len(self.repo.search_prefix("code")), 1)
        self.assertEqual(len(self.repo.search_prefix("gibtesnicht")), 0)

    def test_indexer_survives_a_broken_source(self):
        indexer = AppIndexer(
            self.repo,
            sources=[BrokenSource([]), FakeSource([discovered("Discord", "C:/Discord.exe")])],
        )
        self.assertEqual(indexer.rebuild(), 1)

    def test_indexer_reports_progress(self):
        seen = []
        indexer = AppIndexer(self.repo, sources=[FakeSource([discovered("A", "C:/A.exe")])])
        indexer.rebuild(lambda name, number, total: seen.append((name, number, total)))
        self.assertEqual(seen, [("Testquelle", 1, 1)])

    def test_last_index_timestamp_is_stored(self):
        self.repo.replace_all([discovered("A", "C:/A.exe")])
        self.assertTrue(self.repo.last_index_time())


if __name__ == "__main__":
    unittest.main()
