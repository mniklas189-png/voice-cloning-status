"""Eigene Funktionen ausfuehren.

Jede Aktionsart hat genau eine Funktion. Eine neue Art braucht einen
Eintrag in :data:`models.ACTION_TYPES` und hier einen Eintrag im
Verzeichnis - die Oberflaeche und die Erkennung bleiben unveraendert.
"""

from __future__ import annotations

import logging
import re

from ..actions.base import ActionContext, ActionResult
from ..app_index.matching import find_matches, is_confident
from .models import CustomCommand, action_type

log = logging.getLogger(__name__)


def _open_app(command: CustomCommand, context: ActionContext) -> ActionResult:
    from ..app_index import launcher

    # Aus einer beantworteten Rueckfrage steht das Programm bereits fest.
    if context.chosen_app is not None:
        return _launch(context.chosen_app, context)

    apps = context.command.apps()
    if not apps:
        return ActionResult.failed("Der Programm-Index ist noch leer.")

    found = find_matches(
        command.target, apps,
        threshold=context.settings.match_threshold,
        limit=max(context.settings.max_candidates, 1),
    )
    if not found:
        return ActionResult.failed(
            f"„{command.target}“ steht nicht mehr im Programm-Index."
        )
    if not is_confident(found):
        return ActionResult(
            ok=True, message="Welches Programm meinst du?",
            candidates=found, needs_choice=True,
        )

    return _launch(found[0].app, context)


def _launch(entry, context: ActionContext) -> ActionResult:
    from ..app_index import launcher

    outcome = launcher.launch(entry)
    if outcome.ok:
        context.command.repository.note_launch(entry.id)
        context.command.last_app = entry
    return ActionResult(ok=outcome.ok, message=outcome.message, app=entry)


def _open_website(command: CustomCommand, context: ActionContext) -> ActionResult:
    url = command.target.strip()
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", url):
        # Ohne Schema kann Windows die Adresse nicht oeffnen.
        url = f"https://{url}"
    context.backend.open_path(url)
    return ActionResult.done(f"{url} geöffnet.")


def _run_command(command: CustomCommand, context: ActionContext) -> ActionResult:
    context.backend.run_shell(command.target)
    return ActionResult.done(f"Befehl ausgeführt: {command.target}")


def _open_folder(command: CustomCommand, context: ActionContext) -> ActionResult:
    context.backend.open_path(command.target)
    return ActionResult.done(f"{command.target} geöffnet.")


def _type_text(command: CustomCommand, context: ActionContext) -> ActionResult:
    context.backend.type_text(command.target)
    preview = command.target if len(command.target) <= 40 else command.target[:37] + "..."
    return ActionResult.done(f"Getippt: „{preview}“")


def _send_keys(command: CustomCommand, context: ActionContext) -> ActionResult:
    context.backend.send_keys(command.target)
    return ActionResult.done(f"{command.target} gesendet.")


HANDLERS = {
    "app": _open_app,
    "website": _open_website,
    "command": _run_command,
    "folder": _open_folder,
    "text": _type_text,
    "keys": _send_keys,
}


def run(command: CustomCommand, context: ActionContext) -> ActionResult:
    """Eine eigene Funktion ausfuehren."""
    handler = HANDLERS.get(command.action)
    if handler is None:
        return ActionResult.failed(
            f"Die Aktionsart „{command.action}“ kenne ich nicht (mehr)."
        )
    if not command.target.strip():
        label = action_type(command.action).config_label
        return ActionResult.failed(f"Für „{command.phrase}“ fehlt: {label}.")

    from ..actions.backends.base import NotSupported

    try:
        return handler(command, context)
    except NotSupported as exc:
        return ActionResult.failed(str(exc))
    except Exception as exc:
        log.exception("Eigene Funktion %r fehlgeschlagen", command.phrase)
        return ActionResult.failed(f"„{command.phrase}“ hat nicht geklappt: {exc}")
