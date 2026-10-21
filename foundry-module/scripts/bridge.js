// DM Companion Bridge
// Runs in the GM's browser. Connects to the local DM Companion server,
// sends world data to it, and runs commands it receives.

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
});

Hooks.once("ready", () => {
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

  // a vault NPC: linked to the world actor with that name when there is one, so HP and initiative rolls work
  async combatAddNpc({ name }) {
    if (!name) throw new Error("Name is required");
    const wanted = String(name).trim().toLowerCase();
    const actor = game.actors.find((a) => a.name.toLowerCase() === wanted)
      ?? game.actors.find((a) => a.name.toLowerCase().startsWith(wanted));
    let combat = activeCombat();
    if (!combat) combat = await Combat.implementation.create({ scene: canvas.scene?.id ?? null, active: true });
    await combat.createEmbeddedDocuments("Combatant", [actor
      ? { actorId: actor.id, name: actor.name, img: actor.img }
      : { name: String(name).slice(0, 80), img: "icons/svg/mystery-man.svg" }]);
    return { name: actor?.name ?? name, linked: Boolean(actor) };
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
