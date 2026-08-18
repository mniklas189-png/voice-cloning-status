"""Mikrofonaufnahme.

``sounddevice`` (PortAudio) ist bewusst die einzige Audio-Abhaengigkeit:
plattformuebergreifend, liefert rohe 16-Bit-Bloecke ohne Konvertierung und
kommt unter Windows ohne zusaetzliche Treiber aus.

Fehlt das Paket, laesst sich Local Ally trotzdem starten - die UI meldet dann
lediglich, dass kein Mikrofon verfuegbar ist. Das ist wichtig, damit App-Index
und Einstellungen auch ohne Audio nutzbar bleiben.
"""

from __future__ import annotations

import logging
import queue
from dataclasses import dataclass
from typing import Any

from .base import BLOCK_SIZE, CHANNELS, SAMPLE_RATE

log = logging.getLogger(__name__)


class AudioError(RuntimeError):
    """Mikrofon nicht verfuegbar oder nicht zu oeffnen."""


@dataclass(slots=True)
class InputDevice:
    index: int
    name: str
    channels: int


def _import_sounddevice() -> Any:
    try:
        import sounddevice  # type: ignore[import-not-found]
    except Exception as exc:  # ImportError, aber auch OSError bei fehlendem PortAudio
        raise AudioError(
            "Das Paket 'sounddevice' ist nicht verfügbar. "
            "Installation: pip install sounddevice"
        ) from exc
    return sounddevice


def is_available() -> bool:
    try:
        _import_sounddevice()
    except AudioError:
        return False
    return True


def list_input_devices() -> list[InputDevice]:
    """Alle Eingabegeraete. Leere Liste, wenn kein Audio verfuegbar ist."""
    try:
        sd = _import_sounddevice()
        devices = sd.query_devices()
    except Exception as exc:  # AudioError, aber auch PortAudio-Fehler
        log.warning("Mikrofone konnten nicht abgefragt werden: %s", exc)
        return []

    result: list[InputDevice] = []
    for index, device in enumerate(devices):
        channels = int(device.get("max_input_channels", 0))
        if channels > 0:
            result.append(InputDevice(index=index, name=str(device.get("name", f"Geraet {index}")), channels=channels))
    return result


def resolve_device(name_or_index: str) -> int | str | None:
    """Geraeteangabe aus den Einstellungen in etwas fuer sounddevice uebersetzen."""
    value = (name_or_index or "").strip()
    if not value:
        return None  # Standardgeraet des Systems
    if value.isdigit():
        return int(value)
    return value


class Microphone:
    """Nimmt auf und legt PCM-Bloecke in eine Warteschlange.

    Der PortAudio-Callback laeuft in einem eigenen Thread und darf niemals
    blockieren - deshalb wird dort ausschliesslich in die Queue geschrieben.
    """

    def __init__(self, device: str = "", block_size: int = BLOCK_SIZE) -> None:
        self._device = resolve_device(device)
        self._block_size = block_size
        self._queue: "queue.Queue[bytes]" = queue.Queue(maxsize=200)
        self._stream = None
        self._overflows = 0

    def start(self) -> None:
        sd = _import_sounddevice()
        try:
            self._stream = sd.RawInputStream(
                samplerate=SAMPLE_RATE,
                blocksize=self._block_size,
                device=self._device,
                dtype="int16",
                channels=CHANNELS,
                callback=self._callback,
            )
            self._stream.start()
        except Exception as exc:  # PortAudio-Fehler sind nicht typisiert
            raise AudioError(f"Mikrofon konnte nicht geöffnet werden: {exc}") from exc
        log.info("Mikrofon gestartet (%s Hz, Geraet=%s)", SAMPLE_RATE, self._device or "Standard")

    def _callback(self, indata, frames, time_info, status) -> None:  # noqa: ANN001
        if status:
            log.debug("Audio-Status: %s", status)
        try:
            self._queue.put_nowait(bytes(indata))
        except queue.Full:
            self._overflows += 1  # Erkennung haengt hinterher - Block verwerfen

    def read(self, timeout: float = 0.5) -> bytes | None:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def stop(self) -> None:
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception as exc:  # beim Herunterfahren nicht eskalieren
                log.debug("Fehler beim Schliessen des Mikrofons: %s", exc)
        with self._queue.mutex:
            self._queue.queue.clear()
        if self._overflows:
            log.info("%d Audiobloecke verworfen (Erkennung zu langsam)", self._overflows)
            self._overflows = 0
