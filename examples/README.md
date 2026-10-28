# Try the Lantern Quay sample

This small, original fictional campaign demonstrates the supported note formats.
All text is covered by the repository MIT license. It contains no purchased
adventure content, real player information, or artwork.

## Configure

1. Back up any existing root `config.json`.
2. Copy `examples/sample-config.json` to the repository root as `config.json`.
   Paths are relative to the repository root, not to this file.
3. Restart the companion, open its UI, and select
   **Session 1 - The Missing Lantern**.
4. Visit Notes and Encounters; follow Mira Reed's link. Check Players, NPCs,
   Map, and Improv. These work without Foundry.

Do not copy the sample config over a real configuration without saving it first.
Alternatively, copy `sample-vault/` anywhere and set `vault_dir` to that location.
Obsidian is optional; any Markdown editor works.

## Optional Foundry exercise

Use a disposable dnd5e test world, not a running campaign.

1. Create a scene named exactly **Lantern Quay**. A blank scene is sufficient.
2. Create an NPC actor named exactly **Mira Reed** and a character actor named
   exactly **Tavi Finch**. Give Mira a non-default portrait from artwork you own
   or from Foundry's bundled icons. No portrait is shipped with this sample.
3. Enable the bridge and connect as GM. In Encounters, expand
   **A Light at the Quay** and click **Load encounter**.
4. Verify that Lantern Quay becomes active and Mira's portrait is added without
   clearing other showcase items. No combat or tokens should be created.
5. Try NPC sync on Mira only in this test world. The fictional, minimal stats
   demonstrate parsing, not a balanced or complete published stat block.

If the actor or its artwork is missing, loading reports an error. Merely having
an NPC note does not satisfy the existing-actor/artwork requirement. Omitting
the `NPCs` line is appropriate when you only want scene activation.

## Files and expected behavior

| File/folder | Demonstrates |
| --- | --- |
| `Sessions/` | Session picker and encounter links |
| `Encounters/` | Explicit Scene/NPCs fields, metadata, story links |
| `NPCs/` | Card fields, basic stat parsing, relationships |
| `Players/` | Dashboard player/class mapping and active checklist |
| `Factions/`, `Locations/` | Typed map nodes and wikilinks |
| `improv.md` | Single-column and roll-twice tables |

Only open tasks under the player's Active heading appear on the card. The map
should include four nodes (Mira, Tavi, Lantern Keepers, Lantern Quay).
Restore your saved config and restart when finished. Sample notes do not contain
or modify Foundry documents; any test-world changes must be removed in Foundry.
