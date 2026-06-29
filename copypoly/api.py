from __future__ import annotations

from typing import Any

import requests

from .models import Trade


class PolymarketDataClient:
    def __init__(self, host: str, timeout: float = 15.0) -> None:
        self.host = host.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "copypoly/0.1"})

    def _get(self, path: str, params: dict[str, Any]) -> Any:
        response = self.session.get(
            f"{self.host}{path}",
            params={k: v for k, v in params.items() if v not in (None, "")},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def trades(
        self,
        *,
        user: str,
        limit: int = 100,
        offset: int = 0,
        taker_only: bool = True,
    ) -> list[Trade]:
        payload = self._get(
            "/trades",
            {
                "user": user,
                "limit": limit,
                "offset": offset,
                "takerOnly": str(taker_only).lower(),
            },
        )
        trades: list[Trade] = []
        for item in _items(payload):
            trade = _parse_trade(user, item)
            if trade:
                trades.append(trade)
        return trades

    def activity_trades(
        self,
        *,
        user: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Trade]:
        payload = self._get(
            "/activity",
            {
                "user": user,
                "limit": limit,
                "offset": offset,
            },
        )
        trades: list[Trade] = []
        for item in _items(payload):
            if str(item.get("type") or "").strip().upper() != "TRADE":
                continue
            trade = _parse_trade(user, item)
            if trade:
                trades.append(trade)
        return trades

    def recent_trades(
        self,
        *,
        user: str,
        limit: int = 100,
        taker_only: bool = False,
        include_activity: bool = True,
    ) -> list[Trade]:
        candidates: list[Trade] = []
        trades_error: Exception | None = None
        try:
            candidates.extend(
                self.trades(user=user, limit=limit, taker_only=taker_only)
            )
        except Exception as exc:
            trades_error = exc

        # /trades is normally indexed before /activity. Avoid waiting for the
        # slower activity feed when the primary endpoint already returned a
        # complete page, while retaining activity as a sparse/error fallback.
        if len(candidates) >= limit:
            return _dedupe_recent_trades(candidates, limit=limit)
        if include_activity:
            try:
                candidates.extend(self.activity_trades(user=user, limit=limit))
            except Exception:
                if trades_error is not None:
                    raise trades_error
        elif trades_error is not None:
            raise trades_error
        return _dedupe_recent_trades(candidates, limit=limit)

    def positions(
        self,
        *,
        user: str,
        market: str | None = None,
        limit: int = 500,
        size_threshold: float = 0.0,
    ) -> list[dict[str, Any]]:
        payload = self._get(
            "/positions",
            {
                "user": user,
                "market": market,
                "limit": limit,
                "sizeThreshold": size_threshold,
            },
        )
        return _items(payload)

    def portfolio_value(self, *, user: str) -> float | None:
        """Return total open-position value from Polymarket's /value endpoint."""
        try:
            payload = self._get("/value", {"user": user})
            items = _items(payload)
            if items:
                return float(items[0].get("value") or 0)
        except Exception:
            pass
        return None

    def position(
        self,
        *,
        user: str,
        asset: str,
        market: str | None = None,
    ) -> dict[str, Any] | None:
        for position in self.positions(user=user, market=market):
            if str(position.get("asset") or "") == asset:
                return position
        return None

    def position_size(
        self,
        *,
        user: str,
        asset: str,
        market: str | None = None,
    ) -> float:
        position = self.position(user=user, asset=asset, market=market)
        return _number(position.get("size")) if position else 0.0


def _dedupe_recent_trades(candidates: list[Trade], *, limit: int) -> list[Trade]:
    seen: set[str] = set()
    merged: list[Trade] = []
    for trade in sorted(candidates, key=lambda item: item.timestamp, reverse=True):
        key = trade.fingerprint
        if key in seen:
            continue
        seen.add(key)
        merged.append(trade)
    return merged[:limit]


def _parse_trade(user: str, item: dict[str, Any]) -> Trade | None:
    side = str(item.get("side") or "").strip().upper()
    asset = str(item.get("asset") or "").strip()
    if side not in {"BUY", "SELL"} or not asset:
        return None

    try:
        price = _number(item.get("price"))
        size = _number(item.get("size"))
        timestamp = int(item.get("timestamp") or 0)
    except (TypeError, ValueError):
        return None

    if price <= 0 or size <= 0 or timestamp <= 0:
        return None

    return Trade(
        trader_wallet=str(item.get("proxyWallet") or user),
        side=side,
        asset=asset,
        condition_id=str(item.get("conditionId") or ""),
        size=size,
        price=price,
        timestamp=timestamp,
        title=str(item.get("title") or ""),
        outcome=str(item.get("outcome") or ""),
        transaction_hash=str(item.get("transactionHash") or ""),
        slug=str(item.get("slug") or ""),
        event_slug=str(item.get("eventSlug") or item.get("event_slug") or ""),
    )


def _number(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    return float(value)


def _items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("value"), list):
        return [item for item in payload["value"] if isinstance(item, dict)]
    return []
