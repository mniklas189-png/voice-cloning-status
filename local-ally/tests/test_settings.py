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
