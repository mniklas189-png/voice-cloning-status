"""Mediensteuerung: Wiedergabe und Titelwechsel."""

from __future__ import annotations

from ..intents.model import IntentMatch
from .base import ActionContext, ActionResult, register


@register("media.playpause")
def playpause(match: IntentMatch, context: ActionContext) -> ActionResult:
    context.backend.media("playpause")
    return ActionResult.done("Wiedergabe umgeschaltet.")


@register("media.next")
def next_track(match: IntentMatch, context: ActionContext) -> ActionResult:
    context.backend.media("next")
    return ActionResult.done("Nächster Titel.")


@register("media.previous")
def previous_track(match: IntentMatch, context: ActionContext) -> ActionResult:
    context.backend.media("previous")
    return ActionResult.done("Vorheriger Titel.")
