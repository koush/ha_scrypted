"""Tests for the Scrypted HTTP proxy view."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from homeassistant.const import CONF_HOST

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.scrypted.const import DOMAIN
from custom_components.scrypted.http import ScryptedView


def _build_view(hass) -> ScryptedView:
    """Create a ScryptedView with a dummy session."""
    return ScryptedView(hass, SimpleNamespace(loop=hass.loop))


@pytest.mark.asyncio
async def test_get_state_accepts_entry_id_and_legacy_token(hass):
    """Runtime state can be resolved by entry ID and legacy token route."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "example"})
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "entry": entry,
        "token": "token",
    }

    view = _build_view(hass)

    assert view._get_state(entry.entry_id)["entry"] == entry
    assert view._get_state("token")["entry"] == entry


@pytest.mark.asyncio
async def test_entrypoint_uses_requested_identifier(hass):
    """The entrypoint keeps using whichever route identifier was requested."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "example"})
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "entry": entry,
        "token": "token",
    }

    view = _build_view(hass)
    response = await view._handle(SimpleNamespace(), entry.entry_id, "entrypoint.js")
    body = response.body.decode()

    assert f"/api/{DOMAIN}/{entry.entry_id}/entrypoint.html" in body


@pytest.mark.asyncio
async def test_create_url_uses_entry_state_for_host(hass):
    """URL creation resolves the backend host from the entry ID state."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "1.2.3.4:10443"})
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "entry": entry,
        "token": "token",
    }

    view = _build_view(hass)

    assert view._create_url(entry.entry_id, "endpoint/foo") == "https://1.2.3.4:10443/endpoint/foo"
