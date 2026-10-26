// DM Companion Bridge
// Runs in the GM's browser. Connects to the local DM Companion server,
// sends world data to it, and runs commands it receives.
// Progress clocks and the artwork showcase are saved in world settings and drawn on every client.

const MODULE_ID = "dm-companion";
const RETRY_MAX_MS = 15000;

let socket = null;
let retryMs = 1000;
let sceneSyncTimer = null;
let combatSyncTimer = null;

Hooks.once("init", () => {
  game.settings.register(MODULE_ID, "serverUrl", {
    name: "DM Companion server URL",
    hint: "WebSocket address of the local DM Companion server.",
    scope: "client",
    config: true,
    type: String,
    default: "ws://localhost:4000/ws/foundry",
    onChange: () => reconnect(),
  });
  game.settings.register(MODULE_ID, "clocks", {
    scope: "world",
    config: false,
    type: Array,
    default: [],
    onChange: () => renderClocks(),
  });
  game.settings.register(MODULE_ID, "showcase", {
    scope: "world",
    config: false,
    type: Object,
    default: { items: [], layout: "column", view: "corner" },
    onChange: () => renderShowcase(),
  });
});

Hooks.once("ready", () => {
  renderClocks();
  renderShowcase();
  if (!game.user.isGM) return;
  connect();

  for (const hook of ["createScene", "updateScene", "deleteScene", "createFolder", "updateFolder", "deleteFolder"]) {
    Hooks.on(hook, () => queueSceneSync());
  }

  // combat state, plus actor/token changes so HP stays current
  for (const hook of [
    "createCombat", "updateCombat", "deleteCombat",
    "createCombatant", "updateCombatant", "deleteCombatant",
    "updateActor", "updateToken",
  ]) {
    Hooks.on(hook, () => queueCombatSync());
  }
});

// ---------------------------------------------------------------- connection

function connect() {
  const url = game.settings.get(MODULE_ID, "serverUrl");
  try {
    socket = new WebSocket(url);
  } catch (err) {
    console.warn(`${MODULE_ID} | Bad server URL "${url}"`, err);
    return;
  }

  socket.addEventListener("open", () => {
    console.log(`${MODULE_ID} | Connected to ${url}`);
    retryMs = 1000;
    send({
      type: "hello",
      world: game.world.title,
      worldId: game.world.id,
      user: game.user.name,
      origin: window.location.origin,
      version: game.version,
    });
    sendScenes();
    sendCombat();
  });

  socket.addEventListener("message", (event) => {
    let data;
    try {
      data = JSON.parse(event.data);
    } catch {
      return;
    }
    if (data.type === "command") handleCommand(data);
    else if (data.type === "clocks") saveClocks(data.clocks);
    else if (data.type === "showcase") saveShowcase(data.showcase);
  });

  socket.addEventListener("close", () => {
    socket = null;
    setTimeout(connect, retryMs);
    retryMs = Math.min(retryMs * 2, RETRY_MAX_MS);
  });
}

function reconnect() {
  if (socket) socket.close();
  else connect();
}

function send(message) {
  if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(message));
}

// ------------------------------------------------------------------ clocks

async function saveClocks(clocks) {
  const visible = (clocks ?? []).filter((c) => c.visible !== false)
    .map(({ id, name, segments, filled }) => ({ id, name, segments, filled }));
  if (JSON.stringify(visible) === JSON.stringify(game.settings.get(MODULE_ID, "clocks"))) return;
  await game.settings.set(MODULE_ID, "clocks", visible);
}

function clockSvg({ segments, filled }) {
  const done = filled >= segments;
  const point = (k) => {
    const angle = (k / segments) * 2 * Math.PI - Math.PI / 2;
    return `${(50 + 45 * Math.cos(angle)).toFixed(2)},${(50 + 45 * Math.sin(angle)).toFixed(2)}`;
  };
  let wedges = "";
  for (let i = 0; i < segments; i++) {
    const fill = i < filled ? (done ? "#b4532a" : "#c9a227") : "#2a2420";
    wedges += `<path d="M50,50 L${point(i)} A45,45 0 0 1 ${point(i + 1)} Z" fill="${fill}" stroke="#110f0d" stroke-width="3"/>`;
  }
  return `<svg viewBox="0 0 100 100">${wedges}<circle cx="50" cy="50" r="45" fill="none" stroke="#c9a22788" stroke-width="2"/></svg>`;
}

function renderClocks() {
  const clocks = game.settings.get(MODULE_ID, "clocks") ?? [];
  let root = document.getElementById("dmc-clocks");
  if (!clocks.length) return root?.remove();
  if (!root) {
    root = document.createElement("div");
    root.id = "dmc-clocks";
    overlay().prepend(root);
  }
  root.innerHTML = clocks.map((c) => `
    <div class="dmc-clock${c.filled >= c.segments ? " done" : ""}">
      ${clockSvg(c)}
      <div class="dmc-clock-name"></div>
      <div class="dmc-clock-count">${c.filled} / ${c.segments}</div>
    </div>`).join("");
  root.querySelectorAll(".dmc-clock-name").forEach((label, i) => (label.textContent = clocks[i].name));
}

// ---------------------------------------------------------------- showcase

let showcaseCollapsed = false; // per client
let showcaseView = null; // switching views reopens a collapsed showcase

async function saveShowcase(showcase) {
  const items = (showcase?.items ?? []).filter((i) => i.shown !== false).map(({ id, name, src }) => ({ id, name, src }));
  const value = { items, layout: showcase?.layout === "row" ? "row" : "column", view: showcase?.view === "fullscreen" ? "fullscreen" : "corner" };
  if (JSON.stringify(value) === JSON.stringify(game.settings.get(MODULE_ID, "showcase"))) return;
  await game.settings.set(MODULE_ID, "showcase", value);
}

// every shown portrait at once, stacked in a column or lined up in a row,
// either in the top-right corner or filling the screen
function renderShowcase() {
  const { items = [], layout = "column", view = "corner" } = game.settings.get(MODULE_ID, "showcase") ?? {};
  let root = document.getElementById("dmc-showcase");
  const full = document.getElementById("dmc-showcase-full");
  if (!items.length) {
    full?.remove();
    return root?.remove();
  }
  if (view !== showcaseView) showcaseCollapsed = false;
  showcaseView = view;
  if (view === "fullscreen" && !showcaseCollapsed) {
    root?.remove();
    return renderFullscreenShowcase(items, layout);
  }
  full?.remove();
  if (!root) {
    root = document.createElement("div");
    root.id = "dmc-showcase";
    overlay().append(root);
  }
  root.className = `${layout}${showcaseCollapsed ? " collapsed" : ""}`;
  root.innerHTML = `
    <a class="dmc-showcase-toggle" title="${showcaseCollapsed ? "Show artwork" : "Hide artwork"}">
      <i class="fa-solid fa-${showcaseCollapsed ? "image" : "chevron-up"}"></i>${showcaseCollapsed ? ` ${items.length}` : ""}
    </a>
    ${showcaseCollapsed ? "" : `<div class="dmc-showcase-items">${items.map(() => `
      <div class="dmc-showcase-item"><img alt="" title="Click to enlarge"><div class="dmc-showcase-name"></div></div>`).join("")}
    </div>`}`;
  root.querySelectorAll(".dmc-showcase-item").forEach((item, i) => {
    const { name, src } = items[i];
    item.querySelector(".dmc-showcase-name").textContent = name;
    const img = item.querySelector("img");
    img.src = src;
    img.onclick = () => {
      const Popout = foundry.applications?.apps?.ImagePopout ?? globalThis.ImagePopout;
      new Popout({ src, window: { title: name } }).render({ force: true });
    };
  });
  root.querySelector(".dmc-showcase-toggle").onclick = () => {
    showcaseCollapsed = !showcaseCollapsed;
    renderShowcase();
  };
}

function renderFullscreenShowcase(items, layout) {
  ensureOverlayStyles();
  let root = document.getElementById("dmc-showcase-full");
  if (!root) {
    root = document.createElement("div");
    root.id = "dmc-showcase-full";
    document.body.append(root);
  }
  root.className = layout;
  root.innerHTML = `
    <a class="dmc-showcase-close" title="Hide artwork"><i class="fa-solid fa-xmark"></i></a>
    <div class="dmc-showcase-items">${items.map(() => `
      <div class="dmc-showcase-item"><img alt=""><div class="dmc-showcase-name"></div></div>`).join("")}
    </div>`;
  root.querySelectorAll(".dmc-showcase-item").forEach((item, i) => {
    item.querySelector(".dmc-showcase-name").textContent = items[i].name;
    item.querySelector("img").src = items[i].src;
  });
  root.querySelector(".dmc-showcase-close").onclick = () => {
    showcaseCollapsed = true;
    renderShowcase();
  };
}

// ----------------------------------------------------------------- overlay

// top-right column for clocks and the showcase, just left of the sidebar
function overlay() {
  let root = document.getElementById("dmc-overlay");
  if (!root) {
    ensureOverlayStyles();
    root = document.createElement("div");
    root.id = "dmc-overlay";
    document.body.append(root);
    placeOverlay();
  }
  return root;
}

function placeOverlay() {
  const root = document.getElementById("dmc-overlay");
  if (!root) return;
  const left = document.getElementById("sidebar")?.getBoundingClientRect().left;
  root.style.right = `${left ? Math.max(12, window.innerWidth - left + 12) : 12}px`;
}

Hooks.on("collapseSidebar", () => setTimeout(placeOverlay, 300)); // after the collapse animation
window.addEventListener("resize", () => placeOverlay());

function ensureOverlayStyles() {
  if (document.getElementById("dmc-overlay-styles")) return;
  const style = document.createElement("style");
  style.id = "dmc-overlay-styles";
  style.textContent = `
    #dmc-overlay { position: fixed; top: 12px; right: 12px; z-index: 70; display: flex; flex-direction: column;
      align-items: flex-end; gap: 10px; max-width: 70vw; pointer-events: none; }
    #dmc-clocks { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 10px; }
    .dmc-clock { width: 96px; padding: 8px 6px 6px; text-align: center; border-radius: 6px;
      background: rgba(17, 15, 13, 0.85); border: 1px solid rgba(201, 162, 39, 0.4); box-shadow: 0 2px 8px rgba(0, 0, 0, 0.5); }
    .dmc-clock.done { border-color: #b4532a; }
    .dmc-clock svg { width: 64px; height: 64px; display: block; margin: 0 auto 4px; }
    .dmc-clock-name { color: #e8dcc4; font-size: 12px; line-height: 1.2; overflow-wrap: anywhere; }
    .dmc-clock-count { color: #c9a227; font-size: 11px; }
    #dmc-showcase { display: flex; flex-direction: column; align-items: flex-end; gap: 6px; pointer-events: auto; }
    .dmc-showcase-toggle { color: #c9a227; cursor: pointer; font-size: 12px; padding: 2px 8px; border-radius: 4px;
      background: rgba(17, 15, 13, 0.85); border: 1px solid rgba(201, 162, 39, 0.4); }
    .dmc-showcase-items { display: flex; gap: 8px; }
    #dmc-showcase.column .dmc-showcase-items { flex-direction: column; align-items: flex-end;
      max-height: calc(100vh - 160px); overflow-y: auto; }
    #dmc-showcase.row .dmc-showcase-items { flex-direction: row; flex-wrap: wrap; justify-content: flex-end; max-width: 70vw; }
    .dmc-showcase-item { flex: 0 0 auto; width: auto; margin: 0; padding: 4px; border-radius: 6px; background: rgba(17, 15, 13, 0.92);
      border: 1px solid rgba(201, 162, 39, 0.4); box-shadow: 0 2px 8px rgba(0, 0, 0, 0.5); }
    .dmc-showcase-item img { display: block; margin: 0; padding: 0; border: 0; border-radius: 4px; cursor: zoom-in; background: #0a0908; object-fit: contain; }
    #dmc-showcase.column .dmc-showcase-item img { width: 150px; max-height: 190px; }
    #dmc-showcase.row .dmc-showcase-item img { height: 170px; max-width: 150px; }
    .dmc-showcase-name { color: #e8dcc4; font-size: 12px; text-align: center; padding-top: 3px;
      max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    #dmc-showcase-full { position: fixed; inset: 0; z-index: 1000; background: rgba(10, 9, 8, 0.96); padding: 40px 32px 24px; }
    #dmc-showcase-full .dmc-showcase-close { position: absolute; top: 10px; right: 14px; color: #c9a227; font-size: 22px; cursor: pointer; }
    #dmc-showcase-full .dmc-showcase-items { display: flex; gap: 20px; width: 100%; height: 100%; justify-content: center; }
    #dmc-showcase-full.column .dmc-showcase-items { flex-direction: column; align-items: center; }
    #dmc-showcase-full .dmc-showcase-item { flex: 1 1 0; min-width: 0; min-height: 0; display: flex; flex-direction: column;
      align-items: center; padding: 0; background: none; border: 0; box-shadow: none; }
    #dmc-showcase-full .dmc-showcase-item img { flex: 1 1 0; min-height: 0; width: 100%; object-fit: contain; display: block; border: 0; }
    #dmc-showcase-full .dmc-showcase-name { color: #e8dcc4; font-size: 22px; text-align: center; padding-top: 8px;
      font-family: "Modesto Condensed", serif; letter-spacing: 0.05em; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  `;
  document.head.append(style);
}

// ------------------------------------------------------------------ scenes

function queueSceneSync() {
  clearTimeout(sceneSyncTimer);
  sceneSyncTimer = setTimeout(sendScenes, 250);
}

function folderPath(folder) {
  const parts = [];
  while (folder) {
    parts.unshift(folder.name);
    folder = folder.folder;
  }
  return parts.join(" / ");
}

function sendScenes() {
  const scenes = game.scenes.contents
    .map((scene) => ({
      id: scene.id,
      name: scene.name,
      thumb: scene.thumb || null,
      active: scene.active,
      navigation: scene.navigation,
      folder: folderPath(scene.folder),
      sort: scene.sort,
    }))
    .sort((a, b) => a.folder.localeCompare(b.folder) || a.sort - b.sort || a.name.localeCompare(b.name));
  send({ type: "scenes", scenes });
}

// ------------------------------------------------------------------ combat

// "Linus" matches "Linus, the Hollow Legate" and "Dana" matches "Dana Bumbleboots", but "K" doesn't match "Kibber"
function sameName(a, b) {
  [a, b] = [a.toLowerCase().trim(), b.toLowerCase().trim()];
  return a === b || /^[ ,(]/.test(a.slice(b.length)) && a.startsWith(b) || /^[ ,(]/.test(b.slice(a.length)) && b.startsWith(a);
}

// Foundry's mystery man, or the placeholder dnd5e gives each actor type (systems/dnd5e/icons/svg/actors/npc.svg)
function isDefaultImage(src) {
  return !src || src === CONST.DEFAULT_TOKEN || src === "icons/svg/mystery-man.svg"
    || src.startsWith("systems/dnd5e/icons/svg/actors/");
}

// a data: URL from the web app, saved under the world's folder; returns its path
async function uploadImage({ name, data }, actorName) {
  const FP = foundry.applications?.apps?.FilePicker?.implementation ?? globalThis.FilePicker;
  const dir = `worlds/${game.world.id}/dm-companion`;
  try {
    await FP.createDirectory("data", dir);
  } catch {} // already exists
  const ext = (name.match(/\.\w+$/)?.[0] ?? ".png").toLowerCase();
  const fileName = `${actorName.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")}${ext}`;
  const blob = await (await fetch(data)).blob();
  const result = await FP.upload("data", dir, new File([blob], fileName, { type: blob.type }), {}, { notify: false });
  if (!result?.path) throw new Error("Image upload failed");
  return result.path;
}

// world actor by name, preferring player characters when `character` is set
function findActor(name, character = false) {
  const wanted = String(name).trim().toLowerCase();
  const actors = character ? [...game.actors.filter((a) => a.type === "character"), ...game.actors] : [...game.actors];
  return actors.find((a) => a.name.toLowerCase() === wanted) ?? actors.find((a) => sameName(a.name, wanted));
}

function activeCombat() {
  return game.combats.active ?? game.combat ?? null;
}

function queueCombatSync() {
  clearTimeout(combatSyncTimer);
  combatSyncTimer = setTimeout(sendCombat, 150);
}

// dnd5e actor stats; null when the actor doesn't have them
function actorStats(actor) {
  const attrs = actor?.system?.attributes;
  const hp = attrs?.hp;
  return {
    hp: hp && Number.isFinite(hp.max) ? { value: hp.value ?? 0, max: hp.max, temp: hp.temp || 0 } : null,
    ac: attrs?.ac?.value ?? null,
  };
}

function sendCombat() {
  const combat = activeCombat();
  if (!combat) return send({ type: "combat", combat: null });

  const currentId = combat.combatant?.id;
  const combatants = combat.turns.map((c) => ({
    id: c.id,
    name: c.name,
    img: c.token?.texture?.src || c.img || null,
    initiative: c.initiative,
    isNPC: c.isNPC,
    hidden: c.hidden,
    defeated: c.isDefeated ?? c.defeated,
    isCurrent: c.id === currentId,
    isCustom: !c.tokenId && !c.actorId,
    ...actorStats(c.actor),
  }));

  send({
    type: "combat",
    combat: { id: combat.id, round: combat.round, turn: combat.turn, started: combat.started, combatants },
  });
}

function requireCombat() {
  const combat = activeCombat();
  if (!combat) throw new Error("No active combat");
  return combat;
}

function requireCombatant(combatantId) {
  const combatant = requireCombat().combatants.get(combatantId);
  if (!combatant) throw new Error("Combatant not found");
  return combatant;
}

// ---------------------------------------------------------------- commands

const COMMANDS = {
  async activateScene({ sceneId }) {
    const scene = game.scenes.get(sceneId);
    if (!scene) throw new Error("Scene not found");
    await scene.activate();
    return { sceneId, name: scene.name };
  },

  async syncAll() {
    sendScenes();
    sendCombat();
    return { scenes: game.scenes.size };
  },

  async togglePause() {
    await game.togglePause(!game.paused, { broadcast: true });
    return { paused: game.paused };
  },

  // ---- combat

  async addSelectedTokens() {
    const tokens = canvas.tokens?.controlled.map((t) => t.document) ?? [];
    if (!tokens.length) throw new Error("No tokens selected in Foundry");
    const before = activeCombat()?.combatants.size ?? 0;
    await TokenDocument.implementation.createCombatants(tokens);
    const combat = activeCombat();
    if (combat && !combat.active) await combat.activate();
    return { added: (activeCombat()?.combatants.size ?? 0) - before };
  },

  // an entry with no token or actor: lair actions, hazards, timers
  async combatAddCustom({ name, initiative = null, img = null, hidden = false }) {
    if (!name) throw new Error("Name is required");
    let combat = activeCombat();
    if (!combat) combat = await Combat.implementation.create({ scene: canvas.scene?.id ?? null, active: true });
    await combat.createEmbeddedDocuments("Combatant", [{
      name: String(name).slice(0, 80),
      img: img || "icons/svg/mystery-man.svg",
      initiative: Number.isFinite(initiative) ? initiative : null,
      hidden: Boolean(hidden),
    }]);
    return { name };
  },

  // a vault NPC or player character by name: uses the world actor with that name when there is one
  // (its token on the current scene if placed), so HP and initiative rolls work; else a plain entry
  async combatAddByName({ name, character = false }) {
    if (!name) throw new Error("Name is required");
    const actor = findActor(name, character);
    let combat = activeCombat();
    if (!combat) combat = await Combat.implementation.create({ scene: canvas.scene?.id ?? null, active: true });
    const inCombat = new Set(combat.combatants.map((c) => c.tokenId).filter(Boolean));
    const token = actor && canvas.scene?.tokens.find((t) => t.actorId === actor.id && !inCombat.has(t.id));
    await combat.createEmbeddedDocuments("Combatant", [token
      ? { tokenId: token.id, sceneId: canvas.scene.id, actorId: actor.id, hidden: token.hidden }
      : actor
        ? { actorId: actor.id, name: actor.name, img: actor.img }
        : { name: String(name).slice(0, 80), img: "icons/svg/mystery-man.svg" }]);
    if (!combat.active) await combat.activate();
    return { name: actor?.name ?? name, linked: Boolean(actor) };
  },

  // an NPC's or player character's portrait, for the showcase
  async loadEncounter({ scene = "", npcs = [] }) {
    const matches = scene ? game.scenes.filter((s) => s.id === scene || s.name.trim().toLowerCase() === scene.trim().toLowerCase()) : [];
    if (scene && matches.length !== 1) throw new Error(matches.length ? `More than one scene named ${scene}` : `No Foundry scene named ${scene}`);
    const missing = npcs.filter((target) => !findActor(target.split("/").pop()));
    if (missing.length) return { missing };
    const artwork = [];
    // Resolve everything before activating the scene, so a typo doesn't partially load it.
    for (const target of npcs) {
      const name = target.split("/").pop();
      artwork.push(await COMMANDS.findArtwork({ name }));
    }
    if (matches.length) await matches[0].activate();
    return { scene: matches[0]?.name, artwork };
  },

  async findArtwork({ name, character = false }) {
    const actor = findActor(name, character);
    if (!actor) throw new Error(`No Foundry actor named ${name}`);
    const src = [actor.img, actor.prototypeToken?.texture?.src].find((img) => !isDefaultImage(img));
    if (!src) throw new Error(`${actor.name} has no artwork`);
    return { name: actor.name, src };
  },

  // create or update a dnd5e NPC from a vault note: the note becomes the biography,
  // and stat block fields found in it overwrite the actor's (others are left alone)
  async syncNpc({ name, biography = "", stats = {}, image = null }) {
    if (!name) throw new Error("Name is required");
    const wanted = String(name).trim().toLowerCase();
    const npcs = game.actors.filter((a) => a.type === "npc");
    let actor = npcs.find((a) => a.name.toLowerCase() === wanted) ?? npcs.find((a) => sameName(a.name, wanted));

    const data = { "system.details.biography.value": biography };
    if (Number.isFinite(stats.ac)) Object.assign(data, { "system.attributes.ac.calc": "flat", "system.attributes.ac.flat": stats.ac });
    if (Number.isFinite(stats.hp)) data["system.attributes.hp.max"] = stats.hp;
    if (stats.hpFormula) data["system.attributes.hp.formula"] = stats.hpFormula;
    if (Number.isFinite(stats.cr)) data["system.details.cr"] = stats.cr;
    if (Number.isFinite(stats.speed)) data["system.attributes.movement.walk"] = stats.speed;
    if (Number.isFinite(stats.fly)) data["system.attributes.movement.fly"] = stats.fly;
    if (stats.size) data["system.traits.size"] = stats.size;
    if (stats.type) data["system.details.type.value"] = stats.type;
    if (stats.subtype) data["system.details.type.subtype"] = stats.subtype;
    if (stats.alignment) data["system.details.alignment"] = stats.alignment;
    for (const [ability, value] of Object.entries(stats.abilities ?? {})) data[`system.abilities.${ability}.value`] = value;

    const fields = Object.keys(data).length - 1;
    const created = !actor;
    if (actor) {
      await actor.update(data);
    } else {
      const folder = game.folders.find((f) => f.type === "Actor" && f.name === "NPCs")
        ?? await Folder.implementation.create({ name: "NPCs", type: "Actor" });
      if (Number.isFinite(stats.hp)) data["system.attributes.hp.value"] = stats.hp;
      actor = await Actor.implementation.create({
        name: String(name).slice(0, 80),
        type: "npc",
        folder: folder.id,
        ...foundry.utils.expandObject(data),
      });
    }

    // the note's image, only over Foundry's default art so hand-picked portraits stay
    let imageSet = false;
    if (image?.data && isDefaultImage(actor.img)) {
      const src = await uploadImage(image, actor.name);
      const update = { img: src };
      if (isDefaultImage(actor.prototypeToken?.texture?.src)) update["prototypeToken.texture.src"] = src;
      await actor.update(update);
      imageSet = true;
    }
    return { name: actor.name, created, fields, imageSet };
  },

  async combatRemove({ combatantId }) {
    await requireCombatant(combatantId).delete();
    return {};
  },

  async combatStart() {
    await requireCombat().startCombat();
    return {};
  },

  async combatNext() {
    await requireCombat().nextTurn();
    return {};
  },

  async combatPrevious() {
    await requireCombat().previousTurn();
    return {};
  },

  async combatEnd() {
    // delete directly; Combat#endCombat would open a confirm dialog in Foundry
    await requireCombat().delete();
    return {};
  },

  async combatRollNPC() {
    await requireCombat().rollNPC();
    return {};
  },

  async combatRollAll() {
    await requireCombat().rollAll();
    return {};
  },

  async combatSetInitiative({ combatantId, value }) {
    const combatant = requireCombatant(combatantId);
    await combatant.update({ initiative: value === null || Number.isNaN(value) ? null : Number(value) });
    return {};
  },

  async combatToggleHidden({ combatantId }) {
    const combatant = requireCombatant(combatantId);
    await combatant.update({ hidden: !combatant.hidden });
    return { hidden: combatant.hidden };
  },

  async combatToggleDefeated({ combatantId }) {
    const combatant = requireCombatant(combatantId);
    const defeated = !combatant.isDefeated;
    await combatant.update({ defeated });
    // mirror Foundry's tracker: toggle the defeated status on the token's actor
    const statusId = CONFIG.specialStatusEffects.DEFEATED;
    if (statusId && combatant.actor) {
      await combatant.actor.toggleStatusEffect(statusId, { active: defeated, overlay: true });
    }
    return { defeated };
  },

  // positive amount = damage, negative = healing
  async combatApplyDamage({ combatantId, amount }) {
    const actor = requireCombatant(combatantId).actor;
    if (!actor) throw new Error("Combatant has no actor");
    if (typeof actor.applyDamage === "function") {
      await actor.applyDamage(Number(amount));
    } else {
      const hp = actor.system?.attributes?.hp;
      if (!hp) throw new Error("Actor has no HP");
      const value = Math.max(0, Math.min(hp.max, hp.value - Number(amount)));
      await actor.update({ "system.attributes.hp.value": value });
    }
    return {};
  },
};

async function handleCommand({ requestId, command, args = {} }) {
  const fn = COMMANDS[command];
  try {
    if (!fn) throw new Error(`Unknown command "${command}"`);
    const result = await fn(args);
    send({ type: "result", requestId, ok: true, result });
  } catch (err) {
    console.error(`${MODULE_ID} | ${command} failed`, err);
    send({ type: "result", requestId, ok: false, error: err.message });
  }
}
