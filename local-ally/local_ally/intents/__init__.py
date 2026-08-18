"""Absichtserkennung: gesprochener Satz -> Absicht mit Parametern.

Der Kern ist eine kleine Mustersprache. Statt für jede Formulierung eine
eigene Regel zu programmieren, beschreibt jede Absicht ein paar Muster:

    "(mach|dreh) * (lauter|lauter machen)"
    "(setz|stell) * lautstaerke auf {level}"

Daraus entsteht ein Vergleicher, der Formulierungsvarianten derselben
Aktion zuordnet und Parameter wie Lautstärke, Programmname oder Suchbegriff
herausschneidet.

* :mod:`.pattern`  - Mustersprache: lesen und vergleichen
* :mod:`.slots`    - Parameter aus dem Satz gewinnen
* :mod:`.catalog`  - alle Absichten als Daten, nicht als Code
* :mod:`.matcher`  - beste passende Absicht bestimmen
"""

from .matcher import IntentMatcher, default_matcher
from .model import IntentMatch, IntentSpec

__all__ = ["IntentMatcher", "default_matcher", "IntentMatch", "IntentSpec"]
