"""Constants for the Scrypted integration."""

DOMAIN = "scrypted"
CONF_SCRYPTED_NVR = "scrypted_nvr"
CONF_AUTO_REGISTER_RESOURCES = "auto_register_resources"
CONF_ENABLE_ENTITIES = "enable_entities"

# Dispatcher signals. format() args noted per signal.
SIGNAL_DEVICE_UPDATE = "scrypted_{}_device_update_{}"  # entry_id, device_id
SIGNAL_NEW_DEVICE = "scrypted_{}_new_device"  # entry_id; payload: device_id
SIGNAL_CONNECTION = "scrypted_{}_connection"  # entry_id; payload: connected bool

# Scrypted device types that are server plumbing, never user-facing devices.
EXCLUDED_DEVICE_TYPES = {
    "API",
    "Automation",
    "Bridge",
    "Builtin",
    "DataSource",
    "DeviceProvider",
    "Internal",
    "Internet",
    "LLM",
    "Network",
    "Notifier",
    "Program",
    "Scene",
}

# Device-type allowlist option: which scrypted device types produce entities.
CONF_DEVICE_TYPES = "device_types"
DEFAULT_DEVICE_TYPES = ["Camera", "Doorbell"]

# scrypted plugin that imports HA entities into scrypted; mirroring those
# back would duplicate entities and loop commands through two hops.
HA_PLUGIN_ID = "@scrypted/homeassistant"
