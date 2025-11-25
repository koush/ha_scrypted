import asyncio
from types import SimpleNamespace

import aiohttp
from aiohttp import web
import pytest
from yarl import URL

from custom_components.scrypted import http
from custom_components.scrypted.const import CONF_SCRYPTED_NVR, DOMAIN


class FakeResponse:
    def __init__(self, data):
        self._data = data

    async def json(self):
        return self._data


class FakeSession:
    def __init__(self, data):
        self._data = data

    async def get(self, *args, **kwargs):
        return FakeResponse(self._data)


@pytest.mark.asyncio
async def test_retrieve_token_success():
    token = await http.retrieve_token(
        {
            "username": "user",
            "password": "pass",
            "host": "1.1.1.1:1234",
        },
        FakeSession({"token": "abc"}),
    )
    assert token == "abc"


@pytest.mark.asyncio
async def test_retrieve_token_missing_token():
    with pytest.raises(ValueError):
        await http.retrieve_token(
            {"username": "user", "password": "", "host": "1.1.1.1"},
            FakeSession({}),
        )


def _fake_request(headers=None, query_string="", peer="127.0.0.1"):
    headers = headers or {}
    request = SimpleNamespace()
    request.headers = headers
    request.transport = SimpleNamespace(
        get_extra_info=lambda name: (peer, 0) if name == "peername" else None
    )
    request.host = "example"
    request.url = URL("https://example/base")
    request.query = {}
    request.method = "GET"
    request.content = b""
    request.query_string = query_string
    return request


def test_init_header_and_response_header():
    request = _fake_request(
        {
            "X-Forwarded-For": "10.0.0.1",
            "Connection": "keep-alive, Upgrade",
            "Upgrade": "websocket",
        }
    )
    headers = http._init_header(request)
    assert "X-Forwarded-For" in headers
    response = SimpleNamespace(headers={"Transfer-Encoding": "chunked", "X-Test": "1"})
    out_headers = http._response_header(response)
    assert "X-Test" in out_headers and "Transfer-Encoding" not in out_headers


def test_is_websocket_detection():
    ws_headers = {aiohttp.hdrs.CONNECTION: "Upgrade", aiohttp.hdrs.UPGRADE: "websocket"}
    assert http._is_websocket(SimpleNamespace(headers=ws_headers))
    assert not http._is_websocket(SimpleNamespace(headers={}))


@pytest.mark.asyncio
async def test_websocket_forward_text_and_binary():
    class FakeMsg:
        def __init__(self, msg_type, data=b""):
            self.type = msg_type
            self.data = data
            self.extra = b""

    class FakeWS:
        def __init__(self, messages):
            self._messages = messages
            self.sent = []
            self.closed = False
            self.close_code = 1000

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

        async def close(self, **kwargs):
            self.closed = True

    ws_from = FakeWS(
        [
            FakeMsg(aiohttp.WSMsgType.TEXT, "hello"),
            FakeMsg(aiohttp.WSMsgType.BINARY, b"data"),
            FakeMsg(aiohttp.WSMsgType.PING),
            FakeMsg(aiohttp.WSMsgType.PONG),
        ]
    )
    ws_to = FakeWS([])
    await http._websocket_forward(ws_from, ws_to)
    assert ("str", "hello") in ws_to.sent
    assert ("bytes", b"data") in ws_to.sent


@pytest.mark.asyncio
async def test_scrypted_view_static_handlers(monkeypatch, event_loop):
    hass = SimpleNamespace(
        data={DOMAIN: {"tok": SimpleNamespace(data={CONF_SCRYPTED_NVR: True})}},
        async_add_executor_job=lambda func: func(),
    )
    session = SimpleNamespace(loop=event_loop)
    monkeypatch.setattr(http.ScryptedView, "load_files", lambda self, loop: None)
    view = http.ScryptedView(hass, session)
    view.lit_core.set_result("core")
    view.entrypoint_js.set_result("console.log('__TOKEN__')")
    view.entrypoint_html.set_result("<html>core</html>")
    request = _fake_request()
    response = await view._handle(request, "tok", "lit-core.min.js")
    assert response.body == b"core"
    response = await view._handle(request, "tok", "entrypoint.js")
    assert b"tok" in response.body
    response = await view._handle(request, "tok", "entrypoint.html")
    assert b"nvr" in response.body

    async def _fake_request_handler(_, __, ___):
        return web.Response(text="ok")

    view._handle_request = _fake_request_handler
    response = await view._handle(request, "tok", "other")
    assert response.text == "ok"

    async def _raise(*args, **kwargs):
        raise aiohttp.ClientError()

    view._handle_request = _raise
    with pytest.raises(web.HTTPBadGateway):
        await view._handle(request, "tok", "bad")


class DummyStreamResponse:
    def __init__(self, status, headers):
        self.status = status
        self.headers = headers
        self.content_type = None
        self.body = b""

    async def prepare(self, request):
        return True

    async def write(self, data):
        self.body += data


class DummyWSResponse:
    def __init__(self, *args, **kwargs):
        self.prepared = False

    async def prepare(self, request):
        self.prepared = True


class DummyWSClient:
    async def __aenter__(self):
        return SimpleNamespace(close=asyncio.coroutine(lambda *args: None))

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_handle_request_streaming(monkeypatch, event_loop):
    hass = SimpleNamespace(
        data={DOMAIN: {"tok": SimpleNamespace(data={})}},
        async_add_executor_job=lambda func: func(),
    )
    session = SimpleNamespace(loop=event_loop)
    view = http.ScryptedView(hass, session)

    async def _chunker(body):
        yield body

    class DummyResult:
        def __init__(self, headers, body: bytes):
            self.headers = headers
            self.status = 200
            self.content_type = "text/plain"
            self._body = body
            self.content = SimpleNamespace(iter_chunked=lambda size: _chunker(body))

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def read(self):
            return self._body

    def _request(*args, **kwargs):
        headers = {"Content-Length": "9999999"}
        return DummyResult(headers, b"stream")

    monkeypatch.setattr(view, "_session", SimpleNamespace(request=_request))
    monkeypatch.setattr(http.web, "StreamResponse", DummyStreamResponse)
    request = _fake_request()
    response = await view._handle_request(request, "tok", "path")
    assert isinstance(response, DummyStreamResponse)
    assert response.body == b"stream"


@pytest.mark.asyncio
async def test_handle_websocket(monkeypatch, event_loop):
    hass = SimpleNamespace(
        data={DOMAIN: {"tok": SimpleNamespace(data={})}},
        async_add_executor_job=lambda func: func(),
    )
    session = SimpleNamespace(loop=event_loop)
    view = http.ScryptedView(hass, session)
    dummy_request = _fake_request({aiohttp.hdrs.SEC_WEBSOCKET_PROTOCOL: "chat"})
    monkeypatch.setattr(
        http.web, "WebSocketResponse", lambda *args, **kwargs: DummyWSResponse()
    )
    monkeypatch.setattr(
        view,
        "_session",
        SimpleNamespace(ws_connect=lambda *args, **kwargs: DummyWSClient()),
    )
    async def _noop(*args, **kwargs):
        return None
    monkeypatch.setattr(http, "_websocket_forward", _noop)
    response = await view._handle_websocket(dummy_request, "tok", "path")
    assert isinstance(response, DummyWSResponse)
