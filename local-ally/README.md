# Local Ally

Ein **lokaler Sprachassistent für Windows**. Local Ally hört zu, erkennt
Sprache auf dem eigenen Rechner und startet Programme:

> „Öffne Lunar Client“ · „Starte Discord“ · „Spotify öffnen“

Kein Cloud-Dienst, kein Konto, keine Datenübertragung. Die Spracherkennung,
der Programm-Index und alle Einstellungen liegen ausschließlich auf dem
eigenen PC.

---

## Schnellstart

```bash
# 1. Abhängigkeiten installieren
pip install -r requirements.txt

# 2. Deutsches Sprachmodell laden (einmalig, ca. 45 MB)
python -m local_ally.tools.fetch_vosk_model

# 3. Starten
python run.py
```

Beim ersten Start durchsucht Local Ally den PC nach installierten Programmen
und legt einen lokalen Index an. Danach: auf **Sprechen** klicken und
„Öffne Discord“ sagen.

### Ohne Mikrofon ausprobieren

```bash
python -m local_ally --reindex               # Programm-Index aufbauen
python -m local_ally --intents               # alles auflisten, was verstanden wird
python -m local_ally --say "öffne discord"    # Befehl als Text ausführen
python -m local_ally --say "mach es lauter"
python -m local_ally --say "schließ spotify" --yes   # Rückfragen bejahen
```

---

## Oberfläche

Drei Seiten, gebaut mit [Slint](https://slint.dev):

| Seite | Inhalt |
|---|---|
| **Start** | Status, Aufnahmeknopf mit Pegelband, erkannter Text, ausgeführte Aktion und – bei mehreren Treffern – die Vorschlagsliste |
| **Programme** | Der lokale App-Index als Tabelle: Name, Startziel, Quelle; Suche und „Index aktualisieren“ |
| **Einstellungen** | Farbschema (hell/dunkel), Aktivierung und Hotkeys, Speech-to-Text-Modell mit Verfügbarkeit, Modelldetails, Mikrofon, Verhalten |

**Hell und dunkel** – beide Schemata stammen aus der Bildmarke: dunkel das
Marineblau mit Stahlblau, hell das Cremeweiß mit Olivschwarz. Umschalten in
den Einstellungen unter „Erscheinungsbild“; die Wahl wird lokal gespeichert.
Das Logo liegt als Vektor in `local_ally/ui/assets/` (eine Fassung je
Schema); die Grundfarben `#061222` / `#437693` und `#f7f3e7` / `#201f19`
stammen direkt daraus.

Gestaltet als Werkzeug, nicht als Schaufenster: dunkle, fast einfarbige
Oberfläche, Farbe nur wo sie etwas bedeutet (Rot = Aufnahme, Grün = erledigt,
Bernstein = Auswahl), Trennung durch Haarlinien statt durch gestapelte Karten.
Punkt und Quadrat auf dem Aufnahmeknopf, ein Pegelband aus Segmenten – die
Bildsprache eines Aufnahmegeräts. Die Begründungen stehen im Abschnitt
[Gestaltung der Oberfläche](ARCHITECTURE.md#gestaltung-der-oberfläche).

---

## Aktivierung: Wake Word, Stummschaltung, Push-to-Talk

Drei Wege, Local Ally anzusprechen – einzeln oder kombiniert, alles in den
Einstellungen unter **Aktivierung und Hotkeys**:

| | Wirkung |
|---|---|
| **Wake Word** | Befehle laufen erst nach dem Weckwort. Standard „Hey Ally“, frei änderbar. Das Weckwort wird abgeschnitten und landet nie im Befehl. |
| **Stummschaltung** | Globales Tastenkürzel (Standard `Strg+Alt+M`). Stumm heißt: kein Ton erreicht die Erkennung – weder Weckwort noch Befehl. |
| **Push-to-Talk** | Optional. Local Ally hört nur, solange die Taste gehalten wird (Standard `Strg+Alt+Leertaste`), und umgeht dabei das Weckwort. |

Beide Kürzel wirken systemweit, also auch wenn Local Ally im Hintergrund
liegt. Dafür wird `pynput` gebraucht; fehlt es, läuft alles Übrige weiter und
die Einstellungsseite sagt, was fehlt.

Beides geht in einer Äußerung oder in zweien:

```
„Hey Ally, öffne Lunar Client“      → sofort ausgeführt
„Hey Ally“ … „öffne Discord“        → weckt, dann Befehl (8 s Zeitfenster)
```

Die Startseite zeigt jederzeit, woran man ist: **Warte auf Wake Word**,
**Ich höre zu** oder **Mikrofon stumm**. Was ohne Weckwort gesagt wurde,
erscheint zurückgenommen als „ohne Wake Word verworfen“ – so sieht man, dass
zugehört wurde, ohne dass etwas passiert.

---

## Spracherkennung

Zwei Backends, umschaltbar in den Einstellungen:

| Modell | Eigenschaften | Wann sinnvoll |
|---|---|---|
| **Vosk** (Vorgabe) | streamend, Zwischenergebnisse beim Sprechen, deutsches Modell ~45 MB, eigenes Endpointing | kurze Befehle – der Normalfall |
| **faster-whisper** | genauer, erkennt ganze Sätze, rechnet nach jeder Äußerung | schwierige Namen, Diktat später einmal |

Deutsch ist von Anfang an die eingestellte Sprache. Beide Backends laufen
vollständig offline; lediglich das Herunterladen eines Modells braucht
einmalig Internet.

Fehlt ein Backend, sagt die Einstellungsseite genau, was fehlt und wie es
installiert wird – das Programm startet trotzdem.

Das Wake Word funktioniert mit beiden Backends gleich: es wird auf dem
erkannten *Text* geprüft, nicht im Modell. Vosk liefert dabei
Kleinschreibung ohne Satzzeichen, faster-whisper ganze Sätze – beides läuft
durch dieselbe Schleuse.

**Ein weiteres Modell ergänzen:** eine Klasse von
`local_ally.speech.base.SpeechEngine` ableiten und in
`local_ally/speech/registry.py` eintragen. Mehr ist nicht nötig.

---

## Programme erkennen

Der App-Index wird aus mehreren Quellen zusammengeführt (siehe
`local_ally/app_index/sources/`):

| Priorität | Quelle | Was sie liefert |
|---|---|---|
| 45 | `Get-StartApps` (PowerShell) | die Startmenü-Liste von Windows selbst – **inklusive Store-/UWP-Apps** wie Spotify |
| 40 | Startmenü-Verknüpfungen | alle `.lnk`/`.url`-Dateien in Benutzer- und System-Startmenü |
| 30 | Registry `App Paths` | was Windows bei „Ausführen“ startet |
| 20 | Registry `Uninstall` | die Liste „Apps & Features“, gefiltert um Treiber und Laufzeiten |
| 10 | `PATH` | Kommandozeilenwerkzeuge ohne Startmenü-Eintrag |

Gespeichert wird in **SQLite** (`%LOCALAPPDATA%\LocalAlly\local_ally.sqlite3`):

* Programmname, Startziel und Startart (`path`, `shell`, `uri`, `command`)
* Quelle und Priorität, Arbeitsverzeichnis, Symbol
* **alternative Namen** in einer eigenen Tabelle (Dateiname, bereinigter
  Name, Akronym, selbst vergebene Namen)
* wie oft ein Programm gestartet wurde

Der Index entsteht beim ersten Start und lässt sich jederzeit über den Knopf
**Index aktualisieren** erneuern. Nutzungszähler und selbst vergebene Namen
überleben jeden Neuaufbau.

---

## Programme per Sprache öffnen

Es gibt **keinen Eintrag pro Programm im Code**. Der Befehl erkennt nur das
Muster „&lt;Verb&gt; &lt;Name&gt;“ und gleicht den Namen mit dem Index ab:

```
"Öffne Lunar Client"      "Starte Discord"        "Spotify öffnen"
"mach mal Steam auf"      "Kannst du bitte Discord öffnen"
```

Die unscharfe Suche kombiniert vier Signale, damit auch verhörte Namen
treffen:

1. exakte Übereinstimmung des normalisierten Namens
2. Wortteilmengen („discord“ → „Discord Inc.“)
3. Zeichenähnlichkeit (`difflib`)
4. **Kölner Phonetik** – der deutsche Klangabgleich: „lunar klient“ findet
   „Lunar Client“, „fotoshop“ findet „Adobe Photoshop“

Wenn mehrere Programme ähnlich gut passen, **startet Local Ally nichts**,
sondern zeigt die Treffer an. Die Antwort geht per Klick oder per Sprache:

```
"zwei"  ·  "die dritte"  ·  "Grafik Tool B"  ·  "abbrechen"
```

---

## PC steuern

Local Ally öffnet nicht nur Programme, sondern bedient den Rechner. Dahinter
steht **kein Befehl pro Formulierung**, sondern ein Absichtskatalog: jede
Absicht beschreibt ein paar Satzmuster mit Platzhaltern, ein Vergleicher
ordnet Varianten derselben Aktion zu und schneidet Parameter heraus.

| Bereich | Was geht |
|---|---|
| **Audio** | lauter, leiser, „auf 60 Prozent“, stumm, Stummschaltung aufheben, Mikrofon stumm, Audiogerät wechseln |
| **System** | sperren, herunterfahren, neu starten, Energiesparmodus, Bildschirm aus, Einstellungen, Task-Manager, WLAN, Bluetooth, Helligkeit, Anzeige umschalten |
| **Fenster** | wechseln, minimieren, maximieren, schließen |
| **Programme** | öffnen, schließen, „läuft X?“, zu X wechseln |
| **Medien** | Play/Pause, nächster und vorheriger Titel |
| **Dateien** | Downloads, Dokumente, Desktop, Bilder, Musik, Videos, Papierkorb; Dateisuche |

So klingt das im Alltag – alle Sätze führen zur jeweils selben Aktion:

```
„Mach es etwas lauter“   „lauter“   „dreh mal lauter“   „Lautstärke hoch“
„Stell die Lautstärke auf 60 Prozent“   „Lautstärke auf vierzig Prozent“
„Mute meinen PC“   „Ton aus“        „Mach mein Mikro aus“
„Zeig mir meine Downloads“           „Mach den Bildschirm aus“
„Mach die Musik weiter“              „Sperr meinen PC“
```

Zahlwörter versteht Local Ally genauso wie Ziffern („vierzig“, „45“,
„hundert“), und Steigerungen wirken auf die Schrittweite: „etwas lauter“
bewegt weniger als „deutlich lauter“.

**Kritische Aktionen fragen vorher nach.** Herunterfahren, Neustarten und das
Schließen von Programmen oder Fenstern können Ungespeichertes kosten – sie
laufen erst nach einem klaren Ja, per Sprache („ja“ / „nein“) oder per Klick.
Abschaltbar in den Einstellungen unter *Verhalten*.

Alles läuft mit Bordmitteln: Tastencodes über `user32`, `shutdown`,
`ms-settings:`-Seiten, `tasklist`/`taskkill` und PowerShell. Keine Cloud,
keine zusätzlichen Pakete. Was ein System nicht kann, sagt Local Ally in
einem Satz statt es stillschweigend zu verschlucken.

**Eine neue Fähigkeit ergänzen** – zwei Stellen, kein Umbau:

```python
# 1. local_ally/intents/catalog.py – was verstanden wird
IntentSpec(
    id="system.screenshot",
    action="system.screenshot",
    templates=["(mach|erstell) * screenshot", "screenshot"],
    description="Bildschirmfoto",
)

# 2. local_ally/actions/system.py – was passiert
@register("system.screenshot")
def screenshot(match, context):
    context.backend.screenshot()
    return ActionResult.done("Bildschirmfoto gespeichert.")
```

---

## Projektstruktur

```
local_ally/
├── core/          Zustand, Ereignisse, Controller, Textnormalisierung
├── settings/      Nutzereinstellungen (JSON)
├── database/      SQLite-Verbindung und Schema
├── app_index/     Programme finden, speichern, suchen, starten
│   └── sources/   je eine Datei pro Fundstelle (Startmenü, Registry, PATH …)
├── speech/        Mikrofon, Pausenerkennung, Erkenner-Backends
│   └── engines/   Vosk, faster-whisper
├── intents/       Absichtserkennung: Satzmuster, Parameter, Katalog
├── actions/       Ausführung: Audio, System, Fenster, Medien, Dateien, Programme
│   └── backends/  plattformabhängig (Windows, Linux, keiner)
├── commands/      Ablauf: Rückfragen, Bestätigungen, Brücke zu den Absichten
├── ui/            Slint-Oberfläche und die Brücke zu Python
│   └── slint/     .slint-Dateien (Theme, Seiten, Komponenten)
└── tools/         Hilfsprogramme (Modell-Download)
```

Details und die Begründungen zu den Architekturentscheidungen stehen in
[ARCHITECTURE.md](ARCHITECTURE.md).

---

## Tests

Die Tests kommen ohne zusätzliche Pakete aus (nur `unittest`):

```bash
python -m unittest discover -s tests -t .
```

Ist `slint` installiert, werden zusätzlich die `.slint`-Dateien übersetzt und
die Brücke zwischen Python und Oberfläche geprüft – ohne ein Fenster zu
öffnen.

Wake Word, Stummschaltung, Push-to-Talk und Hotkey-Konflikte sind
abgedeckt; ein zusätzlicher Test drückt echte Tasten und prüft damit die
systemweite Anbindung – weil er im aktiven Fenster landet, läuft er nur auf
Anforderung:

```bash
LOCAL_ALLY_HOTKEY_E2E=1 python -m unittest tests.test_hotkeys
```

Auch die Windows-Quellen sind abgedeckt, obwohl sie sich anderswo nicht
ausführen lassen: das Startmenü bekommt ein künstliches Verzeichnis mit
echten `.lnk`-Bytes, `Get-StartApps` eine vorgegebene PowerShell-Antwort
(`tests/test_sources.py`).

---

## Datenablage

| Was | Wo |
|---|---|
| Datenbank | `%LOCALAPPDATA%\LocalAlly\local_ally.sqlite3` |
| Einstellungen | `%LOCALAPPDATA%\LocalAlly\settings.json` |
| Sprachmodelle | `%LOCALAPPDATA%\LocalAlly\models\` |
| Protokoll | `%LOCALAPPDATA%\LocalAlly\local_ally.log` |

Über die Umgebungsvariable `LOCAL_ALLY_DATA_DIR` lässt sich ein anderer Ort
festlegen (nutzen auch die Tests).

---

## Stand und nächste Schritte

Fertig und benutzbar: Oberfläche, lokale Spracherkennung mit zwei Backends,
App-Index aus fünf Quellen, unscharfe Namenssuche mit Rückfrage,
Programmstart.

Naheliegende Erweiterungen, für die die Struktur bereits vorbereitet ist:

* Aktivierungswort („Hey Ally“) im `RecognitionService`
* weitere Befehle (Fenster schließen, Lautstärke, Timer) als neue Klasse in
  `commands/`
* eigene Namen für Programme vergeben (`AppRepository.add_user_alias`
  existiert bereits)
* Autostart und Ablage im Infobereich
