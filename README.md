# PolyMirror — Polymarket Copy Trading Bot

![PolyMirror Dashboard](preview.png)

Automatically copy trades from any Polymarket wallet in real time. Configure everything from the browser dashboard — no config files, no terminal commands after setup.

---

## Quick Start

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

Open your browser at **http://localhost:8080**

### Mac

```bash
git clone https://github.com/vikogozon/polymirror-copy-bot.git
cd polymirror-copy-bot
python3 install.py
bash start.sh
```

Open your browser at **http://localhost:8080**

---

## First Time Setup

1. **Activate your license** — paste your license key and click ACTIVATE
2. **Enter your Polymarket credentials** — private key, API key, and the wallet address you want to copy
3. **Set your trade size** — fixed USDC amount per trade or percentage of capital
4. **Click START** — the bot begins copying trades in real time

Everything is configured directly from the dashboard. No need to edit any files.

---

## Updating

To get the latest version:

```bash
cd polymirror-copy-bot
git pull
python3 install.py
```

Then restart the bot normally (`start.bat` or `bash start.sh`). Your credentials and settings are preserved.

---

## Run in the Background

### Linux / VPS — keep running after closing the terminal

**Option 1 — screen (recommended, lets you reconnect later):**
```bash
screen -S polymirror
bash start.sh
# Detach with Ctrl+A then D
# Reconnect later with: screen -r polymirror
```

**Option 2 — nohup (simple, runs silently):**
```bash
nohup bash start.sh > polymirror.log 2>&1 &
echo "Bot PID: $!"
# View logs: tail -f polymirror.log
# Stop: kill <PID>
```

**Option 3 — systemd (auto-starts on reboot):**
```bash
sudo nano /etc/systemd/system/polymirror.service
```
Paste this (replace `/home/ubuntu` with your home directory):
```ini
[Unit]
Description=PolyMirror Copy Trading Bot
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/polymirror-copy-bot
ExecStart=/home/ubuntu/polymirror-copy-bot/venv/bin/python run_dashboard.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```
Then enable it:
```bash
sudo systemctl daemon-reload
sudo systemctl enable polymirror
sudo systemctl start polymirror
# Check status: sudo systemctl status polymirror
# View logs:    sudo journalctl -u polymirror -f
```

### Windows — keep running after closing the window

**Option 1 — minimize to tray:**
Double-click `start.bat` normally. Minimize the window. The bot keeps running.

**Option 2 — run hidden at Windows startup:**
Press `Win+R`, type `shell:startup`, press Enter. Create a shortcut to `start.bat` in that folder. The bot will start automatically when Windows boots, with no visible window.

---

## Requirements

- Python 3.14 or higher
- A funded Polymarket account (wallet-based, not email sign-up)
- A valid PolyMirror license key

---

> Trading on prediction markets involves risk of loss. Always test with small amounts first.
