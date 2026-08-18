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

## Gestaltung der Oberfläche

Local Ally soll wie ein **Werkzeug** aussehen, nicht wie ein Produkt-Schaufenster.
Daraus folgen ein paar harte Regeln, die in `ui/slint/theme.slint` verankert sind:

* **Keine Farbverläufe, kein Leuchten, keine weichen Schatten.** Ein pulsierender
  Farbkreis als Mikrofonknopf ist die naheliegende Lösung – und die falsche: er
  zeigt nichts an, er dekoriert.
* **Fast einfarbige Palette.** Grau in Grau; Farbe trägt Bedeutung statt
  Dekoration: Rot = Aufnahme läuft, Grün = erledigt, Bernstein = Auswahl,
  Pegel und Kennzahlen. Bedienelemente sind unbunt (helle Fläche auf dunklem
  Grund).
* **Haarlinien statt gestapelter Kästen.** Abschnitte werden durch 1px-Linien
  und Großbuchstaben-Beschriftungen getrennt, nicht durch ineinander
  geschachtelte Karten.
* **Hierarchie über Typografie.** Schriftgröße, -stärke und Laufweite ordnen die
  Seite; Pfade und Kennzahlen stehen in Schreibmaschinenschrift, weil sie
  Daten sind und keine Prosa.

**Zwei Farbschemata, beide aus der Bildmarke.** `Theme.dark` ist die einzige
Schaltstelle: alle Farben in `theme.slint` sind Ausdrücke der Form
`dark ? … : …`, die Brücke setzt das Flag beim Zeichnen aus den
Einstellungen. Dunkel übernimmt Marineblau und Stahlblau der dunklen
Logofassung, Hell das Cremeweiß und Olivschwarz der hellen. Der Akzent ist
damit in beiden Fällen die Markenfarbe.

Konkrete Entscheidungen:

**Aufnahmeknopf und Pegel.** Punkt = aufnehmen, Quadrat = stoppen – die
Bildsprache eines Aufnahmegeräts, sofort lesbar. Daneben ein Pegelband aus
einzelnen Segmenten: daran liest man ab, *wie laut* das Mikrofon hört, und
sieht sofort, ob es überhaupt etwas hört. Ein pulsierender Kreis kann das nicht.

**Keine Symbolschriften.** Emoji sehen je nach installierter Schrift
unterschiedlich aus, fehlen auf manchen Systemen ganz (im Testlauf blieben
zwei Navigationssymbole schlicht leer) und wirken schnell verspielt. Die
Navigation ist deshalb reiner Text mit einem farbigen Aktivbalken; alle
übrigen Zeichen (Auswahlmarkierung, Schalter, Statuspunkt) bestehen aus
Rechtecken.

**Eigene Bedienelemente statt der Standard-Widgets.** Der Stil der
std-widgets wird beim *Übersetzen* der `.slint`-Dateien festgelegt und lässt
sich zur Laufzeit nicht wechseln – ein Umschalten zwischen Hell und Dunkel
hätte damit nur die Hälfte der Oberfläche erreicht. Deshalb bringt
`components/inputs.slint` `TextField` (auf Basis von `TextInput`),
`Segmented` (wenige feste Werte, alle sichtbar) und `OptionList` (wechselnde
Einträge wie Mikrofone) mit; `Theme.Toggle` ersetzt die `CheckBox`, die
zusätzlich die blaue Systemfarbe mitbrächte. Aus `std-widgets` bleiben nur
`ScrollView` und `ListView` – dort geht es um Bildlauf, nicht um Farbe.

Nebeneffekt: Aufklapplisten entfallen ganz. Fünf Whisper-Größen als
Segmentschalter zeigen alle Möglichkeiten auf einen Blick, und die
Mikrofonliste steht offen da, statt sich hinter einem Klick zu verstecken.

**Leere Flächen bekommen eine Aufgabe.** Solange nichts erkannt wurde, erklärt
die Startseite in drei Zeilen die Bedienung, statt zwei leere Abschnitte mit
Gedankenstrichen zu zeigen. Die Fußzeile der Navigation zeigt, wie viele
Programme im Index stehen und wann er zuletzt aufgebaut wurde.

**Die Bildmarke liegt als Vektor bei.** `ui/assets/logo-mark-{light,dark}.svg`
enthält das „A“ als Polygonzug – je eine Fassung pro Farbschema. Als Vektor
bleibt es in jeder Größe scharf, und die Seitenleiste wählt per
`Theme.dark ? … : …` die passende Datei.

Die Dateien sind aus den Logo-Vorlagen **vektorisiert**, nicht nach Augenmaß
gezeichnet: Hintergrund abziehen, zusammenhängende Flächen suchen, deren
Umriss entlang der Pixelkanten verfolgen und mit Douglas-Peucker auf die
Eckpunkte reduzieren. Die Marke besteht aus geraden Kanten, deshalb bleibt
davon exakt der Polygonzug übrig – vier Flächen mit 6, 6, 4 und 6 Ecken.
Aus derselben Quelle stammen die Grundfarben der beiden Schemata:

| | dunkel | hell |
|---|---|---|
| Grund | `#061222` | `#f7f3e7` |
| Marke / Akzent | `#437693` | `#201f19` |
| Text | `#f8f9fb` | `#1e1e18` |

### Zwei Slint-Eigenheiten, die das Design geprägt haben

* Der **Software-Renderer zeichnet keine `Path`-Elemente**. Auf Windows läuft
  Slint mit GPU-Backend und könnte sie darstellen, aber dann wäre das Ergebnis
  in einer headless Umgebung nicht mehr prüfbar. Die gesamte Bildsprache kommt
  deshalb mit Rechtecken aus – und sieht auf jedem Backend identisch aus.
* Die **`ComboBox` zeigte ihren Text aus `current-value`**, nicht aus
  `current-index`: eine Bindung an den Index blieb wirkungslos, sobald das
  Modell erst nach dem Erzeugen des Elements gefüllt wurde. Seit dem Eigenbau
  ist das gegenstandslos, aber die Lehre bleibt – Auswahlen laufen überall
  über den *Wert* (`Actions.select-…(string)`), nicht über einen Index.
* `rotation-angle` gibt es nur für `Image` und `Text` – gedrehte Rechtecke
  (etwa für ein Häkchen) sind keine Option.

## Absichten und Aktionen

Der Weg vom Satz zur Wirkung führt über drei Schichten, die einander nicht
kennen müssen:

```
Text ─► IntentMatcher ─► IntentMatch ─► Aktion ─► SystemBackend ─► Windows
        (intents/)       id + Slots     (actions/)  (backends/)
```

**Warum eine Mustersprache statt fester Befehle.** „Mach es etwas lauter“,
„lauter“, „dreh mal lauter“ und „Lautstärke hoch“ meinen dasselbe. Ein
Befehl pro Formulierung wäre nicht wartbar, ein Sprachmodell überzogen.
Stattdessen beschreibt jede Absicht ein paar Muster:

```
"(mach|dreh|stell|schalt) * (lauter|laut)"
"(setz|stell) * lautstaerke auf {level}"
```

Vier Sonderformen genügen: `(a|b)` Alternativen, `[wort]` optional, `*`
beliebige Wörter, `{name}` Parameter. Verglichen wird auf **Wortebene** mit
Backtracking, nicht mit einem großen regulären Ausdruck – nur so lässt sich
sagen, *wieviel* eines Satzes wörtlich getroffen wurde.

**Daran entscheidet sich der Gleichstand.** Die Bewertung ist
`wörtliche Treffer + 0,5 je selbstprüfendem Parameter + Priorität`.
Selbstprüfend heißt: der Parameter lehnt ab, was nicht passt – eine Zahl,
ein bekannter Ordner. Ein freier Parameter wie ein Programmname passt immer
und zählt deshalb nicht mit. Damit gewinnt von allein:

| Satz | Sieger | warum |
|---|---|---|
| „öffne downloads“ | `files.folder` | bekannter Ordner statt beliebiger Name |
| „schließ das fenster“ | `window.close` | mehr wörtliche Treffer als `app.close` |
| „mach das Mikro aus“ | `audio.mic.mute` | Priorität vor allgemeinem Stummschalten |

**Parameter bieten Lesarten an, statt eine zu erzwingen.** Ein Leser gibt
alle Möglichkeiten zurück („60 prozent“ als zwei Wörter oder als eines), das
Muster probiert sie durch. Ohne das könnte hinter einem freien Parameter
kein Wort mehr stehen – „check ob **steam** läuft“ wäre unmöglich.

**Füllwörter fliegen vor dem Vergleich raus** („bitte“, „mal“, „mein“,
„das“). Dadurch braucht kein Muster Varianten für Höflichkeitsformen.
Steigerungswörter („etwas“, „deutlich“) werden dabei nicht verworfen,
sondern als Parameter `degree` gemerkt – sie ändern die Schrittweite, nicht
die Absicht.

### Aktionen und Backends

Eine Aktion ist eine Funktion mit `@register("bereich.name")`. Sie kennt
weder Slint noch Windows, sondern nur `ActionContext`: Programm-Index,
Einstellungen und ein `SystemBackend`.

Das Backend ist die einzige Stelle mit Plattformwissen. Die Grundfassung
kann **nichts** und sagt das in einem verständlichen Satz; Windows und Linux
überschreiben, was sie können. Dadurch gibt es keinen stillen Fehlschlag –
und in den Tests steht dort eine Attrappe, die nur mitschreibt.

Windows kommt ohne Zusatzpakete aus: Tastencodes über `user32` (Lautstärke,
Medien, Fenster), `rundll32`/`shutdown` für Energie, `ms-settings:`-URIs für
Einstellungsseiten, `tasklist`/`taskkill` für Prozesse, PowerShell für die
Helligkeit, `SHGetKnownFolderPath` für Ordner. Ist `pycaw` installiert, wird
die Lautstärke exakt gesetzt; ohne das Paket regeln Tastendrücke in
Zweierschritten.

Zwei Dinge liegen bewusst in der Aktion statt im Backend, weil sie
plattformunabhängig sind: die Zuordnung eines gesprochenen Gerätenamens auf
ein Audiogerät und die Auflösung eines Programmnamens – beides über dieselbe
unscharfe Suche wie beim Öffnen. „Schließ Spotify“ versteht damit genau die
Namen, die auch „Öffne Spotify“ versteht.

### Rückfrage bei kritischen Aktionen

Herunterfahren, Neustarten, ein Programm oder Fenster schließen: alles, was
Ungespeichertes kosten kann, trägt im Katalog eine Frage. `IntentCommand`
führt solche Absichten nicht aus, sondern legt sie als offene Rückfrage ab;
`ConfirmCommand` löst sie auf – per Sprache oder über die zwei Knöpfe in der
Oberfläche.

Zwei Details, die den Unterschied machen:

* Die Frage nennt den Namen aus dem Index („Soll ich **Spotify** wirklich
  schließen?“), nicht den gesprochenen Wortlaut.
* Als Antwort zählt nur eine **kurze, reine** Ja/Nein-Äußerung. Sonst würde
  „mach es lauter“ als Zustimmung gelesen, weil es mit „mach“ beginnt – ein
  neuer Befehl hebt die Rückfrage stattdessen auf.

Beim Schließen wird `taskkill` **ohne** `/F` verwendet: das Programm darf
noch nach dem Speichern fragen.

## Aktivierung: Wake Word, Stummschaltung, Push-to-Talk

**Das Wake Word wird auf dem Text geprüft, nicht im Modell.**
`speech/wakeword.py` bekommt das fertige Erkennungsergebnis. Damit gilt
derselbe Code für Vosk (streamend, Kleinschreibung) und faster-whisper
(ganze Sätze mit Satzzeichen), und die Schleuse liegt an genau einer Stelle
im Controller. Ein eigenes Weckwort-Modell (Porcupine, openWakeWord) wäre
genauer, brächte aber ein weiteres Modell, teils eine Lizenz und einen
zweiten Erkennungspfad mit.

Der Abgleich ist unscharf wie bei den Programmnamen: verglichen werden
zusammengezogene Wortfenster über Zeichenähnlichkeit und Kölner Phonetik.
„hey alli“, „heyally“ und „hey alley“ wecken damit genauso wie „Hey Ally“,
„hey alaska“ dagegen nicht. Fenster mit einem Wort mehr oder weniger fangen
ab, dass die Erkennung Wörter zusammenzieht oder trennt.

Das Weckwort wird immer **abgeschnitten**: an den Befehlsparser geht nur der
Rest der Äußerung. Kommt das Weckwort allein, merkt sich der Controller für
`wake_word_timeout` Sekunden, dass der nächste Satz ein Befehl sein darf.
Der Ablauf dieser Frist wird in `pump()` geprüft – das läuft ohnehin im
UI-Takt und spart einen eigenen Timer-Thread.

**Stumm wird an der Quelle geschaltet.** `RecognitionService` verwirft die
Audioblöcke, bevor sie den Erkenner erreichen, und setzt ihn beim Umschalten
zurück. So kann im stummen Zustand weder ein Weckwort noch ein Befehl
entstehen – und das Aufheben wirkt sofort, weil das Mikrofon offen bleibt
und kein Modell neu geladen werden muss.

**Push-to-Talk ist Start und Stopp des Erkenners.** Drücken startet die
Aufnahme, Loslassen beendet sie; `flush()` liefert dabei das Endergebnis –
bei Vosk aus dem Streaming-Puffer, bei Whisper durch Transkription des
Aufgenommenen. Weil dieses Ergebnis erst kurz *nach* dem Loslassen
eintrifft, gilt eine Nachfrist von drei Sekunden, in der die Äußerung
weiterhin als Push-to-Talk zählt und das Weckwort umgeht. Ohne diese Frist
würde ausgerechnet der per Taste diktierte Befehl an der Weckwort-Schleuse
hängenbleiben.

**Ein Ort für den sichtbaren Zustand.** Stummschaltung, Weckwort,
Erkennerzustand und Fehler beeinflussen alle dieselbe Statusanzeige.
`Controller._refresh_status()` leitet sie aus allen Einflussgrößen ab,
statt sie an fünf Stellen zu setzen – sonst widersprechen sich die Zustände
früher oder später.

### Globale Tastenkürzel

`pynput` statt `keyboard`: es hört systemweit mit (also auch, wenn Local Ally
nicht im Vordergrund ist), meldet Drücken **und** Loslassen – ohne das gäbe
es kein Push-to-Talk – und braucht unter Windows keine Administratorrechte.

Die Schichten sind getrennt, damit sich das Verhalten ohne echte Tastatur
prüfen lässt:

* `hotkeys/keys.py` liest und prüft Kombinationen (`Hotkey.parse`),
* `hotkeys/tracker.py` ist der Zustandsautomat über gedrückten Tastennamen,
* `hotkeys/manager.py` verbindet ihn mit dem Betriebssystem.

Zwei Entscheidungen verhindern Kollisionen:

* **Zusatztasten müssen exakt stimmen.** `Strg + M` löst nicht bei
  `Strg + Umschalt + M` aus. Sonst überlappten sich zwei Kürzel, sobald eines
  eine Teilmenge des anderen ist.
* **Bei doppelter Belegung wird gar nichts angemeldet.** Eine halb aktive
  Belegung wäre schwerer zu verstehen als keine; die Einstellungsseite nennt
  die betroffene Kombination im Klartext.

Fehlerhafte Eingaben bleiben stehen, wie sie getippt wurden – zusammen mit
der Meldung, was daran nicht stimmt („`m` allein würde beim normalen Tippen
auslösen“). Gültige Eingaben werden vereinheitlicht gespeichert
(`ctrl+alt+m`) und lesbar angezeigt (`Strg + Alt + M`).

Der Tastatur-Thread ruft **keine** Anwendungslogik auf: er legt sein Ereignis
in denselben `EventBus` wie die Spracherkennung, und `pump()` wertet es im
UI-Thread aus. Damit bleibt es bei genau einem Thread, der Zustand ändert.

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

Für Wake Word, Stummschaltung und Push-to-Talk gilt dasselbe Prinzip:
`ComboTracker` kennt nur Tastennamen als Zeichenketten und lässt sich damit
ohne Tastatur prüfen (auch Halten und Loslassen), die Weckwort-Schleuse
arbeitet auf Text, und die Stummschaltung wird im echten Aufnahme-Thread
gegen einen Attrappen-Erkenner geprüft – dort zählt, dass wirklich kein
Block mehr ankommt.

Ein Test drückt echte Tasten und prüft damit die Betriebssystem-Anbindung
mitsamt Tastencode-Übersetzung. Er landet im laufenden System des Nutzers,
deshalb läuft er nur auf ausdrückliche Anforderung:

```bash
LOCAL_ALLY_HOTKEY_E2E=1 python -m unittest tests.test_hotkeys
```

Die beiden Windows-Quellen sind bewusst so gebaut, dass sie sich auch ohne
Windows prüfen lassen: `StartMenuSource` nimmt die zu durchsuchenden
Verzeichnisse entgegen und bekommt im Test einen künstlichen Startmenü-Baum
mit echten `.lnk`-Bytes; `StartAppsSource` bekommt eine vorgegebene
PowerShell-Antwort untergeschoben. So sind Filterregeln, Startziele,
Zweitnamen und das Verhalten bei kaputten oder fehlenden Daten festgenagelt.

Dabei fiel auch ein realer Fehler auf: `Path(...).stem` zerlegt einen
Windows-Pfad nur *auf* Windows. Der Dateiname eines Startziels kommt deshalb
jetzt überall aus `core.paths.target_stem()`.
