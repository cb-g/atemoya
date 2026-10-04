"""The broad study: did cheapness, quality and a peer-implied value sort returns before 2022?

    uv run python/broad_study.py [--panel data/broad/panel.jsonl] [--out output/broad_study]

The anchor study and the naive baseline read eighteen quarter-ends in one market, in which
every fundamentals-based sort failed the same way. That cannot tell a measure that never
worked from one that did not work lately. This reads the broad panel (python/broad_panel.py:
every SEC filer with a ticker today, formed each June from the fiscal year before, with the
next twelve months' return) and asks the same question of each measure in two stretches:
the formations before SPLIT_YEAR and those from it, which are the anchor study's years.

Measures, each from filed items and the market value on the day, no model of ours:

- `earnings_yield`: net income over market value; `book_to_price`: stockholders' equity
  over market value, null when equity is not positive.
- `gross_profitability`: gross profit (as filed, else revenue less cost of revenue) over
  total assets. `accruals_ratio`: net income less operating cash flow over average total
  assets; low is cash ahead of earnings.
- `f_score`: Piotroski's nine signals on the year against the year before, as
  ocaml/lib/quality.ml forms them, with long-term debt for leverage; null unless all nine
  are available.
- `peer_gap`: the peer-implied value over the market value, less one (after Bartram and
  Grinblatt, "Agnostic fundamental analysis works", 2018). Each June, market value per
  dollar of assets is regressed across the companies on equity, revenue, net income and
  operating cash flow per dollar of assets and on the reciprocal of assets, every column
  winsorised at its 1st and 99th percentile; the fitted value is what the market pays that
  year for those accounts on other companies. No return enters the fit. A non-positive
  fitted value gives no gap.

Tables. For each measure and stretch: quintiles cut within the formation year (5 the
highest value of the measure), the median excess over SPY at twelve months and the share
positive; the top quintile's median less the bottom's, pooled and year by year, with the
count of years it was positive. Then cheapness against the score in four cells, and the
score taken apart: by its value, each of the nine signals alone, and within thirds of
market value. The main
tables are on filers that report current assets, which leaves out banks and insurers, as
the literature does; the count left out is stated.

**Descriptive only, and survivors only.** A filer is in the panel only if it has a ticker
today, so the failures and the acquired are missing, more of them the further back; a sort
that would have held the companies that later failed looks better here than it was. Years
are sixteen at most and overlap nothing, but sixteen is still sixteen. The held-out names
in reference/holdout.json are left out. Nothing here feeds a model, a belief or a signal."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import numpy as np

import anchor_study as study

PANEL = study.REPO_ROOT / "data" / "broad" / "panel.jsonl"
OUT = study.REPO_ROOT / "output" / "broad_study"
SPLIT_YEAR = 2022            # formations from this June on are the anchor study's years
MIN_CELL = study.MIN_CELL
MIN_YEAR = 50                # a formation year with fewer rows carrying a measure cuts no quintiles
HIGH_QUALITY = 6
MEASURES = ("earnings_yield", "book_to_price", "gross_profitability", "accruals_ratio", "f_score", "peer_gap")
REGRESSORS = ("book_equity", "revenue", "net_income", "operating_cash_flow")
Json = dict[str, object]


SIGNALS = ("return_on_assets_positive", "operating_cash_flow_positive", "return_on_assets_higher", "cash_flow_above_net_income", "leverage_lower",
           "current_ratio_higher", "no_more_shares", "gross_margin_higher", "asset_turnover_higher")


@dataclass
class Row:
    ticker: str
    year: int
    excess: float | None
    non_financial: bool
    values: dict[str, float]
    signals: dict[str, bool] = field(default_factory=lambda: {})   # each of the nine that could be formed
    cap: float | None = None


def num(d: Json, key: str) -> float | None:
    return study.as_float(d.get(key))


def ratio(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None or b == 0 else a / b


def gross_profit(d: Json) -> float | None:
    filed = num(d, "gross_profit")
    if filed is not None:
        return filed
    revenue, cost = num(d, "revenue"), num(d, "cost_of_revenue")
    return None if revenue is None or cost is None else revenue - cost


def signals_of(now: Json, prior: Json) -> dict[str, bool]:
    """Piotroski's nine on the two years, each one that can be formed, by name."""
    def roa(d: Json) -> float | None:
        return ratio(num(d, "net_income"), num(d, "total_assets"))

    def leverage(d: Json) -> float | None:
        return ratio(num(d, "long_term_debt"), num(d, "total_assets"))

    def current(d: Json) -> float | None:
        return ratio(num(d, "current_assets"), num(d, "current_liabilities"))

    def margin(d: Json) -> float | None:
        return ratio(gross_profit(d), num(d, "revenue"))

    def turnover(d: Json) -> float | None:
        return ratio(num(d, "revenue"), num(d, "total_assets"))

    def higher(a: float | None, b: float | None) -> bool | None:
        return None if a is None or b is None else a > b

    cfo, income = num(now, "operating_cash_flow"), num(now, "net_income")
    shares, shares_before = num(now, "weighted_shares"), num(prior, "weighted_shares")
    lev, lev_before = leverage(now), leverage(prior)
    signals: list[bool | None] = [
        None if roa(now) is None else cast(float, roa(now)) > 0,
        None if cfo is None else cfo > 0,
        higher(roa(now), roa(prior)),
        None if cfo is None or income is None else cfo > income,
        None if lev is None or lev_before is None else (lev < lev_before or (lev == 0 and lev_before == 0)),
        higher(current(now), current(prior)),
        None if shares is None or shares_before is None or shares_before <= 0 or shares / shares_before > 1.25 else shares <= shares_before,
        higher(margin(now), margin(prior)),
        higher(turnover(now), turnover(prior)),
    ]
    return {name: s for name, s in zip(SIGNALS, signals) if s is not None}


def f_score(now: Json, prior: Json) -> int | None:
    """The count passed; None unless every one of the nine can be formed."""
    signals = signals_of(now, prior)
    return sum(1 for v in signals.values() if v) if len(signals) == len(SIGNALS) else None


def measures_of(raw: Json) -> dict[str, float]:
    out: dict[str, float] = {}
    cap, income, equity, assets = num(raw, "market_cap"), num(raw, "net_income"), num(raw, "book_equity"), num(raw, "total_assets")
    if cap is not None and cap > 0:
        if income is not None:
            out["earnings_yield"] = income / cap
        if equity is not None and equity > 0:
            out["book_to_price"] = equity / cap
    gp = ratio(gross_profit(raw), assets)
    if gp is not None:
        out["gross_profitability"] = gp
    prior = raw.get("prior")
    if isinstance(prior, dict):
        p = cast(Json, prior)
        before, cfo = num(p, "total_assets"), num(raw, "operating_cash_flow")
        if assets is not None and before is not None and income is not None and cfo is not None and assets + before > 0:
            out["accruals_ratio"] = (income - cfo) / ((assets + before) / 2)
        score = f_score(raw, p)
        if score is not None:
            out["f_score"] = float(score)
    return out


def winsorise(column: np.ndarray, lower: float = 1.0, upper: float = 99.0) -> np.ndarray:
    lo, hi = np.percentile(column, [lower, upper])
    return np.clip(column, lo, hi)


def peer_gaps(raws: list[Json]) -> dict[int, float]:
    """index in [raws] -> fitted market value over the market value, less one, from one
    year's cross-section; rows lacking an item are left out of the fit and get no gap."""
    usable: list[tuple[int, float, float, list[float]]] = []
    for i, raw in enumerate(raws):
        cap, assets = num(raw, "market_cap"), num(raw, "total_assets")
        items = [num(raw, k) for k in REGRESSORS]
        if cap is None or cap <= 0 or assets is None or assets <= 0 or any(x is None for x in items):
            continue
        usable.append((i, cap, assets, [cast(float, x) / assets for x in items] + [1.0 / assets]))
    if len(usable) < MIN_YEAR:
        return {}
    y = winsorise(np.array([cap / assets for _, cap, assets, _ in usable]))
    x = np.column_stack([np.ones(len(usable))] + [winsorise(np.array([row[3][j] for row in usable])) for j in range(len(REGRESSORS) + 1)])
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    fitted = x @ beta
    out: dict[int, float] = {}
    for (i, cap, assets, _), value in zip(usable, fitted):
        if value > 0:
            out[i] = float(value) * assets / cap - 1
    return out


def load(path: Path, held_out: frozenset[str]) -> list[Row]:
    by_year: dict[int, list[Json]] = {}
    for line in path.read_text().splitlines():
        if line.strip():
            raw = cast(Json, json.loads(line))
            if str(raw["ticker"]) not in held_out:
                by_year.setdefault(int(str(raw["formation"])[:4]), []).append(raw)
    rows: list[Row] = []
    for year in sorted(by_year):
        raws = by_year[year]
        gaps = peer_gaps(raws)
        for i, raw in enumerate(raws):
            values = measures_of(raw)
            if i in gaps:
                values["peer_gap"] = gaps[i]
            forward, spy = num(raw, "forward_12m"), num(raw, "spy_12m")
            prior = raw.get("prior")
            rows.append(Row(ticker=str(raw["ticker"]), year=year, excess=None if forward is None or spy is None else forward - spy,
                            non_financial=num(raw, "current_assets") is not None, values=values,
                            signals=signals_of(raw, cast(Json, prior)) if isinstance(prior, dict) else {}, cap=num(raw, "market_cap")))
    return rows


def quintiles(rows: list[Row], measure: str) -> dict[tuple[str, int], int]:
    """1 the lowest value of the measure, 5 the highest, cut within each formation year."""
    out: dict[tuple[str, int], int] = {}
    for year in {r.year for r in rows}:
        have = sorted((r for r in rows if r.year == year and measure in r.values), key=lambda r: (r.values[measure], r.ticker))
        if len(have) < MIN_YEAR:
            continue
        for k, r in enumerate(have):
            out[(r.ticker, r.year)] = min(5, 1 + (k * 5) // len(have))
    return out


def cell(rows: list[Row]) -> tuple[int, float | None, int]:
    values = [r.excess for r in rows if r.excess is not None]
    return len(values), (statistics.median(values) if len(values) >= MIN_CELL else None), sum(1 for x in values if x > 0)


def measure_block(rows: list[Row], measure: str, label: str) -> list[str]:
    q = quintiles(rows, measure)
    ranked = [r for r in rows if (r.ticker, r.year) in q]
    years = sorted({r.year for r in ranked})
    title = f"{measure}, {label}: {len(ranked)} rows over {len(years)} formation years"
    lines = [title, "-" * len(title)]
    if not ranked:
        return lines + ["  no formation year carries enough rows"]
    medians: dict[int, float | None] = {}
    for k in range(1, 6):
        n, med, positive = cell([r for r in ranked if q[(r.ticker, r.year)] == k])
        medians[k] = med
        lines.append(f"  quintile {k}: n={n}" + ("" if med is None else f" median excess {med:+.3f}, positive {positive}/{n}"))
    top, bottom = medians[5], medians[1]
    lines.append("  highest less lowest, pooled: " + ("n under the small-cell floor" if top is None or bottom is None else f"{top - bottom:+.3f}"))
    yearly: list[tuple[int, float]] = []
    for year in years:
        hi = cell([r for r in ranked if r.year == year and q[(r.ticker, r.year)] == 5])[1]
        lo = cell([r for r in ranked if r.year == year and q[(r.ticker, r.year)] == 1])[1]
        if hi is not None and lo is not None:
            yearly.append((year, hi - lo))
    if yearly:
        lines.append(f"  by year: positive in {sum(1 for _, s in yearly if s > 0)} of {len(yearly)}; median of the yearly figures {statistics.median(s for _, s in yearly):+.3f}")
        lines.append("    " + ", ".join(f"{year} {s:+.2f}" for year, s in yearly))
    return lines


def interaction(rows: list[Row], label: str) -> list[str]:
    both = [r for r in rows if "earnings_yield" in r.values and "f_score" in r.values]
    title = f"cheapness against the score, {label}: {len(both)} rows carry both (cheap is above the year's median earnings yield, high is a score of {HIGH_QUALITY} or more)"
    lines = [title, "-" * len(title)]
    medians = {year: statistics.median(r.values["earnings_yield"] for r in both if r.year == year) for year in {r.year for r in both}}
    for name, cheap, high in (("cheap, high score", True, True), ("cheap, low score", True, False), ("dear, high score", False, True), ("dear, low score", False, False)):
        n, med, positive = cell([r for r in both if (r.values["earnings_yield"] > medians[r.year]) == cheap and (r.values["f_score"] >= HIGH_QUALITY) == high])
        lines.append(f"  {name}: n={n}" + ("" if med is None else f" median excess {med:+.3f}, positive {positive}/{n}"))
    return lines


def line_of(name: str, rows: list[Row]) -> str:
    n, med, positive = cell(rows)
    return f"  {name}: n={n}" + ("" if med is None else f" median excess {med:+.3f}, positive {positive}/{n}")


def yearly_difference(high: list[Row], low: list[Row]) -> str:
    """The median of one group less the other's, year by year, and how often it was positive."""
    figures: list[tuple[int, float]] = []
    for year in sorted({r.year for r in high} | {r.year for r in low}):
        a, b = cell([r for r in high if r.year == year])[1], cell([r for r in low if r.year == year])[1]
        if a is not None and b is not None:
            figures.append((year, a - b))
    if not figures:
        return "no year carries both groups"
    return f"positive in {sum(1 for _, x in figures if x > 0)} of {len(figures)} years, median of the yearly figures {statistics.median(x for _, x in figures):+.3f}"


def quality_detail(rows: list[Row], label: str) -> list[str]:
    """The score taken apart: by its value, each signal alone, and within thirds of market
    value cut within the year, so a reader sees what carries it and where."""
    scored = [r for r in rows if "f_score" in r.values]
    title = f"the score in detail, {label}: {len(scored)} rows carry all nine"
    lines = [title, "-" * len(title), "by score:"]
    for value in range(10):
        lines.append(line_of(f"  {value}", [r for r in scored if r.values["f_score"] == value]))
    high, low = [r for r in scored if r.values["f_score"] >= 7], [r for r in scored if r.values["f_score"] <= 3]
    lines.append(f"  seven or more less three or fewer: {yearly_difference(high, low)}")
    lines.append("each signal alone, on every row where it can be formed: passed, failed, and passed less failed year by year")
    for name in SIGNALS:
        passed, failed = [r for r in rows if r.signals.get(name) is True], [r for r in rows if r.signals.get(name) is False]
        (n1, m1, _), (n0, m0, _) = cell(passed), cell(failed)
        figures = "" if m1 is None or m0 is None else f" passed {m1:+.3f} (n={n1}), failed {m0:+.3f} (n={n0});"
        lines.append(f"  {name}:{figures} {yearly_difference(passed, failed)}")
    lines.append("within thirds of market value, cut within the year (1 the smallest): seven or more less three or fewer")
    thirds: dict[tuple[str, int], int] = {}
    for year in {r.year for r in scored}:
        sized = sorted((r for r in scored if r.year == year and r.cap is not None), key=lambda r: (cast(float, r.cap), r.ticker))
        for k, r in enumerate(sized):
            thirds[(r.ticker, r.year)] = min(3, 1 + (k * 3) // len(sized))
    for third in (1, 2, 3):
        inside = [r for r in scored if thirds.get((r.ticker, r.year)) == third]
        a, b = cell([r for r in inside if r.values["f_score"] >= 7]), cell([r for r in inside if r.values["f_score"] <= 3])
        spread = "n under the small-cell floor" if a[1] is None or b[1] is None else f"{a[1] - b[1]:+.3f}"
        lines.append(f"  third {third}: {spread} (n={a[0]} and {b[0]}); "
                     + yearly_difference([r for r in inside if r.values["f_score"] >= 7], [r for r in inside if r.values["f_score"] <= 3]))
    return lines


def report(rows: list[Row], held_out: int) -> str:
    years = sorted({r.year for r in rows})
    with_return = [r for r in rows if r.excess is not None]
    main = [r for r in with_return if r.non_financial]
    lines = [
        f"The broad study: {len(rows)} rows on {len({r.ticker for r in rows})} filers, formed each June {years[0]} to {years[-1]}; {len(with_return)} carry a twelve-month return.",
        "Descriptive only and survivors only: a filer is here only if it has a ticker today, so the failed and the acquired are missing, more of them the further back. Excess is over SPY across the same twelve months. No statistic is claimed.",
        f"Main tables: the {len(main)} rows of filers reporting current assets (banks and insurers report none); {len(with_return) - len(main)} rows left out. {held_out} held-out names left out of everything.",
        "",
    ]
    stretches = ((f"formations before {SPLIT_YEAR}", [r for r in main if r.year < SPLIT_YEAR]),
                 (f"formations from {SPLIT_YEAR}", [r for r in main if r.year >= SPLIT_YEAR]))
    for measure in MEASURES:
        for label, subset in stretches:
            lines += measure_block(subset, measure, label) + [""]
    for label, subset in stretches:
        lines += interaction(subset, label) + [""]
    for label, subset in stretches:
        lines += quality_detail(subset, label) + [""]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--panel", type=Path, default=PANEL)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    panel: Path = args.panel
    out: Path = args.out
    if not panel.exists():
        print(f"{panel} not built: run python/broad_panel.py first", file=sys.stderr)
        return 2
    holdout = study.load_holdout()
    text = report(load(panel, holdout.names), len(holdout.names))
    out.mkdir(parents=True, exist_ok=True)
    (out / "tables.txt").write_text(text)
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
