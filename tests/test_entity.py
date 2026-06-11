"""Tests for discovery helpers."""
from custom_components.scrypted.entity import device_matches


def test_device_matches_interface(fake_sdk):
    assert device_matches(fake_sdk, "cam1", "MotionSensor")
    assert not device_matches(fake_sdk, "leak1", "MotionSensor")


def test_device_matches_missing_device(fake_sdk):
    assert not device_matches(fake_sdk, "nope", "MotionSensor")


def test_excluded_types_never_match(fake_sdk):
    # plugin1 has Online but is type API (excluded plumbing)
    assert not device_matches(fake_sdk, "plugin1", "Online")
