# SchachCoach

Eine statische Website zum Schachspielen mit Live-Coach — gebaut für Anfänger.
Läuft vollständig im Browser, ohne Server, ohne Login, ohne externe Bibliotheken.

**Live:** `https://<benutzer>.github.io/voice-cloning-status/chess/`

## Was die Seite kann

| Bereich | Inhalt |
| --- | --- |
| **Spielen** | Partie gegen die eingebaute Engine (11 Stufen, ca. 250–2300 Elo). Der beste Zug wird als Pfeil gezeigt **und** in einem Satz erklärt. Bedrohte Figuren werden markiert. Bei einem groben Fehler warnt der Coach und bietet die Rücknahme an. |
| **Chess.com** | Profil, Wertungen und die zuletzt **beendeten** Partien über die offizielle Public-Data-API. Jede Partie lässt sich Zug für Zug auswerten. |
| **Analyse** | Beliebige PGN oder FEN laden und durchgehen — inklusive Zugbewertung, Engine-Vorschlägen und Verlaufsgrafik. |
| **Hilfe** | Kurzanleitung, Symbol-Legende und die Fair-Play-Regeln. |

## Fair Play — bitte lesen

Chess.com bietet **keine öffentliche Schnittstelle zum Spielen** an. Die verwendete API
(`api.chess.com/pub/...`) ist ausschließlich lesend.

Engine-Hilfe während einer laufenden Partie gegen einen echten Gegner ist auf Chess.com und
Lichess **Betrug** und führt zur Sperrung des Kontos — auch dann, wenn die Hilfe von einer
anderen Website kommt. Diese Seite lädt deshalb bewusst nur abgeschlossene Partien.

Erlaubt und sinnvoll ist beides, was die Seite anbietet: Üben gegen die Engine (dort sind
Tipps ein Feature) und die Auswertung *nach* der Partie.

## Aufbau

```
chess/
├── index.html            Oberfläche (vier Tabs)
├── style.css             Gesamtes Layout und Brettdarstellung
├── js/
│   ├── chess-core.js     Regelwerk: 0x88-Brett, Zuggenerierung, FEN, SAN, PGN
│   ├── engine.js         Bewertung + Alpha-Beta-Suche
│   ├── engine-worker.js  Suche im Web Worker (Fallback: Hauptthread)
│   ├── pieces.js         Figuren als SVG
│   ├── board.js          Interaktives Brett (Ziehen, Klicken, Pfeile, Umwandlung)
│   ├── coach.js          Übersetzt Engine-Zahlen in Sätze und Zugbewertungen
│   ├── chesscom.js       Client für die Chess.com-Public-Data-API
│   └── app.js            Verdrahtung, Partieablauf, Analyse-Ansicht
└── tests/
    ├── perft.mjs         Regelwerk gegen die Perft-Referenzwerte
    └── engine.mjs        Engine: Mattfolgen, SEE, Bewertung, Selbstpartien
```

Keine Abhängigkeiten, kein Build-Schritt. Die Dateien werden so ausgeliefert, wie sie sind.

## Engine

Eigenständige Implementierung, keine übernommene Fremdengine:

- 0x88-Brettdarstellung, Zobrist-Hashing
- Iterative Vertiefung, Alpha-Beta mit Transpositionstabelle
- Quiescence-Suche mit SEE- und Delta-Pruning
- Null-Move-Pruning, Late Move Reductions, Killer- und History-Heuristik
- Getaperte Bewertung: Material, Positionstabellen, Bauernstruktur, Mobilität,
  Königssicherheit, Läuferpaar, Türme auf offenen Linien

Etwa 400 000 Knoten pro Sekunde im Browser. Die Spielstärke-Stufen begrenzen Suchtiefe
und Rechenzeit und wählen auf niedrigen Stufen absichtlich nicht immer den besten Zug —
Stufe 11 spielt immer den besten.

## Tests

```bash
node chess/tests/perft.mjs     # Regelwerk: 6 Referenzstellungen, 16,5 Mio Knoten
node chess/tests/engine.mjs    # Engine: Mattfolgen, Taktik, SEE, Symmetrie, Selbstpartien
```

`perft.mjs` vergleicht die Zuganzahl mit den bekannten Referenzwerten der Chess Programming
Wiki — inklusive Rochade, en passant, Umwandlungen und Fesselungen. `engine.mjs` spielt jede
behauptete Mattfolge nach und prüft, ob am Ende wirklich Schachmatt steht.

## Datenschutz

- Die Engine rechnet auf dem Gerät des Nutzers. Kein Zug verlässt den Browser.
- Von Chess.com werden nur öffentlich abrufbare Daten gelesen. Kein Passwort, kein OAuth.
- Spielstärke, Benutzername und Einstellungen liegen im `localStorage` des Browsers.
