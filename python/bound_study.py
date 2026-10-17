"""The options bound against what followed.

Every record valued under --options carries an options-implied expected return, the
Martin-Wagner formula on the risk-neutral variances the chains price: the benchmark's, the
name's, and the mean of the names'. Back, Crotty and Kazempour, "Validity, tightness, and
forecasting power of risk premium bounds", Journal of Financial Economics 144 (2022)
732-760, doi:10.1016/j.jfineco.2022.02.003, test that formula as the lower bound it is
without its assumptions, on S&P 500 names 1996-2020: it is valid and slack, the realised
excess return about twice the bound (Table 2: 9.23 per cent against 4.50 at twelve months);
the ranking of names on it carries almost nothing (Table 7's Fama-MacBeth slope negative,
Table 10's top less bottom fifth 1.93 points on a standard error of 4.60); what information
there is sits in a name's bound against its own history (the fixed-effects slope near one);
and the bound is a lower bound only for a name whose delta, the ratio of its return variance
to its covariance with the market, is small: above seven the Martin formula on the name
itself met or exceeded what followed (Table 2's Other group, 7.07 against 6.90). Their
discrete sum over quoted strikes, equation C.2 on page 759, "is always smaller than the
integral", so every such bound understates, and a chain quoted over a narrower range
understates more.

This study asks those questions of the options store, in the tool's own terms. The records
never carried the expected return on the point-in-time dates, so the bound is computed here
from each day's chains with the paper's own sum: at the shortest expiry at least 365 days out
with eight quoted strikes each side of the spot, the rule the record reads an expiry by, the
strikes with a put and a call quoted and the cheaper of the two, the sum of the strike step
times the smaller neighbouring price, twice that over the squared spot, per year. That is the
risk-free rate times SVIX squared, the Kadan-Tang bound on the name; the Martin-Wagner bound
is the benchmark's plus half the name's excess over the names' mean. The mean here is
equal-weighted over the names the store holds that day, where the record's is weighted by
market capitalisation and the paper's by the index's.

Then, on the last store day of each month: the strike coverage beside the bound, the lowest
and highest strike over the spot and what the bound reads when every chain is cut to one
common window; the slack, realised excess return over the one-year rate less the bound, at
one, three, six and twelve months, pooled and by the paper's delta groups; per name, whether
the bound met what followed; the rank of the bound against delta and against the return that
followed within the date; and the earliest reading of the own-history question, a name's
demeaned bound against its own trailing mean. Every row's demeaned bound is written out so
the own-history test can be run properly once the store holds years.

Descriptive only. The store begins in April 2025, so the twelve-month rows end in September
2025 and the dates overlap; the realised returns are from split-adjusted closes without
dividends; the held-out names and dates are set aside unless --holdout opens them. Nothing
here feeds a record, a belief or a signal.

    uv run python/bound_study.py [--holdout]     # -> output/bound_study/tables.txt, rows.jsonl
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import cast

import numpy as np

import anchor_study as study
import panel_stats as ps

OUT = study.REPO_ROOT / "output" / "bound_study"
STORE = study.REPO_ROOT / "data" / "options"
RATES = study.REPO_ROOT / "data" / "broad" / "rule" / "fred" / "DGS1.json"
BENCHMARK = "SPY"
MIN_DAYS_OUT = 365              # the record's rule for the expiry it reads (ocaml/lib/market_implied.ml)
MIN_STRIKES_EACH_SIDE = 8       # the same
HORIZONS = (21, 63, 126, 252)   # trading days: the paper's one, three, six and twelve months
DELTA_WINDOW = 252              # the paper's rolling window of daily returns for delta
DELTA_MIN_DAYS = 200            # and its floor
DELTA_GROUPS = (("conservative", 3.0), ("liberal", 7.0), ("other", float("inf")))   # the paper's: delta at most 3, 3 to 7, above 7
COMMON_WINDOW = (0.75, 1.5)     # strikes over spot: one width every chain is cut to, to read what the range does to the bound
OWN_HISTORY_MONTHS = 6          # a name's demeaned bound against its mean over this many month-ends before

Json = dict[str, object]


@dataclass(frozen=True)
class Bound:
    ticker: str
    day: str
    expiry: str
    days: int
    spot: float
    strikes: int                # strikes with a put and a call quoted at the expiry
    low: float                  # the lowest such strike over the spot
    high: float                 # the highest
    bound: float                # 2 I / (S^2 T): the risk-free rate times SVIX^2, per year
    common: float               # the same on the strikes inside COMMON_WINDOW
    reaches: bool               # the chain reaches both edges of the common window
    longest: float              # the bound at the longest usable expiry, the record's choice


@dataclass
class Row:
    bound: Bound
    market: float               # the benchmark's bound on the day
    mean: float                 # the equal-weighted mean of the names' bounds on the day
    rf: float                   # the one-year rate on the day, per year
    delta: float | None = None
    beta_positive: bool | None = None
    excess: dict[int, float] = field(default_factory=lambda: {})     # horizon -> realised excess over the rate, per year

    @property
    def kt(self) -> float:
        return self.bound.bound

    @property
    def demeaned(self) -> float:
        return self.bound.bound - self.mean

    @property
    def mw(self) -> float:
        return self.market + self.demeaned / 2

    @property
    def group(self) -> str | None:
        if self.delta is None or self.beta_positive is None:
            return None
        if not self.beta_positive:
            return "other"
        for name, ceiling in DELTA_GROUPS:
            if self.delta <= ceiling:
                return name
        return "other"


# --- the bound from a chain -----------------------------------------------------------------

def quoted(quotes: list[Json], expiry: str) -> list[Json]:
    return [q for q in quotes if q["expiration"] == expiry and float(cast(float, q["bid"])) > 0]


def usable_expiries(quotes: list[Json], spot: float, day: str) -> list[tuple[str, int]]:
    """(expiry, days out) for every expiry at least MIN_DAYS_OUT away with MIN_STRIKES_EACH_SIDE
    quoted strikes below the spot in puts and above it in calls, shortest first."""
    out: list[tuple[str, int]] = []
    for expiry in sorted({str(q["expiration"]) for q in quotes}):
        days = (date.fromisoformat(expiry) - date.fromisoformat(day)).days
        if days < MIN_DAYS_OUT:
            continue
        qs = quoted(quotes, expiry)
        below = {q["strike"] for q in qs if q["right"] == "put" and float(cast(float, q["strike"])) < spot}
        above = {q["strike"] for q in qs if q["right"] == "call" and float(cast(float, q["strike"])) > spot}
        if len(below) >= MIN_STRIKES_EACH_SIDE and len(above) >= MIN_STRIKES_EACH_SIDE:
            out.append((expiry, days))
    return sorted(out, key=lambda e: e[1])


def otm_prices(quotes: list[Json], expiry: str) -> list[tuple[float, float]]:
    """The paper's Appendix C: at each strike with both a put and a call quoted, the cheaper of
    the two mids, which is the out-of-the-money one; (strike, price) ascending."""
    sides: dict[float, dict[str, float]] = {}
    for q in quoted(quotes, expiry):
        sides.setdefault(float(cast(float, q["strike"])), {})[str(q["right"])] = float(cast(float, q["mid"]))
    return sorted((k, min(s["put"], s["call"])) for k, s in sides.items() if "put" in s and "call" in s)


def integral(points: list[tuple[float, float]]) -> float:
    """Equation C.2: the sum over neighbouring strikes of the step times the smaller price."""
    return sum((k - k0) * min(p, p0) for (k0, p0), (k, p) in zip(points, points[1:], strict=False))


def bound_of(points: list[tuple[float, float]], spot: float, years: float) -> float:
    """2 I / S^2 over the horizon in years: the risk-free rate times SVIX squared, per year."""
    return 2 * integral(points) / (spot * spot) / years


def cut(points: list[tuple[float, float]], spot: float, window: tuple[float, float] = COMMON_WINDOW) -> tuple[list[tuple[float, float]], bool]:
    """The points inside the window of strikes over spot, and whether the chain reaches both edges."""
    lo, hi = window[0] * spot, window[1] * spot
    inside = [(k, p) for k, p in points if lo <= k <= hi]
    reaches = bool(points) and points[0][0] <= lo and points[-1][0] >= hi
    return inside, reaches


def bound_of_chain(path: Path) -> Bound | None:
    raw = cast(Json, json.loads(path.read_text()))
    spot = float(cast(float, raw["underlying_close"]))
    day = str(raw["snapshot_date"])
    quotes = cast(list[Json], raw["quotes"])
    if spot <= 0 or not quotes:
        return None
    expiries = usable_expiries(quotes, spot, day)
    if not expiries:
        return None
    expiry, days = expiries[0]
    points = otm_prices(quotes, expiry)
    if len(points) < 2 * MIN_STRIKES_EACH_SIDE:
        return None
    years = days / 365
    inside, reaches = cut(points, spot)
    far, far_days = expiries[-1]
    return Bound(ticker=str(raw["ticker"]), day=day, expiry=expiry, days=days, spot=spot, strikes=len(points),
                 low=points[0][0] / spot, high=points[-1][0] / spot, bound=bound_of(points, spot, years),
                 common=bound_of(inside, spot, years) if len(inside) >= 2 else 0.0, reaches=reaches,
                 longest=bound_of(otm_prices(quotes, far), spot, far_days / 365))


# --- rates, closes, delta, what followed ---------------------------------------------------

def load_rates(path: Path) -> list[tuple[str, float]]:
    """(day, one-year yield per year) ascending, from the FRED series the rule panel cached."""
    out: list[tuple[str, float]] = []
    for obs in cast(list[Json], cast(Json, json.loads(path.read_text()))["observations"]):
        try:
            out.append((str(obs["date"]), float(str(obs.get("value"))) / 100))
        except ValueError:          # the source writes "." where it has no observation
            continue
    return sorted(out)


def rate_on(rates: list[tuple[str, float]], day: str) -> float | None:
    """The last yield observed on or before the day."""
    last: float | None = None
    for d, v in rates:
        if d > day:
            break
        last = v
    return last


def closes_of(cache: Path, ticker: str) -> dict[date, float] | None:
    """The newest cached closes for the name; never fetches."""
    files = sorted(cache.glob(f"{ticker}-*.json"))
    if not files:
        return None
    raw = cast(dict[str, float], json.loads(files[-1].read_text()))
    return {date.fromisoformat(d): float(v) for d, v in raw.items()}


def returns_to(closes: dict[date, float], day: date, window: int) -> dict[date, float]:
    """day -> the return into it over the last [window] trading days up to and including [day]."""
    days = sorted(d for d in closes if d <= day)[-(window + 1):]
    return {b: closes[b] / closes[a] - 1 for a, b in zip(days, days[1:], strict=False)}


def delta_of(stock: dict[date, float], market: dict[date, float], day: date) -> tuple[float, bool] | None:
    """The paper's delta, var(R_i) / cov(R_i, R_m) over the DELTA_WINDOW trading days to the day,
    with whether the covariance is positive; None under DELTA_MIN_DAYS common days."""
    s, m = returns_to(stock, day, DELTA_WINDOW), returns_to(market, day, DELTA_WINDOW)
    common = sorted(set(s) & set(m))
    if len(common) < DELTA_MIN_DAYS:
        return None
    x, y = np.asarray([s[d] for d in common]), np.asarray([m[d] for d in common])
    cov = float(np.cov(x, y, ddof=1)[0, 1])
    if cov == 0:
        return None
    return float(x.var(ddof=1)) / cov, cov > 0


def attach(rows: list[Row], cache: Path) -> int:
    """Delta and the realised excess returns on every row from the cached closes; the rows that
    got at least one."""
    market = closes_of(cache, BENCHMARK)
    if market is None:
        return 0
    by_name: dict[str, dict[date, float] | None] = {}
    attached = 0
    for r in rows:
        if r.bound.ticker not in by_name:
            by_name[r.bound.ticker] = closes_of(cache, r.bound.ticker)
        closes = by_name[r.bound.ticker]
        if closes is None:
            continue
        day = date.fromisoformat(r.bound.day)
        d = delta_of(closes, market, day)
        if d is not None:
            r.delta, r.beta_positive = d
        for h in HORIZONS:
            ret, _ = study.forward_return(closes, day, h)
            if ret is not None:
                r.excess[h] = (ret - r.rf * h / 252) * 252 / h
        if r.excess or d is not None:
            attached += 1
    return attached


# --- the rows -------------------------------------------------------------------------------

def rows_of(store: Path, rates: list[tuple[str, float]], holdout: study.Holdout, *, opened: bool) -> tuple[list[Row], str, int]:
    """One row per name and store day with a usable chain on a day the benchmark has one; the
    holdout line; the days skipped for want of a benchmark bound or a rate."""
    rows: list[Row] = []
    held = 0
    skipped = 0
    for day_dir in sorted(p for p in store.iterdir() if p.is_dir()):
        day = day_dir.name
        rf = rate_on(rates, day)
        market = bound_of_chain(day_dir / f"{BENCHMARK}.json") if (day_dir / f"{BENCHMARK}.json").exists() else None
        if rf is None or market is None:
            skipped += 1
            continue
        bounds = [b for p in sorted(day_dir.glob("*.json")) if p.stem != BENCHMARK and (b := bound_of_chain(p)) is not None]
        kept: list[Bound] = []
        for b in bounds:
            if holdout.holds(b.ticker, b.day) and not opened:
                held += 1
                continue
            kept.append(b)
        if not kept:
            continue
        mean = statistics.fmean(b.bound for b in kept)
        rows += [Row(bound=b, market=market.bound, mean=mean, rf=rf) for b in kept]
    line = (f"HOLDOUT OPENED: the held-out names and dates are in the tables below; record the opening in reference/holdout.json."
            if opened else f"Holdout (reference/holdout.json): {held} rows set aside, {len(holdout.names)} names and every day after {holdout.dates_after}; not read.")
    return rows, line, skipped


def month_ends(rows: list[Row]) -> list[Row]:
    """The rows on the last store day of each month."""
    last: dict[str, str] = {}
    for r in rows:
        last[r.bound.day[:7]] = max(last.get(r.bound.day[:7], ""), r.bound.day)
    ends = set(last.values())
    return [r for r in rows if r.bound.day in ends]


# --- the tables -----------------------------------------------------------------------------

def pct(x: float) -> str:
    return f"{100 * x:+.1f}"


def coverage_block(rows: list[Row]) -> list[str]:
    lines = ["the bound and the strikes it ran over, on the last store day of each month (medians over the names; per cent per year)", "-" * 120,
             f"  {'month':<8} {'names':>5} {'market':>7} {'name':>7} {'MW':>7} {'low K/S':>8} {'high K/S':>9} {'strikes':>8} {'reach':>6} {'cut/full':>9} {'long/12m':>9}"]
    for day in sorted({r.bound.day for r in rows}):
        rs = [r for r in rows if r.bound.day == day]
        med = statistics.median
        lines.append(f"  {day[:7]:<8} {len(rs):>5} {100 * rs[0].market:>7.2f} {100 * med(r.kt for r in rs):>7.2f} {100 * med(r.mw for r in rs):>7.2f} "
                     f"{med(r.bound.low for r in rs):>8.2f} {med(r.bound.high for r in rs):>9.2f} {med(r.bound.strikes for r in rs):>8.0f} "
                     f"{sum(1 for r in rs if r.bound.reaches) / len(rs):>6.0%} {med(r.bound.common / r.bound.bound for r in rs if r.bound.bound > 0):>9.2f} "
                     f"{med(r.bound.longest / r.bound.bound for r in rs if r.bound.bound > 0):>9.2f}")
    lines.append(f"  'name' is the Kadan-Tang bound, the Martin formula on the name itself; 'MW' the Martin-Wagner bound, the market's plus half the name's excess over the mean; "
                 f"'reach' the share of chains quoted to both edges of the window {COMMON_WINDOW[0]:.2f} to {COMMON_WINDOW[1]:.2f} of spot; "
                 f"'cut/full' the bound on the window over the bound on every strike; 'long/12m' the bound at the longest usable expiry, which the record reads, over the one here")
    lines.append("  the paper's Table 2: Martin-Wagner mean 4.50 per cent at twelve months, median 2.92; Kadan-Tang 10.51 and 6.94; its sum over quoted strikes is always under the integral, as this one is")
    return lines


def slack_block(rows: list[Row]) -> list[str]:
    lines = ["the slack: the realised excess return over the one-year rate less the bound, per cent per year, means over the month-end rows with an outcome, by the paper's delta groups", "-" * 120,
             f"  {'horizon':<10} {'group':<14} {'rows':>5} {'names':>5}   {'excess':>8} {'MW':>7} {'KT':>7}   {'slack MW':>9} {'slack KT':>9}   {'bound met':>9}"]
    for h in HORIZONS:
        with_outcome = [r for r in rows if h in r.excess]
        for group in ("all", *[g for g, _ in DELTA_GROUPS]):
            rs = with_outcome if group == "all" else [r for r in with_outcome if r.group == group]
            if len(rs) < study.MIN_CELL:
                lines.append(f"  {h:<10} {group:<14} {len(rs):>5}   fewer than {study.MIN_CELL} rows")
                continue
            excess = statistics.fmean(r.excess[h] for r in rs)
            mw, kt = statistics.fmean(r.mw for r in rs), statistics.fmean(r.kt for r in rs)
            met = sum(1 for r in rs if r.kt >= r.excess[h]) / len(rs)
            lines.append(f"  {h:<10} {group:<14} {len(rs):>5} {len({r.bound.ticker for r in rs}):>5}   {pct(excess):>8} {pct(mw):>7} {pct(kt):>7}   {pct(excess - mw):>9} {pct(excess - kt):>9}   {met:>9.0%}")
    lines.append("  'bound met' is the share of rows whose Kadan-Tang bound was at or above the excess return that followed; 'other' holds delta above seven and the "
                 f"{sum(1 for r in rows if r.beta_positive is False)} rows whose covariance with the market over the year was not positive, where the formula bounds nothing")
    lines.append("  the paper's Table 2 at twelve months: excess 9.23 against Martin-Wagner 4.50 and Kadan-Tang 10.51 over all names; conservative 12.31 against 3.50 and 7.45; "
                 "liberal 7.44 against 4.45 and 10.60; other 6.90 against 7.07 and 17.57, the Martin formula on the name an upper bound there")
    return lines


def names_block(rows: list[Row]) -> list[str]:
    lines = ["per name, over its month-end rows with a twelve-month outcome: did the bound meet what followed", "-" * 120,
             f"  {'name':<8} {'rows':>4} {'delta':>6} {'group':<13} {'excess':>8} {'MW':>7} {'KT':>7}   {'KT met':>6}"]
    names = sorted({r.bound.ticker for r in rows if 252 in r.excess})
    flagged: dict[str, list[str]] = {}
    for name in names:
        rs = [r for r in rows if r.bound.ticker == name and 252 in r.excess]
        deltas = [r.delta for r in rs if r.delta is not None]
        delta = statistics.median(deltas) if deltas else None
        groups = [r.group for r in rs if r.group is not None]
        group = statistics.mode(groups) if groups else "n/a"
        excess, mw, kt = (statistics.fmean(r.excess[252] for r in rs), statistics.fmean(r.mw for r in rs), statistics.fmean(r.kt for r in rs))
        met = kt >= excess
        if met:
            flagged.setdefault(group, []).append(name)
        lines.append(f"  {name:<8} {len(rs):>4} {('n/a' if delta is None else f'{delta:.1f}'):>6} {group:<13} {pct(excess):>8} {pct(mw):>7} {pct(kt):>7}   {'yes' if met else 'no':>6}")
    if names:
        lines.append(f"  {len(names)} names; the Kadan-Tang bound met the excess return that followed on {sum(len(v) for v in flagged.values())}: "
                     + "; ".join(f"{g} {', '.join(v)}" for g, v in sorted(flagged.items())))
    lines.append("  a name whose bound met what followed over these months is a name the formula did not bound from below here; the paper reads that of delta above seven, not of a name")
    return lines


def rank_block(rows: list[Row]) -> list[str]:
    lines = ["within the date, the rank correlation of the Martin-Wagner bound with delta and with what followed (median over month-ends; the count of dates)", "-" * 120]
    def value(r: Row, horizon: int | None) -> float | None:
        return r.delta if horizon is None else r.excess.get(horizon)

    for label, horizon in (("delta", None), *[(f"excess at {h} days", h) for h in HORIZONS]):
        per_date: list[float] = []
        pooled: list[tuple[float, float]] = []
        for day in sorted({r.bound.day for r in rows}):
            pairs = [(r.mw, v) for r in rows if r.bound.day == day and (v := value(r, horizon)) is not None]
            rho = ps.spearman(pairs)
            if rho is not None:
                per_date.append(rho)
            pooled += pairs
        pooled_rho = ps.spearman(pooled)
        lines.append(f"  with {label:<20} " + ("no date carries ten rows" if not per_date else
                     f"median {statistics.median(per_date):+.2f} over {len(per_date)} dates (lowest {min(per_date):+.2f}, highest {max(per_date):+.2f}); pooled {('n/a' if pooled_rho is None else f'{pooled_rho:+.2f}')}"))
    lines.append("  the paper: the bound rises with delta while the return that followed falls (p. 739); the Fama-MacBeth slope of the return on the bound is negative, -0.25 at twelve months (Table 7); "
                 "the top less bottom fifth 1.93 points on a standard error of 4.60 (Table 10)")
    return lines


def own_history_block(rows: list[Row]) -> list[str]:
    lines = [f"a name's demeaned bound against its own mean over the {OWN_HISTORY_MONTHS} month-ends before: the excess return that followed (medians; the earliest reading the store allows)", "-" * 120]
    by_name: dict[str, list[Row]] = {}
    for r in rows:
        by_name.setdefault(r.bound.ticker, []).append(r)
    above: dict[int, list[float]] = {h: [] for h in HORIZONS}
    below: dict[int, list[float]] = {h: [] for h in HORIZONS}
    for series in by_name.values():
        series.sort(key=lambda r: r.bound.day)
        for i in range(OWN_HISTORY_MONTHS, len(series)):
            own = statistics.fmean(s.demeaned for s in series[i - OWN_HISTORY_MONTHS:i])
            target = above if series[i].demeaned > own else below
            for h in HORIZONS:
                if h in series[i].excess:
                    target[h].append(series[i].excess[h])
    for h in HORIZONS:
        a, b = above[h], below[h]
        if len(a) < study.MIN_CELL or len(b) < study.MIN_CELL:
            lines.append(f"  {h} days: above {len(a)} rows, below {len(b)}: fewer than {study.MIN_CELL} on a side")
            continue
        lines.append(f"  {h} days: above its own mean {len(a)} rows, median excess {pct(statistics.median(a))}; below {len(b)} rows, {pct(statistics.median(b))}; difference {pct(statistics.median(a) - statistics.median(b))}")
    lines.append("  the paper: the information in the bound is in a name's own time series, the panel slope with stock fixed effects 1.08 at twelve months (Table 7), the cross-section nothing; "
                 "months are not years, and rows.jsonl carries every day's demeaned bound for the test once the store holds them")
    return lines


def report(rows: list[Row], holdout_line: str, skipped: int, attached: int) -> str:
    ends = month_ends(rows)
    names = {r.bound.ticker for r in rows}
    head = [f"The options bound against what followed. {len(rows)} name-days on {len(names)} names over {len({r.bound.day for r in rows})} store days; "
            f"the tables read the {len(ends)} rows on the {len({r.bound.day for r in ends})} month-ends; {skipped} day(s) skipped for want of a benchmark chain or a rate; "
            f"{attached} rows with closes attached.",
            holdout_line,
            "Descriptive: the dates overlap, the returns are from split-adjusted closes without dividends, the mean bound is equal-weighted over the store's names. Nothing here feeds a record.", ""]
    return "\n".join(head + coverage_block(ends) + [""] + slack_block(ends) + [""] + names_block(ends) + [""] + rank_block(ends) + [""] + own_history_block(ends)) + "\n"


def write_rows(rows: list[Row], path: Path) -> None:
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps({"ticker": r.bound.ticker, "day": r.bound.day, "expiry": r.bound.expiry, "days": r.bound.days, "spot": r.bound.spot,
                                "strikes": r.bound.strikes, "low_over_spot": r.bound.low, "high_over_spot": r.bound.high, "kadan_tang": r.kt,
                                "common_window": r.bound.common, "reaches_window": r.bound.reaches, "longest_expiry": r.bound.longest,
                                "market": r.market, "mean": r.mean, "demeaned": r.demeaned, "martin_wagner": r.mw, "risk_free_rate": r.rf,
                                "delta": r.delta, "beta_positive": r.beta_positive, "group": r.group,
                                "excess": {str(h): v for h, v in r.excess.items()}}) + "\n")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--store", type=Path, default=STORE)
    parser.add_argument("--closes", type=Path, default=study.CACHE)
    parser.add_argument("--rates", type=Path, default=RATES)
    parser.add_argument("--holdout-file", type=Path, default=study.HOLDOUT)
    parser.add_argument("--holdout", action="store_true", help="read the held-out names and dates too, and say so")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    if not args.store.is_dir():
        print(f"no options store at {args.store}: run python/fetch_options.py first", file=sys.stderr)
        return 2
    if not args.rates.exists():
        print(f"no one-year rate series at {args.rates}: run python/rule_panel.py first, which caches it", file=sys.stderr)
        return 2
    rows, holdout_line, skipped = rows_of(args.store, load_rates(args.rates), study.load_holdout(args.holdout_file), opened=args.holdout)
    attached = attach(rows, args.closes)
    args.out.mkdir(parents=True, exist_ok=True)
    text = report(rows, holdout_line, skipped, attached)
    (args.out / "tables.txt").write_text(text)
    write_rows(rows, args.out / "rows.jsonl")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
