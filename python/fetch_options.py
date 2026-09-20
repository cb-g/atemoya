"""The options store (36): the full end-of-day option chain for a name and a date from
ThetaData, through the local ThetaTerminal, to data/options/<date>/<TICKER>.json.

    uv run python/fetch_options.py AAPL MSFT PG [--as-of 2026-09-17] [--out data/options]

Every expiry and strike the vendor returns for the date is stored, unfiltered: bid, ask,
mid, sizes, the option's close as last, volume and trade count, with the underlying's
close for the date from the stock endpoint, the vendor's created stamp, and the source.
Requests are paced at ThetaData's guidance (20 per minute by default, --rate). A name the
vendor has no rows for on the date (HTTP 472) is reported and nothing is written. The
terminal must be running (python/theta_terminal.py start); nothing here reads a credential."""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import boundary

BASE_URL = "http://127.0.0.1:25503"
CHAIN_ENDPOINT = "/v3/option/history/eod"
STOCK_ENDPOINT = "/v3/stock/history/eod"
SOURCE = f"thetadata {CHAIN_ENDPOINT} through ThetaTerminal v3"
UNDERLYING_SOURCE = f"thetadata {STOCK_ENDPOINT}"
REQUEST_TIMEOUT = 300.0
NO_DATA = 472


def option_symbol(ticker: str) -> str:
    """ThetaData's option symbols drop the class separator: BRK-B -> BRKB."""
    return ticker.replace("-", "").replace(".", "")


def stock_symbol(ticker: str) -> str:
    """ThetaData's stock symbols keep it as a dot: BRK-B -> BRK.B."""
    return ticker.replace("-", ".")


def compact(date: str) -> str:
    return date.replace("-", "")


class RateLimiter:
    """At most [per_minute] requests in any 60-second window."""

    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self.times: deque[float] = deque()

    def wait(self) -> None:
        now = time.monotonic()
        while self.times and now - self.times[0] >= 60.0:
            self.times.popleft()
        if len(self.times) >= self.per_minute:
            time.sleep(60.0 - (now - self.times[0]) + 0.1)
        self.times.append(time.monotonic())


def get_csv(endpoint: str, params: Mapping[str, str], *, limiter: RateLimiter, base_url: str = BASE_URL) -> list[dict[str, str]] | None:
    """The rows of a CSV response; None when the vendor has no data (472); raises otherwise."""
    limiter.wait()
    query = urllib.parse.urlencode({**params, "format": "csv"})
    url = f"{base_url}{endpoint}?{query}"
    try:
        with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT) as resp:
            text = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code == NO_DATA:
            return None
        raise RuntimeError(f"{endpoint}: HTTP {e.code} {e.reason}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"{endpoint}: {e.reason}; is the terminal running? (uv run python/theta_terminal.py status)") from e
    return list(csv.DictReader(io.StringIO(text)))


def quote_of_row(row: Mapping[str, str]) -> boundary.OptionQuote:
    """One vendor row to one stored quote; every field kept, mid computed."""
    bid = float(row["bid"])
    ask = float(row["ask"])
    return boundary.OptionQuote(
        expiration=row["expiration"].strip('"'),
        strike=float(row["strike"]),
        right=row["right"].strip('"').lower(),
        bid=bid,
        ask=ask,
        mid=(bid + ask) / 2.0,
        bid_size=int(float(row["bid_size"])),
        ask_size=int(float(row["ask_size"])),
        last=float(row["close"]),
        volume=int(float(row["volume"])),
        count=int(float(row["count"])),
    )


def chain_of_rows(ticker: str, rows: Sequence[Mapping[str, str]], *, snapshot_date: str, underlying_close: float, fetched_at: str) -> boundary.OptionChain:
    created = max((r.get("created", "") for r in rows), default="")
    quotes = [quote_of_row(r) for r in rows]
    quotes.sort(key=lambda q: (q.expiration, q.strike, q.right))
    return boundary.OptionChain(
        ticker=ticker,
        snapshot_date=snapshot_date,
        snapshot_timestamp=created,
        source=SOURCE,
        underlying_close=underlying_close,
        underlying_source=UNDERLYING_SOURCE,
        fetched_at=fetched_at,
        quotes=quotes,
    )


MAX_SPAN_DAYS = 365  # the stock endpoint refuses a wider span (HTTP 400)


def spans(start: str, end: str, *, max_days: int = MAX_SPAN_DAYS) -> list[tuple[str, str]]:
    """[start, end] cut into inclusive windows of at most max_days calendar days."""
    a = date.fromisoformat(start)
    stop = date.fromisoformat(end)
    out: list[tuple[str, str]] = []
    while a <= stop:
        b = min(a + timedelta(days=max_days - 1), stop)
        out.append((a.isoformat(), b.isoformat()))
        a = b + timedelta(days=1)
    return out


def stock_closes(ticker: str, start: str, end: str, *, limiter: RateLimiter, base_url: str = BASE_URL) -> dict[str, float]:
    """Close by date (YYYY-MM-DD) from the stock end-of-day endpoint over [start, end], one request per 365-day window."""
    rows: list[dict[str, str]] = []
    for a, b in spans(start, end):
        rows.extend(get_csv(STOCK_ENDPOINT, {"symbol": stock_symbol(ticker), "start_date": compact(a), "end_date": compact(b)}, limiter=limiter, base_url=base_url) or [])
    closes: dict[str, float] = {}
    for r in rows:
        stamp = (r.get("created") or r.get("date") or "").strip('"')
        day = stamp[:10]
        if len(day) == 10 and r.get("close") not in (None, ""):
            closes[day if "-" in day else f"{day[:4]}-{day[4:6]}-{day[6:8]}"] = float(r["close"])
    return closes


def fetch_chain(ticker: str, date: str, *, limiter: RateLimiter, base_url: str = BASE_URL) -> boundary.OptionChain | None:
    rows = get_csv(
        CHAIN_ENDPOINT,
        {"symbol": option_symbol(ticker), "expiration": "*", "strike": "*", "right": "both", "start_date": compact(date), "end_date": compact(date)},
        limiter=limiter,
        base_url=base_url,
    )
    if not rows:
        return None
    closes = stock_closes(ticker, date, date, limiter=limiter, base_url=base_url)
    if date not in closes:
        raise RuntimeError(f"{ticker}: the stock endpoint has no close for {date}; the chain is not stored without its spot")
    return chain_of_rows(ticker, rows, snapshot_date=date, underlying_close=closes[date], fetched_at=datetime.now(UTC).isoformat(timespec="seconds"))


def chain_path(out: Path, ticker: str, date: str) -> Path:
    return out / date / f"{ticker}.json"


def write_chain(chain: boundary.OptionChain, out: Path) -> Path:
    path = chain_path(out, chain.ticker, chain.snapshot_date)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(chain.to_json(), separators=(",", ":")) + "\n")
    return path


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tickers", nargs="+")
    parser.add_argument("--as-of", default=datetime.now(UTC).strftime("%Y-%m-%d"), help="snapshot date, YYYY-MM-DD (default: today, UTC)")
    parser.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "data" / "options"))
    parser.add_argument("--rate", type=int, default=20, help="requests per minute")
    args = parser.parse_args(argv)
    limiter = RateLimiter(args.rate)
    out = Path(args.out)
    failures = 0
    for ticker in args.tickers:
        try:
            chain = fetch_chain(ticker, args.as_of, limiter=limiter)
        except RuntimeError as e:
            print(f"{ticker}: {e}", file=sys.stderr)
            failures += 1
            continue
        if chain is None:
            print(f"{ticker}: no rows on {args.as_of} (vendor 472)")
            continue
        path = write_chain(chain, out)
        expiries = len({q.expiration for q in chain.quotes})
        print(f"{ticker}: {len(chain.quotes)} quotes over {expiries} expiries, spot {chain.underlying_close}, -> {path}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
