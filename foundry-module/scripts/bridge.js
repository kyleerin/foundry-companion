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
    default: { items: [], layout: "column" },
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

async function saveShowcase(showcase) {
  const items = (showcase?.items ?? []).filter((i) => i.shown !== false).map(({ id, name, src }) => ({ id, name, src }));
  const value = { items, layout: showcase?.layout === "row" ? "row" : "column" };
  if (JSON.stringify(value) === JSON.stringify(game.settings.get(MODULE_ID, "showcase"))) return;
  await game.settings.set(MODULE_ID, "showcase", value);
}

// every shown portrait at once, stacked in a column or lined up in a row
function renderShowcase() {
  const { items = [], layout = "column" } = game.settings.get(MODULE_ID, "showcase") ?? {};
  let root = document.getElementById("dmc-showcase");
  if (!items.length) return root?.remove();
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
  async findArtwork({ name, character = false }) {
    const actor = findActor(name, character);
    if (!actor) throw new Error(`No Foundry actor named ${name}`);
    const fallback = CONST.DEFAULT_TOKEN ?? "icons/svg/mystery-man.svg";
    const src = [actor.img, actor.prototypeToken?.texture?.src].find((img) => img && img !== fallback);
    if (!src) throw new Error(`${actor.name} has no artwork`);
    return { name: actor.name, src };
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
