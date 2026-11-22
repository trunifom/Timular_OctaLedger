"""Tray model, notifications and autostart (AP-39) with stand-ins; no registry, no desktop."""

import sys
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any

import pytest

from octaledger.agent.supervisor import DeviceStatus
from octaledger.agent.tray import (
    NOT_RECORDING,
    PystrayTray,
    TrayModel,
    format_elapsed,
    tray_available,
)
from octaledger.application.attention_service import AttentionService
from octaledger.application.notifier import NotificationRelay, describe, in_quiet_hours
from octaledger.application.tracking_service import TrackingService
from octaledger.cli import main
from octaledger.core.errors import ConfigurationError, InvalidStateError
from octaledger.core.settings import NotificationSettings, TraySettings
from octaledger.domain.attention import AttentionItem, AttentionKind
from octaledger.domain.models import Activity, Device
from octaledger.domain.state_machine import ConnectionState
from octaledger.infrastructure.storage.database import Database
from octaledger.infrastructure.storage.repositories import Storage
from octaledger.infrastructure.system.autostart import (
    VALUE_NAME,
    Autostart,
    build_command,
)
from octaledger.infrastructure.system.toast import toast_available
from tests.unit.test_attention import Env as ApiEnv
from tests.unit.test_attention import env as api_env  # noqa: F401

T0 = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)


# ---------------------------------------------------------------------- autostart


class FakeRunKey:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def read(self, name: str) -> str | None:
        return self.values.get(name)

    def write(self, name: str, value: str) -> None:
        self.values[name] = value

    def delete(self, name: str) -> None:
        self.values.pop(name, None)


def test_the_command_quotes_the_interpreter_and_starts_the_agent(tmp_path: Path) -> None:
    folder = tmp_path / "with space"
    folder.mkdir()
    exe = folder / "python.exe"
    exe.write_text("", encoding="utf-8")
    assert build_command(exe, windowless=False) == f'"{exe}" -m octaledger agent'
    (folder / "pythonw.exe").write_text("", encoding="utf-8")
    assert build_command(exe) == f'"{folder / "pythonw.exe"}" -m octaledger agent'


def test_autostart_reads_the_real_state_and_switches() -> None:
    registry = FakeRunKey()
    switch = Autostart(registry, available=True)
    assert not switch.status().enabled
    status = switch.enable()
    assert status.enabled and status.current and registry.values[VALUE_NAME] == build_command()
    assert not switch.disable().enabled and VALUE_NAME not in registry.values
    switch.disable()  # twice is fine


def test_a_stale_command_is_reported_and_enable_renews_it() -> None:
    registry = FakeRunKey()
    registry.values[VALUE_NAME] = '"C:\\old\\python.exe" -m octaledger agent'
    switch = Autostart(registry, available=True)
    assert switch.status().enabled and not switch.status().current
    assert switch.enable().current


def test_autostart_is_unavailable_outside_windows() -> None:
    switch = Autostart(available=False)
    assert switch.status().available is False
    with pytest.raises(InvalidStateError):
        switch.enable()
    with pytest.raises(InvalidStateError):
        switch.disable()


@pytest.mark.skipif(sys.platform != "win32", reason="needs the Windows registry")
def test_the_real_registry_can_be_read() -> None:
    assert Autostart().status().available is True  # reading never writes anything


def test_cli_autostart_status_on_and_off(monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    registry = FakeRunKey()

    def fake(*_a: Any, **_k: Any) -> Autostart:
        return Autostart(registry, available=True)

    monkeypatch.setattr("octaledger.infrastructure.system.autostart.Autostart", fake)
    assert main(["autostart", "status"]) == 0 and "Autostart: aus" in capsys.readouterr().out
    assert main(["autostart", "on"]) == 0 and "Autostart: an" in capsys.readouterr().out
    assert VALUE_NAME in registry.values
    assert main(["autostart", "off"]) == 0 and "aus" in capsys.readouterr().out


def test_cli_autostart_outside_windows(monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    monkeypatch.setattr(
        "octaledger.infrastructure.system.autostart.Autostart", lambda: Autostart(available=False)
    )
    assert main(["autostart", "status"]) == 1
    assert "nur unter Windows" in capsys.readouterr().out


# --------------------------------------------------------------------- settings


def test_notification_and_tray_settings_defaults_and_validation() -> None:
    notify = NotificationSettings()
    assert (notify.toast, notify.quiet_start, notify.quiet_end) == (False, "22:00", "07:00")
    assert TraySettings().enabled is True
    for bad in ({"toast": "ja"}, {"quiet_start": "25:00"}, {"quiet_end": "abc"}):
        with pytest.raises(ConfigurationError):
            NotificationSettings(**bad)  # type: ignore[arg-type]
    with pytest.raises(ConfigurationError):
        TraySettings(enabled="ja")  # type: ignore[arg-type]
    assert NotificationSettings(quiet_start="", quiet_end="").quiet_start == ""


# ------------------------------------------------------------------ quiet hours


@pytest.mark.parametrize(
    ("local", "inside"),
    [
        (time(21, 59), False),
        (time(22, 0), True),
        (time(3, 0), True),
        (time(6, 59), True),
        (time(7, 0), False),
        (time(12, 0), False),
    ],
)
def test_quiet_hours_span_midnight(local: time, inside: bool) -> None:
    assert in_quiet_hours(local, "22:00", "07:00") is inside


def test_quiet_hours_within_one_day_and_off() -> None:
    assert in_quiet_hours(time(13, 0), "12:00", "14:00")
    assert not in_quiet_hours(time(15, 0), "12:00", "14:00")
    assert not in_quiet_hours(time(3, 0), "", "")
    assert not in_quiet_hours(time(3, 0), "08:00", "08:00")


# ------------------------------------------------------------------ the relay


class Recorder:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def notify(self, title: str, message: str) -> None:
        self.messages.append((title, message))


class Exploding:
    def notify(self, title: str, message: str) -> None:
        raise RuntimeError("no display")


class Rig:
    def __init__(self, tmp_path: Path) -> None:
        database = Database(tmp_path / "t.sqlite3", backup_dir=tmp_path / "bk")
        database.initialize()
        self.storage = Storage(database)
        self.config = NotificationSettings(toast=True, quiet_start="22:00", quiet_end="07:00")
        self.now = T0
        self.recorder = Recorder()
        self.relay = NotificationRelay(
            self.storage,
            [self.recorder],
            lambda: self.config,
            lambda: "UTC",
            clock=lambda: self.now,
        )

    def raise_item(self, kind: AttentionKind = AttentionKind.REMINDER, **payload: Any) -> str:
        with self.storage.transaction() as repos:
            return repos.attention.add(
                AttentionItem(kind=kind, created_at=T0, payload=payload or {"reason": "battery"})
            ).id


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    return Rig(tmp_path)


def test_items_that_existed_at_start_are_not_announced(rig: Rig) -> None:
    rig.raise_item()
    assert rig.relay.check() == 0 and rig.recorder.messages == []
    rig.raise_item(reason="no_timer")
    assert rig.relay.check() == 1 and rig.recorder.messages[0][0] == "Zeit starten?"


def test_each_item_is_announced_once(rig: Rig) -> None:
    rig.relay.check()
    rig.raise_item()
    assert rig.relay.check() == 1 and rig.relay.check() == 0


def test_switched_off_and_quiet_hours_send_nothing(rig: Rig) -> None:
    rig.relay.check()
    rig.config = NotificationSettings(toast=False)
    rig.raise_item()
    assert rig.relay.check() == 0
    rig.config = NotificationSettings(toast=True)
    rig.now = T0.replace(hour=23)
    rig.raise_item(reason="running_long")
    assert rig.relay.check() == 0 and rig.recorder.messages == []


def test_a_failing_notifier_never_raises(rig: Rig) -> None:
    rig.relay = NotificationRelay(
        rig.storage,
        [Exploding(), rig.recorder],
        lambda: rig.config,
        lambda: "UTC",
        clock=lambda: rig.now,
    )
    rig.relay.check()
    rig.raise_item()
    assert rig.relay.check() == 1  # the second notifier still delivers
    assert len(rig.recorder.messages) == 1


def test_texts_are_german_and_contain_no_payload_details() -> None:
    for kind, payload in (
        (AttentionKind.GAP, {"device_id": "geheim", "lost_at": "x"}),
        (AttentionKind.IDLE, {"idle_since": "x"}),
        (AttentionKind.AUTO_STOP, {"ended_at": "x"}),
        (AttentionKind.REMINDER, {"reason": "battery", "alias": "MeinWürfel", "percent": 3}),
        (AttentionKind.REMINDER, {"reason": "unknown"}),
    ):
        title, message = describe(AttentionItem(kind=kind, created_at=T0, payload=payload))
        assert title and message and "geheim" not in message and "MeinWürfel" not in message


def test_extras_are_detected_without_importing_them() -> None:
    assert isinstance(toast_available(), bool) and isinstance(tray_available(), bool)


# ------------------------------------------------------------------- tray model


def status(device_id: str, state: ConnectionState) -> DeviceStatus:
    return DeviceStatus(
        device_id=device_id,
        state=state,
        connection_id=None,
        attempt=0,
        last_error=None,
        last_value=None,
        last_event_at=None,
        battery_percent=None,
        dropped_values=0,
        duplicates_ignored=0,
    )


class TrayRig:
    def __init__(self, tmp_path: Path) -> None:
        database = Database(tmp_path / "t.sqlite3", backup_dir=tmp_path / "bk")
        database.initialize()
        self.storage = Storage(database)
        self.now = T0
        self.tracking = TrackingService(self.storage, clock=lambda: self.now)
        self.attention = AttentionService(self.storage)
        with self.storage.transaction() as repos:
            self.device = repos.devices.add(Device(alias="Büro")).id
            self.activity = repos.activities.add(Activity(name="Entwicklung")).id
        self.tracking.set_active_device(self.device)
        self.states: list[DeviceStatus] = [status(self.device, ConnectionState.READY)]
        self.opened: list[str] = []
        self.quit_calls = 0
        self.model = TrayModel(
            self.tracking,
            self.attention,
            lambda: self.states,
            self._quit,
            open_url=self.opened.append,
        )

    def _quit(self) -> None:
        self.quit_calls += 1


@pytest.fixture
def tray(tmp_path: Path) -> TrayRig:
    return TrayRig(tmp_path)


def test_grey_when_nothing_runs(tray: TrayRig) -> None:
    view = tray.model.view()
    assert view.color == "grey" and view.tooltip == "Keine Zeiterfassung"


def test_green_with_activity_and_elapsed_time(tray: TrayRig) -> None:
    tray.tracking.start_manual(tray.activity)
    tray.now = T0 + timedelta(hours=1, minutes=23, seconds=45)
    view = tray.model.view()
    assert view.color == "green" and view.tooltip == "Entwicklung 1:23:45"


def test_red_when_the_active_cube_is_not_connected(tray: TrayRig) -> None:
    tray.states = [status(tray.device, ConnectionState.RECONNECT_WAIT)]
    assert tray.model.view().color == "red" and "Würfel getrennt" in tray.model.view().tooltip
    tray.states = []  # not even started
    assert tray.model.view().color == "red"
    assert ConnectionState.READY not in NOT_RECORDING


def test_yellow_wins_when_a_question_waits(tray: TrayRig) -> None:
    tray.tracking.start_manual(tray.activity)
    tray.states = [status(tray.device, ConnectionState.DISCONNECTED)]
    with tray.storage.transaction() as repos:
        repos.attention.add(
            AttentionItem(kind=AttentionKind.REMINDER, created_at=T0, payload={"reason": "battery"})
        )
    view = tray.model.view()
    assert view.color == "yellow" and "1 Rückfrage(n) offen" in view.tooltip


def test_menu_actions_call_the_services(tray: TrayRig) -> None:
    labels = [label for label, _ in tray.model.menu()]
    assert labels == [
        "Zeit stoppen",
        "Pause / Fortsetzen",
        "Dashboard öffnen",
        "Rückfragen anzeigen",
        "OctaLedger beenden",
    ]
    tray.tracking.start_manual(tray.activity)
    tray.model.pause_resume()
    assert tray.tracking.status().running is None and tray.tracking.status().paused
    tray.model.pause_resume()
    assert tray.tracking.status().running is not None
    tray.model.stop()
    assert tray.tracking.status().running is None
    tray.model.stop()  # nothing running: no error
    tray.model.open_dashboard()
    assert tray.opened == ["http://127.0.0.1:8501"]
    tray.model.quit()
    assert tray.quit_calls == 1


def test_elapsed_formatting() -> None:
    assert format_elapsed(5025) == "1:23:45" and format_elapsed(-5) == "0:00:00"


def test_the_pystray_wrapper_is_inert_without_the_package(
    monkeypatch: pytest.MonkeyPatch, tray: TrayRig
) -> None:
    monkeypatch.setattr("octaledger.agent.tray.tray_available", lambda: False)
    wrapper = PystrayTray(tray.model)
    assert wrapper.start() is False
    wrapper.refresh()
    wrapper.stop()  # all harmless


# -------------------------------------------------------------------------- API


def test_capabilities_and_autostart_endpoints(api_env: ApiEnv) -> None:  # noqa: F811
    caps = api_env.get("/system/capabilities").json()
    assert set(caps) >= {"tray", "toast"}
    registry = FakeRunKey()
    api_env.context.autostart = Autostart(registry, available=True)
    assert api_env.get("/system/autostart").json()["enabled"] is False
    on = api_env.call("PUT", "/system/autostart", json={"enabled": True}).json()
    assert on["enabled"] and on["current"] and VALUE_NAME in registry.values
    off = api_env.call("PUT", "/system/autostart", json={"enabled": False}).json()
    assert off["enabled"] is False
    assert api_env.call("PUT", "/system/autostart", json={"enabled": "x"}).status_code == 422
    api_env.context.autostart = Autostart(available=False)
    assert api_env.get("/system/autostart").json()["available"] is False
    assert api_env.call("PUT", "/system/autostart", json={"enabled": True}).status_code == 409
