import logging

import pytest
from starlette.requests import Request

import client_address as module
import config
from client_address import client_address, client_key


def request(headers: dict[str, str] | None = None, peer: str | None = "10.0.0.9") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "client": (peer, 1234) if peer else None,
    }
    return Request(scope)


@pytest.fixture(autouse=True)
def fresh_warning(monkeypatch):
    monkeypatch.setattr(module, "_warned_missing", False)


def use(monkeypatch, source: str):
    monkeypatch.setattr(config, "CLIENT_IP_SOURCE", source)


def test_reads_cloudflares_header(monkeypatch):
    use(monkeypatch, "cf-connecting-ip")

    assert client_address(request({"CF-Connecting-IP": "203.0.113.7"})) == "203.0.113.7"


def test_never_trusts_the_leftmost_forwarded_entry(monkeypatch):
    # The client wrote "1.2.3.4"; the proxy appended the real address.
    use(monkeypatch, "x-forwarded-for-last")

    address = client_address(request({"X-Forwarded-For": "1.2.3.4, 203.0.113.7"}))

    assert address == "203.0.113.7"


def test_a_forwarded_header_is_ignored_unless_chosen(monkeypatch):
    use(monkeypatch, "cf-connecting-ip")

    address = client_address(request({"X-Forwarded-For": "1.2.3.4", "CF-Connecting-IP": "203.0.113.7"}))

    assert address == "203.0.113.7"


def test_peer_mode_ignores_headers(monkeypatch):
    use(monkeypatch, "peer")

    assert client_address(request({"CF-Connecting-IP": "203.0.113.7"})) == "10.0.0.9"


def test_falls_back_to_the_peer_and_warns_once(monkeypatch, caplog):
    use(monkeypatch, "cf-connecting-ip")
    caplog.set_level(logging.WARNING, logger="voiceguard.client")

    assert client_address(request()) == "10.0.0.9"
    assert client_address(request()) == "10.0.0.9"

    warnings = [r for r in caplog.records if "client_address_missing" in r.getMessage()]
    assert len(warnings) == 1


@pytest.mark.parametrize("junk", ["not-an-ip", "203.0.113.7; drop", "", "x" * 500])
def test_a_header_that_isnt_an_address_is_ignored(monkeypatch, junk):
    use(monkeypatch, "cf-connecting-ip")

    assert client_address(request({"CF-Connecting-IP": junk})) == "10.0.0.9"


def test_ipv6_is_normalised(monkeypatch):
    use(monkeypatch, "cf-connecting-ip")

    assert client_address(request({"CF-Connecting-IP": "2001:DB8::0001"})) == "2001:db8::1"


def test_no_peer_at_all(monkeypatch):
    use(monkeypatch, "peer")

    assert client_address(request(peer=None)) == "unknown"


def test_key_is_a_hash_not_the_address(monkeypatch):
    use(monkeypatch, "cf-connecting-ip")

    key = client_key(request({"CF-Connecting-IP": "203.0.113.7"}))

    assert "203.0.113.7" not in key
    assert key == client_key(request({"CF-Connecting-IP": "203.0.113.7"}))
    assert key != client_key(request({"CF-Connecting-IP": "203.0.113.8"}))


@pytest.mark.parametrize("value", ["x-forwarded-for", "true-client-ip", "", "cf"])
def test_setting_rejects_unknown_sources(value):
    with pytest.raises(RuntimeError, match="CLIENT_IP_SOURCE"):
        config.client_ip_source(value)


def test_setting_accepts_known_sources():
    assert config.client_ip_source(" CF-Connecting-IP ") == "cf-connecting-ip"
    assert config.client_ip_source("peer") == "peer"
