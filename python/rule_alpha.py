"""The rule study scored on market-adjusted returns: the same sorts, read as alpha.

    uv run python/rule_alpha.py [--panel data/broad/rule/panel.jsonl] [--out output/rule_alpha]

The rule study (python/rule_study.py) sets each fifth's twelve-month return beside SPY's.
That takes out the market's level and nothing else: a fifth that holds the riskier names
is credited with the market's rise as if it had earned it. Two papers read for this tool
find the published sorts mostly where the market's part has been taken out by regression
and far less in the raw returns:

- Jensen, Kelly and Pedersen, "Is There a Replication Crisis in Finance?", NBER Working
  Paper 28432, February 2021, doi:10.3386/w28432. Each factor's alpha is the
  intercept of its monthly return on a constant and the market's excess return, and of
  their US factors 84.9 per cent replicate on that alpha against 56.9 on raw returns
  ("Alpha, Not Raw Return", page 4).
- Gormsen and Lazarus, "Duration-Driven Returns", working paper, April 2019,
  doi:10.2139/ssrn.3359027. Their sort's spread is insignificant raw and significant as
  alpha, the market betas of its tenths running from 0.72 to 1.61 (Table 3).

So this module scores the rule panel's sorts the way those papers do, **beside** the rule
study's tables and never in place of them. A raw return is what a holder earned; an alpha
that appears only after the adjustment is a finding about risk, not a better record.

Method, as the first paper states it and where this differs:

- each June the valued rows carrying a measure are cut into fifths within the date, the
  rule study's cut (the paper cuts thirds; fifths keep these tables beside the others);
- a fifth's monthly return over the twelve months from July is the mean of its names'
  dividend-adjusted monthly returns (`equal`), and again weighted by market value capped
  at the formation's eightieth percentile and carried forward with each name's own return
  (`capped value`; the paper caps at the New York Stock Exchange's eightieth percentile,
  which this panel does not hold, so the cap is the panel's own);
- the years are chained into one monthly series, formation by formation;
- the regression is `r - rf = alpha + beta (SPY - rf)` by least squares, the spread of the
  highest fifth over the lowest regressed without a rate; the t-ratio is the plain
  least-squares one, as in the paper.

The rate is the one-year Treasury yield of the month before, a twelfth of it, from the rule
panel's own cache: the paper uses the Treasury bill, which that cache does not hold, and on
a monthly return the difference is small beside the returns themselves.

**Descriptive only**, under every limit of the rule study, and one more: at most a hundred
and fifty-six months, forty-eight of them from 2022, against the papers' six hundred and
more. The t-ratio is a scale to read the alpha by, not a test. Nothing here feeds a model,
a belief or a signal."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import numpy as np

import anchor_study as study
import broad_study as broad
from broad_study import Row

PANEL = study.REPO_ROOT / "data" / "broad" / "rule" / "panel.jsonl"
PRICES = study.REPO_ROOT / "data" / "broad" / "prices"
RATE = study.REPO_ROOT / "data" / "broad" / "rule" / "fred" / "DGS1.json"
OUT = study.REPO_ROOT / "output" / "rule_alpha"
BENCHMARK = "SPY"
SPLIT_YEAR = broad.SPLIT_YEAR
MEASURES = ("margin_of_safety", "shadow_margin", "earnings_yield", "f_score")
CAP_PERCENTILE = 80.0        # the paper's cap, on this panel's own formation
MIN_MONTHS = 24              # fewer months than this and a regression is not printed
MIN_NAMES = 5                # the paper's floor on the names in a leg, month by month
EXACT = 1e-18                # residual share of the variance at or under which a fit is exact
Json = dict[str, object]
Series = dict[str, float]    # month "YYYY-MM" -> return


@dataclass(frozen=True)
class Fit:
    months: int
    mean: float      # the mean monthly return regressed, over the rate unless a spread
    beta: float
    alpha: float
    t_alpha: float | None


def months_after(year: int) -> list[str]:
    """The twelve months a June formation holds: July of the year to June of the next."""
    return [f"{year}-{m:02d}" for m in range(7, 13)] + [f"{year + 1}-{m:02d}" for m in range(1, 7)]


def previous(month: str) -> str:
    year, m = int(month[:4]), int(month[5:])
    return f"{year - 1}-12" if m == 1 else f"{year}-{m - 1:02d}"


def monthly_return(adjusted: dict[str, float], month: str) -> float | None:
    now, before = adjusted.get(month), adjusted.get(previous(month))
    if now is None or before is None or before <= 0:
        return None
    return now / before - 1


def load_rows(path: Path) -> list[Row]:
    """The valued rows of the rule panel, each with its measures and the market value."""
    rows: list[Row] = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        raw = cast(Json, json.loads(line))
        if raw.get("status") != "Ok":
            continue
        values = {m: v for m in MEASURES if (v := study.as_float(raw.get(m))) is not None}
        rows.append(Row(ticker=str(raw["ticker"]), year=int(str(raw["date"])[:4]), excess=None, non_financial=True,
                        values=values, cap=study.as_float(raw.get("market_cap"))))
    return rows


def load_adjusted(directory: Path) -> dict[str, dict[str, float]]:
    """ticker -> month -> dividend-adjusted close, from the broad panel's cached bars."""
    out: dict[str, dict[str, float]] = {}
    for path in sorted(directory.glob("*.json")):
        for ticker, bars in cast(dict[str, Json], json.loads(path.read_text())).items():
            adjusted = bars.get("adjusted")
            if isinstance(adjusted, dict):
                out[ticker] = {str(k): float(v) for k, v in cast(dict[str, object], adjusted).items() if isinstance(v, (int, float))}
    return out


def load_rate(path: Path) -> Series:
    """month -> the monthly rate applying in it: the last one-year yield observed in the
    month before, a twelfth of it."""
    last: dict[str, float] = {}
    for obs in cast(list[Json], cast(Json, json.loads(path.read_text()))["observations"]):
        try:
            value = float(str(obs.get("value")))      # the source writes "." where it has no observation
        except ValueError:
            continue
        last[str(obs["date"])[:7]] = value / 100 / 12   # observations are ascending by date
    months = sorted(last)
    return {month: last[before] for before, month in zip(months, months[1:], strict=False) if previous(month) == before}


def fifth_returns(rows: list[Row], q: dict[tuple[str, int], int], adjusted: dict[str, dict[str, float]], *, capped_value: bool) -> dict[int, Series]:
    """fifth -> month -> the fifth's return, the formations chained. A month with fewer than
    MIN_NAMES names carrying a return is left out of that fifth."""
    out: dict[int, Series] = {k: {} for k in range(1, 6)}
    for year in sorted({r.year for r in rows}):
        formed = [r for r in rows if r.year == year and (r.ticker, r.year) in q]
        caps = [r.cap for r in formed if r.cap is not None]
        ceiling = float(np.percentile(caps, CAP_PERCENTILE)) if caps else None
        for k in range(1, 6):
            members = [r for r in formed if q[(r.ticker, r.year)] == k]
            weight = {r.ticker: 1.0 if not capped_value else (min(r.cap, ceiling) if r.cap is not None and ceiling is not None else 0.0) for r in members}
            for month in months_after(year):
                got = [(t, r) for t in weight if (r := monthly_return(adjusted.get(t, {}), month)) is not None and weight[t] > 0]
                total = sum(weight[t] for t, _ in got)
                if len(got) >= MIN_NAMES and total > 0:
                    out[k][month] = sum(weight[t] * r for t, r in got) / total
                if capped_value:
                    for t, r in got:
                        weight[t] *= 1 + r        # carried forward: bought in June and held
    return out


def fit(y: list[float], x: list[float]) -> Fit | None:
    """Least squares of y on a constant and x; None under MIN_MONTHS observations or where
    x does not vary."""
    n = len(y)
    if n < MIN_MONTHS or n != len(x):
        return None
    ya, xa = np.asarray(y, dtype=float), np.asarray(x, dtype=float)
    sxx = float(((xa - xa.mean()) ** 2).sum())
    if sxx <= EXACT * float((xa ** 2).sum()):      # a market that does not move, to rounding
        return None
    beta = float(((xa - xa.mean()) * (ya - ya.mean())).sum()) / sxx
    alpha = float(ya.mean()) - beta * float(xa.mean())
    residual = ya - alpha - beta * xa
    rss, tss = float((residual ** 2).sum()), float(((ya - ya.mean()) ** 2).sum())
    if rss <= EXACT * tss:                # an exact fit carries no t-ratio, only rounding
        return Fit(months=n, mean=float(ya.mean()), beta=beta, alpha=alpha, t_alpha=None)
    se = (rss / (n - 2) * (1 / n + float(xa.mean()) ** 2 / sxx)) ** 0.5
    return Fit(months=n, mean=float(ya.mean()), beta=beta, alpha=alpha, t_alpha=alpha / se)


def regress(series: Series, market: Series, rate: Series, months: list[str], *, over_rate: bool) -> Fit | None:
    """The series (over the rate, or as it is for a spread of two fifths) on the market over
    the rate, across the months that carry all three."""
    kept = [m for m in months if m in series and m in market and m in rate]
    return fit([series[m] - (rate[m] if over_rate else 0.0) for m in kept], [market[m] - rate[m] for m in kept])


def line(label: str, f: Fit | None) -> str:
    if f is None:
        return f"  {label}: fewer than {MIN_MONTHS} months"
    t = "" if f.t_alpha is None else f" (t {f.t_alpha:+.2f})"
    mean, beta, alpha = (round(v, 2) + 0.0 for v in (100 * f.mean, f.beta, 100 * f.alpha))   # no "-0.00"
    return f"  {label}: {f.months} months, mean {mean:+.2f}% a month, beta {beta:+.2f}, alpha {alpha:+.2f}% a month{t}"


def measure_block(rows: list[Row], measure: str, adjusted: dict[str, dict[str, float]], market: Series, rate: Series,
                  label: str, *, capped_value: bool) -> list[str]:
    q = broad.quintiles(rows, measure)
    years = sorted({year for _, year in q})
    weighting = "capped value" if capped_value else "equal"
    title = f"{measure}, {label}, {weighting} weights: {len(q)} rows over {len(years)} formation years"
    lines = [title, "-" * len(title)]
    if not q:
        return lines + ["  no formation year carries enough rows"]
    months = [m for year in years for m in months_after(year)]
    fifths = fifth_returns(rows, q, adjusted, capped_value=capped_value)
    for k in range(1, 6):
        lines.append(line(f"fifth {k}", regress(fifths[k], market, rate, months, over_rate=True)))
    spread = {m: fifths[5][m] - fifths[1][m] for m in fifths[5] if m in fifths[1]}
    lines.append(line("highest less lowest", regress(spread, market, rate, months, over_rate=False)))
    return lines


def report(rows: list[Row], adjusted: dict[str, dict[str, float]], rate: Series) -> str:
    market = {m: r for m in adjusted.get(BENCHMARK, {}) if (r := monthly_return(adjusted[BENCHMARK], m)) is not None}
    years = sorted({r.year for r in rows})
    lines = [
        f"The rule study on market-adjusted returns: {len(rows)} valued records on {len({r.ticker for r in rows})} filers, formed each June {years[0]} to {years[-1]}.",
        "Descriptive only, under the rule study's limits. Monthly returns of each fifth over the twelve months from July, the formations chained; "
        f"regressed on {BENCHMARK} over the one-year Treasury rate. Mean is the fifth's return over the rate, or the spread's own. "
        "The t-ratio is the plain least-squares one on at most 156 months: a scale, not a test. Fifth 5 holds the highest value of the measure.",
        "After Jensen, Kelly and Pedersen, \"Is There a Replication Crisis in Finance?\", NBER Working Paper 28432, February 2021, doi:10.3386/w28432; "
        "and Gormsen and Lazarus, \"Duration-Driven Returns\", working paper, April 2019, doi:10.2139/ssrn.3359027.",
        "",
    ]
    def every(_: Row) -> bool:
        return True

    def before(r: Row) -> bool:
        return r.year < SPLIT_YEAR

    def since(r: Row) -> bool:
        return r.year >= SPLIT_YEAR

    stretches = (("all formations", every), (f"formations before {SPLIT_YEAR}", before), (f"formations from {SPLIT_YEAR}", since))
    for measure in MEASURES:
        for label, keep in stretches:
            kept = [r for r in rows if keep(r)]
            for capped_value in (False, True):
                lines += measure_block(kept, measure, adjusted, market, rate, label, capped_value=capped_value) + [""]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--panel", type=Path, default=PANEL)
    parser.add_argument("--prices", type=Path, default=PRICES)
    parser.add_argument("--rate", type=Path, default=RATE)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    panel: Path = args.panel
    prices: Path = args.prices
    rate_path: Path = args.rate
    out: Path = args.out
    for path, how in ((panel, "run python/rule_panel.py first"), (rate_path, "run python/rule_panel.py first: it fills the rate cache"),
                      (prices, "run python/broad_panel.py first: it fetches the monthly bars")):
        if not path.exists():
            print(f"{path} not built: {how}", file=sys.stderr)
            return 2
    adjusted = load_adjusted(prices)
    if BENCHMARK not in adjusted:
        print(f"no monthly bars for {BENCHMARK} under {prices}: run python/broad_panel.py --retry-missing", file=sys.stderr)
        return 2
    text = report(load_rows(panel), adjusted, load_rate(rate_path))
    out.mkdir(parents=True, exist_ok=True)
    (out / "tables.txt").write_text(text)
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
