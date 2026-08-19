"""Einstellungen laden, speichern und gegen kaputte Dateien absichern."""

from tests.support import TempDataDirTestCase, unittest  # noqa: F401

from local_ally.settings import Settings, SettingsStore


class SettingsTests(TempDataDirTestCase):
    def test_defaults_are_german_and_local(self):
        settings = Settings()
        self.assertEqual(settings.language, "de")
        self.assertEqual(settings.speech_engine, "vosk")

    def test_roundtrip(self):
        store = SettingsStore()
        store.update(speech_engine="faster_whisper", whisper_model_size="medium")
        self.assertEqual(SettingsStore().settings.whisper_model_size, "medium")

    def test_unknown_keys_are_ignored(self):
        path = self.data_dir / "settings.json"
        path.write_text('{"speech_engine": "vosk", "aus_der_zukunft": 42}', encoding="utf-8")
        self.assertEqual(SettingsStore().settings.speech_engine, "vosk")

    def test_broken_file_falls_back_to_defaults(self):
        (self.data_dir / "settings.json").write_text("{kaputt", encoding="utf-8")
        self.assertEqual(SettingsStore().settings, Settings())

    def test_update_ignores_unknown_fields(self):
        store = SettingsStore()
        store.update(gibt_es_nicht=1)
        self.assertFalse(hasattr(store.settings, "gibt_es_nicht"))


if __name__ == "__main__":
    unittest.main()


class BrokenValueTests(TempDataDirTestCase):
    """Die Datei ist von Hand editierbar - unsinnige Werte dürfen nichts kaputtmachen."""

    def load(self, payload: dict):
        import json

        (self.data_dir / "settings.json").write_text(json.dumps(payload), encoding="utf-8")
        return SettingsStore().settings

    def test_wrong_types_fall_back_to_defaults(self):
        settings = self.load({
            "wake_word_timeout": "acht",
            "match_threshold": "hoch",
            "whisper_model_size": 5,
            "max_candidates": None,
        })
        self.assertEqual(settings.wake_word_timeout, Settings().wake_word_timeout)
        self.assertEqual(settings.match_threshold, Settings().match_threshold)
        self.assertEqual(settings.whisper_model_size, Settings().whisper_model_size)
        self.assertEqual(settings.max_candidates, Settings().max_candidates)

    def test_readable_booleans_are_accepted(self):
        settings = self.load({"wake_word_enabled": "ja", "auto_execute": 0, "ptt_enabled": "true"})
        self.assertTrue(settings.wake_word_enabled)
        self.assertFalse(settings.auto_execute)
        self.assertTrue(settings.ptt_enabled)

    def test_numbers_arrive_as_numbers(self):
        settings = self.load({"wake_word_timeout": "12", "max_candidates": "3"})
        self.assertEqual(settings.wake_word_timeout, 12.0)
        self.assertEqual(settings.max_candidates, 3)

    def test_values_are_kept_in_sensible_bounds(self):
        settings = self.load({"match_threshold": 5.0, "max_candidates": 0, "wake_word_timeout": 0.1})
        self.assertLessEqual(settings.match_threshold, 1.0)
        self.assertGreaterEqual(settings.max_candidates, 1)
        self.assertGreaterEqual(settings.wake_word_timeout, 1.0)

    def test_a_wrong_value_does_not_stop_the_assistant(self):
        self.load({"wake_word_timeout": "acht", "wake_word_enabled": True})
        from local_ally.core.controller import Controller

        store = SettingsStore()
        store.settings.index_on_first_start = False
        store.settings.hotkeys_enabled = False
        controller = Controller(settings_store=store)
        try:
            controller.state.listening = True
            controller._arm_wake()          # hat vorher mit TypeError abgebrochen
            self.assertTrue(controller.state.wake_armed)
        finally:
            controller.shutdown()
