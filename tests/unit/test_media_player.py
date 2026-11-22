# ruff: noqa: F401, F811  (the Home Assistant fixture is re-used from test_adapter_homeassistant)
"""Media: safe addresses, Home Assistant media actions, the local player and its worker (AP-45)."""

import io
import os
import threading
import time
from pathlib import Path
from typing import Any, BinaryIO

import pytest

from octaledger.core.errors import IntegrationError, ValidationError
from octaledger.infrastructure.audio.engine import UnavailableEngine, audio_available
from octaledger.infrastructure.audio.worker import (
    AudioWorker,
    Command,
    open_stream,
    resolve_file,
)
from octaledger.infrastructure.integrations.player import PlayerAdapter
from octaledger.infrastructure.integrations.registry import default_adapters
from octaledger.infrastructure.integrations.urlcheck import (
    MAX_REDIRECTS,
    check_media_url,
    follow_redirects,
    resolve_checked,
)
from tests.unit.test_adapter_homeassistant import (
    SECRETS,
    TIMEOUT,
    FakeHomeAssistant,
    action,
    adapter,
    config,
    ha,
)

PUBLIC = "93.184.216.34"  # a public address literal: no DNS is needed in the tests


def resolver(mapping: dict[str, list[str]]):  # type: ignore[no-untyped-def]
    def resolve(host: str, port: int) -> list[str]:
        if host not in mapping:
            raise ValidationError("unknown host", user_message="Name nicht auflösbar.")
        return mapping[host]

    return resolve


# ------------------------------------------------------------ the address check


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/stream",
        "http://[::1]/stream",
        "http://0.0.0.0/stream",
        "http://169.254.169.254/latest/meta-data",
        "http://169.254.1.1/x",
        "http://[fe80::1]/x",
        "http://224.0.0.1/x",
        "http://[fd00:ec2::254]/x",
        "ftp://example.org/x",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "https://user:pass@example.org/x",
        "https://user@example.org/x",
        "http://",
        "http://exa mple.org/x",
        "http://example.org/\nx",
        "",
        "   ",
        "http://example.org/" + "a" * 2100,
    ],
)
def test_dangerous_or_malformed_addresses_are_always_refused(url: str) -> None:
    with pytest.raises(ValidationError):
        check_media_url(url, allow_lan=True, resolver=resolver({"example.org": [PUBLIC]}))


def test_a_public_address_passes_and_is_returned_unchanged() -> None:
    assert check_media_url(f"https://{PUBLIC}/radio.mp3") == f"https://{PUBLIC}/radio.mp3"
    assert check_media_url(
        "https://radio.example/live", resolver=resolver({"radio.example": [PUBLIC]})
    ).endswith("/live")


@pytest.mark.parametrize("address", ["192.168.1.20", "10.0.0.5", "172.16.4.4", "172.31.255.1"])
def test_home_network_addresses_need_the_lan_switch(address: str) -> None:
    url = f"http://{address}:8000/stream"
    with pytest.raises(ValidationError) as info:
        check_media_url(url)
    assert "LAN-Adressen erlauben" in info.value.user_message
    assert check_media_url(url, allow_lan=True) == url


def test_a_name_resolving_to_a_forbidden_address_is_refused() -> None:
    sneaky = resolver({"evil.example": [PUBLIC, "127.0.0.1"], "meta.example": ["169.254.169.254"]})
    for host in ("evil.example", "meta.example"):
        with pytest.raises(ValidationError):
            check_media_url(f"http://{host}/x", allow_lan=True, resolver=sneaky)
    with pytest.raises(ValidationError):
        check_media_url("http://unknown.example/x", resolver=sneaky)


def test_resolve_checked_returns_the_addresses_to_connect_to() -> None:
    assert resolve_checked(
        "http://radio.example/x", resolver=resolver({"radio.example": [PUBLIC]})
    ) == [PUBLIC]
    assert resolve_checked(f"http://{PUBLIC}:8080/x") == [PUBLIC]


def test_every_redirect_hop_is_checked_again() -> None:
    hops = {
        f"http://{PUBLIC}/a": f"http://{PUBLIC}/b",
        f"http://{PUBLIC}/b": "http://127.0.0.1/secret",
    }
    with pytest.raises(ValidationError):
        follow_redirects(f"http://{PUBLIC}/a", hops.get)
    ok = {f"http://{PUBLIC}/a": f"http://{PUBLIC}/final"}
    assert follow_redirects(f"http://{PUBLIC}/a", ok.get) == f"http://{PUBLIC}/final"


def test_too_many_redirects_are_refused() -> None:
    with pytest.raises(ValidationError):
        follow_redirects(f"http://{PUBLIC}/a", lambda url: f"http://{PUBLIC}/loop")
    assert MAX_REDIRECTS == 3


# -------------------------------------------------------- Home Assistant media


@pytest.mark.parametrize(
    ("fields", "path", "body"),
    [
        (
            {
                "action": "media_play",
                "entity_id": "media_player.wz",
                "media_url": f"https://{PUBLIC}/r.mp3",
            },
            "media_player/play_media",
            {
                "entity_id": "media_player.wz",
                "media_content_id": f"https://{PUBLIC}/r.mp3",
                "media_content_type": "music",
            },
        ),
        (
            {
                "action": "media_play",
                "entity_id": "media_player.wz",
                "media_url": "http://192.168.1.50:8000/radio",
                "media_type": "audio/mpeg",
            },
            "media_player/play_media",
            {
                "entity_id": "media_player.wz",
                "media_content_id": "http://192.168.1.50:8000/radio",
                "media_content_type": "audio/mpeg",
            },
        ),
        (
            {"action": "media_pause", "entity_id": "media_player.wz"},
            "media_player/media_pause",
            {"entity_id": "media_player.wz"},
        ),
        (
            {"action": "media_stop", "entity_id": "media_player.wz"},
            "media_player/media_stop",
            {"entity_id": "media_player.wz"},
        ),
        (
            {"action": "media_volume", "entity_id": "media_player.wz", "volume": 35},
            "media_player/volume_set",
            {"entity_id": "media_player.wz", "volume_level": 0.35},
        ),
    ],
)
def test_media_actions_send_the_documented_service_bodies(
    ha: FakeHomeAssistant, fields: dict[str, Any], path: str, body: dict[str, Any]
) -> None:
    adapter().execute(config(ha), SECRETS, adapter().validate_action(fields), timeout=TIMEOUT)
    (seen,) = ha.requests
    assert (seen["method"], seen["path"], seen["body"]) == ("POST", f"/api/services/{path}", body)


@pytest.mark.parametrize(
    "fields",
    [
        {"action": "media_play", "entity_id": "light.desk", "media_url": f"https://{PUBLIC}/x"},
        {"action": "media_play", "entity_id": "media_player.a", "media_url": "http://127.0.0.1/x"},
        {"action": "media_play", "entity_id": "media_player.a", "media_url": "file:///c:/x.mp3"},
        {
            "action": "media_play",
            "entity_id": "media_player.a",
            "media_url": "http://169.254.169.254/",
        },
        {
            "action": "media_play",
            "entity_id": "media_player.a",
            "media_url": "https://u:p@example.org/x",
        },
        {"action": "media_volume", "entity_id": "media_player.a", "volume": 101},
        {"action": "media_volume", "entity_id": "media_player.a"},
        {"action": "media_pause", "entity_id": "switch.x"},
    ],
)
def test_media_actions_are_validated(fields: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        adapter().validate_action(fields)


def test_provider_identifiers_are_allowed_for_home_assistant() -> None:
    cleaned = adapter().validate_action(
        {"action": "media_play", "entity_id": "media_player.a", "media_url": "spotify:playlist:abc"}
    )
    assert cleaned["media_url"] == "spotify:playlist:abc"
    with pytest.raises(ValidationError):
        adapter().validate_action(
            {"action": "media_play", "entity_id": "media_player.a", "media_url": "spotify:a b"}
        )


def test_the_media_actions_have_help_and_the_player_list_is_discoverable() -> None:
    spec = adapter().spec
    media = [a for a in spec.actions if a.id.startswith("media_")]
    assert [a.id for a in media] == ["media_play", "media_pause", "media_stop", "media_volume"]
    assert all(f.help for a in media for f in a.fields)
    assert any(f.choices_from == ("media_player",) for a in media for f in a.fields)


# ------------------------------------------------------------- stream opening


class FakeResponse:
    def __init__(
        self,
        status: int = 200,
        content_type: str = "audio/mpeg",
        body: bytes = b"x" * 100,
        location: str | None = None,
    ) -> None:
        self.status_code = status
        self.headers = {
            "Content-Type": content_type,
            **({"Location": location} if location else {}),
        }
        self.raw = io.BytesIO(body)
        self.is_redirect = location is not None
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeSession:
    def __init__(self, *answers: FakeResponse) -> None:
        self.answers = list(answers)
        self.urls: list[str] = []
        self.trust_env = True

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.urls.append(url)
        assert kwargs["allow_redirects"] is False and kwargs["stream"] is True
        assert kwargs["timeout"][0] <= 5.0  # a bounded connection time
        return self.answers.pop(0)


def test_a_stream_is_opened_only_with_an_audio_content_type() -> None:
    session = FakeSession(FakeResponse(content_type="audio/mpeg; charset=x"))
    stream = open_stream(f"http://{PUBLIC}/r", session=session)  # type: ignore[arg-type]
    assert stream.read(10) == b"x" * 10 and session.trust_env is False  # no proxy
    page = FakeSession(FakeResponse(content_type="text/html"))
    with pytest.raises(IntegrationError) as info:
        open_stream(f"http://{PUBLIC}/r", session=page)  # type: ignore[arg-type]
    assert "keine Audiodatei" in info.value.user_message


def test_http_errors_and_unreachable_servers_are_explained() -> None:
    with pytest.raises(IntegrationError) as info:
        open_stream(f"http://{PUBLIC}/r", session=FakeSession(FakeResponse(status=404)))  # type: ignore[arg-type]
    assert "404" in info.value.user_message

    class Broken:
        trust_env = True

        def get(self, *a: Any, **k: Any) -> Any:
            import requests

            raise requests.ConnectionError("down")

    with pytest.raises(IntegrationError):
        open_stream(f"http://{PUBLIC}/r", session=Broken())  # type: ignore[arg-type]


def test_a_redirect_to_a_forbidden_address_is_refused_and_a_safe_one_followed() -> None:
    evil = FakeSession(FakeResponse(status=302, location="http://127.0.0.1/admin"))
    with pytest.raises(ValidationError):
        open_stream(f"http://{PUBLIC}/r", session=evil)  # type: ignore[arg-type]
    assert evil.urls == [f"http://{PUBLIC}/r"]  # the forbidden target was never contacted
    good = FakeSession(
        FakeResponse(status=301, location=f"http://{PUBLIC}/real"), FakeResponse(body=b"audio")
    )
    stream = open_stream(f"http://{PUBLIC}/r", session=good)  # type: ignore[arg-type]
    assert good.urls[-1] == f"http://{PUBLIC}/real" and stream.read(5) == b"audio"


def test_a_redirect_loop_is_cut_off() -> None:
    loop = FakeSession(
        *[FakeResponse(status=302, location=f"http://{PUBLIC}/r") for _ in range(10)]
    )
    with pytest.raises(ValidationError):
        open_stream(f"http://{PUBLIC}/r", session=loop)  # type: ignore[arg-type]
    assert len(loop.urls) == MAX_REDIRECTS + 1


def test_the_amount_read_from_a_stream_is_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("octaledger.infrastructure.audio.worker.MAX_STREAM_BYTES", 150)
    stream = open_stream(
        f"http://{PUBLIC}/r",
        session=FakeSession(FakeResponse(body=b"y" * 1000)),  # type: ignore[arg-type]
    )
    assert len(stream.read(1000)) == 150 and stream.read(10) == b""


# ----------------------------------------------------------------------- files


def make_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "Musik"
    (folder / "Album").mkdir(parents=True)
    (folder / "Album" / "lied.mp3").write_bytes(b"ID3")
    (folder / "notizen.txt").write_text("nur Text", encoding="utf-8")
    (tmp_path / "geheim.mp3").write_bytes(b"ID3")
    return folder


def test_a_file_inside_an_allowed_folder_is_accepted(tmp_path: Path) -> None:
    folder = make_folder(tmp_path)
    assert resolve_file([folder], "0:Album/lied.mp3").name == "lied.mp3"


@pytest.mark.parametrize(
    "choice",
    [
        "",
        "0",
        "0:",
        "x:Album/lied.mp3",
        "1:Album/lied.mp3",
        "0:../geheim.mp3",
        "0:notizen.txt",
        "0:fehlt.mp3",
    ],
)
def test_everything_else_is_refused(tmp_path: Path, choice: str) -> None:
    with pytest.raises(ValidationError):
        resolve_file([make_folder(tmp_path)], choice)


def test_a_link_pointing_out_of_the_folder_is_refused(tmp_path: Path) -> None:
    folder = make_folder(tmp_path)
    link = folder / "abkürzung.mp3"
    try:
        os.symlink(tmp_path / "geheim.mp3", link)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are not available here")
    with pytest.raises(ValidationError):
        resolve_file([folder], "0:abkürzung.mp3")


# ---------------------------------------------------------------------- worker


class FakeEngine:
    def __init__(self) -> None:
        self.events: list[tuple[str, Any]] = []
        self.fail_next: BaseException | None = None

    def play(self, source: BinaryIO, volume: float) -> None:
        if self.fail_next is not None:
            error, self.fail_next = self.fail_next, None
            raise error
        self.events.append(("play", (source.read(3), round(volume, 2))))

    def stop(self) -> None:
        self.events.append(("stop", None))

    def set_volume(self, volume: float) -> None:
        self.events.append(("volume", round(volume, 2)))


def wait_for(predicate: Any, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "condition not reached in time"
        time.sleep(0.01)


def worker_with(engine: FakeEngine) -> AudioWorker:
    return AudioWorker(lambda: engine, opener=lambda url, **kw: io.BytesIO(b"abcdef"))


def test_commands_run_in_order_in_a_separate_thread() -> None:
    engine = FakeEngine()
    worker = worker_with(engine)
    caller = threading.get_ident()
    seen: list[int] = []
    original = engine.play

    def spy(source: BinaryIO, volume: float) -> None:
        seen.append(threading.get_ident())
        original(source, volume)

    engine.play = spy  # type: ignore[method-assign]
    worker.submit(Command("play_url", "http://x", 0.5))
    worker.submit(Command("volume", 0.2))
    worker.submit(Command("stop"))
    wait_for(lambda: len(engine.events) == 3)
    assert engine.events == [("play", (b"abc", 0.5)), ("volume", 0.2), ("stop", None)]
    assert seen and seen[0] != caller  # never on the caller's thread
    worker.stop_thread()


def test_submit_never_blocks_even_when_the_engine_is_slow() -> None:
    gate = threading.Event()

    class Slow(FakeEngine):
        def play(self, source: BinaryIO, volume: float) -> None:
            gate.wait(5)

    worker = AudioWorker(lambda: Slow(), opener=lambda url, **kw: io.BytesIO(b"x"))
    started = time.monotonic()
    worker.submit(Command("play_url", "http://x", 0.5))
    worker.submit(Command("stop"))
    assert time.monotonic() - started < 1
    gate.set()
    worker.stop_thread()


def test_a_full_queue_is_reported_instead_of_blocking() -> None:
    gate = threading.Event()

    class Slow(FakeEngine):
        def play(self, source: BinaryIO, volume: float) -> None:
            gate.wait(5)

    worker = AudioWorker(lambda: Slow(), opener=lambda url, **kw: io.BytesIO(b"x"))
    with pytest.raises(IntegrationError):
        for _ in range(50):
            worker.submit(Command("play_url", "http://x", 0.5))
    gate.set()
    worker.stop_thread()


def test_an_engine_error_is_remembered_and_the_worker_keeps_going() -> None:
    engine = FakeEngine()
    engine.fail_next = IntegrationError("nope", user_message="Format wird nicht unterstützt")
    worker = worker_with(engine)
    worker.submit(Command("play_url", "http://x", 0.5))
    wait_for(lambda: worker.last_error is not None)
    assert "Format" in str(worker.last_error)
    worker.submit(Command("play_url", "http://x", 0.5))
    wait_for(lambda: ("play", (b"abc", 0.5)) in engine.events)
    wait_for(lambda: worker.last_error is None)
    worker.stop_thread()


def test_an_unexpected_exception_does_not_kill_the_thread() -> None:
    engine = FakeEngine()
    engine.fail_next = RuntimeError("bug")
    worker = worker_with(engine)
    worker.submit(Command("play_url", "http://x", 0.5))
    wait_for(lambda: worker.last_error is not None)
    worker.submit(Command("stop"))
    wait_for(lambda: ("stop", None) in engine.events)
    worker.stop_thread()


def test_without_an_audio_package_the_engine_explains_itself() -> None:
    with pytest.raises(IntegrationError) as info:
        UnavailableEngine().play(io.BytesIO(b""), 0.5)
    assert "audio" in info.value.user_message
    UnavailableEngine().stop()
    UnavailableEngine().set_volume(0.1)


# --------------------------------------------------------------------- adapter


def player(engine: FakeEngine) -> PlayerAdapter:
    return PlayerAdapter(worker_with(engine))


def test_the_player_is_registered_with_help_everywhere() -> None:
    spec = default_adapters()["player"].spec
    fields = [f for a in spec.actions for f in a.fields] + list(spec.config_fields)
    assert spec.title.startswith("Lokaler Player") and all(f.help for f in fields)
    assert [a.id for a in spec.actions] == [
        "play_url",
        "play_file",
        "play_path",
        "stop",
        "pause",
        "resume",
        "next",
        "previous",
        "volume",
    ]
    assert "AAC" in spec.setup_guide and "Spielen Sie nur Inhalte ab" in spec.setup_guide


def test_playing_a_stream_returns_at_once_and_uses_the_default_volume() -> None:
    engine = FakeEngine()
    adapter_ = player(engine)
    cfg = adapter_.validate_config({"volume": 30})
    message = adapter_.execute(
        cfg,
        {},
        adapter_.validate_action({"action": "play_url", "url": f"https://{PUBLIC}/r"}),
        timeout=1,
    )
    assert "Stream" in message
    wait_for(lambda: engine.events)
    assert engine.events[0] == ("play", (b"abc", 0.3))
    adapter_.execute(
        cfg,
        {},
        adapter_.validate_action(
            {"action": "play_url", "url": f"https://{PUBLIC}/r", "volume": 80}
        ),
        timeout=1,
    )
    wait_for(lambda: len(engine.events) == 2)
    assert engine.events[1] == ("play", (b"abc", 0.8))
    adapter_.worker.stop_thread()


def test_the_lan_switch_is_enforced_when_the_action_runs() -> None:
    adapter_ = player(FakeEngine())
    lan = adapter_.validate_action({"action": "play_url", "url": "http://192.168.1.9:8000/radio"})
    with pytest.raises(ValidationError):
        adapter_.execute(adapter_.validate_config({}), {}, lan, timeout=1)  # LAN not allowed
    adapter_.execute(adapter_.validate_config({"allow_lan": True}), {}, lan, timeout=1)
    adapter_.worker.stop_thread()


def test_dangerous_addresses_never_pass_validation_at_all() -> None:
    for url in ("http://127.0.0.1/x", "http://169.254.169.254/x", "file:///c:/x.mp3"):
        with pytest.raises(ValidationError):
            player(FakeEngine()).validate_action({"action": "play_url", "url": url})


def test_folders_are_validated_and_files_come_only_from_them(tmp_path: Path) -> None:
    folder = make_folder(tmp_path)
    engine = FakeEngine()
    adapter_ = player(engine)
    cfg = adapter_.validate_config({"allowed_folders": str(folder)})
    listed = adapter_.discover(cfg, {}, timeout=1)["files"]
    assert [f["id"] for f in listed] == ["0:Album/lied.mp3"]  # no .txt, nothing from outside
    adapter_.execute(
        cfg,
        {},
        adapter_.validate_action({"action": "play_file", "file": "0:Album/lied.mp3"}),
        timeout=1,
    )
    wait_for(lambda: engine.events)
    assert engine.events[0][0] == "play"
    with pytest.raises(ValidationError):
        adapter_.execute(
            cfg,
            {},
            adapter_.validate_action({"action": "play_file", "file": "0:../geheim.mp3"}),
            timeout=1,
        )
    for bad in ("relative/path", str(tmp_path / "gibt-es-nicht")):
        with pytest.raises(ValidationError):
            adapter_.validate_config({"allowed_folders": bad})
    with pytest.raises(ValidationError):
        adapter_.validate_config({"allowed_folders": ";".join([str(folder)] * 11)})
    assert adapter_.discover(adapter_.validate_config({}), {}, timeout=1) == {}  # nothing allowed
    adapter_.worker.stop_thread()


def test_stop_and_volume_reach_the_engine() -> None:
    engine = FakeEngine()
    adapter_ = player(engine)
    cfg = adapter_.validate_config({})
    adapter_.execute(cfg, {}, adapter_.validate_action({"action": "stop"}), timeout=1)
    adapter_.execute(
        cfg, {}, adapter_.validate_action({"action": "volume", "level": 25}), timeout=1
    )
    wait_for(lambda: len(engine.events) == 2)
    assert engine.events == [("stop", None), ("volume", 0.25)]
    with pytest.raises(ValidationError):
        adapter_.validate_action({"action": "volume", "level": 101})
    adapter_.worker.stop_thread()


def test_check_reports_readiness() -> None:
    assert "bereit" in player(FakeEngine()).check({}, {}, timeout=1)


@pytest.mark.skipif(not audio_available(), reason="optional audio package not installed")
def test_the_real_engine_can_be_created_without_sound_hardware() -> None:
    from octaledger.infrastructure.audio.engine import MiniaudioEngine

    engine = MiniaudioEngine()
    engine.set_volume(0.3)
    engine.stop()  # nothing plays: harmless
