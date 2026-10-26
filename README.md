# DM Companion

A local web app that talks to Foundry VTT.

```
web UI (localhost:4000)  <-ws->  Python server  <-ws->  Foundry module (GM's browser)
```

## Install

### Prerequisites

- Python **3.9 or newer**, with `pip` and `venv` (a currently supported Python release is recommended).
- Internet access to install Python dependencies. The web UI also loads libraries and fonts from CDNs.
- Foundry VTT for scene/combat control. The development environment uses Foundry 14 and D&D 5e 6.0.6; other versions are not yet verified by a release test matrix.

Download or clone this repository, then open a terminal in its directory.

### macOS / Linux

```sh
python3 setup_env.py
./run.sh
```

### Windows (PowerShell)

Install Python from python.org, including the Python launcher, then run:

```powershell
py -3 setup_env.py
.\.venv\Scripts\python.exe server\server.py
```

No environment activation or PowerShell execution-policy change is required.
If `py` is unavailable but `python --version` shows Python 3.9 or newer, use
`python setup_env.py` instead.

Setup creates a project-local `.venv`, installs the pinned server dependency from
`requirements.txt`, and checks dependency compatibility. It can be rerun after
updating the project; it does not delete campaign data. Transitive dependencies
are resolved by pip for your Python version and platform, not locked byte-for-byte.

### Connect Foundry

1. Copy the contents of `foundry-module/` into `<Foundry User Data>/Data/modules/dm-companion/`.
   The resulting folder must contain `module.json` directly, not another `foundry-module` folder.
   You can find the User Data path in Foundry's configuration.
2. Restart Foundry if it was running, open your world **as GM**, and enable
   **DM Companion Bridge** in Manage Modules.
3. With the companion server running, open http://localhost:4000.

For this initial setup, use Foundry in a browser on the same computer at a
`localhost` or `127.0.0.1` address. Hosted/remote Foundry is not covered by these
instructions. The module defaults to `ws://localhost:4000/ws/foundry`.

Stop the companion server with Ctrl+C. Start it again with the platform's launch
command above; setup is only needed initially or when dependencies change.
Local app data lives in `data/` by default; preserve that directory when updating.

### Troubleshooting

- **Python not found / too old:** install a supported Python release, reopen your
  terminal, and check `python3 --version` (Windows: `py -3 --version`).
- **`venv` or `ensurepip` missing on Linux:** install your distribution's Python
  venv package (often `python3-venv` on Debian/Ubuntu), then rerun setup.
- **Dependency download fails:** check your internet connection and pip's error
  output, then rerun setup.
- **Environment breaks after moving the project or upgrading Python:** remove
  only the project's `.venv` directory and rerun setup. Do not remove `data/`.
- **`./run.sh` permission denied:** use `sh run.sh`.
- **Port 4000 already in use:** check whether DM Companion is already running.
  To use another port, set `DMC_PORT` before launching and update the bridge's
  WebSocket URL in Foundry's module settings to match.
- **Foundry disconnected:** confirm the module is enabled, you are logged in as
  GM, and Foundry is opened using a local address. Reload Foundry after module updates.
- **No vault notes:** installation does not configure your campaign vault.
  The current default is `~/Documents/Lysoria`; `DMC_VAULT_DIR` overrides that root,
  but session notes currently need to be under `Story/Act 1/Sessions`.

## Layout
- `server/server.py` — aiohttp server; serves the UI and relays messages
- `web/index.html` — the web UI
- `foundry-module/` — the Foundry module (symlinked into Foundry's `Data/modules/dm-companion`)

## Adding a command
1. Add a function to `COMMANDS` in `foundry-module/scripts/bridge.js`
2. Send `{type: "command", requestId, command, args}` from the UI
3. Reload Foundry (F5) to pick up module changes

## Features
- Scene browser: click a scene to activate it in Foundry; star scenes to pin them at the top
- Initiative tracker: turns, initiative, HP/damage, hide/defeated, custom entries
