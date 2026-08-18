"""faster-whisper: hoehere Genauigkeit, dafuer blockweise.

Whisper arbeitet nicht streamend: es braucht eine vollstaendige Aeusserung.
Deshalb sammelt dieser Erkenner Audio, erkennt mit :mod:`..vad` das Ende einer
Aeusserung und rechnet erst dann - typischerweise unter einer Sekunde fuer das
Modell "small" auf einer normalen CPU (int8).

Warum trotzdem "faster-whisper" und nicht ``openai-whisper``: es nutzt
CTranslate2, laeuft dadurch auf der CPU um ein Vielfaches schneller, braucht
weniger Speicher und bringt keine Torch-Installation mit. Es bleibt genauso
offline - das Modell wird einmalig heruntergeladen und danach lokal geladen.
"""

from __future__ import annotations

import logging

from ...core.paths import whisper_models_dir
from ..base import SAMPLE_RATE, SpeechEngine, SpeechResult
from ..vad import VoiceActivityDetector

log = logging.getLogger(__name__)

ENGINE_ID = "faster_whisper"
MODEL_SIZES = ("tiny", "base", "small", "medium", "large-v3")


def is_installed() -> bool:
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return False
    return True


class FasterWhisperEngine(SpeechEngine):
    id = ENGINE_ID
    display_name = "faster-whisper (genauer, etwas langsamer)"

    def __init__(
        self,
        model_size: str = "small",
        language: str = "de",
        compute_type: str = "int8",
    ) -> None:
        self._model_size = model_size if model_size in MODEL_SIZES else "small"
        self._language = language or "de"
        self._compute_type = compute_type or "int8"
        self._model = None
        self._buffer = bytearray()
        self._vad = VoiceActivityDetector()

    def start(self) -> None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "faster-whisper ist nicht installiert. "
                "Installation: pip install faster-whisper"
            ) from exc

        if self._model is None:
            log.info("Lade Whisper-Modell '%s' (%s)", self._model_size, self._compute_type)
            self._model = WhisperModel(
                self._model_size,
                device="cpu",
                compute_type=self._compute_type,
                download_root=str(whisper_models_dir()),
            )
        self.reset()

    def feed(self, pcm: bytes) -> list[SpeechResult]:
        if self._model is None:
            return []

        is_speech, finished = self._vad.process(pcm)
        if is_speech or self._vad.in_speech:
            self._buffer.extend(pcm)

        if not finished:
            # Whisper kann keine Zwischenergebnisse - stattdessen ein Hinweis,
            # dass gerade Sprache ankommt.
            return [SpeechResult(text="...", is_final=False)] if is_speech else []

        return self._transcribe_buffer()

    def flush(self) -> list[SpeechResult]:
        if self._model is None or not self._buffer:
            return []
        return self._transcribe_buffer()

    def reset(self) -> None:
        self._buffer.clear()
        self._vad.reset()

    def stop(self) -> None:
        self.reset()  # Modell bleibt geladen

    def _transcribe_buffer(self) -> list[SpeechResult]:
        audio = bytes(self._buffer)
        self.reset()
        if len(audio) < SAMPLE_RATE:  # weniger als 0,5 Sekunden
            return []

        try:
            text, confidence = self._transcribe(audio)
        except Exception:
            log.exception("Whisper-Erkennung fehlgeschlagen")
            return []
        return [SpeechResult(text=text, is_final=True, confidence=confidence)] if text else []

    def _transcribe(self, audio: bytes) -> tuple[str, float]:
        import numpy as np

        samples = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
        segments, _info = self._model.transcribe(  # type: ignore[union-attr]
            samples,
            language=self._language,
            beam_size=1,          # Kommandos sind kurz - Beam-Suche lohnt nicht
            vad_filter=False,     # die Pausenerkennung machen wir selbst
            condition_on_previous_text=False,  # kein Kontextuebertrag zwischen Befehlen
        )
        parts: list[str] = []
        probabilities: list[float] = []
        for segment in segments:
            parts.append(segment.text.strip())
            probabilities.append(float(getattr(segment, "avg_logprob", 0.0)))

        text = " ".join(part for part in parts if part).strip()
        confidence = 0.0
        if probabilities:
            # avg_logprob liegt typischerweise zwischen -1.5 und 0.
            confidence = max(0.0, min(1.0, 1.0 + sum(probabilities) / len(probabilities)))
        return text, confidence
