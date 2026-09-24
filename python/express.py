"""Expressing a declared view with a vertical spread (46): the hedging machinery pointed the
other way. The holder declares a view; the tool never supplies, infers or adjusts one. It
prices every vertical on the view's side from the store's quotes, applies the holder's
probability only where the max-profit region is reached at or beyond the declared level,
puts the market's risk-neutral probability beside it, and ranks by expected value per
dollar at risk. No signal, no backtest, no recommendation without a declared view.

    uv run python/express.py views.json [--options data/options] [--run output] [--out output/express]

views.json: {"views": [{"ticker": "AAPL", "direction": "up", "level": 380, "horizon_days":
180, "probability": 0.35, "why": "...", "as_of": "2026-09-21", "slippage_per_leg": 0.00,
"max_risk_usd": 5000 (optional), "as_of_snapshot": "2026-09-17" (optional)}]}. The
probability is the holder's that the price is at or beyond the level in the direction at
the horizon; a view without a probability or a why is refused. slippage_per_leg is a
dollar amount per contract per leg added to every cost and must be written, even at 0.00.

Candidates: for each expiry at or beyond the horizon and within 60 days past it, up ->
bull call spreads (debit) and bull put spreads (credit), down -> bear put spreads (debit)
and bear call spreads (credit), over every pair of quoted strikes with a positive bid
(a leg more than five vol points off the fitted smile is a stale quote and excluded, as in
the hedging tool). Cost is ask for what is bought and bid for what is sold plus slippage.
Three probabilities per candidate: p_market, the risk-neutral probability of the
max-profit region from the fitted density on the candidate's expiry (the breakeven and
max-loss regions beside it); p_view, the declared probability, which applies at the level
and nowhere else (47): only to candidates whose max-profit region is exactly the declared
one, the short strike at the quoted strike nearest the level (ties to the near side,
recorded as level_strike) and the long strike where the spread's definition puts it, any
width, debit or credit alike; every other candidate carries p_view null with the reason
and is listed, not ranked; ev_per_dollar_at_risk = (p_view x max_profit - (1 - p_view) x
max_loss) / max_loss where p_view is. The ranking therefore answers two questions and
only two, how wide and debit or credit; the level itself is the holder's.

--fill-model DIR (50) replaces the flat slippage with the fill model's per-bucket median
fill position on each leg: a bought leg fills at bid + q50 x spread, a sold leg at
bid + (1 - q50) x spread by symmetry, the cell (moneyness third by |delta|, spread width
in ticks) and the quantile recorded on every candidate; a name without a model falls back
to the flat slippage, and the two are never combined on one leg. One
diagnostic per view: the nearest expiry's at-the-money implied volatility against the
name's realised volatility over the horizon's length and against its own ATM IV over the
last 250 snapshot dates as a percentile."""

# pyright: reportUnknownMemberType=false
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from pydantic import BaseModel, ConfigDict, ValidationError  # noqa: E402

import boundary  # noqa: E402
import fill_model as fm  # noqa: E402
import hedge  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
WINDOW_BEYOND_DAYS = 60
HISTORY_DATES = 250
CONTRACT = 100
RISK_NEUTRAL_NOTE = "risk-neutral: the probability embeds the market's risk pricing and is not a forecast"
SCOPE_LIMITS = [
    "every spread is evaluated held to expiry",
    "assignment on a short leg before expiry is possible and not modelled",
    "the holder's probability is theirs, not a forecast, and the ranking is only as good as it",
    "the market's probability is risk-neutral: it embeds the market's risk pricing and is not a forecast",
    "a fill model is not this tool's; slippage_per_leg is the declared placeholder for it",
]


class View(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    ticker: str
    direction: str
    level: float
    horizon_days: int
    probability: float | None = None
    why: str | None = None
    as_of: str
    slippage_per_leg: float
    as_of_snapshot: str | None = None
    max_risk_usd: float | None = None


class Views(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    views: list[View]


def check_view(v: View) -> str | None:
    """Why a view cannot be priced, or None: a direction alone is not a view."""
    if v.direction not in ("up", "down"):
        return f"direction must be up or down, got {v.direction!r}"
    if v.probability is None or not v.why:
        return "a view without a probability or a why is refused: a direction alone is not a view the tool can price"
    if not 0.0 < v.probability < 1.0:
        return "probability must be strictly between 0 and 1"
    if v.level <= 0 or v.horizon_days <= 0 or v.slippage_per_leg < 0:
        return "level and horizon_days must be positive and slippage_per_leg non-negative"
    return None


def load_views(path: Path) -> Views:
    try:
        return Views.model_validate_json(path.read_text())
    except ValidationError as e:
        raise SystemExit(f"{path}: {e}") from e


# --- spreads ---

@dataclass(frozen=True)
class FillModel:
    """A name's fill table (50): the median fill position per (moneyness, width) cell, the
    overall median as the fallback, and what was used."""
    ticker: str
    by_cell: dict[str, tuple[float, int]]
    overall: tuple[float, int] | None

    @classmethod
    def load(cls, path: Path) -> FillModel:
        m = json.loads(path.read_text())
        cells: dict[str, tuple[float, int]] = {}
        for k, v in hedge.points([m["by_moneyness_width"]])[0].items():
            c = hedge.points([v])
            if c and "q50" in c[0]:
                cells[k] = (float(str(c[0]["q50"])), int(str(c[0]["count"])))
        o = hedge.points([m["overall"]])[0]
        return cls(str(m["ticker"]), cells, (float(str(o["q50"])), int(str(o["count"]))) if "q50" in o else None)

    def fill(self, leg: hedge.Leg, bought: bool) -> tuple[float, str] | None:
        """The leg's fill price and the cell used; None when the model has no cell for it."""
        key = f"{fm.moneyness_bucket(abs(leg.greeks.delta))} | {fm.width_bucket(leg.bid, leg.ask)}"
        if key in self.by_cell:
            q, n, cell = self.by_cell[key][0], self.by_cell[key][1], key
        elif self.overall is not None:
            q, n, cell = self.overall[0], self.overall[1], "overall"
        else:
            return None
        position = q if bought else 1.0 - q
        return leg.bid + position * (leg.ask - leg.bid), f"{cell} (q50 {q:.2f}, {n} prints)"


@dataclass(frozen=True)
class Spread:
    kind: str            # bull_call | bull_put | bear_put | bear_call
    expiry: str
    days: int
    long_strike: float
    short_strike: float
    cost: float          # per share, debit positive, credit negative, slippage included
    cost_at_mid: float
    width: float
    max_profit: float
    max_loss: float
    breakeven: float
    fill: str = "ask for what is bought, bid for what is sold"

    @property
    def credit(self) -> bool:
        return self.kind in ("bull_put", "bear_call")

    @property
    def max_profit_region_from(self) -> float:
        return self.short_strike

    def payoff(self, s_t: float) -> float:
        """Per share at expiry, cost included."""
        call = self.kind in ("bull_call", "bear_call")

        def intrinsic(k: float) -> float:
            return max(s_t - k, 0.0) if call else max(k - s_t, 0.0)

        return intrinsic(self.long_strike) - intrinsic(self.short_strike) - self.cost


def spread(kind: str, expiry: hedge.Expiry, long: hedge.Leg, short: hedge.Leg, slippage_per_share: float, model: FillModel | None = None) -> Spread:
    """Cost at ask-bought/bid-sold plus slippage, or, with a fill model, at the model's fills
    on each leg and no slippage: the two are never combined on one leg."""
    fill = "ask for what is bought, bid for what is sold"
    if model is not None:
        bought, sold = model.fill(long, True), model.fill(short, False)
        if bought is not None and sold is not None:
            cost = bought[0] - sold[0]
            fill = f"fill model: long at {bought[1]}; short at {sold[1]}"
        else:
            cost = long.ask - short.bid + slippage_per_share
            fill = "ask for what is bought, bid for what is sold (no model cell for a leg; flat slippage)"
    else:
        cost = long.ask - short.bid + slippage_per_share
        if slippage_per_share:
            fill += " plus slippage"
    mid = long.mid - short.mid
    width = abs(long.strike - short.strike)
    if kind in ("bull_call", "bear_put"):
        max_loss, max_profit = cost, width - cost
        breakeven = long.strike + cost if kind == "bull_call" else long.strike - cost
    else:
        credit = -cost
        max_profit, max_loss = credit, width - credit
        breakeven = short.strike - credit if kind == "bull_put" else short.strike + credit
    return Spread(kind, expiry.expiry, expiry.days, long.strike, short.strike, cost, mid, width, max_profit, max_loss, breakeven, fill)


def candidates_of(expiries: list[hedge.Expiry], direction: str, slippage_per_leg: float, model: FillModel | None = None) -> list[Spread]:
    """Every vertical on the view's side over every pair of quoted strikes; a spread whose
    quotes leave nothing to win or nothing at risk is not a candidate."""
    per_share = 2.0 * slippage_per_leg / CONTRACT
    out: list[Spread] = []
    for e in expiries:
        calls = [leg for _, leg in sorted(e.calls.items())]
        puts = [leg for _, leg in sorted(e.puts.items())]
        for i, lo in enumerate(calls):
            for hi in calls[i + 1:]:
                if direction == "up":
                    out.append(spread("bull_call", e, lo, hi, per_share, model))
                else:
                    out.append(spread("bear_call", e, hi, lo, per_share, model))
        for i, lo in enumerate(puts):
            for hi in puts[i + 1:]:
                if direction == "up":
                    out.append(spread("bull_put", e, lo, hi, per_share, model))
                else:
                    out.append(spread("bear_put", e, hi, lo, per_share, model))
    return [s for s in out if s.max_profit > 0.0 and s.max_loss > 0.0]


# --- probabilities ---

NOT_DECLARED = "max-profit region is not the declared one"


def level_strike(strikes: list[float], level: float, direction: str) -> float | None:
    """(47) The quoted strike nearest the level; a tie goes to the near side, below the level
    for an up view and above it for a down view."""
    if not strikes:
        return None

    def key(k: float) -> tuple[float, int]:
        near = k <= level if direction == "up" else k >= level
        return abs(k - level), 0 if near else 1

    return min(strikes, key=key)


def p_view_of(s: Spread, direction: str, probability: float, level_strikes: dict[tuple[str, str], float | None]) -> tuple[float | None, str | None]:
    """(47) The declared probability applies only where the max-profit region is exactly the
    declared one: the short strike at the expiry's level strike for the spread's right; the
    long strike sits where the spread's definition puts it, any width. Else null with the
    reason; never interpolated or extrapolated."""
    right = "call" if s.kind in ("bull_call", "bear_call") else "put"
    at = level_strikes.get((s.expiry, right))
    if at is not None and s.short_strike == at:
        return probability, None
    return None, NOT_DECLARED


def p_market_of(s: Spread, e: hedge.Expiry) -> dict[str, float]:
    """The risk-neutral probabilities of the three payoff regions from the expiry's fitted density."""
    def cdf(k: float) -> float:
        return hedge.risk_neutral_cdf(e.smile, math.log(k / e.forward))

    up = s.kind in ("bull_call", "bull_put")
    hi, lo = max(s.long_strike, s.short_strike), min(s.long_strike, s.short_strike)
    p_above_hi, p_below_lo = 1.0 - cdf(hi), cdf(lo)
    p_max_profit = p_above_hi if up else p_below_lo
    p_max_loss = p_below_lo if up else p_above_hi
    p_profit = 1.0 - cdf(s.breakeven) if up else cdf(s.breakeven)
    return {"max_profit": p_max_profit, "between": max(0.0, 1.0 - p_max_profit - p_max_loss), "max_loss": p_max_loss, "beyond_breakeven": p_profit}


def ev_per_dollar_at_risk(p_view: float, max_profit: float, max_loss: float) -> float:
    return (p_view * max_profit - (1.0 - p_view) * max_loss) / max_loss


# --- the volatility diagnostic ---

def atm_iv(quotes: list[dict[str, object]], expiry: str, spot: float, t_years: float, rf: float) -> float | None:
    """The at-the-money implied volatility at an expiry from the straddle nearest spot:
    the call's and put's mids inverted under Black on spot compounded at rf, averaged."""
    forward = spot * math.exp(rf * t_years)
    rows = [q for q in quotes if q["expiration"] == expiry and float(str(q["bid"])) > 0.0]
    strikes = sorted({float(str(q["strike"])) for q in rows})
    if not strikes:
        return None
    k = min(strikes, key=lambda x: abs(x - spot))
    ivs: list[float] = []
    for right in ("call", "put"):
        q = next((q for q in rows if float(str(q["strike"])) == k and q["right"] == right), None)
        if q is None:
            continue
        w = hedge.implied_total_variance(right, forward, k, float(str(q["mid"])) * math.exp(rf * t_years))
        if w is not None:
            ivs.append(math.sqrt(w / t_years))
    return sum(ivs) / len(ivs) if ivs else None


def nearest_expiry(quotes: list[dict[str, object]], snapshot_date: str, horizon_days: int) -> tuple[str, int] | None:
    """The expiry at or beyond the horizon nearest to it, with its days."""
    d0 = date.fromisoformat(snapshot_date)
    best: tuple[int, str] | None = None
    for e in {str(q["expiration"]) for q in quotes}:
        days = (date.fromisoformat(e) - d0).days
        if days >= horizon_days and (best is None or days < best[0]):
            best = (days, e)
    return None if best is None else (best[1], best[0])


def realised_vol(closes: list[tuple[str, float]], horizon_days: int, end: str) -> tuple[float | None, int]:
    """Annualised standard deviation of daily log returns of the store's closes over the
    horizon's length of calendar days ending at [end]; the count of returns beside it."""
    d1 = date.fromisoformat(end)
    window = [(d, c) for d, c in sorted(closes) if 0 <= (d1 - date.fromisoformat(d)).days <= horizon_days and c > 0]
    rets = [math.log(b / a) for (_, a), (_, b) in zip(window, window[1:])]
    if len(rets) < 5:
        return None, len(rets)
    m = sum(rets) / len(rets)
    var = sum((r - m) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(var * 252.0), len(rets)


def percentile_of(value: float, history: list[float]) -> float | None:
    if not history:
        return None
    return 100.0 * sum(1 for h in history if h <= value) / len(history)


def event_line(record: boundary.Valuation | None) -> dict[str, object]:
    """(68) The volatility diagnostic's event line: what the option market charges for the
    next results release against what the last eight actually did.

    The two are not the same measurement and the line says so. The implied move is one
    standard deviation of the event under the market's own distribution, from the two expiries
    bracketing the release; the realised figure is the MEDIAN absolute excess move over the
    last eight, which is nearer the middle of the distribution than its standard deviation.
    The ratio is therefore expected to sit above one even where the market charges nothing
    for the event, and a reader who treats it as a spread to collect has misread it."""
    if record is None or record.earnings is None:
        return {"implied_event_move": None, "realised_median_abs_excess": None, "ratio": None,
                "sentence": None,
                "reason": ("no record in the run" if record is None
                           else record.earnings_reason or "the run's record carries no earnings block")}
    e = record.earnings
    implied = None if e.implied is None else e.implied.implied_move
    realised = e.calendar.realised_median_abs_excess
    ratio = e.implied_over_realised
    sentence = (None if implied is None or realised is None else
                f"the market charges {implied:.1%} for the release on {e.calendar.next_date} "
                f"({e.calendar.next_source}), {e.days_to_next} days out, against a median absolute excess "
                f"move of {realised:.1%} over the last {len(e.calendar.events)}")
    return {"implied_event_move": implied, "realised_median_abs_excess": realised, "ratio": ratio,
            "next_date": e.calendar.next_date, "next_source": e.calendar.next_source,
            "days_to_next": e.days_to_next, "events": len(e.calendar.events),
            "sentence": sentence, "reason": None if implied is not None else e.implied_reason,
            "note": "one standard deviation of the event under the market's distribution against the MEDIAN "
                    "absolute excess move realised: the ratio sits above one on a quiet name and is not a spread to collect"}


def vol_diagnostic(options: Path, ticker: str, snapshot_date: str, horizon_days: int, rf: float, *,
                   record: boundary.Valuation | None = None) -> dict[str, object]:
    """Reads the store's chains for the name over the last 250 snapshot dates at or before the
    view's snapshot: the ATM IV at the expiry nearest the horizon on each, the closes."""
    dates = sorted((d.name for d in options.iterdir() if d.is_dir() and d.name <= snapshot_date and (options / d.name / f"{ticker}.json").exists()), reverse=True)[:HISTORY_DATES]
    history: list[float] = []
    closes: list[tuple[str, float]] = []
    today_iv: float | None = None
    today_expiry: tuple[str, int] | None = None
    for d in dates:
        chain = json.loads((options / d / f"{ticker}.json").read_text())
        quotes: list[dict[str, object]] = [dict(q) for q in chain["quotes"]]
        spot = float(chain["underlying_close"])
        closes.append((str(chain["snapshot_date"]), spot))
        ne = nearest_expiry(quotes, str(chain["snapshot_date"]), horizon_days)
        if ne is None:
            continue
        iv = atm_iv(quotes, ne[0], spot, ne[1] / 365.0, rf)
        if iv is None:
            continue
        if d == dates[0]:
            today_iv, today_expiry = iv, ne
        else:
            history.append(iv)
    realised, n = realised_vol(closes, horizon_days, snapshot_date)
    pct = None if today_iv is None else percentile_of(today_iv, history)
    sentence = (None if today_iv is None or realised is None or pct is None
                else f"the market charges {today_iv:.1%} vol against {realised:.1%} realised, at the {pct:.0f}th percentile of the past year")
    return {"atm_expiry": None if today_expiry is None else today_expiry[0], "atm_days": None if today_expiry is None else today_expiry[1],
            "atm_implied_vol": today_iv, "realised_vol": realised, "realised_returns": n, "realised_window_days": horizon_days,
            "iv_percentile_over_history": pct, "history_snapshots": len(history), "sentence": sentence,
            "event": event_line(record),
            "note": "debit spreads pay the implied premium; credit spreads receive it; the ATM vol is the straddle nearest spot at the expiry nearest the horizon, inverted from mids"}


# --- the run ---

def candidate_json(s: Spread, pm: dict[str, float], pv: float | None, pv_reason: str | None, max_risk: float | None,
                   gate: hedge.EarningsGate | None = None) -> dict[str, object]:
    """(68) [gate] marks the candidate at the serialisation boundary, so neither ranking key
    can see it: a vertical held across a results release is a different instrument, and that
    is the holder's to weigh. Nothing is excluded and nothing is re-ordered."""
    ev = None if pv is None else ev_per_dollar_at_risk(pv, s.max_profit, s.max_loss)
    return {"kind": s.kind, "credit": s.credit, "expiry": s.expiry, "days_to_expiry": s.days, "long_strike": s.long_strike, "short_strike": s.short_strike,
            "width": s.width, "cost_per_share": s.cost, "cost_per_share_at_mid": s.cost_at_mid, "fill": s.fill, "max_profit_per_share": s.max_profit, "max_loss_per_share": s.max_loss,
            "breakeven": s.breakeven, "p_market": pm["max_profit"], "p_market_regions": pm, "risk_neutral": True, "p_view": pv, "p_view_reason": pv_reason,
            "ev_per_dollar_at_risk": ev, "disagreement": None if pv is None else pv - pm["max_profit"],
            "contracts_for_max_risk": None if max_risk is None else int(max_risk // (s.max_loss * CONTRACT)),
            **(gate.mark(s.expiry) if gate is not None else {})}


def express_one(v: View, chain: boundary.OptionChain, smiles: boundary.ChainSmiles, diagnostic: dict[str, object], model: FillModel | None = None,
                gate: hedge.EarningsGate | None = None) -> dict[str, object]:
    expiries, notes = hedge.expiries_in_window(smiles, chain, v.horizon_days, beyond=WINDOW_BEYOND_DAYS)
    by_expiry = {e.expiry: e for e in expiries}
    prob = float(v.probability or 0.0)
    level_strikes = {(e.expiry, right): level_strike(sorted(e.calls if right == "call" else e.puts), v.level, v.direction) for e in expiries for right in ("call", "put")}
    rows: list[dict[str, object]] = []
    for s in candidates_of(expiries, v.direction, v.slippage_per_leg, model):
        pv, reason = p_view_of(s, v.direction, prob, level_strikes)
        rows.append(candidate_json(s, p_market_of(s, by_expiry[s.expiry]), pv, reason, v.max_risk_usd, gate))
    ranked = sorted((r for r in rows if r["p_view"] is not None), key=lambda r: (-float(str(r["ev_per_dollar_at_risk"])), float(str(r["max_loss_per_share"])), str(r["kind"]), str(r["expiry"]), float(str(r["long_strike"])), float(str(r["short_strike"]))))
    unranked = sorted((r for r in rows if r["p_view"] is None), key=lambda r: (-float(str(r["p_market"])), float(str(r["max_loss_per_share"])), str(r["kind"]), str(r["expiry"]), float(str(r["long_strike"])), float(str(r["short_strike"]))))
    return {
        "ticker": v.ticker, "view": v.model_dump(), "snapshot_date": smiles.snapshot_date, "spot": smiles.spot, "risk_free_rate": smiles.risk_free_rate,
        "expiries": [{"expiry": e.expiry, "days_to_expiry": e.days, "forward": e.forward, "calls_quoted": len(e.calls), "puts_quoted": len(e.puts), "legs_excluded_stale": e.excluded_stale,
                      "level_strike_calls": level_strikes[(e.expiry, "call")], "level_strike_puts": level_strikes[(e.expiry, "put")]} for e in expiries],
        "mapping": "p_view applies only where the short strike is the quoted strike nearest the level (ties to the near side); the ranking answers how wide and debit or credit, the level is the holder's",
        "expiries_without_a_smile": notes,
        "pricing": (f"fill model {model.ticker}: each leg at the model's median fill position for its cell, a bought leg at bid + q50 x spread and a sold leg at bid + (1 - q50) x spread, the flat slippage not applied"
                    if model is not None else f"ask for what is bought, bid for what is sold, plus slippage_per_leg {v.slippage_per_leg:.2f} per contract per leg on both legs; the mid beside it"),
        "fill_model": None if model is None else {"ticker": model.ticker, "cells": len(model.by_cell), "overall_q50": None if model.overall is None else model.overall[0], "note": fm.SYMMETRY_NOTE},
        "candidates": rows, "ranked": ranked, "top": ranked[:10], "unranked_on_p_market": unranked,
        "market_prices_the_view_more_strongly": [r for r in ranked if float(str(r["p_market"])) > float(str(r["p_view"]))][:10],
        "vol_diagnostic": diagnostic, "risk_neutral_note": RISK_NEUTRAL_NOTE, "scope_limits": SCOPE_LIMITS,
        "earnings_gate": ({"next_date": None, "reason": None if gate is None else gate.reason} if gate is None or gate.next_date is None
                          else {"next_date": gate.next_date, "source": gate.next_source, "implied_move": gate.implied_move,
                                "spanning": sum(1 for r in rows if r.get("spans_earnings") is True), "candidates": len(rows),
                                "note": "a mark, never a filter: nothing is excluded or re-ranked by it"}),
    }


def draw(result: dict[str, object], png: Path) -> None:
    rows = hedge.points(result["candidates"])
    ranked = hedge.points(result["ranked"])
    fig, ax = plt.subplots(figsize=(9, 6))
    mappable = None
    for credit, marker, label in ((False, "o", "debit spreads"), (True, "^", "credit spreads")):
        pts = [r for r in ranked if bool(r["credit"]) == credit]
        if pts:
            mappable = ax.scatter([float(str(r["max_loss_per_share"])) for r in pts], [float(str(r["ev_per_dollar_at_risk"])) for r in pts], c=[float(str(r["p_market"])) for r in pts],
                                  cmap="viridis", vmin=0.0, vmax=1.0, marker=marker, s=14, alpha=0.7, label=f"{label} with p_view ({len(pts)})")
    # (68) the mark: colour is taken by p_market and the marker by credit/debit, so a
    # candidate expiring on or after the release gets a ring. Drawn, never filtered.
    spanning = [r for r in ranked if r.get("spans_earnings") is True]
    if spanning:
        gate = result.get("earnings_gate")
        when = gate.get("next_date") if isinstance(gate, dict) else None  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        ax.scatter([float(str(r["max_loss_per_share"])) for r in spanning], [float(str(r["ev_per_dollar_at_risk"])) for r in spanning],
                   s=48, facecolors="none", edgecolors="tab:orange", linewidths=0.6,
                   label=f"expires on or after earnings {when} ({len(spanning)}); marked, not excluded")
    if ranked and mappable is not None:
        fig.colorbar(mappable, ax=ax, label="p_market (risk-neutral probability of max profit)")
        top = ranked[0]
        ax.scatter([float(str(top["max_loss_per_share"]))], [float(str(top["ev_per_dollar_at_risk"]))], s=180, marker="*", color="tab:red", zorder=5,
                   label=f"top: {top['kind']} {top['long_strike']}/{top['short_strike']} {top['expiry']}")
    ax.axhline(0.0, color="tab:gray", linewidth=0.8)
    ax.set_xlabel("max_loss per share (capital at risk)")
    ax.set_ylabel("ev_per_dollar_at_risk under the holder's probability")
    view = hedge.points([result["view"]])[0]
    ax.set_title(f"{result['ticker']} on {result['snapshot_date']}: view {view['direction']} to {view['level']} in {view['horizon_days']} days at p = {view['probability']}; {len(rows)} candidates, {len(ranked)} with p_view", fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower right", fontsize=8)
    diag = hedge.points([result["vol_diagnostic"]])[0]
    event = diag.get("event")
    event_text = (str(e.get("sentence") or e.get("reason")) if isinstance(event, dict) and (e := {str(k): v for k, v in event.items()}) else "")  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType, reportUnknownMemberType]
    fig.text(0.01, 0.01, f"slippage {float(str(view['slippage_per_leg'])):.2f} per contract per leg; {diag.get('sentence') or 'no vol diagnostic'}; {event_text}; {RISK_NEUTRAL_NOTE}.", fontsize=7, wrap=True)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(png, dpi=120)
    plt.close(fig)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("views", type=Path)
    parser.add_argument("--options", type=Path, default=REPO_ROOT / "data" / "options")
    parser.add_argument("--run", type=Path, default=REPO_ROOT / "output")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "output" / "express")
    parser.add_argument("--rf", type=float, default=None)
    parser.add_argument("--fill-model", type=Path, default=None, help="the fill model directory (50): each leg priced at its cell's median fill instead of the flat slippage")
    args = parser.parse_args(argv)
    views = load_views(args.views)
    out_dir: Path = args.out / args.views.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    rc = 0
    for v in views.views:
        why_not = check_view(v)
        if why_not is not None:
            print(f"{v.ticker}: refused: {why_not}", file=sys.stderr)
            rc = 1
            continue
        chain_path = hedge.latest_chain(args.options, v.ticker, v.as_of_snapshot)
        if chain_path is None:
            print(f"{v.ticker}: refused: no options data for {v.ticker} in the store{' at or before ' + v.as_of_snapshot if v.as_of_snapshot else ''}; fetch it with: uv run python/fetch_options.py {v.ticker}", file=sys.stderr)
            rc = 1
            continue
        record = hedge.record_of(args.run, v.ticker)          # one scan, read twice
        rf = args.rf if args.rf is not None else hedge.rf_of(record)
        if rf is None:
            print(f"{v.ticker}: no risk-free rate on the run's record; pass --rf", file=sys.stderr)
            rc = 1
            continue
        chain = boundary.OptionChain.from_json_string(chain_path.read_text())
        smiles = hedge.smiles_of(chain_path, rf)
        diagnostic = vol_diagnostic(args.options, v.ticker, chain.snapshot_date, v.horizon_days, rf, record=record)
        model_path: Path | None = None if args.fill_model is None else args.fill_model / f"{v.ticker}.json"
        model = FillModel.load(model_path) if model_path is not None and model_path.exists() else None
        if args.fill_model is not None and model is None:
            print(f"{v.ticker}: no fill model at {model_path}; the flat slippage applies", file=sys.stderr)
        result = express_one(v, chain, smiles, diagnostic, model, hedge.earnings_gate(record, ticker=v.ticker))
        (out_dir / f"{v.ticker}.json").write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
        draw(result, out_dir / f"{v.ticker}.png")
        top = hedge.points(result["top"])
        head = f"{v.ticker} {chain.snapshot_date}: view {v.direction} to {v.level:g} in {v.horizon_days} days at p {v.probability}; {len(hedge.points(result['candidates']))} candidates, {len(hedge.points(result['ranked']))} with p_view; {'fill model' if model else 'ask/bid plus slippage'}; {diagnostic.get('sentence')}"
        print(head)
        for r in top[:3]:
            print(f"   {r['kind']} {r['long_strike']}/{r['short_strike']} {r['expiry']}: cost {float(str(r['cost_per_share'])):+.2f}, max profit {float(str(r['max_profit_per_share'])):.2f}, max loss {float(str(r['max_loss_per_share'])):.2f}, "
                  f"p_view {float(str(r['p_view'])):.2f}, p_market {float(str(r['p_market'])):.3f}, disagreement {float(str(r['disagreement'])):+.3f}, EV/$ {float(str(r['ev_per_dollar_at_risk'])):+.3f}")
        print(f"   {hedge.gate_line(result)}")
        event = diagnostic.get("event")
        if isinstance(event, dict):
            print(f"   event: {event.get('sentence') or event.get('reason')}")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
