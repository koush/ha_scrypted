# Scrypted Custom Component for Home Assistant

The Scrypted Custom Component for Home Assistant adds support managing Scrypted from your HA Dashboard, and creation of Scrypted NVR cards.
This custom component is unnecessary if Scrypted was installed as a Home Assistant OS addon.

<img width="100%" alt="image" src="https://github.com/koush/ha_scrypted/assets/73924/7c6fdd6a-8722-4c82-8581-632cdfa4476d">


## Scrypted Setup

Retrieve a token that Home Assistant can use to authenticate with Scrypted.

1. In the Scrypted Management Console, open the Terminal tool in the drawer.
2. Run `npx scrypted login`.
3. Log in with your Scrypted credentials for your user token.

Example:

```
koush@Koushik-MacStudio nvr-electron % npx scrypted login
username: koush
password: ********
login successful. token: 28d12b0b97cd99c3f0808cb7a78d08ef
```

## Home Assistant Setup

1. Install this repository using [HACS](https://hacs.xyz).
2. Edit `configuration.yaml` and add the following (adjusting local IP and token):

```yaml
scrypted:
  host: 192.168.1.124:10443

# This section is optional. Add Scrypted to the drawer within the HA dashboard for quick access.
panel_iframe:
  scrypted:
    title: "Scrypted"
    icon: mdi:memory
    url: "/api/scrypted/28d12b0b97cd99c3f0808cb7a78d08ef/"
```

## Scrypted NVR Card Setup

[Scrypted NVR provides Home Assistant cards](https://github.com/koush/nvr.scrypted.app/wiki/Home-Assistant) that feature low latency playback and two way audio.

1. Install the Scrypted NVR plugin in Scrypted.
2. Then add the following `Webpage Card` in Home Assistant (adjusting token and `24` as necessary):

```yaml
type: iframe
# Replace "24" with the id of your camera in Scrypted. The id is visible in the address bar in the browser.
url: >-
  /api/scrypted/28d12b0b97cd99c3f0808cb7a78d08ef/endpoint/@scrypted/nvr/public/#/iframe/24
aspect_ratio: '16:9'
```
