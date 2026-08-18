"""Aktionen am System: Energie, Einstellungen, Anzeige."""

from __future__ import annotations

from ..intents.model import IntentMatch
from .base import ActionContext, ActionResult, register

BRIGHTNESS_STEPS = {"small": 5, "": 10, "large": 25}


@register("system.lock")
def lock(match: IntentMatch, context: ActionContext) -> ActionResult:
    context.backend.lock()
    return ActionResult.done("PC gesperrt.")


@register("system.shutdown")
def shutdown(match: IntentMatch, context: ActionContext) -> ActionResult:
    context.backend.shutdown()
    return ActionResult.done("PC fährt herunter.")


@register("system.restart")
def restart(match: IntentMatch, context: ActionContext) -> ActionResult:
    context.backend.restart()
    return ActionResult.done("PC startet neu.")


@register("system.sleep")
def sleep(match: IntentMatch, context: ActionContext) -> ActionResult:
    context.backend.sleep()
    return ActionResult.done("Energiesparmodus.")


@register("system.screen_off")
def screen_off(match: IntentMatch, context: ActionContext) -> ActionResult:
    context.backend.screen_off()
    return ActionResult.done("Bildschirm aus.")


@register("system.settings")
def settings(match: IntentMatch, context: ActionContext) -> ActionResult:
    context.backend.open_settings("")
    return ActionResult.done("Einstellungen geöffnet.")


@register("system.taskmanager")
def task_manager(match: IntentMatch, context: ActionContext) -> ActionResult:
    context.backend.open_task_manager()
    return ActionResult.done("Task-Manager geöffnet.")


@register("system.wifi")
def wifi(match: IntentMatch, context: ActionContext) -> ActionResult:
    context.backend.open_settings("wifi")
    return ActionResult.done("WLAN-Einstellungen geöffnet.")


@register("system.bluetooth")
def bluetooth(match: IntentMatch, context: ActionContext) -> ActionResult:
    context.backend.open_settings("bluetooth")
    return ActionResult.done("Bluetooth-Einstellungen geöffnet.")


@register("system.brightness.up")
def brightness_up(match: IntentMatch, context: ActionContext) -> ActionResult:
    step = BRIGHTNESS_STEPS.get(match.slot("degree"), BRIGHTNESS_STEPS[""])
    context.backend.brightness_step(step)
    return ActionResult.done("Heller.")


@register("system.brightness.down")
def brightness_down(match: IntentMatch, context: ActionContext) -> ActionResult:
    step = BRIGHTNESS_STEPS.get(match.slot("degree"), BRIGHTNESS_STEPS[""])
    context.backend.brightness_step(-step)
    return ActionResult.done("Dunkler.")


@register("system.brightness.set")
def brightness_set(match: IntentMatch, context: ActionContext) -> ActionResult:
    raw = match.slot("level")
    if not raw.isdigit():
        return ActionResult.failed("Auf welche Helligkeit soll ich stellen?")
    level = max(0, min(100, int(raw)))
    context.backend.brightness_set(level)
    return ActionResult.done(f"Helligkeit auf {level} Prozent.")


@register("system.display.switch")
def display_switch(match: IntentMatch, context: ActionContext) -> ActionResult:
    context.backend.display_mode("switch")
    return ActionResult.done("Anzeige umgeschaltet.")


@register("system.display.mode")
def display_mode(match: IntentMatch, context: ActionContext) -> ActionResult:
    """Modus aus dem Satz ableiten - "erweitern", "duplizieren", "nur pc"."""
    text = match.text.lower()
    if "erweiter" in text:
        mode, label = "extend", "erweitert"
    elif "dupliz" in text or "spiegel" in text:
        mode, label = "duplicate", "dupliziert"
    elif "nur pc" in text or "erster" in text:
        mode, label = "internal", "nur auf dem PC-Bildschirm"
    elif "zweiter" in text or "extern" in text:
        mode, label = "external", "nur auf dem zweiten Bildschirm"
    else:
        mode, label = "switch", "umgeschaltet"
    context.backend.display_mode(mode)
    return ActionResult.done(f"Anzeige {label}.")
