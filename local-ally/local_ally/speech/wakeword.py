"""Wake-Word-Erkennung auf dem erkannten Text.

Architekturentscheidung
-----------------------
Das Wake Word wird **nicht** im Erkenner geprueft, sondern auf dessen
Ergebnistext. Damit funktioniert es mit jedem Backend gleich - Vosk liefert
streamend Endergebnisse, faster-whisper ganze Aeusserungen, beide landen hier
im selben Code. Ein eigenes Wake-Word-Modell (Porcupine, openWakeWord) waere
genauer, braucht aber ein weiteres Modell, teils eine Lizenz und liefe an der
bestehenden Architektur vorbei.

Der Abgleich ist bewusst unscharf: eine deutsche Spracherkennung schreibt
"Hey Ally" gern als "hey alli", "hey alley" oder "heyally". Verglichen werden
deshalb zusammengezogene Wortfenster - ueber Zeichenaehnlichkeit und die
Koelner Phonetik aus :mod:`local_ally.core.text`.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from ..core import text as textutil

DEFAULT_WAKE_WORD = "Hey Ally"

# Wieviele Woerter vor dem Wake Word toleriert werden ("aehm, hey ally ...")
_MAX_LEAD_TOKENS = 2
# Ab dieser Zeichenaehnlichkeit gilt ein Wortfenster als das Wake Word
_MIN_RATIO = 0.82
# Sehr kurze Wake Words werden strenger geprueft - sonst loest jedes
# zweite Wort aus.
_SHORT_PHRASE_CHARS = 6
_SHORT_MIN_RATIO = 0.92
# Ab dieser Laenge zaehlt auch reiner Gleichklang
_MIN_PHONETIC_CHARS = 6


@dataclass(slots=True)
class WakeMatch:
    """Ein erkanntes Wake Word und der Rest der Aeusserung."""

    spoken: str      # das erkannte Wake Word, so wie es gesprochen wurde
    command: str     # alles danach - leer, wenn nur das Wake Word kam

    @property
    def has_command(self) -> bool:
        return bool(self.command.strip())


class WakeWordDetector:
    """Prueft, ob eine Aeusserung mit dem Wake Word beginnt."""

    def __init__(self, phrase: str = DEFAULT_WAKE_WORD) -> None:
        self.phrase = (phrase or DEFAULT_WAKE_WORD).strip() or DEFAULT_WAKE_WORD
        self._tokens = textutil.normalize(self.phrase).split()
        self._compact = "".join(self._tokens)
        self._phonetic = textutil.koelner_phonetik(self._compact)

    def __repr__(self) -> str:  # hilfreich in Logs und Tests
        return f"<WakeWordDetector {self.phrase!r}>"

    @property
    def is_usable(self) -> bool:
        """Ein Wake Word aus einem oder zwei Zeichen waere unbrauchbar."""
        return len(self._compact) >= 3

    def split(self, spoken_text: str) -> WakeMatch | None:
        """Wake Word abtrennen.

        Gibt ``None`` zurueck, wenn die Aeusserung nicht mit dem Wake Word
        beginnt. Sonst enthaelt das Ergebnis den verbleibenden Befehl - das
        Wake Word selbst wird nie weitergereicht.
        """
        if not self.is_usable:
            return None

        tokens = textutil.normalize(spoken_text).split()
        if not tokens:
            return None

        want = len(self._tokens)
        # Fenster um die erwartete Wortzahl herum: die Erkennung zieht
        # "hey ally" gern zu "heyally" zusammen oder trennt es zusaetzlich.
        widths = sorted({max(1, want - 1), want, want + 1})

        for start in range(min(_MAX_LEAD_TOKENS + 1, len(tokens))):
            for width in widths:
                window = tokens[start : start + width]
                if len(window) < width:
                    continue
                if self._matches("".join(window)):
                    rest = " ".join(tokens[start + width :])
                    return WakeMatch(spoken=" ".join(window), command=rest)
        return None

    def _matches(self, candidate: str) -> bool:
        if not candidate:
            return False
        if candidate == self._compact:
            return True

        minimum = (
            _SHORT_MIN_RATIO if len(self._compact) < _SHORT_PHRASE_CHARS else _MIN_RATIO
        )
        if SequenceMatcher(None, self._compact, candidate).ratio() >= minimum:
            return True

        # Gleichklang - faengt "alli"/"ally" und "hey"/"hei" ab.
        if len(self._compact) >= _MIN_PHONETIC_CHARS and len(candidate) >= 3:
            if textutil.koelner_phonetik(candidate) == self._phonetic:
                return True
        return False
