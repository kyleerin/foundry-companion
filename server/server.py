"""DM Companion local server.

Serves the web UI and relays messages between the browser UI and the
Foundry VTT module over WebSockets:

    web UI  <--ws /ws/ui-->  server  <--ws /ws/foundry-->  Foundry module
"""

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from urllib.parse import urlparse

from aiohttp import WSMsgType, web

HOST = "127.0.0.1"
PORT = int(os.environ.get("DMC_PORT", 4000))
ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
DATA_DIR = Path(os.environ.get("DMC_DATA_DIR", ROOT / "data"))
ALLOWED_HOSTS = {"localhost", "127.0.0.1", "::1"}
VAULT_DIR = Path(os.environ.get("DMC_VAULT_DIR", Path.home() / "Documents" / "Lysoria"))
SESSIONS_DIR = VAULT_DIR / "Story" / "Act 1" / "Sessions"
NPCS_DIR = VAULT_DIR / "NPCs"
PLAYERS_DIR = VAULT_DIR / "Players"
PLAYER_DASHBOARD = "Player Dashboard"

log = logging.getLogger("dm-companion")


class JsonStore:
    """A small JSON file, written atomically."""

    def __init__(self, path, default):
        self.path = path
        try:
            self.data = json.loads(path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            self.data = default

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2))
        tmp.replace(self.path)


class State:
    def __init__(self):
        self.foundry = None  # the connected Foundry module socket
        self.foundry_info = {}  # world, user, origin
        self.ui_clients = set()
        self.scenes = []  # last scene list sent by Foundry
        self.combat = None  # last combat state sent by Foundry
        self.favorites = JsonStore(DATA_DIR / "favorites.json", {})  # world key -> [scene ids]
        self.clocks = JsonStore(DATA_DIR / "clocks.json", [])  # progress clocks, shared across worlds

    def world_key(self):
        return self.foundry_info.get("worldId") or self.foundry_info.get("world")

    def world_favorites(self):
        key = self.world_key()
        return list(self.favorites.data.get(key, [])) if key else []

    def toggle_favorite(self, scene_id):
        key = self.world_key()
        if not key or not isinstance(scene_id, str):
            return
        ids = self.favorites.data.setdefault(key, [])
        if scene_id in ids:
            ids.remove(scene_id)
        else:
            ids.append(scene_id)
        self.favorites.save()

    def set_clocks(self, clocks):
        if not isinstance(clocks, list):
            return
        valid = []
        for c in clocks[:100]:
            if not isinstance(c, dict) or not isinstance(c.get("id"), str):
                continue
            try:
                segments = max(2, min(12, int(c.get("segments", 4))))
                filled = max(0, min(segments, int(c.get("filled", 0))))
            except (TypeError, ValueError):
                continue
            valid.append({"id": c["id"][:40], "name": str(c.get("name") or "Clock")[:80],
                          "segments": segments, "filled": filled})
        self.clocks.data = valid
        self.clocks.save()

    def snapshot(self):
        return {
            "type": "state",
            "foundryConnected": self.foundry is not None,
            "foundry": self.foundry_info,
            "scenes": self.scenes,
            "combat": self.combat,
            "favorites": self.world_favorites(),
            "clocks": self.clocks.data,
        }

    async def broadcast(self, message):
        data = json.dumps(message)
        for ws in list(self.ui_clients):
            try:
                await ws.send_str(data)
            except ConnectionError:
                self.ui_clients.discard(ws)


def origin_allowed(request):
    origin = request.headers.get("Origin")
    if not origin:
        return True  # non-browser clients
    return urlparse(origin).hostname in ALLOWED_HOSTS


async def foundry_ws(request):
    state = request.app["state"]
    if not origin_allowed(request):
        raise web.HTTPForbidden(text="Origin not allowed")

    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)

    if state.foundry is not None and not state.foundry.closed:
        await state.foundry.close(message=b"Replaced by a newer Foundry connection")
    state.foundry = ws
    log.info("Foundry connected")

    try:
        async for msg in ws:
            if msg.type != WSMsgType.TEXT:
                continue
            try:
                data = json.loads(msg.data)
            except json.JSONDecodeError:
                continue

            kind = data.get("type")
            if kind == "hello":
                state.foundry_info = {
                    "world": data.get("world"),
                    "worldId": data.get("worldId"),
                    "user": data.get("user"),
                    "origin": data.get("origin"),
                    "version": data.get("version"),
                }
                log.info("Foundry world: %s (v%s)", data.get("world"), data.get("version"))
                await state.broadcast(state.snapshot())
            elif kind == "scenes":
                state.scenes = data.get("scenes", [])
                await state.broadcast({"type": "scenes", "scenes": state.scenes})
            elif kind == "combat":
                state.combat = data.get("combat")
                await state.broadcast({"type": "combat", "combat": state.combat})
            elif kind == "result":
                await state.broadcast(data)
    finally:
        if state.foundry is ws:
            state.foundry = None
            state.foundry_info = {}
            state.combat = None
            log.info("Foundry disconnected")
            await state.broadcast(state.snapshot())
    return ws


async def ui_ws(request):
    state = request.app["state"]
    if not origin_allowed(request):
        raise web.HTTPForbidden(text="Origin not allowed")

    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)
    state.ui_clients.add(ws)
    await ws.send_str(json.dumps(state.snapshot()))

    try:
        async for msg in ws:
            if msg.type != WSMsgType.TEXT:
                continue
            try:
                data = json.loads(msg.data)
            except json.JSONDecodeError:
                continue

            if data.get("type") == "command":
                if state.foundry is None:
                    await ws.send_str(json.dumps({
                        "type": "result",
                        "requestId": data.get("requestId"),
                        "ok": False,
                        "error": "Foundry is not connected",
                    }))
                    continue
                await state.foundry.send_str(json.dumps(data))
            elif data.get("type") == "toggleFavorite":
                state.toggle_favorite(data.get("sceneId"))
                await state.broadcast({"type": "favorites", "favorites": state.world_favorites()})
            elif data.get("type") == "setClocks":
                state.set_clocks(data.get("clocks"))
                await state.broadcast({"type": "clocks", "clocks": state.clocks.data})
    finally:
        state.ui_clients.discard(ws)
    return ws


# ------------------------------------------------------------------ vault

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
META_RE = re.compile(r"^\*\*(Type|Difficulty|Duration|Location)\*\*:\s*(.+)$")
NPC_FIELD_RE = re.compile(r"^\*\*(Race|Occupation|Faction|Location)(?::\*\*|\*\*:)\s*(.+)$")
# headings, tables, rules, quotes, embeds, URLs, bold-only lines and "**Label:**" lines don't make a summary
NPC_SKIP_RE = re.compile(r"^(#|\||---|>|!\[|https?://|\*\*[^*]+\*\*$|\*\*[^*]+(:\*\*|\*\*:)|\w+:\s)")
NPC_TABLE_RE = re.compile(r"^\|\s*(Class/Role|Faction|Location)\s*\|\s*(.+?)\s*\|$")


def natural_key(name):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", name)]


def list_sessions():
    if not SESSIONS_DIR.is_dir():
        return []
    return sorted((p.stem for p in SESSIONS_DIR.glob("*.md")), key=natural_key)


def section_links(text, title):
    """Wikilink targets under the heading named `title`, until the next heading of the same or higher level."""
    links, level = [], None
    for line in text.splitlines():
        heading = HEADING_RE.match(line)
        if heading:
            if level is not None and len(heading.group(1)) <= level:
                break
            if level is None and heading.group(2).strip().lower() == title:
                level = len(heading.group(1))
            continue
        if level is not None:
            links += [m.group(1).strip() for m in WIKILINK_RE.finditer(line)]
    return list(dict.fromkeys(links))


def resolve_note(target):
    """Find a vault note the way Obsidian resolves [[target]]: by path, else by file name."""
    direct = (VAULT_DIR / target).with_suffix(".md")
    if direct.is_file() and VAULT_DIR in direct.resolve().parents:
        return direct
    name = Path(target).name + ".md"
    matches = [p for p in VAULT_DIR.rglob(name) if not p.relative_to(VAULT_DIR).parts[0] in ("books", ".obsidian", ".trash")]
    # prefer notes next to the session's act
    matches.sort(key=lambda p: (SESSIONS_DIR.parent not in p.parents, len(p.parts)))
    return matches[0] if matches else None


def parse_encounter(name, path):
    meta, body, title = {}, [], name
    for line in path.read_text(encoding="utf-8").splitlines():
        heading = HEADING_RE.match(line)
        if heading and len(heading.group(1)) == 1 and title == name and not body:
            title = re.sub(r"^Encounter\s*-\s*", "", heading.group(2))
            continue
        field = META_RE.match(line.strip())
        if field and not any(l.startswith("## ") for l in body):
            meta[field.group(1).lower()] = field.group(2)
            continue
        body.append(line)
    return {"name": name, "title": title, "found": True, "meta": meta,
            "path": str(path.relative_to(VAULT_DIR)), "markdown": "\n".join(body).strip()}


async def api_sessions(_request):
    return web.json_response({"sessions": list_sessions()})


async def api_encounters(request):
    session = request.query.get("session", "")
    if session not in list_sessions():
        raise web.HTTPNotFound(text="No such session")
    text = (SESSIONS_DIR / f"{session}.md").read_text(encoding="utf-8")
    encounters = []
    for target in section_links(text, "encounters"):
        path = resolve_note(target)
        encounters.append(parse_encounter(Path(target).name, path) if path else
                          {"name": Path(target).name, "title": Path(target).name, "found": False})
    return web.json_response({"session": session, "encounters": encounters})


async def api_note(request):
    session = request.query.get("session", "")
    if session not in list_sessions():
        raise web.HTTPNotFound(text="No such session")
    text = (SESSIONS_DIR / f"{session}.md").read_text(encoding="utf-8")
    text = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S)  # drop frontmatter
    return web.json_response({"session": session, "markdown": text.strip()})


async def api_vault_note(request):
    target = request.query.get("target", "").strip()
    path = resolve_note(target) if target else None
    if not path:
        raise web.HTTPNotFound(text=f"No note named {target}")
    text = re.sub(r"\A---\n.*?\n---\n", "", path.read_text(encoding="utf-8"), flags=re.S)
    return web.json_response({"target": target, "title": path.stem,
                              "path": str(path.relative_to(VAULT_DIR)), "markdown": text.strip()})


def parse_npc(path):
    fields = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        match = NPC_FIELD_RE.match(line) or NPC_TABLE_RE.match(line)
        if match:
            key = "occupation" if match.group(1) == "Class/Role" else match.group(1).lower()
            fields.setdefault(key, match.group(2).strip())
        elif "summary" not in fields:
            text = re.sub(r"^([-*+]|\d+\.)\s+", "", line)
            if re.search(r"[a-z]{3}", text) and not NPC_SKIP_RE.match(text):
                fields["summary"] = text
    target = str(path.relative_to(VAULT_DIR).with_suffix(""))
    return {"name": path.stem, "target": target, **fields}


async def api_npcs(_request):
    paths = NPCS_DIR.rglob("*.md") if NPCS_DIR.is_dir() else []
    npcs = sorted((parse_npc(p) for p in paths), key=lambda n: natural_key(n["name"]))
    return web.json_response({"npcs": npcs})


def player_dashboard():
    """Player and class per character from the Player Dashboard note: "## Rob" then "**Dana - artificer**"."""
    path = PLAYERS_DIR / f"{PLAYER_DASHBOARD}.md"
    players, player = [], None
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            heading = re.match(r"^##\s+(.+?)\s*$", line)
            if heading:
                player = heading.group(1)
                continue
            bold = re.match(r"^\*\*(.+?)\*\*\s*$", line.strip())
            if player and bold:
                character, _, cls = bold.group(1).rpartition(" - ")
                character = re.sub(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", r"\1", character)
                players.append({"player": player, "character": character, "class": cls})
                player = None
    return players


def parse_player(path, dashboard):
    text = path.read_text(encoding="utf-8")
    info = {"name": path.stem, "target": str(path.relative_to(VAULT_DIR).with_suffix(""))}
    entry = next((d for d in dashboard if d["character"] and path.stem.lower().startswith(d["character"].lower())), None)
    if entry:
        info.update(player=entry["player"], **{"class": entry["class"]})
    else:
        # "# Rob - Dana", "## Chris" or "**Chase**" near the top of the note
        for line in text.splitlines()[:30]:
            match = re.match(r"^(?:#{1,2}\s+([A-Z]\w+)\s+-\s|##\s+([A-Z]\w+)\s*$|\*\*([A-Z]\w+)\*\*\s*$)", line.strip())
            if match:
                info["player"] = next(g for g in match.groups() if g)
                cls = next((d["class"] for d in dashboard if d["player"] == info["player"]), None)
                if cls:
                    info["class"] = cls
                break
    role = re.search(r"^\|\s*\**Class\s*/\s*Role\**\s*\|\s*(.+?)\s*\|", text, re.M)
    if role:
        info["role"] = role.group(1)

    # open checklist items under an "Active ..." heading
    storylines, active = [], False
    for line in text.splitlines():
        heading = HEADING_RE.match(line)
        if heading:
            active = "active" in heading.group(2).lower()
        elif active:
            item = re.match(r"^\s*[-*]\s+\[ \]\s+(?:\*\*(.+?)\*\*|(.+))", line)
            if item:
                storylines.append((item.group(1) or item.group(2)).strip())
    info["storylines"] = storylines
    return info


async def api_players(_request):
    if not PLAYERS_DIR.is_dir():
        return web.json_response({"players": [], "dashboard": None})
    dashboard = player_dashboard()
    paths = [p for p in PLAYERS_DIR.rglob("*.md") if p.stem != PLAYER_DASHBOARD]
    players = sorted((parse_player(p, dashboard) for p in paths), key=lambda n: natural_key(n["name"]))
    has_dashboard = (PLAYERS_DIR / f"{PLAYER_DASHBOARD}.md").is_file()
    return web.json_response({"players": players,
                              "dashboard": f"{PLAYERS_DIR.name}/{PLAYER_DASHBOARD}" if has_dashboard else None})


async def index(_request):
    return web.FileResponse(WEB_DIR / "index.html")


def make_app():
    app = web.Application()
    app["state"] = State()
    app.router.add_get("/", index)
    app.router.add_get("/ws/foundry", foundry_ws)
    app.router.add_get("/ws/ui", ui_ws)
    app.router.add_get("/api/sessions", api_sessions)
    app.router.add_get("/api/encounters", api_encounters)
    app.router.add_get("/api/note", api_note)
    app.router.add_get("/api/vault-note", api_vault_note)
    app.router.add_get("/api/npcs", api_npcs)
    app.router.add_get("/api/players", api_players)
    app.router.add_static("/static/", WEB_DIR)
    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    print(f"DM Companion running at http://localhost:{PORT}")
    web.run_app(make_app(), host=HOST, port=PORT, print=None)
