from __future__ import annotations

from dataclasses import replace

from .api import PolymarketDataClient
from .config import Config, load_config
from .executor import build_executor
from .runner import run_forever, run_once
from .state import BotState


DEFAULT_COPY_WALLET = "0x204f72f35326db932158cba6adff0b9a1da95e14"


def single_wallet_config(config: Config, wallet: str | None = None) -> Config:
    if wallet is None:
        if len(config.watchlist_wallets) != 1:
            raise ValueError(
                "Configure exactly one WATCHLIST_WALLETS address or pass --wallet."
            )
        wallet = config.watchlist_wallets[0]
    wallet = wallet.strip().lower()
    if not wallet.startswith("0x") or len(wallet) != 42:
        raise ValueError("Wallet must be a 42-character 0x address.")
    return replace(config, watchlist_wallets=(wallet,))


def run_single_wallet_copier(
    *,
    wallet: str | None = None,
    once: bool = False,
) -> None:
    config = single_wallet_config(load_config(), wallet)
    client = PolymarketDataClient(config.data_host, timeout=config.data_timeout_seconds)
    state = BotState(config.database_path)
    try:
        executor = build_executor(config, state)
        if once:
            run_once(config=config, client=client, state=state, executor=executor)
        else:
            run_forever(config=config, client=client, state=state, executor=executor)
    finally:
        state.close()
