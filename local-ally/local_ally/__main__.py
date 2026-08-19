"""Einstiegspunkt: ``python -m local_ally``."""

from __future__ import annotations

import argparse
import logging
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="local_ally",
        description="Local Ally - lokaler Sprachassistent",
    )
    parser.add_argument("--debug", action="store_true", help="ausfuehrliche Protokollierung")
    parser.add_argument(
        "--reindex",
        action="store_true",
        help="Programm-Index neu aufbauen und beenden (ohne Oberflaeche)",
    )
    parser.add_argument(
        "--say",
        metavar="TEXT",
        help="Befehl als Text ausfuehren, ohne Mikrofon und Oberflaeche",
    )
    parser.add_argument(
        "--intents",
        action="store_true",
        help="alle verstandenen Absichten samt Beispielen auflisten",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="mit --say: Rueckfragen bei kritischen Aktionen automatisch bejahen",
    )
    args = parser.parse_args(argv)

    from .core.logging_setup import setup_logging

    setup_logging(logging.DEBUG if args.debug else logging.INFO)

    if args.intents:
        return _list_intents()
    if args.reindex:
        return _reindex()
    if args.say:
        return _say(args.say, confirm=args.yes)

    from .core.controller import Controller
    from .ui import run_ui

    controller = Controller()
    try:
        run_ui(controller)
    except KeyboardInterrupt:
        pass
    finally:
        controller.shutdown()
    return 0


def _reindex() -> int:
    """Index im Terminal aufbauen - praktisch fuer den ersten Start und Tests."""
    from .app_index.indexer import AppIndexer
    from .app_index.repository import AppRepository
    from .database import Database

    database = Database()
    indexer = AppIndexer(AppRepository(database))
    count = indexer.rebuild(lambda name, number, total: print(f"[{number}/{total}] {name}"))
    print(f"{count} Programme im Index.")
    database.close()
    return 0


def _list_intents() -> int:
    """Zeigt, was Local Ally versteht - eine Zeile je Absicht."""
    from .intents.catalog import all_specs

    for spec in sorted(all_specs(), key=lambda item: item.id):
        example = spec.examples[0] if spec.examples else spec.templates[0]
        print(f"{spec.id:26} {spec.description:34} z.B. „{example}“")

    _list_custom()
    return 0


def _list_custom() -> None:
    """Dazu die selbst angelegten Funktionen - sie gehen dem Katalog vor."""
    from .custom.models import action_type
    from .custom.repository import CustomCommandRepository
    from .database import Database

    database = Database()
    try:
        commands = CustomCommandRepository(database).all()
    finally:
        database.close()
    if not commands:
        return

    print("\nEigene Funktionen (haben Vorrang):")
    for command in commands:
        state = "" if command.enabled else "  [aus]"
        kind = action_type(command.action)
        print(f"{command.phrase:26} {kind.label:34} {command.target}{state}")


def _say(text: str, confirm: bool = False) -> int:
    """Einen Befehl ohne Sprache ausfuehren - fuer Tests und Fehlersuche."""
    from .core.controller import Controller

    controller = Controller()
    try:
        # Wer den Befehl tippt, hat die Absicht schon geaeussert - das
        # Wake Word waere hier nur im Weg.
        controller.handle_text(text, bypass_wake=True)
        state = controller.state
        print(state.action_text)

        if state.awaiting_confirm and confirm:
            controller.confirm_pending()
            print(state.action_text)
        elif state.awaiting_confirm:
            print("  (Rückfrage offen - mit --yes bestätigen)")

        for position, match in enumerate(state.candidates, start=1):
            print(f"  {position}. {match.app.name}  ({match.score:.2f}, {match.reason})")
        return 0 if state.action_ok else 1
    finally:
        controller.shutdown()


if __name__ == "__main__":
    sys.exit(main())
