from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Trader:
    wallet: str
    username: str
    rank: int | None
    pnl: float
    volume: float
    roi: float
    score: float


@dataclass(frozen=True)
class Trade:
    trader_wallet: str
    side: str
    asset: str
    condition_id: str
    size: float
    price: float
    timestamp: int
    title: str
    outcome: str
    transaction_hash: str
    slug: str = ""
    event_slug: str = ""

    @property
    def usdc_size(self) -> float:
        return self.size * self.price

    @property
    def fingerprint(self) -> str:
        fields = [
            self.trader_wallet.lower(),
            self.transaction_hash.lower(),
            self.asset,
            self.side,
            f"{self.size:.8f}",
            f"{self.price:.8f}",
            str(self.timestamp),
        ]
        return "|".join(fields)


@dataclass(frozen=True)
class CopyDecision:
    should_copy: bool
    reason: str
    side: str
    asset: str
    price: float
    size: float
    usdc_size: float
    max_usdc: float = 0.0


@dataclass(frozen=True)
class OrderResult:
    ok: bool
    mode: str
    status: str
    order_id: str
    message: str
