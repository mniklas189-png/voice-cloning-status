"""Tastenkombinationen: lesen, pruefen, verfolgen, anmelden."""

import os
import time

from tests.support import unittest  # noqa: F401

from local_ally.hotkeys import ACTION_MUTE, ACTION_PTT, PRESS, RELEASE
from local_ally.hotkeys.keys import Hotkey, HotkeyError, find_conflicts
from local_ally.hotkeys.manager import HotkeyManager, backend_available
from local_ally.hotkeys.tracker import ComboTracker


class ParsingTests(unittest.TestCase):
    def test_common_notations(self):
        cases = {
            "ctrl+alt+m": "ctrl+alt+m",
            "STRG + ALT + M": "ctrl+alt+m",
            "ctrl-alt-space": "ctrl+alt+space",
            "win+leertaste": "cmd+space",
            "umschalt+f4": "shift+f4",
            "f9": "f9",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(Hotkey.parse(value).normalized(), expected)

    def test_display_is_german(self):
        self.assertEqual(Hotkey.parse("ctrl+alt+m").display(), "Strg + Alt + M")

    def test_errors_are_understandable(self):
        for value in ("", "ctrl", "ctrl+alt", "m", "ctrl+a+b", "ctrl+gibtesnicht"):
            with self.subTest(value=value):
                with self.assertRaises(HotkeyError) as caught:
                    Hotkey.parse(value)
                message = str(caught.exception)
                self.assertTrue(message.endswith("."), message)
                self.assertGreater(len(message), 20, "Meldung zu knapp")

    def test_single_letter_needs_a_modifier(self):
        with self.assertRaises(HotkeyError):
            Hotkey.parse("m")
        self.assertTrue(Hotkey.parse("f13"))  # Funktionstasten gehen allein

    def test_modifiers_must_match_exactly(self):
        hotkey = Hotkey.parse("ctrl+m")
        self.assertTrue(hotkey.matches({"ctrl", "m"}))
        self.assertFalse(hotkey.matches({"ctrl", "shift", "m"}))
        self.assertFalse(hotkey.matches({"m"}))

    def test_conflicts_are_reported_once_per_combination(self):
        messages = find_conflicts({
            ACTION_MUTE: Hotkey.parse("ctrl+alt+m"),
            ACTION_PTT: Hotkey.parse("STRG+ALT+M"),
        })
        self.assertEqual(len(messages), 1)
        self.assertIn(ACTION_MUTE, messages[0])
        self.assertIn(ACTION_PTT, messages[0])

    def test_different_combinations_do_not_conflict(self):
        self.assertEqual(find_conflicts({
            ACTION_MUTE: Hotkey.parse("ctrl+alt+m"),
            ACTION_PTT: Hotkey.parse("ctrl+alt+space"),
        }), [])


class TrackerTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.tracker = ComboTracker(
            {ACTION_MUTE: Hotkey.parse("ctrl+alt+m"),
             ACTION_PTT: Hotkey.parse("ctrl+alt+space")},
            lambda action, phase: self.events.append((action, phase)),
        )

    def press(self, *keys):
        for key in keys:
            self.tracker.press(key)

    def release(self, *keys):
        for key in keys:
            self.tracker.release(key)

    def test_combination_fires_once(self):
        self.press("ctrl", "alt", "m")
        self.assertEqual(self.events, [(ACTION_MUTE, PRESS)])

    def test_key_repeat_does_not_fire_again(self):
        self.press("ctrl", "alt", "m", "m", "m")
        self.assertEqual(self.events.count((ACTION_MUTE, PRESS)), 1)

    def test_release_is_reported_for_push_to_talk(self):
        self.press("ctrl", "alt", "space")
        self.release("space")
        self.assertEqual(self.events, [(ACTION_PTT, PRESS), (ACTION_PTT, RELEASE)])

    def test_releasing_a_modifier_also_ends_the_combination(self):
        self.press("ctrl", "alt", "space")
        self.release("ctrl")
        self.assertEqual(self.events[-1], (ACTION_PTT, RELEASE))

    def test_incomplete_combination_stays_silent(self):
        self.press("ctrl", "m")
        self.press("alt")          # jetzt erst vollstaendig
        self.assertEqual(self.events, [(ACTION_MUTE, PRESS)])

    def test_extra_modifier_blocks_the_combination(self):
        self.press("ctrl", "alt", "shift", "m")
        self.assertEqual(self.events, [])

    def test_both_combinations_stay_apart(self):
        self.press("ctrl", "alt", "space")
        self.release("space")
        self.press("m")
        self.assertEqual(
            self.events,
            [(ACTION_PTT, PRESS), (ACTION_PTT, RELEASE), (ACTION_MUTE, PRESS)],
        )

    def test_reset_releases_active_combinations(self):
        self.press("ctrl", "alt", "space")
        self.tracker.reset()
        self.assertEqual(self.events[-1], (ACTION_PTT, RELEASE))
        self.assertEqual(self.tracker.pressed, set())

    def test_a_failing_receiver_does_not_break_the_keyboard(self):
        def boom(action, phase):
            raise RuntimeError("Empfänger kaputt")

        tracker = ComboTracker({ACTION_MUTE: Hotkey.parse("ctrl+alt+m")}, boom)
        tracker.press("ctrl")
        tracker.press("alt")
        tracker.press("m")          # darf nicht durchschlagen
        self.assertEqual(tracker.active, {ACTION_MUTE})


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.manager = HotkeyManager(lambda a, p: self.events.append((a, p)))
        self.addCleanup(self.manager.stop)

    def test_invalid_input_reports_but_does_not_crash(self):
        status = self.manager.apply({ACTION_MUTE: "ctrl+gibtesnicht"})
        self.assertFalse(status.ok)
        self.assertTrue(status.errors)
        self.assertIn(ACTION_MUTE, status.errors[0])

    def test_conflicting_hotkeys_are_refused(self):
        status = self.manager.apply({ACTION_MUTE: "ctrl+alt+m", ACTION_PTT: "ctrl+alt+m"})
        self.assertFalse(status.ok)
        self.assertFalse(status.active, "bei Konflikt darf nichts angemeldet werden")
        self.assertTrue(any("mehrfach vergeben" in message for message in status.errors))

    def test_disabled_means_inactive_without_error(self):
        status = self.manager.apply({ACTION_MUTE: "ctrl+alt+m"}, enabled=False)
        self.assertFalse(status.active)
        self.assertEqual(status.errors, [])
        self.assertEqual(status.detail, "ausgeschaltet")

    def test_status_explains_a_missing_backend(self):
        # Auf Rechnern ohne pynput muss die Meldung sagen, was fehlt.
        status = self.manager.apply({ACTION_MUTE: "ctrl+alt+m"})
        if not status.available:
            self.assertIn("pynput", status.detail)
        else:
            self.assertTrue(status.active or status.detail)


if __name__ == "__main__":
    unittest.main()


# Dieser Test drueckt echte Tasten - auf einem benutzten Rechner landen sie
# im gerade aktiven Fenster. Er laeuft deshalb nur auf ausdrueckliche
# Anforderung:   LOCAL_ALLY_HOTKEY_E2E=1 python -m unittest ...
@unittest.skipUnless(
    os.environ.get("LOCAL_ALLY_HOTKEY_E2E") == "1" and backend_available()[0],
    "Systemtest der Tastatur nur mit LOCAL_ALLY_HOTKEY_E2E=1",
)
class SystemKeyboardTests(unittest.TestCase):
    """Echter Zuhoerer, echte Tastendruecke - prueft die Betriebssystem-Anbindung."""

    def setUp(self):
        self.events = []
        self.manager = HotkeyManager(lambda a, p: self.events.append((a, p)))
        self.addCleanup(self.manager.stop)
        status = self.manager.apply({ACTION_MUTE: "ctrl+alt+m", ACTION_PTT: "ctrl+alt+space"})
        if not status.active:
            self.skipTest(f"Zuhörer nicht gestartet: {status.detail}")
        time.sleep(0.5)

    def wait_for(self, count, timeout=2.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and len(self.events) < count:
            time.sleep(0.02)

    def test_mute_hotkey_fires(self):
        from pynput.keyboard import Controller, Key

        keyboard = Controller()
        keyboard.press(Key.ctrl); keyboard.press(Key.alt); keyboard.press("m")
        time.sleep(0.2)
        keyboard.release("m"); keyboard.release(Key.alt); keyboard.release(Key.ctrl)
        self.wait_for(2)
        self.assertEqual(self.events[:2], [(ACTION_MUTE, PRESS), (ACTION_MUTE, RELEASE)])

    def test_ptt_stays_pressed_while_the_key_is_held(self):
        from pynput.keyboard import Controller, Key

        keyboard = Controller()
        keyboard.press(Key.ctrl); keyboard.press(Key.alt); keyboard.press(Key.space)
        self.wait_for(1)
        self.assertEqual(self.events, [(ACTION_PTT, PRESS)], "zu früh losgelassen")

        keyboard.release(Key.space); keyboard.release(Key.alt); keyboard.release(Key.ctrl)
        self.wait_for(2)
        self.assertEqual(self.events[-1], (ACTION_PTT, RELEASE))
