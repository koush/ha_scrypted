# Scrypted Custom Component for Home Assistant

The Scrypted Custom Component for Home Assistant adds support managing Scrypted from your HA Dashboard, and creation of Scrypted NVR cards.
This custom component is unnecessary if Scrypted was installed as a Home Assistant OS addon.

<img width="100%" alt="image" src="https://github.com/koush/ha_scrypted/assets/73924/7c6fdd6a-8722-4c82-8581-632cdfa4476d">

## Home Assistant Setup

1. Install this repository using [HACS](https://hacs.xyz) (add this repo as a Custom Repository).
2. Go to `Settings > Devices & Services > Add New` and select Scrypted
3. Enter the host, username, and password for your Scrypted server, as well as a name and icon for the sidebar link in the Home Assistant menu.

## Scrypted NVR Card Setup

[Scrypted NVR provides Home Assistant cards](https://github.com/koush/nvr.scrypted.app/wiki/Home-Assistant) that feature low latency playback and two way audio.

1. Install the Scrypted NVR plugin in Scrypted.
2. Find the Scrypted token sensor entity and note the `token`:
  * <img width="300" alt="image" src="https://github.com/koush/ha_scrypted/assets/73924/a8a44b2d-c1c6-4acd-bc33-11090a892858">
  * <img width="300" alt="image" src="https://github.com/koush/ha_scrypted/assets/73924/83239aef-036b-4977-a5eb-23dd8b2d5eb0">
3. Find the Scrypted camera `id` from within the Scrypted Management console. The `id` is visible in the address bar in the browser. E.g. `32` below:
  * <img width="300" alt="image" src="https://github.com/koush/ha_scrypted/assets/73924/813e4218-3050-4c45-a5ad-db40ff60a159">
4. Then add the following `Webpage Card` in Home Assistant (adjusting `<token>` and `<id>` as necessary):

```yaml
type: iframe
# Replace <id> with the id of your camera in Scrypted.
# Replace <token> with the value from the token entity in Home Assistant.
url: >-
  /api/scrypted/<token>/endpoint/@scrypted/nvr/public/#/iframe/<id>
aspect_ratio: '16:9'
```
