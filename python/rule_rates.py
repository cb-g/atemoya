"""The rule panel under shifted rates: how far a fair value moves per point of the risk-free rate.

    uv run python/rule_rates.py [--shift 0.005] [--pass-through 0.35] [--out output/rule_rates]

The rule study found the median margin of safety on a date running from well above zero in
the low-rate years to below it since 2023. The discount rate follows the risk-free rate, so
the model treats every move in the rate as a move in what the future is worth. Whether the
market does the same is measured in Gormsen and Lazarus, "Interest Rates and Equity
Valuations", NBER Working Paper 34814, February 2026, doi:10.3386/w34814: a change in the
trend real rate is a change in time preference, in expected growth or in risk, and only the
first moves equity prices by their cash-flow duration (their Result 2); three-year US market
returns load about -19 on a point of that pure-discounting part and insignificantly on a
point of the raw ten-year yield (their Table 2), and the pure-discounting part was under
half of the fall in the real rate over 1990-2023 (their Table 4).

This reruns the binary on the rule panel's own point-in-time records, statements and
prices untouched, under three readings of the United States curve per date:

- `as run`;
- `up` and `down`: every tenor of the curve shifted by SHIFT either way, the terminal
  growth held to the shifted rate as the model holds it; the elasticity of a fair value is
  the difference of its logs over the difference in the rate, per point, on the records
  valued under both, and its sign changed is the duration the model gives the name;
- `pass-through`: the curve replaced by its mean over the panel's dates plus PASS_THROUGH
  of the date's distance from that mean, the question being what the level and the sort
  would have been had the model taken a part of each rate move for pure discounting rather
  than all of it.

Prints, per date, the rate as run, the median and quartiles of the elasticity, the records
valued under both shifts and the count that change status under either, and the
pass-through reading's rate, count valued and median margin; then the sort under the
pass-through reading, cheapest fifth less dearest, before SPLIT_YEAR and from it.

Descriptive only, under the rule study's limits. A variant is a question put to the model,
not a change to it: nothing here moves a parameter file or a record on the valuation path."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import statistics
import sys
from pathlib import Path
from typing import cast

import anchor_study as study
import broad_study as broad
import rule_panel
import rule_variants as variants
from broad_study import Row

OUT = study.REPO_ROOT / "output" / "rule_rates"
COUNTRY = variants.COUNTRY
SPLIT_YEAR = broad.SPLIT_YEAR
SHIFT = 0.005            # half a point either way: a point between the two readings
PASS_THROUGH = 0.35      # the paper's share of the US real-rate fall that was pure discounting, 1990-2023
Json = dict[str, object]


def shifted_reference(source: Path, target: Path, *, by: float | None = None, to: float | None = None) -> None:
    """A copy of a point-in-time reference directory with the United States curve moved:
    every tenor by [by], or every tenor to the value [to] plus its own distance from the
    projection tenor's rate, so the curve keeps its shape around the new level."""
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    path = target / "risk_free_rates.json"
    curves = cast(Json, json.loads(path.read_text()))
    rates = cast(dict[str, float], cast(Json, cast(Json, curves["countries"])[COUNTRY])["rates"])
    if to is not None:
        tenor = variants.rates_on(source)[3]
        by = to - rates[tenor]
    for tenor_name in list(rates):
        rates[tenor_name] = rates[tenor_name] + (by or 0.0)
    path.write_text(json.dumps(curves, indent=2) + "\n")


def elasticities(up: list[Json], down: list[Json], shift: float) -> tuple[list[float], int]:
    """Per record valued under both readings, d ln(fair value) / d rate per point; and the
    count of records whose status differs between the two."""
    by_ticker_up = {str(r["ticker"]): r for r in up}
    out: list[float] = []
    changed = 0
    for r in down:
        u = by_ticker_up.get(str(r["ticker"]))
        if u is None:
            continue
        if (r["status"] == "Ok") != (u["status"] == "Ok"):
            changed += 1
            continue
        a, b = study.as_float(r.get("fair_value")), study.as_float(u.get("fair_value"))
        if a is not None and b is not None and a > 0 and b > 0:
            out.append((math.log(b) - math.log(a)) / (2 * shift) / 100)   # per point of rate, as a fraction of value
    return out, changed


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--binary", type=Path, default=rule_panel.BINARY)
    parser.add_argument("--shift", type=float, default=SHIFT)
    parser.add_argument("--pass-through", type=float, default=PASS_THROUGH)
    args = parser.parse_args(argv)
    out: Path = args.out
    binary: Path = args.binary
    shift: float = args.shift
    share: float = args.pass_through
    pit_root = rule_panel.ROOT / "pit"
    panel_path = rule_panel.ROOT / "panel.jsonl"
    if not panel_path.exists():
        print(f"{panel_path} not built: run python/rule_panel.py first", file=sys.stderr)
        return 2
    forward: dict[tuple[str, str], float] = {}
    for line in panel_path.read_text().splitlines():
        if line.strip():
            raw = cast(Json, json.loads(line))
            f, s = study.as_float(raw.get("forward_12m")), study.as_float(raw.get("spy_12m"))
            if f is not None and s is not None:
                forward[(str(raw["ticker"]), str(raw["date"]))] = f - s
    dates = sorted(p for p in pit_root.iterdir() if p.is_dir())
    rf_by_date = {p.name: variants.rates_on(p / "reference")[0] for p in dates}
    mean_rf = statistics.mean(rf_by_date.values())
    lines = [
        f"The rule panel under shifted rates. Descriptive only; a variant is a question put to the model, not a change to it. Shift {shift:.2%} either way; "
        f"pass-through {share:.0%} of each date's distance from the mean rate of {mean_rf:.2%} at the projection tenor over {len(dates)} dates.",
        "After Gormsen and Lazarus, \"Interest Rates and Equity Valuations\", NBER Working Paper 34814, February 2026, doi:10.3386/w34814.",
        "",
        "by date: the rate as run; the elasticity of a fair value per point of rate (median, quartiles) on the records valued under both shifts, and the count whose status differs between them; "
        "then the pass-through reading's rate, count valued and median margin of safety beside the run's",
        "-" * 100,
    ]
    rows: list[Row] = []
    base_rows: list[Row] = []
    for pit_dir in dates:
        d = pit_dir.name
        universe = rule_panel.ROOT / "universe" / f"{d}.study.json"
        rf = rf_by_date[d]
        readings: dict[str, list[Json]] = {}
        for name, by, to in (("as_run", None, None), ("up", shift, None), ("down", -shift, None), ("pass_through", None, mean_rf + share * (rf - mean_rf))):
            reference_dir = out / "reference" / name / d
            shifted_reference(pit_dir / "reference", reference_dir, by=by, to=to)
            readings[name] = variants.run_variant(binary, pit_dir, universe, reference_dir, d, out / name / d)
        e, changed = elasticities(readings["up"], readings["down"], shift)
        for name, store in (("as_run", base_rows), ("pass_through", rows)):
            for r in readings[name]:
                m = study.as_float(r.get("margin_of_safety"))
                if r["status"] == "Ok" and m is not None:
                    store.append(Row(ticker=str(r["ticker"]), year=int(d[:4]), excess=forward.get((str(r["ticker"]), d)), non_financial=True, values={"margin_of_safety": m}))
        def median_margin(records: list[Json]) -> str:
            ms = [m for r in records if r["status"] == "Ok" and (m := study.as_float(r.get("margin_of_safety"))) is not None]
            return f"{len(ms)} valued, median margin {statistics.median(ms):+.2f}" if ms else "none valued"
        q = statistics.quantiles(e, n=4) if len(e) >= 4 else None
        lines.append(f"  {d}: rate {rf:.2%}; elasticity per point"
                     + (f" median {100 * statistics.median(e):+.1f}%, quartiles {100 * q[0]:+.1f}% to {100 * q[2]:+.1f}% on {len(e)} records" if q else f" on {len(e)} records")
                     + f", {changed} change status between the shifts; pass-through rate {mean_rf + share * (rf - mean_rf):.2%}: {median_margin(readings['pass_through'])}; as run: {median_margin(readings['as_run'])}")
        print(lines[-1], flush=True)
    lines.append("")
    lines.append("The paper's benchmarks, per point of rate: about -19% for the part that is pure discounting (its Table 2, three-year US market returns), about nothing for a change in the raw ten-year yield; "
                 "a model whose discount rate follows the rate one-for-one carries its full duration against every move.")
    lines.append("")
    for label, before in ((f"formations before {SPLIT_YEAR}", True), (f"formations from {SPLIT_YEAR}", False)):
        lines += broad.measure_block([r for r in base_rows if (r.year < SPLIT_YEAR) == before and r.excess is not None], "margin_of_safety", f"as run, {label}") + [""]
        lines += broad.measure_block([r for r in rows if (r.year < SPLIT_YEAR) == before and r.excess is not None], "margin_of_safety", f"pass-through, {label}") + [""]
    text = "\n".join(lines)
    out.mkdir(parents=True, exist_ok=True)
    (out / "tables.txt").write_text(text)
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
