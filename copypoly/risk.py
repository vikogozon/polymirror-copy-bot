from __future__ import annotations

import time
from math import ceil, floor

from .config import Config
from .models import CopyDecision, Trade
from .state import BotState


def evaluate_trade(
    trade: Trade,
    config: Config,
    state: BotState,
    trader_remaining_size: float | None = None,
    force_close: bool = False,
    capital_usdc: float | None = None,
) -> CopyDecision:
    if trade.side == "BUY" and not config.copy_buys:
        return _skip(trade, "BUY copying is disabled.")
    if trade.side == "SELL" and not config.copy_sells:
        return _skip(trade, "SELL copying is disabled.")
    if config.is_live and trade.side == "SELL" and not config.allow_live_sells:
        return _skip(trade, "Live SELL copying is disabled.")

    age = int(time.time()) - trade.timestamp
    if config.trade_lookback_seconds > 0 and age > config.trade_lookback_seconds:
        return _skip(trade, f"Trade is stale ({age}s old).")
    if trade.side == "BUY" and (
        trade.price < config.min_price or trade.price > config.max_price
    ):
        return _skip(trade, f"Price {trade.price:.4f} is outside configured bounds.")

    if trade.side == "BUY":
        target_usdc = _target_buy_usdc(trade, config, capital_usdc=capital_usdc)
        if target_usdc < config.min_trade_usdc:
            return _skip(
                trade,
                f"Copied size ${target_usdc:.2f} is below MIN_TRADE_USDC.",
            )
        if config.daily_max_usdc > 0:
            remaining = config.daily_max_usdc - state.daily_spent()
            if remaining < target_usdc:
                return _skip(trade, "Daily buy budget is exhausted.")
        if config.max_market_usdc > 0:
            market_spent = _market_buy_spent(state, trade)
            market_remaining = config.max_market_usdc - market_spent
            if market_remaining <= 0:
                return _skip(
                    trade,
                    (
                        f"Market budget is exhausted: ${market_spent:.2f} already "
                        f"spent of ${config.max_market_usdc:.2f}."
                    ),
                )
            if target_usdc > market_remaining:
                target_usdc = _floor_cents(market_remaining)
                if target_usdc < config.min_trade_usdc:
                    return _skip(
                        trade,
                        (
                            f"Remaining market budget ${market_remaining:.2f} is "
                            f"below MIN_TRADE_USDC ${config.min_trade_usdc:.2f}."
                        ),
                    )
        if config.max_total_open_usdc > 0:
            open_cost = state.open_cost_basis()
            open_remaining = config.max_total_open_usdc - open_cost
            if open_remaining < target_usdc:
                return _skip(
                    trade,
                    (
                        f"Open exposure limit is exhausted: ${open_cost:.2f} "
                        f"open of ${config.max_total_open_usdc:.2f}."
                    ),
                )
        if (
            config.max_open_positions > 0
            and state.open_position_count_for_trader(trade.trader_wallet)
            >= config.max_open_positions
        ):
            return _skip(
                trade,
                (
                    f"Open position limit reached "
                    f"({config.max_open_positions})."
                ),
            )
        limit_price = _round_price(
            min(0.99, trade.price * (1.0 + config.slippage_bps / 10_000.0)),
            config.tick_size,
            "BUY",
        )
        if limit_price > config.max_price:
            return _skip(
                trade,
                f"Buy price {limit_price:.4f} is above MAX_PRICE {config.max_price:.4f}.",
            )
        size = _round_size(target_usdc / limit_price)
    else:
        held = state.position(trade.asset).size
        if held <= 0:
            return _skip(trade, "No paper position available to sell.")
        requested_size = _target_sell_size(
            trade=trade,
            config=config,
            held_size=held,
            trader_remaining_size=trader_remaining_size,
            force_close=force_close,
        )
        size = min(requested_size, held)
        if size <= 0:
            return _skip(trade, "Computed SELL size is zero.")
        limit_price = _round_price(
            max(0.01, trade.price * (1.0 - config.slippage_bps / 10_000.0)),
            config.tick_size,
            "SELL",
        )
        target_usdc = size * limit_price
        if target_usdc < config.min_trade_usdc:
            return _skip(
                trade,
                f"Copied SELL value ${target_usdc:.4f} is below MIN_TRADE_USDC.",
            )

    if size <= 0:
        return _skip(trade, "Computed order size is zero.")

    return CopyDecision(
        should_copy=True,
        reason="ok",
        side=trade.side,
        asset=trade.asset,
        price=limit_price,
        size=size,
        usdc_size=target_usdc,
        max_usdc=_buy_max_usdc(trade, config, target_usdc),
    )


def _target_buy_usdc(
    trade: Trade,
    config: Config,
    *,
    capital_usdc: float | None = None,
) -> float:
    if config.sizing_mode == "fixed_usdc":
        return (
            min(config.fixed_trade_usdc, config.max_trade_usdc)
            if config.max_trade_usdc > 0
            else config.fixed_trade_usdc
        )
    if config.sizing_mode == "source_ratio":
        ratio_size = trade.usdc_size * config.copy_ratio
        return min(ratio_size, config.max_trade_usdc) if config.max_trade_usdc > 0 else ratio_size
    base_capital = config.capital_usdc if capital_usdc is None else capital_usdc
    target = base_capital * config.position_percent
    return min(target, config.max_trade_usdc) if config.max_trade_usdc > 0 else target


def _buy_max_usdc(trade: Trade, config: Config, target_usdc: float) -> float:
    if trade.side != "BUY":
        return 0.0
    if config.sizing_mode in {"fixed_usdc", "source_ratio"}:
        return _ceil_cents(target_usdc)
    if config.auto_capital_from_balance:
        cap = max(target_usdc, config.fixed_trade_usdc)
        if config.max_trade_usdc > 0:
            cap = min(cap, config.max_trade_usdc)
        return _ceil_cents(cap)
    return 0.0


def _market_buy_spent(state: BotState, trade: Trade) -> float:
    if trade.condition_id:
        return state.condition_buy_spent(trade.condition_id)
    return state.asset_buy_spent(trade.asset)


def _target_sell_size(
    *,
    trade: Trade,
    config: Config,
    held_size: float,
    trader_remaining_size: float | None,
    force_close: bool,
) -> float:
    if force_close:
        return held_size
    if config.sell_sync_mode == "close_on_sell":
        return held_size
    if config.sell_sync_mode == "mirror_size":
        return _round_size(trade.size * config.copy_ratio)

    if trader_remaining_size is None or trader_remaining_size <= 0:
        return held_size

    estimated_before_sell = trader_remaining_size + trade.size
    if estimated_before_sell <= 0:
        return held_size
    sold_fraction = min(max(trade.size / estimated_before_sell, 0.0), 1.0)
    return _round_size(held_size * sold_fraction)


def _skip(trade: Trade, reason: str) -> CopyDecision:
    return CopyDecision(
        should_copy=False,
        reason=reason,
        side=trade.side,
        asset=trade.asset,
        price=trade.price,
        size=0.0,
        usdc_size=0.0,
    )


def _round_price(price: float, tick_size: float, side: str) -> float:
    ticks = price / tick_size
    if side == "BUY":
        rounded = floor(ticks + 0.999999) * tick_size
    else:
        rounded = floor(ticks) * tick_size
    return round(min(max(rounded, 0.01), 0.99), 6)


def _round_size(size: float) -> float:
    return round(size, 6)


def _ceil_cents(value: float) -> float:
    return round(ceil((value - 0.000000001) * 100) / 100, 2)


def _floor_cents(value: float) -> float:
    return round(floor((value + 0.000000001) * 100) / 100, 2)
