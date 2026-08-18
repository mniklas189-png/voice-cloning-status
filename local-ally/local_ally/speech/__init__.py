"""Lokale Spracherkennung.

Aufbau:

* :mod:`.base`     - gemeinsame Schnittstelle aller Erkenner
* :mod:`.audio`    - Mikrofonaufnahme (16 kHz, mono, 16 Bit)
* :mod:`.vad`      - einfache Sprach-/Pausenerkennung ueber die Lautstaerke
* :mod:`.engines`  - konkrete Backends (Vosk, faster-whisper)
* :mod:`.registry` - welche Backends sind installiert und einsatzbereit?
* :mod:`.service`  - Aufnahme + Erkennung in einem Hintergrundthread

Alles laeuft ausschliesslich auf dem eigenen Rechner. Es gibt keine
Netzwerkaufrufe zur Laufzeit; lediglich das einmalige Herunterladen eines
Modells benoetigt Internet.
"""

from .base import SAMPLE_RATE, EngineInfo, SpeechEngine, SpeechResult

__all__ = ["SAMPLE_RATE", "EngineInfo", "SpeechEngine", "SpeechResult"]
