"""Configuration and vaultless API checks; run with unittest discovery."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from aiohttp.test_utils import TestClient, TestServer
import server


class VaultConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.vault = self.root / "My Campaign"
        self.vault.mkdir()

    def config(self, **values):
        (self.root / "config.json").write_text(json.dumps(values), encoding="utf-8")

    def test_no_config_disables_vault(self):
        vault, paths = server.load_vault_config(self.root, {})
        self.assertIsNone(vault)
        self.assertTrue(all(path is None for path in paths.values()))

    def test_relative_root_and_nested_folders(self):
        self.config(vault_dir="My Campaign", sessions_dir="Story/Act 2/Sessions",
                    players_dir="Characters/Players", improv_note="Tables/rolls.md")
        vault, paths = server.load_vault_config(self.root, {})
        self.assertEqual(vault, self.vault)
        self.assertEqual(paths["sessions_dir"], self.vault / "Story/Act 2/Sessions")
        self.assertEqual(paths["players_dir"], self.vault / "Characters/Players")
        self.assertEqual(paths["improv_note"], self.vault / "Tables/rolls.md")
        self.assertEqual(paths["npcs_dir"], self.vault / "NPCs")

    def test_environment_override_and_disable(self):
        self.config(vault_dir="missing")
        vault, _ = server.load_vault_config(self.root, {"DMC_VAULT_DIR": str(self.vault)})
        self.assertEqual(vault, self.vault)
        vault, _ = server.load_vault_config(self.root, {"DMC_VAULT_DIR": ""})
        self.assertIsNone(vault)

    def test_home_expansion(self):
        self.config(vault_dir="~/My Campaign")
        with patch.dict(os.environ, {"HOME": str(self.root), "USERPROFILE": str(self.root)}):
            vault, _ = server.load_vault_config(self.root, {})
        self.assertEqual(vault, self.vault)

    def test_invalid_configuration(self):
        for values in [
            {"vault_dir": "missing"},
            {"vault_dir": 123},
            {"session_dir": "typo"},
            {"sessions_dir": "../outside"},
            {"sessions_dir": str(self.root)},
            {"sessions_dir": ""},
            {"sessions_dir": None},
        ]:
            with self.subTest(values=values):
                self.config(**values)
                with self.assertRaises(ValueError):
                    server.load_vault_config(self.root, {})

    def test_wrong_content_type(self):
        (self.vault / "Sessions").write_text("not a directory")
        self.config(vault_dir=str(self.vault))
        with self.assertRaisesRegex(ValueError, "wrong file type"):
            server.load_vault_config(self.root, {})

    def test_malformed_json(self):
        for content in ["{", "[]"]:
            (self.root / "config.json").write_text(content)
            with self.assertRaises(ValueError):
                server.load_vault_config(self.root, {})


class VaultApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.settings = patch.multiple(
            server, VAULT_DIR=None, SESSIONS_DIR=None, NPCS_DIR=None,
            PLAYERS_DIR=None, IMPROV_NOTE=None, MAP_FOLDERS=[],
            DATA_DIR=self.root / "data", relations_cache={"key": None, "value": None},
        )
        self.settings.start()
        self.addCleanup(self.settings.stop)
        self.client = TestClient(TestServer(server.make_app()))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)

    async def test_vaultless_endpoints_and_ui(self):
        for endpoint, key in [
            ("sessions", "sessions"), ("npcs", "npcs"), ("players", "players"),
            ("relations", "nodes"), ("improv", "tables"),
        ]:
            response = await self.client.get("/api/" + endpoint)
            self.assertEqual(response.status, 200)
            self.assertEqual((await response.json())[key], [])
        for endpoint in ["vault-note?target=Missing", "vault-file?path=image.png",
                         "npc?target=Missing", "note?session=Missing", "encounters?session=Missing"]:
            response = await self.client.get("/api/" + endpoint)
            self.assertEqual(response.status, 404)
        response = await self.client.get("/")
        self.assertEqual(response.status, 200)
        async with self.client.ws_connect("/ws/ui") as ws:
            state = await ws.receive_json()
            self.assertEqual(state["type"], "state")
            self.assertEqual(state["clocks"], [])

    async def test_custom_layout_and_dashboard_target(self):
        sessions = self.root / "Story/Act 2/Sessions"
        players = self.root / "Characters/Players"
        sessions.mkdir(parents=True)
        players.mkdir(parents=True)
        (sessions / "Session 1.md").write_text("## Encounters\n[[Meeting]]")
        (self.root / "Meeting.md").write_text("# Encounter - Meeting\n**Scene**: Inn")
        (players / "Player Dashboard.md").write_text("## Sam\n**Hero - wizard**")
        (players / "Hero.md").write_text("# Hero")
        with patch.multiple(server, VAULT_DIR=self.root, SESSIONS_DIR=sessions, PLAYERS_DIR=players):
            response = await self.client.get("/api/sessions")
            self.assertEqual((await response.json())["sessions"], ["Session 1"])
            response = await self.client.get("/api/encounters", params={"session": "Session 1"})
            self.assertEqual((await response.json())["encounters"][0]["scene"], "Inn")
            response = await self.client.get("/api/players")
            result = await response.json()
            self.assertEqual(result["dashboard"], "Characters/Players/Player Dashboard")
            response = await self.client.get("/api/vault-note", params={"target": result["dashboard"]})
            self.assertEqual(response.status, 200)
