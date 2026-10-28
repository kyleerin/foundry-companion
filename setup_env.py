"""Create the local Python environment: python3 setup_env.py (Windows: py -3 setup_env.py)."""

import os
from pathlib import Path
import subprocess
import sys
import venv


def main():
    if sys.version_info < (3, 9):
        print("DM Companion requires Python 3.9 or newer.", file=sys.stderr)
        return 1

    root = Path(__file__).resolve().parent
    environment = root / ".venv"
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    try:
        if not python.is_file():
            print("Creating .venv...", flush=True)
            venv.EnvBuilder(with_pip=True).create(environment)
        subprocess.run(
            [str(python), "-m", "pip", "install", "-r", str(root / "requirements.txt")],
            check=True,
        )
        subprocess.run([str(python), "-m", "pip", "check"], check=True)
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"Setup failed: {error}", file=sys.stderr)
        print(
            "Check your internet connection and Python venv/pip installation, "
            "then rerun this command. See README.md for troubleshooting.",
            file=sys.stderr,
        )
        return 1

    command = r".\.venv\Scripts\python.exe server\server.py" if os.name == "nt" else "./run.sh"
    print(f"\nSetup complete. Start DM Companion with:\n  {command}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
