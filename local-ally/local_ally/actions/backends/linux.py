"""Linux-Umsetzung.

Local Ally ist fuer Windows gedacht. Dieses Backend existiert, damit sich
die gesamte Kette - Absicht, Aktion, Rueckmeldung - auf einem Linux-Rechner
entwickeln und ausprobieren laesst. Es nutzt gaengige Bordmittel und meldet
sauber, wenn eines davon fehlt.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess

from .base import NotSupported, SystemBackend

log = logging.getLogger(__name__)

SETTINGS_PAGES = {
    "": ["gnome-control-center"],
    "wifi": ["gnome-control-center", "wifi"],
    "bluetooth": ["gnome-control-center", "bluetooth"],
    "sound": ["gnome-control-center", "sound"],
    "display": ["gnome-control-center", "display"],
}

XDG_FOLDERS = {
    "downloads": "DOWNLOAD", "documents": "DOCUMENTS", "desktop": "DESKTOP",
    "pictures": "PICTURES", "music": "MUSIC", "videos": "VIDEOS",
}


class LinuxBackend(SystemBackend):
    id = "linux"
    display_name = "Linux"

    # --- Hilfen --------------------------------------------------------
    def _require(self, program: str, what: str) -> str:
        path = shutil.which(program)
        if not path:
            raise NotSupported(f"{what} braucht „{program}“ - das ist hier nicht installiert.")
        return path

    def _run(self, args: list[str], what: str, timeout: float = 15.0) -> str:
        self._require(args[0], what)
        completed = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        if completed.returncode != 0:
            raise NotSupported(completed.stderr.strip()[:200] or f"{what} fehlgeschlagen.")
        return completed.stdout.strip()

    def _detach(self, args: list[str], what: str) -> None:
        self._require(args[0], what)
        subprocess.Popen(args, start_new_session=True, close_fds=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # --- Audio ---------------------------------------------------------
    def volume_up(self, steps: int = 1) -> None:
        self._run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"+{5 * max(1, steps)}%"],
                  "Lautstärke ändern")

    def volume_down(self, steps: int = 1) -> None:
        self._run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"-{5 * max(1, steps)}%"],
                  "Lautstärke ändern")

    def volume_set(self, percent: int) -> None:
        self._run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{max(0, min(100, percent))}%"],
                  "Lautstärke setzen")

    def volume_mute(self, muted: bool) -> None:
        self._run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1" if muted else "0"],
                  "Stummschalten")

    def audio_devices(self) -> list[str]:
        output = self._run(["pactl", "list", "short", "sinks"], "Audiogeräte auflisten")
        return [line.split("\t")[1] for line in output.splitlines() if "\t" in line]

    def set_audio_device(self, name: str) -> str:
        self._run(["pactl", "set-default-sink", name], "Audiogerät wechseln")
        return name

    # --- Medien --------------------------------------------------------
    def media(self, command: str) -> None:
        mapping = {"playpause": "play-pause", "next": "next", "previous": "previous"}
        action = mapping.get(command)
        if action is None:
            raise NotSupported(f"Unbekannter Medienbefehl „{command}“.")
        self._run(["playerctl", action], "Mediensteuerung")

    # --- System --------------------------------------------------------
    def lock(self) -> None:
        for args in (["loginctl", "lock-session"], ["xdg-screensaver", "lock"]):
            if shutil.which(args[0]):
                self._detach(args, "Sperren")
                return
        raise NotSupported("Zum Sperren fehlt loginctl oder xdg-screensaver.")

    def shutdown(self) -> None:
        self._detach(["systemctl", "poweroff"], "Herunterfahren")

    def restart(self) -> None:
        self._detach(["systemctl", "reboot"], "Neustarten")

    def sleep(self) -> None:
        self._detach(["systemctl", "suspend"], "Energiesparmodus")

    def screen_off(self) -> None:
        self._run(["xset", "dpms", "force", "off"], "Bildschirm ausschalten")

    def open_settings(self, page: str = "") -> None:
        self._detach(SETTINGS_PAGES.get(page, SETTINGS_PAGES[""]), "Einstellungen öffnen")

    def open_task_manager(self) -> None:
        for program in ("gnome-system-monitor", "ksysguard", "xterm"):
            if shutil.which(program):
                self._detach([program], "Systemmonitor öffnen")
                return
        raise NotSupported("Kein Systemmonitor gefunden.")

    def brightness_step(self, delta: int) -> int:
        sign = "+" if delta >= 0 else "-"
        self._run(["brightnessctl", "set", f"{abs(delta)}%{sign}"], "Helligkeit ändern")
        return 0

    def brightness_set(self, percent: int) -> None:
        self._run(["brightnessctl", "set", f"{max(0, min(100, percent))}%"], "Helligkeit setzen")

    def display_mode(self, mode: str) -> None:
        raise NotSupported("Anzeigemodus umschalten ist hier nicht eingebaut.")

    # --- Fenster -------------------------------------------------------
    def window_switch(self) -> None:
        self._run(["wmctrl", "-s", "0"], "Fenster wechseln")

    def window_minimize(self) -> None:
        self._run(["xdotool", "getactivewindow", "windowminimize"], "Fenster minimieren")

    def window_maximize(self) -> None:
        self._run(["wmctrl", "-r", ":ACTIVE:", "-b", "add,maximized_vert,maximized_horz"],
                  "Fenster maximieren")

    def window_close(self) -> None:
        self._run(["wmctrl", "-c", ":ACTIVE:"], "Fenster schließen")

    # --- Prozesse ------------------------------------------------------
    def running_processes(self) -> list[str]:
        output = subprocess.run(["ps", "-eo", "comm="], capture_output=True, text=True).stdout
        return sorted({line.strip() for line in output.splitlines() if line.strip()})

    def close_process(self, name: str) -> int:
        completed = subprocess.run(["pkill", "-x", name], capture_output=True, text=True)
        return 1 if completed.returncode == 0 else 0

    def focus_process(self, name: str) -> bool:
        if not shutil.which("wmctrl"):
            raise NotSupported("Zum Wechseln fehlt „wmctrl“.")
        completed = subprocess.run(["wmctrl", "-a", name], capture_output=True, text=True)
        return completed.returncode == 0

    # --- Dateien -------------------------------------------------------
    def known_folder(self, key: str) -> str:
        if key == "home":
            return os.path.expanduser("~")
        if key == "recycle_bin":
            return os.path.expanduser("~/.local/share/Trash/files")
        name = XDG_FOLDERS.get(key)
        if name is None:
            raise NotSupported(f"Ordner „{key}“ ist nicht bekannt.")
        if shutil.which("xdg-user-dir"):
            path = subprocess.run(["xdg-user-dir", name], capture_output=True, text=True).stdout.strip()
            if path:
                return path
        return os.path.join(os.path.expanduser("~"), name.title())

    def open_path(self, path: str) -> None:
        self._detach(["xdg-open", path], "Ordner öffnen")

    def search_files(self, query: str) -> None:
        raise NotSupported("Eine Dateisuche gibt es hier nicht - unter Windows nutzt sie den Explorer.")
