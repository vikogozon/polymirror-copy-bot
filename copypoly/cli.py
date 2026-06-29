from __future__ import annotations

import argparse
import sys

from .config import load_config
from .executor import LiveExecutor
from .single_wallet_copier import DEFAULT_COPY_WALLET, run_single_wallet_copier
from .state import BotState


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Single-wallet Polymarket copier.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    copy_parser = subparsers.add_parser("copy-wallet")
    copy_parser.add_argument("--wallet")
    copy_parser.add_argument("--once", action="store_true")

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--wallet")
    run_parser.add_argument("--once", action="store_true")

    subparsers.add_parser("live-check")
    subparsers.add_parser("paper-status")

    args = parser.parse_args(argv)

    try:
        if args.command in {"copy-wallet", "run"}:
            run_single_wallet_copier(wallet=args.wallet, once=args.once)
            return 0

        config = load_config()
        state = BotState(config.database_path)
        try:
            if args.command == "live-check":
                return _live_check(config, state)
            if args.command == "paper-status":
                return _paper_status(state)
        finally:
            state.close()
    except KeyboardInterrupt:
        print("Stopped.")
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


def _live_check(config, state: BotState) -> int:
    missing = []
    if not config.clob_private_key:
        missing.append("CLOB_PRIVATE_KEY or POLYMARKET_PRIVATE_KEY")
    if not config.clob_api_key:
        missing.append("CLOB_API_KEY")
    if not config.clob_secret:
        missing.append("CLOB_SECRET or CLOB_API_SECRET")
    if not config.clob_pass_phrase:
        missing.append("CLOB_PASS_PHRASE or CLOB_API_PASSPHRASE")
    if missing:
        print("Live credentials are incomplete:")
        for name in missing:
            print(f"- {name}")
        return 1

    executor = LiveExecutor(config, state)
    open_orders = executor.check_connection()
    print("Live CLOB credentials OK.")
    print(f"Host: {config.clob_host}")
    print(f"Watching: {', '.join(config.watchlist_wallets)}")
    print(f"Signature type: {config.clob_signature_type}")
    print(f"Funder set: {'yes' if config.clob_funder else 'no'}")
    print(f"Open orders visible: {open_orders}")
    print("No order was placed.")
    return 0


def _paper_status(state: BotState) -> int:
    positions = state.positions()
    if not positions:
        print("No local copied positions yet.")
        return 0
    total_cost = 0.0
    for position in positions:
        cost = position.size * position.avg_price
        total_cost += cost
        print(
            f"{position.outcome or position.asset[:12]} | "
            f"size {position.size:.4f} | avg {position.avg_price:.4f} | "
            f"cost ${cost:.2f} | {position.title[:70]}"
        )
    print(f"Open local cost basis: ${total_cost:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
