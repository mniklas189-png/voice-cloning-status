"""Prueft, ob die installierte Slint-Fassung Listenmodelle am Leben haelt.

Eigenstaendig lauffaehig, ohne Local Ally:

    python docs/slint_model_lifetime_check.py

Hintergrund: docs/slint-python-model-lifetime.md
"""

import gc
import pathlib
import sys
import tempfile

import slint

SOURCE = """
export global Store { in-out property <[string]> rows: []; }
export component Main inherits Window { }
"""


def main() -> int:
    # slint.load_file braucht eine Datei - eine Zeichenkette nimmt es nicht.
    path = pathlib.Path(tempfile.mkdtemp()) / "model_lifetime.slint"
    path.write_text(SOURCE, encoding="utf-8")

    ui = slint.load_file(str(path))
    window = ui.Main()
    window.Store.rows = slint.ListModel(["a", "b", "c"])

    before = len(window.Store.rows)
    gc.collect()
    after = len(window.Store.rows)

    print(f"vor der Sammlung: {before} Zeilen, danach: {after} Zeilen")
    if after == before:
        print("Modelle ueberleben - die Huelle in ui/store.py waere nicht mehr noetig.")
        return 0
    print("Modelle werden eingesammelt - die Huelle in ui/store.py wird gebraucht.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
