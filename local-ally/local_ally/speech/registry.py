"""Verzeichnis der verfuegbaren Spracherkenner.

Ein neues Backend braucht nur eine Fabrikfunktion und einen Eintrag in
:data:`_ENGINES` - Einstellungen und UI ziehen ihre Liste von hier.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from ..settings import Settings
from .base import EngineInfo, SpeechEngine
from .engines import vosk_engine, whisper_engine

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Registration:
    id: str
    display_name: str
    description: str
    factory: Callable[[Settings], SpeechEngine]
    availability: Callable[[Settings], tuple[bool, str]]


def _vosk_availability(settings: Settings) -> tuple[bool, str]:
    if not vosk_engine.is_installed():
        return False, "Paket fehlt – Installation: pip install vosk"
    if vosk_engine.find_model(settings.vosk_model_path) is None:
        return False, (
            "Kein Modell gefunden – herunterladen mit: "
            "python -m local_ally.tools.fetch_vosk_model"
        )
    return True, "einsatzbereit"


def _whisper_availability(settings: Settings) -> tuple[bool, str]:
    if not whisper_engine.is_installed():
        return False, "Paket fehlt – Installation: pip install faster-whisper"
    return True, f"Modell '{settings.whisper_model_size}' (laedt beim ersten Start)"


_ENGINES: tuple[_Registration, ...] = (
    _Registration(
        id=vosk_engine.ENGINE_ID,
        display_name="Vosk",
        description="Streamend, sehr schnell, kleines deutsches Modell (~45 MB).",
        factory=lambda s: vosk_engine.VoskEngine(s.vosk_model_path, s.language),
        availability=_vosk_availability,
    ),
    _Registration(
        id=whisper_engine.ENGINE_ID,
        display_name="faster-whisper",
        description="Genauer, erkennt ganze Sätze; rechnet nach jeder Äußerung.",
        factory=lambda s: whisper_engine.FasterWhisperEngine(
            s.whisper_model_size, s.language, s.whisper_compute_type
        ),
        availability=_whisper_availability,
    ),
)

DEFAULT_ENGINE_ID = _ENGINES[0].id


def engine_ids() -> list[str]:
    return [registration.id for registration in _ENGINES]


def available_engines(settings: Settings) -> list[EngineInfo]:
    """Alle Backends mit Verfuegbarkeit - auch die nicht installierten.

    Die UI zeigt bewusst auch nicht installierte Backends an, damit der Nutzer
    sieht, was es gibt und was ihm dafuer noch fehlt.
    """
    infos: list[EngineInfo] = []
    for registration in _ENGINES:
        try:
            available, detail = registration.availability(settings)
        except Exception as exc:  # eine kaputte Pruefung darf die UI nicht stoppen
            log.debug("Verfuegbarkeitspruefung fuer %s fehlgeschlagen: %s", registration.id, exc)
            available, detail = False, str(exc)
        infos.append(
            EngineInfo(
                id=registration.id,
                display_name=registration.display_name,
                description=registration.description,
                available=available,
                detail=detail,
            )
        )
    return infos


def create_engine(settings: Settings) -> SpeechEngine:
    """Erzeugt den in den Einstellungen gewaehlten Erkenner."""
    for registration in _ENGINES:
        if registration.id == settings.speech_engine:
            return registration.factory(settings)
    raise RuntimeError(f"Unbekanntes Spracherkennungs-Modell: {settings.speech_engine}")
