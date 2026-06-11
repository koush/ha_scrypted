"""Import shim for the Scrypted Python SDK.

The SDK is not published to PyPI yet. Try the installed package first, then
fall back to the repo-local vendored symlinks (vendor/scrypted_client) that
point into a sibling checkout of the scrypted main repo.

When the SDK is published, delete the fallback and add the package to
manifest.json requirements instead.
"""
from __future__ import annotations

import sys
from pathlib import Path


def _ensure_sdk_importable() -> None:
    try:
        import scrypted_python  # noqa: F401

        return
    except ImportError:
        pass
    vendor = Path(__file__).resolve().parents[2] / "vendor" / "scrypted_client"
    if vendor.is_dir() and str(vendor) not in sys.path:
        sys.path.insert(0, str(vendor))


_ensure_sdk_importable()

import plugin_remote  # noqa: E402
import rpc_reader  # noqa: E402
from plugin_remote import (  # noqa: E402
    DeviceManager,
    MediaManager,
    PluginRemote,
    SystemManager,
)
from scrypted_python.scrypted_sdk import ScryptedStatic  # noqa: E402
from scrypted_python.scrypted_sdk.types import (  # noqa: E402
    ScryptedDeviceType,
    ScryptedInterface,
    ScryptedInterfaceProperty,
    ScryptedMimeTypes,
)

__all__ = [
    "DeviceManager",
    "MediaManager",
    "PluginRemote",
    "ScryptedDeviceType",
    "ScryptedInterface",
    "ScryptedInterfaceProperty",
    "ScryptedMimeTypes",
    "ScryptedStatic",
    "SystemManager",
    "plugin_remote",
    "rpc_reader",
]
