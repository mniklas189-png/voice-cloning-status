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
    args = parser.parse_args(argv)

    from .core.logging_setup import setup_logging

    setup_logging(logging.DEBUG if args.debug else logging.INFO)

    if args.reindex:
        return _reindex()
    if args.say:
        return _say(args.say)

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


def _say(text: str) -> int:
    """Einen Befehl ohne Sprache ausfuehren - fuer Tests und Fehlersuche."""
    from .core.controller import Controller

    controller = Controller()
    try:
        controller.handle_text(text)
        state = controller.state
        print(state.action_text)
        for position, match in enumerate(state.candidates, start=1):
            print(f"  {position}. {match.app.name}  ({match.score:.2f}, {match.reason})")
        return 0 if state.action_ok else 1
    finally:
        controller.shutdown()


if __name__ == "__main__":
    sys.exit(main())
