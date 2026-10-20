"""DM Companion local server.

Serves the web UI and relays messages between the browser UI and the
Foundry VTT module over WebSockets:

    web UI  <--ws /ws/ui-->  server  <--ws /ws/foundry-->  Foundry module
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from urllib.parse import urlparse

from aiohttp import WSMsgType, web

HOST = "127.0.0.1"
PORT = int(os.environ.get("DMC_PORT", 4000))
ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
DATA_DIR = Path(os.environ.get("DMC_DATA_DIR", ROOT / "data"))
ALLOWED_HOSTS = {"localhost", "127.0.0.1", "::1"}

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


async def index(_request):
    return web.FileResponse(WEB_DIR / "index.html")


def make_app():
    app = web.Application()
    app["state"] = State()
    app.router.add_get("/", index)
    app.router.add_get("/ws/foundry", foundry_ws)
    app.router.add_get("/ws/ui", ui_ws)
    app.router.add_static("/static/", WEB_DIR)
    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    print(f"DM Companion running at http://localhost:{PORT}")
    web.run_app(make_app(), host=HOST, port=PORT, print=None)
