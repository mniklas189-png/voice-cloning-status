"""Laedt ein deutsches Vosk-Modell in das lokale Modellverzeichnis.

Aufruf::

    python -m local_ally.tools.fetch_vosk_model            # kleines Modell (~45 MB)
    python -m local_ally.tools.fetch_vosk_model --gross    # grosses Modell (~1,9 GB)

Das ist der einzige Programmteil, der ueberhaupt ins Internet greift - und
auch nur, wenn er ausdruecklich aufgerufen wird. Danach laeuft die Erkennung
vollstaendig offline.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from ..core.paths import vosk_models_dir

MODELS = {
    "klein": (
        "vosk-model-small-de-0.15",
        "https://alphacephei.com/vosk/models/vosk-model-small-de-0.15.zip",
        "ca. 45 MB - schnell, fuer kurze Befehle voellig ausreichend",
    ),
    "gross": (
        "vosk-model-de-0.21",
        "https://alphacephei.com/vosk/models/vosk-model-de-0.21.zip",
        "ca. 1,9 GB - genauer, braucht deutlich mehr Arbeitsspeicher",
    ),
}


def _report(done: int, block: int, total: int) -> None:
    if total <= 0:
        return
    percent = min(done * block * 100 // total, 100)
    print(f"\r  {percent:3d} %", end="", flush=True)


def download(variant: str = "klein") -> Path:
    name, url, description = MODELS[variant]
    target = vosk_models_dir() / name
    if target.is_dir():
        print(f"Modell ist bereits vorhanden: {target}")
        return target

    print(f"Lade {name} ({description})")
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "model.zip"
        urllib.request.urlretrieve(url, archive, _report)  # noqa: S310 - feste HTTPS-URL
        print("\n  entpacke ...")
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(tmp)
        extracted = Path(tmp) / name
        if not extracted.is_dir():  # Archivstruktur weicht ab
            candidates = [p for p in Path(tmp).iterdir() if p.is_dir()]
            if not candidates:
                raise RuntimeError("Archiv enthielt kein Modellverzeichnis")
            extracted = candidates[0]
        shutil.move(str(extracted), str(target))

    print(f"Fertig: {target}")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deutsches Vosk-Modell herunterladen")
    parser.add_argument(
        "--gross", action="store_true", help="grosses Modell statt des kleinen laden"
    )
    args = parser.parse_args(argv)
    try:
        download("gross" if args.gross else "klein")
    except Exception as exc:
        print(f"Fehlgeschlagen: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
