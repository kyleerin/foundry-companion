# Release readiness handoff

## Working directory and branch

- The user's primary checkout is `/Users/kyle/Documents/dm-companion`.
- Work on `release/v1`. Completed implementation commits:
  - `4d48407` — Add reproducible local installation setup.
  - `b16201e` — Make campaign vault paths configurable and optional.
- Both commits were copied into the primary checkout and verified there.
- Nothing has been pushed or published. Step 3 is implemented locally (see below).
- The user wants edits visible in the primary checkout, not left in an isolated
  Delta worktree. Verify the actual working directory before editing. If the
  environment forces an isolated checkout, explain that limitation first and
  agree on how changes will reach the primary checkout.
- Read `AGENTS.md` and `CLAUDE.md` before working.

## Completed

### Step 1: Installation

- `setup_env.py` creates a local virtual environment, installs dependencies, and
  checks dependency compatibility.
- `requirements.txt` pins aiohttp to 3.13.5, retaining Python 3.9 support.
- `run.sh` reports missing environments/dependencies with setup instructions.
- README covers macOS/Linux/Windows setup, manual module installation, and
  troubleshooting. Transitive Python dependencies are not fully locked.

### Step 2: Campaign-independent configuration

- `config.example.json` documents the optional, gitignored `config.json`.
- Vault root and sessions/NPCs/players/factions/locations/improv paths are
  configurable. `DMC_VAULT_DIR` overrides the vault root.
- No implicit Lysoria default remains. Without a vault, vault-dependent features
  return empty results; Foundry controls, clocks, and showcase remain available.
- Invalid configuration fails startup; missing content folders are allowed.
- Nested player dashboard links and vault empty-state messages were updated.
- README includes migration instructions for the original campaign layout.

Validation already run: 12 tests passed, Python and JavaScript syntax checks
passed, and a vaultless HTTP/WebSocket smoke test passed on port 4100 using
temporary data. Earlier installation checks verified fresh and repeated setup
on macOS/Python 3.9. Windows/Linux and live Foundry integration remain untested.

## Next: Step 3 — Distributable Foundry module

The user explicitly requested this next.

Local implementation completed on `release/v1` in the primary checkout:

- `build_module.py` builds an allowlisted, reproducible module ZIP and standalone
  manifest in `dist/`, checks version/tag/URL agreement, and validates the archive.
- Manifest includes project, stable update, versioned download, and license links.
- `.github/workflows/module-release.yml` validates on PRs/branch pushes.
  Publication requires manual dispatch with an existing version tag and explicit
  `publish: true`; its default is false.
- README covers manifest/manual installation, updates, the separate Python app,
  local builds, and the future publication procedure. Release URLs are not
  represented as live.
- Validation: 4 packaging tests and 12 existing server tests passed; build with
  `--tag v0.1.0`, ZIP listing, and `git diff --check` passed. Ruby parsed the workflow
  YAML and checked triggers, publication default, and build dependency.
- GitHub Actions execution/actionlint and live Foundry install/update remain
  unverified. No running server was stopped, and no push/tag/release was performed.

Original step 3 checklist:

1. Inspect `foundry-module/module.json`, module assets, and repository release
   conventions. Current module ID is `dm-companion`, version is `0.1.0`.
   Repository remote was `git@github.com:kyleerin/foundry-companion.git`;
   verify before using it.
2. Add a repeatable ZIP build command with a valid Foundry package layout.
   Include required module files and license; exclude local configuration,
   campaign data, virtual environments, and development artifacts.
3. Add manifest project/install/update/download URLs using a consistent GitHub
   release asset convention. Keep module version, release tag, and ZIP URLs in
   agreement. Do not imply URLs are live before a release exists.
4. Add a release workflow that builds and validates the ZIP and manifest.
   Make the publication trigger explicit and document it.
5. Document installation via manifest URL, enabling the module in a world,
   updating it, and connecting it to the separately installed Python companion.
   Retain a manual installation path.
6. Validate archive contents, manifest references, version consistency, and
   workflow configuration. Test installation/update in Foundry if available;
   otherwise state that it remains unverified.
7. Do not push, tag remotely, or publish a release without explicit approval.

## Remaining readiness work

### Deferred follow-up and branch push

The user requested that remediation be documented for later and authorized
committing/pushing the current work on `release/v1` to `origin`. This authorizes
the branch push only, not a merge into `main`, remote tag, or published release.
Earlier no-push statements below describe the state before this authorization.

Resume with `docs/SECURITY_REVIEW.md` and `docs/DEPENDENCY_AUDIT.md`. Python 3.11+
and per-world clocks/showcase with explicit migration remain recommendations;
neither has been implemented. Security fixes, dependency updates, CDN/offline
work, Windows/Linux CI results, and live Foundry validation remain outstanding.
Do not treat the branch push or passing functional CI as release approval.

### Progress after step 3

Work continued in the primary checkout on `release/v1`, one commit per requested
item. No push, remote tag, or release was performed.

- `2a2651b`: committed step 3 packaging before starting later work.
- `dbba8e0`: full user guide with three real-browser fictional-data screenshots.
- `8909272`: fictional sample vault and API/wikilink validation.
- `4f5ec7d`: backup/restore, upgrades, and troubleshooting guide.
- `c929c86`: portable fresh-install check; macOS passed, Windows/Linux pending.
- `f3be5f0`: installed versions confirmed as Foundry 14.369 / dnd5e 6.0.6;
  live Foundry was unavailable. Narrowed minimum and removed untested `verified`.
- `0c9a0a9`: six-job OS/Python CI matrix and broader regressions. Locally,
  21 server tests, 4 packaging tests, and 7 Node tests passed.
- Security/world-data/CDN review: see `docs/SECURITY_REVIEW.md` and
  `docs/DEPENDENCY_AUDIT.md`. Confirmed release blockers remain open.

**Next decisions:** recommend Python 3.11+ to allow patched dependencies, and
per-world clocks/showcase with explicit migration. No support-floor or data
migration change was made without a decision. Fix confirmed security/state
findings, resolve CDN dependencies, run remote CI, and perform the disposable
Foundry checklist before release. The original readiness scope follows.

### Step 4: User-facing documentation and examples

- Expand the README into a complete guide to current features, with screenshots.
- Add a small fictional sample vault demonstrating supported note formats.
- Cover setup, configuration, backups, updates, and common connection problems.
- Ship no private campaign content, purchased adventure text, or unlicensed art.

### Step 5: Define and verify support

- Start with local Foundry, one GM connection, and a tested D&D 5e version.
- The documented development environment is Foundry 14.369 / dnd5e 6.0.6.
- The module currently advertises Foundry minimum 13 and verified 14; test
  compatibility or narrow those claims.
- Hosted/remote Foundry requires separate security and connection design.
  Do not simply expose the server publicly or relax origin checks.

### Before public release

- Have another GM follow only the README on a clean machine.
- Verify installation on Windows and Linux as well as macOS.
- Add CI and regression checks for connection/reconnection, command errors,
  vault access, persistence, and world switching.
- Review vault path handling, Markdown rendering, and command-bridge access.
- Decide/document whether clocks and showcase should remain shared across worlds;
  favorites are already per-world.
- Bundle frontend dependencies for offline reliability, or explicitly document
  internet requirements and pin CDN versions.
- Review dependency security and Python support before release.

## First milestone

Another GM can install the companion and module, configure a sample vault, and
load a sample encounter in about 15 minutes without the author's help.

Do not rewrite the application or add hosted support/desktop installers just to
reach that milestone. Never stop the user's running server to test; use port
4100 and throwaway data as described in `CLAUDE.md`.
