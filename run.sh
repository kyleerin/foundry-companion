#!/bin/sh
# Start the DM Companion server at http://localhost:4000
cd "$(dirname "$0")" || exit 1
PY=.venv/bin/python
[ -x "$PY" ] || PY=.venv/Scripts/python.exe
exec "$PY" server/server.py
