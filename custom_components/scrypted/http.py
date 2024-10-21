"""The Scrypted integration."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from functools import lru_cache
from ipaddress import ip_address
import os
from typing import Any
from urllib.parse import quote
import threading

import aiohttp
from aiohttp import ClientTimeout, hdrs, web
from aiohttp.web_exceptions import HTTPBadGateway, HTTPBadRequest
from homeassistant.components.http import HomeAssistantView
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from multidict import CIMultiDict
from yarl import URL

from .const import DOMAIN, CONF_SCRYPTED_NVR

_LOGGER = logging.getLogger(__name__)


async def retrieve_token(data: dict[str, Any], session: aiohttp.ClientSession) -> str:
    """Retrieve token from Scrypted server."""
    username = data[CONF_USERNAME]
    password = data.get(CONF_PASSWORD, "")
    host = data[CONF_HOST]
    ipport = host.split(":")
    if len(ipport) > 2:
        raise Exception("invalid Scrypted host")
    ip = ipport[0]
    if len(ipport) == 2:
        port = ipport[1]
    else:
        port = "10443"

    resp = await session.get(
        f"https://{ip}:{port}/login",
        headers={"authorization": aiohttp.BasicAuth(username, password).encode()},
        json={"username": username},
        raise_for_status=True,
        verify_ssl=False,
    )
    resp_json = await resp.json()
    if "token" not in resp_json:
        raise ValueError("No token in response")

    return resp_json["token"]


class ScryptedView(HomeAssistantView):
    """Hass.io view to handle base part."""

    name = "api:scrypted"
    url = "/api/scrypted/{token}/{path:.*}"
    requires_auth = False

    def __init__(self, hass: HomeAssistant, session: aiohttp.ClientSession) -> None:
        """Initialize a Hass.io ingress view."""
        self.hass = hass
        self._session = session
        self.lit_core = asyncio.Future[str]()
        self.entrypoint_js = asyncio.Future[str]()
        self.entrypoint_html = asyncio.Future[str]()
        hass.async_add_executor_job(lambda: self.load_files(session.loop))

    def load_files(self, loop: asyncio.AbstractEventLoop):
        lit_core = str(open(os.path.join(os.path.dirname(__file__), "lit-core.min.js")).read())
        entrypoint_js = str(open(os.path.join(os.path.dirname(__file__), "entrypoint.js")).read())
        entrypoint_html = str(open(os.path.join(os.path.dirname(__file__), "entrypoint.html")).read())
        loop.call_soon_threadsafe(lambda: self.lit_core.set_result(lit_core))
        loop.call_soon_threadsafe(lambda: self.entrypoint_js.set_result(entrypoint_js))
        loop.call_soon_threadsafe(lambda: self.entrypoint_html.set_result(entrypoint_html))

    @lru_cache
    def _create_url(self, token: str, path: str) -> str:
        """Create URL to service."""
        entry: ConfigEntry = self.hass.data[DOMAIN][token]
        host = entry.data[CONF_HOST]
        ipport = host.split(":")
        if len(ipport) > 2:
            raise Exception("invalid Scrypted host")
        ip = ipport[0]
        if len(ipport) == 2:
            port = ipport[1]
        else:
            port = "10443"

        base_path = "/"
        url = f"https://{ip}:{port}/{quote(path)}"

        try:
            if not URL(url).path.startswith(base_path):
                raise HTTPBadRequest()
        except ValueError as err:
            raise HTTPBadRequest() from err

        return url

    async def _handle(
        self, request: web.Request, token: str, path: str
    ) -> web.Response | web.StreamResponse | web.WebSocketResponse:
        """Route data to Hass.io ingress service."""
        try:
            if path == "lit-core.min.js":
                response = web.Response(
                    body=await self.lit_core,
                    headers={
                        "Content-Type": "text/javascript",
                        "Cache-Control": "no-store, max-age=0",
                    },
                )
                return response

            if path == "entrypoint.js":
                body = (await self.entrypoint_js).replace("__DOMAIN__", DOMAIN).replace("__TOKEN__", token)
                response = web.Response(
                    body=body,
                    headers={
                        "Content-Type": "text/javascript",
                        "Cache-Control": "no-store, max-age=0",
                    },
                )
                return response

            if path == "entrypoint.html":
                body = (await self.entrypoint_html).replace("__DOMAIN__", DOMAIN).replace("__TOKEN__", token)
                entry: ConfigEntry = self.hass.data[DOMAIN][token]
                if CONF_SCRYPTED_NVR in entry.data and entry.data[CONF_SCRYPTED_NVR]:
                    body = body.replace("core", "nvr")

                response = web.Response(
                    body=body,
                    headers={
                        "Content-Type": "text/html",
                        "Cache-Control": "no-store, max-age=0",
                    },
                )
                return response

            # Websocket
            if _is_websocket(request):
                return await self._handle_websocket(request, token, path)

            # Request
            return await self._handle_request(request, token, path)

        except aiohttp.ClientError as err:
            _LOGGER.debug("Ingress error with %s: %s", path, err)

        raise HTTPBadGateway() from None

    get = _handle
    post = _handle
    put = _handle
    delete = _handle
    patch = _handle
    # options = _handle

    async def _handle_websocket(
        self, request: web.Request, token: str, path: str
    ) -> web.WebSocketResponse:
        """Ingress route for websocket."""
        req_protocols: Iterable[str]
        if hdrs.SEC_WEBSOCKET_PROTOCOL in request.headers:
            req_protocols = [
                str(proto.strip())
                for proto in request.headers[hdrs.SEC_WEBSOCKET_PROTOCOL].split(",")
            ]
        else:
            req_protocols = ()

        ws_server = web.WebSocketResponse(
            protocols=req_protocols, autoclose=False, autoping=False
        )
        await ws_server.prepare(request)

        # Preparing
        url = self._create_url(token, path)
        source_header = _init_header(request)
        source_header["Authorization"] = f"Bearer {token}"

        # Support GET query
        if request.query_string:
            url = f"{url}?{request.query_string}"

        # Start proxy
        async with self._session.ws_connect(
            url,
            verify_ssl=False,
            headers=source_header,
            protocols=req_protocols,
            autoclose=False,
            autoping=False,
        ) as ws_client:
            # Proxy requests
            await asyncio.wait(
                [
                    asyncio.create_task(_websocket_forward(ws_server, ws_client)),
                    asyncio.create_task(_websocket_forward(ws_client, ws_server)),
                ],
                return_when=asyncio.FIRST_COMPLETED,
            )

        return ws_server

    async def _handle_request(
        self, request: web.Request, token: str, path: str
    ) -> web.Response | web.StreamResponse:
        """Ingress route for request."""
        url = self._create_url(token, path)
        source_header = _init_header(request)
        source_header["Authorization"] = f"Bearer {token}"

        async with self._session.request(
            request.method,
            url,
            verify_ssl=False,
            headers=source_header,
            params=request.query,
            allow_redirects=False,
            data=request.content,
            timeout=ClientTimeout(total=None),
            skip_auto_headers={hdrs.CONTENT_TYPE},
        ) as result:
            headers = _response_header(result)

            # Simple request
            if (
                hdrs.CONTENT_LENGTH in result.headers
                and int(result.headers.get(hdrs.CONTENT_LENGTH, 0)) < 4194000
            ) or result.status in (204, 304):
                # Return Response
                body = await result.read()
                return web.Response(
                    headers=headers,
                    status=result.status,
                    content_type=result.content_type,
                    body=body,
                )

            # Stream response
            response = web.StreamResponse(status=result.status, headers=headers)
            response.content_type = result.content_type

            try:
                await response.prepare(request)
                async for data in result.content.iter_chunked(4096):
                    await response.write(data)

            except (
                aiohttp.ClientError,
                aiohttp.ClientPayloadError,
                ConnectionResetError,
            ) as err:
                _LOGGER.debug("Stream error %s: %s", path, err)

            return response


def _init_header(request: web.Request) -> CIMultiDict | dict[str, str]:
    """Create initial header."""
    headers = {}

    # filter flags
    for name, value in request.headers.items():
        if name in (
            hdrs.CONTENT_LENGTH,
            hdrs.CONTENT_ENCODING,
            hdrs.TRANSFER_ENCODING,
            hdrs.CONNECTION,
            hdrs.SEC_WEBSOCKET_EXTENSIONS,
            hdrs.SEC_WEBSOCKET_PROTOCOL,
            hdrs.SEC_WEBSOCKET_VERSION,
            hdrs.SEC_WEBSOCKET_KEY,
            hdrs.HOST,
        ):
            continue
        headers[name] = value

    # Set X-Forwarded-For
    forward_for = request.headers.get(hdrs.X_FORWARDED_FOR)
    assert request.transport
    if (peername := request.transport.get_extra_info("peername")) is None:
        _LOGGER.error("Can't set forward_for header, missing peername")
        raise HTTPBadRequest()

    connected_ip = ip_address(peername[0])
    if forward_for:
        forward_for = f"{forward_for}, {connected_ip!s}"
    else:
        forward_for = f"{connected_ip!s}"
    headers[hdrs.X_FORWARDED_FOR] = forward_for

    # Set X-Forwarded-Host
    if not (forward_host := request.headers.get(hdrs.X_FORWARDED_HOST)):
        forward_host = request.host
    headers[hdrs.X_FORWARDED_HOST] = forward_host

    # Set X-Forwarded-Proto
    forward_proto = request.headers.get(hdrs.X_FORWARDED_PROTO)
    if not forward_proto:
        forward_proto = request.url.scheme
    headers[hdrs.X_FORWARDED_PROTO] = forward_proto

    return headers


def _response_header(response: aiohttp.ClientResponse) -> dict[str, str]:
    """Create response header."""
    headers = {}

    for name, value in response.headers.items():
        if name in (
            hdrs.TRANSFER_ENCODING,
            hdrs.CONTENT_LENGTH,
            hdrs.CONTENT_TYPE,
            hdrs.CONTENT_ENCODING,
        ):
            continue
        headers[name] = value

    return headers


def _is_websocket(request: web.Request) -> bool:
    """Return True if request is a websocket."""
    headers = request.headers

    if (
        "upgrade" in headers.get(hdrs.CONNECTION, "").lower()
        and headers.get(hdrs.UPGRADE, "").lower() == "websocket"
    ):
        return True
    return False


async def _websocket_forward(ws_from, ws_to):
    """Handle websocket message directly."""
    try:
        async for msg in ws_from:
            if msg.type == aiohttp.WSMsgType.TEXT:
                await ws_to.send_str(msg.data)
            elif msg.type == aiohttp.WSMsgType.BINARY:
                await ws_to.send_bytes(msg.data)
            elif msg.type == aiohttp.WSMsgType.PING:
                await ws_to.ping()
            elif msg.type == aiohttp.WSMsgType.PONG:
                await ws_to.pong()
            elif ws_to.closed:
                await ws_to.close(code=ws_to.close_code, message=msg.extra)
    except RuntimeError:
        _LOGGER.debug("Ingress Websocket runtime error")
    except ConnectionResetError:
        _LOGGER.debug("Ingress Websocket Connection Reset")
