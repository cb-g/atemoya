"""The discount rate on the rule panel: how much of a rate move to take, and a premium that moves.

    uv run python/rule_discount.py [--lambdas 0.7 0.46 0.3 0] [--out output/rule_discount]

The model's cost of equity is the risk-free rate at the projection tenor plus a beta times
a premium from a table, so a point on the rate is a point on the discount rate, and the
rate study found the fair values carrying their full duration against every move above the
kink. Two papers measure how far that is from what the market does. Gormsen and Lazarus,
"Interest Rates and Equity Valuations", NBER Working Paper 34814, February 2026,
doi:10.3386/w34814, find only the pure-discounting part of a rate move passes to equity
yields, about 35 per cent of the US fall over 1990-2023 and almost none of it after 2000
(pp. 3, 20, 45). Gormsen and Huber, "Corporate Discount Rates", NBER Working Paper 31329,
June 2023, doi:10.3386/w31329, value firms at a country cost of equity equal to the
earnings yield plus two per cent plus trailing ten-year inflation, so that the premium over
the risk-free rate moves against the rate (p. 14, equation 6), and find managers' perceived
cost of equity tracks that measure rather than a constant premium on the rate (p. 20).

This reruns the binary on the rule panel's own point-in-time records, statements and prices
untouched, under readings of the United States curve and premium per date:

- `as run`;
- `lambda L` for each L given: the curve moved to its mean over the panel's dates plus L of
  the date's distance from that mean, the shape kept and the terminal growth held to the
  moved rate as the model holds it; L = 1 is the run, L = 0 one flat rate on every date, the
  value Hommel, Landier and Thesmar found fits prices best (the flat rate of candidate C3);
- `implied premium`: the table's premium replaced by the paper's construct on the panel's own
  names, the aggregate earnings yield (each name's mean net income over its filed periods,
  at most five, summed, over the sum of market values on the date) plus two per cent plus
  the trailing ten-year CPI inflation, less the risk-free rate at the projection tenor.

Prints, by date, the rate and each reading's rate or premium with the count valued and the
median margin of safety; then for each reading the swing of the level, the mean of the yearly
median margins before 2022 against from 2023 and the rank correlation of the yearly medians
with the rate; the rank correlation of its margins with the run's within the date; and the
sort, the cheapest fifth's median excess return over SPY less the dearest's, before 2022 and
from it.

Descriptive only, under the rule study's limits. A variant is a question put to the model,
not a change to it: nothing here moves a parameter file or a record on the valuation path.
The CPI series is fetched from FRED once into the rule panel's cache; nothing fetched is
tracked."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import date
from pathlib import Path
from typing import cast

import anchor_study as study
import broad_study as broad
import panel_stats as ps
import pit
import refresh_rates
import rule_panel
import rule_rates
import rule_variants as variants
from broad_study import Row

OUT = study.REPO_ROOT / "output" / "rule_discount"
CPI_SERIES = "CPIAUCSL"
CPI_START = "2003-01-01"        # ten years before the first June the panel forms
REAL_GROWTH = 0.02              # the paper's long-run real growth in its equation 6
INFLATION_YEARS = 10            # its trailing window
MAX_PERIODS = 5                 # its five-year earnings
LAMBDAS = (0.7, 0.46, 0.3, 0.0)
SPLIT_YEAR = broad.SPLIT_YEAR
Json = dict[str, object]


# --- the implied premium --------------------------------------------------------------------

def aggregate_earnings_yield(pit_dir: Path, panel_rows: list[Json]) -> tuple[float, int] | None:
    """The sum over the date's names of each one's mean net income over its filed periods, at
    most MAX_PERIODS, over the sum of their market values; and the count of names in it. None
    under the small-cell floor."""
    earnings = 0.0
    caps = 0.0
    names = 0
    for row in panel_rows:
        cap = study.as_float(row.get("market_cap"))
        path = pit_dir / f"{row['ticker']}.json"
        if cap is None or cap <= 0 or not path.exists():
            continue
        periods = cast(list[Json], cast(Json, json.loads(path.read_text())).get("periods", []))[:MAX_PERIODS]
        incomes = [v for p in periods if (v := study.as_float(p.get("net_income"))) is not None]
        if not incomes:
            continue
        earnings += statistics.fmean(incomes)
        caps += cap
        names += 1
    if names < study.MIN_CELL or caps <= 0:
        return None
    return earnings / caps, names


def cpi_history(cache: Path, key: str | None) -> bytes:
    """The CPI series, from the rule panel's cache where it is, else fetched once with the key."""
    path = cache / f"{CPI_SERIES}.json"
    if path.exists():
        return path.read_bytes()
    if key is None:
        raise FileNotFoundError(f"{path} is not cached and FRED_API_KEY is not set")
    pit.FRED_CACHE = cache
    pit.HISTORY_START = CPI_START
    return pit.fred_history(CPI_SERIES, key)


def trailing_inflation(body: bytes, d: date) -> float:
    """The annual rate over the INFLATION_YEARS to the date: the ratio of the last CPI on or
    before it to the last on or before the same date INFLATION_YEARS earlier."""
    _, now = pit.observation_on_or_before(body, CPI_SERIES, d)
    _, before = pit.observation_on_or_before(body, CPI_SERIES, d.replace(year=d.year - INFLATION_YEARS))
    return (now / before) ** (1 / INFLATION_YEARS) - 1


def implied_premium(earnings_yield: float, inflation: float, rf: float) -> float:
    """Equation 6 less the risk-free rate: earnings yield + REAL_GROWTH + inflation - rf."""
    return earnings_yield + REAL_GROWTH + inflation - rf


# --- the readings -----------------------------------------------------------------------------

def level_for(mean_rf: float, rf: float, lam: float) -> float:
    return mean_rf + lam * (rf - mean_rf)


def margins_of(records: list[Json], year: int, forward: dict[tuple[str, str], float], d: str) -> list[Row]:
    out: list[Row] = []
    for r in records:
        m = study.as_float(r.get("margin_of_safety"))
        if r["status"] == "Ok" and m is not None:
            out.append(Row(ticker=str(r["ticker"]), year=year, excess=forward.get((str(r["ticker"]), d)), non_financial=True, values={"margin_of_safety": m}))
    return out


def yearly_medians(rows: list[Row]) -> dict[int, float]:
    out: dict[int, float] = {}
    for year in sorted({r.year for r in rows}):
        values = [r.values["margin_of_safety"] for r in rows if r.year == year]
        if len(values) >= study.MIN_CELL:
            out[year] = statistics.median(values)
    return out


def swing(rows: list[Row], rf_by_year: dict[int, float]) -> str:
    """The mean of the yearly median margins before SPLIT_YEAR against from SPLIT_YEAR + 1, their
    difference, and the rank correlation of the yearly medians with the rate over the years."""
    medians = yearly_medians(rows)
    before = [m for y, m in medians.items() if y < SPLIT_YEAR]
    after = [m for y, m in medians.items() if y > SPLIT_YEAR]
    rho = ps.spearman([(rf_by_year[y], m) for y, m in medians.items() if y in rf_by_year])
    if not before or not after:
        return "too few years"
    return (f"before {SPLIT_YEAR} {statistics.fmean(before):+.2f}, after {statistics.fmean(after):+.2f}, swing {statistics.fmean(before) - statistics.fmean(after):+.2f}; "
            f"rank correlation of the yearly median with the rate {('n/a' if rho is None else f'{rho:+.2f}')} over {len(medians)} years")


def rank_against(rows: list[Row], base: list[Row]) -> str:
    """The median over dates of the within-date rank correlation of the reading's margins with the run's."""
    by_key = {(r.ticker, r.year): r.values["margin_of_safety"] for r in base}
    per_year: list[float] = []
    for year in sorted({r.year for r in rows}):
        pairs = [(r.values["margin_of_safety"], v) for r in rows if r.year == year and (v := by_key.get((r.ticker, r.year))) is not None]
        rho = ps.spearman(pairs)
        if rho is not None:
            per_year.append(rho)
    return f"median {statistics.median(per_year):+.2f} over {len(per_year)} dates (lowest {min(per_year):+.2f})" if per_year else "n/a"


def spread(rows: list[Row], *, before: bool) -> str:
    """The cheapest fifth's median excess less the dearest's, fifths cut within the year."""
    sub = [r for r in rows if (r.year < SPLIT_YEAR) == before and r.excess is not None]
    q = broad.quintiles(sub, "margin_of_safety")
    cheap = broad.cell([r for r in sub if q.get((r.ticker, r.year)) == 5])
    dear = broad.cell([r for r in sub if q.get((r.ticker, r.year)) == 1])
    if cheap[1] is None or dear[1] is None:
        return f"n/a ({cheap[0]} and {dear[0]} rows)"
    return f"{100 * (cheap[1] - dear[1]):+.1f} points ({cheap[0]} and {dear[0]} rows)"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--binary", type=Path, default=rule_panel.BINARY)
    parser.add_argument("--lambdas", nargs="*", type=float, default=list(LAMBDAS))
    args = parser.parse_args(argv)
    out: Path = args.out
    binary: Path = args.binary
    lambdas: list[float] = args.lambdas
    pit_root = rule_panel.ROOT / "pit"
    panel_path = rule_panel.ROOT / "panel.jsonl"
    if not panel_path.exists():
        print(f"{panel_path} not built: run python/rule_panel.py first", file=sys.stderr)
        return 2
    try:
        cpi = cpi_history(rule_panel.ROOT / "fred", refresh_rates._api_key())  # pyright: ignore[reportPrivateUsage]
    except Exception as e:  # noqa: BLE001
        print(f"no CPI series: {e}", file=sys.stderr)
        return 2
    panel_rows: dict[str, list[Json]] = {}
    forward: dict[tuple[str, str], float] = {}
    for line in panel_path.read_text().splitlines():
        if line.strip():
            raw = cast(Json, json.loads(line))
            panel_rows.setdefault(str(raw["date"]), []).append(raw)
            f, s = study.as_float(raw.get("forward_12m")), study.as_float(raw.get("spy_12m"))
            if f is not None and s is not None:
                forward[(str(raw["ticker"]), str(raw["date"]))] = f - s
    dates = sorted(p for p in pit_root.iterdir() if p.is_dir())
    rf_by_date = {p.name: variants.rates_on(p / "reference")[0] for p in dates}
    mean_rf = statistics.mean(rf_by_date.values())
    readings = ["as_run", *[f"lambda_{lam:g}" for lam in lambdas], "implied_premium"]
    rows: dict[str, list[Row]] = {name: [] for name in readings}
    rf_by_year: dict[int, float] = {}
    lines = [
        f"The discount rate on the rule panel. Descriptive only; a variant is a question put to the model, not a change to it. Mean rate at the projection tenor over {len(dates)} dates {mean_rf:.2%}; "
        f"lambda readings {', '.join(f'{lam:g}' for lam in lambdas)}; the implied premium the aggregate earnings yield + {REAL_GROWTH:.0%} + trailing {INFLATION_YEARS}-year CPI inflation - the rate.",
        "After Gormsen and Lazarus, \"Interest Rates and Equity Valuations\", NBER Working Paper 34814, February 2026, doi:10.3386/w34814, and Gormsen and Huber, \"Corporate Discount Rates\", NBER Working Paper 31329, June 2023, doi:10.3386/w31329.",
        "",
        "by date: the rate as run and the table's premium; then each reading's rate or premium, the count valued and the median margin of safety",
        "-" * 120,
    ]
    for pit_dir in dates:
        d = pit_dir.name
        year = int(d[:4])
        rf, _, table_premium, _ = variants.rates_on(pit_dir / "reference")
        rf_by_year[year] = rf
        universe = rule_panel.ROOT / "universe" / f"{d}.study.json"
        cells: list[str] = []
        ey = aggregate_earnings_yield(pit_dir, panel_rows.get(d, []))
        inflation = trailing_inflation(cpi, date.fromisoformat(d))
        for name in readings:
            reference_dir = out / "reference" / name / d
            label = ""
            if name == "as_run":
                rule_rates.shifted_reference(pit_dir / "reference", reference_dir)
                label = f"rate {rf:.2%}"
            elif name.startswith("lambda_"):
                level = level_for(mean_rf, rf, float(name[len("lambda_"):]))
                rule_rates.shifted_reference(pit_dir / "reference", reference_dir, to=level)
                label = f"rate {level:.2%}"
            else:
                if ey is None:
                    cells.append(f"{name}: no aggregate earnings yield on the date")
                    continue
                premium = implied_premium(ey[0], inflation, rf)
                variants.variant_reference(pit_dir / "reference", reference_dir, growth=None, premium=premium)
                label = f"premium {premium:.2%} (earnings yield {ey[0]:.2%} on {ey[1]} names, inflation {inflation:.2%})"
            records = variants.run_variant(binary, pit_dir, universe, reference_dir, d, out / name / d)
            got = margins_of(records, year, forward, d)
            rows[name] += got
            median = statistics.median(r.values["margin_of_safety"] for r in got) if got else None
            cells.append(f"{name}: {label}; {len(got)} valued" + (f", median margin {median:+.2f}" if median is not None else ""))
        lines.append(f"  {d}: rate {rf:.2%}, table premium {table_premium:.2%}")
        lines += [f"      {c}" for c in cells]
        print(lines[-len(cells) - 1], flush=True)
    lines += ["", "the level's swing, the rank against the run and the sort, per reading", "-" * 120]
    for name in readings:
        lines.append(f"  {name}:")
        lines.append(f"      level: {swing(rows[name], rf_by_year)}")
        lines.append(f"      rank against the run within the date: {rank_against(rows[name], rows['as_run'])}")
        lines.append(f"      cheapest fifth less dearest, excess over SPY at twelve months: before {SPLIT_YEAR} {spread(rows[name], before=True)}; from {SPLIT_YEAR} {spread(rows[name], before=False)}")
    lines.append("  the papers: about 35 per cent of the US rate fall was pure discounting and passed through, almost none of it after 2000 (Gormsen and Lazarus, pp. 3, 20); "
                 "the perceived cost of equity tracked the earnings-yield measure, not a constant premium on the rate (Gormsen and Huber, p. 20)")
    text = "\n".join(lines) + "\n"
    out.mkdir(parents=True, exist_ok=True)
    (out / "tables.txt").write_text(text)
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
