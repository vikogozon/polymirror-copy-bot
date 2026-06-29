"""Launch the PolyMirror web dashboard."""

import os
import time

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Trades that happened before this server started will be ignored.
os.environ["START_AFTER_TIMESTAMP"] = str(int(time.time()))

from copypoly.dashboard import run_dashboard

if __name__ == "__main__":
    run_dashboard()
