"""Aktionen am Fenster - am aktiven oder an dem eines Programms."""

from __future__ import annotations

from ..intents.model import IntentMatch
from .apps import process_names, remember, resolve_app
from .base import ActionContext, ActionResult, register


def _target(match: IntentMatch, context: ActionContext):
    """Auf welches Fenster zielt der Satz?

    Rueckgabe ``(Prozessname, Beschriftung, Rueckfrage)``. Ohne
    Programmnamen im Satz bleibt es beim aktiven Fenster.
    """
    # Bewusst die rohen Parameter: der Vorgabewert von "app" dient nur der
    # Rueckfrage ("Soll ich das aktive Fenster schließen?") und waere hier
    # ein Programmname, den es nicht gibt.
    spoken = match.slots.get("app", "").strip()
    if not spoken:
        return "", "Fenster", None

    entry, candidates = resolve_app(spoken, context)
    if entry is None:
        if candidates:
            return "", "", ActionResult(
                ok=True, message="Welches Programm meinst du?",
                candidates=candidates, needs_choice=True,
            )
        return "", "", ActionResult.failed(f"Ich kenne kein Programm namens „{spoken}“.")

    remember(context, entry)
    names = process_names(entry, spoken)
    return (names[0] if names else spoken), entry.name, None


@register("window.switch")
def switch(match: IntentMatch, context: ActionContext) -> ActionResult:
    context.backend.window_switch()
    return ActionResult.done("Fenster gewechselt.")


@register("window.minimize")
def minimize(match: IntentMatch, context: ActionContext) -> ActionResult:
    process, label, question = _target(match, context)
    if question is not None:
        return question
    context.backend.window_minimize(process)
    return ActionResult.done(f"{label} minimiert.")


@register("window.maximize")
def maximize(match: IntentMatch, context: ActionContext) -> ActionResult:
    process, label, question = _target(match, context)
    if question is not None:
        return question
    context.backend.window_maximize(process)
    return ActionResult.done(f"{label} maximiert.")


@register("window.close")
def close(match: IntentMatch, context: ActionContext) -> ActionResult:
    process, label, question = _target(match, context)
    if question is not None:
        return question
    context.backend.window_close(process)
    return ActionResult.done(f"{label} geschlossen.")
