#!/usr/bin/env python3
"""One-time setup script. Run this first before starting the bot."""
import os
import sys
import subprocess
import shutil
from pathlib import Path

ROOT = Path(__file__).parent
VENV = ROOT / "venv"

_PY_MAJOR = 3
_PY_MINOR = 14   # PyArmor runtime requires Python 3.14+


def run(cmd, **kw):
    print(f"  > {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, **kw)
    if result.returncode != 0:
        print(f"\nERROR: command failed with exit code {result.returncode}")
        sys.exit(result.returncode)


def _install_python_linux():
    py = f"python{_PY_MAJOR}.{_PY_MINOR}"
    print(f"\n  {py} not found. Installing automatically...")
    cmds = [
        ["sudo", "apt-get", "install", "-y", "software-properties-common"],
        ["sudo", "add-apt-repository", "ppa:deadsnakes/ppa", "-y"],
        ["sudo", "apt-get", "update", "-q"],
        ["sudo", "apt-get", "install", "-y", py, f"{py}-venv"],
    ]
    for cmd in cmds:
        result = subprocess.run(cmd)
        if result.returncode != 0:
            print(f"\n[ERROR] Failed to install {py} automatically.")
            print("  Try running manually:")
            print("      sudo apt-get install -y software-properties-common")
            print(f"      sudo add-apt-repository ppa:deadsnakes/ppa -y")
            print(f"      sudo apt-get update -q")
            print(f"      sudo apt-get install -y {py} {py}-venv")
            print(f"      {py} install.py")
            sys.exit(1)
    print(f"\n  {py} installed successfully.")


def _ensure_python():
    if sys.version_info >= (_PY_MAJOR, _PY_MINOR):
        return  # already running correct version

    py_bin = f"python{_PY_MAJOR}.{_PY_MINOR}"
    found = shutil.which(py_bin)

    if found is None and sys.platform != "win32":
        _install_python_linux()
        found = shutil.which(py_bin)

    if found:
        print(f"\n  Restarting with Python {_PY_MAJOR}.{_PY_MINOR} ({found})...")
        os.execv(found, [found] + sys.argv)

    # Fallback error
    print(f"\n[ERROR] Python {_PY_MAJOR}.{_PY_MINOR} or higher is required.")
    print(f"        You are running Python {sys.version_info.major}.{sys.version_info.minor}.")
    if sys.platform == "win32":
        print(f"\n  Download Python {_PY_MAJOR}.{_PY_MINOR} from: https://www.python.org/downloads/")
        print("  Make sure to check 'Add Python to PATH' during install.")
    sys.exit(1)


def main():
    print("=" * 50)
    print("  PolyMirror — Setup")
    print("=" * 50)

    _ensure_python()

    if sys.platform == "win32":
        venv_python = VENV / "Scripts" / "python.exe"
    else:
        venv_python = VENV / "bin" / "python"

    if not VENV.exists():
        print("\n[1/2] Creating virtual environment...")
        run([sys.executable, "-m", "venv", str(VENV)])
    else:
        print("\n[1/2] Virtual environment already exists, skipping.")

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
