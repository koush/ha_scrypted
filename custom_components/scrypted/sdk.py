"""HA glue over the scrypted-sdk engine.io client.

The transport, login flow, and plugin-remote handshake live in the published
scrypted-sdk package; this module only wires HA-managed aiohttp sessions into
it. It is intentionally thin and I/O-bound; it is excluded from unit test
coverage (see pyproject.toml) and verified end-to-end with
scripts/dev_connect.py.
"""

from __future__ import annotations

import aiohttp
from scrypted_sdk import (
    EioRpcTransport,
    ScryptedConnectionError,
    ScryptedStatic,
    connect_scrypted_client,
)

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util.ssl import client_context_no_verify

from .const import DEFAULT_SCRYPTED_PORT

__all__ = ["async_connect_sdk", "get_base_url"]

PLUGIN_ID = "@scrypted/core"


def get_base_url(host: str) -> str:
    """Return https base url for a configured host ('ip' or 'ip:port')."""
    ipport = host.split(":")
    if len(ipport) > 2:
        raise ScryptedConnectionError(f"invalid Scrypted host: {host}")
    ip = ipport[0]
    port = ipport[1] if len(ipport) == 2 else DEFAULT_SCRYPTED_PORT
    return f"https://{ip}:{port}"


async def async_connect_sdk(
    hass: HomeAssistant,
    host: str,
    username: str,
    password: str,
    plugin_id: str = PLUGIN_ID,
) -> tuple[EioRpcTransport, ScryptedStatic]:
    """Login and establish the engine.io RPC session. Returns (transport, sdk).

    Login uses HA's shared session, which the SDK leaves open for its owner.
    The transport instead gets a plain session it can genuinely close: HA
    replaces close() on its own sessions with a no-op that only logs, so a
    transport built on one would leak a session per reconnect. The SSL context
    is HA's cached no-verify context, which keeps the blocking
    ssl.create_default_context call off the event loop.
    """
    transport = EioRpcTransport(
        hass.loop,
        http_session=aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=client_context_no_verify())
        ),
    )
    try:
        return await connect_scrypted_client(
            hass.loop,
            get_base_url(host),
            username,
            password,
            plugin_id=plugin_id,
            login_session=async_get_clientsession(hass, verify_ssl=False),
            transport=transport,
        )
    except ScryptedConnectionError:
        # connect_scrypted_client only closes the transport once it reaches
        # the engine.io phase; a login failure would leak our pre-built
        # transport's session and send task. close() is idempotent.
        await transport.close()
        raise
