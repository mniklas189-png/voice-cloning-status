"""Reihenfolge und Auswahl der Befehle.

Die Reihenfolge ist Absicht: eine offene Rueckfrage wird zuerst geprueft.
Sonst wuerde die Antwort "zwei" als Programmname durchgereicht.
"""

from __future__ import annotations

import logging
from typing import Iterable, Sequence

from .base import Command, CommandContext, CommandResult

log = logging.getLogger(__name__)


class CommandRegistry:
    def __init__(self, commands: Iterable[Command] | None = None) -> None:
        self._commands: list[Command] = list(commands or ())

    def register(self, command: Command) -> None:
        self._commands.append(command)

    @property
    def commands(self) -> Sequence[Command]:
        return tuple(self._commands)

    def handle(self, text: str, context: CommandContext) -> CommandResult | None:
        """Ersten passenden Befehl ausfuehren.

        ``None`` bedeutet: kein Befehl fuehlt sich zustaendig - der Satz war
        vermutlich kein Kommando.
        """
        if not text or not text.strip():
            return None

        for command in self._commands:
            try:
                intent = command.match(text, context)
            except Exception:
                log.exception("Befehl %s konnte den Text nicht pruefen", command.id)
                continue
            if intent is None:
                continue
            try:
                return command.execute(intent, context)
            except Exception as exc:
                log.exception("Befehl %s fehlgeschlagen", command.id)
                return CommandResult.failure(f"Befehl fehlgeschlagen: {exc}", intent)
        return None


def default_registry() -> CommandRegistry:
    from .choice import CancelCommand, ChoiceCommand
    from .open_app import OpenAppCommand

    return CommandRegistry([CancelCommand(), ChoiceCommand(), OpenAppCommand()])
