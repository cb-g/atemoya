"""The trade tape (50): every print for every contract that traded, with the quote at the
print, from ThetaData through the local terminal, to data/tape/<date>/<TICKER>.json.

    uv run python/fetch_tape.py AAPL NVDA --from 2026-06-25 --to 2026-09-17 [--out data/tape] [--rate 20]

The contracts that traded on a day are the store's chain for that day with a positive
volume, so the store must hold the day (python/fetch_options.py). Per contract one request
to the trade-with-quote endpoint, paced at ThetaData's guidance; a print is
{expiration, strike, right, time, price, size, bid, ask}. The terminal must be running
(python/theta_terminal.py status); if not, this says so and stops. The endpoint needs a
ThetaData subscription above the free tier: a 403 is reported as the vendor words it and
the run stops, nothing written. The tape is never read by the batch. Nothing here reads a
credential."""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from datetime import date, timedelta
from pathlib import Path

import fetch_options as fo
import theta_terminal as tt

TAPE_ENDPOINT = "/v3/option/history/trade_quote"
SOURCE = f"thetadata {TAPE_ENDPOINT} through ThetaTerminal v3"
REPO_ROOT = Path(__file__).resolve().parents[1]


class Subscription(RuntimeError):
    """The vendor refused the endpoint for the account's tier."""


def get_csv(endpoint: str, params: Mapping[str, str], *, limiter: fo.RateLimiter, base_url: str = fo.BASE_URL) -> list[dict[str, str]] | None:
    limiter.wait()
    url = f"{base_url}{endpoint}?{urllib.parse.urlencode({**params, 'format': 'csv'})}"
    try:
        with urllib.request.urlopen(url, timeout=fo.REQUEST_TIMEOUT) as resp:
            text = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code == fo.NO_DATA:
            return None
        body = e.read().decode("utf-8", "replace").strip()
        if e.code == 403:
            raise Subscription(body or "HTTP 403") from e
        raise RuntimeError(f"{endpoint}: HTTP {e.code} {e.reason}") from e
    return list(csv.DictReader(io.StringIO(text)))


def print_of_row(row: Mapping[str, str], expiration: str, strike: float, right: str) -> dict[str, object] | None:
    """One vendor row to one stored print; the column names are the vendor's and a row
    without a price or a quote is dropped."""
    def pick(*names: str) -> str | None:
        for n in names:
            v = row.get(n)
            if v not in (None, ""):
                return str(v).strip('"')
        return None
    price, size, bid, ask = pick("price"), pick("size"), pick("bid"), pick("ask")
    stamp = pick("time", "timestamp", "created", "ms_of_day")
    if price is None or bid is None or ask is None or stamp is None:
        return None
    return {"expiration": expiration, "strike": strike, "right": right, "time": stamp, "price": float(price), "size": int(float(size or "0")), "bid": float(bid), "ask": float(ask)}


def traded_contracts(store: Path, ticker: str, day: str) -> list[tuple[str, float, str]] | None:
    p = store / day / f"{ticker}.json"
    if not p.exists():
        return None
    chain = json.loads(p.read_text())
    return sorted({(str(q["expiration"]), float(q["strike"]), str(q["right"])) for q in chain["quotes"] if int(q["volume"]) > 0})


def fetch_day(ticker: str, day: str, contracts: list[tuple[str, float, str]], *, limiter: fo.RateLimiter) -> dict[str, object]:
    prints: list[dict[str, object]] = []
    for expiration, strike, right in contracts:
        rows = get_csv(TAPE_ENDPOINT, {"symbol": fo.option_symbol(ticker), "expiration": fo.compact(expiration), "strike": f"{strike:g}", "right": right,
                                       "start_date": fo.compact(day), "end_date": fo.compact(day)}, limiter=limiter)
        for r in rows or []:
            p = print_of_row(r, expiration, strike, right)
            if p is not None:
                prints.append(p)
    return {"ticker": ticker, "date": day, "source": SOURCE, "contracts_traded": len(contracts), "prints": prints}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tickers", nargs="+")
    parser.add_argument("--from", dest="start", required=True)
    parser.add_argument("--to", dest="end", required=True)
    parser.add_argument("--store", type=Path, default=REPO_ROOT / "data" / "options")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "data" / "tape")
    parser.add_argument("--rate", type=int, default=20)
    args = parser.parse_args(argv)
    if not tt.port_open():
        print("ThetaTerminal is not answering on its port: start it with uv run python/theta_terminal.py start", file=sys.stderr)
        return 1
    limiter = fo.RateLimiter(args.rate)
    d0, d1 = date.fromisoformat(args.start), date.fromisoformat(args.end)
    days = [(d0 + timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]
    for ticker in args.tickers:
        for day in days:
            contracts = traded_contracts(args.store, ticker, day)
            if contracts is None:
                continue
            try:
                tape = fetch_day(ticker, day, contracts, limiter=limiter)
            except Subscription as e:
                print(f"{ticker} {day}: the vendor refused the tape endpoint for this account: {e}", file=sys.stderr)
                return 2
            out = args.out / day / f"{ticker}.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(tape, separators=(",", ":")) + "\n")
            print(f"{ticker} {day}: {len(contracts)} contracts traded, {len(tape['prints'])} prints -> {out}")  # pyright: ignore[reportArgumentType]
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
