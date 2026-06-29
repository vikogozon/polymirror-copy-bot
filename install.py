#!/usr/bin/env python3
"""One-time setup script. Run this first before starting the bot."""
import os
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent
VENV = ROOT / "venv"

def run(cmd, **kw):
    print(f"  > {' '.join(cmd)}")
    result = subprocess.run(cmd, **kw)
    if result.returncode != 0:
        print(f"\nERROR: command failed with exit code {result.returncode}")
        sys.exit(result.returncode)

def main():
    print("=" * 50)
    print("  PolyMirror — Setup")
    print("=" * 50)

    # Python executable inside future venv
    if sys.platform == "win32":
        venv_python = VENV / "Scripts" / "python.exe"
        venv_pip    = VENV / "Scripts" / "pip.exe"
    else:
        venv_python = VENV / "bin" / "python"
        venv_pip    = VENV / "bin" / "pip"

    # 1. Create venv
    if not VENV.exists():
        print("\n[1/2] Creating virtual environment...")
        run([sys.executable, "-m", "venv", str(VENV)])
    else:
        print("\n[1/2] Virtual environment already exists, skipping.")

    # 2. Install dependencies
    print("\n[2/2] Installing dependencies...")
    run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip", "-q"])
    run([str(venv_python), "-m", "pip", "install", "-e", ".[live,dashboard]", "-q"])

    print("\n" + "=" * 50)
    print("  Setup complete!")
    print("=" * 50)
    if sys.platform == "win32":
        print("\n  To start the bot, run:\n")
        print("      start.bat\n")
    else:
        print("\n  To start the bot, run:\n")
        print("      bash start.sh\n")

if __name__ == "__main__":
    main()
