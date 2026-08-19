"""Schranken gegen eine Fehlerklasse, die sich sonst still wiederholt.

Slint haelt von einem in Python erzeugten Listenmodell nur eine schwache
Referenz, und ein unbekannter Eigenschaftsname wird beim Schreiben
verschluckt. Beides faellt im laufenden Betrieb nicht auf: keine Ausnahme,
nur eine Liste, die ploetzlich leer ist, oder eine Anzeige, die sich nie
mehr aendert.

Deshalb hier zwei Sorten Test:

* **Quelltextpruefungen** - sie laufen ohne installiertes ``slint`` und
  halten die Bruecke auf dem einen sicheren Weg (``ui/store.py``).
* **Laufzeitpruefung** - sie liest die Listen-Eigenschaften aus
  ``state.slint`` und prueft *jede* davon gegen eine erzwungene
  Speicherbereinigung. Eine neue Liste ist damit automatisch mitgeprueft,
  ohne dass jemand diesen Test anfassen muss.
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.support import TempDataDirTestCase, unittest  # noqa: F401

try:
    import slint  # noqa: F401

    SLINT_AVAILABLE = True
except Exception:  # pragma: no cover - haengt von der Installation ab
    SLINT_AVAILABLE = False

PACKAGE = Path(__file__).resolve().parents[1] / "local_ally"
STATE_SLINT = PACKAGE / "ui" / "slint" / "state.slint"
BRIDGE = PACKAGE / "ui" / "bridge.py"
FACADE = PACKAGE / "ui" / "store.py"

# "in-out property <[AppRow]> apps: [];" -> "apps"
_LIST_PROPERTY = re.compile(r"property\s*<\s*\[[^\]]+\]\s*>\s*([A-Za-z0-9_-]+)")


def declared_list_properties() -> list[str]:
    """Alle Listen-Eigenschaften des Stores - direkt aus der .slint-Datei."""
    text = STATE_SLINT.read_text(encoding="utf-8")
    # Nur der Store-Block; andere Globals haben keine Bruecke nach Python.
    store = text.split("export global Store {", 1)[1].split("\n}", 1)[0]
    return sorted(name.replace("-", "_") for name in _LIST_PROPERTY.findall(store))


class SourceGuardTests(unittest.TestCase):
    """Quelltextpruefungen - ohne slint lauffaehig, deshalb immer aktiv."""

    def test_list_models_are_built_only_in_the_store_facade(self):
        offenders = [
            path.relative_to(PACKAGE).as_posix()
            for path in PACKAGE.rglob("*.py")
            if path != FACADE and "ListModel" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(
            offenders, [],
            "slint.ListModel darf nur in ui/store.py entstehen - sonst haelt "
            "niemand das Modell fest und die Liste ist nach der nächsten "
            "Speicherbereinigung leer. Schreibe stattdessen eine gewöhnliche "
            "Liste: store.meine_liste = [...]",
        )

    def test_the_bridge_never_writes_to_the_raw_store(self):
        source = BRIDGE.read_text(encoding="utf-8")
        uses = [line.strip() for line in source.splitlines() if ".window.Store" in line]
        self.assertEqual(
            len(uses), 1,
            "Der rohe Store darf nur einmal vorkommen: beim Bau der Hülle. "
            f"Gefunden: {uses}",
        )
        self.assertIn("UiStore(", uses[0])

    def test_the_state_file_really_declares_lists(self):
        # Falls sich die Schreibweise in state.slint aendert, faellt die
        # Laufzeitpruefung sonst still auf null Eigenschaften zurueck.
        names = declared_list_properties()
        self.assertGreaterEqual(len(names), 8, names)
        self.assertIn("apps", names)
        self.assertIn("custom_commands", names)


@unittest.skipUnless(SLINT_AVAILABLE, "Paket 'slint' ist nicht installiert")
class StoreFacadeTests(TempDataDirTestCase):
    def test_unknown_property_names_are_refused(self):
        from local_ally.ui.bridge import _UI_FILE
        from local_ally.ui.store import UiStore

        window = slint.load_file(str(_UI_FILE)).MainWindow()
        store = UiStore(window.Store)

        store.status = "listening"          # bekannt: geht durch
        self.assertEqual(window.Store.status, "listening")

        with self.assertRaises(AttributeError):
            store.gibt_es_nicht = 1         # Tippfehler: faellt sofort auf

    def test_a_property_that_would_shadow_the_facade_is_refused(self):
        from local_ally.ui.store import UiStore

        class Fake:
            held_models = []      # heisst wie ein Teil der Huelle

        with self.assertRaises(AttributeError) as caught:
            UiStore(Fake())
        self.assertIn("verdecken", str(caught.exception))

    def test_plain_lists_become_models_and_are_held(self):
        import gc

        from local_ally.ui.bridge import _UI_FILE
        from local_ally.ui.store import UiStore

        window = slint.load_file(str(_UI_FILE)).MainWindow()
        store = UiStore(window.Store)
        store.timers = ["09:58 · 10 Minuten"]

        gc.collect()
        self.assertEqual(list(window.Store.timers), ["09:58 · 10 Minuten"])
        self.assertIn("timers", store.held_models)


@unittest.skipUnless(SLINT_AVAILABLE, "Paket 'slint' ist nicht installiert")
class ListSurvivalTests(TempDataDirTestCase):
    """Jede Liste der Oberflaeche gegen eine volle Speicherbereinigung.

    Die Liste der Eigenschaften kommt aus ``state.slint``, nicht aus diesem
    Test: eine neue Liste ist dadurch automatisch abgedeckt.
    """

    def _populated_bridge(self):
        from local_ally.app_index.models import DiscoveredApp
        from local_ally.core.controller import Controller
        from local_ally.custom.models import CustomCommand
        from local_ally.settings import SettingsStore
        from local_ally.ui.bridge import UiBridge

        from tests.fakes import FakeBackend

        settings = SettingsStore()
        settings.settings.index_on_first_start = False
        settings.settings.hotkeys_enabled = False
        controller = Controller(settings_store=settings, backend=FakeBackend())
        self.addCleanup(controller.shutdown)

        controller.repository.replace_all([
            DiscoveredApp(name="Grafik Tool A", launch_target="C:/A.exe",
                          source="start_menu", priority=40),
            DiscoveredApp(name="Grafik Tool B", launch_target="C:/B.exe",
                          source="start_menu", priority=40),
        ])
        controller.custom_repository.save(
            CustomCommand(phrase="videos", action="website", target="https://example.org")
        )
        controller.startup()

        # Jede Liste einmal fuellen: Timer, Vorschlagsliste, Programmauswahl.
        controller.handle_text("stell einen timer auf 5 minuten", bypass_wake=True)
        controller.pump()
        controller.handle_text("öffne grafik tool", bypass_wake=True)
        controller.custom_search_apps("Grafik")

        bridge = UiBridge(controller)
        bridge.render()
        return bridge

    def test_every_declared_list_is_filled_by_the_test_scenario(self):
        # Ohne Inhalt kann eine Liste nicht leer *werden* - der Test darunter
        # waere dann wertlos. Schlaegt das hier fehl, wurde eine neue Liste
        # eingefuehrt: im Szenario oben fuellen.
        bridge = self._populated_bridge()
        empty = [
            name for name in declared_list_properties()
            if len(getattr(bridge.window.Store, name)) == 0
        ]
        self.assertEqual(
            empty, [],
            "Diese Listen sind im Testszenario leer und damit ungeprüft: "
            f"{empty}. Bitte in _populated_bridge() füllen.",
        )

    def test_every_declared_list_survives_a_full_collection(self):
        import gc

        bridge = self._populated_bridge()
        names = declared_list_properties()
        before = {name: len(getattr(bridge.window.Store, name)) for name in names}

        gc.collect()

        after = {name: len(getattr(bridge.window.Store, name)) for name in names}
        self.assertEqual(
            after, before,
            "Nach der Speicherbereinigung fehlen Einträge. Die betroffene "
            "Liste wurde vermutlich am Store vorbei gesetzt, statt über "
            "UiStore (ui/store.py).",
        )

    def test_repeated_renders_do_not_pile_up_models(self):
        # Die Huelle haelt je Eigenschaft genau ein Modell fest - sonst waere
        # aus dem Fehler ein Speicherleck geworden.
        bridge = self._populated_bridge()
        for _ in range(20):
            bridge.controller.state.apps_revision += 1
            bridge.render()
        self.assertLessEqual(
            len(bridge.store.held_models), len(declared_list_properties())
        )


if __name__ == "__main__":
    unittest.main()
