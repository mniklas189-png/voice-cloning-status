"""Sehr einfache Sprach-/Pausenerkennung ueber die Signalenergie.

Zweck: Erkenner ohne eigenes Endpointing (faster-whisper) brauchen einen
Hinweis, wann eine Aeusserung zu Ende ist. Eine Lautstaerkeschwelle reicht
dafuer voellig aus - ein neuronales VAD waere hier unnoetiger Ballast.

Die Schwelle passt sich an: die ersten Bloecke dienen als Messung des
Grundrauschens, damit ein lautes Zimmer nicht dauerhaft als Sprache gilt.
"""

from __future__ import annotations

import array
import math
from dataclasses import dataclass

from .base import SAMPLE_RATE


def rms(pcm: bytes) -> float:
    """Effektivwert eines 16-Bit-PCM-Blocks (0 - 32767)."""
    if not pcm:
        return 0.0
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    if not samples:
        return 0.0
    total = sum(float(value) * value for value in samples)
    return math.sqrt(total / len(samples))


@dataclass
class VoiceActivityDetector:
    silence_seconds: float = 0.8      # Pause, die eine Aeusserung beendet
    min_speech_seconds: float = 0.3   # kuerzere Geraeusche gelten als Stoerung
    max_speech_seconds: float = 15.0  # Notbremse gegen Endlosaufnahmen
    noise_blocks: int = 6             # Bloecke zur Messung des Grundrauschens
    absolute_floor: float = 220.0     # unterhalb davon nie Sprache

    _noise_level: float = 0.0
    _measured: int = 0
    speech_seconds: float = 0.0
    silence_run: float = 0.0
    in_speech: bool = False

    def reset(self) -> None:
        self.speech_seconds = 0.0
        self.silence_run = 0.0
        self.in_speech = False

    @property
    def threshold(self) -> float:
        return max(self.absolute_floor, self._noise_level * 2.8)

    def process(self, pcm: bytes) -> tuple[bool, bool]:
        """Block bewerten.

        Rueckgabe ``(ist_sprache, aeusserung_beendet)``.
        """
        duration = len(pcm) / (SAMPLE_RATE * 2)
        level = rms(pcm)

        if self._measured < self.noise_blocks:
            self._measured += 1
            # gleitender Mittelwert des Grundrauschens
            self._noise_level = (
                level if self._noise_level == 0.0 else (self._noise_level * 0.7 + level * 0.3)
            )
            return False, False

        is_speech = level > self.threshold

        if is_speech:
            self.in_speech = True
            self.speech_seconds += duration
            self.silence_run = 0.0
        elif self.in_speech:
            self.silence_run += duration
        else:
            # Rauschpegel langsam nachfuehren, solange niemand spricht
            self._noise_level = self._noise_level * 0.95 + level * 0.05

        finished = self.in_speech and (
            (self.silence_run >= self.silence_seconds
             and self.speech_seconds >= self.min_speech_seconds)
            or self.speech_seconds >= self.max_speech_seconds
        )
        return is_speech, finished

    def level_indicator(self, pcm: bytes) -> float:
        """Aussteuerung 0.0 - 1.0 fuer die Anzeige in der UI."""
        return min(rms(pcm) / 6000.0, 1.0)
