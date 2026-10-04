"""The consensus-implied cost of capital: the return the price needs for the Street's own forecasts to be right.

    uv run python/implied_cost.py [--financials data/financials] [--valuations output/valuations.jsonl]

A third required return beside CAPM and the options-implied one, read from neither a beta
nor an option: the discount rate at which the price equals the earnings the analysts
forecast. Easton's PEG model (The Accounting Review, 2004), the simplest of the family and
the one that needs only what the daily consensus snapshot carries:

    r = sqrt((eps_next_year - eps_this_year) / price)

with both forecasts the consensus means for the current and the next fiscal year
(python/consensus.py, the latest ok snapshot) and the price the boundary record's. It
assumes the abnormal growth in earnings beyond those two years continues without growing
and ignores dividends, so it understates for a payer and is undefined where the forecast
does not rise.

A side output, on the same terms as the consensus tool it reads: never on a valuation
record, feeding no model, belief or signal. `output/consensus/implied_cost.jsonl` holds one
line per universe name: the two forecasts with their fiscal year ends and the snapshot day,
the price with its date, `implied_cost`, or null with the reason (no ok snapshot, a
forecast missing or not positive, the next year not above this one, the forecasts in
another currency than the price, a price quoted in a minor unit, no price). Where the run's
records are on disk it puts the record's CAPM cost of equity and its options-implied
expected return beside it. `implied_cost.txt` is the same as a table.

What it is not: the forecasts are the Street's adjusted earnings, not GAAP; analysts'
forecasts run optimistic, which pushes the figure up; and one model's algebra is not the
market's expectation. Read it as what the price and the forecasts together imply, beside
the other two, and no more."""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date
from pathlib import Path
from typing import cast

import consensus

REPO_ROOT = Path(__file__).resolve().parents[1]
FINANCIALS = REPO_ROOT / "data" / "financials"
VALUATIONS = REPO_ROOT / "output" / "valuations.jsonl"
OUT = consensus.OUT
METHOD = "easton_peg"
Json = dict[str, object]


def peg(eps_this: float | None, eps_next: float | None, price: float | None) -> tuple[float | None, str | None]:
    """(implied cost, reason): sqrt((next - this) / price), or why it cannot be formed."""
    if price is None or price <= 0:
        return None, "no price on the boundary record"
    if eps_this is None or eps_next is None:
        return None, "the snapshot lacks a forecast for one of the two fiscal years"
    if eps_this <= 0:
        return None, "the current fiscal year's forecast is not positive: the model has no base to grow from"
    if eps_next <= eps_this:
        return None, "the next fiscal year's forecast is not above the current one: the model is undefined without growth"
    return math.sqrt((eps_next - eps_this) / price), None


def period(snapshot: Json, name: str) -> Json | None:
    for p in cast(list[Json], snapshot.get("periods") or []):
        if p.get("period") == name:
            return p
    return None


def eps_mean(p: Json | None) -> float | None:
    if p is None:
        return None
    mean = cast(Json, p.get("eps") or {}).get("mean")
    return float(mean) if isinstance(mean, (int, float)) and not isinstance(mean, bool) else None


def row_of(ticker: str, snapshot: Json | None, boundary: Json | None, record: Json | None) -> Json:
    out: Json = {"ticker": ticker, "method": METHOD, "implied_cost": None}
    if record is not None:
        out["cost_of_equity_capm"] = record.get("cost_of_equity_capm")
        expected = record.get("options_expected_return")
        out["options_expected_return"] = cast(Json, expected).get("expected_return") if isinstance(expected, dict) else None
    if snapshot is None:
        out["reason"] = "no ok consensus snapshot on disk"
        return out
    this, nxt = period(snapshot, "0y"), period(snapshot, "+1y")
    out.update({"snapshot_date": snapshot.get("date"), "eps_currency": snapshot.get("eps_currency"),
                "eps_this_year": eps_mean(this), "this_year_end": None if this is None else this.get("end_date"),
                "eps_next_year": eps_mean(nxt), "next_year_end": None if nxt is None else nxt.get("end_date")})
    if boundary is None:
        out["reason"] = "no boundary record for the name: no price"
        return out
    price = boundary.get("price")
    out.update({"price": price, "price_as_of": boundary.get("as_of"), "price_currency": boundary.get("trading_currency")})
    if boundary.get("price_unit") not in (None, "major", "Major"):
        out["reason"] = "the price is quoted in a minor unit and the forecasts per share are not reconciled to it"
        return out
    if snapshot.get("eps_currency") != boundary.get("trading_currency"):
        out["reason"] = f"the forecasts are in {snapshot.get('eps_currency')} and the price in {boundary.get('trading_currency')}"
        return out
    value, why = peg(eps_mean(this), eps_mean(nxt), float(price) if isinstance(price, (int, float)) and not isinstance(price, bool) else None)
    out["implied_cost"] = value
    if why is not None:
        out["reason"] = why
    else:
        out["forecast_growth"] = cast(float, eps_mean(nxt)) / cast(float, eps_mean(this)) - 1
    return out


def table(rows: list[Json], as_of: date) -> str:
    def pct(x: object) -> str:
        return f"{x:7.1%}" if isinstance(x, float) else "      -"

    have = [r for r in rows if isinstance(r.get("implied_cost"), float)]
    lines = [f"consensus-implied cost of capital ({METHOD}), {as_of}: {len(have)} of {len(rows)} names",
             "what the price and the Street's two fiscal-year forecasts imply together; beside CAPM and the options-implied return, replacing neither",
             "", f"{'ticker':10} {'implied':>7} {'capm':>7} {'options':>7} {'growth':>7}  note"]
    for r in sorted(rows, key=lambda r: (not isinstance(r.get("implied_cost"), float), -cast(float, r.get("implied_cost") or 0.0), str(r["ticker"]))):
        lines.append(f"{str(r['ticker']):10} {pct(r.get('implied_cost'))} {pct(r.get('cost_of_equity_capm'))} {pct(r.get('options_expected_return'))} "
                     f"{pct(r.get('forecast_growth'))}  {r.get('reason') or ''}")
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--financials", type=Path, default=FINANCIALS, help="the boundary records the price is read from")
    parser.add_argument("--valuations", type=Path, default=VALUATIONS, help="a run's records, for the CAPM and options-implied figures beside it; optional")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    financials: Path = args.financials
    valuations: Path = args.valuations
    out: Path = args.out
    records: dict[str, Json] = {}
    if valuations.exists():
        for line in valuations.read_text().splitlines():
            if line.strip():
                v = cast(Json, json.loads(line))
                records[str(v["ticker"])] = v
    rows: list[Json] = []
    for entry in cast(list[Json], json.loads(consensus.UNIVERSE.read_text())["tickers"]):
        ticker = str(entry["ticker"])
        snapshot = next((s for s in reversed(consensus.snapshots_of(consensus.DATA, ticker)) if s.get("status") == "ok"), None)
        path = financials / f"{ticker}.json"
        rows.append(row_of(ticker, snapshot, cast(Json, json.loads(path.read_text())) if path.exists() else None, records.get(ticker)))
    out.mkdir(parents=True, exist_ok=True)
    (out / "implied_cost.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    text = table(rows, date.today())
    (out / "implied_cost.txt").write_text(text)
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
