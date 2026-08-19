"""Aktionen fuer Programme: oeffnen, schliessen, pruefen, wechseln.

Alle vier greifen auf denselben Programm-Index und dieselbe unscharfe Suche
zurueck wie bisher - deshalb versteht "Schließ Spotify" genau die Namen, die
auch "Öffne Spotify" versteht.
"""

from __future__ import annotations

import logging

from ..app_index.matching import find_matches, is_confident
from ..app_index.models import AppEntry, MatchResult
from ..core import text as textutil
from ..core.paths import target_stem
from ..intents.model import IntentMatch
from ..intents.slots import is_pronoun
from .base import ActionContext, ActionResult, register

log = logging.getLogger(__name__)


def resolve_app(spoken: str, context: ActionContext) -> tuple[AppEntry | None, list[MatchResult]]:
    """Gesprochenen Namen im Programm-Index nachschlagen.

    Rueckgabe: ``(eindeutiger Treffer, Vorschlaege)``. Ist eine Rueckfrage
    bereits beantwortet, steht das Ergebnis im Kontext und wird direkt
    genommen - ohne erneute Suche.
    """
    if context.chosen_app is not None:
        return context.chosen_app, []
    spoken = (spoken or "").strip()
    if not spoken:
        return None, []

    # "Öffne Discord" ... "mach ihn zu": Fuerwoerter meinen das zuletzt
    # betroffene Programm.
    if is_pronoun(spoken):
        return context.command.last_app, []

    settings = context.settings
    results = find_matches(
        spoken,
        context.command.apps(),
        threshold=settings.match_threshold,
        limit=max(settings.max_candidates, 1),
    )
    if results and is_confident(results):
        return results[0].app, results
    return None, results


def _lookup(match: IntentMatch, context: ActionContext) -> tuple[AppEntry | None, list[MatchResult], str]:
    """Wie :func:`resolve_app`, zusaetzlich mit dem gesprochenen Namen."""
    spoken = match.slot("app").strip()
    if context.chosen_app is not None:
        return context.chosen_app, [], context.chosen_app.name
    entry, results = resolve_app(spoken, context)
    return entry, results, spoken


def remember(context: ActionContext, entry: AppEntry | None) -> None:
    """Das zuletzt betroffene Programm merken - fuer Fuerwoerter."""
    if entry is not None:
        context.command.last_app = entry


def process_names(entry: AppEntry | None, spoken: str) -> list[str]:
    """Moegliche Prozessnamen zu einem Programm.

    Der Index kennt das Startziel, das aber nicht immer der laufende Prozess
    ist (Discord startet ueber "Update.exe"). Deshalb kommen Startziel,
    Anzeigename und Zweitnamen alle in die Auswahl.
    """
    candidates: list[str] = []
    if entry is not None:
        stem = target_stem(entry.launch_target)
        if stem:
            candidates.append(stem)
        candidates.append(textutil.compact(entry.name))
        candidates.extend(textutil.compact(alias) for alias in entry.aliases)
        tokens = textutil.significant_tokens(entry.name)
        if tokens:
            candidates.append(tokens[0])
    if spoken:
        candidates.append(textutil.compact(spoken))

    seen: set[str] = set()
    unique: list[str] = []
    for candidate in candidates:
        key = candidate.lower()
        if key and key not in seen and len(key) >= 2:
            seen.add(key)
            unique.append(candidate)
    return unique


def _running_match(context: ActionContext, names: list[str]) -> str | None:
    """Welcher der Namen laeuft gerade?"""
    running = {
        textutil.compact(process.rsplit(".", 1)[0]): process
        for process in context.backend.running_processes()
    }
    for name in names:
        found = running.get(textutil.compact(name))
        if found:
            return found
    return None


def _ask(results: list[MatchResult], spoken: str) -> ActionResult:
    if not results:
        return ActionResult.failed(f"Ich habe kein Programm namens „{spoken}“ gefunden.")
    return ActionResult(
        ok=True,
        message="Welches Programm meinst du?",
        candidates=results,
        needs_choice=True,
    )


@register("app.open")
def open_app(match: IntentMatch, context: ActionContext) -> ActionResult:
    from ..app_index import launcher

    entry, results, spoken = _lookup(match, context)
    if not spoken:
        return ActionResult.failed("Welches Programm soll ich öffnen?")
    if not context.command.apps():
        return ActionResult.failed("Der Programm-Index ist noch leer. Bitte einmal aktualisieren.")

    # Eine beantwortete Rueckfrage wird ausgefuehrt - auch wenn sonst
    # nachgefragt wuerde. Sonst entstuende eine Schleife.
    decided = context.chosen_app is not None
    if entry is None or (not context.settings.auto_execute and not decided):
        if entry is not None:
            return ActionResult(
                ok=True, message=f"Soll ich „{entry.name}“ starten?",
                candidates=results, needs_choice=True,
            )
        return _ask(results, spoken)

    remember(context, entry)
    outcome = launcher.launch(entry)
    if outcome.ok:
        context.command.repository.note_launch(entry.id)
    return ActionResult(ok=outcome.ok, message=outcome.message, app=entry)


@register("app.close")
def close_app(match: IntentMatch, context: ActionContext) -> ActionResult:
    entry, results, spoken = _lookup(match, context)
    if not spoken:
        return ActionResult.failed("Welches Programm soll ich schließen?")
    if entry is None and results:
        return _ask(results, spoken)

    remember(context, entry)
    names = process_names(entry, spoken)
    label = entry.name if entry is not None else spoken
    running = _running_match(context, names)
    if running is None:
        if entry is None:
            return ActionResult.failed(
                f"Ich kenne kein Programm namens „{spoken}“ - und es läuft auch keines."
            )
        return ActionResult.failed(f"{label} läuft gerade nicht.")

    closed = context.backend.close_process(running)
    if closed:
        return ActionResult(ok=True, message=f"{label} wird geschlossen.", app=entry)
    return ActionResult.failed(f"{label} ließ sich nicht schließen.")


@register("app.running")
def app_running(match: IntentMatch, context: ActionContext) -> ActionResult:
    entry, results, spoken = _lookup(match, context)
    if not spoken:
        return ActionResult.failed("Welches Programm meinst du?")

    remember(context, entry)
    names = process_names(entry, spoken)
    label = entry.name if entry is not None else spoken
    running = _running_match(context, names)
    if running:
        return ActionResult.done(f"Ja, {label} läuft.")
    return ActionResult.done(f"Nein, {label} läuft gerade nicht.")


@register("app.switch")
def switch_app(match: IntentMatch, context: ActionContext) -> ActionResult:
    entry, results, spoken = _lookup(match, context)
    if not spoken:
        return ActionResult.failed("Zu welchem Programm soll ich wechseln?")
    if entry is None and results:
        return _ask(results, spoken)

    remember(context, entry)
    label = entry.name if entry is not None else spoken
    for name in process_names(entry, spoken):
        if context.backend.focus_process(name):
            return ActionResult.done(f"{label} ist im Vordergrund.")
    if entry is None:
        return ActionResult.failed(f"Ich kenne kein Programm namens „{spoken}“.")
    return ActionResult.failed(f"{label} ist gerade nicht offen.")
