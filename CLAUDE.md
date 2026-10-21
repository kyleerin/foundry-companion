# CLAUDE.md

## Response Style
- Be minimal and concise
- Just do what is asked, nothing more

## Overview
Local web app for running D&D 5e (2024) sessions in Foundry VTT. Companion to the Obsidian campaign vault at `~/Documents/Lysoria`.

```
web UI (localhost:4000) <-ws /ws/ui-> server/server.py <-ws /ws/foundry-> Foundry module (GM's browser)
```

- `server/server.py` — Python 3.9 + aiohttp (in `.venv`). Serves `web/`, relays messages, keeps last scenes/combat state, stores per-world data in `data/` (gitignored). Localhost origins only.
- `web/index.html` — single-file UI. Tailwind v4 browser CDN + daisyUI 5 CDN, custom `lysoria` dark fantasy theme (Cinzel / EB Garamond). No build step. Views registered in `VIEWS` (`scenes`, `initiative`, `encounters`, `players`, `npcs`, `notes`).
- `foundry-module/` — Foundry module `dm-companion`, symlinked to `~/Library/Application Support/FoundryVTT/Data/modules/dm-companion`. `scripts/bridge.js` connects only when the user is GM, pushes scenes/combat on hooks (debounced), and runs `COMMANDS`.

## Environment
- Foundry v14 (14.369), dnd5e system 6.0.6, Foundry on port 30000
- Worlds: `cressidia` (main campaign), `vecna-eve-of-ruin`
- No node or pdftotext installed

## Protocol
- UI → server: `{type:"command", requestId, command, args}` (relayed to Foundry), `{type:"toggleFavorite", sceneId}`
- Foundry → server: `hello` (world, worldId, user, origin, version), `scenes`, `combat`, `result`
- Server → UI: `state` snapshot on connect/changes, `scenes`, `combat`, `favorites`, `result`
- UI `run(command, args, {key, success})` tracks pending state and shows toasts

## Adding a feature
1. Foundry action: add to `COMMANDS` in `bridge.js`; push new data with a hook + debounced send
2. Server: handle new message types in `foundry_ws` / `ui_ws`; persistent data via `JsonStore`
3. UI: add a render function and register it in `VIEWS` + the nav menu
4. The user must reload Foundry (F5) after module changes; refresh the web app after UI changes; restart the server after server changes

## Running & testing
- `./run.sh` starts the server; the user usually has it running on port 4000. Never kill it to test.
- Test on another port with throwaway data: `DMC_PORT=4100 DMC_DATA_DIR=<scratch dir> .venv/bin/python server/server.py`, drive it with an aiohttp client faking the Foundry and UI sockets.
- Syntax checks: `.venv/bin/python -m py_compile server/server.py`; JS via `osascript -l JavaScript -e 'new Function(...)'`.
- If the server must be restarted after a server change: `nohup ./run.sh > /tmp/dm-companion.log 2>&1 &`

## Features
- Scene browser (cards, folders, search), click to activate, favorites pinned at top (per world, `data/favorites.json`)
- Initiative tracker: start/next/prev/end, roll NPCs/all, edit initiative, HP bar + damage/heal, hide, defeated, remove, custom entries (no token/actor)
- Encounters: pick a session note from `~/Documents/Lysoria/Story/Act 1/Sessions` (`DMC_VAULT_DIR`), shows the `[[links]]` under its `Encounters` heading as collapsible cards (`GET /api/sessions`, `/api/encounters?session=`). Works without Foundry.
- Session picker in the header, right of the Actions menu (shared by all views, saved in localStorage). Notes view renders the selected session note (`GET /api/note?session=`).
- `[[links]]` in rendered notes open the linked vault note in a right-side drawer (`GET /api/vault-note?target=`); links inside the drawer stack with a back button, `#Heading` links scroll to the heading, Esc closes.
- Players: a card per note under `Players/` with player name and class (from the `Player Dashboard` note, else a `# Rob - Dana` / `## Chris` / `**Chase**` line), Class/Role and open `- [ ]` items under "Active" headings; Player Dashboard button; click opens the drawer (`GET /api/players`). Re-reads on view open and window focus.
- NPCs: searchable cards for every note under `NPCs/` (race, occupation, faction, location or a summary line), click opens the note in the drawer (`GET /api/npcs`); swords button adds the NPC to initiative (`combatAddNpc`: links a world actor with the same name, else a plain entry). Re-reads the vault when the view opens or the window regains focus.
- Actions menu: refresh from Foundry, add selected tokens to combat, pause/unpause, open Foundry

Ideas backlog: `~/Documents/Lysoria/project_ideas.md`.
