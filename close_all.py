"""
close_all.py
------------
Cierra todas las posiciones abiertas en Polymarket enviando órdenes SELL
al CLOB por el tamaño completo de cada posición registrada en la base local.

Uso:
    venv\\Scripts\\python close_all.py
"""
from __future__ import annotations

import os
import time

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from copypoly.config import load_config
from copypoly.executor import LiveExecutor
from copypoly.models import CopyDecision, Trade
from copypoly.state import BotState


def main() -> None:
    config = load_config()
    state = BotState(config.database_path)
    try:
        positions = [p for p in state.positions() if p.size > 0.000001]
        if not positions:
            print("No hay posiciones abiertas.")
            return

        print(f"Encontradas {len(positions)} posición(es) abiertas. Cerrando...\n")
        executor = LiveExecutor(config, state)

        ok_count = 0
        fail_count = 0
        for pos in positions:
            label = pos.outcome or pos.asset[:12]
            print(f"Cerrando: {label} | size={pos.size:.4f} | avg={pos.avg_price:.4f} | {pos.title[:60]}")

            trade = Trade(
                trader_wallet=config.clob_funder or "0x0000000000000000000000000000000000000000",
                side="SELL",
                asset=pos.asset,
                condition_id=pos.condition_id,
                size=pos.size,
                price=pos.avg_price or 0.5,
                timestamp=int(time.time()),
                title=pos.title,
                outcome=pos.outcome,
                transaction_hash="close_all",
            )
            decision = CopyDecision(
                should_copy=True,
                reason="close_all",
                side="SELL",
                asset=pos.asset,
                price=max(0.01, (pos.avg_price or 0.5) * 0.9),
                size=pos.size,
                usdc_size=pos.size * (pos.avg_price or 0.5),
            )

            result = executor.execute(trade, decision)
            status = "OK  " if result.ok else "FAIL"
            print(f"  [{status}] {result.message}\n")
            if result.ok:
                ok_count += 1
            else:
                fail_count += 1

        print(f"Listo. OK={ok_count}  FAIL={fail_count}")
    finally:
        state.close()


if __name__ == "__main__":
    main()
