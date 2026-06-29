from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return default if raw in (None, "") else int(raw)


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return default if raw in (None, "") else float(raw)


def _csv(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


def _env_first(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value not in (None, ""):
            return value
    return default


def _optional_int(name: str) -> int | None:
    raw = os.getenv(name)
    if raw in (None, ""):
        return None
    return int(raw)


@dataclass(frozen=True)
class Config:
    data_host: str
    data_timeout_seconds: float
    clob_host: str
    clob_chain_id: int
    mode: str
    database_path: Path
    watchlist_wallets: tuple[str, ...]
    poll_seconds: float
    trades_limit: int
    trade_taker_only: bool
    include_activity: bool
    trade_lookback_seconds: int
    start_after_timestamp: int
    copy_buys: bool
    copy_sells: bool
    block_opposite_buys: bool
    allow_cheap_hedge_buys: bool
    hedge_max_price: float
    hedge_max_usdc: float
    hedge_max_ratio: float
    sizing_mode: str
    capital_usdc: float
    auto_capital_from_balance: bool
    auto_capital_include_open_value: bool
    fixed_trade_usdc: float
    position_percent: float
    copy_ratio: float
    sell_sync_mode: str
    min_trade_usdc: float
    max_trade_usdc: float
    max_market_usdc: float
    max_market_buys: int
    max_total_open_usdc: float
    max_open_positions: int
    market_cooldown_seconds: int
    daily_max_usdc: float
    min_price: float
    max_price: float
    slippage_bps: float
    enforce_live_price_protection: bool
    tick_size: float
    real_trading_confirm: str
    allow_live_sells: bool
    live_order_mode: str
    live_order_type: str
    live_reconcile_attempts: int
    live_reconcile_sleep_seconds: float
    clob_private_key: str
    clob_api_key: str
    clob_secret: str
    clob_pass_phrase: str
    clob_derive_api_key: bool
    clob_signature_type: int | None
    clob_funder: str

    @property
    def is_live(self) -> bool:
        return self.mode == "live"

    @property
    def live_confirmed(self) -> bool:
        return self.real_trading_confirm == "YES_I_ACCEPT_REAL_TRADING_RISK"

    def validate(self) -> None:
        if self.mode not in {"paper", "live"}:
            raise ValueError("MODE must be 'paper' or 'live'.")
        if not self.watchlist_wallets:
            raise ValueError("WATCHLIST_WALLETS must contain one wallet.")
        for wallet in self.watchlist_wallets:
            if not wallet.startswith("0x") or len(wallet) != 42:
                raise ValueError(f"Invalid wallet address: {wallet}")
        if self.data_timeout_seconds <= 0:
            raise ValueError("DATA_TIMEOUT_SECONDS must be greater than 0.")
        if self.poll_seconds <= 0:
            raise ValueError("POLL_SECONDS must be greater than 0.")
        if self.trades_limit <= 0:
            raise ValueError("TRADES_LIMIT must be greater than 0.")
        if self.trade_lookback_seconds < 0:
            raise ValueError("TRADE_LOOKBACK_SECONDS cannot be negative.")
        if self.start_after_timestamp < 0:
            raise ValueError("START_AFTER_TIMESTAMP cannot be negative.")
        if self.sizing_mode not in {"capital_percent", "source_ratio", "fixed_usdc"}:
            raise ValueError(
                "SIZING_MODE must be 'capital_percent', 'source_ratio', or 'fixed_usdc'."
            )
        if self.auto_capital_from_balance and self.sizing_mode != "capital_percent":
            raise ValueError(
                "AUTO_CAPITAL_FROM_BALANCE requires SIZING_MODE=capital_percent."
            )
        if self.auto_capital_include_open_value and not self.auto_capital_from_balance:
            raise ValueError(
                "AUTO_CAPITAL_INCLUDE_OPEN_VALUE requires AUTO_CAPITAL_FROM_BALANCE=true."
            )
        if self.sell_sync_mode not in {"position_fraction", "close_on_sell", "mirror_size"}:
            raise ValueError(
                "SELL_SYNC_MODE must be 'position_fraction', 'close_on_sell', or 'mirror_size'."
            )
        if self.capital_usdc <= 0:
            raise ValueError("CAPITAL_USDC must be greater than 0.")
        if not 0 < self.position_percent <= 1:
            raise ValueError("POSITION_PERCENT must be between 0 and 1.")
        if self.copy_ratio <= 0:
            raise ValueError("COPY_RATIO must be greater than 0.")
        if self.fixed_trade_usdc <= 0:
            raise ValueError("FIXED_TRADE_USDC must be greater than 0.")
        if self.min_trade_usdc < 0 or self.max_trade_usdc < 0:
            raise ValueError("Trade size limits cannot be negative.")
        if self.max_trade_usdc > 0 and self.min_trade_usdc > self.max_trade_usdc:
            raise ValueError("MIN_TRADE_USDC cannot be greater than MAX_TRADE_USDC.")
        if self.max_market_usdc < 0:
            raise ValueError("MAX_MARKET_USDC cannot be negative.")
        if self.max_market_buys < 0:
            raise ValueError("MAX_MARKET_BUYS cannot be negative.")
        if self.max_total_open_usdc < 0:
            raise ValueError("MAX_TOTAL_OPEN_USDC cannot be negative.")
        if self.max_open_positions < 0:
            raise ValueError("MAX_OPEN_POSITIONS cannot be negative.")
        if self.market_cooldown_seconds < 0:
            raise ValueError("MARKET_COOLDOWN_SECONDS cannot be negative.")
        if self.daily_max_usdc < 0:
            raise ValueError("DAILY_MAX_USDC cannot be negative.")
        if not 0 < self.min_price < self.max_price < 1:
            raise ValueError("Expected 0 < MIN_PRICE < MAX_PRICE < 1.")
        if self.slippage_bps < 0:
            raise ValueError("SLIPPAGE_BPS cannot be negative.")
        if self.tick_size <= 0:
            raise ValueError("TICK_SIZE must be greater than 0.")
        if not 0 < self.hedge_max_price < 1:
            raise ValueError("HEDGE_MAX_PRICE must be between 0 and 1.")
        if self.hedge_max_usdc <= 0:
            raise ValueError("HEDGE_MAX_USDC must be greater than 0.")
        if not 0 < self.hedge_max_ratio <= 1:
            raise ValueError("HEDGE_MAX_RATIO must be between 0 and 1.")
        if self.live_order_mode not in {"market", "limit"}:
            raise ValueError("LIVE_ORDER_MODE must be 'market' or 'limit'.")
        if self.live_order_type not in {"FAK", "FOK", "GTC"}:
            raise ValueError("LIVE_ORDER_TYPE must be 'FAK', 'FOK', or 'GTC'.")
        if self.live_order_mode == "market" and self.live_order_type == "GTC":
            raise ValueError("Market live orders cannot use GTC.")
        if self.live_reconcile_attempts < 0:
            raise ValueError("LIVE_RECONCILE_ATTEMPTS cannot be negative.")
        if self.live_reconcile_sleep_seconds < 0:
            raise ValueError("LIVE_RECONCILE_SLEEP_SECONDS cannot be negative.")
        if self.is_live:
            if not self.live_confirmed:
                raise ValueError(
                    "Live trading is blocked. Set REAL_TRADING_CONFIRM="
                    "YES_I_ACCEPT_REAL_TRADING_RISK to enable it."
                )
            if not self.clob_private_key:
                raise ValueError("CLOB_PRIVATE_KEY is required in live mode.")
            has_l2 = all([self.clob_api_key, self.clob_secret, self.clob_pass_phrase])
            if not has_l2 and not self.clob_derive_api_key:
                raise ValueError(
                    "Live mode requires CLOB_API_KEY/CLOB_SECRET/CLOB_PASS_PHRASE, "
                    "or CLOB_DERIVE_API_KEY=true."
                )


def load_config(env_files: Iterable[str | Path] = (".env",)) -> Config:
    # Preserve START_AFTER_TIMESTAMP set by run_dashboard.py before .env can override it
    _sat = os.environ.get("START_AFTER_TIMESTAMP")
    for env_file in env_files:
        load_dotenv(env_file, override=True)
    if _sat is not None:
        os.environ["START_AFTER_TIMESTAMP"] = _sat

    capital_usdc = _float("CAPITAL_USDC", 100.0)
    config = Config(
        data_host=os.getenv("POLY_DATA_HOST", "https://data-api.polymarket.com").rstrip("/"),
        data_timeout_seconds=_float("DATA_TIMEOUT_SECONDS", 5.0),
        clob_host=_env_first(
            "POLY_CLOB_HOST",
            "POLYMARKET_CLOB_HOST",
            default="https://clob.polymarket.com",
        ).rstrip("/"),
        clob_chain_id=int(_env_first("CLOB_CHAIN_ID", "POLYMARKET_CHAIN_ID", default="137")),
        mode=os.getenv("MODE", "paper").strip().lower(),
        database_path=Path(os.getenv("DATABASE_PATH", "data/copypoly.sqlite")),
        watchlist_wallets=tuple(_csv(os.getenv("WATCHLIST_WALLETS"))),
        poll_seconds=_float("POLL_SECONDS", 2.0),
        trades_limit=_int("TRADES_LIMIT", 25),
        trade_taker_only=_bool("TRADE_TAKER_ONLY", False),
        include_activity=_bool("INCLUDE_ACTIVITY", True),
        trade_lookback_seconds=_int("TRADE_LOOKBACK_SECONDS", 300),
        start_after_timestamp=_int("START_AFTER_TIMESTAMP", 0),
        copy_buys=_bool("COPY_BUYS", True),
        copy_sells=_bool("COPY_SELLS", True),
        block_opposite_buys=_bool("BLOCK_OPPOSITE_BUYS", True),
        allow_cheap_hedge_buys=_bool("ALLOW_CHEAP_HEDGE_BUYS", False),
        hedge_max_price=_float("HEDGE_MAX_PRICE", 0.25),
        hedge_max_usdc=_float("HEDGE_MAX_USDC", 5.0),
        hedge_max_ratio=_float("HEDGE_MAX_RATIO", 0.25),
        sizing_mode=os.getenv("SIZING_MODE", "capital_percent").strip().lower(),
        capital_usdc=capital_usdc,
        auto_capital_from_balance=_bool("AUTO_CAPITAL_FROM_BALANCE", False),
        auto_capital_include_open_value=_bool("AUTO_CAPITAL_INCLUDE_OPEN_VALUE", False),
        fixed_trade_usdc=_float("FIXED_TRADE_USDC", 5.0),
        position_percent=_float("POSITION_PERCENT", 0.01),
        copy_ratio=_float("COPY_RATIO", 0.01),
        sell_sync_mode=os.getenv("SELL_SYNC_MODE", "position_fraction").strip().lower(),
        min_trade_usdc=_float("MIN_TRADE_USDC", 0.0),
        max_trade_usdc=_float("MAX_TRADE_USDC", 0.0),
        max_market_usdc=_float("MAX_MARKET_USDC", 5.0),
        max_market_buys=_int("MAX_MARKET_BUYS", 0),
        max_total_open_usdc=_float("MAX_TOTAL_OPEN_USDC", capital_usdc),
        max_open_positions=_int("MAX_OPEN_POSITIONS", 0),
        market_cooldown_seconds=_int("MARKET_COOLDOWN_SECONDS", 0),
        daily_max_usdc=_float("DAILY_MAX_USDC", 0.0),
        min_price=_float("MIN_PRICE", 0.001),
        max_price=_float("MAX_PRICE", 0.999),
        slippage_bps=_float("SLIPPAGE_BPS", 100.0),
        enforce_live_price_protection=_bool(
            "ENFORCE_LIVE_PRICE_PROTECTION",
            True,
        ),
        tick_size=_float("TICK_SIZE", 0.01),
        real_trading_confirm=os.getenv("REAL_TRADING_CONFIRM", ""),
        allow_live_sells=_bool("ALLOW_LIVE_SELLS", True),
        live_order_mode=os.getenv("LIVE_ORDER_MODE", "market").strip().lower(),
        live_order_type=os.getenv("LIVE_ORDER_TYPE", "FAK").strip().upper(),
        live_reconcile_attempts=_int("LIVE_RECONCILE_ATTEMPTS", 5),
        live_reconcile_sleep_seconds=_float("LIVE_RECONCILE_SLEEP_SECONDS", 1.0),
        clob_private_key=_env_first("CLOB_PRIVATE_KEY", "POLYMARKET_PRIVATE_KEY"),
        clob_api_key=_env_first("CLOB_API_KEY", "POLYMARKET_CLOB_API_KEY"),
        clob_secret=_env_first("CLOB_SECRET", "CLOB_API_SECRET", "POLYMARKET_CLOB_API_SECRET"),
        clob_pass_phrase=_env_first(
            "CLOB_PASS_PHRASE",
            "CLOB_API_PASSPHRASE",
            "POLYMARKET_CLOB_API_PASSPHRASE",
        ),
        clob_derive_api_key=_bool("CLOB_DERIVE_API_KEY", False),
        clob_signature_type=(
            _optional_int("CLOB_SIGNATURE_TYPE")
            if os.getenv("CLOB_SIGNATURE_TYPE") not in (None, "")
            else _optional_int("POLYMARKET_SIGNATURE_TYPE")
        ),
        clob_funder=_env_first(
            "CLOB_FUNDER",
            "POLYMARKET_FUNDER",
            "POLYMARKET_DEPOSIT_WALLET",
        ).strip("'\""),
    )
    config.validate()
    return config
