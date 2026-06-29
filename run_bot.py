"""
run_bot.py
----------
Launcher for the copypoly bot with:
  - Automatic restart on crash (with back-off)
  - Log rotation (10 MB cap, 3 backups)
  - Graceful shutdown on Ctrl+C / SIGTERM
  - Timestamped console + file output

Usage:
    python run_bot.py
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import signal
import sys
import time

# ── working directory always at project root ──────────────────────────────────
os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.makedirs("data", exist_ok=True)

# ── logging: console + rotating file ─────────────────────────────────────────
LOG_PATH = os.path.join("data", "bot.log")

_fmt = logging.Formatter(
    fmt="%(asctime)s  %(levelname)-5s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_file_handler = logging.handlers.RotatingFileHandler(
    LOG_PATH, maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8"
)
_file_handler.setFormatter(_fmt)

_console_handler = logging.StreamHandler(sys.stdout)
_console_handler.setFormatter(_fmt)

logging.basicConfig(level=logging.INFO, handlers=[_file_handler, _console_handler])
log = logging.getLogger("copypoly.launcher")

# Redirect bare print() calls from the bot internals to the same logger
class _PrintToLog:
    def write(self, msg: str) -> None:
        msg = msg.rstrip("\n")
        if msg:
            log.info(msg)
    def flush(self) -> None:
        pass

sys.stdout = _PrintToLog()  # type: ignore[assignment]

# ── graceful shutdown ─────────────────────────────────────────────────────────
_shutdown = False

def _handle_signal(signum: int, _frame: object) -> None:
    global _shutdown
    log.info(f"Signal {signum} received — shutting down after current poll.")
    _shutdown = True

signal.signal(signal.SIGINT,  _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)

# ── auto-restart loop ─────────────────────────────────────────────────────────
MAX_RESTARTS  = 50          # safety cap
BACKOFF_START = 5           # seconds before first restart
BACKOFF_MAX   = 120         # cap back-off at 2 minutes

def _run() -> None:
    from copypoly.cli import main as copypoly_main
    copypoly_main(["run"])


def _set_start_timestamp() -> None:
    now = int(time.time())
    os.environ["START_AFTER_TIMESTAMP"] = str(now)
    log.info(f"START_AFTER_TIMESTAMP set to {now} — only trades from now on will be copied.")


def main() -> None:
    log.info("=" * 60)
    log.info("copypoly bot launcher starting")
    log.info("=" * 60)

    _set_start_timestamp()

    restarts = 0
    backoff  = BACKOFF_START

    while not _shutdown and restarts <= MAX_RESTARTS:
        try:
            log.info(f"Starting bot (run #{restarts + 1})")
            _run()
            # _run() only returns if run_forever() exits cleanly (e.g. KeyboardInterrupt
            # was converted to _shutdown=True).  Break out of the restart loop.
            log.info("Bot exited cleanly.")
            break
        except KeyboardInterrupt:
            log.info("KeyboardInterrupt — stopping.")
            break
        except Exception as exc:
            restarts += 1
            log.exception(f"Bot crashed (restart {restarts}/{MAX_RESTARTS}): {exc}")
            if _shutdown or restarts > MAX_RESTARTS:
                break
            log.info(f"Restarting in {backoff}s …")
            time.sleep(backoff)
            backoff = min(backoff * 2, BACKOFF_MAX)

    log.info("Launcher stopped.")


if __name__ == "__main__":
    main()

