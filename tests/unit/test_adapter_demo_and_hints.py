"""The demo adapter and the explanatory Hue connection errors (no network needed)."""

import socket
import ssl

import pytest

from octaledger.core.errors import IntegrationConnectionError, IntegrationError
from octaledger.infrastructure.integrations.demo import DemoAdapter
from octaledger.infrastructure.integrations.hue import HueAdapter, explain_connect_error
from octaledger.infrastructure.integrations.registry import default_adapters

CALL = {"text": "Licht an"}


def test_the_demo_adapter_is_registered_and_self_describing() -> None:
    spec = default_adapters()["demo"].spec
    assert spec.title.startswith("Testverbindung") and spec.setup_guide
    assert [a.id for a in spec.actions] == ["say"]
    assert all(f.help for f in spec.config_fields)


def test_demo_acknowledges_without_sending_anything() -> None:
    adapter = DemoAdapter()
    assert "Licht an" in adapter.execute({}, {}, CALL, timeout=1)
    assert "bereit" in adapter.check({}, {}, timeout=1)


def test_demo_can_simulate_an_unreachable_target_that_is_retried() -> None:
    with pytest.raises(IntegrationConnectionError):
        DemoAdapter().execute({"mode": "unreachable"}, {}, CALL, timeout=1)


def test_demo_can_simulate_a_plain_error_that_is_not_retried() -> None:
    with pytest.raises(IntegrationError) as info:
        DemoAdapter().execute({"mode": "error"}, {}, CALL, timeout=1)
    assert not isinstance(info.value, IntegrationConnectionError)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (TimeoutError(), "Zeitüberschreitung"),
        (ConnectionRefusedError(), "nimmt kein Gerät"),
        (socket.gaierror(), "IP-Adresse"),
        (ssl.SSLError(), "TLS"),
        (OSError("x"), "nicht erreichbar"),
    ],
)
def test_hue_connection_errors_explain_what_to_check(error: OSError, expected: str) -> None:
    text = explain_connect_error("192.168.1.9", error)
    assert expected in text and "192.168.1.9" in text


def test_a_timeout_names_the_browser_probe() -> None:
    assert "/api/config" in explain_connect_error("10.0.0.2", TimeoutError())


def test_pairing_reports_the_explained_error() -> None:
    def refuse(host: str, port: int, timeout: float) -> str:
        raise TimeoutError

    adapter = HueAdapter(fetch_certificate=refuse)
    with pytest.raises(IntegrationConnectionError) as info:
        adapter.pair({"host": "10.0.0.2"}, timeout=1)
    assert "Zeitüberschreitung" in info.value.user_message


def test_guides_help_with_failed_connections() -> None:
    hue = default_adapters()["hue"].spec.setup_guide
    ha = default_adapters()["homeassistant"].spec.setup_guide
    assert "Wenn das Koppeln fehlschlägt" in hue and "/api/config" in hue
    assert "Wo finde ich die Adresse" in ha and "8123" in ha
