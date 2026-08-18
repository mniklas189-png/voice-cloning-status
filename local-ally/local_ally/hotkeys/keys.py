"""Tastenkombinationen lesen, pruefen und vergleichen."""

from __future__ import annotations

from dataclasses import dataclass, field

MODIFIERS = ("ctrl", "alt", "shift", "cmd")

# Schreibweisen, die Nutzer erfahrungsgemaess eingeben - deutsch wie englisch.
ALIASES = {
    "control": "ctrl", "strg": "ctrl", "steuerung": "ctrl",
    "option": "alt", "alt_gr": "alt", "altgr": "alt",
    "umschalt": "shift", "umsch": "shift",
    "win": "cmd", "windows": "cmd", "super": "cmd", "meta": "cmd", "command": "cmd",
    "leertaste": "space", "leer": "space", "spacebar": "space",
    "eingabe": "enter", "return": "enter", "enter": "enter",
    "esc": "escape", "entf": "delete", "einfg": "insert",
    "pos1": "home", "ende": "end", "bild_auf": "page_up", "bild_ab": "page_down",
    "tabulator": "tab", "rueck": "backspace", "rück": "backspace",
    "pause": "pause", "druck": "print_screen", "rollen": "scroll_lock",
    "hoch": "up", "runter": "down", "links": "left", "rechts": "right",
}

# Tasten, die auch ohne Zusatztaste als Kuerzel taugen: sie stehen beim
# normalen Tippen nicht im Weg.
STANDALONE_KEYS = frozenset(
    [f"f{n}" for n in range(1, 25)]
    + ["pause", "scroll_lock", "print_screen", "insert", "menu"]
)

NAMED_KEYS = frozenset(
    list(STANDALONE_KEYS)
    + [
        "space", "enter", "escape", "tab", "backspace", "delete", "home", "end",
        "page_up", "page_down", "up", "down", "left", "right", "caps_lock",
        "num_lock", "plus", "minus", "comma", "period",
    ]
)


class HotkeyError(ValueError):
    """Eine Tastenkombination ist unbrauchbar. Die Meldung ist fuer Nutzer."""


@dataclass(frozen=True)
class Hotkey:
    """Eine Tastenkombination, z.B. ``Strg + Alt + M``."""

    key: str
    modifiers: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def parse(cls, value: str) -> "Hotkey":
        """Liest ``"ctrl+alt+m"``. Wirft :class:`HotkeyError` mit Klartext."""
        raw = (value or "").strip()
        if not raw:
            raise HotkeyError("Keine Tastenkombination angegeben.")

        parts = [part.strip().lower().replace(" ", "_") for part in raw.replace("-", "+").split("+")]
        parts = [ALIASES.get(part, part) for part in parts if part]
        if not parts:
            raise HotkeyError("Keine Tastenkombination angegeben.")

        modifiers = {part for part in parts if part in MODIFIERS}
        keys = [part for part in parts if part not in MODIFIERS]

        if not keys:
            raise HotkeyError(
                "Eine Kombination nur aus Strg, Alt oder Umschalt reicht nicht - "
                "es fehlt die eigentliche Taste."
            )
        if len(keys) > 1:
            raise HotkeyError(
                f"Nur eine Taste pro Kombination möglich, gefunden: {', '.join(keys)}."
            )

        key = keys[0]
        if len(key) != 1 and key not in NAMED_KEYS:
            raise HotkeyError(f"Unbekannte Taste „{key}“.")
        if len(key) == 1 and not (key.isalnum() or key in "+-,.#<^"):
            raise HotkeyError(f"Taste „{key}“ lässt sich nicht als Kürzel verwenden.")

        if not modifiers and key not in STANDALONE_KEYS:
            raise HotkeyError(
                f"„{key}“ allein würde beim normalen Tippen auslösen. "
                "Bitte mit Strg, Alt oder Umschalt kombinieren."
            )

        return cls(key=key, modifiers=frozenset(modifiers))

    @classmethod
    def parse_or_none(cls, value: str) -> "Hotkey | None":
        try:
            return cls.parse(value)
        except HotkeyError:
            return None

    def normalized(self) -> str:
        """Einheitliche Schreibweise, z.B. ``ctrl+alt+m``."""
        ordered = [name for name in MODIFIERS if name in self.modifiers]
        return "+".join([*ordered, self.key])

    def display(self) -> str:
        """Beschriftung fuer die Oberflaeche, z.B. ``Strg + Alt + M``."""
        labels = {"ctrl": "Strg", "alt": "Alt", "shift": "Umschalt", "cmd": "Win"}
        ordered = [labels[name] for name in MODIFIERS if name in self.modifiers]
        key = self.key.upper() if len(self.key) == 1 else self.key.replace("_", " ").title()
        return " + ".join([*ordered, key])

    def matches(self, pressed: set[str]) -> bool:
        """Passt die Kombination auf die aktuell gedrueckten Tasten?

        Die Zusatztasten muessen **genau** stimmen: sonst wuerde
        ``Strg + M`` auch bei ``Strg + Umschalt + M`` ausloesen und sich mit
        einer zweiten Kombination ins Gehege kommen.
        """
        if self.key not in pressed:
            return False
        return {name for name in pressed if name in MODIFIERS} == set(self.modifiers)

    def __str__(self) -> str:
        return self.normalized()


def find_conflicts(bindings: dict[str, Hotkey]) -> list[str]:
    """Meldungen zu doppelt vergebenen Kombinationen."""
    seen: dict[str, list[str]] = {}
    for action, hotkey in bindings.items():
        seen.setdefault(hotkey.normalized(), []).append(action)
    return [
        f"„{Hotkey.parse(combo).display()}“ ist mehrfach vergeben: {' und '.join(actions)}."
        for combo, actions in seen.items()
        if len(actions) > 1
    ]
