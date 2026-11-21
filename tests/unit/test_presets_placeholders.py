"""Presets ("Vorlagen") and placeholders in message texts (AP-46)."""

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from octaledger.application.device_service import DeviceService
from octaledger.application.integration_service import IntegrationService
from octaledger.application.tracking_service import TrackingService
from octaledger.core.errors import ValidationError
from octaledger.core.secrets import SecretStore
from octaledger.domain.models import DeviceMode, EventKind, RawEvent
from octaledger.domain.placeholders import ALLOWED, check, names_in, render
from octaledger.infrastructure.integrations.base import (
    ActionSpec,
    Adapter,
    AdapterSpec,
    FieldSpec,
)
from octaledger.infrastructure.integrations.registry import default_adapters
from octaledger.infrastructure.storage.database import Database
from octaledger.infrastructure.storage.repositories import Storage

T0 = datetime(2026, 1, 5, 8, 0, 3, tzinfo=timezone.utc)
VALUES = {"device": "Büro", "face": 3, "label": "Fokus", "time": "2026-01-05T08:00:03Z"}


# ------------------------------------------------------------------ placeholders


def test_the_whitelist_is_exactly_four_names() -> None:
    assert ALLOWED == ("device", "face", "label", "time")


def test_names_are_found_and_unknown_ones_are_rejected() -> None:
    assert names_in('{"a":"{device}","f":{face},"x":{ "y": 1 }}') == ["device", "face"]
    check("{device} {face} {label} {time} {device}")
    for text in ("{secret}", "{__import__}", "{device}{evil}"):
        with pytest.raises(ValidationError) as info:
            check(text)
        assert "Erlaubt sind" in info.value.user_message


def test_json_like_text_gets_escaped_values() -> None:
    template = '{"device":"{device}","face":{face},"label":"{label}","time":"{time}"}'
    data = json.loads(render(template, VALUES))
    assert data == {"device": "Büro", "face": 3, "label": "Fokus", "time": "2026-01-05T08:00:03Z"}


@pytest.mark.parametrize(
    "label",
    ['Lampe"} {"x":1', "a\\b", 'quote " here', "zeile\nzwei", " ", '"},"admin":true,"y":"'],
)
def test_a_hostile_label_cannot_change_the_json_structure(label: str) -> None:
    out = render('{"label":"{label}","face":{face}}', {**VALUES, "label": label})
    data = json.loads(out)  # still valid JSON ...
    assert set(data) == {"label", "face"} and data["label"] == label  # ... with the same keys


def test_plain_text_is_not_escaped_and_unknown_names_stay_untouched() -> None:
    assert render("Seite {face}: {label}", VALUES) == "Seite 3: Fokus"
    assert render("ON", VALUES) == "ON"
    assert render("{other} {device}", VALUES) == "{other} Büro"
    assert render("{label}", {"label": 'a"b'}) == 'a"b'  # no JSON structure to protect
    assert render("{face}", {}) == "{face}"  # no value: left as it is


def test_there_are_no_expressions() -> None:
    assert render("{face+1} {device.upper()} {0}", VALUES) == "{face+1} {device.upper()} {0}"


# ----------------------------------------------------------------- action fields


def test_unknown_placeholders_are_rejected_when_an_action_is_saved() -> None:
    webhook = default_adapters()["webhook"]
    with pytest.raises(ValidationError):
        webhook.validate_action({"action": "request", "path": "/x", "body": '{"a":"{geheim}"}'})
    ok = webhook.validate_action(
        {"action": "request", "path": "/x", "body": '{"face":{face},"label":"{label}"}'}
    )
    assert ok["body"] == '{"face":{face},"label":"{label}"}'
    mqtt = default_adapters()["mqtt"]
    with pytest.raises(ValidationError):
        mqtt.validate_action({"action": "publish", "topic": "a/b", "payload": "{nope}"})


def test_fields_without_the_flag_are_not_checked_and_headers_never_take_placeholders() -> None:
    webhook = default_adapters()["webhook"]
    flagged = {f.name for a in webhook.spec.actions for f in a.fields if f.placeholders}
    assert flagged == {"body"}  # not the path, not any header
    assert {f.name for f in webhook.spec.config_fields if f.placeholders} == set()
    webhook.validate_action({"action": "request", "path": "/a/{geheim}"})  # a literal path


# ------------------------------------------------------------------------ presets


def adapters_with_presets() -> list[Adapter]:
    return [a for a in default_adapters().values() if a.spec.presets]


def test_webhook_and_mqtt_offer_the_documented_presets() -> None:
    found = {a.spec.kind: {p.id for p in a.spec.presets} for a in adapters_with_presets()}
    assert found["webhook"] >= {
        "node_red",
        "wled_on",
        "wled_off",
        "shelly_on",
        "openhab",
        "ha_webhook",
    }
    assert found["mqtt"] >= {"z2m_on", "z2m_off", "tasmota_on", "node_red"}


def test_every_preset_validates_unchanged_and_is_honestly_marked() -> None:
    for adapter in adapters_with_presets():
        for preset in adapter.spec.presets:
            adapter.validate_action({"action": preset.action, **preset.params})
            assert adapter.spec.action(preset.action)  # it belongs to a real action
            assert preset.label and preset.description
            assert not preset.verified  # none was tried on a real target
            if preset.id not in ("node_red", "ha_webhook"):
                assert "geprüft" in preset.description  # says so in the text as well


def test_preset_ids_are_unique_per_adapter_and_action() -> None:
    for adapter in adapters_with_presets():
        keys = [(p.action, p.id) for p in adapter.spec.presets]
        assert len(keys) == len(set(keys))


def test_presets_are_part_of_the_adapter_description_for_the_dashboard() -> None:
    from octaledger.api.schemas import adapter_out

    out = adapter_out(default_adapters()["webhook"].spec)
    node_red = next(p for p in out["presets"] if p["id"] == "node_red")
    assert node_red["action"] == "request" and node_red["params"]["path"] == "/octaledger"
    assert node_red["verified"] is False


# ------------------------------------------------------- substitution when sending


class Recorder(Adapter):
    spec = AdapterSpec(
        kind="rec",
        title="Recorder",
        description="records",
        config_fields=(FieldSpec("host", "Adresse", required=True),),
        actions=(
            ActionSpec(
                "say",
                "Sagen",
                "sagt",
                (
                    FieldSpec("text", "Text", placeholders=True),
                    FieldSpec("plain", "Nur Text"),
                ),
            ),
        ),
    )

    def __init__(self) -> None:
        self.seen: list[Mapping[str, Any]] = []

    def check(
        self, config: Mapping[str, Any], secrets: Mapping[str, str], *, timeout: float
    ) -> str:
        return "ok"

    def execute(
        self,
        config: Mapping[str, Any],
        secrets: Mapping[str, str],
        params: Mapping[str, Any],
        *,
        timeout: float,
    ) -> str:
        self.seen.append(dict(params))
        return "ok"


def test_placeholders_are_filled_from_the_turn_when_the_job_is_sent(tmp_path: Path) -> None:
    database = Database(tmp_path / "t.sqlite3", backup_dir=tmp_path / "bk")
    database.initialize()
    storage = Storage(database)
    adapter = Recorder()
    service = IntegrationService(
        storage, SecretStore(tmp_path / "s.json"), {"rec": adapter}, clock=lambda: T0
    )
    tracking = TrackingService(storage, clock=lambda: T0)
    devices = DeviceService(storage)
    devices.register("Zeit")
    control = devices.register("Büro")
    devices.set_mode(control.id, DeviceMode.CONTROL)
    connection = service.create("rec", "Rekorder", {"host": "h"}).integration.id
    service.assign_action(
        control.id,
        3,
        connection,
        'Fokus "pur"',
        {
            "action": "say",
            "text": '{"d":"{device}","f":{face},"l":"{label}","t":"{time}"}',
            "plain": "{face}",
        },
    )
    tracking.record_event(
        RawEvent(
            device_id=control.id,
            kind=EventKind.FACE_CHANGE,
            sequence=1,
            connection_id="c1",
            raw_value=3,
            received_at=T0,
        )
    )
    service.process_due()
    (sent,) = adapter.seen
    assert json.loads(sent["text"]) == {
        "d": "Büro",
        "f": 3,
        "l": 'Fokus "pur"',
        "t": "2026-01-05T08:00:03Z",
    }
    assert sent["plain"] == "{face}"  # a field without the flag is never touched
    with storage.read() as repos:  # the stored job still has the template
        (job,) = repos.jobs.list_recent(5)
        assert job.params["plain"] == "{face}" and "{device}" in job.params["text"]
