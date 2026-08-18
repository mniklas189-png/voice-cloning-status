"""Attrappen fuer die Tests."""

from __future__ import annotations

from local_ally.actions.backends.base import NotSupported, SystemBackend


class FakeBackend(SystemBackend):
    """Schreibt nur mit, statt am System etwas zu tun.

    So laesst sich pruefen, *was* eine Aktion ausloest - unabhaengig davon,
    auf welchem Betriebssystem die Tests laufen.
    """

    id = "fake"
    display_name = "Attrappe"

    def __init__(self, processes: list[str] | None = None) -> None:
        self.calls: list[tuple] = []
        self.processes = processes if processes is not None else ["explorer.exe"]
        self.unsupported: set[str] = set()
        self.devices = ["Lautsprecher (Realtek)", "Kopfhörer (Bluetooth)"]
        self.focus_result = True

    # --- Hilfen --------------------------------------------------------
    def _record(self, name: str, *args):
        if name in self.unsupported:
            raise NotSupported(f"{name} wird auf diesem System nicht unterstützt.")
        self.calls.append((name, *args))

    def called(self, name: str) -> bool:
        return any(call[0] == name for call in self.calls)

    def call(self, name: str) -> tuple | None:
        for entry in self.calls:
            if entry[0] == name:
                return entry
        return None

    # --- Audio ---------------------------------------------------------
    def volume_up(self, steps: int = 1) -> None:
        self._record("volume_up", steps)

    def volume_down(self, steps: int = 1) -> None:
        self._record("volume_down", steps)

    def volume_set(self, percent: int) -> None:
        self._record("volume_set", percent)

    def volume_mute(self, muted: bool) -> None:
        self._record("volume_mute", muted)

    def audio_devices(self) -> list[str]:
        self._record("audio_devices")
        return list(self.devices)

    def set_audio_device(self, name: str) -> str:
        self._record("set_audio_device", name)
        return name

    # --- Medien --------------------------------------------------------
    def media(self, command: str) -> None:
        self._record("media", command)

    # --- System --------------------------------------------------------
    def lock(self) -> None:
        self._record("lock")

    def shutdown(self) -> None:
        self._record("shutdown")

    def restart(self) -> None:
        self._record("restart")

    def sleep(self) -> None:
        self._record("sleep")

    def screen_off(self) -> None:
        self._record("screen_off")

    def open_settings(self, page: str = "") -> None:
        self._record("open_settings", page)

    def open_task_manager(self) -> None:
        self._record("open_task_manager")

    def brightness_step(self, delta: int) -> int:
        self._record("brightness_step", delta)
        return 50 + delta

    def brightness_set(self, percent: int) -> None:
        self._record("brightness_set", percent)

    def display_mode(self, mode: str) -> None:
        self._record("display_mode", mode)

    # --- Fenster -------------------------------------------------------
    def window_switch(self) -> None:
        self._record("window_switch")

    def window_minimize(self) -> None:
        self._record("window_minimize")

    def window_maximize(self) -> None:
        self._record("window_maximize")

    def window_close(self) -> None:
        self._record("window_close")

    # --- Prozesse ------------------------------------------------------
    def running_processes(self) -> list[str]:
        return list(self.processes)

    def close_process(self, name: str) -> int:
        self._record("close_process", name)
        return 1 if name in self.processes else 0

    def focus_process(self, name: str) -> bool:
        self._record("focus_process", name)
        return self.focus_result

    # --- Dateien -------------------------------------------------------
    def known_folder(self, key: str) -> str:
        self._record("known_folder", key)
        return f"C:/Users/test/{key}"

    def open_path(self, path: str) -> None:
        self._record("open_path", path)

    def search_files(self, query: str) -> None:
        self._record("search_files", query)


class FakeAssistant:
    """Ersetzt den Controller fuer die Mikrofon-Stummschaltung."""

    def __init__(self) -> None:
        self.muted = False

    def set_mic_muted(self, muted: bool) -> None:
        self.muted = muted

    def is_mic_muted(self) -> bool:
        return self.muted
