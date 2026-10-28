"""Exercise fresh/repeated setup and a real server on port 4100 in a disposable copy."""

import argparse
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parent.parent


def probe(root):
    # Imported only under the freshly installed interpreter.
    import asyncio
    import aiohttp

    async def check():
        async with aiohttp.ClientSession() as client:
            for vault in (False, True):
                env = dict(os.environ, DMC_PORT="4100",
                           DMC_DATA_DIR=str(root / "smoke-data"),
                           DMC_VAULT_DIR=str(root / "examples/sample-vault") if vault else "")
                with (root / "server.log").open("w", encoding="utf-8") as log:
                    process = subprocess.Popen(
                        [sys.executable, str(root / "server/server.py")],
                        cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT,
                    )
                    try:
                        deadline = time.monotonic() + 20
                        while True:
                            if process.poll() is not None:
                                raise RuntimeError("Test server exited: " + (root / "server.log").read_text())
                            try:
                                async with client.get("http://127.0.0.1:4100/") as response:
                                    assert response.status == 200
                                    assert "DM Companion" in await response.text()
                                break
                            except aiohttp.ClientConnectorError:
                                if time.monotonic() > deadline:
                                    raise RuntimeError("Test server did not start")
                                await asyncio.sleep(0.1)
                        async with client.get("http://127.0.0.1:4100/api/sessions") as response:
                            sessions = (await response.json())["sessions"]
                            assert sessions == (["Session 1 - The Missing Lantern"] if vault else [])
                        async with client.ws_connect(
                            "http://127.0.0.1:4100/ws/ui", origin="http://localhost:4100"
                        ) as ws:
                            state = await ws.receive_json(timeout=5)
                            assert state["type"] == "state" and not state["foundryConnected"]
                            await ws.send_json({"type": "command", "requestId": "smoke", "command": "refresh"})
                            result = await ws.receive_json(timeout=5)
                            assert result["requestId"] == "smoke" and result["ok"] is False
                    finally:
                        # Only the child process we created; never discover/kill a user's server.
                        process.terminate()
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                print("HTTP/WebSocket smoke passed:", "sample vault" if vault else "vaultless")
    asyncio.run(check())


def validate():
    # Fail rather than attaching to or stopping an existing process on the test port.
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 4100))
    output = ROOT / "dist"
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="fresh-install-", dir=output) as directory:
        root = Path(directory).resolve()
        for name in ("setup_env.py", "requirements.txt", "run.sh"):
            shutil.copy2(ROOT / name, root / name)
        for name in ("server", "web", "examples"):
            shutil.copytree(ROOT / name, root / name, ignore=shutil.ignore_patterns("__pycache__"))
        # A sentinel confirms repeated setup preserves application data.
        (root / "data").mkdir()
        sentinel = root / "data/keep.txt"
        sentinel.write_text("preserve me", encoding="utf-8")
        for _ in range(2):
            subprocess.run([sys.executable, "setup_env.py"], cwd=root, check=True)
        assert sentinel.read_text(encoding="utf-8") == "preserve me"
        python = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run([str(python), str(Path(__file__).resolve()), "--probe", str(root)], check=True)
        subprocess.run([str(python), "-m", "pip", "freeze"], check=True)
    print("PASS: fresh install, repeated setup, data preservation, and real server smoke")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.probe:
        probe(args.probe)
    else:
        validate()
