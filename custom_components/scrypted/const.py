"""Constants for the Scrypted integration."""

DOMAIN = "scrypted"
CONF_SCRYPTED_NVR = "scrypted_nvr"
CONF_AUTO_REGISTER_RESOURCES = "auto_register_resources"
DEFAULT_SCRYPTED_PORT = "10443"

LIT_CORE_FILENAME = "lit-core.min.js"
ENTRYPOINT_JS_FILENAME = "entrypoint.js"
ENTRYPOINT_HTML_FILENAME = "entrypoint.html"

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
    "Program",
    "Scene",
}

# Device-type allowlist option: which scrypted device types produce entities.
CONF_DEVICE_TYPES = "device_types"
DEFAULT_DEVICE_TYPES = ["Camera", "Doorbell"]

# Plugin exclusion option: scrypted plugin ids whose devices never produce
# entities, e.g. plugins bridging devices Home Assistant already integrates.
# Wins over both the type allowlist and the smart sensor exception.
CONF_EXCLUDED_PLUGINS = "excluded_plugins"

# scrypted plugin that imports HA entities into scrypted; mirroring those
# back would duplicate entities and loop commands through two hops.
HA_PLUGIN_ID = "@scrypted/homeassistant"

# scrypted plugin whose Smart Motion/Occupancy Sensors (type Sensor) filter a
# camera's detections by object class. They exist only in scrypted, so unlike
# Sensor devices bridged from Ring, UniFi or MQTT they never duplicate an HA
# integration and are exposed regardless of the type allowlist.
SMART_SENSOR_PLUGIN_ID = "@scrypted/objectdetector"
SMART_SENSOR_TYPE = "Sensor"
