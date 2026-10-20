"""Button entities for one-shot scrypted device actions."""

from __future__ import annotations

from dataclasses import dataclass

from scrypted_sdk import ScryptedInterface

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import (
    ScryptedDeviceEntity,
    ScryptedEntityDescriptionMixin,
    async_setup_scrypted_platform,
    device_matches,
)


@dataclass(frozen=True, kw_only=True)
class ScryptedButtonDescription(
    ButtonEntityDescription, ScryptedEntityDescriptionMixin
):
    """Describe a scrypted button."""

    method: str


BUTTONS: tuple[ScryptedButtonDescription, ...] = (
    # Created disabled: a restart is rarely needed and takes the device
    # offline, so it should not sit one tap away on every camera.
    ScryptedButtonDescription(
        key="restart",
        name="Restart",
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        interface=ScryptedInterface.Reboot.value,
        method="reboot",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up scrypted buttons."""
    client = config_entry.runtime_data.client

    def _discover(device_id: str) -> list[ScryptedButton]:
        return [
            ScryptedButton(client, config_entry, device_id, description)
            for description in BUTTONS
            if device_matches(client, device_id, description.interface)
        ]

    await async_setup_scrypted_platform(
        hass, config_entry, async_add_entities, _discover
    )


class ScryptedButton(ScryptedDeviceEntity, ButtonEntity):
    """Invokes a scrypted device method when pressed."""

    entity_description: ScryptedButtonDescription

    async def async_press(self) -> None:
        """Invoke the device method."""
        await self._async_device_command(self.entity_description.method)
