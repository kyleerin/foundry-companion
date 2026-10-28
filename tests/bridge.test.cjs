const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

function bridge() {
  const hooks = {};
  const messages = [];
  const settings = new Map([["clocks", []], ["showcase", { items: [] }]]);
  const game = {
    user: { isGM: true }, actors: [], scenes: [], folders: [],
    settings: { get: (_, key) => settings.get(key), set: async (_, key, value) => settings.set(key, value) },
  };
  const context = vm.createContext({
    game, Hooks: { once: (name, fn) => { hooks[name] = fn; }, on() {} },
    console: { log() {}, warn() {}, error() {} },
    document: { getElementById: () => null },
    window: { addEventListener() {} },
    testMessages: messages,
    CONST: { DEFAULT_TOKEN: "icons/svg/mystery-man.svg" },
    WebSocket: class { static OPEN = 1; },
  });
  const source = fs.readFileSync(path.join(__dirname, "../foundry-module/scripts/bridge.js"), "utf8");
  vm.runInContext(source + `
    socket = { readyState: 1, send: message => testMessages.push(JSON.parse(message)) };
    globalThis.api = { COMMANDS, handleCommand, saveClocks, saveShowcase };
  `, context);
  return { ...context.api, game, hooks, messages, settings };
}

test("encounter validates artwork before activating a scene", async () => {
  const b = bridge();
  let activated = false;
  b.game.scenes.push({ id: "quay", name: "Lantern Quay", activate: async () => { activated = true; } });
  b.game.actors.push({ name: "Mira Reed", img: "icons/svg/mystery-man.svg" });
  await assert.rejects(b.COMMANDS.loadEncounter({ scene: "quay", npcs: ["Mira Reed"] }), /no artwork/);
  assert.equal(activated, false);
  b.game.actors[0].img = "owned/mira.png";
  const result = await b.COMMANDS.loadEncounter({ scene: "quay", npcs: ["Mira Reed"] });
  assert.equal(activated, true);
  assert.equal(result.artwork[0].src, "owned/mira.png");
});

test("ambiguous or missing scenes do not activate", async () => {
  const b = bridge();
  await assert.rejects(b.COMMANDS.loadEncounter({ scene: "missing" }), /No Foundry scene/);
  b.game.scenes.push({ name: "Quay" }, { name: "Quay" });
  await assert.rejects(b.COMMANDS.loadEncounter({ scene: "Quay" }), /More than one/);
});

test("missing actor is returned before scene activation", async () => {
  const b = bridge();
  let activated = false;
  b.game.scenes.push({ id: "quay", name: "Quay", activate: async () => { activated = true; } });
  const result = await b.COMMANDS.loadEncounter({ scene: "quay", npcs: ["Absent"] });
  assert.equal(result.missing[0], "Absent");
  assert.equal(activated, false);
});

test("command errors retain the request ID", async () => {
  const b = bridge();
  await b.handleCommand({ requestId: "unknown", command: "notACommand" });
  assert.equal(b.messages[0].requestId, "unknown");
  assert.equal(b.messages[0].ok, false);
  assert.match(b.messages[0].error, /Unknown command/);
});

test("only visible overlays are saved to Foundry", async () => {
  const b = bridge();
  await b.saveClocks([{ id: "hidden", visible: false }, { id: "shown", name: "Beacon", segments: 4, filled: 1 }]);
  assert.equal(b.settings.get("clocks").length, 1);
  await b.saveShowcase({ items: [{ id: "hidden", shown: false }, { id: "shown", src: "owned/mira.png" }],
    layout: "row", view: "fullscreen" });
  assert.equal(b.settings.get("showcase").items.length, 1);
  assert.equal(b.settings.get("showcase").view, "fullscreen");
});

test("player readiness does not create a command connection", () => {
  const b = bridge();
  b.game.user.isGM = false;
  // WebSocket has no addEventListener: attempting to connect would throw.
  assert.doesNotThrow(() => b.hooks.ready());
});

test("NPC sync updates only supplied fields and preserves custom art", async () => {
  const b = bridge();
  const changes = [];
  b.game.actors.push({ type: "npc", name: "Mira Reed", img: "owned/mira.png",
    update: async data => changes.push(data) });
  const result = await b.COMMANDS.syncNpc({ name: "Mira Reed", biography: "<p>Keeper</p>",
    stats: { ac: 12 }, image: { data: "ignored" } });
  assert.equal(result.created, false);
  assert.equal(result.imageSet, false);
  assert.equal(changes[0]["system.attributes.ac.flat"], 12);
  assert.equal(changes[0]["system.attributes.hp.max"], undefined);
  assert.equal(changes.length, 1);
});
