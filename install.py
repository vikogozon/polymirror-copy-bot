#!/usr/bin/env python3
"""One-time setup script. Run this first before starting the bot."""
import os
import sys
import subprocess
import shutil
from pathlib import Path

ROOT = Path(__file__).parent
VENV = ROOT / "venv"


def run(cmd, **kw):
    print(f"  > {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, **kw)
    if result.returncode != 0:
        print(f"\nERROR: command failed with exit code {result.returncode}")
        sys.exit(result.returncode)


def _install_python313_linux():
    print("\n  Python 3.13 not found. Installing automatically...")
    cmds = [
        ["sudo", "apt-get", "install", "-y", "software-properties-common"],
        ["sudo", "add-apt-repository", "ppa:deadsnakes/ppa", "-y"],
        ["sudo", "apt-get", "update", "-q"],
        ["sudo", "apt-get", "install", "-y", "python3.13", "python3.13-venv"],
    ]
    for cmd in cmds:
        result = subprocess.run(cmd)
        if result.returncode != 0:
            print(f"\n[ERROR] Failed to install Python 3.13 automatically.")
            print("  Try running manually:")
            print("      sudo apt-get install -y software-properties-common")
            print("      sudo add-apt-repository ppa:deadsnakes/ppa -y")
            print("      sudo apt-get update -q")
            print("      sudo apt-get install -y python3.13 python3.13-venv")
            print("      python3.13 install.py")
            sys.exit(1)
    print("\n  Python 3.13 installed successfully.")


def _ensure_python313():
    if sys.version_info >= (3, 13):
        return  # already running 3.13+

    # Check if python3.13 is already available
    py313 = shutil.which("python3.13")

    if py313 is None and sys.platform != "win32":
        _install_python313_linux()
        py313 = shutil.which("python3.13")

    if py313:
        print(f"\n  Restarting with Python 3.13 ({py313})...")
        os.execv(py313, [py313] + sys.argv)
        # execv replaces the current process — code below never runs

    # Windows or install failed
    print(f"\n[ERROR] Python 3.13 or higher is required.")
    print(f"        You are running Python {sys.version_info.major}.{sys.version_info.minor}.")
    if sys.platform == "win32":
        print("\n  Download Python 3.13 from: https://www.python.org/downloads/")
        print("  Make sure to check 'Add Python to PATH' during install.")
    sys.exit(1)


def main():
    print("=" * 50)
    print("  PolyMirror — Setup")
    print("=" * 50)

    _ensure_python313()

    # Python executable inside future venv
    if sys.platform == "win32":
        venv_python = VENV / "Scripts" / "python.exe"
    else:
        venv_python = VENV / "bin" / "python"

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
