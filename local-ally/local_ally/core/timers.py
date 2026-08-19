"""Timer und Wecker - rein lokal, ohne eigenen Thread.

Faellige Timer werden in :meth:`Controller.pump` geprueft. Das laeuft
ohnehin im UI-Takt und spart einen weiteren Thread, der sich mit dem
Zustand synchronisieren muesste.

Laufende Timer leben nur, solange das Programm laeuft: ein Timer, der einen
Neustart ueberdauert, waere eine Zusage, die Local Ally im ausgeschalteten
Zustand nicht halten kann.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass(slots=True)
class Timer:
    id: int
    seconds: int          # urspruenglich gewuenschte Dauer
    due: float            # Zeitpunkt (monotone Uhr)
    label: str = ""

    def remaining(self, now: float | None = None) -> int:
        """Restzeit in Sekunden, nie negativ."""
        return max(0, int(round(self.due - (now if now is not None else time.monotonic()))))


def format_duration(seconds: int) -> str:
    """Dauer in Worten: 90 -> "1:30 Minuten", 3600 -> "1 Stunde"."""
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds} Sekunden"
    if seconds < 3600:
        minutes, rest = divmod(seconds, 60)
        if rest == 0:
            return f"{minutes} Minute{'n' if minutes != 1 else ''}"
        return f"{minutes}:{rest:02d} Minuten"
    hours, rest = divmod(seconds, 3600)
    minutes = rest // 60
    if minutes == 0:
        return f"{hours} Stunde{'n' if hours != 1 else ''}"
    return f"{hours}:{minutes:02d} Stunden"


def format_clock(seconds: int) -> str:
    """Kompakte Restzeit fuer die Anzeige: ``09:58``."""
    seconds = max(0, int(seconds))
    if seconds >= 3600:
        hours, rest = divmod(seconds, 3600)
        return f"{hours}:{rest // 60:02d}:{rest % 60:02d}"
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


@dataclass
class TimerService:
    _timers: list[Timer] = field(default_factory=list)
    _next_id: int = 1

    def add(self, seconds: int, label: str = "") -> Timer:
        timer = Timer(
            id=self._next_id,
            seconds=int(seconds),
            due=time.monotonic() + int(seconds),
            label=label,
        )
        self._next_id += 1
        self._timers.append(timer)
        self._timers.sort(key=lambda item: item.due)
        return timer

    def active(self) -> list[Timer]:
        return list(self._timers)

    @property
    def count(self) -> int:
        return len(self._timers)

    def cancel(self, timer_id: int | None = None) -> int:
        """Einen Timer oder alle abbrechen. Rueckgabe: Anzahl."""
        if timer_id is None:
            removed = len(self._timers)
            self._timers.clear()
            return removed
        before = len(self._timers)
        self._timers = [timer for timer in self._timers if timer.id != timer_id]
        return before - len(self._timers)

    def take_due(self, now: float | None = None) -> list[Timer]:
        """Faellige Timer entnehmen - sie verschwinden dabei aus der Liste."""
        moment = now if now is not None else time.monotonic()
        due = [timer for timer in self._timers if timer.due <= moment]
        if due:
            self._timers = [timer for timer in self._timers if timer.due > moment]
        return due
