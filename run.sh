#!/bin/sh
# Start the DM Companion server at http://localhost:4000
cd "$(dirname "$0")" || exit 1
PY=.venv/bin/python
[ -x "$PY" ] || PY=.venv/Scripts/python.exe
if [ ! -x "$PY" ]; then
    echo "Python environment not found. Run: python3 setup_env.py" >&2
    echo "On Windows, run: py -3 setup_env.py" >&2
    exit 1
fi
if ! "$PY" -c 'import aiohttp' 2>/dev/null; then
    echo "Server dependencies are missing. Rerun: python3 setup_env.py" >&2
    echo "On Windows, run: py -3 setup_env.py" >&2
    exit 1
fi
exec "$PY" server/server.py
