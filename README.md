# DM Companion

A local web app that talks to Foundry VTT.

```
web UI (localhost:4000)  <-ws->  Python server  <-ws->  Foundry module (GM's browser)
```

## Run
1. `./run.sh` — starts the server at http://localhost:4000
2. Open your world in Foundry **as GM**, with the **DM Companion Bridge** module enabled
3. Open http://localhost:4000

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
