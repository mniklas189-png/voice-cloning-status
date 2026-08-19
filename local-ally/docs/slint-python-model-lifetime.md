# Bericht an das Slint-Projekt: Listenmodelle überleben die Speicherbereinigung nicht

**Paket:** `slint` (Python) 1.9.2a1 · **Python:** 3.11 · **Plattform:** Linux
(software renderer) und Windows · **Fundort:** Local Ally, `ui/bridge.py`

Dieser Text ist als Fehlerbericht für <https://github.com/slint-ui/slint>
gedacht. Er liegt hier im Projekt, damit die Beobachtung nachvollziehbar
bleibt und beim nächsten Versionswechsel geprüft werden kann.

## Zusammenfassung

Ein in Python erzeugtes `slint.ListModel`, das einer Slint-Eigenschaft
zugewiesen wurde, wird von der Speicherbereinigung eingesammelt, obwohl die
Oberfläche es noch benutzt. Danach liefert das Modell dauerhaft null Zeilen.
Es gibt **keine Ausnahme** – nur eine Meldung auf stderr:

```
Python: Model implementation is lacking self object (in row_count)
```

Für eine Anwendung mit grafischer Oberfläche heißt das: die Liste ist
plötzlich leer, ohne dass etwas darauf hinweist.

## Kleinstes Beispiel

```python
import gc, tempfile, pathlib, slint

source = pathlib.Path(tempfile.mkdtemp()) / "demo.slint"
source.write_text("""
export global Store { in-out property <[string]> rows: []; }
export component Main inherits Window { }
""")

ui = slint.load_file(str(source))
window = ui.Main()
window.Store.rows = slint.ListModel(["a", "b", "c"])

print(len(window.Store.rows))   # 3
gc.collect()
print(len(window.Store.rows))   # 0   <- erwartet: 3
```

## Was wir beobachtet haben

| Beobachtung | Ergebnis |
|---|---|
| Zuweisung an eine Eigenschaft | hält das Python-Objekt **nicht** am Leben |
| Ein aktiver `for`-Wiederholer auf der sichtbaren Seite | hält es **ebenfalls nicht** am Leben |
| Rückgabewert beim Lesen der Eigenschaft | ist dasselbe Python-Objekt (`is`-identisch), solange es lebt |
| Zeitpunkt | nicht deterministisch: 2 Mio. Objektallokationen überlebt das Modell, eine volle Sammlung räumt es weg |
| Callbacks (`Actions.foo = fn`) | überleben die Sammlung, sind also stark referenziert |
| Zuweisung einer einfachen `list` statt eines `ListModel` | `TypeError: 'list' object cannot be converted to 'PyDict'` |

Die letzten beiden Zeilen sind der Grund, warum es aus unserer Sicht ein
Fehler und keine Absicht ist: Callbacks werden stark gehalten, Modelle nicht –
und ein Ausweichen auf eine einfache Liste ist nicht möglich.

## Vermutete Ursache

`slint.models.Model.__init__` ruft `self.init_self(self)`. Die Rust-Seite
scheint daraus eine schwache Referenz zu bilden. Weil das Python-Objekt
zusätzlich einen Zyklus auf sich selbst hat, greift die Referenzzählung
nicht: das Objekt stirbt erst beim zyklischen Sammler – also zeitversetzt.

## Vorschlag

Beim Zuweisen an eine Eigenschaft (oder in `init_self`) eine starke Referenz
auf das Python-Objekt halten, solange die Rust-seitige `ModelRc` lebt.
Ersatzweise wäre schon hilfreich: eine Ausnahme statt einer stillen leeren
Liste, sobald die schwache Referenz nicht mehr aufgelöst werden kann.

## Unser Umgang damit

`local_ally/ui/store.py` hält jedes Modell in einem Wörterbuch fest
(`UiStore`), die Brücke schreibt nur noch gewöhnliche Python-Listen.
`tests/test_ui_store.py` prüft die Fehlerklasse gegen eine erzwungene
Sammlung. Der Umweg bleibt auch dann richtig, wenn Slint das Verhalten
ändert – er kostet nur eine Referenz je Eigenschaft.

**Beim Versionswechsel prüfen:** läuft `docs/slint_model_lifetime_check.py`
ohne Befund durch, kann die Hülle entfallen (muss aber nicht).
