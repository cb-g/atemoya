"""Expressing a view (46): payoffs and max loss for the four verticals by hand with slippage,
the p_view mapping and its null reason, p_market over the three regions on a flat smile,
the EV formula and the ranking, the vol percentile on a synthetic history, and a view
without a probability refused."""

from __future__ import annotations

import math

import express as ex
import hedge
from test_hedge import fixture


def legs(strike: float, right: str) -> hedge.Leg:
    """A leg whose ask is a dollar above its bid; calls cheaper and puts dearer as the strike rises."""
    bid = (200.0 - strike) / 5.0 if right == "call" else strike / 5.0
    return hedge.Leg(right, strike, bid, bid + 1.0, bid + 0.5, 0.25, hedge.Greeks(0, 0, 0, 0))


def expiry() -> hedge.Expiry:
    smile = fixture()[1].expiries[0].smile
    assert smile is not None
    return hedge.Expiry("2027-09-01", 365, 100.0, smile, {90.0: legs(90.0, "put"), 100.0: legs(100.0, "put"), 110.0: legs(110.0, "put")},
                        {90.0: legs(90.0, "call"), 100.0: legs(100.0, "call"), 110.0: legs(110.0, "call")}, 0, 0)


def test_payoffs_and_max_loss_by_hand_with_slippage() -> None:
    e = expiry()
    slip = 0.5 / 100 * 2  # 0.50 per contract per leg, two legs, per share
    c100, c110, p90, p100, p110 = e.calls[100.0], e.calls[110.0], e.puts[90.0], e.puts[100.0], e.puts[110.0]
    bull_call = ex.spread("bull_call", e, c100, c110, slip)
    assert math.isclose(bull_call.cost, c100.ask - c110.bid + slip) and math.isclose(bull_call.max_loss, bull_call.cost) and math.isclose(bull_call.max_profit, 10.0 - bull_call.cost)
    assert math.isclose(bull_call.breakeven, 100.0 + bull_call.cost) and math.isclose(bull_call.payoff(120.0), bull_call.max_profit) and math.isclose(bull_call.payoff(80.0), -bull_call.max_loss)
    bull_put = ex.spread("bull_put", e, e.puts[90.0], e.puts[100.0], slip)   # long 90 put, short 100 put: a credit
    assert bull_put.credit and math.isclose(bull_put.cost, p90.ask - p100.bid + slip) and bull_put.cost < 0 and math.isclose(bull_put.max_profit, -bull_put.cost) and math.isclose(bull_put.max_loss, 10.0 + bull_put.cost)
    assert math.isclose(bull_put.breakeven, 100.0 + bull_put.cost) and math.isclose(bull_put.payoff(120.0), bull_put.max_profit) and math.isclose(bull_put.payoff(80.0), -bull_put.max_loss)
    bear_put = ex.spread("bear_put", e, e.puts[110.0], e.puts[100.0], slip)   # long 110 put, short 100 put: a debit
    assert not bear_put.credit and math.isclose(bear_put.max_loss, p110.ask - p100.bid + slip) and math.isclose(bear_put.max_profit, 10.0 - bear_put.cost) and math.isclose(bear_put.breakeven, 110.0 - bear_put.cost)
    assert math.isclose(bear_put.payoff(80.0), bear_put.max_profit) and math.isclose(bear_put.payoff(120.0), -bear_put.max_loss)
    bear_call = ex.spread("bear_call", e, e.calls[110.0], e.calls[100.0], slip)  # long 110 call, short 100 call: a credit
    assert bear_call.credit and bear_call.cost < 0 and math.isclose(bear_call.cost, c110.ask - c100.bid + slip) and math.isclose(bear_call.max_profit, -bear_call.cost) and math.isclose(bear_call.max_loss, 10.0 + bear_call.cost) and math.isclose(bear_call.breakeven, 100.0 - bear_call.cost)
    assert math.isclose(bear_call.payoff(80.0), bear_call.max_profit) and math.isclose(bear_call.payoff(120.0), -bear_call.max_loss)
    # a fixture whose quotes leave nothing to win is not a candidate; the four kinds appear on their side
    kinds = {s.kind for s in ex.candidates_of([e], "up", 0.0)}
    assert kinds == {"bull_call", "bull_put"} and {s.kind for s in ex.candidates_of([e], "down", 0.0)} == {"bear_put", "bear_call"}


def test_p_view_applies_at_the_level_strike_only() -> None:
    e = expiry()  # strikes 90, 100, 110 on both rights
    # the level 104 is nearest 100; a tie at 105 goes to the near side, 100 for an up view and 110 for a down view
    assert ex.level_strike([90.0, 100.0, 110.0], 104.0, "up") == 100.0 and ex.level_strike([90.0, 100.0, 110.0], 105.0, "up") == 100.0
    assert ex.level_strike([90.0, 100.0, 110.0], 105.0, "down") == 110.0 and ex.level_strike([], 105.0, "up") is None
    ls: dict[tuple[str, str], float | None] = {("2027-09-01", "call"): 100.0, ("2027-09-01", "put"): 100.0}
    debit = ex.spread("bull_call", e, e.calls[90.0], e.calls[100.0], 0.0)   # short at the level strike: qualifies, any width
    credit = ex.spread("bull_put", e, e.puts[90.0], e.puts[100.0], 0.0)     # short put at the level strike: qualifies too
    beyond = ex.spread("bull_call", e, e.calls[100.0], e.calls[110.0], 0.0) # short one strike beyond: not the declared region
    assert ex.p_view_of(debit, "up", 0.3, ls) == (0.3, None) and ex.p_view_of(credit, "up", 0.3, ls) == (0.3, None)
    assert ex.p_view_of(beyond, "up", 0.3, ls) == (None, "max-profit region is not the declared one")
    down: dict[tuple[str, str], float | None] = {("2027-09-01", "call"): 100.0, ("2027-09-01", "put"): 100.0}
    assert ex.p_view_of(ex.spread("bear_put", e, e.puts[110.0], e.puts[100.0], 0.0), "down", 0.4, down) == (0.4, None)
    assert ex.p_view_of(ex.spread("bear_call", e, e.calls[110.0], e.calls[100.0], 0.0), "down", 0.4, down) == (0.4, None)
    assert ex.p_view_of(ex.spread("bear_put", e, e.puts[110.0], e.puts[90.0], 0.0), "down", 0.4, down)[0] is None


def test_p_market_regions_on_a_flat_smile() -> None:
    e = expiry()  # flat total variance 0.0625, forward 100: lognormal
    s = ex.spread("bull_call", e, e.calls[100.0], e.calls[110.0], 0.0)
    pm = ex.p_market_of(s, e)
    w = 0.0625
    def lognormal_cdf(x: float) -> float:
        return hedge.norm_cdf((math.log(x / 100.0) + w / 2) / math.sqrt(w))
    assert math.isclose(pm["max_profit"], 1.0 - lognormal_cdf(110.0), abs_tol=1e-9) and math.isclose(pm["max_loss"], lognormal_cdf(100.0), abs_tol=1e-9)
    assert math.isclose(pm["between"], lognormal_cdf(110.0) - lognormal_cdf(100.0), abs_tol=1e-9) and math.isclose(pm["beyond_breakeven"], 1.0 - lognormal_cdf(s.breakeven), abs_tol=1e-9)
    bear = ex.spread("bear_put", e, e.puts[110.0], e.puts[100.0], 0.0)
    pb = ex.p_market_of(bear, e)
    assert math.isclose(pb["max_profit"], lognormal_cdf(100.0), abs_tol=1e-9) and math.isclose(pb["max_loss"], 1.0 - lognormal_cdf(110.0), abs_tol=1e-9)


def test_ev_formula_and_ranking() -> None:
    assert math.isclose(ex.ev_per_dollar_at_risk(0.4, 9.0, 1.0), 0.4 * 9.0 - 0.6)
    assert math.isclose(ex.ev_per_dollar_at_risk(0.5, 1.0, 1.0), 0.0)
    chain, smiles = fixture()
    v = ex.View(ticker="T", direction="up", level=105.0, horizon_days=330, probability=0.4, why="test", as_of="2026-09-01", slippage_per_leg=0.0)  # the fixture expiry, 365 days out, sits inside the 60-day window
    r = ex.express_one(v, chain, smiles, {"sentence": None})
    ranked = hedge.points(r["ranked"])
    evs = [float(str(x["ev_per_dollar_at_risk"])) for x in ranked]
    # the fixture's strikes step by 10, so the level 105 ties between 100 and 110 and the near side, 100, is the
    # level strike; only spreads short at it are ranked, debit and credit alike
    assert evs == sorted(evs, reverse=True) and ranked and all(float(str(x["short_strike"])) == 100.0 for x in ranked)
    assert {str(x["kind"]) for x in ranked} == {"bull_call", "bull_put"}
    assert all(x["p_view"] is None and x["p_view_reason"] == "max-profit region is not the declared one" for x in hedge.points(r["unranked_on_p_market"]))
    for x in ranked:
        assert math.isclose(float(str(x["disagreement"])), 0.4 - float(str(x["p_market"])))
    shown = hedge.points(r["market_prices_the_view_more_strongly"])
    assert all(float(str(x["p_market"])) > 0.4 for x in shown)


def test_vol_percentile_and_realised_on_synthetic_series() -> None:
    assert ex.percentile_of(0.25, [0.1, 0.2, 0.3, 0.4]) == 50.0 and ex.percentile_of(0.5, [0.1, 0.2, 0.3, 0.4]) == 100.0 and ex.percentile_of(0.1, []) is None
    closes = [(f"2026-01-{d:02d}", 100.0 * math.exp(0.01 * math.sin(d))) for d in range(1, 29)]
    vol, n = ex.realised_vol(closes, 40, "2026-01-28")
    assert n == 27 and vol is not None and 0.1 < vol < 0.3
    assert ex.realised_vol(closes[:3], 40, "2026-01-28") == (None, 2)


def test_a_view_without_a_probability_or_a_why_is_refused() -> None:
    base = dict(ticker="T", direction="up", level=1.0, horizon_days=30, as_of="2026-09-01", slippage_per_leg=0.0)
    assert ex.check_view(ex.View(**base, probability=None, why="w")) is not None  # pyright: ignore[reportArgumentType]
    assert ex.check_view(ex.View(**base, probability=0.5, why=None)) is not None  # pyright: ignore[reportArgumentType]
    assert ex.check_view(ex.View(**base, probability=0.5, why="w")) is None  # pyright: ignore[reportArgumentType]
    assert ex.check_view(ex.View(**{**base, "direction": "sideways"}, probability=0.5, why="w")) is not None  # pyright: ignore[reportArgumentType]
