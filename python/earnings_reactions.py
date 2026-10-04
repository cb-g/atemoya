"""Earnings reactions: what the price did when a name beat or missed its bar.

    uv run python/earnings_reactions.py [--valuations output/valuations.jsonl]

The record already carries a name's last eight releases with the move across each, against
the benchmark, and the move the options imply for the next one (68). The consensus tool
carries each release's bar and reported figure (82). Neither says how the two met: whether
this name's price follows its surprises. This joins them and no more.

Contract. One line per universe name in `output/earnings_reactions/rows.jsonl`: every
release on the record matched by date (the filing date and the vendor's report date within
MATCH_DAYS of each other) to its consensus bar; each matched release with its surprise in
percent of the estimate's magnitude, its outcome (beat, meet or miss on the Street-adjusted
figures) and the excess move across it; the median excess move on beats and on misses with
their counts; `beats_sold`, the beats the price fell on, and `misses_bought`, the misses it
rose on; and beside them the next release's date, the days to it, the implied move and its
ratio to the realised median where the run was made with the options store. A name with no
matched release carries the reason. `table.txt` is the same per name, with the pooled line:
across every matched release in the universe, the median excess move on a beat and on a
miss.

A side output: never on a valuation record, feeding no model, belief or signal. Eight
releases a name is a handful, and the pooled line mixes companies; both are descriptions.
The move across a release carries whatever else moved the price that day, and a beat on
the Street's adjusted figure is not a beat on guidance, which the price often answers to."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import date
from pathlib import Path
from typing import cast

import consensus

REPO_ROOT = Path(__file__).resolve().parents[1]
VALUATIONS = REPO_ROOT / "output" / "valuations.jsonl"
OUT = REPO_ROOT / "output" / "earnings_reactions"
MATCH_DAYS = 2      # an 8-K is filed on the release day or the next; a vendor date may be either
MIN_SIDE = 3        # fewer releases on a side than this and its median is a count alone
Json = dict[str, object]


def outcome(estimate: float, reported: float) -> str:
    return "beat" if reported > estimate else "miss" if reported < estimate else "meet"


def match(events: list[Json], releases: list[Json]) -> list[Json]:
    """Each record event with the release whose report date is nearest its filing date,
    within MATCH_DAYS, when that release carries an estimate and a reported figure."""
    out: list[Json] = []
    for e in events:
        filed = date.fromisoformat(str(e["filed"]))
        near = [(abs((date.fromisoformat(str(r["report_date"])) - filed).days), r) for r in releases]
        near = [(gap, r) for gap, r in near if gap <= MATCH_DAYS and isinstance(r.get("eps_estimate"), (int, float)) and isinstance(r.get("eps_reported"), (int, float))]
        if not near:
            continue
        r = min(near, key=lambda x: x[0])[1]
        estimate, reported = float(cast(float, r["eps_estimate"])), float(cast(float, r["eps_reported"]))
        out.append({"filed": e["filed"], "report_date": r["report_date"], "eps_estimate": estimate, "eps_reported": reported,
                    "surprise_pct": None if estimate == 0 else (reported - estimate) / abs(estimate) * 100,
                    "outcome": outcome(estimate, reported), "excess": e["excess"]})
    return out


def side(matched: list[Json], which: str) -> Json:
    moves = [cast(float, m["excess"]) for m in matched if m["outcome"] == which]
    return {"n": len(moves), "median_excess": statistics.median(moves) if len(moves) >= MIN_SIDE else None}


def row_of(ticker: str, record: Json | None, history: Json | None) -> Json:
    out: Json = {"ticker": ticker}
    earnings = (record or {}).get("earnings")
    if not isinstance(earnings, dict):
        out["reason"] = "the record carries no earnings calendar" if record is not None else "no record for the name in the run"
        return out
    block = cast(Json, earnings)
    calendar = cast(Json, block["calendar"])
    implied = block.get("implied")
    out.update({"next_date": calendar.get("next_date"), "days_to_next": block.get("days_to_next"),
                "implied_move": cast(Json, implied).get("implied_move") if isinstance(implied, dict) else None,
                "realised_median_abs_excess": calendar.get("realised_median_abs_excess"), "implied_over_realised": block.get("implied_over_realised")})
    if history is None or history.get("status") != "ok":
        out["reason"] = "no release history from the consensus tool: run python/consensus.py" if history is None else str(history.get("reason"))
        return out
    matched = match(cast(list[Json], calendar.get("events") or []), cast(list[Json], history["releases"]))
    if not matched:
        out["reason"] = f"no release on the record matches a consensus bar within {MATCH_DAYS} days"
        return out
    out["releases"] = matched
    out["beats"], out["misses"] = side(matched, "beat"), side(matched, "miss")
    out["beats_sold"] = sum(1 for m in matched if m["outcome"] == "beat" and cast(float, m["excess"]) < 0)
    out["misses_bought"] = sum(1 for m in matched if m["outcome"] == "miss" and cast(float, m["excess"]) > 0)
    return out


def table(rows: list[Json], as_of: date) -> str:
    def pct(x: object, signed: bool = True) -> str:
        return (f"{x:+7.1%}" if signed else f"{x:7.1%}") if isinstance(x, float) else "      -"

    have = [r for r in rows if "releases" in r]
    everything = [m for r in have for m in cast(list[Json], r["releases"])]
    pooled = {w: side(everything, w) for w in ("beat", "miss")}
    lines = [f"earnings reactions, {as_of}: {len(have)} of {len(rows)} names with a matched release, {len(everything)} releases",
             "the excess move across a release against the Street-adjusted surprise; a description, not a signal",
             f"pooled: on {pooled['beat']['n']} beats the median excess move was {pct(pooled['beat']['median_excess']).strip()}, on {pooled['miss']['n']} misses {pct(pooled['miss']['median_excess']).strip()}; "
             f"{sum(cast(int, r['beats_sold']) for r in have)} beats were sold and {sum(cast(int, r['misses_bought']) for r in have)} misses bought",
             "", f"{'ticker':10} {'next':10} {'days':>4} {'implied':>7} {'realised':>8} {'beats':>5} {'on beat':>7} {'sold':>4} {'misses':>6} {'on miss':>7} {'bought':>6}  note"]
    for r in sorted(rows, key=lambda r: (not isinstance(r.get("days_to_next"), int), cast(int, r.get("days_to_next") or 0), str(r["ticker"]))):
        b, m = cast(Json, r.get("beats") or {}), cast(Json, r.get("misses") or {})
        lines.append(f"{str(r['ticker']):10} {str(r.get('next_date') or '-'):10} {str(r.get('days_to_next') if r.get('days_to_next') is not None else '-'):>4} "
                     f"{pct(r.get('implied_move'), False)} {pct(r.get('realised_median_abs_excess'), False):>8} {str(b.get('n', '-')):>5} {pct(b.get('median_excess'))} "
                     f"{str(r.get('beats_sold', '-')):>4} {str(m.get('n', '-')):>6} {pct(m.get('median_excess'))} {str(r.get('misses_bought', '-')):>6}  {r.get('reason') or ''}")
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--valuations", type=Path, default=VALUATIONS, help="a run's records; one made with --options carries the implied move")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    valuations: Path = args.valuations
    out: Path = args.out
    if not valuations.exists():
        print(f"{valuations} not found: run the batch first", file=sys.stderr)
        return 2
    records = {str(v["ticker"]): v for v in (cast(Json, json.loads(line)) for line in valuations.read_text().splitlines() if line.strip())}
    rows: list[Json] = []
    for entry in cast(list[Json], json.loads(consensus.UNIVERSE.read_text())["tickers"]):
        ticker = str(entry["ticker"])
        path = consensus.DATA / "history" / f"{ticker}.json"
        rows.append(row_of(ticker, records.get(ticker), cast(Json, json.loads(path.read_text())) if path.exists() else None))
    out.mkdir(parents=True, exist_ok=True)
    (out / "rows.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    text = table(rows, date.today())
    (out / "table.txt").write_text(text)
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
