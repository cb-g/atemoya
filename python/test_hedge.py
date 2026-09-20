"""Hedging a single holding (38): payoffs by hand including the premium, ask for what is
bought and bid for what is sold, the Pareto rule, the three constraint selections, the
anchor above spot, the stale-quote and missing-leg exclusions, the floor probability on a
flat smile, and determinism."""

from __future__ import annotations

import json
import math

import boundary
import hedge

SPOT = 100.0
RF = 0.0
T_DAYS = 365


def flat_smile(w: float) -> boundary.SviSmile:
    return boundary.SviSmile(a=w, b=0.0, rho=0.0, m=0.0, sigma=0.1, rmse=0.0, quotes_fitted=10, quotes_excluded_wide=0, spread_rule="ask <= 3 bid", put_call_iv_gap_at_forward=0.0)


def quote(expiry: str, strike: float, right: str, bid: float, ask: float) -> boundary.OptionQuote:
    return boundary.OptionQuote(expiration=expiry, strike=strike, right=right, bid=bid, ask=ask, mid=(bid + ask) / 2, bid_size=1, ask_size=1, last=0.0, volume=0, count=0)


def lognormal_quotes(expiry: str, vol: float, strikes: list[float], *, spread: float = 0.02, off: dict[float, float] | None = None) -> list[boundary.OptionQuote]:
    """Quotes at the flat lognormal's prices, bid and ask a spread around them; off shifts a
    strike's put quote by a multiple of its price (a stale quote)."""
    w = vol * vol * T_DAYS / 365.0
    out: list[boundary.OptionQuote] = []
    for k in strikes:
        for right in ("call", "put"):
            price = hedge.black_undiscounted(right, SPOT, k, w)
            if right == "put" and off and k in off:
                price *= off[k]
            if price > 0.01:
                out.append(quote(expiry, k, right, price * (1 - spread), price * (1 + spread)))
    return out


def fixture(*, off: dict[float, float] | None = None, drop_call: float | None = None) -> tuple[boundary.OptionChain, boundary.ChainSmiles]:
    expiry = "2027-09-01"
    strikes = [70.0, 80.0, 90.0, 100.0, 110.0, 120.0, 130.0]
    quotes = [q for q in lognormal_quotes(expiry, 0.25, strikes, off=off) if not (drop_call is not None and q.right == "call" and q.strike == drop_call)]
    chain = boundary.OptionChain(ticker="T", snapshot_date="2026-09-01", snapshot_timestamp="", source="fixture", underlying_close=SPOT, underlying_source="fixture", fetched_at="", quotes=quotes)
    smiles = boundary.ChainSmiles(ticker="T", snapshot_date="2026-09-01", spot=SPOT, risk_free_rate=RF,
                                  expiries=[boundary.ExpirySmile(expiry=expiry, days_to_expiry=T_DAYS, forward=SPOT, forward_source="fixture", smile=flat_smile(0.0625), reason=None)])
    return chain, smiles


def legs(chain: boundary.OptionChain, right: str, strike: float) -> tuple[float, float]:
    q = next(q for q in chain.quotes if q.right == right and q.strike == strike)
    return q.bid, q.ask


def by(cands: list[hedge.Candidate], structure: str, **strikes: float) -> hedge.Candidate:
    return next(c for c in cands if c.structure == structure and all(getattr(c, k) == v for k, v in strikes.items()))


def test_payoffs_by_hand_ask_for_bought_bid_for_sold() -> None:
    chain, smiles = fixture()
    expiries, notes = hedge.expiries_in_window(smiles, chain, 300)
    assert notes == [] and len(expiries) == 1
    cands = hedge.candidates_of(expiries, SPOT)
    _, p90_ask = legs(chain, "put", 90.0)
    p80_bid, _ = legs(chain, "put", 80.0)
    c110_bid, _ = legs(chain, "call", 110.0)
    put = by(cands, "protective_put", long_put=90.0)
    assert put.cost == p90_ask and math.isclose(put.floor_pct, (90.0 - p90_ask) / SPOT) and put.cap_pct is None and put.floor_strike == 90.0
    collar = by(cands, "collar", long_put=90.0, short_call=110.0)
    assert math.isclose(collar.cost, p90_ask - c110_bid) and math.isclose(collar.floor_pct, (90.0 - collar.cost) / SPOT) and collar.cap_pct is not None and math.isclose(collar.cap_pct, (110.0 - collar.cost) / SPOT)
    spread = by(cands, "put_spread", long_put=90.0, short_put=80.0)
    assert math.isclose(spread.cost, p90_ask - p80_bid) and math.isclose(spread.floor_pct, (90.0 - 80.0 - spread.cost) / SPOT) and spread.floor_strike == 80.0
    covered = by(cands, "covered_call", short_call=110.0)
    assert math.isclose(covered.cost, -c110_bid) and math.isclose(covered.floor_pct, c110_bid / SPOT) and covered.cap_pct is not None and math.isclose(covered.cap_pct, (110.0 + c110_bid) / SPOT)
    assert covered.floor_strike is None
    # a collar never has the call at or below the put; the mid is reported beside the cost
    assert all(c.short_call > c.long_put for c in cands if c.structure == "collar" and c.long_put is not None and c.short_call is not None)
    assert put.cost_mid < put.cost and covered.cost_mid < covered.cost  # ask above mid; bid below mid
    # the holding's delta is one; a protective put lowers it, a covered call too
    assert 0.0 < put.greeks.delta < 1.0 and 0.0 < covered.greeks.delta < 1.0


def test_pareto_drops_the_dominated_point() -> None:
    def c(cost: float, floor: float, cap: float | None) -> hedge.Candidate:
        return hedge.Candidate("protective_put" if cap is None else "collar", "e", 1, 90.0, None, 110.0 if cap else None, cost, cost, cost, floor, cap, 90.0, hedge.Greeks(1, 0, 0, 0))
    a, b, dominated, capped = c(0.01, 0.80, None), c(0.02, 0.85, None), c(0.03, 0.80, None), c(0.005, 0.80, 1.10)
    front = hedge.pareto([a, b, dominated, capped])
    assert dominated not in front and a in front and b in front and capped in front  # capped is cheaper than a; a has no cap: neither dominates


def test_constraints_select_and_the_anchor_above_spot_says_so() -> None:
    chain, smiles = fixture()
    expiries, _ = hedge.expiries_in_window(smiles, chain, 300)
    front = hedge.pareto(hedge.candidates_of(expiries, SPOT))
    cheap, reason = hedge.select(front, hedge.Constraint(max_cost_pct=0.02), anchor=None, spot=SPOT)
    assert reason is None and all(c.cost_pct <= 0.02 for c in cheap) and cheap[0].floor_pct == max(c.floor_pct for c in cheap)
    floored, reason = hedge.select(front, hedge.Constraint(min_floor_pct=0.85), anchor=None, spot=SPOT)
    assert reason is None and all(c.floor_pct >= 0.85 for c in floored) and floored[0].cost_pct == min(c.cost_pct for c in floored)
    anchored, reason = hedge.select(front, hedge.Constraint(floor="anchor"), anchor=88.0, spot=SPOT)
    assert reason is None and all(c.floor_pct >= 0.88 for c in anchored) and anchored[0].cost_pct == min(c.cost_pct for c in anchored)
    none, reason = hedge.select(front, hedge.Constraint(floor="anchor"), anchor=120.0, spot=SPOT)
    assert none == [] and reason is not None and reason.startswith("the anchor is above the price; nothing above it to insure")
    none, reason = hedge.select(front, hedge.Constraint(floor="anchor"), anchor=None, spot=SPOT)
    assert none == [] and reason == "the anchor is not available: the name has no fair value in the run"
    none, reason = hedge.select(front, hedge.Constraint(max_cost_pct=-5.0), anchor=None, spot=SPOT)
    assert none == [] and reason is not None and reason.startswith("no frontier point costs at most")


def test_stale_quote_and_missing_leg_exclude_the_candidate() -> None:
    chain, smiles = fixture(off={90.0: 1.6}, drop_call=110.0)  # the 90 put quoted 60% rich; no 110 call
    expiries, _ = hedge.expiries_in_window(smiles, chain, 300)
    e = expiries[0]
    assert 90.0 not in e.puts and e.excluded_stale >= 1
    assert 110.0 not in e.calls
    cands = hedge.candidates_of(expiries, SPOT)
    assert not any(c.long_put == 90.0 for c in cands) and not any(c.short_call == 110.0 for c in cands)
    assert any(c.long_put == 80.0 for c in cands) and any(c.short_call == 120.0 for c in cands)


def test_floor_probability_is_the_lognormal_on_a_flat_smile() -> None:
    chain, smiles = fixture()
    expiries, _ = hedge.expiries_in_window(smiles, chain, 300)
    put = by(hedge.candidates_of(expiries, SPOT), "protective_put", long_put=90.0)
    fp = hedge.floor_probability(put, expiries)
    w = 0.0625
    expected = hedge.norm_cdf((math.log(90.0 / SPOT) + w / 2) / math.sqrt(w))
    assert fp["risk_neutral"] is True and isinstance(fp["value"], float) and math.isclose(fp["value"], expected, abs_tol=1e-9)
    covered = by(hedge.candidates_of(expiries, SPOT), "covered_call", short_call=110.0)
    assert hedge.floor_probability(covered, expiries)["value"] is None


def test_window_and_determinism() -> None:
    chain, smiles = fixture()
    assert hedge.expiries_in_window(smiles, chain, 400)[0] == []  # 365 days is short of the horizon
    assert hedge.expiries_in_window(smiles, chain, 200)[0] == []  # 365 days is more than 120 beyond it
    h = hedge.Holding(ticker="T", shares=10.0, horizon_days=300, constraint=hedge.Constraint(min_floor_pct=0.8))
    one = json.dumps(hedge.hedge_one(h, chain, smiles, anchor=None, anchor_reason=None), sort_keys=True)
    two = json.dumps(hedge.hedge_one(h, chain, smiles, anchor=None, anchor_reason=None), sort_keys=True)
    assert one == two and '"scope_limits"' in one


def test_holdings_file_is_strict(tmp_path: object) -> None:
    import pytest
    from pathlib import Path
    assert isinstance(tmp_path, Path)
    bad = tmp_path / "h.json"
    bad.write_text('{"holdings": [{"ticker": "T", "shares": 1, "horizon_days": 30, "constraint": {"max_cost_pct": 0.1, "floor": "anchor"}}]}')
    with pytest.raises(SystemExit, match="exactly one"):
        hedge.load_holdings(bad)
    bad.write_text('{"holdings": [{"ticker": "T", "shares": 1, "horizon_days": 30, "constraint": {"floor": "spot"}}]}')
    with pytest.raises(SystemExit, match="anchor"):
        hedge.load_holdings(bad)
