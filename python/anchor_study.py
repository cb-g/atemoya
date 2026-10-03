"""The anchor study (80): what the records' own judgments preceded.

    uv run python/anchor_study.py [--panel output/pit/panel.jsonl] [--as-of YYYY-MM-DD] [--out output/anchor_study]

Every brief so far verified inputs against filings. This asks about the outputs: for every
(name, quarter-end) row of the point-in-time panel, valued on that date from what was known
then, what the price did afterwards against SPY over the same dates, at one quarter, half a
year and a year of trading days. Then the rows are grouped by what the record said on the
day: Ok or refused; the signal; the margin of safety, in quintiles within each date so the
market's own move that quarter does not masquerade as the anchor's; the belief's
probability_overpaid where a belief existed; the class, the model, and for the refusals the
family of the reason, by class, a gate, or the point-in-time path's own absences.

**Descriptive only.** Medians, quartiles, counts and the share positive; no statistic the
sample can carry, since a hundred and seventy-eight names on eighteen quarter-ends move
together with the market and are not eighteen hundred independent tests. A cell of fewer
than MIN_CELL rows prints its count and nothing else. Nothing here feeds a model, a belief
or a signal; a finding is a finding and the reader judges.

Determinism: the closes are read once per name, cut at --as-of, and cached under
data/anchor_study/ (gitignored), because the current day's close is still forming and two
runs an hour apart would otherwise disagree at the horizons that reach it. Delete the
directory to re-fetch."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parents[1]
PANEL = REPO_ROOT / "output" / "pit" / "panel.jsonl"
PIT_OUT = REPO_ROOT / "output" / "pit"
OUT = REPO_ROOT / "output" / "anchor_study"
CACHE = REPO_ROOT / "data" / "anchor_study" / "closes"
BENCHMARK = "SPY"
HORIZONS = (63, 126, 252)   # trading days: a quarter, a half year, a year
MIN_CELL = 10               # below this a cell is a count, never a median
FAMILIES = ("by class", "gate", "point-in-time")
HOLDOUT = REPO_ROOT / "reference" / "holdout.json"
PO_BUCKETS = (("below 0.25", 0.0, 0.25), ("0.25 to 0.75", 0.25, 0.75), ("0.75 and above", 0.75, 1.0000001))


@dataclass
class Record:
    ticker: str
    as_of: str
    status: str
    entity_class: str | None
    model: str | None
    fair_value: float | None
    price: float | None
    margin_of_safety: float | None
    signal: str | None
    probability_overpaid: float | None
    failed_reason: str | None
    family: str | None                      # for a refusal: by class | gate | point-in-time
    price_date: str | None
    forward: dict[str, float | None] = field(default_factory=lambda: {})
    benchmark: dict[str, float | None] = field(default_factory=lambda: {})
    excess: dict[str, float | None] = field(default_factory=lambda: {})
    mos_quintile: int | None = None         # within the date, 1 = the lowest margin of safety, 5 = the highest
    forward_reason: str | None = None       # why a horizon is null: history short, or the window past the last close


def family_of(reason: str | None) -> str | None:
    """A refusal's family: the class text refusing by design, the point-in-time path's own
    absences (no statements filed by the date, no shares), or a gate the record met."""
    if reason is None:
        return None
    if reason.startswith("dcf not admissible") or "not admissible for" in reason:
        return "by class"
    if reason.startswith("no point-in-time"):
        return "point-in-time"
    return "gate"


def as_float(v: object) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def load_panel(path: Path, pit_out: Path) -> list[Record]:
    """One record per panel row, with the class and the model joined from the date's own
    valuations file, since the panel row carries neither."""
    by_date: dict[str, dict[str, tuple[str | None, str | None]]] = {}
    out: list[Record] = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        r = cast(dict[str, object], json.loads(line))
        d = str(r["as_of"])
        if d not in by_date:
            by_date[d] = {}
            vals = pit_out / d / "valuations.jsonl"
            if vals.exists():
                for vline in vals.read_text().splitlines():
                    if vline.strip():
                        v = cast(dict[str, object], json.loads(vline))
                        by_date[d][str(v["ticker"])] = (cast(str | None, v.get("entity_class")), cast(str | None, v.get("model")))
        entity_class, model = by_date[d].get(str(r["ticker"]), (None, None))
        reason = cast(str | None, r.get("failed_reason"))
        out.append(Record(
            ticker=str(r["ticker"]), as_of=d, status=str(r["status"]), entity_class=entity_class, model=model,
            fair_value=as_float(r.get("fair_value")), price=as_float(r.get("price")), margin_of_safety=as_float(r.get("margin_of_safety")),
            signal=cast(str | None, r.get("signal")), probability_overpaid=as_float(r.get("probability_overpaid")),
            failed_reason=reason, family=family_of(reason) if str(r["status"]) == "Failed" else None,
            price_date=cast(str | None, r.get("price_date"))))
    return out


@dataclass(frozen=True)
class Holdout:
    """reference/holdout.json: the names and the dates put aside before the models change."""
    names: frozenset[str]
    dates_after: str

    def holds(self, ticker: str, as_of: str) -> bool:
        return ticker in self.names or as_of > self.dates_after


def load_holdout(path: Path = HOLDOUT) -> Holdout:
    raw = cast(dict[str, object], json.loads(path.read_text()))
    return Holdout(names=frozenset(cast(list[str], raw["names"])), dates_after=str(raw["dates_after"]))


def set_aside(records: list[Record], holdout: Holdout, *, opened: bool) -> tuple[list[Record], str]:
    """The rows the study may read and the line that says what was put aside. A study never
    reads a held-out row unless it is run with --holdout, and then it says so first."""
    held = [r for r in records if holdout.holds(r.ticker, r.as_of)]
    if opened:
        return records, f"HOLDOUT OPENED: {len(held)} held-out rows on {len({r.ticker for r in held})} names are in the tables below; record the opening in reference/holdout.json."
    kept = [r for r in records if not holdout.holds(r.ticker, r.as_of)]
    return kept, f"Holdout (reference/holdout.json): {len(held)} rows set aside, {len(holdout.names)} names and every date after {holdout.dates_after}; not read."


# --- closes and forward returns ------------------------------------------------------------

def closes_of(ticker: str, as_of: date, *, cache: Path = CACHE) -> dict[date, float]:
    """The vendor's closes to [as_of], fetched once and then read from disk (see the module
    docstring on why the cut matters)."""
    import pit  # noqa: PLC0415

    path = cache / f"{ticker}-{as_of.isoformat()}.json"
    if path.exists():
        stored = cast(dict[str, float], json.loads(path.read_text()))
        return {date.fromisoformat(d): v for d, v in stored.items()}
    h = pit.History.fetch(ticker)
    closes = {d: c for d, c in h.closes.items() if d <= as_of}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({d.isoformat(): closes[d] for d in sorted(closes)}, sort_keys=True))
    return closes


def start_index(days: list[date], on_or_before: date, *, lookback_days: int = 10) -> int | None:
    """The index of the last trading day on or before the date, within a short lookback;
    None when the history does not reach the date."""
    candidates = [i for i, d in enumerate(days) if d <= on_or_before and (on_or_before - d).days <= lookback_days]
    return max(candidates) if candidates else None


def forward_return(closes: dict[date, float], start: date, horizon: int) -> tuple[float | None, date | None]:
    """The simple return from the last close on or before [start] to the close [horizon]
    trading days later, and that later day; (None, None) where the window runs past the last
    close, never a shortened horizon."""
    days = sorted(closes)
    i = start_index(days, start)
    if i is None:
        return None, None
    j = i + horizon
    if j >= len(days) or closes[days[i]] <= 0:
        return None, None
    return closes[days[j]] / closes[days[i]] - 1.0, days[j]


def benchmark_return(closes: dict[date, float], start: date, end: date) -> float | None:
    """The benchmark's return between the same two calendar dates, each taken as the last
    close on or before it, so a foreign name's holidays do not misalign the two legs."""
    days = sorted(closes)
    i, j = start_index(days, start), start_index(days, end)
    if i is None or j is None or closes[days[i]] <= 0:
        return None
    return closes[days[j]] / closes[days[i]] - 1.0


def attach_forward(records: list[Record], as_of: date, *, cache: Path = CACHE) -> None:
    bench = closes_of(BENCHMARK, as_of, cache=cache)
    by_ticker: dict[str, dict[date, float]] = {}
    for r in records:
        if r.price_date is None:
            r.forward_reason = "no price on the date"
            r.forward = {str(h): None for h in HORIZONS}; r.benchmark = dict(r.forward); r.excess = dict(r.forward)
            continue
        if r.ticker not in by_ticker:
            by_ticker[r.ticker] = closes_of(r.ticker, as_of, cache=cache)
        closes = by_ticker[r.ticker]
        start = date.fromisoformat(r.price_date)
        reasons: list[str] = []
        for h in HORIZONS:
            own, end = forward_return(closes, start, h)
            if own is None or end is None:
                r.forward[str(h)] = None; r.benchmark[str(h)] = None; r.excess[str(h)] = None
                reasons.append(f"+{h}: the window runs past the last close" if start_index(sorted(closes), start) is not None else f"+{h}: no close on the date")
                continue
            b = benchmark_return(bench, start, end)
            r.forward[str(h)] = own
            r.benchmark[str(h)] = b
            r.excess[str(h)] = None if b is None else own - b
        r.forward_reason = "; ".join(reasons) if reasons else None


def assign_quintiles(records: list[Record]) -> None:
    """Within each date, the Ok records with a margin of safety ranked into five groups,
    1 the lowest margin (the most overpriced by the anchor) and 5 the highest; a date with
    fewer than five such records assigns none."""
    by_date: dict[str, list[Record]] = {}
    for r in records:
        if r.status == "Ok" and r.margin_of_safety is not None:
            by_date.setdefault(r.as_of, []).append(r)
    for rows in by_date.values():
        if len(rows) < 5:
            continue
        ordered = sorted(rows, key=lambda r: cast(float, r.margin_of_safety))
        n = len(ordered)
        for k, r in enumerate(ordered):
            r.mos_quintile = min(5, 1 + (k * 5) // n)


# --- the tables --------------------------------------------------------------------------

def quantiles(values: list[float]) -> tuple[float, float, float]:
    ordered = sorted(values)
    q = statistics.quantiles(ordered, n=4, method="inclusive") if len(ordered) >= 2 else [ordered[0], ordered[0], ordered[0]]
    return statistics.median(ordered), q[0], q[2]


def cell(rows: Iterable[Record], horizon: int) -> str:
    values = [x for r in rows if (x := r.excess.get(str(horizon))) is not None]
    if len(values) < MIN_CELL:
        return f"n={len(values)}"
    med, q1, q3 = quantiles(values)
    positive = sum(1 for x in values if x > 0)
    return f"n={len(values)} median {med:+.3f} (IQR {q1:+.3f} to {q3:+.3f}), positive {positive}/{len(values)}"


def block(title: str, groups: list[tuple[str, list[Record]]]) -> list[str]:
    lines = [title, "-" * len(title)]
    for label, rows in groups:
        if not rows:
            continue
        lines.append(f"{label}: {len(rows)} rows on {len({r.ticker for r in rows})} names")
        for h in HORIZONS:
            lines.append(f"  +{h:>3}d excess over {BENCHMARK}: {cell(rows, h)}")
    return lines


def po_bucket(p: float) -> str | None:
    for label, lo, hi in PO_BUCKETS:
        if lo <= p < hi:
            return label
    return None


def sign_agreement(records: list[Record], horizon: int) -> list[str]:
    """Per date and overall: of the Ok rows with a margin of safety and an excess at the
    horizon, how many had the sign of the one match the sign of the other. A count, not a
    hit rate with a claim attached."""
    lines = [f"sign agreement at +{horizon}d: margin of safety and the excess over {BENCHMARK} on the same side",
             "-" * 60]
    total = agree = 0
    for d in sorted({r.as_of for r in records}):
        rows = [r for r in records if r.as_of == d and r.status == "Ok" and r.margin_of_safety is not None and r.excess.get(str(horizon)) is not None]
        if not rows:
            lines.append(f"  {d}: no row reaches the horizon")
            continue
        a = sum(1 for r in rows if (cast(float, r.margin_of_safety) > 0) == (cast(float, r.excess[str(horizon)]) > 0))
        total += len(rows); agree += a
        lines.append(f"  {d}: {a}/{len(rows)}")
    lines.append(f"  all dates: {agree}/{total}" if total else "  all dates: nothing reaches the horizon")
    return lines


def report(records: list[Record], as_of: date, holdout_line: str | None = None) -> str:
    ok = [r for r in records if r.status == "Ok"]
    failed = [r for r in records if r.status == "Failed"]
    dates = sorted({r.as_of for r in records})
    lines = [
        f"The anchor study (80): {len(records)} panel rows, {len({r.ticker for r in records})} names, {len(dates)} quarter-ends {dates[0]} to {dates[-1]}, closes cut at {as_of.isoformat()}.",
        "Descriptive only: counts, medians and quartiles on the sample as it is, the excess over SPY at +63, +126 and +252 trading days from the date's price. No statistic the sample can carry; the names on one date move with the market and are not independent tests. A cell under ten rows is a count alone.",
        *([holdout_line] if holdout_line else []),
        "",
    ]
    lines += block("by status", [("Ok", ok), ("Failed", failed)]) + [""]
    lines += block("Ok rows by signal", [(s, [r for r in ok if r.signal == s]) for s in ("Buy", "Hold", "Sell")]) + [""]
    lines += block("Ok rows by margin-of-safety quintile within the date (1 lowest, 5 highest)",
                   [(f"quintile {q}", [r for r in ok if r.mos_quintile == q]) for q in range(1, 6)]) + [""]
    with_belief = [r for r in ok if r.probability_overpaid is not None]
    lines += block(f"Ok rows by probability_overpaid ({len(with_belief)} rows carry a belief)",
                   [(label, [r for r in with_belief if po_bucket(cast(float, r.probability_overpaid)) == label]) for label, _, _ in PO_BUCKETS]) + [""]
    models = sorted({r.model for r in ok if r.model})
    lines += block("Ok rows by model", [(m, [r for r in ok if r.model == m]) for m in models]) + [""]
    classes = sorted({r.entity_class for r in records if r.entity_class})
    lines += block("all rows by class", [(c, [r for r in records if r.entity_class == c]) for c in classes]) + [""]
    lines += block("refusals by family", [(f, [r for r in failed if r.family == f]) for f in FAMILIES]) + [""]
    lines += sign_agreement(records, 252) + [""]
    lines += sign_agreement(records, 63)
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--panel", type=Path, default=PANEL)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today(), help="the day the closes are cut at; the study repeats byte for byte at the same cut")
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--holdout", action="store_true", help="read the held-out names and dates too; a one-time act, recorded in reference/holdout.json")
    args = parser.parse_args(argv)
    panel: Path = args.panel
    as_of: date = args.as_of
    out: Path = args.out
    opened: bool = args.holdout
    records, holdout_line = set_aside(load_panel(panel, panel.parent), load_holdout(), opened=opened)
    attach_forward(records, as_of)
    assign_quintiles(records)
    out.mkdir(parents=True, exist_ok=True)
    (out / "records.jsonl").write_text("".join(json.dumps(asdict(r), sort_keys=True) + "\n" for r in records))
    text = report(records, as_of, holdout_line)
    (out / "tables.txt").write_text(text)
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
