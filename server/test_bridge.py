"""HTTP/WebSocket regressions with disposable persistence and fake Foundry peers."""
import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from aiohttp import WSServerHandshakeError
from aiohttp.test_utils import TestClient, TestServer
import server


class BridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.data = Path(temp.name)
        settings = patch.multiple(server, DATA_DIR=self.data, VAULT_DIR=None,
                                  SESSIONS_DIR=None, NPCS_DIR=None, PLAYERS_DIR=None,
                                  IMPROV_NOTE=None, MAP_FOLDERS=[])
        settings.start()
        self.addCleanup(settings.stop)
        self.app = server.make_app()
        self.client = TestClient(TestServer(self.app))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)
        self.ui = await self.client.ws_connect("/ws/ui")
        self.assertEqual((await self.ui.receive_json(timeout=2))["type"], "state")

    async def receive(self, ws, kind):
        for _ in range(12):
            message = await ws.receive_json(timeout=2)
            if message["type"] == kind:
                return message
        self.fail("No " + kind + " message")

    async def foundry(self, world="harbor"):
        ws = await self.client.ws_connect("/ws/foundry", origin="http://localhost:30000")
        await ws.send_json({"type": "hello", "worldId": world, "world": world,
                            "user": "Test GM", "version": "14.369"})
        await self.receive(ws, "clocks")
        await self.receive(ws, "showcase")
        await self.receive(self.ui, "state")
        return ws

    async def test_disconnected_command_reports_error(self):
        await self.ui.send_json({"type": "command", "requestId": "offline", "command": "syncAll"})
        result = await self.receive(self.ui, "result")
        self.assertEqual(result["requestId"], "offline")
        self.assertFalse(result["ok"])
        self.assertIn("not connected", result["error"])

    async def test_command_results_and_scene_combat_broadcast(self):
        foundry = await self.foundry()
        command = {"type": "command", "requestId": "activate", "command": "activateScene",
                   "args": {"sceneId": "quay"}}
        await self.ui.send_json(command)
        self.assertEqual(await self.receive(foundry, "command"), command)
        result = {"type": "result", "requestId": "activate", "ok": False, "error": "Scene not found"}
        await foundry.send_json(result)
        self.assertEqual(await self.receive(self.ui, "result"), result)
        for message in [{"type": "scenes", "scenes": [{"id": "quay", "name": "Quay"}]},
                        {"type": "combat", "combat": {"id": "combat", "round": 2}}]:
            await foundry.send_json(message)
            self.assertEqual(await self.receive(self.ui, message["type"]), message)
        async with self.client.ws_connect("/ws/ui") as second_ui:
            snapshot = await second_ui.receive_json(timeout=2)
            self.assertEqual(snapshot["scenes"][0]["id"], "quay")
            self.assertEqual(snapshot["combat"]["round"], 2)

    async def test_disconnect_and_reconnect(self):
        foundry = await self.foundry()
        await foundry.close()
        snapshot = await self.receive(self.ui, "state")
        self.assertFalse(snapshot["foundryConnected"])
        self.assertEqual(snapshot["foundry"], {})
        self.assertIsNone(snapshot["combat"])
        await self.foundry()
        self.assertTrue(self.app["state"].snapshot()["foundryConnected"])

    async def test_new_foundry_connection_replaces_previous(self):
        first = await self.foundry()
        second_task = asyncio.create_task(self.foundry("second"))
        await first.receive(timeout=2)  # Process the server's close handshake.
        second = await asyncio.wait_for(second_task, timeout=3)
        self.assertTrue(first.closed)
        await self.ui.send_json({"type": "command", "requestId": "new", "command": "syncAll"})
        self.assertEqual((await self.receive(second, "command"))["requestId"], "new")
        self.assertEqual(self.app["state"].world_key(), "second")

    async def test_persistence_and_world_favorites(self):
        foundry = await self.foundry()
        await self.ui.send_json({"type": "toggleFavorite", "sceneId": "quay"})
        self.assertEqual((await self.receive(self.ui, "favorites"))["favorites"], ["quay"])
        await self.ui.send_json({"type": "setClocks", "clocks": [
            {"id": "beacon", "name": "Repair", "segments": 6, "filled": 2, "visible": False}]})
        clocks = (await self.receive(self.ui, "clocks"))["clocks"]
        self.assertEqual((await self.receive(foundry, "clocks"))["clocks"], clocks)
        showcase = {"items": [{"id": "mira", "name": "Mira", "src": "icons/mira.png", "shown": False}],
                    "layout": "row", "view": "fullscreen"}
        await self.ui.send_json({"type": "setShowcase", "showcase": showcase})
        self.assertEqual((await self.receive(self.ui, "showcase"))["showcase"], showcase)
        self.assertEqual((await self.receive(foundry, "showcase"))["showcase"], showcase)
        restored = server.State()
        restored.foundry_info = {"worldId": "harbor"}
        self.assertEqual(restored.world_favorites(), ["quay"])
        restored.foundry_info = {"worldId": "another"}
        self.assertEqual(restored.world_favorites(), [])
        self.assertEqual(restored.clocks.data, clocks)
        self.assertEqual(restored.showcase.data, showcase)
        self.assertFalse(list(self.data.glob("*.tmp")))

    async def test_remote_browser_origins_rejected(self):
        for endpoint in ("/ws/ui", "/ws/foundry"):
            for origin in ("https://evil.example", "http://localhost.evil.example", "null"):
                with self.subTest(endpoint=endpoint, origin=origin):
                    with self.assertRaises(WSServerHandshakeError) as error:
                        await self.client.ws_connect(endpoint, origin=origin)
                    self.assertEqual(error.exception.status, 403)

    async def test_invalid_json_does_not_disconnect(self):
        await self.ui.send_str("{invalid")
        await self.ui.send_json({"type": "command", "requestId": "after-invalid", "command": "syncAll"})
        self.assertEqual((await self.receive(self.ui, "result"))["requestId"], "after-invalid")

    async def test_clock_and_showcase_normalization(self):
        state = self.app["state"]
        state.set_clocks([None, {"id": "x", "segments": 99, "filled": -3},
                          {"id": "bad", "segments": "not a number"}])
        self.assertEqual(len(state.clocks.data), 1)
        self.assertEqual(state.clocks.data[0]["segments"], 12)
        self.assertEqual(state.clocks.data[0]["filled"], 0)
        state.set_showcase({"items": [None, {"id": "x", "src": "icons/test.png"}],
                            "layout": "invalid", "view": "invalid"})
        self.assertEqual(state.showcase.data["layout"], "column")
        self.assertEqual(state.showcase.data["view"], "corner")
        self.assertEqual(len(state.showcase.data["items"]), 1)
