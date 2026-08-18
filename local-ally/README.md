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
python -m local_ally --reindex          # Programm-Index aufbauen
python -m local_ally --say "öffne discord"   # Befehl als Text ausführen
```

---

## Oberfläche

Drei Seiten, gebaut mit [Slint](https://slint.dev):

| Seite | Inhalt |
|---|---|
| **Start** | Status der Spracherkennung, Mikrofon-Knopf mit Pegelanzeige, erkannter Text, ausgeführte Aktion, Rückfrage bei mehreren Treffern |
| **Programme** | Der lokale App-Index: Name, Startziel, Quelle; Suche und „Index aktualisieren“ |
| **Einstellungen** | Auswahl des Speech-to-Text-Modells, Modelldetails, Mikrofon, Verhalten |

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
├── commands/      Sprachbefehle: Text → Absicht → Aktion
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
