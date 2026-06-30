from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, replace

from .api import PolymarketDataClient
from .config import Config
from .executor import LiveExecutor, PaperExecutor
from .models import CopyDecision, OrderResult, Trade, Trader
from .risk import evaluate_trade
from .state import BotState

_tp_cooldown: dict[str, float] = {}


LogFn = Callable[[str], None]


@dataclass(frozen=True)
class OppositeBuySafety:
    block_reason: str | None = None
    hedge_limit_usdc: float | None = None
    hedge_reason: str = ""


def run_once(
    *,
    config: Config,
    client: PolymarketDataClient,
    state: BotState,
    executor: PaperExecutor | LiveExecutor,
    log: LogFn = print,
) -> None:
    traders = [
        Trader(
            wallet=wallet,
            username="copy-wallet",
            rank=None,
            pnl=0.0,
            volume=0.0,
            roi=0.0,
            score=0.0,
        )
        for wallet in config.watchlist_wallets
    ]
    for trader in traders:
        try:
            _scan_trader(config, client, state, executor, trader, log)
        except Exception as exc:
            log(f"{_trader_label(trader)}: scan error: {exc}")


def run_forever(
    *,
    config: Config,
    client: PolymarketDataClient,
    state: BotState,
    executor: PaperExecutor | LiveExecutor,
    log: LogFn = print,
) -> None:
    while True:
        started = time.time()
        run_once(config=config, client=client, state=state, executor=executor, log=log)
        take_profit_scan(config=config, client=client, state=state, executor=executor, log=log)
        elapsed = time.time() - started
        sleep_for = max(0.05, config.poll_seconds - elapsed)
        time.sleep(sleep_for)


def take_profit_scan(
    *,
    config: Config,
    client: PolymarketDataClient,
    state: BotState,
    executor: PaperExecutor | LiveExecutor,
    log: LogFn = print,
    tp_pct: float | None = None,
) -> None:
    pct = tp_pct if tp_pct is not None else config.take_profit_pct
    if pct <= 0:
        return
    if not config.clob_funder:
        return

    open_positions = [p for p in state.positions() if p.size > 0.01 and p.avg_price > 0]
    if not open_positions:
        return

    try:
        api_positions = client.positions(user=config.clob_funder, size_threshold=0.0)
    except Exception:
        return

    price_map: dict[str, float] = {}
    for ap in api_positions:
        asset_id = str(ap.get("asset") or ap.get("assetId") or ap.get("tokenId") or "")
        price = float(ap.get("curPrice") or ap.get("currentPrice") or 0)
        if asset_id and price > 0:
            price_map[asset_id] = price

    now = time.time()
    for pos in open_positions:
        if now - _tp_cooldown.get(pos.asset, 0) < 30:
            continue
        current_price = price_map.get(pos.asset, 0.0)
        if current_price <= 0:
            continue
        profit_pct = (current_price / pos.avg_price - 1) * 100
        if profit_pct < pct:
            continue

        ts = int(now)
        synthetic_trade = Trade(
            trader_wallet=config.clob_funder,
            side="SELL",
            asset=pos.asset,
            condition_id=pos.condition_id,
            size=pos.size,
            price=current_price,
            timestamp=ts,
            title=pos.title,
            outcome=pos.outcome,
            transaction_hash=f"tp_{pos.asset[:16]}_{ts}",
        )
        decision = CopyDecision(
            should_copy=True,
            reason=f"Take profit at +{profit_pct:.1f}%",
            side="SELL",
            asset=pos.asset,
            price=current_price,
            size=pos.size,
            usdc_size=round(pos.size * current_price, 2),
        )
        _tp_cooldown[pos.asset] = now
        result = executor.execute(synthetic_trade, decision)
        label = pos.title[:50] if pos.title else pos.asset[:18]
        log(
            f"TAKE PROFIT: {label} "
            f"sell {pos.size:.2f}sh @ {current_price:.3f} "
            f"(+{profit_pct:.1f}%) -> {result.message}"
        )


def _scan_trader(
    config: Config,
    client: PolymarketDataClient,
    state: BotState,
    executor: PaperExecutor | LiveExecutor,
    trader: Trader,
    log: LogFn,
) -> None:
    trades = client.recent_trades(
        user=trader.wallet,
        limit=config.trades_limit,
        taker_only=config.trade_taker_only,
        include_activity=config.include_activity,
    )
    trades.sort(key=lambda item: item.timestamp)
    copied = 0
    skipped = 0

    # Capital is fetched at most once per scan, only when a BUY trade needs it.
    _capital_fetched = False
    _capital_cache: float | None = None

    def _get_capital() -> float | None:
        nonlocal _capital_fetched, _capital_cache
        if not _capital_fetched:
            _capital_cache = _capital_basis_usdc(config, client, executor)
            _capital_fetched = True
        return _capital_cache

    for trade in trades:
        if trade.timestamp <= config.start_after_timestamp:
            continue
        if state.seen(trade):
            continue

        opposite_safety = OppositeBuySafety()
        if trade.side == "BUY" and config.block_opposite_buys:
            opposite_safety = _opposite_buy_safety(config, client, state, trade)
            if opposite_safety.block_reason:
                state.mark_seen(trade, "skip", opposite_safety.block_reason)
                skipped += 1
                log(_format_safety_skip(trader, trade, opposite_safety.block_reason))
                continue

        if trade.side == "BUY" and config.max_market_buys > 0:
            market_buys = (
                state.condition_buy_count(trade.condition_id)
                if trade.condition_id
                else state.asset_buy_count(trade.asset)
            )
            if market_buys >= config.max_market_buys:
                reason = (
                    f"Market buy count limit reached "
                    f"({market_buys}/{config.max_market_buys})."
                )
                state.mark_seen(trade, "skip", reason)
                skipped += 1
                log(_format_safety_skip(trader, trade, reason))
                continue

        if (
            trade.side == "BUY"
            and state.recently_copied_market(
                trader_wallet=trade.trader_wallet,
                asset=trade.asset,
                side=trade.side,
                source_timestamp=trade.timestamp,
                cooldown_seconds=config.market_cooldown_seconds,
            )
        ):
            reason = f"Market cooldown is active ({config.market_cooldown_seconds}s)."
            state.mark_seen(trade, "skip", reason)
            skipped += 1
            log(_format_safety_skip(trader, trade, reason))
            continue

        trader_remaining_size = None
        if trade.side == "SELL" and config.sell_sync_mode == "position_fraction":
            trader_remaining_size = client.position_size(
                user=trader.wallet,
                asset=trade.asset,
                market=trade.condition_id or None,
            )

        capital_usdc = None
        if trade.side == "BUY" and config.auto_capital_from_balance:
            capital_usdc = _get_capital()
            if capital_usdc is None:
                reason = "Capital basis could not be read; order not sent."
                state.mark_seen(trade, "skip", reason)
                skipped += 1
                log(_format_safety_skip(trader, trade, reason))
                continue

        decision = evaluate_trade(
            trade,
            config,
            state,
            trader_remaining_size=trader_remaining_size,
            capital_usdc=capital_usdc,
        )
        if not decision.should_copy:
            state.mark_seen(trade, "skip", decision.reason)
            skipped += 1
            log(_format_safety_skip(trader, trade, decision.reason))
            continue

        if trade.side == "BUY" and opposite_safety.hedge_limit_usdc is not None:
            hedge_decision = _cap_hedge_decision(
                decision,
                limit_usdc=opposite_safety.hedge_limit_usdc,
                min_trade_usdc=config.min_trade_usdc,
            )
            if isinstance(hedge_decision, str):
                state.mark_seen(trade, "skip", hedge_decision)
                skipped += 1
                log(_format_safety_skip(trader, trade, hedge_decision))
                continue
            decision = hedge_decision
            log(_format_safety_note(trader, trade, opposite_safety.hedge_reason))

        result = executor.execute(trade, decision)
        result_decision = "copy" if result.ok else "error"
        if result.status == "skipped":
            result_decision = "skip"
            skipped += 1
        elif result.ok:
            copied += 1
        log(_format_copy(trader, trade, result))
        state.mark_seen(trade, result_decision, result.message)

    if copied or skipped:
        log(
            f"{_trader_label(trader)}: copied={copied}, skipped={skipped}, "
            f"new={copied + skipped}"
        )


def _capital_basis_usdc(
    config: Config,
    client: PolymarketDataClient,
    executor: PaperExecutor | LiveExecutor,
) -> float | None:
    try:
        available = executor.available_usdc()
    except Exception:
        return None
    if available is None:
        return None
    if not config.auto_capital_include_open_value:
        return available
    if not config.clob_funder:
        return None
    try:
        positions = client.positions(
            user=config.clob_funder,
            limit=500,
            size_threshold=0.000001,
        )
    except Exception:
        return None
    open_value = sum(_position_current_value(position) for position in positions)
    return available + open_value


def _opposite_buy_safety(
    config: Config,
    client: PolymarketDataClient,
    state: BotState,
    trade: Trade,
) -> OppositeBuySafety:
    if trade.side != "BUY" or not config.block_opposite_buys:
        return OppositeBuySafety()
    if not trade.condition_id:
        return OppositeBuySafety()

    if config.is_live and config.clob_funder:
        try:
            positions = client.positions(
                user=config.clob_funder,
                market=trade.condition_id,
                limit=50,
                size_threshold=0.0,
            )
        except Exception as exc:
            return OppositeBuySafety(
                block_reason=f"Opposite-position check failed for this market: {exc}"
            )

        opposite_positions = [
            position
            for position in positions
            if _position_asset(position)
            and _position_asset(position) != trade.asset
            and _position_number(position, "size", "shares", "balance") > 0.000001
        ]
        if not opposite_positions:
            return OppositeBuySafety()
        outcome = str(opposite_positions[0].get("outcome") or "")
        asset = _position_asset(opposite_positions[0])
        size = sum(
            _position_number(position, "size", "shares", "balance")
            for position in opposite_positions
        )
        cost_basis = sum(_position_cost_basis(position) for position in opposite_positions)
        return _opposite_position_safety_result(
            config=config,
            trade=trade,
            outcome=outcome,
            asset=asset,
            size=size,
            cost_basis=cost_basis,
        )

    local_position = state.open_opposite_position(trade)
    if not local_position:
        return OppositeBuySafety()
    return _opposite_position_safety_result(
        config=config,
        trade=trade,
        outcome=local_position.outcome,
        asset=local_position.asset,
        size=local_position.size,
        cost_basis=local_position.size * local_position.avg_price,
    )


def _opposite_position_safety_result(
    *,
    config: Config,
    trade: Trade,
    outcome: str,
    asset: str,
    size: float,
    cost_basis: float,
) -> OppositeBuySafety:
    block_reason = _format_opposite_position_reason(
        outcome=outcome,
        asset=asset,
        size=size,
    )
    if not config.allow_cheap_hedge_buys:
        return OppositeBuySafety(block_reason=block_reason)
    if trade.price > config.hedge_max_price:
        return OppositeBuySafety(
            block_reason=(
                f"{block_reason} Cheap hedge exception rejected: "
                f"price {trade.price:.4f} is above HEDGE_MAX_PRICE "
                f"{config.hedge_max_price:.4f}."
            )
        )
    if cost_basis <= 0:
        return OppositeBuySafety(
            block_reason=(
                f"{block_reason} Cheap hedge exception rejected: "
                "existing position cost is unknown."
            )
        )

    limit_usdc = min(config.hedge_max_usdc, cost_basis * config.hedge_max_ratio)
    if limit_usdc + 0.000001 < config.min_trade_usdc:
        return OppositeBuySafety(
            block_reason=(
                f"{block_reason} Cheap hedge exception rejected: allowed hedge "
                f"${limit_usdc:.2f} is below MIN_TRADE_USDC ${config.min_trade_usdc:.2f}."
            )
        )
    return OppositeBuySafety(
        hedge_limit_usdc=limit_usdc,
        hedge_reason=(
            "SAFETY hedge allowed: trader bought the opposite outcome cheaply; "
            f"copy is capped at ${limit_usdc:.2f} "
            f"(price {trade.price:.4f}, existing cost ${cost_basis:.2f})."
        ),
    )


def _cap_hedge_decision(
    decision: CopyDecision,
    *,
    limit_usdc: float,
    min_trade_usdc: float,
) -> CopyDecision | str:
    capped_usdc = min(decision.usdc_size, limit_usdc)
    capped_usdc = round(capped_usdc, 2)
    if capped_usdc + 0.000001 < min_trade_usdc:
        return (
            f"Cheap hedge copy ${capped_usdc:.2f} is below "
            f"MIN_TRADE_USDC ${min_trade_usdc:.2f}."
        )
    if decision.price <= 0:
        return "Cheap hedge copy has invalid price."
    return replace(
        decision,
        size=round(capped_usdc / decision.price, 6),
        usdc_size=capped_usdc,
        max_usdc=round(limit_usdc, 2),
    )


def _format_copy(trader: Trader, trade: Trade, result: OrderResult) -> str:
    market = trade.title[:70] if trade.title else trade.asset[:18]
    return (
        f"{result.mode.upper()} {result.status}: {_trader_label(trader)} "
        f"{trade.side} {trade.outcome or trade.asset[:12]} @ {trade.price:.3f} "
        f"on {market} -> {result.message}"
    )


def _format_safety_skip(trader: Trader, trade: Trade, reason: str) -> str:
    market = trade.title[:70] if trade.title else trade.asset[:18]
    return (
        f"SAFETY skip: {_trader_label(trader)} {trade.side} "
        f"{trade.outcome or trade.asset[:12]} on {market} -> {reason}"
    )


def _format_safety_note(trader: Trader, trade: Trade, reason: str) -> str:
    market = trade.title[:70] if trade.title else trade.asset[:18]
    return (
        f"SAFETY note: {_trader_label(trader)} {trade.side} "
        f"{trade.outcome or trade.asset[:12]} on {market} -> {reason}"
    )


def _format_opposite_position_reason(*, outcome: str, asset: str, size: float) -> str:
    label = outcome or asset[:12]
    return (
        "Opposite outcome is already held in this market "
        f"({label}, size {size:.4f})."
    )


def _position_asset(position: dict[str, object]) -> str:
    return str(
        position.get("asset")
        or position.get("assetId")
        or position.get("tokenId")
        or ""
    )


def _position_number(position: dict[str, object], *keys: str) -> float:
    for key in keys:
        value = position.get(key)
        if value in (None, ""):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _position_cost_basis(position: dict[str, object]) -> float:
    direct = _position_number(
        position,
        "initialValue",
        "initial_value",
        "costBasis",
        "cost_basis",
        "totalInvested",
        "total_invested",
    )
    if direct > 0:
        return direct
    size = _position_number(position, "size", "shares", "balance")
    avg_price = _position_number(position, "avgPrice", "avg_price")
    return size * avg_price


def _position_current_value(position: dict[str, object]) -> float:
    return _position_number(
        position,
        "currentValue",
        "current_value",
        "value",
        "marketValue",
        "market_value",
    )


def _trader_label(trader: Trader) -> str:
    return f"{trader.wallet[:6]}...{trader.wallet[-4:]}"
