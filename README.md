# PolyMirror — Polymarket Copy Trading Bot

![PolyMirror Dashboard](preview.png)

Automatically copy trades from any Polymarket wallet in real time. Configure everything from the browser dashboard — no config files, no terminal commands after setup.

---

## Installation

### Windows

1. Install **Python 3.14+** from [python.org](https://www.python.org/downloads/) — check **"Add Python to PATH"** during install
2. Download or clone this repository
3. Open a terminal in the folder and run:
   ```
   python install.py
   ```
4. Double-click **`start.bat`** to launch the bot
5. Open your browser at **http://localhost:8080**

### Linux / VPS

```bash
git clone https://github.com/vikogozon/polymirror-copy-bot.git
cd polymirror-copy-bot
python3 install.py
bash start.sh
```

Then open your browser at **http://localhost:8080**

### Mac

```bash
git clone https://github.com/vikogozon/polymirror-copy-bot.git
cd polymirror-copy-bot
python3 install.py
bash start.sh
```

Then open your browser at **http://localhost:8080**

---

## First Time Setup

1. **Activate your license** — paste your license key and click ACTIVATE
2. **Enter your Polymarket credentials** — private key, API key, and the wallet address you want to copy
3. **Set your trade size** — fixed USDC amount per trade or percentage of capital
4. **Click START** — the bot begins copying trades in real time

Everything is configured directly from the dashboard. No need to edit any files.

---

## Requirements

- Python 3.14 or higher
- A funded Polymarket account (wallet-based, not email sign-up)
- A valid PolyMirror license key

---

> Trading on prediction markets involves risk of loss. Always test with small amounts first.
