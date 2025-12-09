# Scrypted Custom Component for Home Assistant

The Scrypted Custom Component for Home Assistant adds support for managing Scrypted from your Home Assistant Dashboard, and creation of Scrypted NVR cards.

<img width="100%" alt="image" src="https://github.com/koush/ha_scrypted/assets/73924/b76b239a-a61a-451a-84aa-1d3621594a68">

Visit the [Scrypted Documentation](https://docs.scrypted.app/home-assistant.html) for setup instructions.

## Development

### Using Dev Container (Recommended)

The easiest way to develop is using the included dev container:

1. Install [VS Code](https://code.visualstudio.com/) and the [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)
2. Open this repository in VS Code
3. Click "Reopen in Container" when prompted (or run the command manually)
4. Wait for the container to build and dependencies to install
5. Home Assistant will start automatically at http://localhost:8123

The dev container automatically:
- Installs all dependencies
- Sets up pre-commit hooks
- Symlinks `custom_components/scrypted` into the HA config
- Configures debug logging for the integration

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

# Run linting
ruff check custom_components tests
pylint custom_components
```
