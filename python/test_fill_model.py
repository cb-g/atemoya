"""The fill model (50): fill position and clamps, the locked or crossed exclusion, bucket
assignment, the quantile table on a synthetic tape, the expression tool's leg pricing from
a fixture table, and a holder's fill against it."""

from __future__ import annotations

import json
import math
from pathlib import Path

import express as ex
import fill_model as fm
import fills_vs_model as fv
import hedge
from test_hedge import fixture


def test_fill_position_clamps_and_excludes() -> None:
    assert fm.fill_position(1.05, 1.00, 1.10) == (0.5, None) and fm.fill_position(1.00, 1.00, 1.10) == (0.0, None) and fm.fill_position(1.10, 1.00, 1.10) == (1.0, None)
    assert fm.fill_position(1.30, 1.00, 1.10) == (1.5, "clamped") and fm.fill_position(0.80, 1.00, 1.10) == (-0.5, "clamped")
    assert fm.fill_position(1.05, 1.10, 1.10) == (None, "locked or crossed quote") and fm.fill_position(1.05, 1.20, 1.10) == (None, "locked or crossed quote")


def test_bucket_assignment() -> None:
    assert fm.moneyness_bucket(0.1) == "|delta| < 1/3" and fm.moneyness_bucket(0.5) == "1/3 <= |delta| < 2/3" and fm.moneyness_bucket(0.9) == "|delta| >= 2/3"
    assert fm.width_bucket(1.00, 1.05) == "1 tick" and fm.width_bucket(1.00, 1.15) == "2-3 ticks" and fm.width_bucket(5.00, 5.50) == "4-9 ticks" and fm.width_bucket(5.00, 7.00) == "10+ ticks"
    assert fm.half_hour("09:31:12") == "09:30" and fm.half_hour("2026-09-17T15:59:00.000") == "15:30" and fm.half_hour("10:05") == "10:00"
    assert fm.quantiles([0.1, 0.2, 0.3, 0.4, 0.5]) == {"q10": 0.1, "q25": 0.2, "q50": 0.3, "q75": 0.4, "q90": 0.5}


def synthetic_tape(day: str) -> dict[str, object]:
    """Prints at a fixed position per moneyness: near-the-money at the mid, far at the ask."""
    prints: list[dict[str, object]] = []
    for strike, pos in ((100.0, 0.5), (70.0, 1.0)):
        for i in range(20):
            bid, ask = 5.00, 5.10
            prints.append({"expiration": "2027-09-01", "strike": strike, "right": "call", "time": f"{9 + i % 6:02d}:{(i * 7) % 60:02d}", "price": bid + pos * (ask - bid), "size": 1, "bid": bid, "ask": ask})
    prints.append({"expiration": "2027-09-01", "strike": 100.0, "right": "call", "time": "10:00", "price": 5.05, "size": 1, "bid": 5.10, "ask": 5.10})  # locked
    prints.append({"expiration": "2027-09-01", "strike": 100.0, "right": "call", "time": "10:00", "price": 5.40, "size": 1, "bid": 5.00, "ask": 5.10})  # clamped
    return {"ticker": "T", "date": day, "source": "synthetic", "contracts_traded": 2, "prints": prints}


def test_quantile_table_on_a_synthetic_tape(tmp_path: Path) -> None:
    deltas = {"2026-09-01": {("2027-09-01", 100.0, "call"): 0.5, ("2027-09-01", 70.0, "call"): 0.9}}
    model = fm.build("T", [synthetic_tape("2026-09-01")], deltas)
    counts = hedge.points([model["counts"]])[0]
    assert counts["prints"] == 42 and counts["excluded_locked_or_crossed"] == 1 and counts["clamped"] == 1
    by_m = hedge.points([model["by_moneyness"]])[0]
    near = hedge.points([by_m["1/3 <= |delta| < 2/3"]])[0]
    far = hedge.points([by_m["|delta| >= 2/3"]])[0]
    assert near["count"] == 21 and math.isclose(float(str(near["q50"])), 0.5) and far["count"] == 20 and math.isclose(float(str(far["q50"])), 1.0)
    overall = hedge.points([model["overall"]])[0]
    assert overall["count"] == 41 and 0.5 <= float(str(overall["q50"])) <= 1.0
    (tmp_path / "T.json").write_text(json.dumps(model))
    loaded = ex.FillModel.load(tmp_path / "T.json")
    assert loaded.ticker == "T" and loaded.overall is not None and "1/3 <= |delta| < 2/3 | 1 tick" in loaded.by_cell  # a dime spread above three dollars is one tick
    line = fm.summary_line(model)
    assert line.startswith("T: 41 prints, median fill position")


def test_leg_pricing_from_a_fixture_table_and_a_fill_against_it() -> None:
    chain, smiles = fixture()
    expiries, _ = hedge.expiries_in_window(smiles, chain, 300)
    e = expiries[0]
    # a table whose only cell says trades print a quarter of the way from the bid, overall the same
    cell = f"{fm.moneyness_bucket(abs(e.calls[100.0].greeks.delta))} | {fm.width_bucket(e.calls[100.0].bid, e.calls[100.0].ask)}"
    model = ex.FillModel("T", {cell: (0.25, 100)}, (0.25, 200))
    long, short = e.calls[100.0], e.calls[110.0]
    s = ex.spread("bull_call", e, long, short, 0.03, model)
    bought = long.bid + 0.25 * (long.ask - long.bid)
    sold = short.bid + 0.75 * (short.ask - short.bid)
    assert math.isclose(s.cost, bought - sold) and s.fill.startswith("fill model: long at") and "q50 0.25" in s.fill
    flat = ex.spread("bull_call", e, long, short, 0.03, None)
    assert math.isclose(flat.cost, long.ask - short.bid + 0.03) and flat.fill == "ask for what is bought, bid for what is sold plus slippage"
    assert s.cost < flat.cost  # the model's fills sit inside the spread, so the flat rule is the dearer one
    # a holder's fill read against the table: a buy at the mid sits above the model's 25th-percentile cell median
    fills = fv.Fills(ticker="T", date="2026-09-01", legs=[fv.Leg(contract="c", side="buy", price=(long.bid + long.ask) / 2, bid=long.bid, ask=long.ask, abs_delta=abs(long.greeks.delta))])
    table: dict[str, object] = {"ticker": "T", "overall": {"count": 200, "q10": 0.0, "q25": 0.1, "q50": 0.25, "q75": 0.4, "q90": 0.6},
             "by_moneyness_width": {cell: {"count": 100, "q10": 0.0, "q25": 0.1, "q50": 0.25, "q75": 0.4, "q90": 0.6}}}
    rows = fv.compare(fills, table)
    assert rows[0]["cell"] == cell and rows[0]["position"] == 0.5 and rows[0]["band"] == "between the 75th and the 90th percentile"
