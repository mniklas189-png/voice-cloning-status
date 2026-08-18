"""Sprachmodul: Pausenerkennung und Backend-Verzeichnis."""

import struct

from tests.support import TempDataDirTestCase, unittest  # noqa: F401

from local_ally.settings import Settings
from local_ally.speech.base import SAMPLE_RATE
from local_ally.speech.registry import available_engines, create_engine, engine_ids
from local_ally.speech.vad import VoiceActivityDetector, rms


def block(amplitude: int, seconds: float = 0.25) -> bytes:
    count = int(SAMPLE_RATE * seconds)
    # Rechteck statt Sinus: der Effektivwert entspricht genau der Amplitude.
    return struct.pack(f"<{count}h", *([amplitude, -amplitude] * (count // 2)))


class VadTests(unittest.TestCase):
    def test_rms_of_silence_is_zero(self):
        self.assertEqual(rms(block(0)), 0.0)

    def test_speech_then_pause_ends_an_utterance(self):
        vad = VoiceActivityDetector(silence_seconds=0.5, noise_blocks=2)
        for _ in range(2):
            vad.process(block(10))          # Grundrauschen messen
        for _ in range(4):
            speech, finished = vad.process(block(4000))
            self.assertTrue(speech)
            self.assertFalse(finished)
        vad.process(block(0))
        _speech, finished = vad.process(block(0))
        self.assertTrue(finished)

    def test_quiet_room_never_counts_as_speech(self):
        vad = VoiceActivityDetector(noise_blocks=2)
        for _ in range(2):
            vad.process(block(30))
        for _ in range(10):
            speech, finished = vad.process(block(40))
            self.assertFalse(speech)
            self.assertFalse(finished)

    def test_long_speech_is_cut_off(self):
        vad = VoiceActivityDetector(max_speech_seconds=1.0, noise_blocks=1)
        vad.process(block(10))
        finished = False
        for _ in range(8):
            _speech, finished = vad.process(block(5000))
            if finished:
                break
        self.assertTrue(finished)


class RegistryTests(TempDataDirTestCase):
    def test_both_backends_are_listed(self):
        infos = available_engines(Settings())
        self.assertEqual([info.id for info in infos], engine_ids())
        self.assertEqual(engine_ids(), ["vosk", "faster_whisper"])

    def test_unavailable_backends_explain_why(self):
        for info in available_engines(Settings()):
            if not info.available:
                self.assertTrue(info.detail, f"{info.id} ohne Begruendung")

    def test_unknown_backend_raises(self):
        with self.assertRaises(RuntimeError):
            create_engine(Settings(speech_engine="gibt_es_nicht"))

    def test_engine_can_be_created_without_starting(self):
        # Das Erzeugen darf noch kein Modell laden - erst start() tut das.
        engine = create_engine(Settings(speech_engine="vosk"))
        self.assertEqual(engine.id, "vosk")


if __name__ == "__main__":
    unittest.main()
