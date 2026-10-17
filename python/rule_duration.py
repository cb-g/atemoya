"""Duration on the rule panel: what the model's own timing says, against a published measure.

    uv run python/rule_duration.py [--out output/rule_duration]

A fair value is a sum of discounted cash flows, and its sensitivity to the discount rate is
the weighted average time of those flows, the duration. Dechow, Sloan and Soliman, "Implied
Equity Duration: A New Measure of Equity Risk", working paper, May 2002 (the version read
carries no series number), build one from four filed items and the market value, with one
discount rate for every firm so that the measure carries timing alone: book equity and sales,
each with the year before, earnings, and the market value; the return on equity reverts to
12 per cent with a persistence of 0.57 and sales growth to 6 per cent with 0.24; ten years of
clean-surplus cash flows are discounted at 12 per cent, and the value the price carries
beyond them is taken as a level perpetuity whose duration is 19.33 years. They show
algebraically that the measure is a cousin of the earnings yield and of book to market, and
find Spearman correlations of -0.76 and -0.73 with them (their Table 3); and that it forecasts
the next two years' beta and volatility a little (their Table 5: beta on relative duration,
slope 0.32, R-squared 0.02; with the lagged beta beside it, 0.20 and 0.19). Weber, "Cash Flow
Duration and the Term Structure of Equity Returns", NBER Working Paper 22520, August 2016,
doi:10.3386/w22520, uses the same construction with fifteen years.

What it does. For every generic DCF record in the rule panel, each June 2013 to 2025, three
durations. `dss` is the paper's measure as specified, from the point-in-time record's two
latest fiscal periods and the market value on the date, a name with book equity at or below
zero carrying none, as the paper drops them. `model` is the model's own, price-free: the
Macaulay duration of its enterprise value at its own discount rate, the explicit cash flows
at their years and the terminal value as a growing perpetuity whose duration is the horizon
plus one plus the rate over the rate less the terminal growth, levered onto the model's
equity value with net debt at a duration of nought, so it reads the shape of the projection
and nothing of the price. `implied` is the paper's device on the model's flows: the finite
cash flows weighted by their present value over the enterprise value at the price, the
model's terminal duration carrying the rest, so the price's residual stands in for the
model's terminal value. Then: the measures' medians and quartiles by date; the rank
correlation within each date of each with the earnings yield, the margin of safety and book
to market, the paper's -0.76 the figure to compare; the paper's Table 5 on the panel, the
name's plain beta over the twelve months after the date on its relative duration (its
duration over the date's value-weighted mean) alone and beside the beta of the year before,
and the same for the standard deviation of daily returns, pooled and as the median of the
yearly slopes; and the rate study's measured elasticity of each fair value per point of rate
against the model's modified duration, within each date, which says where the analytic
duration describes the record and where the model's hold of terminal growth to the risk-free
rate breaks the link.

What it is not. No new field: every record already carries the fair value at the discount
rate stepped a point either way in its sensitivity block, and the model duration here is that
step's analytic twin, computed to compare with the published measure, not to replace the
block. The paper's market value is at the fiscal year end and ours is at the June date; its
discount rate is one constant and the rule panel's varies only with the date's rate and each
name's debt weight, beta being one. Nothing here moves a record or a parameter.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import anchor_study as study
import panel_stats as ps
import rule_beta as rb
import rule_betas as rbs
import rule_panel
import rule_rates

OUT = study.REPO_ROOT / "output" / "rule_duration"
MEASURES = ("dss", "model", "implied")
# the paper's forecasting parameters (Table 1, p.30; text p.7)
ROE_PERSISTENCE = 0.57
GROWTH_PERSISTENCE = 0.24
COST_OF_EQUITY = 0.12
LONG_RUN_GROWTH = 0.06
HORIZON = 10
Json = dict[str, object]


@dataclass
class Record:
    ticker: str
    year: int
    market_cap: float
    margin: float | None
    earnings_yield: float | None
    book_to_market: float | None
    dss: float | None
    model: float | None
    implied: float | None
    beta: float | None = None            # the plain slope over the year to the date
    beta_ahead: float | None = None      # and over the year after
    vol: float | None = None             # the standard deviation of daily returns over the year to the date
    vol_ahead: float | None = None
    elasticity: float | None = None      # the rate study's d ln(fair value) / d rate per point
    modified: float | None = None        # the model duration over one plus the discount rate, per point
    relative: dict[str, float] = field(default_factory=lambda: {})

    def measure(self, name: str) -> float | None:
        return cast(float | None, getattr(self, name))


def dss_duration(*, market_cap: float, book: float, book_lagged: float, sales: float, sales_lagged: float, earnings: float) -> float | None:
    """The paper's implied equity duration (eq. 6 with eqs. 7-8): ten years of clean-surplus
    cash flows from a return on equity and a sales growth each reverting to its long-run mean,
    discounted at one rate, and the rest of the market value as a level perpetuity. None where
    book equity, lagged book equity, lagged sales or the market value is at or below zero."""
    if market_cap <= 0 or book <= 0 or book_lagged <= 0 or sales_lagged <= 0:
        return None
    roe, growth, bv = earnings / book_lagged, sales / sales_lagged - 1, book
    pv_sum = weighted = 0.0
    for t in range(1, HORIZON + 1):
        growth = LONG_RUN_GROWTH + GROWTH_PERSISTENCE * (growth - LONG_RUN_GROWTH)
        roe = COST_OF_EQUITY + ROE_PERSISTENCE * (roe - COST_OF_EQUITY)
        earnings_t, bv_next = bv * roe, bv * (1 + growth)
        cash_flow = earnings_t - (bv_next - bv)
        pv = cash_flow / (1 + COST_OF_EQUITY) ** t
        pv_sum += pv
        weighted += t * pv
        bv = bv_next
    terminal_duration = HORIZON + (1 + COST_OF_EQUITY) / COST_OF_EQUITY
    return weighted / market_cap + terminal_duration * (market_cap - pv_sum) / market_cap


def model_flows(fcff: float, wacc: float, growth_path: list[float], terminal_growth: float) -> tuple[list[float], float, float]:
    """The present value of each explicit year's cash flow, the present value of the terminal
    value and the terminal value's duration, as the model builds its enterprise value."""
    pvs: list[float] = []
    cash_flow = fcff
    for i, g in enumerate(growth_path, start=1):
        cash_flow *= 1 + g
        pvs.append(cash_flow / (1 + wacc) ** i)
    years = len(growth_path)
    terminal = cash_flow * (1 + terminal_growth) / (wacc - terminal_growth) / (1 + wacc) ** years
    return pvs, terminal, years + (1 + wacc) / (wacc - terminal_growth)


def model_duration(*, fcff: float, wacc: float, growth_path: list[float], terminal_growth: float, net_debt: float) -> float | None:
    """The Macaulay duration of the model's enterprise value, levered onto its equity value with net
    debt at a duration of nought; None where the discount rate is not above the terminal growth or
    the equity value is not positive."""
    if wacc <= terminal_growth or not growth_path:
        return None
    pvs, terminal_pv, terminal_duration = model_flows(fcff, wacc, growth_path, terminal_growth)
    enterprise = sum(pvs) + terminal_pv
    equity = enterprise - net_debt
    if enterprise <= 0 or equity <= 0:
        return None
    weighted = sum(i * pv for i, pv in enumerate(pvs, start=1)) + terminal_duration * terminal_pv
    return weighted / equity


def implied_duration(*, fcff: float, wacc: float, growth_path: list[float], terminal_growth: float, net_debt: float, market_cap: float) -> float | None:
    """The paper's device on the model's flows: the explicit present values weighted over the
    enterprise value at the price, the model's terminal duration on the rest."""
    if wacc <= terminal_growth or not growth_path:
        return None
    pvs, _terminal_pv, terminal_duration = model_flows(fcff, wacc, growth_path, terminal_growth)
    at_price = market_cap + net_debt
    if at_price <= 0:
        return None
    weighted = sum(i * pv for i, pv in enumerate(pvs, start=1))
    return (weighted + terminal_duration * (at_price - sum(pvs))) / at_price


def pit_items(pit: Path, d: str, ticker: str) -> tuple[float, float, float, float, float] | None:
    """Book equity, lagged book equity, sales, lagged sales and earnings from the point-in-time
    record's two latest fiscal periods; None where either period lacks one."""
    path = pit / d / f"{ticker}.json"
    if not path.exists():
        return None
    periods = cast(list[Json], cast(Json, json.loads(path.read_text())).get("periods", []))
    if len(periods) < 2:
        return None
    now, before = periods[0], periods[1]
    values = [study.as_float(now.get("book_equity")), study.as_float(before.get("book_equity")), study.as_float(now.get("total_revenue")),
              study.as_float(before.get("total_revenue")), study.as_float(now.get("net_income"))]
    if any(v is None for v in values):
        return None
    return cast(tuple[float, float, float, float, float], tuple(values))


def load_records(panel_out: Path, pit: Path, panel: Path) -> list[Record]:
    rows = {(str(r["ticker"]), str(r["date"])[:4]): r for r in (cast(Json, json.loads(line)) for line in panel.read_text().splitlines())}
    out: list[Record] = []
    for day_dir in sorted(panel_out.iterdir()):
        path = day_dir / "valuations.jsonl"
        if not path.exists():
            continue
        d, year = day_dir.name, int(day_dir.name[:4])
        for line in path.read_text().splitlines():
            rec = cast(Json, json.loads(line))
            inputs = rec.get("inputs")
            if not (isinstance(inputs, list) and inputs and inputs[0] == "dcf" and rec.get("status") == "Ok"):
                continue
            x = cast(Json, inputs[1])
            ticker = str(rec["ticker"])
            market_cap, fcff, wacc, net_debt = (float(cast(float, x[k])) for k in ("market_cap", "fcff", "wacc", "net_debt"))
            growth_path = [float(g) for g in cast(list[float], x["growth_path"])]
            terminal = float(cast(float, cast(Json, x["terminal_growth_rate"])["value"]))
            items = pit_items(pit, d, ticker)
            dss = dss_duration(market_cap=market_cap, book=items[0], book_lagged=items[1], sales=items[2], sales_lagged=items[3], earnings=items[4]) if items else None
            row = rows.get((ticker, d[:4]), {})
            out.append(Record(ticker=ticker, year=year, market_cap=market_cap, margin=study.as_float(row.get("margin_of_safety")),
                              earnings_yield=study.as_float(row.get("earnings_yield")),
                              book_to_market=items[0] / market_cap if items and market_cap > 0 else None, dss=dss,
                              model=model_duration(fcff=fcff, wacc=wacc, growth_path=growth_path, terminal_growth=terminal, net_debt=net_debt),
                              implied=implied_duration(fcff=fcff, wacc=wacc, growth_path=growth_path, terminal_growth=terminal, net_debt=net_debt, market_cap=market_cap),
                              modified=None))
            if out[-1].model is not None:
                out[-1].modified = out[-1].model / (1 + wacc) / 100
    return out


def attach_betas(records: list[Record], betas_path: Path) -> None:
    by_key: dict[tuple[str, int], Json] = {}
    for line in betas_path.read_text().splitlines():
        b = cast(Json, json.loads(line))
        by_key[(str(b["ticker"]), int(cast(int, b["year"])))] = b
    for r in records:
        b = by_key.get((r.ticker, r.year))
        if b is None:
            continue
        r.beta = study.as_float(b.get("ols"))
        r.beta_ahead = study.as_float(cast(Json, b.get("ahead", {})).get("1"))


def volatility(closes: ps.Daily, first: str, last: str) -> float | None:
    returns = list(ps.daily_returns(closes, first, last).values())
    return statistics.pstdev(returns) if len(returns) >= rbs.MIN_DAYS else None


def attach_volatility(records: list[Record], histories: Path) -> None:
    cache: dict[str, ps.Daily | None] = {}
    for r in records:
        if r.ticker not in cache:
            cache[r.ticker] = ps.load_daily(histories / f"{r.ticker}.json")
        closes = cache[r.ticker]
        if closes is None:
            continue
        day = f"{r.year}-06-30"
        r.vol = volatility(closes, *ps.window(r.year, day, 0))
        r.vol_ahead = volatility(closes, *ps.window(r.year, day, 1))


def attach_elasticities(records: list[Record], rates_out: Path, shift: float) -> None:
    """Each record's d ln(fair value) / d rate per point from the rate study's two shifted runs."""
    for year in sorted({r.year for r in records}):
        d = f"{year}-06-30"
        up, down = (rates_out / side / d / "valuations.jsonl" for side in ("up", "down"))
        if not up.exists() or not down.exists():
            continue
        by_up = {str(x["ticker"]): x for x in (cast(Json, json.loads(line)) for line in up.read_text().splitlines())}
        by_down = {str(x["ticker"]): x for x in (cast(Json, json.loads(line)) for line in down.read_text().splitlines())}
        for r in records:
            if r.year != year or r.ticker not in by_up or r.ticker not in by_down:
                continue
            a, b = study.as_float(by_down[r.ticker].get("fair_value")), study.as_float(by_up[r.ticker].get("fair_value"))
            if a is not None and b is not None and a > 0 and b > 0:
                r.elasticity = (math.log(b) - math.log(a)) / (2 * shift) / 100


def attach_relative(records: list[Record]) -> None:
    """Each measure over the date's value-weighted mean, the paper's relative duration."""
    for year in {r.year for r in records}:
        rows = [r for r in records if r.year == year]
        for name in MEASURES:
            pairs = [(cast(float, r.measure(name)), r.market_cap) for r in rows if r.measure(name) is not None and r.market_cap > 0]
            if not pairs:
                continue
            mean = sum(v * w for v, w in pairs) / sum(w for _, w in pairs)
            if mean == 0:
                continue
            for r in rows:
                v = r.measure(name)
                if v is not None:
                    r.relative[name] = v / mean


def quartiles(values: list[float]) -> str:
    if len(values) < study.MIN_CELL:
        return f"n={len(values)}"
    median, q1, q3 = study.quantiles(values)
    return f"median {median:6.1f}, quartiles {q1:6.1f} to {q3:6.1f}, n={len(values)}"


def levels_block(records: list[Record]) -> list[str]:
    lines = ["the three durations in years, by date", "-" * 110, f"  {'date':<6} " + "   ".join(f"{m:<44}" for m in MEASURES)]
    for year in sorted({r.year for r in records}):
        rows = [r for r in records if r.year == year]
        lines.append(f"  {year:<6} " + "   ".join(f"{quartiles([cast(float, r.measure(m)) for r in rows if r.measure(m) is not None]):<44}" for m in MEASURES))
    lines.append(f"  {'pooled':<6} " + "   ".join(f"{quartiles([cast(float, r.measure(m)) for r in records if r.measure(m) is not None]):<44}" for m in MEASURES))
    lines.append("  the paper's: mean 15.1, quartiles 13.3 to 17.4 on all US stocks 1963-1998 (Table 3); its terminal duration is 19.33 years for every firm, "
                 "the model's is the horizon plus one plus the rate over the rate less terminal growth, which the panel's rates put far higher")
    return lines


def within_date_correlation(records: list[Record], a: str, b: str) -> tuple[float | None, int, float | None]:
    """The median over dates of the within-date rank correlation of two record fields, the count of
    dates with one, and the pooled rank correlation."""
    per_date: list[float] = []
    pooled: list[tuple[float, float]] = []
    for year in sorted({r.year for r in records}):
        pairs = [(cast(float, getattr(r, a)), cast(float, getattr(r, b))) for r in records if r.year == year and getattr(r, a) is not None and getattr(r, b) is not None]
        rho = ps.spearman(pairs)
        if rho is not None:
            per_date.append(rho)
        pooled += pairs
    return (statistics.median(per_date) if per_date else None), len(per_date), ps.spearman(pooled)


def correlations_block(records: list[Record]) -> list[str]:
    lines = ["rank correlations within the date (median over dates; pooled in brackets)", "-" * 110,
             f"  {'':<10}" + "".join(f"{b:>18}" for b in ("earnings_yield", "margin", "book_to_market", "dss", "model"))]
    for a in MEASURES:
        cells: list[str] = []
        for b in ("earnings_yield", "margin", "book_to_market", "dss", "model"):
            if a == b:
                cells.append(f"{'-':>18}")
                continue
            med, n, pooled = within_date_correlation(records, a, b)
            cells.append(f"{'n/a':>18}" if med is None or pooled is None else f"{med:+.2f} ({pooled:+.2f}) {n:>2}".rjust(18))
        lines.append(f"  {a:<10}" + "".join(cells))
    lines.append("  the paper's, Spearman, pooled: duration with earnings to price -0.76, with book to market -0.73; earnings to price with book to market 0.58 (Table 3)")
    return lines


def table5_block(records: list[Record]) -> list[str]:
    """The paper's Table 5 on the panel: next year's beta on relative duration, alone and beside this
    year's beta; the same for the standard deviation of daily returns."""
    lines = ["the paper's Table 5: next year's beta and volatility on relative duration, alone (model 1) and beside this year's (model 2)", "-" * 110]
    for outcome, now, label in (("beta_ahead", "beta", "beta"), ("vol_ahead", "vol", "daily standard deviation")):
        for name in MEASURES:
            rows = [r for r in records if name in r.relative and getattr(r, outcome) is not None and getattr(r, now) is not None]
            pooled1 = ps.fit([[r.relative[name]] for r in rows], [cast(float, getattr(r, outcome)) for r in rows])
            pooled2 = ps.fit([[r.relative[name], cast(float, getattr(r, now))] for r in rows], [cast(float, getattr(r, outcome)) for r in rows])
            yearly: list[float] = []
            for year in sorted({r.year for r in rows}):
                sub = [r for r in rows if r.year == year]
                f = ps.fit([[r.relative[name], cast(float, getattr(r, now))] for r in sub], [cast(float, getattr(r, outcome)) for r in sub])
                if f is not None:
                    yearly.append(f[0][0])
            if pooled1 is None or pooled2 is None:
                lines.append(f"  {label}, {name}: fewer than {ps.MIN_PAIRS} rows")
                continue
            sd_x = statistics.pstdev([r.relative[name] for r in rows])
            sd_y = statistics.pstdev([cast(float, getattr(r, outcome)) for r in rows])
            standardised = pooled2[0][0] * sd_x / sd_y if sd_y > 0 else 0.0
            positive = sum(1 for s in yearly if s > 0)
            lines.append(f"  {label:<24} {name:<8} {len(rows):>5} rows   model 1: slope {pooled1[0][0]:+.4g}, adj. R2 {100 * pooled1[1] + 0.0:5.1f}%   "
                         f"model 2: slope {pooled2[0][0]:+.4g} ({standardised:+.3f} s.d. per s.d.), on this year's {pooled2[0][1]:+.3f}, adj. R2 {100 * pooled2[1] + 0.0:5.1f}%"
                         + (f"   yearly model-2 slopes positive {positive}/{len(yearly)}" if yearly else ""))
    lines.append("  the paper's, pooled 1963-1998, all stocks: beta on relative duration 0.318 (adj. R2 0.02), beside the lagged beta 0.197 and 0.39 (0.19); "
                 "volatility on duration 0.002 (0.04), beside lagged volatility 0.001 and 0.662 (0.46) (Table 5)")
    return lines


def elasticity_block(records: list[Record]) -> list[str]:
    """The rate study's measured fall in each fair value per point of risk-free rate against the
    model's modified duration per point of discount rate, within the date."""
    lines = ["the measured fall in a fair value per point of risk-free rate (the rate study's shifted runs) against the model's modified duration per point of discount rate, by date",
             "-" * 110,
             f"  {'date':<6} {'rows':>5}   {'median measured':>16}   {'median modified duration':>24}   {'ratio':>6}   {'rank correlation':>16}"]
    for year in sorted({r.year for r in records}):
        rows = [r for r in records if r.year == year and r.elasticity is not None and r.modified is not None]
        if len(rows) < study.MIN_CELL:
            lines.append(f"  {year:<6} {len(rows):>5}   no shifted runs for the date" if not rows else f"  {year:<6} {len(rows):>5}   fewer than {study.MIN_CELL} rows")
            continue
        measured = statistics.median([-cast(float, r.elasticity) for r in rows])
        analytic = statistics.median([cast(float, r.modified) for r in rows])
        rho = ps.spearman([(cast(float, r.modified), -cast(float, r.elasticity)) for r in rows])
        lines.append(f"  {year:<6} {len(rows):>5}   {100 * measured:>+15.1f}%   {100 * analytic:>+23.1f}%   {measured / analytic:>6.2f}   {('n/a' if rho is None else f'{rho:+.2f}'):>16}")
    lines.append("  below the kink the model holds terminal growth to the risk-free rate, so a rate move changes the discount rate and the terminal growth together and the "
                 "fair value barely moves; above it the discount rate moves alone and the measured fall is the analytic duration times the share of a risk-free move that "
                 "reaches the weighted cost of capital through the equity and after-tax debt weights")
    return lines


def report(records: list[Record]) -> str:
    counts = ", ".join(f"{m} {sum(1 for r in records if r.measure(m) is not None)}" for m in MEASURES)
    lines = [f"duration on the rule panel: {len(records)} generic DCF records on {len({r.ticker for r in records})} names, "
             f"{min(r.year for r in records)} to {max(r.year for r in records)}; with a figure: {counts}", ""]
    lines += levels_block(records) + [""] + correlations_block(records) + [""] + table5_block(records) + [""] + elasticity_block(records)
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--panel-out", type=Path, default=rule_panel.OUT)
    parser.add_argument("--pit", type=Path, default=rule_panel.ROOT / "pit")
    parser.add_argument("--panel", type=Path, default=rb.PANEL)
    parser.add_argument("--betas", type=Path, default=rbs.OUT / "betas.jsonl")
    parser.add_argument("--histories", type=Path, default=rb.HISTORIES)
    parser.add_argument("--rates-out", type=Path, default=rule_rates.OUT)
    parser.add_argument("--shift", type=float, default=rule_rates.SHIFT)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    if not args.panel_out.is_dir() or not any(args.panel_out.glob("*/valuations.jsonl")):
        print(f"no rule panel records under {args.panel_out}: run `uv run python/rule_panel.py` first", file=sys.stderr)
        return 2
    if not args.panel.exists():
        print(f"no rule panel at {args.panel}: run `uv run python/rule_panel.py` first", file=sys.stderr)
        return 2
    if not args.betas.exists():
        print(f"no betas at {args.betas}: run `uv run python/rule_betas.py --forecast-only` first", file=sys.stderr)
        return 2
    records = load_records(args.panel_out, args.pit, args.panel)
    if not records:
        print("no generic DCF record in the rule panel", file=sys.stderr)
        return 2
    attach_betas(records, args.betas)
    attach_volatility(records, args.histories)
    attach_elasticities(records, args.rates_out, args.shift)
    attach_relative(records)
    args.out.mkdir(parents=True, exist_ok=True)
    text = report(records)
    (args.out / "tables.txt").write_text(text)
    with (args.out / "durations.jsonl").open("w") as fh:
        for r in records:
            fh.write(json.dumps({"ticker": r.ticker, "year": r.year, "dss": r.dss, "model": r.model, "implied": r.implied, "modified": r.modified,
                                 "elasticity": r.elasticity, "beta": r.beta, "beta_ahead": r.beta_ahead, "vol": r.vol, "vol_ahead": r.vol_ahead}) + "\n")
    print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
