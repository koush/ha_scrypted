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
