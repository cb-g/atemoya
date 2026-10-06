"""Fill the Form 4 cache for the three calendar years the trader classification reads (83).

    uv run python/insider_history.py [--universe reference/universe.json] [--as-of YYYY-MM-DD] [--tickers AAPL MSFT]

The insiders block tells a routine trader from an opportunistic one by the timing of this
name's open-market trades over the three calendar years before the as-of year (see
python/insiders.py). The valuation path never fetches that history: it reads what is on
disk and, where a page or a document the index lists is not there, leaves every trader
unclassified and names this command. This fills the cache, once: for every universe name
with an SEC filer, the older submissions pages whose span meets the three years, then every
Form 4 and 4/A document filed in them, paced as every SEC request here is. A document is
immutable once filed and is never fetched twice, so a second run costs the index reads.

Hours the first time on a universe of this size; nothing is tracked, everything under
data/insiders/ and data/sec/."""

from __future__ import annotations

import argparse
import sys
import urllib.error
from datetime import date, timedelta
from pathlib import Path

import fetch
import fetch_sec
import insiders
import universe as universe_file

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_UNIVERSE = REPO_ROOT / "reference" / "universe.json"


def fill(ciks: dict[str, str], as_of: date, user_agent: str, *, log: bool = True) -> tuple[int, int, int]:
    """(pages fetched, documents fetched, documents unreachable) for the three calendar years
    before [as_of]'s year, over ticker -> CIK."""
    first, last = insiders.history_span(as_of)
    last_filed = last + timedelta(days=fetch_sec.INSIDER_FILING_LAG_DAYS)
    pages = documents = failed = 0
    for n, (ticker, cik) in enumerate(sorted(ciks.items()), 1):
        index = fetch_sec.submissions(cik, user_agent)
        if index is None:
            if log:
                print(f"  {ticker}: no submissions index for CIK {cik}", flush=True)
            continue
        for name in fetch_sec.submissions_pages(index, first, last_filed):
            if (fetch_sec.CACHE_DIR / name).exists():
                continue
            try:
                fetch_sec.submissions_page(name, user_agent)
                pages += 1
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
                if log:
                    print(f"  {ticker}: page {name}: {type(e).__name__}: {e}", flush=True)
        filings, absent = fetch_sec.form4_filings_cached(cik, index, first, last_filed)
        got = 0
        for accession, _filed, document in filings:
            try:
                if fetch_sec.insider_document(cik, accession, document, user_agent):
                    got += 1
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
                failed += 1
                if log:
                    print(f"  {ticker}: {accession}: {type(e).__name__}: {e}", flush=True)
        documents += got
        if log:
            print(f"{n}/{len(ciks)} {ticker}: {len(filings)} filing(s) {first.year}-{last.year}, {got} fetched"
                  + (f", {len(absent)} page(s) unreachable" if absent else ""), flush=True)
    return pages, documents, failed


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--universe", type=Path, default=DEFAULT_UNIVERSE)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today(), help="the three calendar years before this date's year")
    parser.add_argument("--tickers", nargs="*", default=None, help="only these universe names")
    args = parser.parse_args(argv)
    entries = universe_file.load(args.universe).tickers
    wanted = set(args.tickers) if args.tickers else None
    sec = fetch.SecContext()
    ciks: dict[str, str] = {}
    for e in entries:
        if wanted is not None and e.ticker not in wanted:
            continue
        cik, _source = fetch.cik_of(e.ticker, sec.tickers, e.cik)
        if cik is not None:
            ciks[e.ticker] = cik
    first, last = insiders.history_span(args.as_of)
    print(f"{len(ciks)} names with an SEC filer; Form 4 history {first.year}-{last.year}", flush=True)
    pages, documents, failed = fill(ciks, args.as_of, sec.user_agent)
    print(f"{pages} page(s) and {documents} document(s) fetched, {failed} unreachable")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
