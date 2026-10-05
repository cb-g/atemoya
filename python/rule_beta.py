"""The rule panel sorted on beta: did the market pay for it among the largest companies?

    uv run python/rule_beta.py [--fetch-benchmark] [--out output/rule_beta]

This tool's cost of equity is a risk-free rate plus a premium times beta, so a name with
twice the beta is charged twice the premium. Whether the market has paid that premium is a
question about returns, and three papers read for this tool bear on it:

- Frazzini and Pedersen, "Betting Against Beta", NBER Working Paper 16601, December 2010,
  doi:10.3386/w16601. Across ten beta-sorted portfolios of US stocks the monthly excess
  return is flat, 0.99 per cent for the lowest beta and 1.02 for the highest, while the
  CAPM alpha falls from 0.54 to -0.05 and the realised beta rises from 0.75 to 1.82
  (Table III). The beta estimator here is theirs (equations 14 and 15).
- Novy-Marx and Velikov, "Betting Against Betting Against Beta", working paper, November
  2018, doi:10.2139/ssrn.3300965. Most of that paper's premium comes from weighting small
  stocks equally; weighted by value it is about half. So every table here is given under
  both weightings, and the names are the largest five hundred to begin with.
- Levi and Welch, "Best Practice for Cost-of-Capital Estimates", Journal of Financial and
  Quantitative Analysis 52(2), 2017, doi:10.1017/S0022109017000114. Between a beta of 0.0
  and one of 1.5 the textbook difference in the cost of equity is about ten points a year;
  shrunk betas and a long-run premium bring it to about two (page 459). The last line of
  each table reads the same quantity off these names: the return earned per unit of
  realised beta across the fifths, beside the market's own excess return.

Each table ends with two lines for that. The first is the return earned per unit of
realised beta between the highest fifth and the lowest, beside the benchmark's excess
return over the same months: equal, if beta was paid in full. The second is the alpha the
spread would show had beta not been paid at all, the first paper's flat line: the spread's
beta times the benchmark's premium, below zero.

Method. Each June every name in the rule panel, valued or refused, is given a beta from
the daily returns of the year to the date, at least MIN_DAYS of them: the sum of the slopes
of its return on the benchmark's return of the same day and of each of the LAGS days
before, then halved toward one, as the first paper does. The names are cut into fifths
within the date, and each fifth's monthly return over the twelve months from July, the
formations chained, is regressed on the benchmark's, both over the rate, exactly as
python/rule_alpha.py scores the other sorts; the weightings and the rate are its.

Where this departs from the papers: fifths of five hundred names formed once a year where
the first paper forms tenths of the whole market every month; SPY for the market; and the
daily regression is on returns, not returns over the rate, the daily rate being a constant
to the fourth decimal inside a window.

**Descriptive only**, under the rule study's limits (survivors only, an industry-code rule
for a class) and the alpha study's: a hundred and fifty-six months at most. This reads the
market's side only. The rule panel values every name at a beta of one, so nothing here
says what a fair value would have been under another beta. A few rows of the panel carry a
market value far too large (a share count in the wrong unit); the cap at the formation's
eightieth percentile bounds what each can weigh. Nothing here feeds a model, a belief or a
signal."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import cast

import numpy as np

import anchor_study as study
import broad_study as broad
import rule_alpha as alpha
from broad_study import Row

PANEL = alpha.PANEL
PRICES = alpha.PRICES
RATE = alpha.RATE
HISTORIES = study.REPO_ROOT / "data" / "broad" / "rule" / "histories"
OUT = study.REPO_ROOT / "output" / "rule_beta"
BENCHMARK = alpha.BENCHMARK
SPLIT_YEAR = alpha.SPLIT_YEAR
MIN_DAYS = 200               # the first paper's floor on daily observations in the year
LAGS = 5                     # its lagged market terms, for trading that is not synchronous
SHRINK = 0.5                 # its weight on the estimate, the rest on one
MIN_BETA_GAP = 0.05          # fifths this close in realised beta carry no price of beta to read
MEASURE = "beta"
Json = dict[str, object]
Daily = dict[str, float]     # day "YYYY-MM-DD" -> split-adjusted close


def load_daily(path: Path) -> Daily | None:
    if not path.exists():
        return None
    closes = cast(Json, json.loads(path.read_text())).get("closes")
    if not isinstance(closes, dict):
        return None
    return {str(day): float(v) for day, v in cast(dict[str, object], closes).items() if isinstance(v, (int, float)) and v > 0}


def daily_returns(closes: Daily, first: str, last: str) -> dict[str, float]:
    """day -> the return into it, for the days after [first] up to [last], each on the
    trading day before it."""
    days = sorted(closes)
    return {day: closes[day] / closes[before] - 1 for before, day in zip(days, days[1:], strict=False) if first < day <= last}


def beta_of(stock: dict[str, float], market_days: list[str], market: dict[str, float]) -> float | None:
    """The first paper's estimate: the stock's daily return on the market's of the day and of
    each of the LAGS days before, the slopes summed, then SHRINK of it and the rest on one.
    None under MIN_DAYS days carrying all of them."""
    position = {day: i for i, day in enumerate(market_days)}
    ys: list[float] = []
    xs: list[list[float]] = []
    for day, r in stock.items():
        i = position.get(day)
        if i is None or i < LAGS:
            continue
        lagged = [market.get(market_days[i - k]) for k in range(LAGS + 1)]
        if all(v is not None for v in lagged):
            ys.append(r)
            xs.append([1.0, *cast(list[float], lagged)])
    if len(ys) < MIN_DAYS:
        return None
    coefficients = np.linalg.lstsq(np.asarray(xs, dtype=float), np.asarray(ys, dtype=float), rcond=None)[0]
    return SHRINK * float(coefficients[1:].sum()) + (1 - SHRINK)


def load_rows(panel: Path, histories: Path, benchmark: Daily) -> tuple[list[Row], int]:
    """(one row per panel name and June that carries a beta, the count that did not)."""
    market_days = sorted(benchmark)
    market_all = daily_returns(benchmark, "0000", "9999")
    rows: list[Row] = []
    without = 0
    cache: dict[str, Daily | None] = {}
    for line in panel.read_text().splitlines():
        if not line.strip():
            continue
        raw = cast(Json, json.loads(line))
        ticker, day = str(raw["ticker"]), str(raw["date"])
        year = int(day[:4])
        if ticker not in cache:
            cache[ticker] = load_daily(histories / f"{ticker}.json")
        closes = cache[ticker]
        beta = None if closes is None else beta_of(daily_returns(closes, f"{year - 1}{day[4:]}", day), market_days, market_all)
        if beta is None:
            without += 1
            continue
        rows.append(Row(ticker=ticker, year=year, excess=None, non_financial=True, values={MEASURE: beta}, cap=study.as_float(raw.get("market_cap"))))
    return rows, without


def block(rows: list[Row], adjusted: dict[str, dict[str, float]], market: alpha.Series, rate: alpha.Series, label: str, *, capped_value: bool) -> list[str]:
    q = broad.quintiles(rows, MEASURE)
    years = sorted({year for _, year in q})
    weighting = "capped value" if capped_value else "equal"
    title = f"beta, {label}, {weighting} weights: {len(q)} rows over {len(years)} formation years"
    lines = [title, "-" * len(title)]
    if not q:
        return lines + ["  no formation year carries enough rows"]
    months = [m for year in years for m in alpha.months_after(year)]
    fifths = alpha.fifth_returns(rows, q, adjusted, capped_value=capped_value)
    fits: dict[int, alpha.Fit | None] = {}
    for k in range(1, 6):
        formed = [r.values[MEASURE] for r in rows if q.get((r.ticker, r.year)) == k]
        fits[k] = alpha.regress(fifths[k], market, rate, months, over_rate=True)
        lines.append(alpha.line(f"fifth {k} (beta at formation {sum(formed) / len(formed):.2f})", fits[k]))
    spread = {m: fifths[5][m] - fifths[1][m] for m in fifths[5] if m in fifths[1]}
    across = alpha.regress(spread, market, rate, months, over_rate=False)
    lines.append(alpha.line("highest less lowest", across))
    low, high = fits[1], fits[5]
    kept = [m for m in months if m in market and m in rate]
    if low is not None and high is not None and across is not None and high.beta - low.beta > MIN_BETA_GAP and kept:
        premium = sum(market[m] - rate[m] for m in kept) / len(kept)
        earned = (high.mean - low.mean) / (high.beta - low.beta)
        lines.append(f"  earned per unit of realised beta, highest fifth against lowest: {12 * 100 * earned + 0.0:+.1f}% a year; "
                     f"{BENCHMARK} over the rate in the same months: {12 * 100 * premium + 0.0:+.1f}% a year")
        lines.append(f"  were beta not paid at all, the spread's alpha would be its beta times that premium below zero: {round(-100 * across.beta * premium, 2) + 0.0:+.2f}% a month")
    return lines


def report(rows: list[Row], without: int, adjusted: dict[str, dict[str, float]], rate: alpha.Series) -> str:
    market = {m: r for m in adjusted.get(BENCHMARK, {}) if (r := alpha.monthly_return(adjusted[BENCHMARK], m)) is not None}
    years = sorted({r.year for r in rows})
    lines = [
        f"The rule panel sorted on beta: {len(rows)} names and Junes carrying a beta, {years[0]} to {years[-1]}, on {len({r.ticker for r in rows})} filers; {without} left out for fewer than {MIN_DAYS} daily returns in the year.",
        f"Descriptive only, under the rule study's limits. Beta from the year's daily returns on {BENCHMARK} with {LAGS} lagged terms, halved toward one; fifths within the date, fifth 5 the highest beta; "
        f"monthly returns over the twelve months from July regressed on {BENCHMARK} over the one-year Treasury rate. The t-ratio is the plain least-squares one on at most 156 months: a scale, not a test.",
        "After Frazzini and Pedersen, \"Betting Against Beta\", NBER Working Paper 16601, December 2010, doi:10.3386/w16601; "
        "Novy-Marx and Velikov, \"Betting Against Betting Against Beta\", working paper, November 2018, doi:10.2139/ssrn.3300965; "
        "and Levi and Welch, \"Best Practice for Cost-of-Capital Estimates\", Journal of Financial and Quantitative Analysis 52(2), 2017, doi:10.1017/S0022109017000114.",
        "",
    ]

    def every(_: Row) -> bool:
        return True

    def before(r: Row) -> bool:
        return r.year < SPLIT_YEAR

    def since(r: Row) -> bool:
        return r.year >= SPLIT_YEAR

    for label, keep in (("all formations", every), (f"formations before {SPLIT_YEAR}", before), (f"formations from {SPLIT_YEAR}", since)):
        kept = [r for r in rows if keep(r)]
        for capped_value in (False, True):
            lines += block(kept, adjusted, market, rate, label, capped_value=capped_value) + [""]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--panel", type=Path, default=PANEL)
    parser.add_argument("--prices", type=Path, default=PRICES)
    parser.add_argument("--rate", type=Path, default=RATE)
    parser.add_argument("--histories", type=Path, default=HISTORIES)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--fetch-benchmark", action="store_true", help=f"fetch {BENCHMARK}'s daily history into the rule panel's cache if it is not there")
    args = parser.parse_args(argv)
    panel: Path = args.panel
    prices: Path = args.prices
    rate_path: Path = args.rate
    histories: Path = args.histories
    out: Path = args.out
    for path, how in ((panel, "run python/rule_panel.py first"), (rate_path, "run python/rule_panel.py first: it fills the rate cache"),
                      (prices, "run python/broad_panel.py first: it fetches the monthly bars"), (histories, "run python/rule_panel.py first: it keeps the daily histories")):
        if not path.exists():
            print(f"{path} not built: {how}", file=sys.stderr)
            return 2
    if args.fetch_benchmark and not (histories / f"{BENCHMARK}.json").exists():
        import rule_panel  # noqa: PLC0415

        rule_panel.history_of(BENCHMARK)
    benchmark = load_daily(histories / f"{BENCHMARK}.json")
    if benchmark is None:
        print(f"no daily history for {BENCHMARK} under {histories}: run python/rule_beta.py --fetch-benchmark", file=sys.stderr)
        return 2
    adjusted = alpha.load_adjusted(prices)
    if BENCHMARK not in adjusted:
        print(f"no monthly bars for {BENCHMARK} under {prices}: run python/broad_panel.py --retry-missing", file=sys.stderr)
        return 2
    rows, without = load_rows(panel, histories, benchmark)
    text = report(rows, without, adjusted, alpha.load_rate(rate_path))
    out.mkdir(parents=True, exist_ok=True)
    (out / "tables.txt").write_text(text)
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
