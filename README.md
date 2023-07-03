# Scrypted Custom Component for Home Assistant

The Scrypted Custom Component for Home Assistant adds support for managing Scrypted from your HA Dashboard and creating Scrypted NVR cards.


<img width="100%" alt="image" src="https://github.com/koush/ha_scrypted/assets/73924/7c6fdd6a-8722-4c82-8581-632cdfa4476d">

## Home Assistant Setup

1. Ensure HACS is installed - see [HACS](https://hacs.xyz) if not
2. From the HACS menu, select 'Integrations'
3. Using the overflow (3 dots) menu on the top right of the screen, select 'Custom repositories'
4. Add [this repository's URL](https://github.com/koush/ha_scrypted) and choose 'Integration' for category then 'Add'
5. You may need to restart Scrypted and/or refresh the page
6. Go to `Settings > Devices & Services > Add New` and select Scrypted
7. Enter the host (e.g. '192.168.1.200:10443'), username, and password for your Scrypted server, as well as a name and icon for the sidebar link in the Home Assistant menu.

After restarting Home Assistant you should see Scrypted in the Sidebar menu.

## Scrypted NVR Card Setup

You can create Home Assistant cards for Scrypted NVR cameras. 
<br>Scrypted NVR cards feature low latency playback and some cameras feature two-way audio.
Note that this requires a valid Scrypted NVR license.

### Obtain the Scrypted token and ID
1. Install the Scrypted NVR plugin in Scrypted.
2. From within Home Assistant, , go to `Settings > Devices & Services` and select the `Entities` page
3. Search for 'sensor.scrypted' and select the Scrypted token entity
<br><img width="300" alt="image" src="https://github.com/koush/ha_scrypted/assets/73924/a8a44b2d-c1c6-4acd-bc33-11090a892858">
5. Record the `token` value:
<br><img width="300" alt="image" src="https://github.com/koush/ha_scrypted/assets/73924/83239aef-036b-4977-a5eb-23dd8b2d5eb0">
5. Open the Scrypted web page.  Don't use the Scrypted sidebar menu item from within Home Assistant for this part of the setup.
6. Enter the Management Console and open a camera page to display the camera details.
7. Note the `id` visible in the address bar in the browser at the end of the URL. E.g. `32` below:
<br><img width="300" alt="image" src="https://github.com/koush/ha_scrypted/assets/73924/813e4218-3050-4c45-a5ad-db40ff60a159">
8. Record the camera `id` from the URL displayed. 

### Create a card in Home Assistant
1. Edit a Home Assistant Dashboard to display '+ ADD CARD'
2. Search for and add a 'Webpage Card'
3. Switch to the Code Editor and replace it's contents with the following:

```yaml
type: iframe
# Replace <id> with the id of your camera in Scrypted.
# Replace <token> with the value from the token entity in Home Assistant.
url: >-
  /api/scrypted/<token>/endpoint/@scrypted/nvr/public/#/iframe/<id>
aspect_ratio: '16:9'
```
4. Replace <token> with the token you obtained earlier
9. Replace <id> with the ID you obtained earlier
10. Click 'Save'
