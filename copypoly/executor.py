from __future__ import annotations

from dataclasses import replace
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
import math
import time
from typing import Any

from .config import Config
from .models import CopyDecision, OrderResult, Trade
from .state import BotState


class PaperExecutor:
    def __init__(self, state: BotState) -> None:
        self.state = state

    def available_usdc(self) -> float | None:
        return None

    def execute(self, trade: Trade, decision: CopyDecision) -> OrderResult:
        realized = self.state.apply_paper_fill(decision, trade=trade)
        if decision.side == "BUY":
            self.state.add_daily_spent(decision.usdc_size)
            message = f"paper BUY filled; spent ${decision.usdc_size:.2f}"
        else:
            message = f"paper SELL filled; realized PnL ${realized:.2f}"
        order_id = self.state.record_paper_order(
            trade,
            decision,
            status="filled",
            message=message,
        )
        return OrderResult(
            ok=True,
            mode="paper",
            status="filled",
            order_id=str(order_id),
            message=message,
        )


class LiveExecutor:
    def __init__(self, config: Config, state: BotState) -> None:
        try:
            from py_clob_client_v2 import (  # type: ignore
                ApiCreds,
                ClobClient,
                MarketOrderArgs,
                OrderArgs,
                OrderType,
                PartialCreateOrderOptions,
                Side,
            )
        except ImportError as exc:
            raise RuntimeError(
                "Install live dependencies first: pip install -e \".[live]\""
            ) from exc

        self.config = config
        self.state = state
        self.MarketOrderArgs = MarketOrderArgs
        self.OrderArgs = OrderArgs
        self.OrderType = OrderType
        self.PartialCreateOrderOptions = PartialCreateOrderOptions
        self.Side = Side
        self._tick_size_cache: dict[str, str] = {}
        self._neg_risk_cache: dict[str, bool] = {}

        kwargs = {
            "host": config.clob_host,
            "chain_id": config.clob_chain_id,
            "key": config.clob_private_key,
        }
        if config.clob_signature_type is not None:
            kwargs["signature_type"] = config.clob_signature_type
        if config.clob_funder:
            kwargs["funder"] = config.clob_funder

        if config.clob_derive_api_key:
            l1_client = ClobClient(**kwargs)
            creds = l1_client.create_or_derive_api_key()
        else:
            creds = ApiCreds(
                api_key=config.clob_api_key,
                api_secret=config.clob_secret,
                api_passphrase=config.clob_pass_phrase,
            )

        kwargs["creds"] = creds
        self.client = ClobClient(**kwargs)

    def execute(self, trade: Trade, decision: CopyDecision) -> OrderResult:
        side = self.Side.BUY if decision.side == "BUY" else self.Side.SELL
        live_decision = decision
        order_id = ""
        try:
            options = self._order_options(decision.asset)
            order_type = getattr(self.OrderType, self.config.live_order_type)
            checked = self._minimum_live_decision(trade, decision)
            if isinstance(checked, OrderResult):
                return checked
            live_decision = checked
            if self.config.live_order_mode == "market":
                amount = (
                    round(live_decision.usdc_size, 2)
                    if live_decision.side == "BUY"
                    else round(live_decision.size, 2)
                )
                if amount <= 0:
                    return OrderResult(
                        ok=False,
                        mode="live",
                        status="skipped",
                        order_id="",
                        message="Computed live order amount rounds to zero.",
                    )
                response = self.client.create_and_post_market_order(
                    order_args=self.MarketOrderArgs(
                        token_id=live_decision.asset,
                        amount=amount,
                        side=side,
                        price=min(_clob_market_price(live_decision.price), self.config.max_price),
                        order_type=order_type,
                    ),
                    options=options,
                    order_type=order_type,
                )
            else:
                response = self.client.create_and_post_order(
                    order_args=self.OrderArgs(
                        token_id=live_decision.asset,
                        price=live_decision.price,
                        side=side,
                        size=live_decision.size,
                    ),
                    options=options,
                    order_type=order_type,
                )
            response = self._reconcile_response(response)
            submitted = _response_success(response)
            order_id = _response_order_id(response)
            status = _response_status(response)
            filled = submitted and _response_has_fill(response)
            ok = filled
            message = _response_message(response)
            if submitted and not filled:
                message = (
                    f"Order {status} but fill is unconfirmed; "
                    "internal position was not updated."
                )
            elif ok and not message:
                message = _filled_message(live_decision, response)
        except Exception as exc:
            ok = False
            status, message = _exception_result(exc)
        if ok:
            self.state.apply_paper_fill(live_decision, trade=trade)
            if live_decision.side == "BUY":
                self.state.add_daily_spent(live_decision.usdc_size)
        self.state.record_order(
            trade,
            live_decision,
            mode="live",
            status=status,
            message=message,
            external_order_id=order_id,
        )
        return OrderResult(
            ok=ok,
            mode="live",
            status=status,
            order_id=order_id,
            message=message,
        )

    def _minimum_live_decision(
        self,
        trade: Trade,
        decision: CopyDecision,
    ) -> CopyDecision | OrderResult:
        try:
            book = self.client.get_order_book(decision.asset)
        except Exception as exc:
            if _is_no_orderbook_exception(exc):
                return OrderResult(
                    ok=False,
                    mode="live",
                    status="skipped",
                    order_id="",
                    message="No live orderbook exists for this token.",
                )
            raise
        min_size = _book_float(book, "min_order_size", 0.0)
        if decision.side == "SELL":
            return self._minimum_sell_decision(decision, book, min_size)
        return self._minimum_buy_decision(trade, decision, book, min_size)

    def _minimum_buy_decision(
        self,
        trade: Trade,
        decision: CopyDecision,
        book: Any,
        min_size: float,
    ) -> CopyDecision | OrderResult:
        best_ask = _best_ask(book)
        if best_ask <= 0:
            return OrderResult(
                ok=False,
                mode="live",
                status="skipped",
                order_id="",
                message="No live ask liquidity is available for this token.",
            )
        if (
            self.config.enforce_live_price_protection
            and best_ask > decision.price + 0.000001
        ):
            return OrderResult(
                ok=False,
                mode="live",
                status="skipped",
                order_id="",
                message=(
                    f"Best ask {best_ask:.4f} exceeds BUY protection "
                    f"{decision.price:.4f} (source {trade.price:.4f}, "
                    f"SLIPPAGE_BPS {self.config.slippage_bps:.0f})."
                ),
            )
        price = (
            decision.price
            if self.config.enforce_live_price_protection
            else best_ask
        )
        if price > self.config.max_price:
            return OrderResult(
                ok=False,
                mode="live",
                status="skipped",
                order_id="",
                message=(
                    f"Market price {price:.4f} is above MAX_PRICE "
                    f"{self.config.max_price:.4f}."
                ),
            )
        minimum_usdc = (
            max(_ceil_cents(min_size * price), self.config.min_trade_usdc)
            if min_size > 0
            else self.config.min_trade_usdc
        )
        target_usdc = _ceil_cents(decision.usdc_size)
        usdc_size = max(target_usdc, minimum_usdc)
        if (
            self.config.auto_capital_from_balance
            and minimum_usdc > target_usdc
            and self.config.fixed_trade_usdc > usdc_size
        ):
            usdc_size = _ceil_cents(self.config.fixed_trade_usdc)
        if decision.max_usdc > 0 and usdc_size > decision.max_usdc + 0.000001:
            return OrderResult(
                ok=False,
                mode="live",
                status="skipped",
                order_id="",
                message=(
                    f"Live buy amount ${usdc_size:.2f} exceeds configured cap "
                    f"${decision.max_usdc:.2f}."
                ),
            )

        if self.config.max_market_usdc > 0:
            market_spent = (
                self.state.condition_buy_spent(trade.condition_id)
                if trade.condition_id
                else self.state.asset_buy_spent(decision.asset)
            )
            market_remaining = self.config.max_market_usdc - market_spent
            if market_remaining <= 0:
                return OrderResult(
                    ok=False,
                    mode="live",
                    status="skipped",
                    order_id="",
                    message=(
                        f"Market budget is exhausted: ${market_spent:.2f} already "
                        f"spent of ${self.config.max_market_usdc:.2f}."
                    ),
                )
            if usdc_size > market_remaining:
                capped_usdc = _floor_cents(market_remaining)
                if capped_usdc < minimum_usdc:
                    return OrderResult(
                        ok=False,
                        mode="live",
                        status="skipped",
                        order_id="",
                        message=(
                            f"Remaining market budget ${market_remaining:.2f} is below "
                            f"market minimum ${minimum_usdc:.2f}."
                        ),
                    )
                usdc_size = capped_usdc
        if self.config.daily_max_usdc > 0:
            remaining = self.config.daily_max_usdc - self.state.daily_spent()
            if usdc_size > remaining:
                return OrderResult(
                    ok=False,
                    mode="live",
                    status="skipped",
                    order_id="",
                    message=(
                        f"Live buy amount ${usdc_size:.2f} exceeds remaining "
                        f"daily budget ${remaining:.2f}."
                    ),
                )
        if self.config.max_trade_usdc > 0 and usdc_size > self.config.max_trade_usdc:
            return OrderResult(
                ok=False,
                mode="live",
                status="skipped",
                order_id="",
                message=(
                    f"Live buy amount ${usdc_size:.2f} exceeds "
                    f"MAX_TRADE_USDC ${self.config.max_trade_usdc:.2f}."
                ),
            )
        if self.config.max_total_open_usdc > 0:
            open_cost = self.state.open_cost_basis()
            open_remaining = self.config.max_total_open_usdc - open_cost
            if usdc_size > open_remaining:
                return OrderResult(
                    ok=False,
                    mode="live",
                    status="skipped",
                    order_id="",
                    message=(
                        f"Live buy amount ${usdc_size:.2f} exceeds remaining "
                        f"open exposure budget ${open_remaining:.2f}."
                    ),
                )
        if (
            self.config.max_open_positions > 0
            and self.state.open_position_count_for_trader(trade.trader_wallet)
            >= self.config.max_open_positions
        ):
            return OrderResult(
                ok=False,
                mode="live",
                status="skipped",
                order_id="",
                message=(
                    f"Open position limit reached "
                    f"({self.config.max_open_positions})."
                ),
            )
        balance = self._usdc_balance()
        if balance is not None and usdc_size > balance:
            return OrderResult(
                ok=False,
                mode="live",
                status="skipped",
                order_id="",
                message=(
                    f"Available USDC ${balance:.2f} is below market minimum "
                    f"${usdc_size:.2f}."
                ),
            )

        size = round(usdc_size / price, 6)
        return replace(
            decision,
            price=round(price, 6),
            size=size,
            usdc_size=usdc_size,
        )

    def _minimum_sell_decision(
        self,
        decision: CopyDecision,
        book: Any,
        min_size: float,
    ) -> CopyDecision | OrderResult:
        size = math.floor(decision.size * 100) / 100
        if min_size > 0 and size < min_size:
            return OrderResult(
                ok=False,
                mode="live",
                status="skipped",
                order_id="",
                message=(
                    f"Live sell size {size:.2f} is below market minimum "
                    f"{min_size:.2f}."
                ),
            )
        best_bid = _best_bid(book)
        if best_bid <= 0:
            return OrderResult(
                ok=False,
                mode="live",
                status="skipped",
                order_id="",
                message="No live bid liquidity is available for this token.",
            )
        if (
            self.config.enforce_live_price_protection
            and best_bid > 0
            and best_bid < decision.price
        ):
            return OrderResult(
                ok=False,
                mode="live",
                status="skipped",
                order_id="",
                message=(
                    f"Best bid {best_bid:.4f} is below SELL protection "
                    f"{decision.price:.4f}."
                ),
            )
        price = (
            decision.price
            if self.config.enforce_live_price_protection
            else best_bid
        )
        usdc_size = size * price
        if usdc_size < self.config.min_trade_usdc:
            return OrderResult(
                ok=False,
                mode="live",
                status="skipped",
                order_id="",
                message=(
                    f"Live sell value ${usdc_size:.2f} is below "
                    f"MIN_TRADE_USDC ${self.config.min_trade_usdc:.2f}."
                ),
            )
        return replace(decision, price=price, size=size, usdc_size=usdc_size)

    def _reconcile_response(self, response: Any) -> Any:
        if _response_has_fill(response):
            return response
        order_id = _response_order_id(response)
        status = _response_status(response).lower()
        if not order_id or status not in {"delayed", "live", "submitted"}:
            return response
        for _ in range(self.config.live_reconcile_attempts):
            if self.config.live_reconcile_sleep_seconds > 0:
                time.sleep(self.config.live_reconcile_sleep_seconds)
            try:
                refreshed = self.client.get_order(order_id)
            except Exception:
                continue
            if _response_has_fill(refreshed):
                return refreshed
            if _response_status(refreshed).lower() not in {
                "delayed",
                "live",
                "submitted",
            }:
                return refreshed
        return response

    def _usdc_balance(self) -> float | None:
        try:
            from py_clob_client_v2 import AssetType, BalanceAllowanceParams  # type: ignore

            payload = self.client.get_balance_allowance(
                BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
            )
        except Exception:
            return None
        try:
            return float(payload.get("balance", 0)) / 1_000_000
        except (AttributeError, TypeError, ValueError):
            return None

    def available_usdc(self) -> float | None:
        return self._usdc_balance()

    def check_connection(self) -> int:
        orders = self.client.get_open_orders()
        return len(orders) if isinstance(orders, list) else 0

    def _order_options(self, token_id: str):
        tick_size = self._tick_size_cache.get(token_id)
        if tick_size is None:
            try:
                tick_size = str(self.client.get_tick_size(token_id))
            except Exception:
                tick_size = f"{self.config.tick_size:g}"
            self._tick_size_cache[token_id] = tick_size

        neg_risk = self._neg_risk_cache.get(token_id)
        if neg_risk is None:
            try:
                neg_risk = bool(self.client.get_neg_risk(token_id))
            except Exception:
                neg_risk = False
            self._neg_risk_cache[token_id] = neg_risk

        return self.PartialCreateOrderOptions(tick_size=tick_size, neg_risk=neg_risk)


def build_executor(config: Config, state: BotState) -> PaperExecutor | LiveExecutor:
    if config.is_live:
        return LiveExecutor(config, state)
    return PaperExecutor(state)


def _clob_market_price(price: float) -> float:
    return math.nextafter(price, math.inf)


def _ceil_cents(value: float) -> float:
    cents = (Decimal(str(value)) - Decimal("0.000000001")).quantize(
        Decimal("0.01"),
        rounding=ROUND_CEILING,
    )
    return float(cents)


def _floor_cents(value: float) -> float:
    cents = (Decimal(str(value)) + Decimal("0.000000001")).quantize(
        Decimal("0.01"),
        rounding=ROUND_FLOOR,
    )
    return float(cents)


def _filled_message(decision: CopyDecision, response: Any = None) -> str:
    # Use actual matched amount from API response when available (FAK may partially fill)
    actual_usdc = 0.0
    if isinstance(response, dict):
        actual_usdc = _response_float(response, "matched_amount")
        if not actual_usdc:
            size_matched = _response_float(response, "size_matched")
            price = _response_float(response, "price") or decision.price
            if size_matched and price:
                actual_usdc = round(size_matched * price, 2)
    size = _response_float(response, "size_matched") or decision.size
    usdc = actual_usdc if actual_usdc > 0 else decision.usdc_size
    if decision.side == "BUY":
        return f"matched market buy; {size:.2f}sh; spent ${usdc:.2f}"
    return f"matched market sell; {size:.2f}sh; value ${usdc:.2f}"


def _response_success(response: Any) -> bool:
    if not isinstance(response, dict):
        return True
    if "success" in response:
        return bool(response.get("success"))
    status = _response_status(response).lower()
    return status not in {"", "error", "failed", "cancelled", "canceled", "unmatched"}


def _response_order_id(response: Any) -> str:
    if not isinstance(response, dict):
        return ""
    return str(response.get("orderID") or response.get("id") or "")


def _response_status(response: Any) -> str:
    if not isinstance(response, dict):
        return "submitted"
    return str(response.get("status") or "submitted").strip().lower()


def _response_message(response: Any) -> str:
    if not isinstance(response, dict):
        return str(response)
    return str(response.get("errorMsg") or response.get("error") or "")


def _response_has_fill(response: Any) -> bool:
    if not isinstance(response, dict):
        return True
    status = _response_status(response).lower()
    if status in {"matched", "filled", "filled_complete", "complete"}:
        return True
    if _response_float(response, "size_matched") > 0:
        return True
    if _response_float(response, "matched_amount") > 0:
        return True
    if response.get("tradeIDs") or response.get("transactionsHashes"):
        return True
    return False


def _exception_result(exc: Exception) -> tuple[str, str]:
    message = str(exc)
    if _is_no_orderbook_exception(exc):
        return "skipped", "No live orderbook exists for this token."
    if "no orders found to match with FAK order" in message:
        return "skipped", "No matching liquidity for FAK order; no fill."
    msg_lower = message.lower()
    if "not enough balance" in msg_lower or "not enough allowance" in msg_lower:
        return "skipped", f"Insufficient USDC balance: {message}"
    return "error", message


def _is_no_orderbook_exception(exc: Exception) -> bool:
    message = str(exc).lower()
    return "no orderbook exists" in message or "no order book exists" in message


def _response_float(response: dict[str, Any], field: str) -> float:
    try:
        return float(response.get(field) or 0)
    except (TypeError, ValueError):
        return 0.0


def _book_float(book: Any, field: str, default: float) -> float:
    try:
        value = book.get(field) if isinstance(book, dict) else getattr(book, field)
        return float(value)
    except (AttributeError, TypeError, ValueError):
        return default


def _best_ask(book: Any) -> float:
    asks = book.get("asks") if isinstance(book, dict) else getattr(book, "asks", [])
    prices: list[float] = []
    for ask in asks or []:
        try:
            price = ask.get("price") if isinstance(ask, dict) else ask.price
            prices.append(float(price))
        except (AttributeError, TypeError, ValueError):
            continue
    return min(prices) if prices else 0.0


def _best_bid(book: Any) -> float:
    bids = book.get("bids") if isinstance(book, dict) else getattr(book, "bids", [])
    prices: list[float] = []
    for bid in bids or []:
        try:
            price = bid.get("price") if isinstance(bid, dict) else bid.price
            prices.append(float(price))
        except (AttributeError, TypeError, ValueError):
            continue
    return max(prices) if prices else 0.0
