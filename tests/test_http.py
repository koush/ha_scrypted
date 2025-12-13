"""Tests for the Scrypted HTTP module."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
from aiohttp import hdrs
from aiohttp.web_exceptions import HTTPBadGateway, HTTPBadRequest
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME

from custom_components.scrypted import http
from custom_components.scrypted.const import (
    CONF_SCRYPTED_NVR,
    DEFAULT_SCRYPTED_PORT,
    DOMAIN,
    ENTRYPOINT_HTML_FILENAME,
    ENTRYPOINT_JS_FILENAME,
    LIT_CORE_FILENAME,
)
from tests.const import (
    API_PATH,
    GENERIC_PATH,
    HOST_WITH_PORT,
    HOST_WITHOUT_PORT,
    PASSWORD,
    TOKEN,
    USERNAME,
)

HTTP_TOKEN = TOKEN
HTTP_PATH = GENERIC_PATH
HTTP_API_PATH = API_PATH


def _register_entry(
    hass, token: str = TOKEN, host: str = HOST_WITH_PORT, **kwargs
) -> MockConfigEntry:
    """Create and register a config entry stored under hass.data for the view."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: host, **kwargs.get("data", {})},
        options=kwargs.get("options", {}),
    )
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})[token] = entry
    return entry


def _body_text(response) -> str:
    """Decode the body from a Response regardless of how aiohttp stores it."""
    body = response.body
    if hasattr(body, "_value"):
        body = body._value
    return body.decode() if isinstance(body, (bytes, bytearray)) else str(body)


# ---------------------------------------------------------------------------
# retrieve_token tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("host", "password", "expected_url"),
    [
        (HOST_WITH_PORT, PASSWORD, f"https://{HOST_WITH_PORT}/login"),
        (
            HOST_WITHOUT_PORT,
            None,
            f"https://{HOST_WITHOUT_PORT}:{DEFAULT_SCRYPTED_PORT}/login",
        ),
    ],
)
async def test_retrieve_token_builds_request(
    login_success_fixture, host, password, expected_url
):
    """Token retrieval should build the login request and return the token."""
    mock_response = AsyncMock()
    mock_response.json = AsyncMock(return_value=login_success_fixture)

    mock_session = MagicMock(spec=aiohttp.ClientSession)
    mock_session.get = AsyncMock(return_value=mock_response)

    data = {CONF_HOST: host, CONF_USERNAME: USERNAME}
    if password is not None:
        data[CONF_PASSWORD] = password

    token = await http.retrieve_token(data, mock_session)

    assert token == login_success_fixture["token"]
    called_url = mock_session.get.call_args.args[0]
    assert called_url == expected_url
    headers = mock_session.get.call_args.kwargs["headers"]
    assert headers["authorization"].startswith("Basic ")


async def test_retrieve_token_no_token_in_response(login_error_not_logged_in_fixture):
    """Test ValueError is raised when response has no token."""
    mock_response = AsyncMock()
    mock_response.json = AsyncMock(return_value=login_error_not_logged_in_fixture)

    mock_session = AsyncMock(spec=aiohttp.ClientSession)
    mock_session.get = AsyncMock(return_value=mock_response)

    data = {
        CONF_HOST: HOST_WITH_PORT,
        CONF_USERNAME: USERNAME,
        CONF_PASSWORD: "wrongpass",
    }

    with pytest.raises(ValueError, match="No token in response"):
        await http.retrieve_token(data, mock_session)


async def test_retrieve_token_invalid_host_too_many_colons():
    """Test exception is raised for invalid host with multiple colons."""
    mock_session = AsyncMock(spec=aiohttp.ClientSession)

    data = {
        CONF_HOST: f"{HOST_WITH_PORT}:extra",
        CONF_USERNAME: USERNAME,
        CONF_PASSWORD: PASSWORD,
    }

    with pytest.raises(Exception, match="invalid Scrypted host"):
        await http.retrieve_token(data, mock_session)


# ---------------------------------------------------------------------------
# ScryptedView tests
# ---------------------------------------------------------------------------


async def test_view_attributes(scrypted_view):
    """Test ScryptedView has correct attributes."""
    assert scrypted_view.name == "api:scrypted"
    assert scrypted_view.url == "/api/scrypted/{token}/{path:.*}"
    assert scrypted_view.requires_auth is False


@pytest.mark.parametrize(
    ("host", "path", "expected"),
    [
        (HOST_WITH_PORT, HTTP_PATH, f"https://{HOST_WITH_PORT}/{HTTP_PATH}"),
        (
            HOST_WITHOUT_PORT,
            "path",
            f"https://{HOST_WITHOUT_PORT}:{DEFAULT_SCRYPTED_PORT}/path",
        ),
    ],
)
async def test_create_url_builds_https_urls(hass, scrypted_view, host, path, expected):
    """Ensure _create_url applies default port and quoting rules."""
    _register_entry(hass, host=host)
    scrypted_view._create_url.cache_clear()

    assert scrypted_view._create_url(HTTP_TOKEN, path) == expected


async def test_create_url_invalid_host(hass, scrypted_view):
    """Test URL creation fails for invalid host."""
    _register_entry(hass, host=f"{HOST_WITH_PORT}:extra")
    scrypted_view._create_url.cache_clear()

    with pytest.raises(Exception, match="invalid Scrypted host"):
        scrypted_view._create_url(HTTP_TOKEN, "path")


async def test_create_url_raises_on_invalid_url(hass, scrypted_view):
    """Test _create_url raises HTTPBadRequest for malformed URLs."""
    _register_entry(hass)
    scrypted_view._create_url.cache_clear()

    with patch(
        "custom_components.scrypted.http.URL", side_effect=ValueError("invalid")
    ):
        with pytest.raises(HTTPBadRequest):
            scrypted_view._create_url(HTTP_TOKEN, HTTP_PATH)


async def test_create_url_rejects_path_outside_base(hass, scrypted_view):
    """Test _create_url rejects paths that don't stay within base path."""
    _register_entry(hass)
    scrypted_view._create_url.cache_clear()

    fake_url = SimpleNamespace(path="badpath")
    with patch("custom_components.scrypted.http.URL", return_value=fake_url):
        with pytest.raises(HTTPBadRequest):
            scrypted_view._create_url(HTTP_TOKEN, HTTP_PATH)


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({hdrs.CONNECTION: "Upgrade", hdrs.UPGRADE: "websocket"}, True),
        ({hdrs.CONNECTION: "keep-alive"}, False),
        ({hdrs.CONNECTION: "Upgrade", hdrs.UPGRADE: "h2c"}, False),
        ({hdrs.CONNECTION: "UPGRADE", hdrs.UPGRADE: "WEBSOCKET"}, True),
    ],
)
def test_is_websocket(mock_web_request, headers, expected):
    """_is_websocket should detect upgrade headers case-insensitively."""
    request = mock_web_request(headers=headers)
    assert http._is_websocket(request) is expected


def test_response_header_filters_headers():
    """Test _response_header filters out certain headers."""
    mock_response = MagicMock(spec=aiohttp.ClientResponse)
    mock_response.headers = {
        hdrs.CONTENT_TYPE: "application/json",
        hdrs.CONTENT_LENGTH: "100",
        hdrs.TRANSFER_ENCODING: "chunked",
        hdrs.CONTENT_ENCODING: "gzip",
        "X-Custom-Header": "value",
        "Cache-Control": "no-cache",
    }

    headers = http._response_header(mock_response)

    # These should be filtered out
    assert hdrs.CONTENT_TYPE not in headers
    assert hdrs.CONTENT_LENGTH not in headers
    assert hdrs.TRANSFER_ENCODING not in headers
    assert hdrs.CONTENT_ENCODING not in headers

    # These should remain
    assert headers["X-Custom-Header"] == "value"
    assert headers["Cache-Control"] == "no-cache"


# ---------------------------------------------------------------------------
# _init_header tests
# ---------------------------------------------------------------------------


def test_init_header_filters_and_sets_forwarding(mock_web_request):
    """Headers should be cleaned and forwarded headers applied."""
    request = mock_web_request(
        headers={
            hdrs.CONTENT_LENGTH: "100",
            hdrs.CONTENT_ENCODING: "gzip",
            hdrs.TRANSFER_ENCODING: "chunked",
            hdrs.CONNECTION: "Upgrade",
            hdrs.SEC_WEBSOCKET_EXTENSIONS: "permessage-deflate",
            hdrs.SEC_WEBSOCKET_PROTOCOL: "graphql-ws",
            hdrs.SEC_WEBSOCKET_VERSION: "13",
            hdrs.SEC_WEBSOCKET_KEY: "abc123",
            hdrs.X_FORWARDED_FOR: "10.0.0.1",
            "X-Custom-Header": "value",
        },
        host="myhost.local:8123",
        scheme="https",
    )

    headers = http._init_header(request)

    assert headers[hdrs.X_FORWARDED_FOR] == "10.0.0.1, 192.168.1.50"
    assert headers[hdrs.X_FORWARDED_HOST] == "myhost.local:8123"
    assert headers[hdrs.X_FORWARDED_PROTO] == "https"
    assert hdrs.CONTENT_LENGTH not in headers
    assert hdrs.CONNECTION not in headers
    assert hdrs.SEC_WEBSOCKET_VERSION not in headers
    assert headers["X-Custom-Header"] == "value"


def test_init_header_respects_existing_forwarded_headers(mock_web_request):
    """Existing forwarded headers should be preserved when present."""
    request = mock_web_request(
        headers={
            hdrs.X_FORWARDED_HOST: "original.host",
            hdrs.X_FORWARDED_PROTO: "http",
            hdrs.X_FORWARDED_FOR: "10.0.0.1",
        },
        scheme="https",
    )
    headers = http._init_header(request)
    assert headers[hdrs.X_FORWARDED_HOST] == "original.host"
    assert headers[hdrs.X_FORWARDED_PROTO] == "http"
    assert headers[hdrs.X_FORWARDED_FOR] == "10.0.0.1, 192.168.1.50"


def test_init_header_sets_forwarded_for_when_missing(mock_web_request):
    """When X-Forwarded-For is absent, it should be set from the peername."""
    request = mock_web_request(headers={})
    headers = http._init_header(request)
    assert headers[hdrs.X_FORWARDED_FOR] == "192.168.1.50"


def test_init_header_raises_on_missing_peername(mock_web_request):
    """Test _init_header raises HTTPBadRequest when peername is missing."""
    request = mock_web_request(peername=None)
    with pytest.raises(HTTPBadRequest):
        http._init_header(request)


# ---------------------------------------------------------------------------
# ScryptedView._handle tests (static file serving)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "token", "expected_strings"),
    [
        (LIT_CORE_FILENAME, HTTP_TOKEN, ("lit-core-content",)),
        (ENTRYPOINT_JS_FILENAME, "my_token", ("scrypted", "my_token")),
    ],
)
async def test_handle_static_js(
    scrypted_view, mock_web_request, path, token, expected_strings
):
    """Static JS assets should be served with cache disabled."""
    request = mock_web_request()
    response = await scrypted_view._handle(request, token, path)

    body_text = _body_text(response)
    for expected in expected_strings:
        assert expected in body_text
    assert response.headers["Content-Type"] == "text/javascript"
    assert response.headers["Cache-Control"] == "no-store, max-age=0"


@pytest.mark.parametrize(
    ("entry_kwargs", "expected_substring", "forbidden"),
    [
        ({}, "core html-content", "nvr"),
        ({"options": {CONF_SCRYPTED_NVR: True}}, "nvr html-content", None),
        ({"data": {CONF_SCRYPTED_NVR: True}}, "nvr html-content", None),
    ],
)
async def test_handle_entrypoint_html(
    hass, scrypted_view, mock_web_request, entry_kwargs, expected_substring, forbidden
):
    """entrypoint.html should respect NVR flag from config entry data or options."""
    _register_entry(hass, **entry_kwargs)

    request = mock_web_request()
    response = await scrypted_view._handle(
        request, HTTP_TOKEN, ENTRYPOINT_HTML_FILENAME
    )

    body_text = _body_text(response)
    assert expected_substring in body_text
    if forbidden:
        assert forbidden not in body_text
    assert response.headers["Content-Type"] == "text/html"


async def test_handle_proxies_to_websocket(hass, scrypted_view, mock_web_request):
    """Test _handle delegates to _handle_websocket for websocket requests."""
    _register_entry(hass)
    request = mock_web_request(
        headers={"Connection": "Upgrade", "Upgrade": "websocket"}
    )

    mock_ws_response = MagicMock()
    with patch(
        "custom_components.scrypted.http.ScryptedView._handle_websocket",
        new_callable=AsyncMock,
        return_value=mock_ws_response,
    ) as mock_ws:
        response = await scrypted_view._handle(request, HTTP_TOKEN, HTTP_PATH)

    mock_ws.assert_called_once_with(request, HTTP_TOKEN, HTTP_PATH)
    assert response == mock_ws_response


async def test_handle_proxies_to_request(hass, scrypted_view, mock_web_request):
    """Test _handle delegates to _handle_request for regular requests."""
    _register_entry(hass)
    request = mock_web_request(headers={"Connection": "keep-alive"})

    mock_response = MagicMock()
    with patch(
        "custom_components.scrypted.http.ScryptedView._handle_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ) as mock_req:
        response = await scrypted_view._handle(request, HTTP_TOKEN, HTTP_API_PATH)

    mock_req.assert_called_once_with(request, HTTP_TOKEN, HTTP_API_PATH)
    assert response == mock_response


async def test_handle_raises_bad_gateway_on_client_error(
    hass, scrypted_view, mock_web_request
):
    """Test _handle raises HTTPBadGateway on aiohttp.ClientError."""
    _register_entry(hass)
    request = mock_web_request(headers={"Connection": "keep-alive"})

    with patch(
        "custom_components.scrypted.http.ScryptedView._handle_request",
        new_callable=AsyncMock,
        side_effect=aiohttp.ClientError(),
    ):
        with pytest.raises(HTTPBadGateway):
            await scrypted_view._handle(request, HTTP_TOKEN, HTTP_API_PATH)


async def test_handle_websocket_builds_headers_and_query(
    hass, scrypted_view, mock_web_request
):
    """_handle_websocket should set auth headers, protocols, and include query."""
    _register_entry(hass)
    request = mock_web_request(headers={hdrs.SEC_WEBSOCKET_PROTOCOL: "proto1, proto2"})
    request.query_string = "a=1"

    fake_server_ws = AsyncMock()
    fake_server_ws.closed = False
    fake_server_ws.close_code = None

    class DummyContextManager:
        def __init__(self, ws):
            self.ws = ws

        async def __aenter__(self):
            return self.ws

        async def __aexit__(self, exc_type, exc, tb):
            return False

    client_ws = AsyncMock()

    def fake_ws_connect(*args, **kwargs):
        return DummyContextManager(client_ws)

    scrypted_view._session.ws_connect = MagicMock(side_effect=fake_ws_connect)

    with (
        patch(
            "custom_components.scrypted.http.web.WebSocketResponse",
            return_value=fake_server_ws,
        ),
        patch(
            "custom_components.scrypted.http._websocket_forward",
            AsyncMock(return_value=None),
        ) as forward,
    ):
        response = await scrypted_view._handle_websocket(
            request, HTTP_TOKEN, HTTP_API_PATH
        )

    expected_url = f"https://{HOST_WITH_PORT}/{HTTP_API_PATH}?a=1"
    scrypted_view._session.ws_connect.assert_called_once()
    call_args = scrypted_view._session.ws_connect.call_args
    assert call_args.args[0] == expected_url
    assert call_args.kwargs["headers"]["Authorization"] == f"Bearer {HTTP_TOKEN}"
    assert call_args.kwargs["protocols"] == ["proto1", "proto2"]
    fake_server_ws.prepare.assert_awaited_once_with(request)
    assert response == fake_server_ws
    assert forward.await_count == 2


async def test_handle_request_streams_large_responses(
    hass, scrypted_view, mock_web_request
):
    """_handle_request should stream large responses."""
    _register_entry(hass)
    request = mock_web_request()
    request.method = "GET"
    request.query = {}
    request.content = b""

    class FakeContent:
        async def iter_chunked(self, size):
            for chunk in (b"chunk1", b"chunk2"):
                yield chunk

    class FakeResponse:
        def __init__(self):
            self.headers = {hdrs.CONTENT_LENGTH: "5000000", "X-Test": "1"}
            self.status = 200
            self.content_type = "application/json"
            self.content = FakeContent()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    def fake_request(*args, **kwargs):
        return FakeResponse()

    scrypted_view._session.request = MagicMock(side_effect=fake_request)

    fake_stream = MagicMock()
    fake_stream.prepare = AsyncMock()
    fake_stream.write = AsyncMock()

    with patch(
        "custom_components.scrypted.http.web.StreamResponse", return_value=fake_stream
    ):
        response = await scrypted_view._handle_request(
            request, HTTP_TOKEN, HTTP_API_PATH
        )

    scrypted_view._session.request.assert_called_once()
    fake_stream.prepare.assert_awaited_once_with(request)
    fake_stream.write.assert_any_await(b"chunk1")
    fake_stream.write.assert_any_await(b"chunk2")
    assert response == fake_stream


async def test_websocket_forward_handles_message_types():
    """_websocket_forward should route text, binary, ping, and pong frames."""

    class DummyMsg:
        def __init__(self, msg_type, data=b"", extra=None):
            self.type = msg_type
            self.data = data
            self.extra = extra

    class DummyWS:
        def __init__(self, messages):
            self._messages = messages
            self.sent = []
            self.closed = False
            self.close_code = None

        def __aiter__(self):
            async def _gen():
                for msg in self._messages:
                    yield msg

            return _gen()

        async def send_str(self, data):
            self.sent.append(("str", data))

        async def send_bytes(self, data):
            self.sent.append(("bytes", data))

        async def ping(self):
            self.sent.append(("ping", None))

        async def pong(self):
            self.sent.append(("pong", None))

        async def close(self, code=None, message=None):
            self.sent.append(("close", code, message))

    messages = [
        DummyMsg(aiohttp.WSMsgType.TEXT, "hi"),
        DummyMsg(aiohttp.WSMsgType.BINARY, b"bytes"),
        DummyMsg(aiohttp.WSMsgType.PING),
        DummyMsg(aiohttp.WSMsgType.PONG),
    ]
    source = DummyWS(messages)
    target = DummyWS([])

    await http._websocket_forward(source, target)

    assert target.sent == [
        ("str", "hi"),
        ("bytes", b"bytes"),
        ("ping", None),
        ("pong", None),
    ]


# ---------------------------------------------------------------------------
# ScryptedView.load_files tests
# ---------------------------------------------------------------------------


def test_load_files():
    """Test load_files reads files and sets futures."""
    loop = asyncio.new_event_loop()

    view = SimpleNamespace(
        lit_core=loop.create_future(),
        entrypoint_js=loop.create_future(),
        entrypoint_html=loop.create_future(),
    )

    file_contents = {
        LIT_CORE_FILENAME: "lit content",
        ENTRYPOINT_JS_FILENAME: "js content",
        ENTRYPOINT_HTML_FILENAME: "html content",
    }

    def fake_read_text(self, encoding="utf-8"):
        return file_contents[self.name]

    with patch("pathlib.Path.read_text", side_effect=fake_read_text, autospec=True):
        http.ScryptedView.load_files(view, loop)

    loop.run_until_complete(asyncio.sleep(0))

    assert view.lit_core.result() == "lit content"
    assert view.entrypoint_js.result() == "js content"
    assert view.entrypoint_html.result() == "html content"
