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

    def snapshot(self):
        return {
            "type": "state",
            "foundryConnected": self.foundry is not None,
            "foundry": self.foundry_info,
            "scenes": self.scenes,
            "combat": self.combat,
            "favorites": self.world_favorites(),
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
    finally:
        state.ui_clients.discard(ws)
    return ws


# ------------------------------------------------------------------ vault

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
META_RE = re.compile(r"^\*\*(Type|Difficulty|Duration|Location)\*\*:\s*(.+)$")


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
    app.router.add_static("/static/", WEB_DIR)
    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    print(f"DM Companion running at http://localhost:{PORT}")
    web.run_app(make_app(), host=HOST, port=PORT, print=None)
