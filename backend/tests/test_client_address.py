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


def test_a_missing_header_means_unknown_not_the_proxy_and_warns_once(monkeypatch, caplog):
    # Falling back to the peer would be the proxy for everyone: one shared limit.
    use(monkeypatch, "cf-connecting-ip")
    caplog.set_level(logging.WARNING, logger="voiceguard.client")

    assert client_address(request()) is None
    assert client_key(request()) is None
    assert client_address(request()) is None

    warnings = [r for r in caplog.records if "client_address_missing" in r.getMessage()]
    assert len(warnings) == 1


@pytest.mark.parametrize("junk", ["not-an-ip", "203.0.113.7; drop", "", "x" * 500])
def test_a_header_that_isnt_an_address_is_ignored(monkeypatch, junk):
    use(monkeypatch, "cf-connecting-ip")

    assert client_address(request({"CF-Connecting-IP": junk})) is None


def test_ipv6_counts_as_its_64_network(monkeypatch):
    # One home or server usually has a whole /64; rotating within it isn't a new client.
    use(monkeypatch, "cf-connecting-ip")

    first = client_address(request({"CF-Connecting-IP": "2001:DB8:0:1::0001"}))
    second = client_address(request({"CF-Connecting-IP": "2001:db8:0:1:ffff::abcd"}))
    other = client_address(request({"CF-Connecting-IP": "2001:db8:0:2::1"}))

    assert first == second == "2001:db8:0:1::/64"
    assert other != first


def test_ipv4_mapped_ipv6_counts_as_ipv4(monkeypatch):
    use(monkeypatch, "cf-connecting-ip")

    assert client_address(request({"CF-Connecting-IP": "::ffff:203.0.113.7"})) == "203.0.113.7"


def test_no_peer_at_all(monkeypatch):
    use(monkeypatch, "peer")

    assert client_address(request(peer=None)) is None


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
