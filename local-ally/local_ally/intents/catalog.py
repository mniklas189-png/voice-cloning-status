"""Alle Absichten als Daten.

Hier steht, *was* Local Ally versteht - nicht *wie*. Eine neue Faehigkeit
braucht einen Eintrag in dieser Liste und eine Aktion gleichen Namens in
:mod:`local_ally.actions`; am Erkenner selbst aendert sich nichts.

Zu den Mustern siehe :mod:`.pattern`. Der Text ist beim Vergleich bereits
normalisiert: klein, ohne Umlaute ("oeffne", "lautstaerke"), ohne
Satzzeichen und ohne Fuellwoerter.
"""

from __future__ import annotations

from .model import IntentSpec

# --- Audio -------------------------------------------------------------
AUDIO = [
    IntentSpec(
        id="audio.volume.up",
        action="audio.volume.up",
        templates=[
            "(mach|dreh|stell|schalt) * (lauter|laut)",
            "lauter",
            "(erhoehe|erhoeh|steigere) * lautstaerke",
            "lautstaerke (hoch|rauf|erhoehen|hochdrehen)",
            "(mehr|hoehere) lautstaerke",
        ],
        description="Lautstärke erhöhen",
        examples=("Mach es etwas lauter", "Lautstärke hoch"),
    ),
    IntentSpec(
        id="audio.volume.down",
        action="audio.volume.down",
        templates=[
            "(mach|dreh|stell|schalt) * (leiser|leise)",
            "leiser",
            "(verringere|reduziere|senke) * lautstaerke",
            "lautstaerke (runter|leiser|verringern|senken|runterdrehen)",
            "(weniger|niedrigere) lautstaerke",
        ],
        description="Lautstärke verringern",
        examples=("Mach es leiser",),
    ),
    IntentSpec(
        id="audio.volume.set",
        action="audio.volume.set",
        templates=[
            "(setz|setze|stell|stelle|mach|dreh) * lautstaerke auf {level}",
            "lautstaerke auf {level}",
            "(setz|setze|stell|stelle) * (ton|sound) auf {level}",
            "lautstaerke {level}",
        ],
        slots={"level": "level"},
        priority=1,   # konkreter als "lauter/leiser"
        description="Bestimmte Lautstärke setzen",
        examples=("Stell die Lautstärke auf 60 Prozent",),
    ),
    IntentSpec(
        id="audio.mute",
        action="audio.mute",
        templates=[
            "(mute|mut) * (pc|rechner|computer|ton|sound)",
            "mute",
            "(schalt|schalte|mach|stell) * (stumm|lautlos)",
            "(stumm|lautlos|stummschalten)",
            "(mach|schalt|schalte|dreh) * (ton|sound|lautsprecher) (aus|ab)",
            "(ton|sound|lautsprecher) (aus|ab)",
        ],
        description="Ton stummschalten",
        examples=("Mute meinen PC", "Ton aus"),
    ),
    IntentSpec(
        id="audio.unmute",
        action="audio.unmute",
        templates=[
            "(stummschaltung|stumm) (aufheben|beenden|aus|weg)",
            "(unmute|entstummen)",
            "(mach|schalt|schalte|stell) * (ton|sound|lautsprecher) (an|ein|wieder an)",
            "(ton|sound) (an|ein|wieder da)",
            "nicht mehr stumm",
        ],
        priority=1,   # "ton an" darf nicht als Stummschalten gelesen werden
        description="Stummschaltung aufheben",
        examples=("Ton wieder an",),
    ),
    IntentSpec(
        id="audio.mic.mute",
        action="audio.mic.mute",
        templates=[
            "(mach|schalt|schalte|stell|dreh) * (mikro|mikrofon|mic) (aus|ab|stumm)",
            "(mikro|mikrofon|mic) (aus|stumm|stummschalten|abschalten)",
            "(mute|stumm) * (mikro|mikrofon|mic)",
        ],
        priority=2,   # geht dem allgemeinen Stummschalten vor
        description="Mikrofon stummschalten",
        examples=("Mach mein Mikro aus",),
    ),
    IntentSpec(
        id="audio.mic.unmute",
        action="audio.mic.unmute",
        templates=[
            "(mach|schalt|schalte|stell) * (mikro|mikrofon|mic) (an|ein|wieder an)",
            "(mikro|mikrofon|mic) (an|ein|anschalten|aktivieren)",
        ],
        priority=2,
        description="Mikrofon wieder aktivieren",
        examples=("Mikro wieder an",),
    ),
    IntentSpec(
        id="audio.device.switch",
        action="audio.device.switch",
        templates=[
            "(wechsle|wechsel|aendere|wechseln) * (audiogeraet|ausgabegeraet|audioausgang|soundausgang)",
            "(audiogeraet|ausgabegeraet|audioausgang|soundausgang) (wechseln|aendern|umschalten)",
            "(wechsle|wechsel|schalt|schalte) * (auf|zu) {device}",
            "(spiel|gib) * ueber {device} (aus|ab)",
        ],
        slots={"device": "device"},
        description="Audiogerät wechseln",
        examples=("Wechsle auf Kopfhörer",),
    ),
]

# --- Windows-Steuerung -------------------------------------------------
SYSTEM = [
    IntentSpec(
        id="system.lock",
        action="system.lock",
        templates=[
            "(sperr|sperre|sperren) *",
            "(pc|rechner|computer|bildschirm) sperren",
        ],
        description="PC sperren",
        examples=("Sperr meinen PC",),
    ),
    IntentSpec(
        id="system.shutdown",
        action="system.shutdown",
        templates=[
            "(fahr|fahre) * (herunter|runter)",
            "(herunterfahren|shutdown|runterfahren)",
            "(pc|rechner|computer) (ausschalten|abschalten|herunterfahren)",
            "(schalt|schalte) * (pc|rechner|computer) (aus|ab)",
        ],
        confirm="Soll ich den PC wirklich herunterfahren?",
        priority=2,
        description="Herunterfahren",
        examples=("Fahr den PC herunter",),
    ),
    IntentSpec(
        id="system.restart",
        action="system.restart",
        templates=[
            "(starte|start|fahr) * neu",
            "(neustart|neustarten|reboot)",
            "(pc|rechner|computer) neu starten",
        ],
        confirm="Soll ich den PC wirklich neu starten?",
        priority=2,
        description="Neustarten",
        examples=("Starte den PC neu",),
    ),
    IntentSpec(
        id="system.sleep",
        action="system.sleep",
        templates=[
            "(energiesparmodus|ruhezustand|standby|schlafmodus)",
            "(geh|gehe|schick|schicke) * (schlafen|standby|ruhezustand)",
            "(pc|rechner|computer) schlafen legen",
        ],
        description="Energiesparmodus",
        examples=("Energiesparmodus",),
    ),
    IntentSpec(
        id="system.screen_off",
        action="system.screen_off",
        templates=[
            "(mach|schalt|schalte|dreh) * (bildschirm|monitor|display) (aus|ab)",
            "(bildschirm|monitor|display) (aus|ausschalten|abschalten)",
        ],
        priority=1,   # sonst greift das allgemeine "mach ... aus"
        description="Bildschirm ausschalten",
        examples=("Mach den Bildschirm aus",),
    ),
    IntentSpec(
        id="system.settings",
        action="system.settings",
        templates=[
            "(oeffne|zeig|zeige|starte) * (einstellungen|systemeinstellungen|systemsteuerung)",
            "(einstellungen|systemeinstellungen|systemsteuerung) (oeffnen|zeigen)",
        ],
        priority=1,
        description="Einstellungen öffnen",
        examples=("Öffne die Einstellungen",),
    ),
    IntentSpec(
        id="system.taskmanager",
        action="system.taskmanager",
        templates=[
            "(oeffne|zeig|zeige|starte) * (task manager|taskmanager|aufgabenmanager)",
            "(task manager|taskmanager|aufgabenmanager)",
        ],
        priority=1,
        description="Task-Manager öffnen",
        examples=("Öffne den Task-Manager",),
    ),
    IntentSpec(
        id="system.wifi",
        action="system.wifi",
        templates=[
            "(oeffne|zeig|zeige) * (wlan|wifi|netzwerk) *",
            "(wlan|wifi) (oeffnen|einstellungen|zeigen)",
        ],
        priority=1,
        description="WLAN-Einstellungen öffnen",
        examples=("Öffne WLAN",),
    ),
    IntentSpec(
        id="system.bluetooth",
        action="system.bluetooth",
        templates=[
            "(oeffne|zeig|zeige) * bluetooth *",
            "bluetooth (oeffnen|einstellungen|zeigen)",
        ],
        priority=1,
        description="Bluetooth-Einstellungen öffnen",
        examples=("Öffne Bluetooth",),
    ),
    IntentSpec(
        id="system.brightness.up",
        action="system.brightness.up",
        templates=[
            "(mach|stell|dreh) * heller",
            "(helligkeit) (hoch|rauf|erhoehen)",
            "heller",
        ],
        description="Bildschirm heller",
        examples=("Mach den Bildschirm heller",),
    ),
    IntentSpec(
        id="system.brightness.down",
        action="system.brightness.down",
        templates=[
            "(mach|stell|dreh) * dunkler",
            "(helligkeit) (runter|senken|verringern)",
            "dunkler",
        ],
        description="Bildschirm dunkler",
        examples=("Mach den Bildschirm dunkler",),
    ),
    IntentSpec(
        id="system.brightness.set",
        action="system.brightness.set",
        templates=[
            "(setz|setze|stell|stelle) * helligkeit auf {level}",
            "helligkeit auf {level}",
        ],
        slots={"level": "level"},
        priority=1,
        description="Helligkeit setzen",
        examples=("Stell die Helligkeit auf 50 Prozent",),
    ),
    IntentSpec(
        id="system.display.switch",
        action="system.display.switch",
        templates=[
            "(wechsle|wechsel|aendere|umschalten) * (monitor|bildschirm|anzeige) *",
            "(anzeige|bildschirm|monitor) (wechseln|umschalten)",
            "(zweiter|zweiten) (bildschirm|monitor) *",
        ],
        slots={},
        description="Anzeige umschalten",
        examples=("Wechsle den Monitor",),
    ),
    IntentSpec(
        id="system.display.mode",
        action="system.display.mode",
        templates=[
            "(anzeige|bildschirm|monitor|bildschirme) (duplizieren|erweitern|spiegeln)",
            "(dupliziere|erweitere|spiegle) * (anzeige|bildschirm|bildschirme|monitor)",
            "nur (pc|erster|zweiter) (bildschirm|monitor)",
        ],
        priority=1,
        description="Anzeigemodus wählen",
        examples=("Bildschirme erweitern",),
    ),
]

# --- Fenster -----------------------------------------------------------
WINDOWS = [
    IntentSpec(
        id="window.switch",
        action="window.switch",
        templates=[
            "(wechsle|wechsel|wechseln|spring|springe) * (fenster|programm|anwendung)",
            "(naechstes|anderes) fenster",
            "(fenster|programm) (wechseln|umschalten)",
        ],
        priority=1,
        description="Zwischen Fenstern wechseln",
        examples=("Wechsle das Fenster",),
    ),
    IntentSpec(
        id="window.minimize",
        action="window.minimize",
        templates=[
            "(minimier|minimiere|minimieren) *",
            "fenster (minimieren|klein machen|verkleinern)",
        ],
        priority=1,
        description="Fenster minimieren",
        examples=("Minimier das Fenster",),
    ),
    IntentSpec(
        id="window.maximize",
        action="window.maximize",
        templates=[
            "(maximier|maximiere|maximieren) *",
            "fenster (maximieren|gross machen|vergroessern|vollbild)",
        ],
        priority=1,
        description="Fenster maximieren",
        examples=("Maximier das Fenster",),
    ),
    IntentSpec(
        id="window.close",
        action="window.close",
        templates=[
            "(schliess|schliesse|schliessen|mach) * fenster *",
            "fenster (schliessen|zumachen|zu)",
        ],
        confirm="Soll ich das aktive Fenster schließen? Ungespeichertes geht dabei verloren.",
        priority=2,   # schlaegt "schliess <Programm>"
        description="Fenster schließen",
        examples=("Mach das Fenster zu",),
    ),
]

# --- Programme ---------------------------------------------------------
APPS = [
    IntentSpec(
        id="app.open",
        action="app.open",
        templates=[
            "(oeffne|oeffnen|starte|start|starten|zeig|zeige|fuehre) {app}",
            "(mach|fahr) {app} (auf|hoch)",
            "{app} (oeffnen|starten|aufmachen|hochfahren)",
        ],
        slots={"app": "app"},
        description="Programm öffnen",
        examples=("Öffne Discord", "Spotify öffnen"),
    ),
    IntentSpec(
        id="app.close",
        action="app.close",
        templates=[
            "(schliess|schliesse|schliessen|beende|beenden|kill) {app}",
            "{app} (schliessen|beenden|zumachen|killen)",
        ],
        slots={"app": "app"},
        confirm="Soll ich {app} wirklich schließen? Ungespeichertes geht dabei verloren.",
        description="Programm schließen",
        examples=("Schließ Spotify",),
    ),
    IntentSpec(
        id="app.running",
        action="app.running",
        templates=[
            "(laeuft|lauft) {app}",
            "(ist|laeuft) {app} (offen|geoeffnet|aktiv|an)",
            "(pruef|pruefe|schau|check) ob {app} laeuft",
        ],
        slots={"app": "app"},
        priority=1,
        description="Prüfen, ob ein Programm läuft",
        examples=("Läuft Discord?",),
    ),
    IntentSpec(
        id="app.switch",
        action="app.switch",
        templates=[
            "(wechsle|wechsel|wechseln|spring|springe|geh|gehe) zu {app}",
            "(hol|hole|zeig|zeige) {app} nach vorne",
            "(zu|nach) {app} wechseln",
        ],
        slots={"app": "app"},
        priority=1,
        description="Zu einem laufenden Programm wechseln",
        examples=("Wechsle zu Discord",),
    ),
]

# --- Medien ------------------------------------------------------------
MEDIA = [
    IntentSpec(
        id="media.playpause",
        action="media.playpause",
        templates=[
            "(play|pause|pausiere|weiter|weiterspielen)",
            "(spiel|spiele|mach|lauf) weiter",
            "(mach|spiel|spiele) * (musik|wiedergabe|song|lied|video) (weiter|an|ab)",
            "(stopp|stoppe|halt|halte|pausier) * (musik|wiedergabe|song|lied|video)",
            "(musik|wiedergabe) (pausieren|anhalten|weiter|starten)",
        ],
        priority=1,
        description="Wiedergabe starten oder anhalten",
        examples=("Mach die Musik weiter", "Pause"),
    ),
    IntentSpec(
        id="media.next",
        action="media.next",
        templates=[
            "(naechster|naechstes|naechsten) (titel|song|lied|track|stueck)",
            "(spiel|spiele|spring|springe) * (naechsten|vor|weiter zum naechsten)",
            "(skip|ueberspringen|weiterskippen)",
            "(naechstes|weiter) lied",
        ],
        priority=1,
        description="Nächster Titel",
        examples=("Nächster Titel",),
    ),
    IntentSpec(
        id="media.previous",
        action="media.previous",
        templates=[
            "(vorheriger|vorheriges|vorherigen|letzter|letztes|voriger) (titel|song|lied|track|stueck)",
            "(spiel|spiele|spring|springe) * (zurueck|vorherigen)",
            "(nochmal|wiederhole) * (titel|song|lied)",
        ],
        priority=1,
        description="Vorheriger Titel",
        examples=("Vorheriger Titel",),
    ),
]

# --- Dateien und Ordner ------------------------------------------------
FILES = [
    IntentSpec(
        id="files.folder",
        action="files.folder",
        templates=[
            "(oeffne|zeig|zeige|geh|gehe|starte) * {folder} *",
            "{folder} (oeffnen|zeigen|anzeigen)",
            "{folder}",
        ],
        slots={"folder": "folder"},
        priority=2,   # bekannter Ordner schlaegt Programmsuche
        description="Bekannten Ordner öffnen",
        examples=("Zeig mir meine Downloads",),
    ),
    IntentSpec(
        id="files.search",
        action="files.search",
        templates=[
            "(such|suche|finde|find) * (datei|dateien|ordner) {query}",
            "(such|suche|finde|find) nach {query}",
            "(such|suche|finde|find) {query}",
        ],
        slots={"query": "query"},
        priority=1,
        description="Dateien suchen",
        examples=("Suche nach Rechnung",),
    ),
]


def all_specs() -> list[IntentSpec]:
    """Der vollstaendige Katalog."""
    return [*AUDIO, *SYSTEM, *WINDOWS, *APPS, *MEDIA, *FILES]
