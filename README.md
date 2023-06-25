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
2. Then add the following `Webpage Card` in Home Assistant (adjusting token and `24` as necessary):

```yaml
type: iframe
# Replace "24" with the id of your camera in Scrypted. The id is visible in the address bar in the browser.
# The integration provides a token sensor that will give you the token value to enter into the URL below
url: >-
  /api/scrypted/<my_token>/endpoint/@scrypted/nvr/public/#/iframe/24
aspect_ratio: '16:9'
```
