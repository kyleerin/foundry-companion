"""Encounter parsing tests that do not require aiohttp."""
import ast
from pathlib import Path
import re
import tempfile
import unittest


class EncounterTests(unittest.TestCase):
    def parse(self, text):
        source = ast.parse(Path(__file__).with_name("server.py").read_text(encoding="utf-8"))
        names = {"HEADING_RE", "WIKILINK_RE", "META_RE"}
        nodes = [n for n in source.body if
                 (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in n.targets))
                 or (isinstance(n, ast.FunctionDef) and n.name == "parse_encounter")]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Encounter.md"
            path.write_text(text, encoding="utf-8")
            namespace = {"re": re, "VAULT_DIR": Path(directory)}
            exec(compile(ast.Module(body=nodes, type_ignores=[]), "server.py", "exec"), namespace)
            return namespace["parse_encounter"]("Encounter", path)

    def test_fields(self):
        result = self.parse("# Encounter\n**Scene**: Inn\n**NPCs**: [[NPCs/Slug|Slug]], [[Belle]], [[Belle]]\n## Story\n[[Other]]")
        self.assertEqual(result["scene"], "Inn")
        self.assertEqual(result["npcs"], ["NPCs/Slug", "Belle"])

    def test_headings(self):
        result = self.parse("## Scene\n[[Inn]]\n## NPCs\n- [[Slug]]\n- Belle\n## Overview\n[[Other]]")
        self.assertEqual(result["scene"], "Inn")
        self.assertEqual(result["npcs"], ["Slug", "Belle"])

    def test_no_inferred_cast(self):
        result = self.parse("**Location**: [[Inn]]\n## Story\n[[Slug]]")
        self.assertEqual(result["scene"], "")
        self.assertEqual(result["npcs"], [])


if __name__ == "__main__":
    unittest.main()
