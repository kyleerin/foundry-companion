# Security, world-state, and offline review

Reviewed 2026-10-28 against `0c9a0a9`. **Not ready for public release.**
Findings below are open; this review does not silently change runtime behavior.
Tests used disposable files, aiohttp test servers, and browser-intercepted
fictional responses. No live world, private vault, or running companion was used.

## Intended trust boundary

The server binds to `127.0.0.1`. Browser WebSockets reject non-local origins,
but origin checks are not authentication: any local process can omit/spoof Origin,
and any page served from an allowed localhost origin can connect. The bridge
executes commands with the logged-in GM's authority. This is a trusted,
single-user local tool, not a hosted service or a multi-user authorization boundary.

The origin-rejection regression tests pass. Do not relax them, bind publicly,
forward the port, or put an unauthenticated proxy in front of this application.

## Release-blocking findings

### S1 — Vault Markdown can execute script in the companion

Locations: [Markdown rendering](../web/index.html#L998),
[inline rendering](../web/index.html#L1055),
[biography export](../web/index.html#L713), and
[encounter metadata](../web/index.html#L1804).

**Confirmed in Chromium.** An intercepted synthetic note containing an image
error handler set `window.auditMarker` to `"executed"` when Notes rendered.
The probe only changed this marker; it did not send Foundry commands or data.

`markdownHtml`, `inlineHtml`, and `biographyHtml` use Marked without sanitization.
Notes, encounters, drawer content, cards, relationship evidence, and improv
results feed HTML sinks. Encounter Location also inserts transformed Markdown
directly. Escaping wikilink attributes does not sanitize the rest of the note.

Impact: a malicious/shared/imported note can run in the companion origin, read
vault API responses, and access the command bridge. Foundry biography import is
another HTML trust boundary; Foundry-side handling was not tested.

**Required fix:** one vetted HTML sanitization policy used by every Markdown/
metadata HTML sink and biography export, with safe URL handling. Preserve
intentional wikilink data attributes and test them. Add browser regression cases
for event handlers, scriptable URLs, inline metadata, and imported biographies.
Use CSP as defense in depth, not as a replacement for sanitization.

Until fixed, use only trusted notes and do not treat imported Markdown as inert.

### S2 — Name-fallback resolution follows symlinks outside the vault

Locations: [note resolution](../server/server.py#L330) and
[file resolution](../server/server.py#L468).

**Confirmed with synthetic files.** A vault `linked.md` symlink to a sibling
`outside.md` was returned by `/api/vault-note?target=linked`; a `linked.png`
symlink likewise returned an outside file through `/api/vault-file`.

Direct-path checks resolve containment, but fallback `rglob` results in
`resolve_note` / `resolve_file` do not. Other recursive readers also need the
same policy, not a one-endpoint patch.

**Required fix:** apply canonical-path containment consistently before every
read, including sessions, NPC/player enumeration, graph building, image lookup,
and fallback resolution. Decide whether internal symlinks are allowed; reject
external targets and unsafe paths. Add direct/fallback/symlink tests on all OSes.
Do not rely on extensions or configured folder containment alone.

### S3 — HTTP data routes do not validate Host

Locations: [WebSocket-only origin guard](../server/server.py#L185) and
[HTTP routing](../server/server.py#L700).

**Confirmed at the server boundary.** Both synthetic vault requests returned
200 with `Host: untrusted.example` and `Origin: http://untrusted.example`.
Only WebSockets apply origin checks; HTTP has no Host guard.

Impact: missing DNS-rebinding defense for local HTTP data. Ordinary cross-origin
JavaScript is constrained by the browser's same-origin policy, but that is not
a substitute for Host validation. A full DNS-rebinding browser exploit was not
performed; browser private-network protections vary.

**Required fix:** consistent HTTP/WebSocket Host validation restricted to intended
loopback names/addresses; explicit browser-origin policy and tests for malformed
headers, IPv6, ports, and lookalike hosts. Consider a pairing/session credential
for command access if the trust model expands. Do not weaken loopback binding.

### S4 — Runtime dependency audit fails

`pip-audit 2.9.0` reported **23 advisories in two installed runtime packages**:
22 for aiohttp 3.13.5 and one for multidict 6.7.1. This is a dependency finding,
not proof every advisory is exploitable in this app. See the
[audit record](DEPENDENCY_AUDIT.md) for versions, IDs, and reproduction.

Reported fixes require aiohttp 3.14.4 and multidict 6.9.1 to cover this set.
Both packages declare Python >=3.10. Staying on the Python 3.9-compatible pins
does not address these findings.

**Recommendation:** raise the supported floor to Python 3.11+, update and lock
the runtime dependencies, rerun install/regression/browser checks on all platforms,
and add a dependency audit gate. This changes the setup/support promise and needs
an explicit decision; no dependency or Python-floor change was made in this review.

### S5 — Scene state survives world boundaries

Locations: [bridge hello handling](../server/server.py#L215) and
[disconnect handling](../server/server.py#L235).

**Confirmed over test WebSockets.** World A sent a scene list, disconnected, and
world B sent `hello`. The disconnect snapshot and world B's initial snapshot
still contained A's scenes. Combat is cleared on disconnect, but scenes are not;
replacement/hello also lacks a coherent reset rule.

**Required fix:** clear all world-derived transient state on disconnect,
replacement, and world identity change, and reject messages from superseded
connections. Add regression tests asserting the intermediate snapshots, not just
the eventual refresh. Do not show old scenes as if they belong to the new world.

## Shared-across-world data decision

| Data | Current behavior | Assessment |
| --- | --- | --- |
| Favorites | Keyed by world ID, falling back to world name | Isolated for ordinary worlds; IDs can collide across Foundry installations |
| Clocks | One file per companion data directory | Shared intentionally in current code |
| Showcase | One file per companion data directory | Shared; artwork can reference another world's paths |
| Foundry overlay settings | World-local copies of shown content | Companion sends its shared values on each hello |
| Browser preferences | Shared within the companion origin | View/session/map filters can outlive a campaign switch |

The persistence regression verifies per-world favorites and global overlays.
Visible clocks/artwork can therefore be sent to another world when its GM
connects, exposing spoilers; stale paths can fail or show the wrong content.

**Recommendation:** make clocks/showcase per-world before broad distribution,
with an explicit one-time migration/import for existing global data. Do not
silently copy old visible content into every world. Retaining global data is a
product choice only if prominently disclosed and accompanied by a safe
world-switch confirmation. This review documents current behavior without
changing the storage format or migrating user data.

Current workaround: use separate `DMC_DATA_DIR` values per campaign, one process
at a time, and review/hide overlays before connecting. See
[operations](OPERATIONS.md#separating-campaigns).

## CDN and offline dependencies

The companion's HTML loads:

| Dependency | Current reference | Consequence |
| --- | --- | --- |
| daisyUI CSS | jsDelivr `daisyui@5` | Floating major version |
| Tailwind browser runtime | jsDelivr `@tailwindcss/browser@4` | Floating major; runtime CSS compilation |
| Marked | jsDelivr `marked@12.0.2` | Exact version, but remote execution and no integrity attribute |
| Cytoscape | jsDelivr `cytoscape@3.30.2` | Exact version, but remote execution and no integrity attribute |
| Cinzel / EB Garamond | Google Fonts CSS and font hosts | External request and variable delivery |

**Confirmed cold-cache failure:** blocking all external requests in a fresh
Chromium context left `marked` and `cytoscape` undefined; opening Notes raised
`marked is not defined`. A cached page working offline is not reliable offline
support. Third-party JavaScript runs with the same UI privileges as local code.

**Recommendation:** bundle reviewed, exact-version JS/CSS/fonts with license
notices, precompile Tailwind, and add a network-disabled browser smoke test.
If deferring bundling, pin every CDN URL, add integrity where feasible, explicitly
require internet access, and provide a visible dependency-load error. Current
docs disclose internet dependence, but floating references remain a release
reproducibility issue. JavaScript advisory scanning and a redistribution-license
inventory have not yet been completed.

The Foundry bridge ZIP itself contains no CDN dependencies; the separate
companion UI is the part affected.

## Additional hardening and behavior findings

These were identified by code inspection, not a complete exploit/test campaign:

- Both WebSocket readers assume decoded JSON is an object; arrays/null can fail
  before dispatch. Add shape/type/size checks and meaningful protocol errors.
- Foundry command lookup uses inherited object properties as well as own keys.
  Restrict it to an explicit own-property allowlist and validate command args.
- UI commands are forwarded without a pairing token, role authentication, or
  server-side command schema. A malicious local process can replace the bridge
  or invoke GM actions. The one-GM browser check is not server authentication.
- Image upload accepts command-supplied data/filename metadata. Validate data URL,
  content type, file extension, and decoded size at the bridge boundary; the
  32 MiB UI WebSocket limit is not complete image validation.
- Valid JSON persistence is not schema-validated; malformed JSON silently falls
  back to defaults and later saves may overwrite it. Preserve/report corruption
  and test recovery rather than treating corruption as an empty campaign.
- Loading an encounter can auto-sync missing NPCs from vault notes before retrying.
  If artwork validation subsequently fails, an actor may already have been created.
  Pre-created actors with owned artwork remain the documented loading contract;
  the operation is not globally transactional. Make this side effect explicit
  or require separate sync/confirmation.
- The release workflow tests packaging, but publication is not dependent on the
  separate full regression workflow or a protected approval environment. Before
  real publication, require the broader checks and manual live-test sign-off.

## Next implementation order

1. Agree on the Python floor and per-world overlay migration policy.
2. Fix S1–S5 with targeted regressions; update dependencies and add audit gating.
3. Bundle frontend dependencies (or make the documented online-only alternative
   reproducible), then run cold-cache/offline browser checks.
4. Run Windows/Linux CI and the disposable Foundry/dnd5e checklist.
5. Re-review before any push/tag/publication approval.
