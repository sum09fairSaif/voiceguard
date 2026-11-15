"""Works out which client sent a request, for per-client limits.

Behind Cloudflare and Render, the TCP peer is a proxy, so the client's address
has to come from a header one of our own proxies sets. Which header is a
setting (config.CLIENT_IP_SOURCE), checked live after each infrastructure
change. A header the client could have written is never trusted: the leftmost
X-Forwarded-For entry is whatever the client sent, so only the rightmost one
(added by the last proxy) is ever used.
"""

import hashlib
import ipaddress
import logging

from fastapi import Request

import config

logger = logging.getLogger("voiceguard.client")

_warned_missing = False


def _valid_ip(value: str) -> str:
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return ""


def client_address(request: Request) -> str:
    """The client's IP address, or the peer's if the configured header is missing."""
    global _warned_missing
    source = config.CLIENT_IP_SOURCE
    address = ""
    if source == "cf-connecting-ip":
        address = _valid_ip(request.headers.get("cf-connecting-ip", ""))
    elif source == "x-forwarded-for-last":
        entries = [entry for entry in request.headers.get("x-forwarded-for", "").split(",") if entry.strip()]
        address = _valid_ip(entries[-1]) if entries else ""

    if not address:
        if source != "peer" and not _warned_missing:
            # Once per process: means CLIENT_IP_SOURCE doesn't match what the
            # proxies send, so every client looks like the proxy.
            logger.warning("client_address_missing source=%s falling back to the peer address", source)
            _warned_missing = True
        address = request.client.host if request.client else "unknown"
    return address


def client_key(request: Request) -> str:
    """A hash of the client's address, so limits never store addresses in clear."""
    return hashlib.sha256(client_address(request).encode("utf-8")).hexdigest()[:32]
