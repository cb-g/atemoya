"""The broad panel: every SEC filer with a ticker today, each June since 2010.

    uv run python/broad_panel.py [--first-year 2009] [--last-year YYYY] [--refresh] [--retry-missing]

The anchor study has eighteen quarter-ends on a hundred and seventy-eight names, all inside
one market. It cannot tell a measure that never worked from one that did not work lately.
This builds the longer, wider sample that can: no model of ours, only filed accounting
items, a market value on the day and what the price did over the next twelve months.

Sources, nothing tracked, everything under data/broad/:

- SEC's frames API, one request per element and period: the fiscal year's flows
  (`CY<year>`: net income, operating cash flow, revenue, gross profit, cost of revenue,
  operating income, the weighted diluted share count) and its balance sheet (the four
  quarter-instant frames `CY<year>Q<n>I`, matched to the flows by filer and fiscal year
  end: total assets, current assets, current liabilities, stockholders' equity, long-term
  debt). A value is the latest the filer has reported for the period, so a later
  restatement is in it; the frames carry no filing date to cut on.
- the cover-page share count, `dei:EntityCommonStockSharesOutstanding`, from the same API:
  an instant on a stated date that no later filing restates.
- the vendor's monthly bars per ticker, bulk: the split-adjusted close, the close adjusted
  for dividends as well, and the splits by month.

Contract. `data/broad/panel.jsonl` holds one row per filer and formation year T: formed on
the last trading day of June of T from the fiscal year whose frame is T-1, so every
statement is at least a few months old (the convention of Fama and French, 1992). Market
value is the newest cover-page count dated in January to June of T, moved onto today's
split basis by every split after its month, times June's split-adjusted close; the two
bases are reconciled as the vendor's split adjustment requires, and a count whose own
month carries a split is ambiguous and the row carries no market value, with the reason.
`forward_12m` is the dividend-adjusted return to the following June and `spy_12m` SPY's
over the same months; null with the reason where the ticker has no bar at either end.

What it is not. Survivors only: a filer is in the sample only if it has a ticker in SEC's
map today, so the companies that failed or were bought are missing from every year, more of
them the further back, and a row's count of years says nothing about them. A filer with
several share classes reports its count per class and none in total, and is missing. The
row says what was filed; ROWS_MIN_REVENUE and ROWS_MIN_CAP keep shells out."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import cast

import fetch_sec

REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT = REPO_ROOT / "data" / "broad"
FRAMES = ROOT / "frames"
PRICES = ROOT / "prices"
OUT = ROOT / "panel.jsonl"
URL = "https://data.sec.gov/api/xbrl/frames/{taxonomy}/{tag}/{unit}/{frame}.json"
BENCHMARK = "SPY"
FIRST_YEAR = 2009
ROWS_MIN_REVENUE = 5e7   # dollars: below it a filer is a shell or a start-up, not a business to rank
ROWS_MIN_CAP = 1e8
CHUNK = 200
# field -> elements in order of preference (the first carrying the filer-year wins)
FLOWS: dict[str, tuple[str, ...]] = {
    "net_income": ("NetIncomeLoss",),
    "operating_cash_flow": ("NetCashProvidedByUsedInOperatingActivities",),
    "revenue": ("Revenues", "RevenuesNetOfInterestExpense", "RevenueFromContractWithCustomerExcludingAssessedTax",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet"),
    "gross_profit": ("GrossProfit",),
    "cost_of_revenue": ("CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"),
    "operating_income": ("OperatingIncomeLoss",),
    "weighted_shares": ("WeightedAverageNumberOfDilutedSharesOutstanding",),
}
STOCKS: dict[str, tuple[str, ...]] = {
    "total_assets": ("Assets",),
    "current_assets": ("AssetsCurrent",),
    "current_liabilities": ("LiabilitiesCurrent",),
    "book_equity": ("StockholdersEquity",),
    "long_term_debt": ("LongTermDebtNoncurrent", "LongTermDebt"),
}
SHARE_UNITS = {"weighted_shares": "shares"}
Json = dict[str, object]


def frame(taxonomy: str, tag: str, unit: str, name: str, user_agent: str, *, refresh: bool = False) -> list[Json]:
    """One frame as fetched and cached; [] when SEC has none."""
    path = FRAMES / f"{taxonomy}-{tag}-{name}.json"
    if path.exists() and not refresh:
        return cast(list[Json], json.loads(path.read_text()).get("data", []))
    try:
        body = fetch_sec._get(URL.format(taxonomy=taxonomy, tag=tag, unit=unit, frame=name), user_agent)  # pyright: ignore[reportPrivateUsage]
    except Exception as e:  # noqa: BLE001
        if "404" not in str(e):
            raise
        body = b'{"data": []}'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return cast(list[Json], json.loads(body).get("data", []))


def number(row: Json) -> float | None:
    v = row.get("val")
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def flows_of(frames: dict[str, list[Json]]) -> dict[int, Json]:
    """cik -> the fiscal year's fields and its end date, from the duration frames of one year.
    The fiscal year end is net income's; a field filed for another end is another period's."""
    out: dict[int, Json] = {}
    for row in frames.get("NetIncomeLoss", []):
        cik, end, val = row.get("cik"), row.get("end"), number(row)
        if isinstance(cik, int) and isinstance(end, str) and val is not None:
            out[cik] = {"fiscal_year_end": end, "net_income": val}
    for field, elements in FLOWS.items():
        if field == "net_income":
            continue
        for tag in elements:
            for row in frames.get(tag, []):
                cik, val = row.get("cik"), number(row)
                if isinstance(cik, int) and cik in out and val is not None and row.get("end") == out[cik]["fiscal_year_end"]:
                    out[cik].setdefault(field, val)
    return out


def stocks_of(frames: dict[str, list[Json]]) -> dict[tuple[int, str], Json]:
    """(cik, date) -> balance-sheet fields on that date, from the instant frames given."""
    out: dict[tuple[int, str], Json] = {}
    for field, elements in STOCKS.items():
        for tag in elements:
            for row in frames.get(tag, []):
                cik, end, val = row.get("cik"), row.get("end"), number(row)
                if isinstance(cik, int) and isinstance(end, str) and val is not None:
                    out.setdefault((cik, end), {}).setdefault(field, val)
    return out


def cover_count(rows: list[Json], year: int) -> dict[int, tuple[str, float]]:
    """cik -> (cover date, shares): the newest cover-page count dated January to June of [year]."""
    out: dict[int, tuple[str, float]] = {}
    lo, hi = f"{year}-01-01", f"{year}-06-30"
    for row in rows:
        cik, end, val = row.get("cik"), row.get("end"), number(row)
        if isinstance(cik, int) and isinstance(end, str) and val is not None and val > 0 and lo <= end <= hi:
            if cik not in out or end > out[cik][0]:
                out[cik] = (end, val)
    return out


def split_factor(splits: dict[str, float], cover_date: str) -> tuple[float | None, str | None]:
    """The product of the split ratios in months after the cover date's month, which moves a
    count stated on that date onto today's split basis; None with the reason when the cover
    date's own month carries a split, since the monthly bar cannot say which came first."""
    month = cover_date[:7]
    if month in splits:
        return None, f"a split in {month}, the month of the cover-page count: which came first is not readable from monthly bars"
    factor = 1.0
    for m, ratio in splits.items():
        if m > month and ratio > 0:
            factor *= ratio
    return factor, None


RETRY_CHUNK = 40
RETRY_PAUSE_SECONDS = 20.0


def _download(chunk: list[str]) -> dict[str, Json]:
    """One bulk request: ticker -> closes, dividend-adjusted closes and splits by month, for
    the tickers the vendor answered."""
    import pandas as pd  # noqa: PLC0415
    import yfinance as yf  # noqa: PLC0415

    df = cast(pd.DataFrame, yf.download(chunk, start=f"{FIRST_YEAR}-12-01", interval="1mo", auto_adjust=False, actions=True,  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]
                                        progress=False, group_by="ticker", threads=True))
    got: dict[str, Json] = {}
    for ticker in chunk:
        try:
            sub = cast(pd.DataFrame, df[ticker])
        except KeyError:
            continue
        close: dict[str, float] = {}
        adjusted: dict[str, float] = {}
        splits: dict[str, float] = {}
        for stamp, row in sub.iterrows():  # pyright: ignore[reportUnknownVariableType]
            month = cast(pd.Timestamp, stamp).strftime("%Y-%m")
            c, a, s = row.get("Close"), row.get("Adj Close"), row.get("Stock Splits")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            if isinstance(c, float) and c == c and c > 0:
                close[month] = c
            if isinstance(a, float) and a == a and a > 0:
                adjusted[month] = a
            if isinstance(s, float) and s == s and s > 0:
                splits[month] = s
        if close:
            got[ticker] = {"close": close, "adjusted": adjusted, "splits": splits}
    return got


def prices_of(tickers: list[str], *, refresh: bool = False, retry: bool = False, log: bool = True) -> dict[str, Json]:
    """ticker -> {"close": {month: split-adjusted close}, "adjusted": {month: dividend-adjusted
    close}, "splits": {month: ratio}}, bulk-fetched in chunks and cached per chunk. The vendor
    answers a long run of bulk requests with a rate limit, which leaves a chunk's tickers
    without bars as if they did not exist; [retry] asks again for every ticker still without
    bars, in small paced chunks, each kept as its own cache file. A ticker absent after that
    is one the vendor does not carry."""
    import time  # noqa: PLC0415

    PRICES.mkdir(parents=True, exist_ok=True)
    if refresh:
        for old in PRICES.glob("*.json"):
            old.unlink()
    out: dict[str, Json] = {}
    for path in sorted(PRICES.glob("*.json")):
        out.update(cast(dict[str, Json], json.loads(path.read_text())))
    wanted = sorted(set(tickers))
    for n in range(0, len(wanted), CHUNK):
        chunk = wanted[n:n + CHUNK]
        path = PRICES / f"{chunk[0]}-{chunk[-1]}-{len(chunk)}.json"
        if path.exists():
            continue
        got = _download(chunk)
        path.write_text(json.dumps(got))
        out.update(got)
        if log:
            print(f"prices {min(n + CHUNK, len(wanted))}/{len(wanted)}: {len(got)} of {len(chunk)} tickers carry bars", flush=True)
    if retry:
        missing = [t for t in wanted if t not in out]
        for n in range(0, len(missing), RETRY_CHUNK):
            chunk = missing[n:n + RETRY_CHUNK]
            got = _download(chunk)
            if got:
                (PRICES / f"retry-{chunk[0]}-{chunk[-1]}-{len(chunk)}.json").write_text(json.dumps(got))
                out.update(got)
            if log:
                print(f"retry {min(n + RETRY_CHUNK, len(missing))}/{len(missing)}: {len(got)} of {len(chunk)} answered", flush=True)
            time.sleep(RETRY_PAUSE_SECONDS)
    return out


def row_of(cik: int, ticker: str, name: str, year: int, flow: Json, prior: Json | None, stocks: dict[tuple[int, str], Json],
           cover: tuple[str, float] | None, prices: dict[str, Json]) -> Json:
    """One filer's row for formation year [year]: the fiscal year filed, the year before for
    the changes, the market value on the day and the next twelve months."""
    end = cast(str, flow["fiscal_year_end"])
    row: Json = {"cik": cik, "ticker": ticker, "name": name, "formation": f"{year}-06", **flow, **stocks.get((cik, end), {})}
    if prior is not None:
        prior_end = cast(str, prior["fiscal_year_end"])
        row["prior"] = {**prior, **stocks.get((cik, prior_end), {})}
    bars = prices.get(ticker)
    june, next_june = f"{year}-06", f"{year + 1}-06"
    if bars is None:
        row["market_cap_reason"] = row["forward_reason"] = "the vendor carries no monthly bars for the ticker"
        return row
    close, adjusted, splits = (cast(dict[str, float], bars[k]) for k in ("close", "adjusted", "splits"))
    if cover is None:
        row["market_cap_reason"] = f"no cover-page share count dated January to June of {year}"
    elif june not in close:
        row["market_cap_reason"] = f"no bar for {june}"
    else:
        factor, why = split_factor(splits, cover[0])
        if factor is None:
            row["market_cap_reason"] = why
        else:
            row["market_cap"] = cover[1] * factor * close[june]
            row["cover_date"], row["cover_shares"], row["split_factor"] = cover[0], cover[1], factor
    if june in adjusted and next_june in adjusted:
        row["forward_12m"] = adjusted[next_june] / adjusted[june] - 1
    else:
        row["forward_reason"] = f"no bar for {june if june not in adjusted else next_june}"
    spy = prices.get(BENCHMARK)
    if spy is not None:
        s = cast(dict[str, float], spy["adjusted"])
        if june in s and next_june in s:
            row["spy_12m"] = s[next_june] / s[june] - 1
    return row


def build(first: int, last: int, user_agent: str, *, refresh: bool = False, retry: bool = False, log: bool = True) -> list[Json]:
    table = fetch_sec.tickers_table(user_agent)
    tickers: dict[int, tuple[str, str]] = {}
    for entry in table.values():
        e = cast(Json, entry)
        cik = e.get("cik_str")
        if isinstance(cik, int):
            tickers.setdefault(cik, (str(e.get("ticker", "")).upper(), str(e.get("title", ""))))
    flows: dict[int, dict[int, Json]] = {}
    stocks: dict[tuple[int, str], Json] = {}
    covers: dict[int, dict[int, tuple[str, float]]] = {}
    for year in range(first, last + 1):
        duration = {tag: frame("us-gaap", tag, SHARE_UNITS.get(field, "USD"), f"CY{year}", user_agent, refresh=refresh)
                    for field, elements in FLOWS.items() for tag in elements}
        flows[year] = flows_of(duration)
        instants: dict[str, list[Json]] = {}
        # a fiscal year in frame CY<year> may end in the first weeks of the next calendar year
        for y, quarters in ((year, (1, 2, 3, 4)), (year + 1, (1,))):
            for q in quarters:
                for elements in STOCKS.values():
                    for tag in elements:
                        instants.setdefault(tag, []).extend(frame("us-gaap", tag, "USD", f"CY{y}Q{q}I", user_agent, refresh=refresh))
        stocks.update(stocks_of(instants))
        counts: list[Json] = []
        for q in (1, 2, 3):
            counts += frame("dei", "EntityCommonStockSharesOutstanding", "shares", f"CY{year + 1}Q{q}I", user_agent, refresh=refresh)
        covers[year + 1] = cover_count(counts, year + 1)
        if log:
            print(f"CY{year}: {len(flows[year])} filers with a fiscal year, {len(covers[year + 1])} cover counts for June {year + 1}", flush=True)
    wanted = sorted({tickers[cik][0] for by in flows.values() for cik in by if cik in tickers and tickers[cik][0]})
    prices = prices_of([*wanted, BENCHMARK], refresh=refresh, retry=retry, log=log)
    rows: list[Json] = []
    for year in range(first + 1, last + 2):
        fiscal = flows.get(year - 1, {})
        for cik, flow in sorted(fiscal.items()):
            if cik not in tickers or not tickers[cik][0]:
                continue
            revenue = flow.get("revenue")
            if not isinstance(revenue, float) or revenue < ROWS_MIN_REVENUE:
                continue
            row = row_of(cik, tickers[cik][0], tickers[cik][1], year, flow, flows.get(year - 2, {}).get(cik), stocks,
                         covers.get(year, {}).get(cik), prices)
            cap = row.get("market_cap")
            if isinstance(cap, float) and cap < ROWS_MIN_CAP:
                continue
            rows.append(row)
    return rows


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--first-year", type=int, default=FIRST_YEAR, help="the first fiscal year read")
    parser.add_argument("--last-year", type=int, default=date.today().year - 1, help="the last fiscal year read; its rows are formed the June after")
    parser.add_argument("--refresh", action="store_true", help="fetch every frame and every price chunk again")
    parser.add_argument("--retry-missing", action="store_true", help="ask the vendor again, slowly, for every ticker still without bars: a bulk run is rate-limited part of the way through")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    out: Path = args.out
    rows = build(int(args.first_year), int(args.last_year), fetch_sec.identity(), refresh=bool(args.refresh), retry=bool(args.retry_missing))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    with_cap = sum(1 for r in rows if "market_cap" in r)
    with_return = sum(1 for r in rows if "forward_12m" in r)
    print(f"{len(rows)} rows on {len({r['cik'] for r in rows})} filers, {with_cap} with a market value, {with_return} with a forward return -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
