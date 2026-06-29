"""Blockchain WebSocket watcher — wakes the bot instantly when the watched wallet trades."""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Callable, Optional

log = logging.getLogger(__name__)

_CTF_EXCHANGE  = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
_NEG_RISK_ADDR = "0xC5d563A36AE78145C45a50134d48A1215220f80a"

_ENDPOINTS = [
    "wss://polygon-bor-rpc.publicnode.com",
    "wss://polygon.drpc.org",
]


def start_watcher(
    wallet: str,
    on_trade: Callable[[], None],
    stop: threading.Event,
    on_connected: Optional[Callable[[str], None]] = None,
) -> threading.Thread:
    t = threading.Thread(
        target=_run,
        args=(wallet.lower(), on_trade, stop, on_connected),
        daemon=True,
        name="chain-watcher",
    )
    t.start()
    return t


def _run(
    wallet: str,
    on_trade: Callable[[], None],
    stop: threading.Event,
    on_connected: Optional[Callable[[str], None]],
) -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_watch_loop(wallet, on_trade, stop, on_connected))
    except Exception as exc:
        log.debug(f"Watcher exited: {exc}")
    finally:
        loop.close()


async def _watch_loop(
    wallet: str,
    on_trade: Callable[[], None],
    stop: threading.Event,
    on_connected: Optional[Callable[[str], None]],
) -> None:
    padded = "0x000000000000000000000000" + wallet[2:]
    backoff = 3.0

    while not stop.is_set():
        for url in _ENDPOINTS:
            if stop.is_set():
                return
            try:
                await _listen(url, padded, on_trade, stop, on_connected)
                backoff = 3.0
            except Exception as exc:
                log.debug(f"WS {url}: {exc}")
        if not stop.is_set():
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)


async def _listen(
    url: str,
    padded_wallet: str,
    on_trade: Callable[[], None],
    stop: threading.Event,
    on_connected: Optional[Callable[[str], None]],
) -> None:
    try:
        import websockets
    except ImportError:
        log.debug("websockets not installed — blockchain watcher disabled")
        stop.wait()
        return

    # Python 3.14 guaranteed — asyncio.timeout available
    async with asyncio.timeout(10):
        async with websockets.connect(url, ping_interval=20) as ws:
            await ws.send(json.dumps({
                "jsonrpc": "2.0", "id": 1,
                "method": "eth_subscribe",
                "params": ["logs", {"address": [_CTF_EXCHANGE, _NEG_RISK_ADDR]}],
            }))
            resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            if "error" in resp:
                raise RuntimeError(f"Subscribe failed: {resp['error']}")

            node = url.split("/")[2]
            log.info(f"Blockchain watcher connected ({node})")
            if on_connected:
                on_connected(node)

            while not stop.is_set():
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                try:
                    data   = json.loads(raw)
                    result = data.get("params", {}).get("result", {})
                    topics = result.get("topics", [])
                    if any(padded_wallet in t.lower() for t in topics):
                        log.debug("On-chain trade detected — waking bot")
                        on_trade()
                except Exception:
                    pass
