# Backups, upgrades, and troubleshooting

## Back up before a session or upgrade

Keep a dated copy outside the application directory. Do not commit private data
or backups to this repository.

1. Stop **your own** companion process with Ctrl+C so its JSON files cannot change
   during the copy. Do not stop someone else's running session.
2. Copy the entire `data/` directory, or the directory selected by `DMC_DATA_DIR`.
3. Copy root `config.json`, if present. Record any `DMC_VAULT_DIR`, `DMC_DATA_DIR`,
   and `DMC_PORT` environment overrides separately; they are not stored in JSON.
4. Back up the vault, including embedded images. The companion does not include
   these in its own data files.
5. Follow Foundry's backup procedure for user data/worlds while the world is
   stopped. Include uploaded files under `worlds/<world-id>/dm-companion/`.
6. Record companion/module version, Foundry version, and dnd5e version alongside
   the backup. Keep at least one known-working version of the application.

Do not rely on `.venv` as a backup: recreate it from `requirements.txt`. Browser
local storage only holds preferences, not your vault or world. Clocks/showcase
are saved in both the companion and Foundry overlay settings, but the companion
sends its stored values when the bridge connects. Back up both sides.

### Restore and verify

1. Work in a separate test directory/world first. Keep the current data copy.
2. Restore matching application code, `config.json`, companion data, vault, and
   Foundry world/uploads. Adjust absolute paths if the machine changed.
3. Rerun `setup_env.py`, then start the companion. For a rehearsal alongside a
   running app, use port 4100 and a **copied** data directory:
   ```sh
   DMC_PORT=4100 DMC_DATA_DIR=/path/to/restored-data .venv/bin/python server/server.py
   ```
   PowerShell:
   ```powershell
   $env:DMC_PORT = "4100"
   $env:DMC_DATA_DIR = "C:/path/to/restored-data"
   .\.venv\Scripts\python.exe server\server.py
   ```
4. Open `http://localhost:4100`; verify notes, clocks, and showcase. Only connect
   a disposable Foundry world, with its bridge URL changed to
   `ws://localhost:4100/ws/foundry`. Verify favorites under the intended world.
5. Close the test process and undo test port/URL environment changes before
   returning to the normal setup.

Malformed JSON currently falls back to default data at startup. If clocks or
favorites unexpectedly disappear, stop and preserve the original files before
making edits in the UI (which can overwrite them). Inspect/restore the backup;
do not assume empty data means the backup contained nothing.

## Upgrade without losing data

1. Read the release notes and confirm the Foundry/dnd5e versions match the tested
   combination. Back up as above.
2. Close the companion and shut down the test/world session before replacing code.
3. Download/check out the desired companion release. Preserve `config.json`,
   your vault, and `data/` (or external paths). If using Git, inspect local edits
   first; do not reset or overwrite them blindly.
4. Run `python3 setup_env.py` (Windows: `py -3 setup_env.py`) to update/check
   dependencies, then launch using the platform command in the README.
5. Update the Foundry module to the **matching release** through Foundry Setup,
   or manually replace its module files. The module updater does not update Python.
6. Reload Foundry clients and the companion page. Check connection, one scene
   activation, an encounter load, a note link, and overlay visibility in a test world.

If an upgrade fails, stop the app and restore the previous code **and its matching
data/world backup**. Recreate the environment for that version. Do not downgrade
Foundry itself against a world that has already been migrated; follow Foundry's
restore guidance. No automatic rollback/migration tool is provided.

## Connection troubleshooting

| Symptom | Check |
| --- | --- |
| Companion page does not open | Start the Python server; check its terminal output and port. Use `http://localhost:4000`, not HTTPS. |
| Server indicator is disconnected | Refresh the page, check whether the process exited, and inspect browser console/network errors. |
| Server connected, Foundry disconnected | Enable the module in the world, log in as GM, open Foundry from a localhost address, and reload Foundry. |
| Still disconnected after changing ports | Set the GM client's **DM Companion server URL** to `ws://localhost:<port>/ws/foundry`. The companion page must use the same port. |
| Repeated connect/disconnect | Close duplicate GM Foundry tabs. Only one bridge connection is supported; a new one replaces the old one. |
| Origin not allowed / mixed-content errors | Use local HTTP Foundry and companion URLs. Do not relax origin checks or expose the server to work around hosted/HTTPS restrictions. |
| Command error or timeout | Verify the Foundry connection and selected world, inspect the error toast, and check Foundry state before retrying a mutating action. |
| Scene/NPC not found | Use exact unique Foundry names or scene IDs; notes do not automatically create scenes. Ensure the NPC actor has non-default artwork. |

## Content and display troubleshooting

| Symptom | Check |
| --- | --- |
| Empty session list | Configure the vault; session `.md` files must be directly inside `sessions_dir`. Restart after config changes. |
| Empty encounters | Add wikilinks under `## Encounters` in the selected session. Check the linked files exist. |
| Wrong linked note | Prefer vault-relative wikilinks and avoid duplicate filenames; name-only resolution can be ambiguous. |
| Notes did not refresh | Reselect the session. NPC/player/map/improv views reload when reopened or focused. |
| NPC stats incomplete after sync | Review the parsed field formats in the sample. Unrecognized fields are not imported. Check the actual actor sheet. |
| Player/class missing | Match the character filename to `Player Dashboard.md`; use `## Player` then `**Character - class**`. |
| Blank or unstyled page / map fails | Check internet/CDN access and browser console. Fonts, styles, Markdown, and the map currently depend on external URLs. A warm browser cache is not offline support. |
| Art missing after a world switch | Artwork paths may belong to the old world. Remove stale items and add portraits from the new world. |
| Old clocks/art appear in another world | Clocks/showcase are shared by companion data directory. Review/hide them before switching; use separate data directories for separate campaigns. |

Never paste a real vault, actor biography, private artwork URL, configuration, or
full browser storage into a public issue. A useful report includes OS, Python,
companion/module, Foundry and system versions; the exact action and error; and a
minimal fictional reproduction. Redact paths and personal/campaign details.

## Separating campaigns

For now, keep one running companion and one GM world connection. If campaigns
must not share clocks/showcase, stop your companion and restart it with a different
`DMC_DATA_DIR` and vault configuration for the next campaign. Use descriptive,
backed-up directories. Do not reuse the same data directory in two server processes.
Favorites are keyed by world ID/name within a data directory, but clocks/showcase
are not. World IDs can also collide across separate Foundry installations.
