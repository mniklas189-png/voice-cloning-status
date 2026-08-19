"""Diktat: Gesprochenes ins aktive Fenster tippen."""

from __future__ import annotations

import re

from ..intents.model import IntentMatch
from .base import ActionContext, ActionResult, register

# Die Auslöser stehen auch im Katalog; hier braucht es sie ein zweites Mal,
# um den Rest des Satzes im *Original* abzuschneiden.
TRIGGERS = ("schreibe", "schreib", "tippe", "tipp")
_LEAD = re.compile(r"^(folgendes|das folgende|mir|mal|bitte)[\s,:;-]+", re.IGNORECASE)

MAX_LENGTH = 2000


def raw_tail(original: str, triggers=TRIGGERS) -> str:
    """Alles nach dem Auslösewort - unveraendert.

    Der Parameter aus dem Muster taugt hier nicht: er ist kleingeschrieben,
    ohne Umlaute und ohne Fuellwoerter. Diktiert wird aber genau das, was
    die Spracherkennung geliefert hat.
    """
    text = (original or "").strip()
    lowered = text.lower()
    for trigger in triggers:
        position = lowered.find(trigger)
        if position < 0:
            continue
        tail = text[position + len(trigger) :].lstrip(" ,:")
        while True:
            shortened = _LEAD.sub("", tail)
            if shortened == tail:
                break
            tail = shortened
        return tail.strip()
    return text


@register("text.type")
def type_text(match: IntentMatch, context: ActionContext) -> ActionResult:
    text = raw_tail(match.text)
    if not text:
        return ActionResult.failed("Was soll ich schreiben?")
    if len(text) > MAX_LENGTH:
        return ActionResult.failed("Das ist mir zu lang zum Tippen.")

    context.backend.type_text(text)
    preview = text if len(text) <= 60 else text[:57] + "..."
    return ActionResult.done(f"Getippt: „{preview}“")
