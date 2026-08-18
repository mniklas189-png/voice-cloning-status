"""Sprachbefehle: erkannter Text -> Absicht -> Aktion.

Bewusst regelbasiert und ohne Sprachmodell. Fuer "Oeffne <Programm>" ist ein
LLM nicht noetig, und ein regelbasierter Parser ist nachvollziehbar, sofort
schnell und laeuft garantiert offline. Die Schnittstelle
(:class:`~local_ally.commands.base.Command`) ist so geschnitten, dass spaeter
ein anderer Interpreter danebengestellt werden kann, ohne die UI anzufassen.
"""

from .base import Command, CommandContext, CommandResult, Intent
from .registry import CommandRegistry, default_registry

__all__ = [
    "Command",
    "CommandContext",
    "CommandResult",
    "Intent",
    "CommandRegistry",
    "default_registry",
]
