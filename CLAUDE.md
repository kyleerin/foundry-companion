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
- `web/index.html` — single-file UI. Tailwind v4 browser CDN + daisyUI 5 CDN, custom `lysoria` dark fantasy theme (Cinzel / EB Garamond). No build step. Views registered in `VIEWS` (`scenes`, `initiative`, `encounters`, `players`, `npcs`, `notes`, `clocks`, `showcase`).
- `foundry-module/` — Foundry module `dm-companion`, symlinked to `~/Library/Application Support/FoundryVTT/Data/modules/dm-companion`. `scripts/bridge.js` connects only when the user is GM, pushes scenes/combat on hooks (debounced), and runs `COMMANDS`.

## Environment
- Foundry v14 (14.369), dnd5e system 6.0.6, Foundry on port 30000
- Worlds: `cressidia` (main campaign), `vecna-eve-of-ruin`
- No node or pdftotext installed

## Protocol
- UI → server: `{type:"command", requestId, command, args}` (relayed to Foundry), `{type:"toggleFavorite", sceneId}`, `{type:"setClocks", clocks}`, `{type:"setShowcase", showcase}`
- Foundry → server: `hello` (world, worldId, user, origin, version), `scenes`, `combat`, `result`
- Server → Foundry: `command`, `clocks`, `showcase` (on hello and on change)
- Server → UI: `state` snapshot on connect/changes, `scenes`, `combat`, `favorites`, `result`, `clocks`, `showcase`
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
- Initiative tracker: start/next/prev/end, roll NPCs/all, edit initiative, HP bar + damage/heal, hide, defeated, remove, custom entries (no token/actor); Party quick-add panel (players from `Players/`, add one or all, greyed once in combat)
- Encounters: pick a session note from `~/Documents/Lysoria/Story/Act 1/Sessions` (`DMC_VAULT_DIR`), shows the `[[links]]` under its `Encounters` heading as collapsible cards (`GET /api/sessions`, `/api/encounters?session=`). Works without Foundry.
- Session picker in the header, right of the Actions menu (shared by all views, saved in localStorage). Notes view renders the selected session note (`GET /api/note?session=`).
- `[[links]]` in rendered notes open the linked vault note in a right-side drawer (`GET /api/vault-note?target=`); links inside the drawer stack with a back button, `#Heading` links scroll to the heading, Esc closes. Links to NPC notes (in Notes, Encounters and the drawer) get an image icon that adds the NPC's artwork to the showcase.
- Players: a card per note under `Players/` with player name and class (from the `Player Dashboard` note, else a `# Rob - Dana` / `## Chris` / `**Chase**` line), Class/Role and open `- [ ]` items under "Active" headings; Player Dashboard button; click opens the drawer (`GET /api/players`). Re-reads on view open and window focus.
- NPCs: searchable cards for every note under `NPCs/` (race, occupation, faction, location or a summary line), click opens the note in the drawer (`GET /api/npcs`); image button toggles the matching actor portrait in the Showcase (`findArtwork` to add, removes when already shown; also on player cards); sync button creates/updates a dnd5e `npc` actor (`GET /api/npc?target=` parses AC, HP, CR, speed, size/type/alignment, abilities; `syncNpc` writes the note as biography, overwrites only parsed fields, new actors go in an `NPCs` actor folder; the note's first embedded vault image (`GET /api/vault-file?path=`) is uploaded to `worlds/<id>/dm-companion/` and set as portrait/token only when the actor still has the default image); swords button adds the NPC to initiative (`combatAddByName`: uses the world actor with that name, its token on the current scene if placed, else a plain entry). Re-reads the vault when the view opens or the window regains focus.
- Clocks: progress clocks (4/6/8/12 segments), click a segment or +/- to tick, rename inline, delete. Stored in `data/clocks.json` (shared across worlds, works without Foundry); UI sends `{type:"setClocks", clocks}`, server validates and broadcasts `clocks` (also to Foundry). Eye toggle per clock: visible clocks are saved by the bridge in the `dm-companion.clocks` world setting and drawn as a top-right overlay (left of the sidebar) on every Foundry client (players included).
- Showcase: artwork shown in Foundry, all at once. `data/showcase.json` holds `{items: [{id, name, src, shown}], layout: "column"|"row", view: "corner"|"fullscreen"}`; page toggles shown/hidden, reorders, removes, switches Row/Column and Corner/Full screen, Party panel toggles each player character's artwork (Show all adds every one). On this page the header search drops down matching players and NPCs; Enter (arrows to move) or a click adds and shows their artwork. The bridge saves shown items + layout in the `dm-companion.showcase` world setting; every client draws them under the clocks (collapse per client, click to enlarge), or in full screen over everything (close per client; switching view reopens it).
- Actions menu: refresh from Foundry, add selected tokens to combat, pause/unpause, open Foundry, clear artwork from Foundry (hides all showcase items)

Ideas backlog: `~/Documents/Lysoria/project_ideas.md`.
