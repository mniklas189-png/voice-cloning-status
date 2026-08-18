"""Minimaler Parser fuer Windows-Verknuepfungen (.lnk).

Warum selbst geschrieben statt ``pywin32``/``pylnk3``:

* Local Ally soll ohne COM-Aufrufe und ohne zusaetzliche Abhaengigkeit
  auskommen; das Format ist oeffentlich dokumentiert (MS-SHLLINK).
* Zum *Starten* braucht man das Ziel gar nicht - ``os.startfile`` oeffnet
  die .lnk-Datei direkt. Der Parser liefert nur Zusatzwissen: den echten
  Programmpfad (fuer Dubletten-Erkennung und zusaetzliche Namen) sowie
  Argumente und Arbeitsverzeichnis.

Schlaegt das Parsen fehl, faellt der Aufrufer auf die .lnk-Datei zurueck.
"""

from __future__ import annotations

import logging
import struct
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

_HEADER_SIZE = 0x4C
_MAGIC = b"L\x00\x00\x00"

# LinkFlags (MS-SHLLINK 2.1.1)
_HAS_LINK_TARGET_ID_LIST = 0x00000001
_HAS_LINK_INFO = 0x00000002
_HAS_NAME = 0x00000004
_HAS_RELATIVE_PATH = 0x00000008
_HAS_WORKING_DIR = 0x00000010
_HAS_ARGUMENTS = 0x00000020
_HAS_ICON_LOCATION = 0x00000040
_IS_UNICODE = 0x00000080

_VOLUME_ID_AND_LOCAL_BASE_PATH = 0x00000001


@dataclass(slots=True)
class ShellLink:
    target: str = ""
    arguments: str = ""
    working_dir: str = ""
    icon_location: str = ""
    description: str = ""


def _read_cstring(data: bytes, offset: int, unicode: bool) -> str:
    if offset <= 0 or offset >= len(data):
        return ""
    if unicode:
        end = offset
        while end + 1 < len(data) and data[end : end + 2] != b"\x00\x00":
            end += 2
        return data[offset:end].decode("utf-16-le", errors="replace")
    end = data.find(b"\x00", offset)
    end = len(data) if end < 0 else end
    return data[offset:end].decode("cp1252", errors="replace")


def _read_sized_string(data: bytes, offset: int, unicode: bool) -> tuple[str, int]:
    """StringData-Block: 2 Byte Laenge (in Zeichen) + Nutzdaten."""
    if offset + 2 > len(data):
        return "", offset
    (count,) = struct.unpack_from("<H", data, offset)
    offset += 2
    size = count * 2 if unicode else count
    raw = data[offset : offset + size]
    offset += size
    encoding = "utf-16-le" if unicode else "cp1252"
    return raw.decode(encoding, errors="replace"), offset


def parse(path: str | Path) -> ShellLink | None:
    """Liest eine .lnk-Datei. Gibt ``None`` zurueck, wenn das nicht gelingt."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    return parse_bytes(data)


def parse_bytes(data: bytes) -> ShellLink | None:
    if len(data) < _HEADER_SIZE or data[:4] != _MAGIC:
        return None

    (flags,) = struct.unpack_from("<I", data, 20)
    unicode = bool(flags & _IS_UNICODE)
    link = ShellLink()
    offset = _HEADER_SIZE

    try:
        if flags & _HAS_LINK_TARGET_ID_LIST:
            (id_list_size,) = struct.unpack_from("<H", data, offset)
            offset += 2 + id_list_size

        if flags & _HAS_LINK_INFO:
            link.target = _parse_link_info(data, offset)
            (info_size,) = struct.unpack_from("<I", data, offset)
            offset += info_size

        # StringData folgt in fester Reihenfolge.
        if flags & _HAS_NAME:
            link.description, offset = _read_sized_string(data, offset, unicode)
        relative_path = ""
        if flags & _HAS_RELATIVE_PATH:
            relative_path, offset = _read_sized_string(data, offset, unicode)
        if flags & _HAS_WORKING_DIR:
            link.working_dir, offset = _read_sized_string(data, offset, unicode)
        if flags & _HAS_ARGUMENTS:
            link.arguments, offset = _read_sized_string(data, offset, unicode)
        if flags & _HAS_ICON_LOCATION:
            link.icon_location, offset = _read_sized_string(data, offset, unicode)

        if not link.target and relative_path and link.working_dir:
            # Relativer Pfad ist immer relativ zur .lnk-Datei; das
            # Arbeitsverzeichnis ist die beste verfuegbare Naeherung.
            link.target = str(Path(link.working_dir) / Path(relative_path).name)

    except struct.error:
        log.debug("Verknuepfung konnte nicht vollstaendig gelesen werden")
        return link if link.target else None

    return link


def _parse_link_info(data: bytes, offset: int) -> str:
    """Lokalen Zielpfad aus dem LinkInfo-Block lesen (MS-SHLLINK 2.3)."""
    try:
        (size,) = struct.unpack_from("<I", data, offset)
        (header_size,) = struct.unpack_from("<I", data, offset + 4)
        (info_flags,) = struct.unpack_from("<I", data, offset + 8)
    except struct.error:
        return ""

    if not info_flags & _VOLUME_ID_AND_LOCAL_BASE_PATH:
        return ""  # Netzwerkpfade unterstuetzen wir hier bewusst nicht

    def field(rel: int) -> int:
        try:
            (value,) = struct.unpack_from("<I", data, offset + rel)
        except struct.error:
            return 0
        return offset + value if value else 0

    if header_size >= 0x24:  # optionale Unicode-Varianten vorhanden
        base = _read_cstring(data, field(28), True)
        suffix = _read_cstring(data, field(32), True)
        if base:
            return base + suffix
    base = _read_cstring(data, field(16), False)
    suffix = _read_cstring(data, field(24), False)
    _ = size
    return (base + suffix) if base else ""
