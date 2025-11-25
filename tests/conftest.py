"""Common fixtures and plugin configuration for Scrypted tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

pytest_plugins = ["pytest_homeassistant_custom_component"]

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import custom_components.scrypted as scrypted  # noqa: E402
from custom_components.scrypted import config_flow  # noqa: E402


@pytest.fixture(autouse=True)
def _patch_async_get_clientsession(monkeypatch):
    """Prevent tests from creating real aiohttp sessions."""

    def _fake_session(*args, **kwargs):
        return SimpleNamespace()

    monkeypatch.setattr(scrypted, "async_get_clientsession", _fake_session)
    monkeypatch.setattr(config_flow, "async_get_clientsession", _fake_session)


@pytest.fixture(autouse=True)
def _patch_retrieve_token(monkeypatch):
    """Return a canned token unless a test overrides the patch."""

    async def _fake_retrieve(data, session):
        return "token"

    monkeypatch.setattr(scrypted, "retrieve_token", _fake_retrieve)
    monkeypatch.setattr(config_flow, "retrieve_token", _fake_retrieve)
