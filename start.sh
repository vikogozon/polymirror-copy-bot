#!/usr/bin/env bash
set -e
if [ ! -f "venv/bin/python" ]; then
    echo "[ERROR] Run install.py first:  python3 install.py"
    exit 1
fi
venv/bin/python run_dashboard.py
