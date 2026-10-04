"""The watch: what changed between two runs, one line a name.

    uv run python/watch.py [--current output/valuations.jsonl] [--previous output/runs/<date>/valuations.jsonl]

A run writes two hundred records and a sitting wants the dozen that moved. The batch's own
diff (`--baseline`) classifies every moved input, which is for auditing a change to the
code; this is for reading a day: it compares two runs' records and lists, in plain
sections, what a holder would want to see first.

Contract. Reads two valuations files and nothing else; fetches nothing and writes
`output/watch/<valued_on>.txt`. Without --previous it takes the newest archived run under
`output/runs/` valued on an earlier day than the current one. Sections, each a count and
its names, empty ones saying none:

- a ticker that no longer names its declared filer (the identity guard), always first;
- status changed, valued to refused or back, with the reason;
- signal changed;
- the price crossed the fair value, the margin of safety changing sign with both valued;
- a new fiscal year was read, the latest period's end moving;
- the fair value moved by more than FAIR_VALUE_MOVE with no new fiscal year, and the price
  by more than PRICE_MOVE;
- stretch newly at or above three on a side; an insider cluster newly present;
- releases due within RELEASE_DAYS, with the implied move where the run carries it;
- names in one run and not the other.

A description of two files. It ranks nothing, scores nothing and recommends nothing; what
a line means for a position is the reader's. The thresholds are constants here, chosen so
a quiet day prints little, and a change to one is a change to what a day shows."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parents[1]
CURRENT = REPO_ROOT / "output" / "valuations.jsonl"
RUNS = REPO_ROOT / "output" / "runs"
OUT = REPO_ROOT / "output" / "watch"
FAIR_VALUE_MOVE = 0.05
PRICE_MOVE = 0.10
RELEASE_DAYS = 7
STRETCH_FLAG = 3
Json = dict[str, object]


def load(path: Path) -> dict[str, Json]:
    return {str(v["ticker"]): v for v in (cast(Json, json.loads(line)) for line in path.read_text().splitlines() if line.strip())}


def valued_on(records: dict[str, Json]) -> str:
    return str(next(iter(records.values()))["valued_on"]) if records else "-"


def previous_run(current_day: str, runs: Path = RUNS) -> Path | None:
    """The newest archived run valued on an earlier day than [current_day]."""
    if not runs.is_dir():
        return None
    for d in sorted((p for p in runs.iterdir() if p.is_dir()), key=lambda p: p.name, reverse=True):
        f = d / "valuations.jsonl"
        if f.exists() and valued_on(load(f)) < current_day:
            return f
    return None


def num(v: Json, key: str) -> float | None:
    x = v.get(key)
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def period_end(v: Json) -> str | None:
    inputs = v.get("inputs")
    if isinstance(inputs, list) and len(cast(list[object], inputs)) == 2:
        body = cast(Json, cast(list[object], inputs)[1])
        body = cast(Json, body.get("dcf") or body)
        end = body.get("fiscal_period_end")
        return str(end) if end is not None else None
    return None


def moved(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None or a == 0 else b / a - 1


def flag(v: Json, side: str) -> int:
    block = v.get("stretch")
    x = cast(Json, block).get(side) if isinstance(block, dict) else None
    return x if isinstance(x, int) and not isinstance(x, bool) else 0


def cluster(v: Json) -> bool:
    block = v.get("insiders")
    return isinstance(block, dict) and cast(Json, block).get("cluster_buy") is True


def section(title: str, lines: list[str]) -> list[str]:
    return [f"{title} ({len(lines)})" + (":" if lines else ": none"), *[f"  {x}" for x in lines], ""]


def report(previous: dict[str, Json], current: dict[str, Json]) -> str:
    both = sorted(set(previous) & set(current))
    out = [f"the watch: {valued_on(previous)} to {valued_on(current)}, {len(both)} names in both runs",
           "what changed between two runs' records; a description, ranking and recommending nothing", ""]
    out += section("ticker identity: the ticker no longer names its declared filer",
                   [f"{t}: {current[t].get('failed_reason')}" for t in sorted(current) if str(current[t].get("failed_reason") or "").startswith("ticker identity")])
    status: list[str] = []
    signal: list[str] = []
    crossed: list[str] = []
    new_year: list[str] = []
    value: list[str] = []
    price: list[str] = []
    stretch: list[str] = []
    insiders: list[str] = []
    for t in both:
        a, b = previous[t], current[t]
        if a["status"] != b["status"]:
            status.append(f"{t}: {a['status']} to {b['status']}" + (f": {b.get('failed_reason')}" if b["status"] != "Ok" else f", fair value {num(b, 'fair_value'):.2f} against {num(b, 'price'):.2f}"))
        if a.get("signal") != b.get("signal") and a["status"] == b["status"] == "Ok":
            signal.append(f"{t}: {a.get('signal')} to {b.get('signal')}, margin of safety {num(a, 'margin_of_safety'):+.2f} to {num(b, 'margin_of_safety'):+.2f}")
        ma, mb = num(a, "margin_of_safety"), num(b, "margin_of_safety")
        if ma is not None and mb is not None and (ma > 0) != (mb > 0):
            crossed.append(f"{t}: price {num(b, 'price'):.2f} now {'below' if mb > 0 else 'above'} fair value {num(b, 'fair_value'):.2f}")
        ea, eb = period_end(a), period_end(b)
        fresh = ea is not None and eb is not None and ea != eb
        if fresh:
            new_year.append(f"{t}: fiscal year ending {eb} read, was {ea}; fair value {num(a, 'fair_value'):.2f} to {num(b, 'fair_value'):.2f}")
        fv = moved(num(a, "fair_value"), num(b, "fair_value"))
        if fv is not None and abs(fv) > FAIR_VALUE_MOVE and not fresh:
            value.append(f"{t}: fair value {num(a, 'fair_value'):.2f} to {num(b, 'fair_value'):.2f} ({fv:+.0%})")
        pm = moved(num(a, "price"), num(b, "price"))
        if pm is not None and abs(pm) > PRICE_MOVE:
            price.append(f"{t}: price {num(a, 'price'):.2f} to {num(b, 'price'):.2f} ({pm:+.0%})")
        for side, name in (("stretch_low", "low"), ("stretch_high", "high")):
            if flag(b, side) >= STRETCH_FLAG > flag(a, side):
                stretch.append(f"{t}: {name} side, {flag(a, side)} to {flag(b, side)}")
        if cluster(b) and not cluster(a):
            insiders.append(f"{t}: two or more insiders bought inside fourteen days")
    out += section("status changed", status)
    out += section("signal changed", signal)
    out += section("the price crossed the fair value", crossed)
    out += section("a new fiscal year was read", new_year)
    out += section(f"fair value moved by more than {FAIR_VALUE_MOVE:.0%} with no new fiscal year", value)
    out += section(f"price moved by more than {PRICE_MOVE:.0%}", price)
    out += section(f"stretch newly at or above {STRETCH_FLAG} on a side", stretch)
    out += section("an insider buying cluster newly present", insiders)
    due: list[tuple[int, str]] = []
    for t in sorted(current):
        block = current[t].get("earnings")
        if isinstance(block, dict):
            e = cast(Json, block)
            days = e.get("days_to_next")
            if isinstance(days, int) and 0 <= days <= RELEASE_DAYS:
                implied = e.get("implied")
                move = cast(Json, implied).get("implied_move") if isinstance(implied, dict) else None
                due.append((days, f"{t}: {cast(Json, e['calendar']).get('next_date')}, in {days} day(s)" + (f", implied move {move:.1%}" if isinstance(move, float) else "")))
    out += section(f"releases due within {RELEASE_DAYS} days", [line for _, line in sorted(due)])
    out += section("in the current run and not the previous", sorted(set(current) - set(previous)))
    out += section("in the previous run and not the current", sorted(set(previous) - set(current)))
    return "\n".join(out)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--current", type=Path, default=CURRENT)
    parser.add_argument("--previous", type=Path, default=None, help="default: the newest run under output/runs/ valued on an earlier day")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    current_path: Path = args.current
    out: Path = args.out
    if not current_path.exists():
        print(f"{current_path} not found: run the batch first", file=sys.stderr)
        return 2
    current = load(current_path)
    previous_path: Path | None = args.previous if args.previous is not None else previous_run(valued_on(current))
    if previous_path is None or not previous_path.exists():
        print("no earlier run to compare with: pass --previous, or run the batch on two days", file=sys.stderr)
        return 2
    text = report(load(previous_path), current)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{valued_on(current)}.txt").write_text(text)
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
