# Release validation record

This is an evidence log, not a blanket support claim. A configured CI job is not
a passing result. No public release, push, or remote tag was performed during
this validation work.

## Fresh installation

Run from the repository root:

```sh
python3 tools/validate_install.py
```

Windows: `py -3 tools/validate_install.py`.

The script copies only application/setup/example files into a disposable
`dist/fresh-install-*` directory, creates a new virtual environment, runs setup
twice, checks that existing data survives, and starts its own server on port 4100.
It exercises HTTP and UI WebSocket behavior both without a vault and with the
fictional sample. It fails if port 4100 is occupied; it does not stop an existing
server. It removes its temporary copy afterward.

This verifies dependency installation and a direct Python launch, not Foundry
integration or every OS shell/launcher. `run.sh` and the documented PowerShell
launch should also be tried by a human before release.

| Platform | Python | Result |
| --- | --- | --- |
| macOS 26.7.1, arm64 | 3.9.6 | Passed fresh and repeated setup, `pip check`, data preservation, vaultless/sample HTTP and WebSocket smoke |
| Windows | Not run locally | Pending a real Windows CI run and manual installation |
| Linux | Not run locally | Pending a real Linux CI run and manual installation |

The macOS run resolved aiohttp 3.13.5, aiohappyeyeballs 2.6.1, aiosignal 1.4.0,
async-timeout 5.0.1, attrs 26.1.0, frozenlist 1.8.0, idna 3.20, multidict 6.7.1,
propcache 0.4.1, typing-extensions 4.16.0, and yarl 1.22.0. Setup uses a pinned
aiohttp but does not fully lock transitive dependencies. Python 3.9 is a
compatibility floor, not a recommendation to use an end-of-life interpreter.

## Documentation/examples

- The guide's three screenshots were generated with Playwright 1.58.2 / Chromium
  using fictional intercepted responses; no live Foundry data was captured.
- The sample vault API test checks encounter loading fields, NPC stats, player
  mapping/tasks, relationship nodes, improv tables, and every wikilink.
- Backup/restore procedures are documented; a real Foundry backup restore has
  not been performed as part of these checks.

## Foundry and system compatibility

Installed manifests confirm Foundry 14.369 and dnd5e 6.0.6. No live Foundry server
was reachable on port 30000, so integration is **pending**, not passed.
The module no longer advertises Foundry 13 or an untested `verified` version.
See the [disposable-world checklist](FOUNDRY_VALIDATION.md) before release.
