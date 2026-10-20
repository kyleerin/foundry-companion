#!/bin/sh
# Start the DM Companion server at http://localhost:4000
cd "$(dirname "$0")" && exec .venv/bin/python server/server.py
