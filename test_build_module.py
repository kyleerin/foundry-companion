import copy
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import build_module as builder


class ModuleBuildTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads(
            (builder.ROOT / "foundry-module/module.json").read_text()
        )

    def test_reproducible_and_allowlisted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "foundry-module/scripts").mkdir(parents=True)
            for name in builder.MODULE_FILES:
                (root / "foundry-module" / name).write_bytes(
                    (builder.ROOT / "foundry-module" / name).read_bytes()
                )
            (root / "LICENSE").write_bytes((builder.ROOT / "LICENSE").read_bytes())
            (root / "foundry-module/config.json").write_text("private")
            (root / "foundry-module/scripts/debug.js").write_text("development")
            first = builder.build(root, root / "first", "v" + self.manifest["version"])
            second = builder.build(root, root / "second")
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(first) as archive:
                self.assertEqual(set(archive.namelist()), set(builder.PACKAGE_FILES))
                self.assertEqual(archive.read("module.json"), (first.parent / "module.json").read_bytes())

    def test_reject_mismatched_tag(self):
        with self.assertRaises(ValueError):
            builder.validate_manifest(self.manifest, "v999.0.0")

    def test_reject_invalid_manifest_references(self):
        for key, value in (
            ("version", "0.2.0"),
            ("download", "https://example.com/wrong.zip"),
            ("manifest", "https://example.com/module.json"),
            ("esmodules", ["missing.js"]),
            ("license", "../LICENSE"),
            ("styles", ["missing.css"]),
        ):
            with self.subTest(key=key), self.assertRaises(ValueError):
                manifest = copy.deepcopy(self.manifest)
                manifest[key] = value
                builder.validate_manifest(manifest)

    def test_reject_archive_extra_file(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = builder.build(output=directory)
            with zipfile.ZipFile(archive) as package:
                payload = {name: package.read(name) for name in package.namelist()}
            with zipfile.ZipFile(archive, "a") as package:
                package.writestr("config.json", "private")
            with self.assertRaises(ValueError):
                builder.validate_archive(archive, payload["module.json"], payload)


if __name__ == "__main__":
    unittest.main()
