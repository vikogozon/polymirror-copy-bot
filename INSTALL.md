# PolyMirror — Installation Guide

## Requirements

- Python 3.14 or higher
- A funded Polymarket account (wallet-based login, not email)
- A valid PolyMirror license key

---

## Step 1 — Install

### Windows
```
python install.py
```
If Python 3.14 is not installed, download it from https://www.python.org/downloads/
and make sure to check **"Add Python to PATH"** during install.

### Linux / VPS
```bash
python3 install.py
```
If Python 3.14 is missing, the script installs it automatically.

### Mac
```bash
python3 install.py
```
If Python 3.14 is missing, download it from https://www.python.org/downloads/

---

## Step 2 — Start

### Windows
```
start.bat
```
Or double-click `start.bat` in File Explorer.

### Linux / Mac
```bash
bash start.sh
```

---

## Step 3 — Open the dashboard

Go to **http://localhost:8080** in your browser.

1. Enter your license key and click **ACTIVATE**
2. Fill in your Polymarket credentials in the Configuration panel
3. Enter the wallet address you want to copy
4. Set your trade size
5. Click **START BOT**

---

## Updating to a new version

```bash
git pull
python3 install.py
```

Restart the bot. Your settings and credentials are preserved.

---

## Useful commands

| What | Command |
|---|---|
| Close all open positions | `python close_all.py` |
| Run in background (Linux) | `nohup bash start.sh > polymirror.log 2>&1 &` |
| View background logs | `tail -f polymirror.log` |
| Stop background bot | `kill $(cat polymirror.pid)` or find PID with `ps aux \| grep python` |

---

## Troubleshooting

**Window closes immediately on Windows**
An error occurred on startup. Re-run from a terminal to see the message:
```
python run_dashboard.py
```

**Port 8080 already in use**
Another process is using the port. Find and stop it:
```bash
# Linux
sudo lsof -i :8080
# Windows
netstat -ano | findstr :8080
```

**Bot not copying trades**
- Make sure you clicked **START BOT** in the dashboard
- The bot only copies trades that happen **after** you click START
- Check the System Log panel for error messages
