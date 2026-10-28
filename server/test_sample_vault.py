"""Keep the shipped fictional vault compatible with the real API."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from aiohttp.test_utils import TestClient, TestServer
import server


class SampleVaultTests(unittest.IsolatedAsyncioTestCase):
    async def test_sample_workflow(self):
        root = Path(__file__).resolve().parent.parent
        vault = root / "examples/sample-vault"
        with tempfile.TemporaryDirectory() as data, patch.multiple(
            server, VAULT_DIR=vault, SESSIONS_DIR=vault / "Sessions",
            NPCS_DIR=vault / "NPCs", PLAYERS_DIR=vault / "Players",
            IMPROV_NOTE=vault / "improv.md", DATA_DIR=Path(data),
            MAP_FOLDERS=[(vault / folder, kind, {"Player Dashboard"})
                         for folder, kind in [("NPCs", "npc"), ("Players", "pc"),
                                              ("Factions", "faction"), ("Locations", "location")]],
            relations_cache={"key": None, "value": None},
        ):
            async with TestClient(TestServer(server.make_app())) as client:
                async def get(endpoint, **params):
                    response = await client.get("/api/" + endpoint, params=params)
                    self.assertEqual(response.status, 200)
                    return await response.json()

                sessions = (await get("sessions"))["sessions"]
                self.assertEqual(sessions, ["Session 1 - The Missing Lantern"])
                encounters = (await get("encounters", session=sessions[0]))["encounters"]
                self.assertEqual(len(encounters), 1)
                self.assertEqual(encounters[0]["scene"], "Lantern Quay")
                self.assertEqual(encounters[0]["npcs"], ["Mira Reed"])
                npc = await get("npc", target="Mira Reed")
                self.assertEqual(npc["stats"]["hp"], 9)
                self.assertEqual(npc["stats"]["abilities"]["wis"], 14)
                players = (await get("players"))["players"]
                self.assertEqual(players[0]["player"], "Alex")
                self.assertEqual(players[0]["class"], "ranger")
                self.assertEqual(len(players[0]["storylines"]), 2)
                graph = await get("relations", session=sessions[0])
                self.assertEqual(len(graph["nodes"]), 4)
                self.assertEqual(len(graph["session"]), 4)
                self.assertTrue(graph["edges"])
                tables = (await get("improv"))["tables"]
                self.assertEqual(len(tables), 3)
                self.assertTrue(tables[1]["split"])
                # Every wikilink should resolve; no hidden dependency on a private vault.
                for note in vault.rglob("*.md"):
                    for link in server.WIKILINK_RE.finditer(note.read_text(encoding="utf-8")):
                        self.assertIsNotNone(server.resolve_note(link.group(1)), link.group(1))
