# Scrypted Custom Component for Home Assistant

The Scrypted Custom Component for Home Assistant adds support for managing Scrypted from your Home Assistant Dashboard, and creation of Scrypted NVR cards.

<img width="100%" alt="image" src="https://github.com/koush/ha_scrypted/assets/73924/b76b239a-a61a-451a-84aa-1d3621594a68">

Visit the [Scrypted Documentation](https://docs.scrypted.app/home-assistant.html) for setup instructions.

## Device entities

When *Create entities for Scrypted devices* is enabled (default), the
integration connects to the Scrypted server over its engine.io RPC API and
creates entities for discovered devices:

- **Camera** — snapshots and live streams for `VideoCamera` devices. Cameras
  exposing `RTCSignalingChannel` (anything managed by the Scrypted WebRTC
  plugin) stream natively over WebRTC end-to-end; others fall back to the
  RTSP rebroadcast stream.
- **Binary sensor** — motion, audio, occupancy, flood, entry, power,
  connectivity, tamper, charging.
- **Sensor** — temperature, humidity, battery, illuminance, UV, CO2,
  PM2.5/PM10, VOC, NOx, air quality.
- **Event** — object detection (`person`, `car`, … from the detector's
  reported classes) and doorbell presses, usable as automation triggers.

State updates are pushed; no polling. Entities reconnect automatically if the
server restarts.

### Development

The Scrypted Python SDK is not yet on PyPI. For development,
`vendor/scrypted_client` symlinks into a sibling checkout of the scrypted repo
(see `vendor/README.md`). `scripts/dev_connect.py` smoke-tests connectivity
against a real server.
