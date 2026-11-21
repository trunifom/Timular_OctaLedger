# ruff: noqa: F401, F811  (the `bridge` fixture is re-used from test_adapter_hue)
"""Hue: transitions, scene modes, request spacing, 429 handling and the bridge search (AP-43)."""

from typing import Any

import pytest

from octaledger.application.integration_service import IntegrationService
from octaledger.core.errors import IntegrationConnectionError, IntegrationError, ValidationError
from octaledger.core.secrets import SecretStore
from octaledger.infrastructure.integrations.hue import (
    CLOUD_DISCOVERY_URL,
    HueAdapter,
    _is_private_ipv4,
    find_via_cloud,
    find_via_mdns,
    zeroconf_available,
)
from octaledger.infrastructure.integrations.registry import default_adapters
from tests.unit.test_adapter_hue import (
    GROUP,
    LAMP,
    SCENE,
    SECRETS,
    TIMEOUT,
    FakeBridge,
    action,
    adapter,
    bridge,
    config,
)

# ----------------------------------------------------------------- bodies per option


def test_a_transition_is_sent_as_dynamics_duration(bridge: FakeBridge) -> None:
    adapter().execute(
        config(bridge),
        SECRETS,
        action("light", light_id=LAMP, brightness=60, transition_ms=2500),
        timeout=TIMEOUT,
    )
    assert bridge.requests[0]["body"] == {
        "on": {"on": True},
        "dimming": {"brightness": 60.0},
        "dynamics": {"duration": 2500},
    }


def test_a_transition_of_zero_means_immediately_and_is_sent(bridge: FakeBridge) -> None:
    adapter().execute(
        config(bridge),
        SECRETS,
        action("room", group_id=GROUP, state="off", transition_ms=0),
        timeout=TIMEOUT,
    )
    assert bridge.requests[0]["body"] == {"on": {"on": False}, "dynamics": {"duration": 0}}


def test_without_a_transition_the_bridge_decides(bridge: FakeBridge) -> None:
    adapter().execute(config(bridge), SECRETS, action("light", light_id=LAMP), timeout=TIMEOUT)
    assert "dynamics" not in bridge.requests[0]["body"]


@pytest.mark.parametrize(
    ("fields", "recall"),
    [
        ({}, {"action": "active"}),
        ({"mode": "dynamic_palette"}, {"action": "dynamic_palette"}),
        (
            {"mode": "static", "brightness": 70},
            {"action": "static", "dimming": {"brightness": 70.0}},
        ),
        ({"transition_ms": 1000}, {"action": "active", "duration": 1000}),
    ],
)
def test_a_scene_can_be_dynamic_dimmed_and_faded(
    bridge: FakeBridge, fields: dict[str, Any], recall: dict[str, Any]
) -> None:
    adapter().execute(
        config(bridge), SECRETS, action("scene", scene_id=SCENE, **fields), timeout=TIMEOUT
    )
    assert bridge.requests[0]["body"] == {"recall": recall}


def test_new_fields_are_validated() -> None:
    for kind, bad in (
        ("light", {"light_id": LAMP, "transition_ms": 20000}),
        ("light", {"light_id": LAMP, "transition_ms": -1}),
        ("scene", {"scene_id": SCENE, "mode": "disco"}),
        ("scene", {"scene_id": SCENE, "brightness": 0}),
    ):
        with pytest.raises(ValidationError):
            action(kind, **bad)


def test_every_new_field_has_a_help_text_and_the_advanced_ones_are_marked() -> None:
    spec = adapter().spec
    fields = [f for a in spec.actions for f in a.fields] + list(spec.config_fields)
    assert all(f.help for f in fields)
    advanced = {f.name for f in fields if f.advanced}
    assert {"transition_ms", "mode", "min_interval_ms"} <= advanced


# ----------------------------------------------------------------- spacing and 429


def test_requests_to_the_same_bridge_keep_the_minimum_distance(bridge: FakeBridge) -> None:
    now = [100.0]
    slept: list[float] = []

    def fake_sleep(seconds: float) -> None:
        slept.append(seconds)
        now[0] += seconds

    paced = HueAdapter(scheme="http", sleep=fake_sleep, monotonic=lambda: now[0])
    cfg = paced.validate_config({"host": bridge.host, "min_interval_ms": 500})
    toggle = paced.validate_action({"action": "light", "light_id": LAMP, "state": "toggle"})
    paced.execute(cfg, SECRETS, toggle, timeout=TIMEOUT)  # GET then PUT: one wait between them
    assert len(slept) == 1 and slept[0] == pytest.approx(0.5)
    now[0] += 5  # long enough ago: no further wait
    paced.execute(cfg, SECRETS, action("light", light_id=LAMP, state="off"), timeout=TIMEOUT)
    assert len(slept) == 1


def test_a_zero_interval_never_waits(bridge: FakeBridge) -> None:
    slept: list[float] = []
    paced = HueAdapter(scheme="http", sleep=slept.append)
    cfg = paced.validate_config({"host": bridge.host, "min_interval_ms": 0})
    toggle = paced.validate_action({"action": "light", "light_id": LAMP, "state": "toggle"})
    paced.execute(cfg, SECRETS, toggle, timeout=TIMEOUT)
    assert slept == []


def test_the_bridge_answering_429_is_retried_later_not_given_up(bridge: FakeBridge) -> None:
    bridge.fail_with = 429
    with pytest.raises(IntegrationConnectionError) as info:
        adapter().execute(config(bridge), SECRETS, action("light", light_id=LAMP), timeout=TIMEOUT)
    assert "überlastet" in info.value.user_message


def test_a_failing_toggle_read_sends_no_command(bridge: FakeBridge) -> None:
    bridge.fail_with = 500
    with pytest.raises(IntegrationError):
        adapter().execute(
            config(bridge),
            SECRETS,
            action("light", light_id=LAMP, state="toggle"),
            timeout=TIMEOUT,
        )
    assert [r["method"] for r in bridge.requests] == ["GET"]  # never a blind PUT


# ------------------------------------------------------------------- bridge search


def finder(*items: dict[str, str]):  # type: ignore[no-untyped-def]
    return lambda _timeout: list(items)


def found(address: str, name: str = "Hue") -> dict[str, str]:
    return {"id": name, "address": address, "name": name}


def test_the_search_is_local_only_unless_the_user_asks_for_the_internet() -> None:
    online_calls: list[float] = []

    def cloud(timeout: float) -> list[dict[str, str]]:
        online_calls.append(timeout)
        return [found("192.168.1.9", "Cloud")]

    searcher = HueAdapter(mdns_finder=finder(found("192.168.1.5", "Lokal")), cloud_finder=cloud)
    assert [i["address"] for i in searcher.find_targets(timeout=1)] == ["192.168.1.5"]
    assert online_calls == []  # nothing left the local network
    both = searcher.find_targets(online=True, timeout=1)
    assert [i["address"] for i in both] == ["192.168.1.5", "192.168.1.9"] and online_calls == [1]


def test_the_same_bridge_found_twice_is_listed_once() -> None:
    searcher = HueAdapter(
        mdns_finder=finder(found("192.168.1.5", "mdns")),
        cloud_finder=finder(found("192.168.1.5", "cloud")),
    )
    (item,) = searcher.find_targets(online=True, timeout=1)
    assert item["name"] == "mdns"


def test_a_failing_way_of_searching_does_not_hide_the_other() -> None:
    def broken(_timeout: float) -> list[dict[str, str]]:
        raise OSError("no network")

    searcher = HueAdapter(mdns_finder=broken, cloud_finder=finder(found("10.0.0.7")))
    assert [i["address"] for i in searcher.find_targets(online=True, timeout=1)] == ["10.0.0.7"]
    assert HueAdapter(mdns_finder=broken).find_targets(timeout=1) == []


@pytest.mark.parametrize(
    ("text", "ok"),
    [
        ("192.168.1.5", True),
        ("10.1.2.3", True),
        ("172.16.0.9", True),
        ("8.8.8.8", False),  # public
        ("127.0.0.1", False),  # loopback
        ("169.254.1.1", True),  # link-local counts as private for a home network
        ("::1", False),
        ("fe80::1", False),
        ("not an ip", False),
    ],
)
def test_only_home_network_addresses_are_accepted_as_a_bridge(text: str, ok: bool) -> None:
    assert _is_private_ipv4(text) is ok


def test_without_the_package_the_mdns_search_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "octaledger.infrastructure.integrations.hue.zeroconf_available", lambda: False
    )
    assert find_via_mdns(1.0) == []


def test_the_cloud_lookup_filters_untrustworthy_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    class Reply:
        status_code = 200
        text = ""

        def __init__(self, payload: Any) -> None:
            self.payload = payload

        def close(self) -> None:
            pass

    seen: dict[str, Any] = {}

    def fake_send(factory: Any, method: str, url: str, **kwargs: Any) -> Reply:
        seen.update(method=method, url=url, verify=kwargs["verify"])
        return Reply(
            [
                {"id": "001788fffe123456", "internalipaddress": "192.168.1.20"},
                {"id": "evil", "internalipaddress": "8.8.8.8"},
                {"id": "bad", "internalipaddress": "javascript:alert(1)"},
                "kein Objekt",
            ]
        )

    monkeypatch.setattr("octaledger.infrastructure.integrations.hue.send", fake_send)
    monkeypatch.setattr(
        "octaledger.infrastructure.integrations.hue.read_limited",
        lambda response: json.dumps(response.payload).encode(),
    )
    items = find_via_cloud(2.0)
    assert [i["address"] for i in items] == ["192.168.1.20"]
    assert seen == {"method": "GET", "url": CLOUD_DISCOVERY_URL, "verify": True}


def test_the_cloud_lookup_survives_garbage(monkeypatch: pytest.MonkeyPatch) -> None:
    class Reply:
        status_code = 200

        def close(self) -> None:
            pass

    monkeypatch.setattr("octaledger.infrastructure.integrations.hue.send", lambda *a, **k: Reply())
    monkeypatch.setattr(
        "octaledger.infrastructure.integrations.hue.read_limited", lambda response: b"<html>"
    )
    assert find_via_cloud(1.0) == []


def test_the_service_only_searches_for_adapters_that_can(tmp_path: Any) -> None:
    from octaledger.infrastructure.storage.database import Database
    from octaledger.infrastructure.storage.repositories import Storage

    database = Database(tmp_path / "t.sqlite3", backup_dir=tmp_path / "bk")
    database.initialize()
    service = IntegrationService(
        Storage(database),
        SecretStore(tmp_path / "s.json"),
        {
            "hue": HueAdapter(mdns_finder=finder(found("192.168.1.5"))),
            **{k: v for k, v in default_adapters().items() if k == "webhook"},
        },
    )
    assert service.find_targets("hue")[0]["address"] == "192.168.1.5"
    with pytest.raises(ValidationError):
        service.find_targets("webhook")
    with pytest.raises(ValidationError):
        service.find_targets("gibt-es-nicht")


def test_the_spec_announces_the_search_and_what_it_sends() -> None:
    spec = default_adapters()["hue"].spec
    assert spec.can_find and "Anfrage an den Dienst von Philips" in spec.find_help
    assert not default_adapters()["webhook"].spec.can_find


@pytest.mark.skipif(not zeroconf_available(), reason="optional discovery package not installed")
def test_the_real_mdns_search_runs_and_never_raises() -> None:
    result = find_via_mdns(1.0)  # nothing may answer in a test network; it must just return a list
    assert isinstance(result, list)
