"""Sprachmodul: Pausenerkennung, Backend-Verzeichnis und Stummschaltung."""

import struct
import threading
import time
from unittest import mock

from tests.support import TempDataDirTestCase, unittest  # noqa: F401

from local_ally.core.events import EventBus, EventType
from local_ally.settings import Settings
from local_ally.speech.base import SAMPLE_RATE, SpeechEngine, SpeechResult
from local_ally.speech.registry import available_engines, create_engine, engine_ids
from local_ally.speech.service import RecognitionService
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


class FakeMicrophone:
    """Liefert unablaessig denselben Block - schnell und ohne Audiogeraet."""

    def __init__(self, device: str = "", block_size: int = 0) -> None:
        self.started = False

    def start(self) -> None:
        self.started = True

    def read(self, timeout: float = 0.5) -> bytes:
        time.sleep(0.005)
        return block(3000, seconds=0.05)

    def stop(self) -> None:
        self.started = False


class FakeEngine(SpeechEngine):
    id = "fake"
    display_name = "Testerkenner"

    def __init__(self) -> None:
        self.fed = 0
        self.resets = 0
        self._lock = threading.Lock()

    def start(self) -> None:
        pass

    def feed(self, pcm: bytes):
        with self._lock:
            self.fed += 1
        return [SpeechResult(text="öffne discord", is_final=True)]

    def flush(self):
        return []

    def reset(self) -> None:
        with self._lock:
            self.resets += 1

    @property
    def feed_count(self) -> int:
        with self._lock:
            return self.fed


class MuteTests(TempDataDirTestCase):
    """Stumm heisst: der Erkenner bekommt keinen einzigen Block mehr."""

    def setUp(self):
        super().setUp()
        self.bus = EventBus()
        self.engine = FakeEngine()
        patches = [
            mock.patch("local_ally.speech.service.Microphone", FakeMicrophone),
            mock.patch("local_ally.speech.service.create_engine", return_value=self.engine),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.service = RecognitionService(self.bus, Settings)
        self.addCleanup(self.service.shutdown)

    def wait_for(self, predicate, timeout=3.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.02)
        return False

    def finals(self):
        return [e for e in self.bus.drain() if e.type is EventType.SPEECH_FINAL]

    def test_audio_reaches_the_engine_while_active(self):
        self.service.start()
        self.assertTrue(self.wait_for(lambda: self.engine.feed_count > 2), "kein Audio verarbeitet")
        self.assertTrue(self.wait_for(lambda: len(self.finals()) > 0))

    def test_muting_stops_all_processing(self):
        self.service.start()
        self.assertTrue(self.wait_for(lambda: self.engine.feed_count > 2))

        self.service.set_muted(True)
        time.sleep(0.15)
        self.bus.drain()
        before = self.engine.feed_count

        time.sleep(0.25)
        self.assertEqual(self.engine.feed_count, before, "trotz Stummschaltung verarbeitet")
        self.assertEqual(self.finals(), [], "trotz Stummschaltung ein Ergebnis gemeldet")

    def test_unmuting_resumes_and_discards_the_old_buffer(self):
        self.service.start()
        self.assertTrue(self.wait_for(lambda: self.engine.feed_count > 2))
        self.service.set_muted(True)
        time.sleep(0.15)
        resets_before = self.engine.resets

        self.service.set_muted(False)
        after = self.engine.feed_count
        self.assertTrue(self.wait_for(lambda: self.engine.feed_count > after + 1))
        self.assertGreater(self.engine.resets, resets_before, "Puffer wurde nicht verworfen")
