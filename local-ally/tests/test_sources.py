"""Index-Quellen.

Schwerpunkt sind die beiden Windows-Quellen: sie lassen sich auf einem
Linux-Rechner nicht ausfuehren, ihr Verhalten aber sehr wohl festnageln.
Das Startmenue bekommt ein kuenstliches Verzeichnis mit echten
.lnk-Bytes, ``Get-StartApps`` eine vorgegebene PowerShell-Antwort.
"""

import json
import subprocess
from unittest import mock

from tests.support import TempDataDirTestCase, unittest  # noqa: F401
from tests.test_lnk import build_lnk

from local_ally.app_index.sources.linux_desktop import DesktopEntrySource
from local_ally.app_index.sources.path_executables import PathExecutablesSource
from local_ally.app_index.sources.windows_start_apps import StartAppsSource
from local_ally.app_index.sources.windows_start_menu import StartMenuSource


class StartMenuTests(TempDataDirTestCase):
    """Verknuepfungen im Startmenue."""

    def setUp(self):
        super().setUp()
        self.menu = self.data_dir / "Start Menu" / "Programs"
        (self.menu / "Discord Inc").mkdir(parents=True)

        (self.menu / "Lunar Client.lnk").write_bytes(
            build_lnk(r"C:\Users\ich\AppData\Local\Lunar Client\Lunar Client.exe")
        )
        (self.menu / "Discord Inc" / "Discord.lnk").write_bytes(
            build_lnk(r"C:\Users\ich\AppData\Local\Discord\app.exe", r"C:\Discord", "--start")
        )
        # Beiwerk, das nicht in den Index gehoert
        (self.menu / "Uninstall Lunar Client.lnk").write_bytes(build_lnk(r"C:\uninst.exe"))
        (self.menu / "Handbuch.lnk").write_bytes(build_lnk(r"C:\hilfe.chm"))
        # Andere Dateitypen: .url zaehlt, .txt nicht
        (self.menu / "Webmail.url").write_text("[InternetShortcut]\nURL=https://example.invalid\n")
        (self.menu / "notizen.txt").write_text("kein Programm")

        self.source = StartMenuSource([self.menu])
        self.apps = {app.name: app for app in self.source.discover()}

    def test_finds_shortcuts_including_subfolders(self):
        self.assertIn("Lunar Client", self.apps)
        self.assertIn("Discord", self.apps)

    def test_ignores_uninstaller_help_and_other_files(self):
        for name in ("Uninstall Lunar Client", "Handbuch", "notizen"):
            self.assertNotIn(name, self.apps)

    def test_internet_shortcuts_are_kept(self):
        self.assertIn("Webmail", self.apps)

    def test_launches_the_shortcut_itself(self):
        # Windows loest Ziel, Argumente und Arbeitsverzeichnis selbst auf -
        # deshalb ist das Startziel die .lnk-Datei, nicht die .exe.
        app = self.apps["Lunar Client"]
        self.assertTrue(app.launch_target.endswith("Lunar Client.lnk"))
        self.assertEqual(app.launch_kind, "path")

    def test_target_filename_becomes_an_alias(self):
        # "Discord.lnk" zeigt auf "app.exe" - der Dateiname des Ziels ist
        # das Zusatzwissen, das der Parser liefert.
        self.assertIn("app", self.apps["Discord"].aliases)
        self.assertEqual(self.apps["Discord"].working_dir, r"C:\Discord")

    def test_broken_shortcut_does_not_stop_the_scan(self):
        (self.menu / "Kaputt.lnk").write_bytes(b"keine gueltige Verknuepfung")
        names = {app.name for app in self.source.discover()}
        self.assertIn("Kaputt", names)      # ohne Zielwissen, aber startbar
        self.assertIn("Lunar Client", names)

    def test_priority_marks_it_as_a_strong_source(self):
        self.assertEqual(self.source.priority, 40)


class StartAppsTests(unittest.TestCase):
    """Get-StartApps: Startmenue-Liste von Windows, inklusive Store-Apps."""

    def _run(self, payload, returncode=0, stdout=None):
        text = json.dumps(payload) if stdout is None else stdout
        completed = subprocess.CompletedProcess(
            args=[], returncode=returncode, stdout=text, stderr=""
        )
        with mock.patch(
            "local_ally.app_index.sources.windows_start_apps.subprocess.run",
            return_value=completed,
        ):
            return list(StartAppsSource().discover())

    def test_store_app_is_launched_through_the_shell(self):
        apps = self._run([
            {"Name": "Spotify", "AppID": "SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify"}
        ])
        self.assertEqual(len(apps), 1)
        self.assertEqual(apps[0].launch_kind, "shell")
        self.assertEqual(
            apps[0].launch_target,
            "shell:AppsFolder\\SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify",
        )

    def test_app_id_tail_becomes_an_alias(self):
        apps = self._run([{"Name": "Spotify - Musik", "AppID": "SpotifyAB.SpotifyMusic_x!Spotify"}])
        self.assertIn("Spotify", apps[0].aliases)

    def test_classic_programs_are_included_too(self):
        apps = self._run([{"Name": "Steam", "AppID": "Valve.Steam.lnk"}])
        self.assertEqual(apps[0].name, "Steam")
        self.assertEqual(apps[0].aliases, [])  # keine AppID mit "!"

    def test_single_object_answer_is_accepted(self):
        # ConvertTo-Json liefert bei genau einem Treffer kein Array.
        apps = self._run({"Name": "Discord", "AppID": "Discord.lnk"})
        self.assertEqual([app.name for app in apps], ["Discord"])

    def test_noise_is_filtered(self):
        apps = self._run([
            {"Name": "Discord", "AppID": "a!b"},
            {"Name": "Discord deinstallieren", "AppID": "c!d"},
            {"Name": "", "AppID": "e!f"},
            {"Name": "Ohne AppID", "AppID": ""},
        ])
        self.assertEqual([app.name for app in apps], ["Discord"])

    def test_failed_powershell_call_yields_nothing(self):
        self.assertEqual(self._run(None, returncode=1, stdout=""), [])
        self.assertEqual(self._run(None, stdout="kein json"), [])

    def test_missing_powershell_is_survivable(self):
        with mock.patch(
            "local_ally.app_index.sources.windows_start_apps.subprocess.run",
            side_effect=FileNotFoundError("powershell.exe fehlt"),
        ):
            self.assertEqual(list(StartAppsSource().discover()), [])

    def test_it_outranks_the_other_sources(self):
        # Windows' eigene Liste ist die verlaesslichste Quelle.
        self.assertGreater(StartAppsSource().priority, StartMenuSource([]).priority)


class PathSourceTests(TempDataDirTestCase):
    def test_finds_executables_and_skips_the_rest(self):
        folder = self.data_dir / "bin"
        folder.mkdir()
        (folder / "mein-werkzeug").write_text("#!/bin/sh\n")
        (folder / "mein-werkzeug").chmod(0o755)
        (folder / "readme").write_text("nicht ausfuehrbar")

        with mock.patch.dict("os.environ", {"PATH": str(folder)}):
            names = {app.name for app in PathExecutablesSource().discover()}
        self.assertIn("mein-werkzeug", names)
        self.assertNotIn("readme", names)


class DesktopSourceTests(TempDataDirTestCase):
    def test_parses_entries_and_strips_field_codes(self):
        folder = self.data_dir / "applications"
        folder.mkdir()
        (folder / "firefox.desktop").write_text(
            "[Desktop Entry]\nType=Application\nName=Firefox\nExec=/usr/bin/firefox %u\n",
            encoding="utf-8",
        )
        (folder / "versteckt.desktop").write_text(
            "[Desktop Entry]\nType=Application\nName=Versteckt\nExec=x\nNoDisplay=true\n",
            encoding="utf-8",
        )

        with mock.patch(
            "local_ally.app_index.sources.linux_desktop.desktop_dirs", return_value=[folder]
        ):
            apps = {app.name: app for app in DesktopEntrySource().discover()}

        self.assertEqual(apps["Firefox"].launch_target, "/usr/bin/firefox")
        self.assertEqual(apps["Firefox"].launch_kind, "command")
        self.assertNotIn("Versteckt", apps)


if __name__ == "__main__":
    unittest.main()
