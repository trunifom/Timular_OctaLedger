"""Local player adapter: play internet radio streams and music files on this computer.

The adapter is a *thin sender*: it validates the request, then hands a command to the
:class:`~octaledger.infrastructure.audio.worker.AudioWorker` (a separate thread) and returns at
once, so neither the Bluetooth loop nor the action dispatcher ever waits for audio.

Safety rules (the player reaches out on behalf of a typed address, so they matter):

* web addresses: only ``http``/``https``, no credentials, the host is resolved and loopback,
  link-local and cloud-metadata addresses are always refused; **home-network addresses only with
  "LAN-Adressen erlauben"**; every redirect hop is checked again; only ``audio/*`` answers are
  played; nothing is downloaded or saved;
* files: only from **folders the user released**; the resolved path must stay below the folder
  (no ``..``, no links pointing out), only MP3/FLAC/WAV/OGG, size limit;
* the volume of this player is changed, never the system volume.

Honest limits: the bundled engine (optional extra ``audio``, ``miniaudio``) plays MP3, FLAC, WAV
and Vorbis but **no AAC**; real playback is not tested here. "Spielen Sie nur Inhalte ab, deren
Nutzung Ihnen erlaubt ist."
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from octaledger.core.errors import IntegrationError, ValidationError
from octaledger.infrastructure.audio.engine import (
    AudioEngine,
    MiniaudioEngine,
    UnavailableEngine,
    audio_available,
)
from octaledger.infrastructure.audio.worker import (
    AUDIO_EXTENSIONS,
    AudioWorker,
    Command,
    resolve_file,
)
from octaledger.infrastructure.integrations.base import (
    ActionSpec,
    Adapter,
    AdapterSpec,
    FieldSpec,
)
from octaledger.infrastructure.integrations.urlcheck import check_media_url

logger = logging.getLogger(__name__)

MAX_FOLDERS: Final = 10
MAX_LISTED_FILES: Final = 200
SCAN_DEPTH: Final = 3

SETUP_GUIDE: Final = """\
**Wofür:** Spielt einen **Internetradio-Stream** oder eine **Musikdatei** direkt an diesem PC ab, wenn Sie
den Würfel drehen. Kein Home Assistant nötig.

1. **Zusatzpaket** installieren: `pip install -e ".[audio]"` (MP3, FLAC, WAV, OGG; **kein AAC**).
2. **Verbindung anlegen** (keine Angaben nötig). Für eigene Dateien unter *Erweiterte Einstellungen* die
   **Ordner** eintragen, aus denen gespielt werden darf (mehrere mit Semikolon trennen).
3. Einer Würfelseite die Aktion **Stream abspielen** (Adresse eintragen) oder **Datei abspielen** geben und
   eine zweite Seite oder die Würfel-Halterung mit **Stoppen** belegen.

**Sicherheit:** Es werden nur `http(s)`-Adressen geöffnet, nie Adressen dieses Computers; Adressen im
**Heimnetz** nur, wenn Sie „LAN-Adressen erlauben“ einschalten. Dateien nur aus den freigegebenen Ordnern.
Es wird nichts gespeichert. Spielen Sie nur Inhalte ab, deren Nutzung Ihnen erlaubt ist.

**Grenzen:** Streams im **AAC**-Format laufen mit der eingebauten Engine nicht. Echte Wiedergabe ist noch
nicht an Ihrem Gerät geprüft.
"""  # noqa: E501


class PlayerAdapter(Adapter):
    """Plays streams and files on this computer (see the module docstring)."""

    spec = AdapterSpec(
        kind="player",
        title="Lokaler Player (dieser PC)",
        description=(
            "Spielt Internetradio-Streams und Musikdateien direkt an diesem PC ab. Braucht das "
            "Zusatzpaket „audio“."
        ),
        setup_guide=SETUP_GUIDE,
        config_fields=(
            FieldSpec(
                "volume",
                "Lautstärke (Voreinstellung in %)",
                kind="int",
                default=50,
                minimum=0,
                maximum=100,
                help="Mit dieser Lautstärke startet eine Wiedergabe, wenn die Aktion keine eigene "
                "angibt. Es ändert nur den Player, nicht die Lautstärke von Windows. "
                "Voreinstellung: 50.",
            ),
            FieldSpec(
                "allowed_folders",
                "Erlaubte Ordner für Dateien",
                advanced=True,
                placeholder=r"C:\Users\Name\Music;D:\Radio",
                help="Nur aus diesen Ordnern dürfen Musikdateien gespielt werden (mehrere mit "
                "Semikolon trennen, höchstens 10). Leer = Dateien sind nicht erlaubt.",
            ),
            FieldSpec(
                "allow_lan",
                "LAN-Adressen erlauben",
                advanced=True,
                kind="bool",
                default=False,
                help="Erlaubt Stream-Adressen im Heimnetz (192.168.x.x, 10.x.x.x). Nötig, wenn "
                "Ihr Radio im eigenen Netz steht. Voreinstellung: aus.",
            ),
        ),
        actions=(
            ActionSpec(
                "play_url",
                "Stream abspielen",
                "Spielt einen Internetradio-Stream ab (ersetzt, was gerade läuft).",
                (
                    FieldSpec(
                        "url",
                        "Stream-Adresse",
                        required=True,
                        placeholder="https://example.org/radio.mp3",
                        help="Eine http(s)-Adresse eines MP3-, OGG- oder FLAC-Streams. Keine "
                        "Zugangsdaten in der Adresse.",
                    ),
                    FieldSpec(
                        "volume",
                        "Lautstärke in % (optional)",
                        kind="int",
                        minimum=0,
                        maximum=100,
                        help="Leer lassen für die Voreinstellung der Verbindung.",
                    ),
                ),
                idempotent=False,
            ),
            ActionSpec(
                "play_file",
                "Datei abspielen",
                "Spielt eine Musikdatei aus einem freigegebenen Ordner (ersetzt, was läuft).",
                (
                    FieldSpec(
                        "file",
                        "Datei",
                        required=True,
                        choices_from=("files",),
                        placeholder="wählen über „Entdecken“",
                        help="Eine Datei aus den erlaubten Ordnern. „Entdecken“ listet sie auf.",
                    ),
                    FieldSpec(
                        "volume",
                        "Lautstärke in % (optional)",
                        kind="int",
                        minimum=0,
                        maximum=100,
                        help="Leer lassen für die Voreinstellung der Verbindung.",
                    ),
                ),
                idempotent=False,
            ),
            ActionSpec("stop", "Stoppen", "Beendet die Wiedergabe ganz."),
            ActionSpec(
                "volume",
                "Lautstärke setzen",
                "Ändert die Lautstärke des Players.",
                (
                    FieldSpec(
                        "level",
                        "Lautstärke in %",
                        kind="int",
                        required=True,
                        minimum=0,
                        maximum=100,
                        help="0 = stumm, 100 = voll (nur der Player).",
                    ),
                ),
            ),
        ),
        can_discover=True,
    )

    def __init__(self, worker: AudioWorker | None = None) -> None:
        """Create the adapter (``worker`` is replaceable for tests)."""
        self._worker = worker

    def _audio(self) -> AudioWorker:
        """The worker, created on first use with the real engine when it is installed."""
        if self._worker is None:
            factory: Any = MiniaudioEngine if audio_available() else UnavailableEngine
            self._worker = AudioWorker(factory)
        return self._worker

    @property
    def worker(self) -> AudioWorker:
        """The audio worker (its ``last_error`` and ``playing`` show the state)."""
        return self._audio()

    # ------------------------------------------------------------------ validation

    def validate_config(self, values: Mapping[str, Any]) -> dict[str, Any]:
        """Check the volume and that every released folder exists."""
        config = super().validate_config(values)
        raw = str(config.get("allowed_folders") or "")
        folders = [part.strip() for part in raw.split(";") if part.strip()]
        if len(folders) > MAX_FOLDERS:
            raise ValidationError(
                "Too many folders", user_message=f"Höchstens {MAX_FOLDERS} Ordner erlaubt."
            )
        for folder in folders:
            path = Path(folder)
            if not path.is_absolute() or not path.is_dir():
                raise ValidationError(
                    f"Folder {folder!r} is not an existing absolute directory",
                    user_message=f"Der Ordner „{folder}“ gibt es nicht (vollständigen Pfad "
                    "angeben).",
                    details={"field": "allowed_folders"},
                )
        config["allowed_folders"] = ";".join(folders)
        return config

    def validate_action(self, params: Mapping[str, Any]) -> dict[str, Any]:
        """Check the address syntax (the LAN rule is applied when the action runs)."""
        cleaned = super().validate_action(params)
        if cleaned["action"] == "play_url":
            # The connection's LAN setting is not known here, so LAN addresses pass this check
            # and are refused at run time unless allowed; unsafe addresses never pass.
            cleaned["url"] = check_media_url(str(cleaned["url"]), allow_lan=True)
        return cleaned

    # ----------------------------------------------------------------- operations

    @staticmethod
    def _folders(config: Mapping[str, Any]) -> list[Path]:
        raw = str(config.get("allowed_folders") or "")
        return [Path(p.strip()) for p in raw.split(";") if p.strip()]

    def check(
        self, config: Mapping[str, Any], secrets: Mapping[str, str], *, timeout: float
    ) -> str:
        """Report whether an audio engine is installed (plays nothing)."""
        if not audio_available() and self._worker is None:
            raise IntegrationError(
                "No audio engine",
                user_message='Das Zusatzpaket „audio“ fehlt: pip install -e ".[audio]".',
            )
        return "Der lokale Player ist bereit (MP3, FLAC, WAV, OGG; kein AAC)."

    def execute(
        self,
        config: Mapping[str, Any],
        secrets: Mapping[str, str],
        params: Mapping[str, Any],
        *,
        timeout: float,
    ) -> str:
        """Hand the request to the audio worker and return at once."""
        action = str(params["action"])
        default = int(config.get("volume", 50)) / 100
        level = params.get("volume")
        volume = default if level is None else int(level) / 100
        if action == "stop":
            self._audio().submit(Command("stop"))
            return "Wiedergabe beendet."
        if action == "volume":
            self._audio().submit(Command("volume", int(params["level"]) / 100))
            return "Lautstärke gesetzt."
        if action == "play_url":
            allow_lan = bool(config.get("allow_lan", False))
            url = check_media_url(str(params["url"]), allow_lan=allow_lan)
            self._audio().submit(Command("play_url", url, volume, allow_lan))
            return "Stream wird gestartet."
        path = resolve_file(self._folders(config), str(params["file"]))
        self._audio().submit(Command("play_file", path, volume))
        return "Datei wird abgespielt."

    def discover(
        self, config: Mapping[str, Any], secrets: Mapping[str, str], *, timeout: float
    ) -> dict[str, list[dict[str, str]]]:
        """List the audio files of the released folders (not recursive beyond three levels)."""
        files: list[dict[str, str]] = []
        for number, folder in enumerate(self._folders(config)):
            base = folder.resolve()
            for current, dirs, names in os.walk(base):
                depth = len(Path(current).relative_to(base).parts)
                if depth >= SCAN_DEPTH:
                    dirs.clear()
                for name in sorted(names):
                    if Path(name).suffix.lower() in AUDIO_EXTENSIONS:
                        relative = (Path(current) / name).relative_to(base).as_posix()
                        files.append(
                            {"id": f"{number}:{relative}", "name": f"{folder.name} / {relative}"}
                        )
                        if len(files) >= MAX_LISTED_FILES:
                            return {"files": files}
        return {"files": files} if files else {}


def default_engine() -> AudioEngine:
    """The engine used when none is injected (real playback if the extra is installed)."""
    return MiniaudioEngine() if audio_available() else UnavailableEngine()
