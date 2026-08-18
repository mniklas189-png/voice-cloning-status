"""Aktionen am aktiven Fenster."""

from __future__ import annotations

from ..intents.model import IntentMatch
from .base import ActionContext, ActionResult, register


@register("window.switch")
def switch(match: IntentMatch, context: ActionContext) -> ActionResult:
    context.backend.window_switch()
    return ActionResult.done("Fenster gewechselt.")


@register("window.minimize")
def minimize(match: IntentMatch, context: ActionContext) -> ActionResult:
    context.backend.window_minimize()
    return ActionResult.done("Fenster minimiert.")


@register("window.maximize")
def maximize(match: IntentMatch, context: ActionContext) -> ActionResult:
    context.backend.window_maximize()
    return ActionResult.done("Fenster maximiert.")


@register("window.close")
def close(match: IntentMatch, context: ActionContext) -> ActionResult:
    context.backend.window_close()
    return ActionResult.done("Fenster geschlossen.")
