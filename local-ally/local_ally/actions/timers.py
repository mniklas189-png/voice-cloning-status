"""Aktionen fuer Timer und Wecker."""

from __future__ import annotations

from ..core.timers import format_clock, format_duration
from ..intents.model import IntentMatch
from .base import ActionContext, ActionResult, register

MAX_TIMERS = 10


@register("timer.start")
def start(match: IntentMatch, context: ActionContext) -> ActionResult:
    if context.timers is None:
        return ActionResult.failed("Timer sind gerade nicht verfügbar.")

    raw = match.slot("duration")
    if not raw.isdigit() or int(raw) <= 0:
        return ActionResult.failed("Auf welche Dauer soll ich den Timer stellen?")
    if context.timers.count >= MAX_TIMERS:
        return ActionResult.failed(f"Es laufen schon {MAX_TIMERS} Timer.")

    seconds = int(raw)
    context.timers.add(seconds)
    return ActionResult.done(f"Timer läuft: {format_duration(seconds)}.")


@register("timer.list")
def show(match: IntentMatch, context: ActionContext) -> ActionResult:
    if context.timers is None or not context.timers.active():
        return ActionResult.done("Es läuft gerade kein Timer.")

    parts = [
        f"{format_clock(timer.remaining())} von {format_duration(timer.seconds)}"
        for timer in context.timers.active()
    ]
    if len(parts) == 1:
        return ActionResult.done(f"Noch {parts[0]}.")
    return ActionResult.done("Es laufen: " + " · ".join(parts))


@register("timer.cancel")
def cancel(match: IntentMatch, context: ActionContext) -> ActionResult:
    if context.timers is None:
        return ActionResult.failed("Timer sind gerade nicht verfügbar.")
    removed = context.timers.cancel()
    if not removed:
        return ActionResult.done("Es lief kein Timer.")
    if removed == 1:
        return ActionResult.done("Timer abgebrochen.")
    return ActionResult.done(f"{removed} Timer abgebrochen.")
