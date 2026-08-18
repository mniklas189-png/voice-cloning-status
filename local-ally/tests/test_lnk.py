"""Parser fuer Windows-Verknuepfungen.

Die Testdateien werden hier nach der Spezifikation MS-SHLLINK erzeugt -
so laesst sich der Parser auch auf Linux pruefen.
"""

import struct

from tests.support import unittest  # noqa: F401

from local_ally.app_index.sources import lnk

_CLSID = b"\x01\x14\x02\x00\x00\x00\x00\x00\xc0\x00\x00\x00\x00\x00\x00\x46"

HAS_LINK_INFO = 0x02
HAS_WORKING_DIR = 0x10
HAS_ARGUMENTS = 0x20
IS_UNICODE = 0x80


def _link_info(base_path: str, suffix: str = "") -> bytes:
    header_size = 0x1C
    volume_id_offset = header_size
    volume_id = struct.pack("<IIII", 16, 3, 0, 16)  # Groesse, Laufwerkstyp, Seriennr., Label
    local_base_offset = volume_id_offset + len(volume_id)
    base_bytes = base_path.encode("cp1252") + b"\x00"
    suffix_offset = local_base_offset + len(base_bytes)
    suffix_bytes = suffix.encode("cp1252") + b"\x00"

    total = suffix_offset + len(suffix_bytes)
    header = struct.pack(
        "<IIIIIII",
        total, header_size, 0x01,
        volume_id_offset, local_base_offset, 0, suffix_offset,
    )
    return header + volume_id + base_bytes + suffix_bytes


def _sized_string(value: str) -> bytes:
    return struct.pack("<H", len(value)) + value.encode("utf-16-le")


def build_lnk(target: str, working_dir: str = "", arguments: str = "") -> bytes:
    flags = HAS_LINK_INFO | IS_UNICODE
    if working_dir:
        flags |= HAS_WORKING_DIR
    if arguments:
        flags |= HAS_ARGUMENTS

    header = struct.pack("<I", 0x4C) + _CLSID + struct.pack("<I", flags)
    header += b"\x00" * (0x4C - len(header))

    payload = _link_info(target)
    if working_dir:
        payload += _sized_string(working_dir)
    if arguments:
        payload += _sized_string(arguments)
    return header + payload


class LnkTests(unittest.TestCase):
    def test_reads_target(self):
        link = lnk.parse_bytes(build_lnk(r"C:\Programme\Discord\Discord.exe"))
        self.assertIsNotNone(link)
        self.assertEqual(link.target, r"C:\Programme\Discord\Discord.exe")

    def test_reads_working_dir_and_arguments(self):
        data = build_lnk(r"C:\Spiele\Lunar.exe", r"C:\Spiele", "--launch")
        link = lnk.parse_bytes(data)
        self.assertEqual(link.working_dir, r"C:\Spiele")
        self.assertEqual(link.arguments, "--launch")

    def test_invalid_data_returns_none(self):
        self.assertIsNone(lnk.parse_bytes(b"kein shell link"))
        self.assertIsNone(lnk.parse_bytes(b""))

    def test_truncated_file_does_not_raise(self):
        data = build_lnk(r"C:\A\B.exe")[:60]
        self.assertIsNone(lnk.parse_bytes(data))


if __name__ == "__main__":
    unittest.main()
