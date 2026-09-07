# Scrypted Custom Component for Home Assistant

The Scrypted Custom Component for Home Assistant adds support for managing
Scrypted from your Home Assistant Dashboard, and creation of Scrypted NVR
cards.

![Scrypted Dashboard](https://github.com/koush/ha_scrypted/assets/73924/b76b239a-a61a-451a-84aa-1d3621594a68)

Visit the [Scrypted Documentation](https://docs.scrypted.app/home-assistant.html)
for setup instructions.

## Device entities

When *Create entities for Scrypted devices* is enabled (default), the
integration connects to the Scrypted server over its engine.io RPC API and
creates entities for discovered devices. By default only **Camera** and
**Doorbell** device types are mirrored; pick additional Scrypted device types
in the integration options.

- **Camera** — snapshots for `VideoCamera` devices. Live streaming is
  intentionally not supported; use the Scrypted NVR cards for live view.
- **Binary sensor** — motion, doorbell button, sound, occupancy, flood, entry,
  power, connectivity, tamper, charging, sleeping.

State updates are pushed; no polling. Entities reconnect automatically if the
server restarts.

## Development

### Using Dev Container (Recommended)

The easiest way to develop is using the included dev container:

1. Install [VS Code](https://code.visualstudio.com/) and the
   [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)
2. Open this repository in VS Code
3. Click "Reopen in Container" when prompted (or run the command manually)
4. Wait for the container to build and dependencies to install
5. Home Assistant will start automatically at <http://localhost:8123>

The dev container automatically:

- Installs all dependencies
- Sets up pre-commit hooks
- Creates a `config/` directory (git-ignored) for Home Assistant and symlinks
  `custom_components` into it
- Configures debug logging for the integration
- Starts debugpy on port 5678 (attach with the provided VS Code launch config).
  To make Home Assistant wait for the debugger on startup, copy
  `.devcontainer/.env.example` to `.devcontainer/.env` and set
  `ENV_DEBUGPY_WAIT=true`.

### Local Development

To set up a local development environment:

```bash
# Create and activate virtual environment
python3.14 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements_dev.txt

# Install pre-commit hooks
pre-commit install

# Run tests
pytest

# Run linting and formatting checks
ruff check .
ruff format --check .
```
