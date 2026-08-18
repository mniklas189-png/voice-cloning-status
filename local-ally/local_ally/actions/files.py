"""Aktionen fuer Ordner und Dateien."""

from __future__ import annotations

from ..intents.model import IntentMatch
from .base import ActionContext, ActionResult, register

FOLDER_LABELS = {
    "downloads": "Downloads", "documents": "Dokumente", "desktop": "Desktop",
    "pictures": "Bilder", "music": "Musik", "videos": "Videos",
    "recycle_bin": "Papierkorb", "home": "Benutzerordner",
}


@register("files.folder")
def open_folder(match: IntentMatch, context: ActionContext) -> ActionResult:
    key = match.slot("folder")
    if not key:
        return ActionResult.failed("Welchen Ordner soll ich öffnen?")
    path = context.backend.known_folder(key)
    context.backend.open_path(path)
    return ActionResult.done(f"{FOLDER_LABELS.get(key, key)} geöffnet.")


@register("files.search")
def search(match: IntentMatch, context: ActionContext) -> ActionResult:
    query = match.slot("query").strip()
    if not query:
        return ActionResult.failed("Wonach soll ich suchen?")
    context.backend.search_files(query)
    return ActionResult.done(f"Ich suche nach „{query}“.")
