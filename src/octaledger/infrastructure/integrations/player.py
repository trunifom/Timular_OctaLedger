"""Local player adapter: play internet radio streams and music files on this computer.

The adapter is a *thin sender*: it validates the request, then hands a command to the
:class:`~octaledger.infrastructure.audio.worker.AudioWorker` (a separate thread) and returns at
once, so neither the Bluetooth loop nor the action dispatcher ever waits for audio.

What it plays (AP-61): internet radio streams, **single files, whole folders (albums) and
playlist files** (``.m3u``) from this computer - once, as a loop over everything, or one track
endlessly, optionally shuffled - with next, previous, pause and stop at any time. The path may be
typed or picked in a file dialog; files from the optional released folders of the connection keep
working as before.

Safety rules (the player reaches out on behalf of a typed address, so they matter):

* web addresses: only ``http``/``https``, no credentials, the host is resolved and loopback,
  link-local and cloud-metadata addresses are always refused; **home-network addresses only with
  "LAN-Adressen erlauben"**; every redirect hop is checked again; only ``audio/*`` answers are
  played; nothing is downloaded or saved;
* files chosen from the **released folders**: the resolved path must stay below the folder (no
  ``..``, no links pointing out), only MP3/FLAC/WAV/OGG, size limit;
* free **local paths** (typed or picked): absolute, on a local drive (no network or device paths),
  only playable extensions, scanned with a depth and count limit;
* the volume of this player is changed, never the system volume.

Honest limits: the bundled engine (optional extra ``audio``, ``miniaudio``) plays MP3, FLAC, WAV
and Vorbis; **AAC/M4A, WMA, Opus and the sound of video files need FFmpeg** on the computer; real
playback and FFmpeg are not tested against real hardware here. "Spielen Sie nur Inhalte ab, deren
Nutzung Ihnen erlaubt ist."
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any, Final

from octaledger.core.errors import IntegrationError, ValidationError
from octaledger.domain.media_formats import support_text
from octaledger.domain.music_source import MusicSource, SourceKind
from octaledger.domain.playlist import REPEAT_TEXT, Repeat, parse_repeat
from octaledger.infrastructure.audio.engine import (
    MiniaudioEngine,
    UnavailableEngine,
    audio_available,
)
from octaledger.infrastructure.audio.ffmpeg import find_ffmpeg
from octaledger.infrastructure.audio.paths import clean_path_text, reject_unsafe, resolve_media
from octaledger.infrastructure.audio.worker import (
    AUDIO_EXTENSIONS,
    AudioWorker,
    Command,
    PlayerStatus,
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


def _int_between(value: Any, low: int, high: int, name: str) -> int:
    """``value`` as an integer within ``low..high``.

    Raises:
        ValidationError: With a German message naming ``name`` if it is not.
    """
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = low - 1
    if isinstance(value, bool) or not low <= number <= high:
        raise ValidationError(
            f"Value out of range: {value!r}",
            user_message=f"{name} muss eine Zahl von {low} bis {high} sein.",
        )
    return number


MAX_FOLDERS: Final = 10
MAX_LISTED_FILES: Final = 200
SCAN_DEPTH: Final = 3

SETUP_GUIDE: Final = """\
**Wofür:** Spielt einen **Internetradio-Stream** oder eine **Musikdatei** direkt an diesem PC ab, wenn Sie
den Würfel drehen. Kein Home Assistant nötig.

1. **Zusatzpaket** installieren: `pip install -e ".[audio]"` (MP3, FLAC, WAV, OGG). Für **AAC/M4A, WMA, Opus
   und den Ton von Videodateien** zusätzlich **FFmpeg** installieren (`winget install ffmpeg`); OctaLedger
   findet es selbst.
2. **Verbindung anlegen** (keine Angaben nötig).
3. Im **Musik-Modus** einer Würfelseite einen **Pfad** geben: eine Datei, einen **Ordner (Album)** oder eine
   Playlist-Datei (.m3u) von diesem Computer, dazu **einmal**, **alles wiederholen** oder **einen Titel
   endlos** und optional **zufällige Reihenfolge**. Im **Musik-Player** können Sie dasselbe jederzeit direkt
   starten, anhalten, überspringen und stoppen.
4. Im Steuerungsmodus gibt es die Aktionen **Stream abspielen**, **Datei abspielen** und **Pfad abspielen**
   sowie **Stoppen**.

**Sicherheit:** Es werden nur `http(s)`-Adressen geöffnet, nie Adressen dieses Computers; Adressen im
**Heimnetz** nur, wenn Sie „LAN-Adressen erlauben“ einschalten. Pfade nur auf **lokalen Laufwerken**
(keine Netzwerkpfade). Es wird nichts kopiert oder gespeichert. Spielen Sie nur Inhalte ab, deren Nutzung
Ihnen erlaubt ist.

**Grenzen:** Echte Wiedergabe und FFmpeg sind noch nicht an Ihrem Gerät geprüft. Die Lautstärke gilt nur für
diesen Player, nicht für Windows.
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
                capability="music",
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
                capability="music",
            ),
            ActionSpec(
                "play_path",
                "Pfad abspielen (Datei, Ordner, Album)",
                "Spielt eine Datei, einen Ordner (Album) oder eine Playlist-Datei von diesem "
                "Computer (ersetzt, was gerade läuft).",
                (
                    FieldSpec(
                        "path",
                        "Pfad",
                        required=True,
                        placeholder="C:/Musik/Album oder C:/Musik/lied.mp3",
                        help="Der vollständige Pfad einer Datei, eines Ordners oder einer .m3u-"
                        "Playlist auf einem lokalen Laufwerk (keine Netzwerkpfade). Ein Ordner "
                        "wird mit allen Unterordnern in Dateinamen-Reihenfolge gespielt.",
                    ),
                    FieldSpec(
                        "repeat",
                        "Wiederholen",
                        kind="choice",
                        choices=tuple((key, text) for key, text in REPEAT_TEXT.items()),
                        default=Repeat.OFF.value,
                        help="Einmal abspielen, alles immer wieder oder einen Titel endlos. "
                        "Voreinstellung: einmal.",
                    ),
                    FieldSpec(
                        "shuffle",
                        "Zufällige Reihenfolge",
                        kind="bool",
                        default=False,
                        help="Mischt die Titel eines Ordners oder einer Playlist.",
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
                capability="music",
            ),
            ActionSpec("stop", "Stoppen", "Beendet die Wiedergabe ganz.", capability="music"),
            ActionSpec("pause", "Pausieren", "Hält die Wiedergabe an (Fortsetzen geht weiter)."),
            ActionSpec("resume", "Fortsetzen", "Setzt eine pausierte Wiedergabe fort."),
            ActionSpec("next", "Nächster Titel", "Springt zum nächsten Titel der Liste."),
            ActionSpec("previous", "Vorheriger Titel", "Springt zum vorherigen Titel der Liste."),
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

    def __init__(
        self,
        worker: AudioWorker | None = None,
        ffmpeg_finder: Callable[[], str | None] = find_ffmpeg,
    ) -> None:
        """Create the adapter (``worker`` and the FFmpeg lookup are replaceable for tests)."""
        self._worker = worker
        self._find_ffmpeg = ffmpeg_finder

    def status(self) -> dict[str, Any]:
        """What the player does now (see ``PlayerStatus`` of the audio worker).

        The audio worker is only created when something was played; before that the player is
        simply stopped, so asking never starts a thread.
        """
        if self._worker is None:
            return {**asdict(PlayerStatus()), "ffmpeg": self._find_ffmpeg() is not None}
        return asdict(self._worker.status())

    def control(self, action: str, value: Any = None) -> str:
        """Control the running playback from the app (same actions the cube can trigger).

        Args:
            action: ``stop``, ``pause``, ``resume``, ``next``, ``previous``, ``volume``,
                ``repeat``, ``shuffle`` or ``jump`` (``value`` is the 0-based queue position).
            value: Level (0-100), repeat mode, ``True``/``False`` or the position.

        Raises:
            ValidationError: For an unknown action or a wrong value.
            IntegrationError: If the player is busy.
        """
        worker = self._audio()
        if action in ("stop", "pause", "resume", "next", "previous"):
            worker.submit(Command(action))
        elif action == "volume":
            level = _int_between(value, 0, 100, "Die Lautstärke")
            worker.submit(Command("volume", level / 100))
        elif action == "repeat":
            worker.submit(Command("set_repeat", parse_repeat(value).value))
        elif action == "shuffle":
            worker.submit(Command("set_shuffle", bool(value)))
        elif action == "jump":
            worker.submit(Command("jump", float(_int_between(value, 0, 100000, "Die Nummer"))))
        else:
            raise ValidationError(
                f"Unknown player action {action!r}",
                user_message="Diese Aktion kennt der Player nicht.",
            )
        return "ok"

    def play(
        self, path: str, *, repeat: str = "off", shuffle: bool = False, volume: int = 50
    ) -> int:
        """Play a local file, folder or playlist now (used by the page *Musik-Player*).

        Returns:
            The number of tracks that were queued.

        Raises:
            ValidationError: If the path is unsafe, missing or has nothing playable.
        """
        tracks = resolve_media(path, ffmpeg=self._find_ffmpeg() is not None)
        self._audio().submit(
            Command(
                "play_queue",
                tracks=tuple(tracks),
                repeat=parse_repeat(repeat),
                shuffle=shuffle,
                volume=_int_between(volume, 0, 100, "Die Lautstärke") / 100,
            )
        )
        return len(tracks)

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
        if cleaned["action"] == "play_path":
            cleaned["path"] = str(reject_unsafe(clean_path_text(cleaned["path"])))
            cleaned["repeat"] = parse_repeat(cleaned.get("repeat", Repeat.OFF.value)).value
        if cleaned["action"] == "play_url":
            # The connection's LAN setting is not known here, so LAN addresses pass this check
            # and are refused at run time unless allowed; unsafe addresses never pass.
            cleaned["url"] = check_media_url(str(cleaned["url"]), allow_lan=True)
        return cleaned

    # ----------------------------------------------------------------------- music

    def music_play_params(
        self, source: MusicSource, volume: int, options: Mapping[str, str]
    ) -> list[dict[str, Any]]:
        """A stream address or a chosen file; Spotify and YouTube links need another target."""
        if options.get("file"):
            return [{"action": "play_file", "file": options["file"], "volume": volume}]
        if source.kind is SourceKind.LOCAL:
            repeat = parse_repeat(options.get("repeat", Repeat.OFF.value)).value
            shuffle = str(options.get("shuffle", "")).lower() in ("1", "true", "yes", "ja")
            # Checked now so a wrong path is reported when the title is saved, not on the first
            # turn of the cube; the folder is read again when it plays (new files are found).
            resolve_media(source.ref, ffmpeg=self._find_ffmpeg() is not None)
            return [
                {
                    "action": "play_path",
                    "path": source.ref,
                    "repeat": repeat,
                    "shuffle": shuffle,
                    "volume": volume,
                }
            ]
        if source.kind is not SourceKind.URL:
            raise ValidationError(
                "The local player plays only streams and local files",
                user_message="Der lokale Player spielt nur Stream-Adressen und Pfade auf diesem "
                "Computer. Spotify-Links gehen über „Spotify“ oder Home Assistant, YouTube-Links "
                "über „Player in der App“ oder Home Assistant (Cast).",
            )
        return [{"action": "play_url", "url": source.ref, "volume": volume}]

    def music_stop_params(
        self, play_params: Mapping[str, Any], pause: bool = False
    ) -> dict[str, Any] | None:
        """The player has no pause, so pausing stops."""
        return {"action": "stop"}

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
        return "Der lokale Player ist bereit. " + support_text(
            ffmpeg=self._find_ffmpeg() is not None
        )

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
        if action in ("pause", "resume", "next", "previous"):
            self._audio().submit(Command(action))
            return {
                "pause": "Wiedergabe pausiert.",
                "resume": "Wiedergabe fortgesetzt.",
                "next": "Nächster Titel.",
                "previous": "Vorheriger Titel.",
            }[action]
        if action == "play_path":
            tracks = resolve_media(params["path"], ffmpeg=self._find_ffmpeg() is not None)
            self._audio().submit(
                Command(
                    "play_queue",
                    tracks=tuple(tracks),
                    repeat=parse_repeat(params.get("repeat", Repeat.OFF.value)),
                    shuffle=bool(params.get("shuffle", False)),
                    volume=volume,
                )
            )
            return f"{len(tracks)} Titel werden abgespielt."
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
