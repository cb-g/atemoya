"""Rate variants on the rule panel: how much of the anchor's level is the model and how much the vintage.

    uv run python/rule_variants.py [--out output/rule_variants]

The rule study found the median margin of safety on a date above one in the low-rate years
and below zero since 2023. Two things could do that. The discount rate follows the
risk-free rate while the terminal growth is one figure per country, so the gap between them
closes when rates fall. And the point-in-time path values past dates with the current
equity risk premium, a 2026 vintage, where a reader at the time had a higher one.

This reruns the binary on the rule panel's own point-in-time records, the statements and
prices untouched, under four parameter sets per date, and reads the level and the sort:

- `baseline`: as the rule panel ran.
- `growth_capped`: the United States' terminal growth held to the date's risk-free rate at
  the projection tenor where that is lower, the convention that a company cannot outgrow
  the economy for ever and the risk-free rate is the market's own reading of nominal growth.
- `premium_vintage`: the United States' equity risk premium replaced by the implied premium
  at the end of the year before the date (reference/erp_history.json).
- `both`.

Contract. Prints, per date, the rates used and each variant's count valued, count refused
at the sanity bound and median margin of safety; then for each variant the cheapest fifth's
median twelve-month excess less the dearest's on its valued rows, within the date, before
SPLIT_YEAR and from it, with the years it was positive. Writes the same to
`<out>/tables.txt` and each variant's records under `<out>/<variant>/<date>/`.

Descriptive only, under the rule study's limits. A variant is a question put to the model,
not a change to it: nothing here moves a parameter file or a record on the valuation path."""

from __future__ import annotations

import argparse
import json
import shutil
import statistics
import subprocess
import sys
from pathlib import Path
from typing import cast

import anchor_study as study
import broad_study as broad
import rule_panel
from broad_study import Row

OUT = study.REPO_ROOT / "output" / "rule_variants"
ERP_HISTORY = study.REPO_ROOT / "reference" / "erp_history.json"
COUNTRY = "United States"
VARIANTS = ("baseline", "growth_capped", "premium_vintage", "both")
SPLIT_YEAR = broad.SPLIT_YEAR
Json = dict[str, object]


def premium_for(year: int, history: dict[str, float]) -> float | None:
    """The implied premium a reader had on 30 June of [year]: the one at the end of the year before."""
    return history.get(str(year - 1))


def variant_reference(source: Path, target: Path, *, growth: float | None, premium: float | None) -> None:
    """A copy of a point-in-time reference directory with the United States' terminal growth
    and equity risk premium replaced where given; every other file and value as it was."""
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    if growth is not None:
        path = target / "params.json"
        params = cast(Json, json.loads(path.read_text()))
        cast(dict[str, float], cast(Json, params["terminal_growth_rate"])["values"])[COUNTRY] = growth
        path.write_text(json.dumps(params, indent=2) + "\n")
    if premium is not None:
        path = target / "equity_risk_premiums.json"
        table = cast(Json, json.loads(path.read_text()))
        cast(dict[str, float], table["values"])[COUNTRY] = premium
        path.write_text(json.dumps(table, indent=2) + "\n")


def rates_on(reference_dir: Path) -> tuple[float, float, float, str]:
    """(risk-free at the projection tenor, table terminal growth, table premium, tenor) on the date."""
    params = cast(Json, json.loads((reference_dir / "params.json").read_text()))
    tenor = f"{cast(Json, params['projection_years'])['value']}y"
    growth = cast(dict[str, float], cast(Json, params["terminal_growth_rate"])["values"])[COUNTRY]
    curves = cast(Json, json.loads((reference_dir / "risk_free_rates.json").read_text()))
    rf = cast(dict[str, float], cast(Json, cast(Json, curves["countries"])[COUNTRY])["rates"])[tenor]
    premium = cast(dict[str, float], cast(Json, json.loads((reference_dir / "equity_risk_premiums.json").read_text()))["values"])[COUNTRY]
    return rf, growth, premium, tenor


def run_variant(binary: Path, pit_dir: Path, universe: Path, reference_dir: Path, d: str, out: Path) -> list[Json]:
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(binary), str(pit_dir), "--reference", str(reference_dir), "--fetched", str(reference_dir), "--today", d,
                    "--universe", str(universe), "--out", str(out)], check=True, capture_output=True, cwd=study.REPO_ROOT)
    return [cast(Json, json.loads(line)) for line in (out / "valuations.jsonl").read_text().splitlines() if line.strip()]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--binary", type=Path, default=rule_panel.BINARY)
    args = parser.parse_args(argv)
    out: Path = args.out
    binary: Path = args.binary
    pit_root = rule_panel.ROOT / "pit"
    panel_path = rule_panel.ROOT / "panel.jsonl"
    if not panel_path.exists():
        print(f"{panel_path} not built: run python/rule_panel.py first", file=sys.stderr)
        return 2
    history = cast(dict[str, float], json.loads(ERP_HISTORY.read_text())["implied_premium_at_year_end"])
    forward: dict[tuple[str, str], float] = {}
    for line in panel_path.read_text().splitlines():
        if line.strip():
            raw = cast(Json, json.loads(line))
            f, s = study.as_float(raw.get("forward_12m")), study.as_float(raw.get("spy_12m"))
            if f is not None and s is not None:
                forward[(str(raw["ticker"]), str(raw["date"]))] = f - s
    rows: dict[str, list[Row]] = {v: [] for v in VARIANTS}
    lines = ["Rate variants on the rule panel. Descriptive only; a variant is a question put to the model, not a change to it.", "",
             "by date: risk-free rate at the projection tenor, the table's terminal growth and premium, the premium of the date's vintage; then per variant the count valued, the count refused at the sanity bound and the median margin of safety",
             "-" * 100]
    for pit_dir in sorted(p for p in pit_root.iterdir() if p.is_dir()):
        d = pit_dir.name
        universe = rule_panel.ROOT / "universe" / f"{d}.study.json"
        rf, growth, premium, tenor = rates_on(pit_dir / "reference")
        vintage = premium_for(int(d[:4]), history)
        capped = min(growth, rf)
        cells: list[str] = []
        for variant in VARIANTS:
            reference_dir = out / "reference" / variant / d
            variant_reference(pit_dir / "reference", reference_dir,
                              growth=capped if variant in ("growth_capped", "both") else None,
                              premium=vintage if variant in ("premium_vintage", "both") else None)
            records = run_variant(binary, pit_dir, universe, reference_dir, d, out / variant / d)
            margins = [m for r in records if r["status"] == "Ok" and (m := study.as_float(r.get("margin_of_safety"))) is not None]
            bound = sum(1 for r in records if "sanity bound" in str(r.get("failed_reason") or ""))
            cells.append(f"{variant} {len(margins)} valued, {bound} at the bound, median {statistics.median(margins):+.2f}" if margins else f"{variant} none valued")
            for r in records:
                m = study.as_float(r.get("margin_of_safety"))
                if r["status"] == "Ok" and m is not None:
                    rows[variant].append(Row(ticker=str(r["ticker"]), year=int(d[:4]), excess=forward.get((str(r["ticker"]), d)),
                                             non_financial=True, values={"margin_of_safety": m}))
        lines.append(f"  {d}: rf {tenor} {rf:.2%}, growth {growth:.2%}, premium {premium:.2%}, vintage premium {'n/a' if vintage is None else f'{vintage:.2%}'}")
        lines += [f"      {c}" for c in cells]
        print(lines[-5], flush=True)
    lines.append("")
    for variant in VARIANTS:
        for label, before in ((f"formations before {SPLIT_YEAR}", True), (f"formations from {SPLIT_YEAR}", False)):
            lines += broad.measure_block([r for r in rows[variant] if (r.year < SPLIT_YEAR) == before and r.excess is not None], "margin_of_safety", f"{variant}, {label}") + [""]
    text = "\n".join(lines)
    (out / "tables.txt").write_text(text)
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
