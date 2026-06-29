from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .models import CopyDecision, Trade


SOURCE_EVENT_COLUMNS = (
    "source_fingerprint",
    "trader_wallet",
    "asset",
    "condition_id",
    "side",
    "price",
    "size",
    "usdc_size",
    "source_timestamp",
    "title",
    "outcome",
    "position_size_before",
    "position_size_after",
    "avg_price_after",
    "current_price",
    "cash_pnl",
    "realized_pnl",
    "closed_realized_pnl",
    "total_bought",
    "opposite_asset",
    "opposite_outcome",
    "opposite_size_after",
    "sold_fraction",
    "action",
    "confidence",
    "explanation",
    "created_at",
)


@dataclass(frozen=True)
class Position:
    asset: str
    size: float
    avg_price: float
    realized_pnl: float
    condition_id: str = ""
    title: str = ""
    outcome: str = ""


class BotState:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self.conn.close()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS processed_trades (
                fingerprint TEXT PRIMARY KEY,
                trader_wallet TEXT NOT NULL,
                asset TEXT NOT NULL,
                condition_id TEXT NOT NULL DEFAULT '',
                side TEXT NOT NULL,
                source_tx TEXT,
                price REAL NOT NULL DEFAULT 0,
                size REAL NOT NULL DEFAULT 0,
                usdc_size REAL NOT NULL DEFAULT 0,
                source_timestamp INTEGER NOT NULL DEFAULT 0,
                title TEXT NOT NULL DEFAULT '',
                outcome TEXT NOT NULL DEFAULT '',
                decision TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS paper_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mode TEXT NOT NULL DEFAULT 'paper',
                source_fingerprint TEXT NOT NULL,
                trader_wallet TEXT NOT NULL,
                asset TEXT NOT NULL,
                condition_id TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                outcome TEXT NOT NULL DEFAULT '',
                side TEXT NOT NULL,
                price REAL NOT NULL,
                size REAL NOT NULL,
                usdc_size REAL NOT NULL,
                status TEXT NOT NULL,
                message TEXT NOT NULL,
                external_order_id TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS paper_positions (
                asset TEXT PRIMARY KEY,
                condition_id TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                outcome TEXT NOT NULL DEFAULT '',
                size REAL NOT NULL,
                avg_price REAL NOT NULL,
                realized_pnl REAL NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS daily_risk (
                day TEXT PRIMARY KEY,
                spent_usdc REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS source_position_events (
                source_fingerprint TEXT PRIMARY KEY,
                trader_wallet TEXT NOT NULL,
                asset TEXT NOT NULL,
                condition_id TEXT NOT NULL DEFAULT '',
                side TEXT NOT NULL,
                price REAL NOT NULL,
                size REAL NOT NULL,
                usdc_size REAL NOT NULL,
                source_timestamp INTEGER NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                outcome TEXT NOT NULL DEFAULT '',
                position_size_before REAL NOT NULL DEFAULT 0,
                position_size_after REAL NOT NULL DEFAULT 0,
                avg_price_after REAL NOT NULL DEFAULT 0,
                current_price REAL NOT NULL DEFAULT 0,
                cash_pnl REAL NOT NULL DEFAULT 0,
                realized_pnl REAL NOT NULL DEFAULT 0,
                closed_realized_pnl REAL NOT NULL DEFAULT 0,
                total_bought REAL NOT NULL DEFAULT 0,
                opposite_asset TEXT NOT NULL DEFAULT '',
                opposite_outcome TEXT NOT NULL DEFAULT '',
                opposite_size_after REAL NOT NULL DEFAULT 0,
                sold_fraction REAL NOT NULL DEFAULT 0,
                action TEXT NOT NULL,
                confidence TEXT NOT NULL,
                explanation TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        self._migrate_schema()
        self.conn.commit()

    def _migrate_schema(self) -> None:
        columns = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(processed_trades)").fetchall()
        }
        additions = {
            "condition_id": "TEXT NOT NULL DEFAULT ''",
            "price": "REAL NOT NULL DEFAULT 0",
            "size": "REAL NOT NULL DEFAULT 0",
            "usdc_size": "REAL NOT NULL DEFAULT 0",
            "source_timestamp": "INTEGER NOT NULL DEFAULT 0",
            "title": "TEXT NOT NULL DEFAULT ''",
            "outcome": "TEXT NOT NULL DEFAULT ''",
        }
        for name, definition in additions.items():
            if name not in columns:
                self.conn.execute(
                    f"ALTER TABLE processed_trades ADD COLUMN {name} {definition}"
                )
        order_columns = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(paper_orders)").fetchall()
        }
        if "mode" not in order_columns:
            self.conn.execute("ALTER TABLE paper_orders ADD COLUMN mode TEXT NOT NULL DEFAULT 'paper'")
        if "external_order_id" not in order_columns:
            self.conn.execute(
                "ALTER TABLE paper_orders ADD COLUMN external_order_id TEXT NOT NULL DEFAULT ''"
            )
        order_additions = {
            "condition_id": "TEXT NOT NULL DEFAULT ''",
            "title": "TEXT NOT NULL DEFAULT ''",
            "outcome": "TEXT NOT NULL DEFAULT ''",
        }
        for name, definition in order_additions.items():
            if name not in order_columns:
                self.conn.execute(
                    f"ALTER TABLE paper_orders ADD COLUMN {name} {definition}"
                )
        position_columns = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(paper_positions)").fetchall()
        }
        position_additions = {
            "condition_id": "TEXT NOT NULL DEFAULT ''",
            "title": "TEXT NOT NULL DEFAULT ''",
            "outcome": "TEXT NOT NULL DEFAULT ''",
        }
        for name, definition in position_additions.items():
            if name not in position_columns:
                self.conn.execute(
                    f"ALTER TABLE paper_positions ADD COLUMN {name} {definition}"
                )

    def seen(self, trade: Trade) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM processed_trades WHERE fingerprint = ?",
            (trade.fingerprint,),
        ).fetchone()
        return row is not None

    def mark_seen(self, trade: Trade, decision: str, reason: str) -> None:
        self.conn.execute(
            """
            INSERT OR IGNORE INTO processed_trades (
                fingerprint, trader_wallet, asset, condition_id, side, source_tx,
                price, size, usdc_size, source_timestamp, title, outcome,
                decision, reason, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trade.fingerprint,
                trade.trader_wallet,
                trade.asset,
                trade.condition_id,
                trade.side,
                trade.transaction_hash,
                trade.price,
                trade.size,
                trade.usdc_size,
                trade.timestamp,
                trade.title,
                trade.outcome,
                decision,
                reason,
                _now(),
            ),
        )
        self.conn.commit()

    def record_source_position_event(self, event: dict[str, object]) -> None:
        payload = {column: event.get(column, "") for column in SOURCE_EVENT_COLUMNS}
        payload["created_at"] = payload.get("created_at") or _now()
        placeholders = ", ".join("?" for _ in SOURCE_EVENT_COLUMNS)
        columns = ", ".join(SOURCE_EVENT_COLUMNS)
        updates = ", ".join(
            f"{column} = excluded.{column}"
            for column in SOURCE_EVENT_COLUMNS
            if column != "source_fingerprint"
        )
        self.conn.execute(
            f"""
            INSERT INTO source_position_events ({columns})
            VALUES ({placeholders})
            ON CONFLICT(source_fingerprint) DO UPDATE SET {updates}
            """,
            tuple(payload[column] for column in SOURCE_EVENT_COLUMNS),
        )
        self.conn.commit()

    def recent_source_position_events(
        self,
        *,
        limit: int = 20,
        wallet: str | None = None,
        asset: str | None = None,
    ) -> list[sqlite3.Row]:
        clauses = []
        params: list[object] = []
        if wallet:
            clauses.append("lower(trader_wallet) = lower(?)")
            params.append(wallet)
        if asset:
            clauses.append("asset = ?")
            params.append(asset)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"""
            SELECT *
            FROM source_position_events
            {where}
            ORDER BY source_timestamp DESC, created_at DESC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
        return rows

    def position(self, asset: str) -> Position:
        row = self.conn.execute(
            """
            SELECT asset, condition_id, title, outcome, size, avg_price, realized_pnl
            FROM paper_positions
            WHERE asset = ?
            """,
            (asset,),
        ).fetchone()
        if not row:
            return Position(asset=asset, size=0.0, avg_price=0.0, realized_pnl=0.0)
        return Position(
            asset=row["asset"],
            size=float(row["size"]),
            avg_price=float(row["avg_price"]),
            realized_pnl=float(row["realized_pnl"]),
            condition_id=str(row["condition_id"] or ""),
            title=str(row["title"] or ""),
            outcome=str(row["outcome"] or ""),
        )

    def positions(self) -> list[Position]:
        rows = self.conn.execute(
            """
            SELECT asset, condition_id, title, outcome, size, avg_price, realized_pnl
            FROM paper_positions
            WHERE ABS(size) > 0.00000001 OR ABS(realized_pnl) > 0.00000001
            ORDER BY updated_at DESC
            """
        ).fetchall()
        return [
            Position(
                asset=row["asset"],
                size=float(row["size"]),
                avg_price=float(row["avg_price"]),
                realized_pnl=float(row["realized_pnl"]),
                condition_id=str(row["condition_id"] or ""),
                title=str(row["title"] or ""),
                outcome=str(row["outcome"] or ""),
            )
            for row in rows
        ]

    def open_opposite_position(self, trade: Trade) -> Position | None:
        if not trade.condition_id:
            return None
        row = self.conn.execute(
            """
            SELECT asset, condition_id, title, outcome, size, avg_price, realized_pnl
            FROM paper_positions
            WHERE condition_id = ?
              AND asset != ?
              AND size > 0.00000001
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (trade.condition_id, trade.asset),
        ).fetchone()
        if not row:
            return None
        return Position(
            asset=str(row["asset"] or ""),
            size=float(row["size"]),
            avg_price=float(row["avg_price"]),
            realized_pnl=float(row["realized_pnl"]),
            condition_id=str(row["condition_id"] or ""),
            title=str(row["title"] or ""),
            outcome=str(row["outcome"] or ""),
        )

    def open_opposite_position_for_trader(
        self,
        trade: Trade,
        trader_wallet: str,
    ) -> Position | None:
        if not trade.condition_id:
            return None
        row = self.conn.execute(
            """
            SELECT asset,
                   condition_id,
                   title,
                   outcome,
                   COALESCE(
                       SUM(
                           CASE
                               WHEN side = 'BUY' THEN size
                               WHEN side = 'SELL' THEN -size
                               ELSE 0
                           END
                       ),
                       0
                   ) AS net_size
            FROM paper_orders
            WHERE lower(trader_wallet) = lower(?)
              AND condition_id = ?
              AND asset != ?
              AND status IN ('filled', 'matched', 'filled_complete', 'complete', 'submitted', 'delayed')
            GROUP BY asset, condition_id, title, outcome
            HAVING net_size > 0.00000001
            ORDER BY MAX(created_at) DESC
            LIMIT 1
            """,
            (trader_wallet, trade.condition_id, trade.asset),
        ).fetchone()
        if not row:
            return None
        return Position(
            asset=str(row["asset"] or ""),
            size=float(row["net_size"]),
            avg_price=0.0,
            realized_pnl=0.0,
            condition_id=str(row["condition_id"] or ""),
            title=str(row["title"] or ""),
            outcome=str(row["outcome"] or ""),
        )

    def open_cost_basis(self) -> float:
        row = self.conn.execute(
            """
            SELECT COALESCE(SUM(size * avg_price), 0) AS cost_basis
            FROM paper_positions
            WHERE size > 0.00000001
            """
        ).fetchone()
        return 0.0 if row is None else float(row["cost_basis"])

    def open_position_count(self) -> int:
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS open_positions
            FROM paper_positions
            WHERE size > 0.00000001
            """
        ).fetchone()
        return 0 if row is None else int(row["open_positions"])

    def open_position_count_for_trader(self, trader_wallet: str) -> int:
        rows = self.conn.execute(
            """
            SELECT asset,
                   COALESCE(
                       SUM(
                           CASE
                               WHEN side = 'BUY' THEN size
                               WHEN side = 'SELL' THEN -size
                               ELSE 0
                           END
                       ),
                       0
                   ) AS net_size
            FROM paper_orders
            WHERE lower(trader_wallet) = lower(?)
              AND status IN ('filled', 'matched', 'filled_complete', 'complete')
            GROUP BY asset
            HAVING net_size > 0.00000001
            """,
            (trader_wallet,),
        ).fetchall()
        return len(rows)

    def open_position_sizes_for_trader(self, trader_wallet: str) -> dict[str, float]:
        rows = self.conn.execute(
            """
            SELECT asset,
                   COALESCE(
                       SUM(
                           CASE
                               WHEN side = 'BUY' THEN size
                               WHEN side = 'SELL' THEN -size
                               ELSE 0
                           END
                       ),
                       0
                   ) AS net_size
            FROM paper_orders
            WHERE lower(trader_wallet) = lower(?)
              AND status IN ('filled', 'matched', 'filled_complete', 'complete')
            GROUP BY asset
            HAVING net_size > 0.00000001
            """,
            (trader_wallet,),
        ).fetchall()
        return {str(row["asset"]): float(row["net_size"]) for row in rows}

    def daily_spent(self) -> float:
        row = self.conn.execute(
            "SELECT spent_usdc FROM daily_risk WHERE day = ?",
            (_today(),),
        ).fetchone()
        return 0.0 if not row else float(row["spent_usdc"])

    def add_daily_spent(self, amount: float) -> None:
        self.conn.execute(
            """
            INSERT INTO daily_risk(day, spent_usdc)
            VALUES (?, ?)
            ON CONFLICT(day) DO UPDATE SET spent_usdc = spent_usdc + excluded.spent_usdc
            """,
            (_today(), amount),
        )
        self.conn.commit()

    def asset_buy_spent(self, asset: str) -> float:
        row = self.conn.execute(
            """
            SELECT COALESCE(SUM(usdc_size), 0) AS spent
            FROM paper_orders
            WHERE asset = ?
              AND side = 'BUY'
              AND status IN ('filled', 'matched', 'submitted', 'delayed')
            """,
            (asset,),
        ).fetchone()
        return 0.0 if row is None else float(row["spent"])

    def condition_buy_spent(self, condition_id: str) -> float:
        if not condition_id:
            return 0.0
        row = self.conn.execute(
            """
            SELECT COALESCE(SUM(usdc_size), 0) AS spent
            FROM paper_orders
            WHERE condition_id = ?
              AND side = 'BUY'
              AND status IN ('filled', 'matched', 'submitted', 'delayed')
            """,
            (condition_id,),
        ).fetchone()
        return 0.0 if row is None else float(row["spent"])

    def asset_buy_count(self, asset: str) -> int:
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS buy_count
            FROM paper_orders
            WHERE asset = ?
              AND side = 'BUY'
              AND status IN ('filled', 'matched', 'submitted', 'delayed')
            """,
            (asset,),
        ).fetchone()
        return 0 if row is None else int(row["buy_count"])

    def condition_buy_count(self, condition_id: str) -> int:
        if not condition_id:
            return 0
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS buy_count
            FROM paper_orders
            WHERE condition_id = ?
              AND side = 'BUY'
              AND status IN ('filled', 'matched', 'submitted', 'delayed')
            """,
            (condition_id,),
        ).fetchone()
        return 0 if row is None else int(row["buy_count"])

    def recently_copied_market(
        self,
        *,
        trader_wallet: str,
        asset: str,
        side: str,
        source_timestamp: int,
        cooldown_seconds: int,
    ) -> bool:
        if cooldown_seconds <= 0:
            return False
        row = self.conn.execute(
            """
            SELECT 1
            FROM processed_trades
            WHERE trader_wallet = ?
              AND asset = ?
              AND side = ?
              AND decision = 'copy'
              AND source_timestamp >= ?
              AND source_timestamp <= ?
            LIMIT 1
            """,
            (
                trader_wallet,
                asset,
                side,
                source_timestamp - cooldown_seconds,
                source_timestamp,
            ),
        ).fetchone()
        return row is not None

    def record_order(
        self,
        trade: Trade,
        decision: CopyDecision,
        *,
        mode: str,
        status: str,
        message: str,
        external_order_id: str = "",
    ) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO paper_orders (
                mode, source_fingerprint, trader_wallet, asset, condition_id,
                title, outcome, side, price, size, usdc_size, status, message,
                external_order_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mode,
                trade.fingerprint,
                trade.trader_wallet,
                decision.asset,
                trade.condition_id,
                trade.title,
                trade.outcome,
                decision.side,
                decision.price,
                decision.size,
                decision.usdc_size,
                status,
                message,
                external_order_id,
                _now(),
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def record_paper_order(
        self,
        trade: Trade,
        decision: CopyDecision,
        *,
        status: str,
        message: str,
    ) -> int:
        return self.record_order(
            trade,
            decision,
            mode="paper",
            status=status,
            message=message,
        )

    def apply_paper_fill(self, decision: CopyDecision, trade: Trade | None = None) -> float:
        pos = self.position(decision.asset)
        condition_id = trade.condition_id if trade and trade.condition_id else pos.condition_id
        title = trade.title if trade and trade.title else pos.title
        outcome = trade.outcome if trade and trade.outcome else pos.outcome
        if decision.side == "BUY":
            new_size = pos.size + decision.size
            new_avg = (
                ((pos.size * pos.avg_price) + (decision.size * decision.price)) / new_size
                if new_size > 0
                else 0.0
            )
            realized = pos.realized_pnl
        else:
            sell_size = min(decision.size, pos.size)
            new_size = pos.size - sell_size
            new_avg = pos.avg_price if new_size > 0 else 0.0
            realized = pos.realized_pnl + sell_size * (decision.price - pos.avg_price)

        self.conn.execute(
            """
            INSERT INTO paper_positions(
                asset, condition_id, title, outcome, size, avg_price,
                realized_pnl, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(asset) DO UPDATE SET
                condition_id = excluded.condition_id,
                title = excluded.title,
                outcome = excluded.outcome,
                size = excluded.size,
                avg_price = excluded.avg_price,
                realized_pnl = excluded.realized_pnl,
                updated_at = excluded.updated_at
            """,
            (
                decision.asset,
                condition_id,
                title,
                outcome,
                new_size,
                new_avg,
                realized,
                _now(),
            ),
        )
        self.conn.commit()
        return realized - pos.realized_pnl


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()
