"""Aktionen rund um den Ton."""

from __future__ import annotations

from ..app_index.matching import find_matches
from ..app_index.models import AppEntry
from ..intents.model import IntentMatch
from .base import ActionContext, ActionResult, register

# Schrittweiten je nach Formulierung: "etwas lauter" bewegt weniger als
# "deutlich lauter".
STEPS = {"small": 1, "": 2, "large": 5}


def _steps(match: IntentMatch) -> int:
    return STEPS.get(match.slot("degree"), STEPS[""])


@register("audio.volume.up")
def volume_up(match: IntentMatch, context: ActionContext) -> ActionResult:
    steps = _steps(match)
    context.backend.volume_up(steps)
    return ActionResult.done("Lauter." if steps <= 2 else "Deutlich lauter.")


@register("audio.volume.down")
def volume_down(match: IntentMatch, context: ActionContext) -> ActionResult:
    steps = _steps(match)
    context.backend.volume_down(steps)
    return ActionResult.done("Leiser." if steps <= 2 else "Deutlich leiser.")


@register("audio.volume.set")
def volume_set(match: IntentMatch, context: ActionContext) -> ActionResult:
    raw = match.slot("level")
    if not raw.isdigit():
        return ActionResult.failed("Auf welche Lautstärke soll ich stellen?")
    level = max(0, min(100, int(raw)))
    context.backend.volume_set(level)
    return ActionResult.done(f"Lautstärke auf {level} Prozent.")


@register("audio.mute")
def mute(match: IntentMatch, context: ActionContext) -> ActionResult:
    context.backend.volume_mute(True)
    return ActionResult.done("Ton ist stumm.")


@register("audio.unmute")
def unmute(match: IntentMatch, context: ActionContext) -> ActionResult:
    context.backend.volume_mute(False)
    return ActionResult.done("Ton ist wieder an.")


@register("audio.mic.mute")
def mic_mute(match: IntentMatch, context: ActionContext) -> ActionResult:
    """Schaltet das Mikrofon von Local Ally stumm.

    Danach hört der Assistent nichts mehr - auch kein "Mikro wieder an".
    Deshalb sagt die Rueckmeldung, wie es zurueckgeht.
    """
    if context.assistant is None:
        return ActionResult.failed("Das Mikrofon lässt sich gerade nicht schalten.")
    context.assistant.set_mic_muted(True)
    hotkey = context.settings.mute_hotkey or "dem Knopf"
    return ActionResult.done(f"Mikrofon ist stumm. Aufheben mit {hotkey} oder dem Knopf.")


@register("audio.mic.unmute")
def mic_unmute(match: IntentMatch, context: ActionContext) -> ActionResult:
    if context.assistant is None:
        return ActionResult.failed("Das Mikrofon lässt sich gerade nicht schalten.")
    context.assistant.set_mic_muted(False)
    return ActionResult.done("Mikrofon ist wieder aktiv.")


@register("audio.device.switch")
def device_switch(match: IntentMatch, context: ActionContext) -> ActionResult:
    """Audiogerät wechseln.

    Der Name wird hier zugeordnet, nicht im Backend: dafuer gibt es bereits
    die unscharfe Suche aus dem Programm-Index, die auch Umlaute und
    Verhoerer verzeiht ("kopfhoerer" -> "Kopfhörer (Bluetooth)").
    """
    devices = context.backend.audio_devices()
    if not devices:
        context.backend.open_settings("sound")
        return ActionResult.done("Ich habe die Sound-Einstellungen geöffnet.")

    wanted = match.slot("device").strip()
    if not wanted:
        listing = ", ".join(devices[:5])
        return ActionResult.done(f"Auf welches Gerät? Verfügbar: {listing}")

    entries = [
        AppEntry(id=index, name=device, launch_target=device)
        for index, device in enumerate(devices)
    ]
    found = find_matches(wanted, entries, threshold=0.55, limit=1)
    if not found:
        listing = ", ".join(devices[:5])
        return ActionResult.failed(
            f"Kein Audiogerät passt zu „{wanted}“. Verfügbar: {listing}"
        )

    chosen = found[0].app.name
    context.backend.set_audio_device(chosen)
    return ActionResult.done(f"Ton läuft jetzt über {chosen}.")
