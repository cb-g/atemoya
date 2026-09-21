"""A holder's own fills against the fill model (50): each fill's position in the quoted
spread, and where it sits among the model's quantiles for its bucket.

    uv run python/fills_vs_model.py data/fills/mine.json [--model data/fill_model]

The fills file is untracked: {"ticker", "date", "legs": [{"contract": "2027-03-19 370 call",
"side": "buy" | "sell", "price", "bid", "ask", "abs_delta" (optional)}]}. A fill's position
is compared with the name's per-moneyness-and-width cell when abs_delta is given, else
with the name's overall quantiles; a sold leg is read as 1 - position so that 0 is the
holder's side of the market and 1 the far side, the same convention the model uses by
symmetry. These fills are the asymmetric truth the tape cannot give."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

import fill_model as fm
import hedge

REPO_ROOT = Path(__file__).resolve().parents[1]


class Leg(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    contract: str
    side: str
    price: float
    bid: float
    ask: float
    abs_delta: float | None = None


class Fills(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    ticker: str
    date: str
    legs: list[Leg]


def band(position: float, cell: dict[str, object]) -> str:
    """Where a position sits among the cell's quantiles."""
    qs = [(q, float(str(cell[f"q{q}"]))) for q in fm.QUANTILES if f"q{q}" in cell]
    below = [q for q, v in qs if position <= v]
    if not qs:
        return "no quantiles in the cell"
    if not below:
        return f"above the {qs[-1][0]}th percentile"
    if below[0] == qs[0][0]:
        return f"at or below the {qs[0][0]}th percentile"
    return f"between the {[q for q, v in qs if position > v][-1]}th and the {below[0]}th percentile"


def compare(fills: Fills, model: dict[str, object]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for leg in fills.legs:
        pos, why = fm.fill_position(leg.price, leg.bid, leg.ask)
        if pos is None:
            out.append({"contract": leg.contract, "side": leg.side, "position": None, "note": why})
            continue
        holder_side = pos if leg.side == "buy" else 1.0 - pos
        cell_name = "overall"
        cell = hedge.points([model["overall"]])[0]
        if leg.abs_delta is not None:
            key = f"{fm.moneyness_bucket(leg.abs_delta)} | {fm.width_bucket(leg.bid, leg.ask)}"
            table = hedge.points([model["by_moneyness_width"]])[0]
            if key in table:
                cell_name, cell = key, hedge.points([table[key]])[0]
        out.append({"contract": leg.contract, "side": leg.side, "position": pos, "position_from_the_holders_side": holder_side, "cell": cell_name,
                    "cell_count": cell.get("count"), "band": band(holder_side, cell), "clamped": why == "clamped"})
    return out


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("fills", type=Path)
    parser.add_argument("--model", type=Path, default=REPO_ROOT / "data" / "fill_model")
    args = parser.parse_args(argv)
    try:
        fills = Fills.model_validate_json(args.fills.read_text())
    except ValidationError as e:
        raise SystemExit(f"{args.fills}: {e}") from e
    model_path: Path = args.model / f"{fills.ticker}.json"
    if not model_path.exists():
        print(f"{fills.ticker}: no fill model at {model_path}; build it with uv run python/fill_model.py {fills.ticker}", file=sys.stderr)
        return 1
    rows = compare(fills, json.loads(model_path.read_text()))
    for r in rows:
        if r["position"] is None:
            print(f"{r['contract']} {r['side']}: {r['note']}")
        else:
            print(f"{r['contract']} {r['side']}: position {float(str(r['position'])):.2f} ({float(str(r['position_from_the_holders_side'])):.2f} from the holder's side), {r['band']} of the {r['cell']} cell ({r['cell_count']} prints)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
