# Scrypted Custom Component for Home Assistant

The Scrypted Custom Component for Home Assistant adds support for Scrypted NVR cards.
This custom component is unnecessary if Scrypted was installed as a Home Assistant OS addon.

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
# Change the IP as necessary.
# Port 10443 is Scrypted's default SSL listener port
# in Scrypted and should typically *NOT** be changed.
scrypted:
  host: 192.168.2.124:10443

# This section is optional.
# Add Scrypted to the drawer within the HA dashboard for quick access.
panel_iframe:
  scrypted:
    title: "Scrypted"
    icon: mdi:memory
    url: "/api/scrypted/28d12b0b97cd99c3f0808cb7a78d08ef/"
```

## Scrypted NVR Card Setup

Add the following `Webpage Card` (adjusting token and `24` as necessary):

```yaml
type: iframe
# Replace "24" with the id of your camera in Scrypted. The id is visible in the address bar in the browser.
url: >-
  /api/scrypted/28d12b0b97cd99c3f0808cb7a78d08ef/endpoint/@scrypted/nvr/public/#/iframe/24
aspect_ratio: '16:9'
```
