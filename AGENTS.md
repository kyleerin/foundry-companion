# Agent instructions

Read and follow `CLAUDE.md` for project architecture, workflows, and the canonical **Encounter note format**.

When writing vault encounter notes, include explicit loading fields before the first `##` heading:

```markdown
# Encounter - Example

**Scene**: Exact Foundry Scene Name
**NPCs**: [[Slug Marrow]], [[Lady Niyren]]
```

`Scene` must identify the Foundry scene (exact name or ID); NPC wikilink targets identify existing Foundry actors with artwork. Do not infer the scene from `Location` or the cast from incidental story links. Omitted fields leave the scene unchanged or add no portraits, respectively.

The encounter card's **Load encounter** action activates the scene and adds NPC portraits to the showcase, preserving existing artwork. It does not start combat or place tokens.
