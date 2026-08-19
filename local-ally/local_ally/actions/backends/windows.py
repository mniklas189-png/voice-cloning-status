"""Windows-Umsetzung - ohne zusaetzliche Pakete.

Alles laeuft ueber Bordmittel: Tastencodes ueber ``user32`` (Lautstärke,
Medien, Fenster), ``rundll32``/``shutdown`` fuer Energie, ``ms-settings:``
fuer Einstellungsseiten, ``tasklist``/``taskkill`` fuer Prozesse und
PowerShell fuer die Helligkeit. Das haelt Local Ally installationsfrei und
vollstaendig lokal.

Ist ``pycaw`` installiert, wird es fuer das exakte Setzen der Lautstärke
genutzt - ohne das Paket geht es ueber Tastendruecke, die in Zweierschritten
regeln.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess

from .base import NotSupported, SystemBackend

log = logging.getLogger(__name__)

# Virtuelle Tastencodes
VK_MEDIA_NEXT = 0xB0
VK_MEDIA_PREV = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MENU = 0x12        # Alt
VK_TAB = 0x09
VK_LWIN = 0x5B
VK_UP = 0x26
VK_DOWN = 0x28
VK_F4 = 0x73
KEYEVENTF_KEYUP = 0x0002

# ShowWindow-Befehle und Fensternachrichten
# Tastencodes fuer selbst vergebene Kombinationen
_VK_BY_NAME = {
    "ctrl": VK_MENU - 6, "alt": VK_MENU, "shift": 0x10, "cmd": VK_LWIN,
    "enter": 0x0D, "escape": 0x1B, "space": 0x20, "tab": VK_TAB,
    "backspace": 0x08, "delete": 0x2E, "insert": 0x2D,
    "home": 0x24, "end": 0x23, "page_up": 0x21, "page_down": 0x22,
    "left": 0x25, "up": VK_UP, "right": 0x27, "down": VK_DOWN,
    **{f"f{number}": 0x70 + number - 1 for number in range(1, 25)},
}

SW_MAXIMIZE = 3
SW_MINIMIZE = 6
SW_RESTORE = 9
WM_CLOSE = 0x0010

# Ein Tastendruck aendert die Lautstaerke um zwei Prozentpunkte.
VOLUME_STEP_PERCENT = 2

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

SETTINGS_PAGES = {
    "": "ms-settings:",
    "wifi": "ms-settings:network-wifi",
    "bluetooth": "ms-settings:bluetooth",
    "sound": "ms-settings:sound",
    "display": "ms-settings:display",
}

DISPLAY_MODES = {
    "switch": "/clone",
    "duplicate": "/clone",
    "extend": "/extend",
    "internal": "/internal",
    "external": "/external",
}

# Bekannte Ordner ueber ihre GUID - zuverlaessiger als Pfade zu raten,
# denn "Downloads" liegt nicht auf jedem Rechner unter dem Benutzerprofil.
KNOWN_FOLDER_GUIDS = {
    "downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
    "documents": "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}",
    "desktop": "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
    "pictures": "{33E28130-4E1E-4676-835A-98395C3BC3BB}",
    "music": "{4BD8D571-6D19-48D3-BE97-422220080E43}",
    "videos": "{18989B1D-99B5-455B-841C-AB7C74E4DDFC}",
}


class WindowsBackend(SystemBackend):
    id = "windows"
    display_name = "Windows"

    def __init__(self) -> None:
        import ctypes

        self._ctypes = ctypes
        self._user32 = ctypes.windll.user32

    # --- Hilfen --------------------------------------------------------
    def _tap(self, *keys: int) -> None:
        """Tasten druecken und in umgekehrter Reihenfolge loslassen."""
        for key in keys:
            self._user32.keybd_event(key, 0, 0, 0)
        for key in reversed(keys):
            self._user32.keybd_event(key, 0, KEYEVENTF_KEYUP, 0)

    @staticmethod
    def _run(args: list[str], timeout: float = 20.0) -> subprocess.CompletedProcess:
        return subprocess.run(
            args, capture_output=True, text=True, timeout=timeout,
            creationflags=_NO_WINDOW,
        )

    @staticmethod
    def _detach(args: list[str]) -> None:
        subprocess.Popen(args, creationflags=_NO_WINDOW | 0x00000008, close_fds=True)

    def _powershell(self, script: str, timeout: float = 25.0) -> str:
        completed = self._run(
            ["powershell.exe", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-Command", script],
            timeout=timeout,
        )
        if completed.returncode != 0:
            raise NotSupported(completed.stderr.strip()[:200] or "PowerShell-Aufruf fehlgeschlagen.")
        return completed.stdout.strip()

    # --- Audio ---------------------------------------------------------
    def volume_up(self, steps: int = 1) -> None:
        for _ in range(max(1, steps)):
            self._tap(VK_VOLUME_UP)

    def volume_down(self, steps: int = 1) -> None:
        for _ in range(max(1, steps)):
            self._tap(VK_VOLUME_DOWN)

    def volume_set(self, percent: int) -> None:
        percent = max(0, min(100, percent))
        if self._volume_set_exact(percent):
            return
        # Ohne pycaw: erst ganz herunter, dann in Zweierschritten hoch.
        for _ in range(50):
            self._tap(VK_VOLUME_DOWN)
        for _ in range(percent // VOLUME_STEP_PERCENT):
            self._tap(VK_VOLUME_UP)

    def _volume_set_exact(self, percent: int) -> bool:
        try:
            from ctypes import cast, POINTER

            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        except Exception:
            return False
        try:
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))
            volume.SetMasterVolumeLevelScalar(percent / 100.0, None)
            return True
        except Exception:
            log.debug("pycaw vorhanden, aber nicht nutzbar", exc_info=True)
            return False

    def volume_mute(self, muted: bool) -> None:
        # Die Taste schaltet um; der genaue Zustand ist ohne pycaw nicht
        # lesbar. Mit pycaw wird er exakt gesetzt.
        if not self._volume_mute_exact(muted):
            self._tap(VK_VOLUME_MUTE)

    def _volume_mute_exact(self, muted: bool) -> bool:
        try:
            from ctypes import cast, POINTER

            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        except Exception:
            return False
        try:
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))
            volume.SetMute(1 if muted else 0, None)
            return True
        except Exception:
            return False

    def audio_devices(self) -> list[str]:
        try:
            output = self._powershell(
                "Get-AudioDevice -List | Where-Object {$_.Type -eq 'Playback'} "
                "| Select-Object -ExpandProperty Name"
            )
        except NotSupported:
            return []
        return [line.strip() for line in output.splitlines() if line.strip()]

    def set_audio_device(self, name: str) -> str:
        """Genau dieses Geraet aktivieren.

        Ohne das PowerShell-Modul AudioDeviceCmdlets geht das unter Windows
        nicht - dann bleibt der ehrliche Weg ueber die Systemseite.
        """
        quoted = name.replace("'", "''")
        self._powershell(f"Set-AudioDevice -Name '{quoted}'")
        return name

    # --- Medien --------------------------------------------------------
    def media(self, command: str) -> None:
        keys = {
            "playpause": VK_MEDIA_PLAY_PAUSE,
            "next": VK_MEDIA_NEXT,
            "previous": VK_MEDIA_PREV,
        }
        key = keys.get(command)
        if key is None:
            raise NotSupported(f"Unbekannter Medienbefehl „{command}“.")
        self._tap(key)

    # --- System --------------------------------------------------------
    def lock(self) -> None:
        self._user32.LockWorkStation()

    def shutdown(self) -> None:
        self._detach(["shutdown.exe", "/s", "/t", "0"])

    def restart(self) -> None:
        self._detach(["shutdown.exe", "/r", "/t", "0"])

    def sleep(self) -> None:
        self._detach(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])

    def screen_off(self) -> None:
        # An alle Fenster: Monitor in den Energiesparzustand
        HWND_BROADCAST, WM_SYSCOMMAND, SC_MONITORPOWER = 0xFFFF, 0x0112, 0xF170
        self._user32.SendMessageW(HWND_BROADCAST, WM_SYSCOMMAND, SC_MONITORPOWER, 2)

    def open_settings(self, page: str = "") -> None:
        uri = SETTINGS_PAGES.get(page, SETTINGS_PAGES[""])
        os.startfile(uri)  # type: ignore[attr-defined]

    def open_task_manager(self) -> None:
        self._detach(["taskmgr.exe"])

    def brightness_step(self, delta: int) -> int:
        current = int(self._powershell(
            "(Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightness)"
            ".CurrentBrightness | Select-Object -First 1"
        ) or 0)
        target = max(0, min(100, current + delta))
        self.brightness_set(target)
        return target

    def brightness_set(self, percent: int) -> None:
        percent = max(0, min(100, percent))
        self._powershell(
            "(Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightnessMethods)"
            f".WmiSetBrightness(1,{percent})"
        )

    def display_mode(self, mode: str) -> None:
        flag = DISPLAY_MODES.get(mode)
        if flag is None:
            raise NotSupported(f"Unbekannter Anzeigemodus „{mode}“.")
        self._detach(["DisplaySwitch.exe", flag])

    # --- Fenster -------------------------------------------------------
    def window_switch(self) -> None:
        self._tap(VK_MENU, VK_TAB)

    def window_minimize(self, process: str = "") -> None:
        if process:
            self._show_window(process, SW_MINIMIZE)
            return
        self._tap(VK_LWIN, VK_DOWN)

    def window_maximize(self, process: str = "") -> None:
        if process:
            self._show_window(process, SW_MAXIMIZE)
            return
        self._tap(VK_LWIN, VK_UP)

    def window_close(self, process: str = "") -> None:
        if process:
            hwnd = self._find_window(process)
            if hwnd is None:
                raise NotSupported(f"Kein Fenster von {process} gefunden.")
            # WM_CLOSE statt Abschuss: das Programm darf nach dem Speichern
            # fragen, genau wie beim Klick auf das Kreuz.
            self._user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            return
        self._tap(VK_MENU, VK_F4)

    def _show_window(self, process: str, command: int) -> None:
        hwnd = self._find_window(process)
        if hwnd is None:
            raise NotSupported(f"Kein Fenster von {process} gefunden.")
        self._user32.ShowWindow(hwnd, command)

    def _find_window(self, name: str):
        """Erstes sichtbares Fenster eines Prozesses suchen."""
        import ctypes
        from ctypes import wintypes

        image = name.lower().removesuffix(".exe")
        user32 = self._user32
        kernel32 = ctypes.windll.kernel32
        found: list[int] = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def enumerate_windows(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            # PROCESS_QUERY_LIMITED_INFORMATION - reicht und braucht keine
            # erhoehten Rechte.
            handle = kernel32.OpenProcess(0x1000, False, pid.value)
            if not handle:
                return True
            try:
                buffer = ctypes.create_unicode_buffer(260)
                size = wintypes.DWORD(260)
                kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size))
            finally:
                kernel32.CloseHandle(handle)
            if os.path.basename(buffer.value).lower().removesuffix(".exe") == image:
                found.append(hwnd)
                return False
            return True

        user32.EnumWindows(enumerate_windows, 0)
        return found[0] if found else None

    # --- Prozesse ------------------------------------------------------
    def running_processes(self) -> list[str]:
        completed = self._run(["tasklist.exe", "/fo", "csv", "/nh"])
        names: list[str] = []
        for line in completed.stdout.splitlines():
            match = re.match(r'"([^"]+)"', line.strip())
            if match:
                names.append(match.group(1))
        return names

    def close_process(self, name: str) -> int:
        image = name if name.lower().endswith(".exe") else f"{name}.exe"
        # Ohne /F: das Programm darf noch nach dem Speichern fragen.
        completed = self._run(["taskkill.exe", "/IM", image])
        return completed.stdout.count("PID") if completed.returncode == 0 else 0

    def focus_process(self, name: str) -> bool:
        hwnd = self._find_window(name)
        if hwnd is None:
            return False
        self._user32.ShowWindow(hwnd, SW_RESTORE)
        self._user32.SetForegroundWindow(hwnd)
        return True

    # --- Eingabe -------------------------------------------------------
    def type_text(self, text: str) -> None:
        """Text in das aktive Fenster tippen.

        Ueber pynput - dasselbe Paket, das schon die globalen Tastenkuerzel
        traegt. Es kennt die Sonderzeichen der Tastaturbelegung, was ein
        eigener Nachbau ueber Tastencodes nicht leisten wuerde.
        """
        try:
            from pynput.keyboard import Controller
        except Exception as exc:
            raise NotSupported(
                "Zum Tippen fehlt das Paket pynput - Installation: pip install pynput"
            ) from exc
        Controller().type(text)

    def beep(self) -> None:
        import winsound

        winsound.MessageBeep(winsound.MB_ICONASTERISK)

    def send_keys(self, combination: str) -> None:
        """Tastenkombination senden - ueber denselben Leser wie die Hotkeys."""
        from ...hotkeys.keys import Hotkey

        hotkey = Hotkey.parse(combination)
        codes = [_VK_BY_NAME[name] for name in ("ctrl", "alt", "shift", "cmd")
                 if name in hotkey.modifiers]
        key = _VK_BY_NAME.get(hotkey.key)
        if key is None:
            if len(hotkey.key) == 1:
                key = ord(hotkey.key.upper())
            else:
                raise NotSupported(f"Taste „{hotkey.key}“ lässt sich nicht senden.")
        self._tap(*codes, key)

    def run_shell(self, command: str) -> None:
        # Bewusst ohne Konsolenfenster: ein Kurzbefehl per Sprache soll nicht
        # ein Fenster aufblitzen lassen. Wer Ausgaben sehen will, laesst den
        # Befehl in eine Datei schreiben.
        self._detach(["cmd.exe", "/c", command])

    # --- Dateien -------------------------------------------------------
    def known_folder(self, key: str) -> str:
        if key == "home":
            return os.path.expanduser("~")
        if key == "recycle_bin":
            return "shell:RecycleBinFolder"

        guid = KNOWN_FOLDER_GUIDS.get(key)
        if guid is None:
            raise NotSupported(f"Ordner „{key}“ ist nicht bekannt.")
        try:
            import ctypes
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                            ("Data3", wintypes.WORD), ("Data4", ctypes.c_byte * 8)]

            path_pointer = ctypes.c_wchar_p()
            folder_id = GUID()
            ctypes.windll.ole32.CLSIDFromString(guid, ctypes.byref(folder_id))
            result = ctypes.windll.shell32.SHGetKnownFolderPath(
                ctypes.byref(folder_id), 0, None, ctypes.byref(path_pointer)
            )
            if result == 0 and path_pointer.value:
                path = path_pointer.value
                ctypes.windll.ole32.CoTaskMemFree(path_pointer)
                return path
        except Exception:
            log.debug("SHGetKnownFolderPath fehlgeschlagen", exc_info=True)

        fallback = {"downloads": "Downloads", "documents": "Documents", "desktop": "Desktop",
                    "pictures": "Pictures", "music": "Music", "videos": "Videos"}
        return os.path.join(os.path.expanduser("~"), fallback.get(key, ""))

    def open_path(self, path: str) -> None:
        os.startfile(path)  # type: ignore[attr-defined]

    def search_files(self, query: str) -> None:
        cleaned = re.sub(r'[\x00-\x1f"&|<>]', " ", query).strip()
        if not cleaned:
            raise NotSupported("Für die Suche fehlt ein Suchbegriff.")
        from urllib.parse import quote

        self._detach(["explorer.exe", f"search-ms:query={quote(cleaned)}"])
