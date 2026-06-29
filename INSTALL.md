# PolyMirror — Installation Guide

## Requirements
- Python 3.10 or higher
- A Polymarket account with funds
- Your Polymarket API credentials

## Setup (Windows)

```
python -m venv venv
venv\Scripts\activate
pip install -e ".[live,dashboard]"
```

## Setup (Linux / VPS)

```
python3 -m venv venv
source venv/bin/activate
pip install -e ".[live,dashboard]"
```

## Configure .env

Open the `.env` file and fill in your details:

```
WATCHLIST_WALLETS=0x...   # wallet you want to copy
CLOB_PRIVATE_KEY=0x...    # MetaMask -> Account Details -> Export Private Key
CLOB_API_KEY=...          # polymarket.com -> Settings -> API Keys
CLOB_FUNDER=0x...         # your 0x address on polymarket.com
LICENSE_KEY=POLY-...      # provided by seller
FIXED_TRADE_USDC=5.0      # USD amount per copied trade
```

## Run

```
python run_dashboard.py
```

Then open your browser at: http://localhost:8080

Click START BOT when ready. The bot only copies trades that happen after you click START.

## Notes
- The data/ folder and database are created automatically on first run.
- To close all open positions: python close_all.py
- The bot requires an active internet connection at all times.
