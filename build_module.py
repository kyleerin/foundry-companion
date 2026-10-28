"""Build and validate the Foundry release assets using only Python 3.9+."""

import argparse
import json
from pathlib import Path
import re
import zipfile


ROOT = Path(__file__).resolve().parent
PROJECT_URL = "https://github.com/kyleerin/foundry-companion"
# Deliberately explicit: new runtime assets must be reviewed before shipping.
MODULE_FILES = ("module.json", "scripts/bridge.js")
PACKAGE_FILES = (*MODULE_FILES, "LICENSE")


def validate_manifest(manifest, tag=None):
    version = manifest.get("version", "")
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("version must be a stable major.minor.patch version")
    expected_tag = "v" + version
    if tag is not None and tag != expected_tag:
        raise ValueError(f"release tag must be {expected_tag}, not {tag}")
    expected = {
        "id": "dm-companion",
        "url": PROJECT_URL,
        "manifest": f"{PROJECT_URL}/releases/latest/download/module.json",
        "download": f"{PROJECT_URL}/releases/download/{expected_tag}/dm-companion.zip",
        "license": "LICENSE",
        "esmodules": ["scripts/bridge.js"],
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise ValueError(f"manifest {key} must be {value!r}")
    # Reject newly declared assets until the package allowlist supports them.
    for key in ("scripts", "styles", "packs", "languages"):
        if manifest.get(key):
            raise ValueError(f"add packaging support before declaring {key}")
    if not manifest.get("title") or not manifest.get("compatibility", {}).get("minimum"):
        raise ValueError("title and compatibility.minimum are required")


def validate_archive(archive, manifest_bytes, payload, tag=None):
    validate_manifest(json.loads(manifest_bytes), tag)
    with zipfile.ZipFile(archive) as package:
        if sorted(package.namelist()) != sorted(PACKAGE_FILES):
            raise ValueError("ZIP must contain only the approved root-level module files")
        if package.testzip() is not None:
            raise ValueError("ZIP failed its CRC check")
        for name, content in payload.items():
            if package.read(name) != content:
                raise ValueError(f"ZIP contents differ from source: {name}")
        if package.read("module.json") != manifest_bytes:
            raise ValueError("standalone and packaged manifests differ")


def build(root=ROOT, output=None, tag=None):
    root = Path(root).resolve()
    output = Path(output) if output is not None else root / "dist"
    payload = {}
    for name in MODULE_FILES:
        source = root / "foundry-module" / name
        if source.resolve() != source:
            raise ValueError(f"refusing symlinked package source: {source}")
        payload[name] = source.read_bytes()
    payload["LICENSE"] = (root / "LICENSE").read_bytes()
    manifest_bytes = payload["module.json"]
    validate_manifest(json.loads(manifest_bytes), tag)
    output.mkdir(parents=True, exist_ok=True)
    archive = output / "dm-companion.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
        for name in sorted(payload):
            # Fixed timestamps and modes make repeated builds reproducible.
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            package.writestr(info, payload[name])
    (output / "module.json").write_bytes(manifest_bytes)
    validate_archive(archive, (output / "module.json").read_bytes(), payload, tag)
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="Require this release tag to match the manifest")
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    try:
        archive = build(output=args.output, tag=args.tag)
    except (ValueError, OSError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"Module build failed: {exc}\n")
    print(f"Built and validated {archive} and its standalone module.json")


if __name__ == "__main__":
    main()
