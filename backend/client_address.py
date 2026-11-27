"""Works out which client sent a request, for per-client limits.

Behind Cloudflare and Render, the TCP peer is a proxy, so the client's address
has to come from a header one of our own proxies sets. Which header is a
setting (config.CLIENT_IP_SOURCE), checked live after each infrastructure
change. A header the client could have written is never trusted: the leftmost
X-Forwarded-For entry is whatever the client sent, so only the rightmost one
(added by the last proxy) is ever used, and only once the live check shows it
is the client rather than a proxy.

If the configured header is missing, the client is unknown (None) rather than
the proxy's address: falling back to the proxy would put every user in one
shared per-client limit. Callers then skip per-client limits; the per-account
limits and the all-users backstops still apply.
"""

import hashlib
import ipaddress
import logging

from fastapi import Request

import config

logger = logging.getLogger("voiceguard.client")

_warned_missing = False


def _valid_ip(value: str) -> str:
    """The address in a canonical form, or "" if it isn't one. IPv6 is cut to
    its /64 network: one home or server usually gets a whole /64, so each
    address in it isn't a separate client."""
    try:
        address = ipaddress.ip_address(value.strip())
    except ValueError:
        return ""
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped:
            return str(address.ipv4_mapped)
        return f"{ipaddress.ip_network(f'{address}/64', strict=False).network_address}/64"
    return str(address)


def client_address(request: Request) -> str | None:
    """The client's IP address (an IPv6 /64), or None if it can't be told."""
    global _warned_missing
    source = config.CLIENT_IP_SOURCE
    address = ""
    if source == "cf-connecting-ip":
        address = _valid_ip(request.headers.get("cf-connecting-ip", ""))
    elif source == "x-forwarded-for-last":
        entries = [entry for entry in request.headers.get("x-forwarded-for", "").split(",") if entry.strip()]
        address = _valid_ip(entries[-1]) if entries else ""
    elif request.client:  # "peer"
        address = _valid_ip(request.client.host) or request.client.host

    if not address:
        if not _warned_missing:
            # Once per process: means CLIENT_IP_SOURCE doesn't match what the
            # proxies send, so per-client limits are off until it's fixed.
            logger.warning("client_address_missing source=%s per-client limits skipped", source)
            _warned_missing = True
        return None
    return address


def client_key(request: Request) -> str | None:
    """A hash of the client's address, so limits never store addresses in
    clear; None if the client can't be told."""
    address = client_address(request)
    return hashlib.sha256(address.encode("utf-8")).hexdigest()[:32] if address else None
