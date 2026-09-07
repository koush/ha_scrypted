# TODO

## 1. Cache Scrypted resources in Home Assistant

Resources are currently served from Scrypted over the ingress proxy and may
fail if Scrypted is remote or temporarily unavailable. Cache the web-components
assets locally whenever they are fetched through `ScryptedView` and expose the
cached files via a registered static path, falling back to the cache on ingress
failures. Ensure the local static path is registered on setup and cleaned up on
unload, mirroring the approach used in `lock_code_manager`.

## 2. Add automated testing and coverage requirements

Introduce a test suite with code coverage reporting (e.g., Codecov) to enforce
minimum component-level and overall coverage for new PRs. Once the baseline
coverage is in place, gate future changes on maintaining those thresholds.

## 3. Generate native camera entities via the Scrypted engineio API

Investigate using Scrypted's engineio API to surface each managed camera as a
Home Assistant entity, along with relevant events. Forward Scrypted events into
Home Assistant so users can leverage HA automations (in addition to or instead
of Scrypted automations) without manual wiring. With entities representing each
device, the custom frontend cards could be configured by selecting HA entities
rather than copying Scrypted device IDs manually.

## 4. Improve card configuration UX

Open an issue describing how the cards can adopt Home Assistant's graphical
card configuration flow per the guidance in the
[Custom Card documentation](https://developers.home-assistant.io/docs/frontend/custom-ui/custom-card#graphical-card-configuration).
The cards are simple enough that the built-in form editor should work once the
schema is defined, making the setup more approachable.

## 5. Make the integration NVR-aware

Determine whether the connected Scrypted instance has an active NVR
subscription (via its upstream API) so we can tailor functionality accordingly.
Use that signal to gate features like Lovelace resource auto-registration,
exposing them only when NVR is enabled. Surface the subscription state in the
UI so users know why certain features are or are not available.

## 6. Move panel configuration into the options flow

The credentials reauth step currently collects the panel name/icon alongside
passwords; move those UI fields into the options flow so credential updates
only prompt for authentication details. Once the options flow exposes these
fields, remove them from the credentials step to reduce user confusion.

## 7. NVR clips: inline playback in Chrome

Clips resolve to HLS through HA's stream component, which plays inline on
Safari/iOS, the companion apps and Chromecast, but not in Chrome/desktop
because HA's generic media dialog lacks hls.js (core's camera media source
only works via the camera entity's own player). Universal inline playback
needs native MP4, and scrypted NVR cannot convert clips synchronously (only to
FFmpegInput), so this would be an async NVR mp4-export flow: start the export
on resolve, poll for completion, serve through the proxy.

## 8. Controllable device follow-ups

- Reconnect discovery gap: `ScryptedClient.async_connect` reseeds
  `_known_ids` on reconnect, so devices added during an outage never fire
  `SIGNAL_NEW_DEVICE` and get no entities until reload. Dispatch the signal
  for genuinely new ids on reconnect; the platform helper dedups.
- Climate `supported_features` flips between TARGET_TEMPERATURE and
  TARGET_TEMPERATURE_RANGE based on the live setpoint shape and advertises
  TURN_OFF even when "Off" is not an available mode; derive stable flags from
  `availableModes`.
- Fan `availableModes` is captured only at entity construction; a fan whose
  FanStatus populates after discovery never gains PRESET_MODE.
- `async_remove_config_entry_device` reimplements the discovery check inline
  and lacks the HA_PLUGIN_ID loop guard; share a predicate with
  `device_matches`.
- PTZ support (`PanTiltZoom` interface) on cameras.
