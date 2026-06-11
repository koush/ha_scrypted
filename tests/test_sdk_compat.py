"""Tests for the SDK import shim."""


def test_sdk_imports():
    """The shim exposes the SDK regardless of install mechanism."""
    from custom_components.scrypted import sdk_compat

    assert sdk_compat.ScryptedInterface.MotionSensor.value == "MotionSensor"
    assert sdk_compat.ScryptedInterfaceProperty.motionDetected.value == "motionDetected"
    assert sdk_compat.ScryptedMimeTypes.FFmpegInput.value == "x-scrypted/x-ffmpeg-input"
    # Runtime pieces used by client.py
    assert hasattr(sdk_compat, "plugin_remote")
    assert hasattr(sdk_compat, "rpc_reader")
    assert hasattr(sdk_compat, "ScryptedStatic")
