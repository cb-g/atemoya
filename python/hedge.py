"""Hedging a single holding (38): four structures priced from the store's quotes, a
distribution-free Pareto set over cost, floor and cap, and a declared constraint that
selects. Nothing here prices a leg with a model, samples anything, or recommends without a
constraint; holdings are never tracked.

    uv run python/hedge.py holdings.json [--run output] [--options data/options] [--out output/hedge]

holdings.json: {"holdings": [{"ticker": "AAPL", "shares": 100, "horizon_days": 180,
"constraint": {"max_cost_pct": 0.03}}, ...]}, the constraint exactly one of
{"max_cost_pct": x}, {"min_floor_pct": y} or {"floor": "anchor"}; optional "as_of" picks
the store date (the latest snapshot at or before it), default the latest.

Structures, per share held, evaluated held to expiry: protective put (long put), collar
(long put, short call above it), put spread (long put, short lower put), covered call
(short call). For every expiry at least horizon_days out and within 120 days beyond, and
every quoted strike with a positive bid: cost is the ask for what is bought and the bid
for what is sold, the mid reported beside it; a structure whose leg has no quote is not a
candidate; a leg whose mid sits more than five vol points off the fitted smile of brief 36
(or does not invert) is a stale or junk quote and excludes the candidate. cost_pct is the
net premium over today's value (negative for a credit); floor_pct the worst outcome at
expiry including the premium over today's value (a put spread's worst is at zero, the
protection ending at the short strike; a covered call's is the premium alone); cap_pct the
best outcome where a short call binds, null otherwise. Position Greeks of holding plus
structure come from the smile at the quoted strikes (Black on the parity forward, no
dividends). The frontier is the exact Pareto set (lower cost, higher floor, higher or null
cap); the declared constraint selects from it; the floor: anchor constraint reads the
name's fair value from the latest run. One risk-neutral readout per selection: the
market's probability that the price at expiry is at or below the floor's strike, from the
same smile, flagged as everywhere."""

# pyright: reportUnknownMemberType=false
# matplotlib's Axes methods take **kwargs typed as Unknown; every call here passes only named, typed arguments.
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from pydantic import BaseModel, ConfigDict, ValidationError  # noqa: E402

import boundary  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
SMILE_BINARY = REPO_ROOT / "_build" / "default" / "ocaml" / "bin" / "smile.exe"
WINDOW_BEYOND_DAYS = 120
STALE_VOL_POINTS = 0.05
STRUCTURES = ("protective_put", "collar", "put_spread", "covered_call")
SCOPE_LIMITS = [
    "short calls carry assignment risk before expiry (American exercise), stated, not modelled",
    "every structure is evaluated held to expiry",
    "dividends inside the horizon are not modelled",
    "commissions are not included beyond the bid-ask spread",
    "the floor probability is risk-neutral: it embeds the market's risk pricing and is not a forecast",
]


class Constraint(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    max_cost_pct: float | None = None
    min_floor_pct: float | None = None
    floor: str | None = None

    def kind(self) -> str:
        given = [k for k, v in (("max_cost_pct", self.max_cost_pct), ("min_floor_pct", self.min_floor_pct), ("floor", self.floor)) if v is not None]
        if len(given) != 1:
            raise ValueError(f"constraint must be exactly one of max_cost_pct, min_floor_pct, floor: anchor; got {given}")
        if self.floor is not None and self.floor != "anchor":
            raise ValueError(f'floor must be "anchor", got {self.floor!r}')
        return given[0]


class Holding(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    ticker: str
    shares: float
    horizon_days: int
    constraint: Constraint


class Holdings(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    holdings: list[Holding]
    as_of: str | None = None


def load_holdings(path: Path) -> Holdings:
    try:
        h = Holdings.model_validate_json(path.read_text())
    except ValidationError as e:
        raise SystemExit(f"{path}: {e}") from e
    for entry in h.holdings:
        try:
            entry.constraint.kind()
        except ValueError as e:
            raise SystemExit(f"{path}: {entry.ticker}: {e}") from e
        if entry.shares <= 0 or entry.horizon_days <= 0:
            raise SystemExit(f"{path}: {entry.ticker}: shares and horizon_days must be positive")
    return h


# --- Black on the forward, and the smile ---

def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def black_undiscounted(right: str, forward: float, strike: float, w: float) -> float:
    if w <= 0.0:
        intrinsic = forward - strike if right == "call" else strike - forward
        return max(intrinsic, 0.0)
    s = math.sqrt(w)
    k = math.log(strike / forward)
    d1 = -k / s + s / 2.0
    d2 = -k / s - s / 2.0
    call = forward * norm_cdf(d1) - strike * norm_cdf(d2)
    return call if right == "call" else call - forward + strike


def implied_total_variance(right: str, forward: float, strike: float, price: float) -> float | None:
    """The total variance at which Black's undiscounted price equals price; None outside its bounds."""
    intrinsic = black_undiscounted(right, forward, strike, 0.0)
    upper = forward if right == "call" else strike
    if price <= intrinsic or price >= upper:
        return None
    lo, hi = 1e-10, 25.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if black_undiscounted(right, forward, strike, mid) < price:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def svi_w(s: boundary.SviSmile, k: float) -> float:
    d = k - s.m
    return s.a + s.b * (s.rho * d + math.sqrt(d * d + s.sigma * s.sigma))


def svi_dw(s: boundary.SviSmile, k: float) -> float:
    d = k - s.m
    return s.b * (s.rho + d / math.sqrt(d * d + s.sigma * s.sigma))


def risk_neutral_cdf(s: boundary.SviSmile, k: float) -> float:
    """P(ln(S_T / F) <= k) under the fitted smile, brief 36's closed form."""
    w = svi_w(s, k)
    sw = math.sqrt(w)
    dm = -k / sw - sw / 2.0
    return min(1.0, max(0.0, 1.0 - norm_cdf(dm) + norm_pdf(dm) * svi_dw(s, k) / (2.0 * sw)))


@dataclass(frozen=True)
class Greeks:
    """Per share of the underlying: delta in shares, gamma per unit of spot, vega per vol point, theta per day."""
    delta: float
    gamma: float
    vega: float
    theta: float

    def scaled(self, factor: float) -> Greeks:
        return Greeks(self.delta * factor, self.gamma * factor, self.vega * factor, self.theta * factor)

    def plus(self, other: Greeks) -> Greeks:
        return Greeks(self.delta + other.delta, self.gamma + other.gamma, self.vega + other.vega, self.theta + other.theta)


def option_greeks(right: str, spot: float, forward: float, strike: float, t: float, w: float, rf: float) -> Greeks:
    """Black's Greeks at the smile's total variance, no dividends: the forward is spot compounded at rf."""
    sigma = math.sqrt(w / t)
    s = math.sqrt(w)
    k = math.log(strike / forward)
    d1 = -k / s + s / 2.0
    d2 = -k / s - s / 2.0
    disc = math.exp(-rf * t)
    delta = norm_cdf(d1) if right == "call" else norm_cdf(d1) - 1.0
    gamma = norm_pdf(d1) / (spot * sigma * math.sqrt(t))
    vega = spot * norm_pdf(d1) * math.sqrt(t) / 100.0
    theta_common = -spot * norm_pdf(d1) * sigma / (2.0 * math.sqrt(t))
    theta = theta_common - rf * strike * disc * norm_cdf(d2) if right == "call" else theta_common + rf * strike * disc * norm_cdf(-d2)
    return Greeks(delta, gamma, vega, theta / 365.0)


# --- legs and candidates ---

@dataclass(frozen=True)
class Leg:
    right: str
    strike: float
    bid: float
    ask: float
    mid: float
    iv: float  # from the mid
    greeks: Greeks


@dataclass(frozen=True)
class Expiry:
    expiry: str
    days: int
    forward: float
    smile: boundary.SviSmile
    puts: dict[float, Leg]
    calls: dict[float, Leg]
    excluded_stale: int
    excluded_no_inversion: int


@dataclass(frozen=True)
class Candidate:
    structure: str
    expiry: str
    days: int
    long_put: float | None
    short_put: float | None
    short_call: float | None
    cost: float          # per share, ask for bought, bid for sold; negative for a credit
    cost_mid: float
    cost_pct: float
    floor_pct: float
    cap_pct: float | None
    floor_strike: float | None
    greeks: Greeks       # holding plus structure, per share held

    def key(self) -> tuple[float, float, float, str, str, float, float, float]:
        return (self.cost_pct, -self.floor_pct, -(self.cap_pct if self.cap_pct is not None else math.inf), self.structure, self.expiry,
                self.long_put or 0.0, self.short_put or 0.0, self.short_call or 0.0)

    def to_json(self) -> dict[str, object]:
        return {"structure": self.structure, "expiry": self.expiry, "days_to_expiry": self.days, "long_put": self.long_put, "short_put": self.short_put,
                "short_call": self.short_call, "cost_per_share": self.cost, "cost_per_share_at_mid": self.cost_mid, "cost_pct": self.cost_pct,
                "floor_pct": self.floor_pct, "cap_pct": self.cap_pct, "floor_strike": self.floor_strike,
                "position_greeks_per_share": {"delta": self.greeks.delta, "gamma": self.greeks.gamma, "vega": self.greeks.vega, "theta": self.greeks.theta}}


def expiries_in_window(smiles: boundary.ChainSmiles, chain: boundary.OptionChain, horizon_days: int, *, beyond: int = WINDOW_BEYOND_DAYS) -> tuple[list[Expiry], list[dict[str, object]]]:
    """Every expiry at least horizon_days out and within beyond days past it, with its quoted
    legs checked against the smile; the second list says why an expiry contributed nothing."""
    out: list[Expiry] = []
    notes: list[dict[str, object]] = []
    spot = smiles.spot
    rf = smiles.risk_free_rate
    for e in smiles.expiries:
        if e.days_to_expiry < horizon_days or e.days_to_expiry > horizon_days + beyond:
            continue
        if e.smile is None:
            notes.append({"expiry": e.expiry, "days_to_expiry": e.days_to_expiry, "reason": e.reason or "no smile"})
            continue
        t = e.days_to_expiry / 365.0
        growth = math.exp(rf * t)
        puts: dict[float, Leg] = {}
        calls: dict[float, Leg] = {}
        stale = 0
        no_inv = 0
        for q in chain.quotes:
            if q.expiration != e.expiry or q.bid <= 0.0:
                continue
            w_quote = implied_total_variance(q.right, e.forward, q.strike, q.mid * growth)
            if w_quote is None:
                no_inv += 1
                continue
            k = math.log(q.strike / e.forward)
            w_smile = svi_w(e.smile, k)
            if abs(math.sqrt(w_quote / t) - math.sqrt(w_smile / t)) > STALE_VOL_POINTS:
                stale += 1
                continue
            leg = Leg(q.right, q.strike, q.bid, q.ask, q.mid, math.sqrt(w_quote / t), option_greeks(q.right, spot, e.forward, q.strike, t, w_smile, rf))
            (puts if q.right == "put" else calls)[q.strike] = leg
        out.append(Expiry(e.expiry, e.days_to_expiry, e.forward, e.smile, puts, calls, stale, no_inv))
    return out, notes


def candidates_of(expiries: list[Expiry], spot: float) -> list[Candidate]:
    """Every structure at every quoted strike, per share held; the holding's own Greeks are delta one."""
    holding = Greeks(1.0, 0.0, 0.0, 0.0)
    out: list[Candidate] = []
    for e in expiries:
        for kp, p in sorted(e.puts.items()):
            out.append(Candidate("protective_put", e.expiry, e.days, kp, None, None, p.ask, p.mid, p.ask / spot, (kp - p.ask) / spot, None, kp, holding.plus(p.greeks)))
            for kc, c in sorted(e.calls.items()):
                if kc <= kp:
                    continue
                cost = p.ask - c.bid
                out.append(Candidate("collar", e.expiry, e.days, kp, None, kc, cost, p.mid - c.mid, cost / spot, (kp - cost) / spot, (kc - cost) / spot, kp,
                                     holding.plus(p.greeks).plus(c.greeks.scaled(-1.0))))
            for kl, low in sorted(e.puts.items()):
                if kl >= kp:
                    continue
                cost = p.ask - low.bid
                out.append(Candidate("put_spread", e.expiry, e.days, kp, kl, None, cost, p.mid - low.mid, cost / spot, (kp - kl - cost) / spot, None, kl,
                                     holding.plus(p.greeks).plus(low.greeks.scaled(-1.0))))
        for kc, c in sorted(e.calls.items()):
            out.append(Candidate("covered_call", e.expiry, e.days, None, None, kc, -c.bid, -c.mid, -c.bid / spot, c.bid / spot, (kc + c.bid) / spot, None,
                                 holding.plus(c.greeks.scaled(-1.0))))
    out.sort(key=Candidate.key)
    return out


def pareto(cands: list[Candidate]) -> list[Candidate]:
    """The exact Pareto set over (lower cost_pct, higher floor_pct, higher or null cap_pct):
    a candidate is dominated if another is at least as good on all three and strictly
    better on one. No weights, no optimiser."""
    if not cands:
        return []
    cost = np.array([c.cost_pct for c in cands])
    floor = np.array([c.floor_pct for c in cands])
    cap = np.array([c.cap_pct if c.cap_pct is not None else np.inf for c in cands])
    keep: list[Candidate] = []
    for i, c in enumerate(cands):
        at_least = (cost <= cost[i]) & (floor >= floor[i]) & (cap >= cap[i])
        strictly = (cost < cost[i]) | (floor > floor[i]) | (cap > cap[i])
        if not bool(np.any(at_least & strictly)):
            keep.append(c)
    keep.sort(key=Candidate.key)
    return keep


def select(frontier: list[Candidate], constraint: Constraint, *, anchor: float | None, spot: float) -> tuple[list[Candidate], str | None]:
    """The eligible frontier points in the constraint's order, the first being the selection,
    or the reason there is none."""
    kind = constraint.kind()
    if kind == "max_cost_pct":
        x = float(constraint.max_cost_pct or 0.0)
        eligible = sorted([c for c in frontier if c.cost_pct <= x], key=lambda c: (-c.floor_pct, c.cost_pct, c.key()))
        return eligible, None if eligible else f"no frontier point costs at most {x:.4f} of the holding"
    if kind == "min_floor_pct":
        y = float(constraint.min_floor_pct or 0.0)
        eligible = sorted([c for c in frontier if c.floor_pct >= y], key=lambda c: (c.cost_pct, -c.floor_pct, c.key()))
        return eligible, None if eligible else f"no frontier point floors at least {y:.4f} of the holding"
    if anchor is None:
        return [], "the anchor is not available: the name has no fair value in the run"
    if anchor > spot:
        return [], f"the anchor is above the price; nothing above it to insure (fair value {anchor:.2f}, spot {spot:.2f})"
    target = anchor / spot
    eligible = sorted([c for c in frontier if c.floor_pct >= target], key=lambda c: (c.cost_pct, -c.floor_pct, c.key()))
    return eligible, None if eligible else f"no frontier point floors at or above the anchor ({target:.4f} of spot)"


def floor_probability(c: Candidate, expiries: list[Expiry]) -> dict[str, object]:
    """The market's probability that the price at expiry is at or below the floor's strike."""
    if c.floor_strike is None:
        return {"value": None, "reason": "no floor strike: the covered call leaves the downside unhedged", "risk_neutral": True}
    e = next(x for x in expiries if x.expiry == c.expiry)
    p = risk_neutral_cdf(e.smile, math.log(c.floor_strike / e.forward))
    what = "the short put's strike, below which the protection ends" if c.structure == "put_spread" else "the long put's strike"
    return {"value": p, "strike": c.floor_strike, "strike_is": what, "expiry": c.expiry, "risk_neutral": True,
            "note": "risk-neutral: the probability embeds the market's risk pricing and is not a forecast"}


# --- the run ---

def smiles_of(chain_path: Path, rf: float, binary: Path = SMILE_BINARY) -> boundary.ChainSmiles:
    if not binary.exists():
        raise SystemExit(f"{binary} not built: run dune build first")
    r = subprocess.run([str(binary), str(chain_path), "--rf", f"{rf:.10f}"], capture_output=True, text=True, check=True)
    return boundary.ChainSmiles.from_json_string(r.stdout)


def record_of(run: Path, ticker: str) -> boundary.Valuation | None:
    for line in (run / "valuations.jsonl").read_text().splitlines():
        if line.strip():
            v = boundary.Valuation.from_json_string(line)
            if v.ticker == ticker:
                return v
    return None


def rf_of(v: boundary.Valuation | None) -> float | None:
    if v is None or v.inputs is None:
        return None
    i = v.inputs.value
    if isinstance(i, boundary.DcfMidcycle):
        return i.value.dcf.risk_free_rate.value
    if isinstance(i, boundary.ResidualIncomeInsurer):
        return i.value.core.risk_free_rate.value
    return i.value.risk_free_rate.value


def latest_chain(options: Path, ticker: str, as_of: str | None) -> Path | None:
    """The store's latest snapshot at or before as_of (default any) holding the name."""
    dates = sorted((d.name for d in options.iterdir() if d.is_dir() and (as_of is None or d.name <= as_of)), reverse=True)
    for d in dates:
        p = options / d / f"{ticker}.json"
        if p.exists():
            return p
    return None


def hedge_one(h: Holding, chain: boundary.OptionChain, smiles: boundary.ChainSmiles, *, anchor: float | None, anchor_reason: str | None) -> dict[str, object]:
    spot = smiles.spot
    expiries, notes = expiries_in_window(smiles, chain, h.horizon_days)
    cands = candidates_of(expiries, spot)
    frontier = pareto(cands)
    eligible, reason = select(frontier, h.constraint, anchor=anchor, spot=spot)
    selection = eligible[0] if eligible else None
    return {
        "ticker": h.ticker, "snapshot_date": smiles.snapshot_date, "spot": spot, "shares": h.shares, "value": h.shares * spot,
        "horizon_days": h.horizon_days, "risk_free_rate": smiles.risk_free_rate,
        "constraint": h.constraint.model_dump(exclude_none=True),
        "anchor": {"fair_value": anchor, "fair_value_over_spot": (anchor / spot) if anchor is not None else None, "reason": anchor_reason},
        "expiries": [{"expiry": e.expiry, "days_to_expiry": e.days, "forward": e.forward, "puts_quoted": len(e.puts), "calls_quoted": len(e.calls),
                      "legs_excluded_stale": e.excluded_stale, "legs_excluded_no_inversion": e.excluded_no_inversion} for e in expiries],
        "expiries_without_a_smile": notes,
        "pricing": "ask for what is bought, bid for what is sold; the mid beside it; a leg without a quote is not a candidate",
        "stale_rule": f"a leg whose mid's implied vol is more than {STALE_VOL_POINTS:.2f} off the fitted smile is excluded",
        "candidates": [c.to_json() for c in cands],
        "frontier": [c.to_json() for c in frontier],
        "eligible": [c.to_json() for c in eligible],
        "selection": None if selection is None else {**selection.to_json(), "floor_probability": floor_probability(selection, expiries)},
        "selection_reason": reason,
        "scope_limits": SCOPE_LIMITS,
    }


def points(entries: object) -> list[dict[str, object]]:
    return [{str(k): v for k, v in e.items()} for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType, reportUnknownMemberType]


def draw(result: dict[str, object], png: Path) -> None:
    cands = points(result["candidates"])
    frontier = points(result["frontier"])
    selected = points([result["selection"]])
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.scatter([float(str(c["cost_pct"])) for c in cands], [float(str(c["floor_pct"])) for c in cands], s=6, color="tab:gray", alpha=0.25, label=f"candidates ({len(cands)})")
    uncapped = [c for c in frontier if c["cap_pct"] is None]
    capped = [c for c in frontier if c["cap_pct"] is not None]
    # The Pareto set has three objectives; the line is its uncapped part (puts and put
    # spreads), the cost-floor frontier proper; the capped points sit beside it by colour.
    ax.plot([float(str(c["cost_pct"])) for c in uncapped], [float(str(c["floor_pct"])) for c in uncapped], marker="o", markersize=4, color="tab:blue", linewidth=1.5,
            label=f"frontier without a cap: puts and put spreads ({len(uncapped)} of the Pareto set's {len(frontier)})")
    if capped:
        sc = ax.scatter([float(str(c["cost_pct"])) for c in capped], [float(str(c["floor_pct"])) for c in capped], s=18, c=[float(str(c["cap_pct"])) for c in capped], cmap="viridis", label=f"collars and covered calls, coloured by cap ({len(capped)})")
        fig.colorbar(sc, ax=ax, label="cap_pct (best outcome at expiry over today's value)")
        step = max(1, len(capped) // 20)
        for c in capped[::step]:
            ax.annotate(f"cap {float(str(c['cap_pct'])):.2f}", (float(str(c["cost_pct"])), float(str(c["floor_pct"]))), fontsize=6, color="tab:blue", xytext=(3, 3), textcoords="offset points")
    if selected:
        sel = selected[0]
        ax.scatter([float(str(sel["cost_pct"]))], [float(str(sel["floor_pct"]))], s=160, marker="*", color="tab:red", zorder=5, label=f"selection: {sel['structure']} {sel['expiry']}")
    ax.set_xlabel("cost_pct (net premium over today's value; negative is a credit)")
    ax.set_ylabel("floor_pct (worst outcome at expiry over today's value)")
    ax.set_title(f"{result['ticker']} on {result['snapshot_date']}: {result['shares']} shares at {result['spot']}, horizon {result['horizon_days']} days")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower right", fontsize=8)
    fig.text(0.01, 0.01, "constraint: " + json.dumps(result["constraint"]) + (f"; {result['selection_reason']}" if result["selection_reason"] else "") + ". Held to expiry; quotes, not model prices; no forecast.", fontsize=7)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(png, dpi=120)
    plt.close(fig)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("holdings", type=Path)
    parser.add_argument("--run", type=Path, default=REPO_ROOT / "output")
    parser.add_argument("--options", type=Path, default=REPO_ROOT / "data" / "options")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "output" / "hedge")
    parser.add_argument("--rf", type=float, default=None, help="override the run's risk-free rate (needed for a name whose record carries none)")
    args = parser.parse_args(argv)
    holdings = load_holdings(args.holdings)
    out_dir: Path = args.out / args.holdings.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    rc = 0
    for h in holdings.holdings:
        chain_path = latest_chain(args.options, h.ticker, holdings.as_of)
        if chain_path is None:
            print(f"{h.ticker}: no options data{' at or before ' + holdings.as_of if holdings.as_of else ''}", file=sys.stderr)
            rc = 1
            continue
        record = record_of(args.run, h.ticker)
        rf = args.rf if args.rf is not None else rf_of(record)
        if rf is None:
            print(f"{h.ticker}: no risk-free rate on the run's record; pass --rf", file=sys.stderr)
            rc = 1
            continue
        anchor = record.fair_value if record is not None and record.status.kind == "Ok" else None
        anchor_reason = None if anchor is not None else ("no record in the run" if record is None else f"{record.status.kind}: {record.failed_reason}")
        chain = boundary.OptionChain.from_json_string(chain_path.read_text())
        smiles = smiles_of(chain_path, rf)
        result = hedge_one(h, chain, smiles, anchor=anchor, anchor_reason=anchor_reason)
        (out_dir / f"{h.ticker}.json").write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
        draw(result, out_dir / f"{h.ticker}.png")
        selected = points([result["selection"]])
        n_cands, n_front = len(points(result["candidates"])), len(points(result["frontier"]))
        if selected:
            s = selected[0]
            fp = points([s["floor_probability"]])
            fp_value = fp[0].get("value") if fp else None
            print(f"{h.ticker} {smiles.snapshot_date}: {n_cands} candidates, frontier {n_front}; selection {s['structure']} {s['expiry']} "
                  f"cost {float(str(s['cost_pct'])):+.4f} floor {float(str(s['floor_pct'])):.4f} cap {s['cap_pct']}, floor probability {fp_value}")
        else:
            print(f"{h.ticker} {smiles.snapshot_date}: {n_cands} candidates, frontier {n_front}; no selection: {result['selection_reason']}")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
