# Architektur von Local Ally

Dieses Dokument erklärt den Aufbau und – wichtiger – **warum** er so ist.

## Leitgedanken

1. **Alles lokal.** Kein Modul darf zur Laufzeit ins Netz. Einzige Ausnahme
   ist `local_ally/tools/fetch_vosk_model.py`, das ausdrücklich aufgerufen
   werden muss.
2. **Ein Thema, ein Modul.** Nur `ui/` kennt Slint. Nur `speech/` kennt Vosk
   und Whisper. Nur `app_index/sources/` kennt Windows-Interna.
3. **Erweitern ohne Umbauen.** Neues Erkennungs-Backend, neue Index-Quelle,
   neuer Sprachbefehl: jeweils eine neue Datei und ein Eintrag in einer
   Registry.
4. **Nichts Falsches starten.** Bei Zweifeln fragt Local Ally nach, statt zu
   raten.

## Datenfluss

```
Mikrofon ─► SpeechEngine ─► EventBus ─► Controller ─► CommandRegistry ─► Launcher
(Thread)     (Thread)       (Queue)     (UI-Thread)     (UI-Thread)        │
                                            │                              ▼
                                            ▼                          Programm
                                        AppState ─► UiBridge ─► Slint
```

## Threads und warum es eine Warteschlange gibt

Slint läuft im Hauptthread, Audio und Erkennung laufen in eigenen Threads.
Die Python-Anbindung von Slint (Stand 1.9) bietet **kein**
`invoke_from_event_loop`, mit dem ein Hintergrundthread in den UI-Thread
springen könnte.

Deshalb:

* Hintergrundthreads schreiben ausschließlich in `EventBus` (eine
  `queue.Queue`).
* Ein `slint.Timer` im UI-Thread leert die Warteschlange alle 60 ms
  (`UiBridge._tick`) und übergibt sie dem Controller.
* Der Controller verändert den Zustand **nur** in diesem einen Thread.

Nebenwirkung: die gesamte Anwendungslogik ist ohne UI testbar – die Tests
rufen `controller.pump()` direkt auf.

Wichtig für die Stabilität: eine Ausnahme, die aus einem Slint-Callback oder
-Timer entkommt, beendet das Programm hart (Rust-Panik). `UiBridge` fängt
deshalb in `_tick` und in jedem Callback alles ab.

## Warum SQLite

Der Index umfasst je nach PC einige hundert bis über tausend Programme, wird
regelmäßig komplett abgeglichen und soll Nutzungsstatistiken sowie eigene
Namen mitführen. Genau dafür ist SQLite da – Teil der Standardbibliothek,
kein Server, eine Datei.

Alternative Namen liegen in einer **eigenen Tabelle** statt in einer
Textspalte, weil jeder Name einzeln durchsuchbar sein und ein eigenes
Gewicht tragen muss (siehe unten).

`replace_all()` schreibt keinen leeren Index neu, sondern aktualisiert
bestehende Zeilen und löscht am Ende alles, was der aktuelle Scan nicht
gesehen hat. So überleben `launch_count` und selbst vergebene Namen einen
Neuaufbau. Erkennungsmerkmal ist der Zeitstempel des Laufs – deshalb hat er
Mikrosekunden-Auflösung, sonst würden zwei schnell aufeinanderfolgende
Läufe denselben Wert tragen und nichts würde mehr aufgeräumt.

## Warum eine eigene unscharfe Suche

Eine Fuzzy-Bibliothek (rapidfuzz, fuzzywuzzy) misst Zeichenabstände. Die
Fehler einer **deutschen** Spracherkennung sind aber überwiegend
*klangliche*: „klient“ statt „client“, „fotoshop“ statt „photoshop“.

`app_index/matching.py` kombiniert deshalb vier Signale und nimmt das beste:

| Signal | Beispiel | Höchstwert |
|---|---|---|
| exakte Übereinstimmung | „discord“ = „Discord“ | 1.00 |
| gleicher Klang (Kölner Phonetik) | „klient“ ↔ „client“ | 0.95 |
| Wortteilmenge | „discord“ in „Discord Inc.“ | 0.95 |
| Namensanfang | „vsc“ → „VSC“ | 0.97 |
| Zeichenähnlichkeit (`difflib`) | „diskord“ ↔ „Discord“ | 1.00 |

Dazu zwei kleine Boni: Quellenpriorität (max. +0,06) und Nutzungshäufigkeit
(max. +0,04). Sie entscheiden nur bei nahezu gleichwertigen Namen – deshalb
sind sie bewusst *nicht* auf 1,0 gedeckelt, sonst läge ein exakter Treffer
nach dem Bonus mit einem guten Teiltreffer gleichauf.

Fallstricke, die dabei abgesichert sind:

* **Kurze Wörter** teilen sich schnell einen Klangcode („bash“ und „bc“
  ergeben beide `18`). Gleichklang zählt erst ab vier Zeichen und
  dreistelligem Code.
* **Einzelbuchstaben** würden über den Namensanfang zu allem passen –
  daher Mindestlänge 3 und Mindestabdeckung 40 %.
* **Automatische Akronyme** kollidieren („gi-inspect-typelib“ ergibt „git“).
  Sie werden als eigene Alias-Art gespeichert und zählen nur zu 88 %.

**Rückfrage statt Rateversuch:** `is_confident()` verlangt, dass der beste
Treffer mindestens 0,06 Punkte vor dem zweiten liegt. Sonst zeigt die
Oberfläche die Kandidaten an, und der Nutzer antwortet per Klick oder mit
„zwei“ / „die dritte“ / einem genaueren Namen.

Zur Geschwindigkeit: die Suche über 2000 Programme dauert rund 160 ms in
reinem Python. Sollte das je stören, lässt sich `_ratio()` gegen `rapidfuzz`
tauschen, ohne die Logik anzufassen.

## Warum Vosk die Vorgabe ist

| | Vosk | faster-whisper |
|---|---|---|
| Betriebsart | streamend | blockweise nach jeder Äußerung |
| Zwischenergebnisse | ja | nein |
| Modellgröße (Deutsch) | ~45 MB | ~250 MB (small) |
| Endpointing | eingebaut | eigene Pausenerkennung nötig |
| Genauigkeit | gut für kurze Befehle | besser bei ganzen Sätzen |

Für „Öffne Lunar Client“ gewinnt Vosk klar: sofortige Rückmeldung beim
Sprechen und kaum Rechenlast. faster-whisper ist als genauere Alternative
eingebaut und nutzt CTranslate2 statt PyTorch – dadurch deutlich schneller
auf der CPU und ohne Torch-Installation. Für seine Blockverarbeitung liefert
`speech/vad.py` eine einfache Pausenerkennung über die Signalenergie mit
selbstkalibrierendem Grundrauschen; ein neuronales VAD wäre hier unnötiger
Ballast.

Der geladene Erkenner bleibt zwischen zwei Aufnahmen im Speicher – das Laden
dauert Sekunden, das Starten der Aufnahme soll sich sofort anfühlen.

## Warum kein pywin32 / keine COM-Aufrufe

Zwei Windows-Besonderheiten sind ohne zusätzliche Abhängigkeit gelöst:

* **Verknüpfungen (.lnk):** `app_index/sources/lnk.py` liest das
  dokumentierte Format (MS-SHLLINK) direkt. Zum *Starten* wird die
  .lnk-Datei ohnehin an `os.startfile` übergeben – Windows löst Ziel,
  Argumente und Arbeitsverzeichnis selbst auf. Der Parser liefert nur
  Zusatzwissen für Dubletten-Erkennung und Zweitnamen; schlägt er fehl,
  funktioniert der Start trotzdem.
* **Store-/UWP-Apps:** `Get-StartApps` über PowerShell liefert Name und
  AppID, gestartet wird über `shell:AppsFolder\<AppID>`. Das ist der
  offizielle Weg und deckt Win32- und Store-Apps gleichermaßen ab. Ohne
  diese Quelle wäre ein per Store installiertes Spotify unauffindbar.

## Warum es eine Linux-Quelle gibt

`app_index/sources/linux_desktop.py` liest `.desktop`-Dateien. Local Ally ist
für Windows gedacht, aber so lässt sich die ganze Kette – Index, Suche,
Befehl, Start – auf jedem Rechner entwickeln und testen, ohne den
Windows-Code anzufassen. `sources/default_sources()` wählt automatisch.

## Warum regelbasiert und kein Sprachmodell

„Öffne &lt;Programm&gt;“ braucht kein LLM. Der Parser in `commands/` ist
nachvollziehbar, sofort schnell, läuft garantiert offline und lässt sich
Satz für Satz testen. Die Formulierungen stehen gesammelt in
`commands/phrases.py`, damit neue Varianten ergänzt werden können, ohne die
Befehle anzufassen.

Die Reihenfolge in `default_registry()` ist bedeutsam:
`CancelCommand` → `ChoiceCommand` → `OpenAppCommand`. Eine offene Rückfrage
wird zuerst geprüft, sonst würde die Antwort „zwei“ als Programmname
gesucht. Umgekehrt gibt `ChoiceCommand` einen vollständigen neuen Befehl
(„starte discord“) sofort wieder frei.

`match()` erkennt nur und hat keine Nebenwirkungen, `execute()` handelt.
Diese Trennung macht das Parsen einzeln testbar (siehe
`tests/test_commands.py::ParsingTests`).

## Erweitern

**Neuer Sprachbefehl**

```python
# local_ally/commands/volume.py
class VolumeCommand(Command):
    id = "set_volume"
    def match(self, text, context): ...      # Intent oder None
    def execute(self, intent, context): ...  # CommandResult
```
in `commands/registry.py::default_registry()` eintragen – fertig.

**Neue Index-Quelle**

Klasse mit `id`, `display_name`, `priority`, `is_available()` und
`discover()` anlegen (siehe `sources/base.py`) und in
`sources/__init__.py::default_sources()` eintragen. Zusammenführung,
Zweitnamen und Speicherung übernimmt der Indexer.

**Neues Erkennungs-Backend**

Von `speech.base.SpeechEngine` ableiten (`start`, `feed`, `flush`) und in
`speech/registry.py::_ENGINES` eintragen. Die Einstellungsseite listet es
automatisch samt Verfügbarkeitsprüfung.

**Neue UI-Seite**

`.slint`-Datei unter `ui/slint/pages/` anlegen, in `app-window.slint`
importieren, einen `NavItem` und einen `if root.page == N`-Zweig ergänzen.
Zustand kommt über `Store`, Aktionen gehen über `Actions` – beides in
`ui/slint/state.slint`.

## Tests

`unittest` statt `pytest`: die Tests laufen dadurch ohne jede zusätzliche
Installation, auch auf einem frisch aufgesetzten Windows-Rechner. Mit
`pytest` funktionieren sie ebenfalls.

Abgedeckt sind Textnormalisierung und Phonetik, die unscharfe Suche
inklusive ihrer Fallstricke, Zusammenführung und Speicherung des Index, der
.lnk-Parser (mit im Test erzeugten Dateien), Befehlserkennung und
-ausführung (mit ersetztem Launcher), das Ereignis- und Zustandsmodell des
Controllers, die Einstellungen sowie die Übersetzung der `.slint`-Dateien
samt Datenübertragung in die Oberfläche.
