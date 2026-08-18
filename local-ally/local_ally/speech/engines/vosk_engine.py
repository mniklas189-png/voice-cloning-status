"""Vosk: streamende Offline-Erkennung.

Warum Vosk die Vorgabe ist:

* echtes Streaming - Zwischenergebnisse erscheinen beim Sprechen
* eigenes Endpointing, es braucht also keine Pausenerkennung
* das deutsche Kleinmodell ist rund 45 MB gross und laeuft fluessig auf CPU
* keinerlei Netzwerkzugriff nach dem einmaligen Herunterladen

Fuer kurze Kommandos wie "Oeffne Lunar Client" ist das genau richtig.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ...core.paths import vosk_models_dir
from ..base import SAMPLE_RATE, SpeechEngine, SpeechResult

log = logging.getLogger(__name__)

ENGINE_ID = "vosk"


def find_model(configured_path: str = "") -> Path | None:
    """Modellordner bestimmen: erst Einstellung, dann Automatik.

    Ein Vosk-Modellordner enthaelt immer ein Unterverzeichnis ``am`` oder
    ``conf`` - daran erkennen wir ihn, egal wie er heisst.
    """
    if configured_path:
        candidate = Path(configured_path).expanduser()
        if _looks_like_model(candidate):
            return candidate
        log.warning("Konfiguriertes Vosk-Modell nicht gefunden: %s", candidate)

    base = vosk_models_dir()
    if _looks_like_model(base):
        return base
    try:
        for child in sorted(base.iterdir()):
            if child.is_dir() and _looks_like_model(child):
                return child
    except OSError:
        pass
    return None


def _looks_like_model(path: Path) -> bool:
    return path.is_dir() and ((path / "am").is_dir() or (path / "conf").is_dir())


def is_installed() -> bool:
    try:
        import vosk  # noqa: F401
    except ImportError:
        return False
    return True


class VoskEngine(SpeechEngine):
    id = ENGINE_ID
    display_name = "Vosk (streamend, sehr schnell)"

    def __init__(self, model_path: str = "", language: str = "de") -> None:
        self._model_path = model_path
        self._language = language
        self._model = None
        self._recognizer = None

    def start(self) -> None:
        try:
            import vosk
        except ImportError as exc:
            raise RuntimeError(
                "Vosk ist nicht installiert. Installation: pip install vosk"
            ) from exc

        model_dir = find_model(self._model_path)
        if model_dir is None:
            raise RuntimeError(
                "Kein Vosk-Modell gefunden. Lade ein deutsches Modell mit:\n"
                "  python -m local_ally.tools.fetch_vosk_model"
            )

        vosk.SetLogLevel(-1)  # Vosk schreibt sonst sehr gespraechig auf stderr
        if self._model is None:
            log.info("Lade Vosk-Modell: %s", model_dir)
            self._model = vosk.Model(str(model_dir))
        self._recognizer = vosk.KaldiRecognizer(self._model, SAMPLE_RATE)
        self._recognizer.SetWords(False)

    def feed(self, pcm: bytes) -> list[SpeechResult]:
        if self._recognizer is None:
            return []
        if self._recognizer.AcceptWaveform(pcm):
            text = _extract(self._recognizer.Result(), "text")
            return [SpeechResult(text=text, is_final=True)] if text else []
        partial = _extract(self._recognizer.PartialResult(), "partial")
        return [SpeechResult(text=partial, is_final=False)] if partial else []

    def flush(self) -> list[SpeechResult]:
        if self._recognizer is None:
            return []
        text = _extract(self._recognizer.FinalResult(), "text")
        return [SpeechResult(text=text, is_final=True)] if text else []

    def reset(self) -> None:
        if self._recognizer is not None:
            self._recognizer.Reset()

    def stop(self) -> None:
        # Das Modell bleibt geladen: erneutes Einlesen dauert mehrere Sekunden.
        self._recognizer = None


def _extract(payload: str, key: str) -> str:
    try:
        return str(json.loads(payload).get(key, "")).strip()
    except (ValueError, AttributeError):
        return ""
