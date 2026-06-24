from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from data.kotak_neo_feed import KotakLiveTick, KotakNeoFeed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Kotak Neo one-symbol live tick test")
    parser.add_argument("--symbol", default="RELIANCE", help="Display symbol for logs only")
    parser.add_argument("--token", default="", help="Kotak instrument token. Optional if symbol can be resolved from scrip master.")
    parser.add_argument("--segment", default="nse_cm", help="Exchange segment, for example nse_cm")
    parser.add_argument("--totp", default="", help="6-digit TOTP code if you do not want to use KOTAK_TOTP_SECRET")
    parser.add_argument("--reconnect-delay", type=float, default=5.0, help="Seconds between reconnect attempts")
    parser.add_argument("--max-reconnects", type=int, default=0, help="0 means unlimited reconnect attempts")
    return parser


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def build_feed(totp: str) -> KotakNeoFeed:
    return KotakNeoFeed(
        consumer_key=(os.getenv("KOTAK_CONSUMER_KEY") or os.getenv("KOTAK_NEO_CONSUMER_KEY")),
        access_token=(os.getenv("KOTAK_ACCESS_TOKEN") or os.getenv("KOTAK_NEO_ACCESS_TOKEN")),
        environment=os.getenv("KOTAK_ENVIRONMENT", "prod"),
        neo_fin_key=os.getenv("KOTAK_NEO_FIN_KEY"),
        mobile_number=os.getenv("KOTAK_MOBILE_NUMBER"),
        ucc=os.getenv("KOTAK_UCC"),
        mpin=os.getenv("KOTAK_MPIN"),
        totp_secret=os.getenv("KOTAK_TOTP_SECRET"),
        totp_code=totp,
    )


def main() -> int:
    load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env", override=False)
    configure_logging()
    args = build_parser().parse_args()
    log = logging.getLogger("kotak_live_test")
    feed = build_feed(args.totp.strip())
    keep_running = True

    def on_tick(tick: KotakLiveTick) -> None:
        log.info(
            "TICK symbol=%s token=%s segment=%s ltp=%s at=%s",
            tick.symbol,
            tick.instrument_token,
            tick.exchange_segment,
            tick.ltp,
            tick.received_at,
        )

    def on_close(message: str) -> None:
        log.warning("SOCKET_CLOSE %s", message)

    def on_error(message: str) -> None:
        log.error("SOCKET_ERROR %s", message)

    def shutdown(*_: object) -> None:
        nonlocal keep_running
        keep_running = False
        log.info("Stopping live feed.")
        feed.stop_live_feed()

    signal.signal(signal.SIGINT, shutdown)
    try:
        signal.signal(signal.SIGTERM, shutdown)
    except Exception:
        pass

    instrument = {
        "instrument_token": args.token.strip(),
        "exchange_segment": args.segment.strip().lower(),
        "symbol": args.symbol.strip().upper(),
    }
    if not instrument["instrument_token"]:
        resolved = feed.resolve_tokens([instrument["symbol"]], exchange_segment=instrument["exchange_segment"])
        token = resolved.get(instrument["symbol"], "").strip()
        if not token:
            log.error(
                "Could not resolve instrument token for symbol=%s segment=%s. Pass --token explicitly.",
                instrument["symbol"],
                instrument["exchange_segment"],
            )
            return 2
        instrument["instrument_token"] = token
        log.info(
            "Resolved symbol=%s segment=%s to instrument_token=%s",
            instrument["symbol"],
            instrument["exchange_segment"],
            instrument["instrument_token"],
        )
    log.info("Starting Kotak live test for %s", instrument)
    feed.start_live_feed(
        instruments=[instrument],
        on_tick=on_tick,
        on_close=on_close,
        on_error=on_error,
        reconnect=True,
        reconnect_delay=args.reconnect_delay,
        max_reconnect_attempts=None if args.max_reconnects == 0 else args.max_reconnects,
    )
    log.info("Live session ready. Waiting for ticks. Press Ctrl+C to stop.")

    try:
        while keep_running:
            time.sleep(1)
    finally:
        feed.stop_live_feed()
    return 0


if __name__ == "__main__":
    sys.exit(main())
