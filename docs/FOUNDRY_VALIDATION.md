# Foundry / dnd5e release gate

## Current evidence and scope

The installed application manifest reports **Foundry 14.369** and the installed
system manifest reports **dnd5e 6.0.6** (whose own minimum is Foundry 14.367).
These agree with the documented development environment. A manifest inspection
verifies installed versions, **not functional compatibility**.

During this validation pass, no server answered at `http://localhost:30000`.
No world was started, changed, or upgraded. The target release combination is
Foundry **14.369 + dnd5e 6.0.6**, local HTTP, one GM connection. It remains pending
the live checks below.

The bridge manifest now has minimum Foundry 14.369 and omits `verified` until a
release integration pass exists. This deliberately removes the untested Foundry
13 claim. Foundry may warn that the module is unverified; do not interpret
installability on newer versions as a support guarantee. No other system,
Foundry version, hosted deployment, or multi-GM setup is certified.

## Run in a disposable world

Record OS, browser/version, companion commit/tag, module version, Foundry build,
and dnd5e version. Use the [fictional sample](../examples/README.md), owned or
bundled artwork, and a separate companion data directory on port 4100.
Never use this checklist to test destructive actions in a live campaign.

| Check | Expected result | Status |
| --- | --- | --- |
| Extract/install module ZIP | `module.json` at module root; recognized in Setup | Pending |
| Manifest URL install | Published manifest and versioned ZIP resolve; correct version installed | Pending publication |
| Enable module as GM | Companion connects; world/user and scene list appear | Pending |
| Player client | No command socket; clocks/showcase render | Pending |
| Activate scene / favorites | Scene activates; favorites survive reload and are per-world | Pending |
| Start/add/roll/advance/end combat | Foundry and companion agree; HP/initiative edits persist | Pending |
| Party quick-add | Matching character added; existing combatants not duplicated | Pending |
| NPC sync | Name/type and parsed dnd5e fields correct; missing fields preserved | Pending |
| NPC image upload | Owned image uploaded; custom artwork not overwritten | Pending |
| Encounter load | Exact scene activated, cast artwork added, old artwork preserved; no combat/tokens | Pending |
| Missing scene/actor/artwork | Clear error; no misleading success | Pending |
| Clocks | Visibility/progress match on GM and player clients | Pending |
| Showcase | Row/column, corner/fullscreen, local close, and clear behave correctly | Pending |
| Reconnect | Close/reopen GM tab and restart test companion; state resynchronizes | Pending |
| World switch | Favorites isolated; clocks/showcase behavior reviewed before connecting next world | Pending |
| Version update | Install prior release, update through manifest, reload clients; data retained | Pending publication |
| Restore | Restore disposable backup and verify actors/uploads/notes/companion state | Pending |

For each failure, record exact steps, expected/actual results, and a redacted error.
Do not mark a row passed based on a server mock or reading API documentation.
When all required rows pass, record the evidence here and add the exact tested
Foundry version to the manifest's `compatibility.verified` field. Broaden the
minimum version only after testing that version with a compatible dnd5e release.
