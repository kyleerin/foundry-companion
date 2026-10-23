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
FACTIONS_DIR = VAULT_DIR / "Factions"
LOCATIONS_DIR = VAULT_DIR / "World" / "Locations"
# relationship map nodes: folder, node type, note names to leave out
MAP_FOLDERS = [(NPCS_DIR, "npc", set()), (PLAYERS_DIR, "pc", {PLAYER_DASHBOARD}),
               (FACTIONS_DIR, "faction", {"Factions Notes"}), (LOCATIONS_DIR, "location", {"Inspirations"})]

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
        # artwork shown in Foundry: {"items": [{id, name, src, shown}], "layout": "column" | "row", "view": "corner" | "fullscreen"}
        self.showcase = JsonStore(DATA_DIR / "showcase.json", {"items": [], "layout": "column"})
        if isinstance(self.showcase.data, list):  # older files held just the items
            self.showcase.data = {"items": self.showcase.data, "layout": "column"}

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
                          "segments": segments, "filled": filled, "visible": c.get("visible", True) is not False})
        self.clocks.data = valid
        self.clocks.save()

    def set_showcase(self, showcase):
        if not isinstance(showcase, dict) or not isinstance(showcase.get("items"), list):
            return
        items = [
            {"id": i["id"][:40], "name": str(i.get("name") or "")[:80], "src": i["src"][:500], "shown": i.get("shown") is not False}
            for i in showcase["items"][:50]
            if isinstance(i, dict) and isinstance(i.get("id"), str) and isinstance(i.get("src"), str) and i["src"]
        ]
        layout = "row" if showcase.get("layout") == "row" else "column"
        view = "fullscreen" if showcase.get("view") == "fullscreen" else "corner"
        self.showcase.data = {"items": items, "layout": layout, "view": view}
        self.showcase.save()

    def snapshot(self):
        return {
            "type": "state",
            "foundryConnected": self.foundry is not None,
            "foundry": self.foundry_info,
            "scenes": self.scenes,
            "combat": self.combat,
            "favorites": self.world_favorites(),
            "clocks": self.clocks.data,
            "showcase": self.showcase.data,
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
                await ws.send_str(json.dumps({"type": "clocks", "clocks": state.clocks.data}))
                await ws.send_str(json.dumps({"type": "showcase", "showcase": state.showcase.data}))
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

    ws = web.WebSocketResponse(heartbeat=20, max_msg_size=32 * 1024 * 1024)  # NPC images pass through
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
                if state.foundry is not None:
                    await state.foundry.send_str(json.dumps({"type": "clocks", "clocks": state.clocks.data}))
            elif data.get("type") == "setShowcase":
                state.set_showcase(data.get("showcase"))
                message = json.dumps({"type": "showcase", "showcase": state.showcase.data})
                await state.broadcast({"type": "showcase", "showcase": state.showcase.data})
                if state.foundry is not None:
                    await state.foundry.send_str(message)
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


SIZES = {"tiny": "tiny", "small": "sm", "medium": "med", "large": "lg", "huge": "huge", "gargantuan": "grg"}
ABILITIES = ["str", "dex", "con", "int", "wis", "cha"]


def parse_stats(text):
    """Best-effort 5e stat block fields from a note; the first match of each wins."""
    stats = {}
    lines = [re.sub(r"[*_]", "", line).strip() for line in text.splitlines()]
    for i, line in enumerate(lines):
        if "ac" not in stats and (m := re.search(r"\b(?:AC|Armor Class)\s*:?\s*(\d+)", line)):
            stats["ac"] = int(m.group(1))
        if "hp" not in stats and (m := re.search(r"\b(?:HP|Hit Points)\s*:?\s*(\d+)(?:\s*\(([\dd+\- ]+)\))?", line)):
            stats["hp"] = int(m.group(1))
            if m.group(2):
                stats["hpFormula"] = m.group(2).replace(" ", "")
        if "cr" not in stats and (m := re.search(r"\b(?:CR|Challenge(?: Rating)?)\s*:?\s*(\d+(?:/\d+)?)\b", line)):
            num, _, den = m.group(1).partition("/")
            stats["cr"] = int(num) / int(den) if den else int(num)
        if "speed" not in stats and (m := re.search(r"\bSpeed\s*:?\s*(\d+)\s*ft", line)):
            stats["speed"] = int(m.group(1))
            if fly := re.search(r"\bfly\s*(\d+)", line):
                stats["fly"] = int(fly.group(1))
        if "size" not in stats and (m := re.match(r"^(Tiny|Small|Medium|Large|Huge|Gargantuan)\s+([A-Za-z]+)(?:\s*\(([^)]*)\))?\s*,\s*(.+)$", line, re.I)):
            stats["size"] = SIZES[m.group(1).lower()]
            stats["type"] = m.group(2).lower()
            if m.group(3):
                stats["subtype"] = m.group(3)
            stats["alignment"] = m.group(4).strip()
        if "abilities" not in stats and re.match(r"^\|\s*STR\s*\|\s*DEX\s*\|", line, re.I):
            for row in lines[i + 1:i + 3]:
                scores = [int(m.group(1)) for m in re.finditer(r"\|\s*(\d+)", row)]
                if len(scores) >= 6:
                    stats["abilities"] = dict(zip(ABILITIES, scores[:6]))
                    break
    return stats


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif"}
IMAGE_EMBED_RE = re.compile(r"!\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]|!\[[^\]]*\]\(([^)\s]+)\)")


def resolve_file(target):
    """A vault file by path, else by file name, the way Obsidian resolves embeds."""
    direct = VAULT_DIR / target
    if direct.is_file() and VAULT_DIR in direct.resolve().parents:
        return direct
    name = Path(target).name
    return next((p for p in VAULT_DIR.rglob(name) if p.relative_to(VAULT_DIR).parts[0] not in ("books", ".obsidian", ".trash")), None)


def first_image(text):
    for m in IMAGE_EMBED_RE.finditer(text):
        target = m.group(1) or m.group(2)
        if re.match(r"^[a-z]+:", target) or Path(target).suffix.lower() not in IMAGE_EXTS:
            continue  # URLs and attachments that aren't in the vault
        path = resolve_file(target.strip())
        if path:
            return str(path.relative_to(VAULT_DIR))
    return None


async def api_vault_file(request):
    path = resolve_file(request.query.get("path", ""))
    if not path or path.suffix.lower() not in IMAGE_EXTS:
        raise web.HTTPNotFound(text="No such image")
    return web.FileResponse(path)


async def api_npc(request):
    target = request.query.get("target", "")
    path = resolve_note(target) if target else None
    if not path or NPCS_DIR not in path.parents:
        raise web.HTTPNotFound(text=f"No NPC note named {target}")
    text = re.sub(r"\A---\n.*?\n---\n", "", path.read_text(encoding="utf-8"), flags=re.S).strip()
    return web.json_response({"name": path.stem, "markdown": text, "stats": parse_stats(text), "image": first_image(text)})


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


def link_snippet(line):
    """A line of a note, trimmed for showing why two nodes are connected."""
    text = re.sub(r"^\s*([-*+]|\d+\.)\s+(\[.\]\s+)?", "", line).strip()
    return text if len(text) <= 240 else text[:237].rstrip() + "…"


def build_relations():
    """Nodes for every NPC, player, faction and location note, edges for the [[links]] between them."""
    paths = [(p, kind) for folder, kind, skip in MAP_FOLDERS if folder.is_dir()
             for p in folder.rglob("*.md") if p.stem not in skip]
    by_target, by_name = {}, {}
    nodes = []
    for path, kind in paths:
        target = str(path.relative_to(VAULT_DIR).with_suffix("")).replace("\\", "/")
        node = {"id": target, "name": path.stem, "type": kind}
        nodes.append((node, path))
        by_target[target.lower()] = node
        by_name.setdefault(path.stem.lower(), node)

    def resolve(link):
        link = link.strip().replace("\\", "/")
        return by_target.get(link.lower()) or by_name.get(link.split("/")[-1].lower())

    edges = {}
    for node, path in nodes:
        text = path.read_text(encoding="utf-8")
        image = first_image(text)
        if image:
            node["image"] = image.replace("\\", "/")
        heading = ""
        for line in text.splitlines():
            match = HEADING_RE.match(line)
            if match:
                heading = match.group(2).lower()
                continue
            field = NPC_FIELD_RE.match(line.strip()) or NPC_TABLE_RE.match(line.strip())
            if field and field.group(1) == "Faction":
                kind = "member"
            elif field and field.group(1) == "Location":
                kind = "location"
            elif "knows" in heading:
                kind = "knows"
            else:
                kind = "link"
            for m in WIKILINK_RE.finditer(line):
                other = resolve(m.group(1))
                if not other or other is node:
                    continue
                key = tuple(sorted((node["id"], other["id"])))
                edge = edges.setdefault(key, {"id": "|".join(key), "source": key[0], "target": key[1], "kinds": [], "evidence": []})
                if kind not in edge["kinds"]:
                    edge["kinds"].append(kind)
                item = {"from": node["id"], "kind": kind, "text": link_snippet(line)}
                if item not in edge["evidence"] and len(edge["evidence"]) < 8:
                    edge["evidence"].append(item)
    return {"nodes": [n for n, _ in nodes], "edges": list(edges.values())}


relations_cache = {"key": None, "value": None}


async def api_relations(request):
    files = [p for folder, _, _ in MAP_FOLDERS if folder.is_dir() for p in folder.rglob("*.md")]
    key = tuple(sorted((str(p), p.stat().st_mtime_ns) for p in files))
    if relations_cache["key"] != key:
        relations_cache["value"] = build_relations()
        relations_cache["key"] = key
    graph = relations_cache["value"]

    # nodes the selected session note links to
    session, linked = request.query.get("session", ""), []
    if session in list_sessions():
        names = {n["name"].lower(): n["id"] for n in graph["nodes"]}
        ids = {n["id"].lower(): n["id"] for n in graph["nodes"]}
        text = (SESSIONS_DIR / f"{session}.md").read_text(encoding="utf-8")
        for m in WIKILINK_RE.finditer(text):
            link = m.group(1).strip().replace("\\", "/")
            node = ids.get(link.lower()) or names.get(link.split("/")[-1].lower())
            if node and node not in linked:
                linked.append(node)
    return web.json_response({**graph, "session": linked})


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
    app.router.add_get("/api/npc", api_npc)
    app.router.add_get("/api/vault-file", api_vault_file)
    app.router.add_get("/api/players", api_players)
    app.router.add_get("/api/relations", api_relations)
    app.router.add_static("/static/", WEB_DIR)
    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    print(f"DM Companion running at http://localhost:{PORT}")
    web.run_app(make_app(), host=HOST, port=PORT, print=None)
