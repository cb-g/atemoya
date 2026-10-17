"""Betas on the rule panel: which beta forecasts next year's, and what a fair value reads under each.

    uv run python/rule_betas.py [--forecast-only] [--out output/rule_betas]

The rule panel values every name at a beta of one, the record saying so, and the beta study
(python/rule_beta.py) read the market's side: among the largest five hundred US filers since
2013 the market paid for beta about in full, and the beta gap of a sort lost more than half
of itself in five years. Two questions were left open there, and two papers read for this
tool bear on them:

- Which beta to put in a cost of equity, if any. Levi and Welch, "Best Practice for
  Cost-of-Capital Estimates", Journal of Financial and Quantitative Analysis 52(2), 2017,
  doi:10.1017/S0022109017000114, ask which historical beta best forecasts next year's
  realised beta: a year of daily returns, Vasicek's shrinkage toward the cross-sectional
  mean, then a second shrinkage of about a quarter toward a target near one for large firms
  (their equation 1), reaches an R-squared near a half (their Table 1); an industry beta in
  place of the stock's own explains four per cent (their Table 11); and the slope of a
  future beta on today's falls from 0.73 one year ahead to 0.52 at five and 0.39 at ten
  (their Table 12). The first part here runs the same forecast on the panel's names.
- Whether one beta belongs on every projection year. Keloharju, Linnainmaa and Nyberg,
  "Long-Term Discount Rates Do Not Vary Across Firms", NBER Working Paper 25579, February
  2019, doi:10.3386/w25579, find the beta gap between the top and bottom tenths of a sort
  half gone after five years and 0.36 of itself after ten (their Figure 6), and recommend
  about the same discount rate for every stock. The second part here values the panel under
  a beta with its deviation from one halved, the paper's five-year figure, beside the
  others.

Part one, the forecast. Each June every name in the rule panel with a year of daily closes
is given, from its returns on SPY's over the year to the date:

- `ols`: the plain slope, at least MIN_DAYS days, winsorised at WINSOR, with its standard
  error;
- `vck`: Vasicek's estimate, the slope weighted by the cross-section's variance of slopes
  against its own squared standard error, the rest on the cross-sectional mean of the
  date's names;
- `lw`: `vck` shrunk a second time, SECOND_SHRINK of it replaced by TARGET, the second
  paper's recipe for a large firm;
- `fp`: the beta study's estimate (Frazzini and Pedersen, "Betting Against Beta", NBER
  Working Paper 16601, December 2010, doi:10.3386/w16601): five lagged market terms, the
  slopes summed, halved toward one;
- `industry`: the mean `ols` of the other names sharing the two-digit SEC industry code
  at the date, MIN_GROUP of them at least;
- `one`: the constant the rule panel runs on.

The target is the name's `ols` over the twelve months after the date. For each estimator,
used as it is: the R-squared as one less the squared errors over the squared deviations
from the targets' mean, and the root mean squared error; then fitted, the intercept and
slope of the target on the estimator and the R-squared of that line. Then the horizon:
the slope and R-squared of the `ols` one to HORIZONS years ahead on today's `vck`.

Part two, the fair values. The binary is rerun on the rule panel's own point-in-time
records, statements and prices untouched, with each name's industry set to its own ticker
and a beta table of the date carrying that name's beta, so the valuation reads the beta as
it reads an industry table and the record says where it came from. Four readings per date:
`one`, `lw`, `fp`, and `lw_faded`, one plus FADE of `lw`'s deviation from it. Per date:
each reading's count valued, median margin of safety, the rank correlation of its margins
with `one`'s and the median change of the fair value's log. Then the rank correlation of
the margin with `lw` beta under each reading, the flat rate's lean toward or against the
high-beta names and what each beta does to it. Then each reading's sort, cheapest fifth
less dearest on the next twelve months over SPY, before and from SPLIT_YEAR, and the same
sort scored as CAPM alpha as python/rule_alpha.py scores the others.

Where this departs from the papers: the forecast is pooled over the largest five hundred
each June and a single market where the second paper pools every CRSP stock over nine
decades, so its mean and dispersion are those of large names; returns, not returns over the
rate, as the beta study has it; and an industry here is the mean of own betas in a
two-digit code, not the beta of an industry portfolio.

Descriptive only, under the rule study's limits. A reading is a question put to the model,
not a change to it: nothing here moves a parameter file, a record on the valuation path,
or the beta any record carries."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import numpy as np

import anchor_study as study
import broad_study as broad
import panel_stats as ps
import rule_alpha as alpha
import rule_beta as rb
import rule_panel
import rule_variants as variants
from broad_study import Row

OUT = study.REPO_ROOT / "output" / "rule_betas"
SPLIT_YEAR = broad.SPLIT_YEAR
BENCHMARK = alpha.BENCHMARK
MIN_DAYS = 220                 # the second paper's floor on daily returns in the year
WINSOR = (-3.0, 5.0)           # its bounds on a slope
SECOND_SHRINK = 0.25           # its equation 1: a quarter of the Vasicek estimate replaced by the target
TARGET = 1.0                   # its target for a large firm
FADE = 0.5                     # the third paper's beta gap after five years, as a share of the gap at formation
MIN_GROUP = 5                  # fewer names than this in an industry code and it has no industry beta
HORIZONS = 5
ESTIMATORS = ("one", "ols", "vck", "lw", "fp", "industry")
READINGS = ("one", "lw", "fp", "lw_faded")
Json = dict[str, object]


@dataclass(frozen=True)
class Ols:
    beta: float        # the slope, winsorised
    se: float          # its standard error
    days: int


@dataclass
class Betas:
    """One name at one June: its estimates at the date and its realised `ols` in the years after."""
    ticker: str
    year: int
    ols: Ols
    vck: float
    lw: float
    fp: float | None
    industry: float | None
    ahead: dict[int, float] = field(default_factory=lambda: {})   # years ahead -> ols over that year

    def estimate(self, name: str) -> float | None:
        if name == "one":
            return 1.0
        if name == "ols":
            return self.ols.beta
        return cast(float | None, getattr(self, name))


def ols_of(stock: dict[str, float], market: dict[str, float]) -> Ols | None:
    """The slope of the stock's daily return on the market's of the same day, with its
    standard error; None under MIN_DAYS days carrying both or where the market does not move."""
    days = [d for d in stock if d in market]
    if len(days) < MIN_DAYS:
        return None
    x = np.asarray([market[d] for d in days], dtype=float)
    y = np.asarray([stock[d] for d in days], dtype=float)
    sxx = float(((x - x.mean()) ** 2).sum())
    if sxx <= 0:
        return None
    beta = float(((x - x.mean()) * (y - y.mean())).sum()) / sxx
    residual = y - (y.mean() - beta * x.mean()) - beta * x
    se = math.sqrt(float((residual ** 2).sum()) / (len(days) - 2) / sxx)
    return Ols(beta=min(max(beta, WINSOR[0]), WINSOR[1]), se=se, days=len(days))


def vasicek(own: Ols, mean: float, sd: float) -> float:
    """The slope weighted by the cross-section's variance against its own squared standard
    error, the rest on the cross-sectional mean: a precise slope keeps itself, a noisy one
    moves to the mean."""
    weight = sd ** 2 / (sd ** 2 + own.se ** 2) if sd > 0 or own.se > 0 else 1.0
    return weight * own.beta + (1 - weight) * mean


def levi_welch(vck: float) -> float:
    return (1 - SECOND_SHRINK) * vck + SECOND_SHRINK * TARGET


def faded(beta: float) -> float:
    return 1.0 + FADE * (beta - 1.0)


def industry_betas(betas: dict[str, float], codes: dict[str, int | None]) -> dict[str, float]:
    """ticker -> the mean beta of the other names sharing its two-digit industry code, where
    MIN_GROUP others carry one."""
    groups: dict[int, list[tuple[str, float]]] = {}
    for ticker, beta in betas.items():
        sic = codes.get(ticker)
        if sic is not None:
            groups.setdefault(sic // 100, []).append((ticker, beta))
    out: dict[str, float] = {}
    for members in groups.values():
        for ticker, _ in members:
            others = [b for t, b in members if t != ticker]
            if len(others) >= MIN_GROUP:
                out[ticker] = sum(others) / len(others)
    return out


def load_codes(universe_dir: Path, d: str) -> dict[str, int | None]:
    path = universe_dir / f"{d}.json"
    if not path.exists():
        return {}
    return {str(e["ticker"]): (int(cast(int, e["sic"])) if e.get("sic") is not None else None) for e in cast(list[Json], json.loads(path.read_text()))}


def betas_of(panel: Path, histories: Path, benchmark: ps.Daily, universe_dir: Path) -> tuple[list[Betas], int]:
    """(one entry per panel name and June carrying an `ols` at the date, the count that did not)."""
    market_days = sorted(benchmark)
    market = ps.daily_returns(benchmark, "0000", "9999")
    by_date: dict[str, list[Json]] = {}
    for line in panel.read_text().splitlines():
        if line.strip():
            raw = cast(Json, json.loads(line))
            by_date.setdefault(str(raw["date"]), []).append(raw)
    cache: dict[str, ps.Daily | None] = {}
    out: list[Betas] = []
    without = 0
    for d in sorted(by_date):
        year = int(d[:4])
        codes = load_codes(universe_dir, d)
        own: dict[str, tuple[Ols, float | None, dict[int, float]]] = {}
        for raw in by_date[d]:
            ticker = str(raw["ticker"])
            if ticker not in cache:
                cache[ticker] = ps.load_daily(histories / f"{ticker}.json")
            closes = cache[ticker]
            if closes is None:
                without += 1
                continue
            first, last = ps.window(year, d, 0)
            returns = ps.daily_returns(closes, first, last)
            ols = ols_of(returns, market)
            if ols is None:
                without += 1
                continue
            fp = rb.beta_of(returns, market_days, market)
            ahead: dict[int, float] = {}
            for k in range(1, HORIZONS + 1):
                later = ols_of(ps.daily_returns(closes, *ps.window(year, d, k)), market)
                if later is not None:
                    ahead[k] = later.beta
            own[ticker] = (ols, fp, ahead)
        if not own:
            continue
        slopes = [o.beta for o, _, _ in own.values()]
        mean, sd = statistics.mean(slopes), (statistics.pstdev(slopes) if len(slopes) > 1 else 0.0)
        by_industry = industry_betas({t: o.beta for t, (o, _, _) in own.items()}, codes)
        for ticker, (ols, fp, ahead) in sorted(own.items()):
            vck = vasicek(ols, mean, sd)
            out.append(Betas(ticker=ticker, year=year, ols=ols, vck=vck, lw=levi_welch(vck), fp=fp, industry=by_industry.get(ticker), ahead=ahead))
    return out, without


def forecast_block(rows: list[Betas]) -> list[str]:
    lines = ["which beta forecasts next year's: the name's plain slope over the twelve months after the date, on each estimate at the date",
             "-" * 100,
             f"  {'estimate':<10} {'pairs':>6}   as it is: R2    rmse   fitted: intercept  slope   R2"]
    for name in ESTIMATORS:
        pairs = [(e, r.ahead[1]) for r in rows if 1 in r.ahead and (e := r.estimate(name)) is not None]
        f = ps.forecast([x for x, _ in pairs], [y for _, y in pairs])
        if f is None:
            lines.append(f"  {name:<10} {len(pairs):>6}   fewer than {ps.MIN_PAIRS} pairs")
            continue
        lines.append(f"  {name:<10} {f.pairs:>6}   {100 * f.r2_as_is + 0.0:>13.1f}%  {f.rmse_as_is:.3f}   {f.intercept + 0.0:>17.2f}  {f.slope + 0.0:>5.2f}  {100 * f.r2_fitted + 0.0:.1f}%")
    sd = statistics.pstdev([r.ahead[1] for r in rows if 1 in r.ahead]) if sum(1 for r in rows if 1 in r.ahead) > 1 else 0.0
    lines.append(f"  the targets' standard deviation, the error of a constant: {sd:.3f}")
    lines += ["", "the horizon: the plain slope one to five years ahead on today's vck", "-" * 100]
    for k in range(1, HORIZONS + 1):
        pairs = [(r.vck, r.ahead[k]) for r in rows if k in r.ahead]
        f = ps.forecast([x for x, _ in pairs], [y for _, y in pairs])
        lines.append(f"  {k} year(s) ahead: " + (f"fewer than {ps.MIN_PAIRS} pairs" if f is None else f"{f.pairs} pairs, slope {f.slope + 0.0:.2f}, intercept {f.intercept + 0.0:.2f}, R2 {100 * f.r2_fitted + 0.0:.1f}%"))
    return lines


def reading_beta(b: Betas, reading: str) -> float | None:
    if reading == "one":
        return 1.0
    if reading == "lw":
        return b.lw
    if reading == "fp":
        return b.fp
    if reading == "lw_faded":
        return faded(b.lw)
    raise ValueError(reading)


def reading_inputs(pit_dir: Path, target: Path, d: str, betas: dict[str, float], reading: str) -> tuple[Path, Path]:
    """A copy of a point-in-time directory in which every name carrying a beta has its
    industry set to its own ticker, and whose reference carries a beta table of the date
    keyed the same way; (the records' directory, the reference directory). Everything else
    as it was."""
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(pit_dir, target)
    for path in sorted(target.glob("*.json")):
        ticker = path.stem
        if ticker in betas:
            record = cast(Json, json.loads(path.read_text()))
            record["industry"] = ticker
            path.write_text(json.dumps(record))
    reference = target / "reference"
    (reference / "industry_betas.json").write_text(json.dumps({
        "source": f"the rule panel's own per-name beta, reading {reading}, from the year of daily returns to {d} (python/rule_betas.py)",
        "as_of": d, "max_age_days": 400,
        "notes": ["keyed on the ticker, which the record carries as its industry for this reading; a study input, never on the valuation path"],
        "values": betas}, indent=1) + "\n")
    return target, reference


def date_line(d: str, readings: dict[str, list[Json]]) -> str:
    base = {str(r["ticker"]): r for r in readings["one"]}
    cells: list[str] = []
    for name in READINGS:
        records = readings[name]
        margins = [(str(r["ticker"]), m) for r in records if r["status"] == "Ok" and (m := study.as_float(r.get("margin_of_safety"))) is not None]
        if not margins:
            cells.append(f"{name}: none valued")
            continue
        cell = f"{name}: {len(margins)} valued, median margin {statistics.median(m for _, m in margins):+.2f}"
        if name != "one":
            pairs = [(m, bm) for t, m in margins if (b := base.get(t)) is not None and b["status"] == "Ok" and (bm := study.as_float(b.get("margin_of_safety"))) is not None]
            logs = [math.log(fv / bfv) for r in records if r["status"] == "Ok" and (fv := study.as_float(r.get("fair_value"))) and fv > 0
                    and (b := base.get(str(r["ticker"]))) is not None and (bfv := study.as_float(b.get("fair_value"))) and bfv > 0]
            changed = sum(1 for r in records if (b := base.get(str(r["ticker"]))) is not None and (r["status"] == "Ok") != (b["status"] == "Ok"))
            rho = ps.spearman(pairs)
            cell += (f", rank correlation with one {rho:+.2f}" if rho is not None else ", rank correlation with one n/a") + \
                    (f", median fair value {100 * statistics.median(logs) + 0.0:+.1f}% of one's" if logs else "") + f", {changed} change status"
        cells.append(cell)
    return f"  {d}:\n" + "\n".join(f"      {c}" for c in cells)


def margin_against_beta(rows_by_reading: dict[str, list[Row]], lw: dict[tuple[str, int], float]) -> list[str]:
    lines = ["the margin against lw beta: the rank correlation within each date, its median over the dates and its range", "-" * 100]
    for name in READINGS:
        rhos: list[float] = []
        for year in sorted({r.year for r in rows_by_reading[name]}):
            pairs = [(lw[(r.ticker, r.year)], r.values["margin_of_safety"]) for r in rows_by_reading[name] if r.year == year and (r.ticker, r.year) in lw]
            rho = ps.spearman(pairs)
            if rho is not None:
                rhos.append(rho)
        lines.append(f"  {name}: " + (f"median {statistics.median(rhos):+.2f} over {len(rhos)} dates, from {min(rhos):+.2f} to {max(rhos):+.2f}" if rhos else "no date with enough rows"))
    return lines


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--panel", type=Path, default=alpha.PANEL)
    parser.add_argument("--prices", type=Path, default=alpha.PRICES)
    parser.add_argument("--rate", type=Path, default=alpha.RATE)
    parser.add_argument("--histories", type=Path, default=rb.HISTORIES)
    parser.add_argument("--universe-dir", type=Path, default=rule_panel.ROOT / "universe")
    parser.add_argument("--pit", type=Path, default=rule_panel.ROOT / "pit")
    parser.add_argument("--binary", type=Path, default=rule_panel.BINARY)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--forecast-only", action="store_true", help="part one alone; the binary is not run")
    args = parser.parse_args(argv)
    panel: Path = args.panel
    histories: Path = args.histories
    out: Path = args.out
    for path, how in ((panel, "run python/rule_panel.py first"), (histories, "run python/rule_panel.py first: it keeps the daily histories"),
                      (args.prices, "run python/broad_panel.py first: it fetches the monthly bars"), (args.rate, "run python/rule_panel.py first: it fills the rate cache")):
        if not path.exists():
            print(f"{path} not built: {how}", file=sys.stderr)
            return 2
    benchmark = ps.load_daily(histories / f"{BENCHMARK}.json")
    if benchmark is None:
        print(f"no daily history for {BENCHMARK} under {histories}: run python/rule_beta.py --fetch-benchmark", file=sys.stderr)
        return 2
    rows, without = betas_of(panel, histories, benchmark, args.universe_dir)
    years = sorted({r.year for r in rows})
    lines = [
        f"Betas on the rule panel: {len(rows)} names and Junes carrying a year of daily returns, {years[0]} to {years[-1]}, on {len({r.ticker for r in rows})} filers; {without} left out under {MIN_DAYS} days.",
        f"Descriptive only, under the rule study's limits. Slopes on {BENCHMARK}'s daily returns over the year to the date, winsorised at {WINSOR[0]:.0f} and {WINSOR[1]:.0f}; "
        f"vck weights the slope by the date's cross-sectional variance against its own squared standard error; lw keeps {1 - SECOND_SHRINK:.2f} of vck and puts {SECOND_SHRINK:.2f} on {TARGET:.0f}; "
        f"fp is the beta study's; industry the mean slope of the other names in the two-digit code, {MIN_GROUP} at least; lw_faded is one plus {FADE:.1f} of lw's deviation from it.",
        "After Levi and Welch, \"Best Practice for Cost-of-Capital Estimates\", Journal of Financial and Quantitative Analysis 52(2), 2017, doi:10.1017/S0022109017000114; "
        "Keloharju, Linnainmaa and Nyberg, \"Long-Term Discount Rates Do Not Vary Across Firms\", NBER Working Paper 25579, February 2019, doi:10.3386/w25579; "
        "and, for fp, Frazzini and Pedersen, \"Betting Against Beta\", NBER Working Paper 16601, December 2010, doi:10.3386/w16601.",
        "",
        *forecast_block(rows), "",
    ]
    print("\n".join(lines), flush=True)
    if not args.forecast_only:
        lines += valuation_blocks(rows, args, out)
    text = "\n".join(lines)
    out.mkdir(parents=True, exist_ok=True)
    (out / "tables.txt").write_text(text)
    (out / "betas.jsonl").write_text("".join(json.dumps({"ticker": r.ticker, "year": r.year, "ols": r.ols.beta, "se": r.ols.se, "days": r.ols.days, "vck": r.vck, "lw": r.lw,
                                                          "fp": r.fp, "industry": r.industry, "ahead": r.ahead}) + "\n" for r in rows))
    return 0


def valuation_blocks(rows: list[Betas], args: argparse.Namespace, out: Path) -> list[str]:
    pit_root: Path = args.pit
    binary: Path = args.binary
    forward: dict[tuple[str, str], float] = {}
    caps: dict[tuple[str, str], float | None] = {}
    for line in cast(Path, args.panel).read_text().splitlines():
        if line.strip():
            raw = cast(Json, json.loads(line))
            key = (str(raw["ticker"]), str(raw["date"]))
            f, s = study.as_float(raw.get("forward_12m")), study.as_float(raw.get("spy_12m"))
            if f is not None and s is not None:
                forward[key] = f - s
            caps[key] = study.as_float(raw.get("market_cap"))
    by_key = {(r.ticker, r.year): r for r in rows}
    lines = ["the fair values under each reading of beta, by date; a name without a year of daily returns stays at one under every reading", "-" * 100]
    rows_by_reading: dict[str, list[Row]] = {name: [] for name in READINGS}
    for pit_dir in sorted(p for p in pit_root.iterdir() if p.is_dir()):
        d = pit_dir.name
        year = int(d[:4])
        universe = cast(Path, args.universe_dir) / f"{d}.study.json"
        readings: dict[str, list[Json]] = {}
        for name in READINGS:
            betas = {t: b for (t, y), r in by_key.items() if y == year and (b := reading_beta(r, name)) is not None}
            records_dir, reference_dir = reading_inputs(pit_dir, out / "pit" / name / d, d, betas, name)
            readings[name] = variants.run_variant(binary, records_dir, universe, reference_dir, d, out / name / d)
            shutil.rmtree(records_dir)
            for r in readings[name]:
                m = study.as_float(r.get("margin_of_safety"))
                if r["status"] == "Ok" and m is not None:
                    key = (str(r["ticker"]), d)
                    rows_by_reading[name].append(Row(ticker=str(r["ticker"]), year=year, excess=forward.get(key), non_financial=True, values={"margin_of_safety": m}, cap=caps.get(key)))
        lines.append(date_line(d, readings))
        print(lines[-1], flush=True)
    lines.append("")
    lines += margin_against_beta(rows_by_reading, {k: r.lw for k, r in by_key.items()}) + [""]
    adjusted = alpha.load_adjusted(cast(Path, args.prices))
    market = {m: r for m in adjusted.get(BENCHMARK, {}) if (r := alpha.monthly_return(adjusted[BENCHMARK], m)) is not None}
    rate = alpha.load_rate(cast(Path, args.rate))
    for name in READINGS:
        for label, before in ((f"formations before {SPLIT_YEAR}", True), (f"formations from {SPLIT_YEAR}", False)):
            lines += broad.measure_block([r for r in rows_by_reading[name] if (r.year < SPLIT_YEAR) == before and r.excess is not None], "margin_of_safety", f"{name}, {label}") + [""]
        for capped_value in (False, True):
            lines += alpha.measure_block(rows_by_reading[name], "margin_of_safety", adjusted, market, rate, f"{name}, all formations", capped_value=capped_value) + [""]
    return lines


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
