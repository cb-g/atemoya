"""Hedging a book with one index product (41): brief 38's structures, quotes, Pareto set,
constraint and risk-neutral readout on the index's own chain, sized by each holding's
declared beta. The only new arithmetic is the book's exposure and its floor and cap on the
index payoff.

    uv run python/hedge_book.py book.json [--run output] [--options data/options] [--out output/hedge]

book.json: {"index": "SPY", "horizon_days": 180, "constraint": {"max_cost_pct": 0.02},
"min_cap_pct": 1.2 (optional), "as_of": "2026-09-17" (optional), "holdings": [{"ticker":
"AAPL", "shares": 100, "beta": 1.2, "beta_why": "...", "beta_as_of": "2026-09-01"}, ...]}.
Beta is declared, with a why and a date; python/beta.py reports a regression beside it that
this tool never reads. A holding without a declared beta is listed and excluded.

Exposure: each holding's index-equivalent exposure is shares x spot x beta, the book's the
sum; index contracts = book exposure / (index spot x multiplier), rounded to the nearest
whole contract with the residual exposure reported, fractional cover never assumed. For an
index move m the book moves by the exposure times m (floored at zero) and the structure,
held on contracts x multiplier index shares, pays on the index; floor_pct and cap_pct are
the worst and best outcomes at expiry over today's book value, cost_pct the quoted cost
over book value. A cap is hard only when the short call covers the exposure; otherwise
the book keeps moving beyond the strike at the residual slope, recorded. Exact for the
declared betas, and wrong exactly when the holdings' co-movement with the index breaks."""

# pyright: reportUnknownMemberType=false
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

import boundary
import hedge

REPO_ROOT = Path(__file__).resolve().parent.parent
MULTIPLIERS = {"SPY": 100}
DEFAULT_MULTIPLIER = 100
SCOPE_LIMITS = hedge.SCOPE_LIMITS + [
    "the book moves with the index by the declared betas: exact for those betas, and wrong exactly when the holdings' co-movement with the index breaks, which is when hedges are needed most",
    "contracts are whole; the residual exposure is unhedged and reported",
]


class BookHolding(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    ticker: str
    shares: float
    beta: float | None = None
    beta_why: str | None = None
    beta_as_of: str | None = None

    def declared(self) -> bool:
        return self.beta is not None and bool(self.beta_why) and bool(self.beta_as_of)


class Book(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    index: str
    horizon_days: int
    constraint: hedge.Constraint
    min_cap_pct: float | None = None
    as_of: str | None = None
    holdings: list[BookHolding]


def load_book(path: Path) -> Book:
    try:
        b = Book.model_validate_json(path.read_text())
    except ValidationError as e:
        raise SystemExit(f"{path}: {e}") from e
    try:
        b.constraint.kind()
    except ValueError as e:
        raise SystemExit(f"{path}: {e}") from e
    if b.horizon_days <= 0 or any(h.shares <= 0 for h in b.holdings):
        raise SystemExit(f"{path}: horizon_days and every shares must be positive")
    return b


@dataclass(frozen=True)
class Exposure:
    ticker: str
    shares: float
    spot: float
    spot_source: str
    beta: float
    value: float
    exposure: float


def exposures(holdings: list[BookHolding], spots: dict[str, tuple[float, str]]) -> tuple[list[Exposure], list[dict[str, object]]]:
    """Included holdings with their index-equivalent exposure, and the excluded ones with the reason."""
    included: list[Exposure] = []
    excluded: list[dict[str, object]] = []
    for h in holdings:
        if not h.declared():
            excluded.append({"ticker": h.ticker, "reason": "no declared beta (beta, beta_why and beta_as_of are all required)"})
            continue
        if h.ticker not in spots:
            excluded.append({"ticker": h.ticker, "reason": "no spot: the name is neither in the store on the snapshot date nor in the run"})
            continue
        spot, source = spots[h.ticker]
        beta = float(h.beta or 0.0)
        included.append(Exposure(h.ticker, h.shares, spot, source, beta, h.shares * spot, h.shares * spot * beta))
    return included, excluded


def contracts_for(exposure: float, index_spot: float, multiplier: int) -> tuple[int, float]:
    """Whole contracts nearest to the exposure, and the residual exposure (signed) left unhedged."""
    n = int(round(exposure / (index_spot * multiplier)))
    return n, exposure - n * index_spot * multiplier


def book_outcome(m: float, *, book_value: float, exposure: float, index_spot: float, index_shares: float, c: hedge.Candidate) -> float:
    """The book plus the structure at expiry for an index move m, the book floored at zero."""
    s_t = index_spot * (1.0 + m)
    book = max(book_value + exposure * m, 0.0)
    payoff = 0.0
    if c.long_put is not None:
        payoff += max(c.long_put - s_t, 0.0)
    if c.short_put is not None:
        payoff -= max(c.short_put - s_t, 0.0)
    if c.short_call is not None:
        payoff -= max(s_t - c.short_call, 0.0)
    return book + index_shares * (payoff - c.cost)


def book_candidate(c: hedge.Candidate, *, book_value: float, exposure: float, index_spot: float, index_shares: float) -> hedge.Candidate:
    """Brief 38's index candidate re-evaluated for the book: cost, floor and cap over the
    book's value; the Greeks in index-share equivalents (the book's delta is exposure over
    the index spot)."""
    def outcome(m: float) -> float:
        return book_outcome(m, book_value=book_value, exposure=exposure, index_spot=index_spot, index_shares=index_shares, c=c)

    # The outcome is piecewise linear in the index move: its kinks are the strikes, the move
    # at which the book reaches zero, and the ends; the worst outcome sits on one of them.
    kinks = [-1.0, 0.0] + [k / index_spot - 1.0 for k in (c.long_put, c.short_put, c.short_call) if k is not None]
    if exposure > 0.0:
        kinks.append(max(-1.0, -book_value / exposure))
    floor = min(outcome(m) for m in kinks)
    cost = index_shares * c.cost
    cap: float | None = None
    if c.short_call is not None:
        cap = outcome(c.short_call / index_spot - 1.0)
    idx_delta = exposure / index_spot
    structure = c.greeks.plus(hedge.Greeks(-1.0, 0.0, 0.0, 0.0))  # the single-name candidate held delta one of the underlying; strip it
    greeks = hedge.Greeks(idx_delta, 0.0, 0.0, 0.0).plus(structure.scaled(index_shares))
    return hedge.Candidate(c.structure, c.expiry, c.days, c.long_put, c.short_put, c.short_call, cost, index_shares * c.cost_mid,
                           cost / book_value, floor / book_value, None if cap is None else cap / book_value, c.floor_strike, greeks)


def book_json(c: hedge.Candidate) -> dict[str, object]:
    """The single-name candidate's JSON with the cost keys named for what they are on a book:
    the structure's cost on every covered index share, and the Greeks in index-share terms."""
    j = c.to_json()
    j["cost_on_covered_index_shares"] = j.pop("cost_per_share")
    j["cost_on_covered_index_shares_at_mid"] = j.pop("cost_per_share_at_mid")
    j["position_greeks_in_index_shares"] = j.pop("position_greeks_per_share")
    return j


def hedge_book(book: Book, chain: boundary.OptionChain, smiles: boundary.ChainSmiles, spots: dict[str, tuple[float, str]], *, anchor: float | None, anchor_reason: str | None) -> dict[str, object]:
    index_spot = smiles.spot
    multiplier = MULTIPLIERS.get(book.index, DEFAULT_MULTIPLIER)
    included, excluded = exposures(book.holdings, spots)
    book_value = sum(e.value for e in included)
    exposure = sum(e.exposure for e in included)
    n_contracts, residual = contracts_for(exposure, index_spot, multiplier)
    index_shares = float(n_contracts * multiplier)
    expiries, notes = hedge.expiries_in_window(smiles, chain, book.horizon_days)
    per_share = hedge.candidates_of(expiries, index_spot)
    cands = sorted((book_candidate(c, book_value=book_value, exposure=exposure, index_spot=index_spot, index_shares=index_shares) for c in per_share), key=hedge.Candidate.key) if book_value > 0 and index_shares > 0 else []
    frontier = hedge.pareto(cands)
    eligible, reason = hedge.select(frontier, book.constraint, anchor=anchor, spot=book_value, min_cap_pct=book.min_cap_pct) if cands else ([], "no candidates: the book has no value or rounds to zero contracts")
    _, selectable_note = hedge.selectable(frontier, book.min_cap_pct)
    selection = eligible[0] if eligible else None
    slope_beyond_cap = exposure - index_shares * index_spot
    return {
        "index": book.index, "snapshot_date": smiles.snapshot_date, "index_spot": index_spot, "contract_multiplier": multiplier,
        "horizon_days": book.horizon_days, "risk_free_rate": smiles.risk_free_rate,
        "holdings": [{"ticker": e.ticker, "shares": e.shares, "spot": e.spot, "spot_source": e.spot_source, "beta": e.beta, "value": e.value, "index_equivalent_exposure": e.exposure} for e in included],
        "excluded": excluded,
        "book_value": book_value, "book_exposure": exposure, "contracts": n_contracts, "index_shares_covered": index_shares,
        "residual_exposure": residual, "residual_exposure_pct": (residual / book_value) if book_value else None,
        "upside_slope_beyond_a_short_call": slope_beyond_cap,
        "cap_is_hard": slope_beyond_cap <= 0.0,
        "constraint": book.constraint.model_dump(exclude_none=True), "min_cap_pct": book.min_cap_pct, "selectable": selectable_note,
        "anchor": {"fair_value_of_the_book": anchor, "over_book_value": (anchor / book_value) if anchor is not None and book_value else None, "reason": anchor_reason},
        "expiries": [{"expiry": e.expiry, "days_to_expiry": e.days, "forward": e.forward, "puts_quoted": len(e.puts), "calls_quoted": len(e.calls),
                      "legs_excluded_stale": e.excluded_stale, "legs_excluded_no_inversion": e.excluded_no_inversion} for e in expiries],
        "expiries_without_a_smile": notes,
        "pricing": "index quotes: ask for what is bought, bid for what is sold, on contracts x multiplier index shares; the mid beside it",
        "candidates": [book_json(c) for c in cands],
        "frontier": [book_json(c) for c in frontier],
        "eligible": [book_json(c) for c in eligible],
        "selection": None if selection is None else {**book_json(selection), "floor_probability": hedge.floor_probability(selection, expiries)},
        "selection_reason": reason,
        "scope_limits": SCOPE_LIMITS,
    }


def spots_of(book: Book, options: Path, run: Path, snapshot_date: str) -> dict[str, tuple[float, str]]:
    """Each holding's spot: the store's underlying close on the index's snapshot date when the
    name is in the store that day, else the run's price."""
    out: dict[str, tuple[float, str]] = {}
    for h in book.holdings:
        p = options / snapshot_date / f"{h.ticker}.json"
        if p.exists():
            out[h.ticker] = (boundary.OptionChain.from_json_string(p.read_text()).underlying_close, f"options store, close on {snapshot_date}")
            continue
        r = hedge.record_of(run, h.ticker)
        if r is not None and r.price is not None:
            out[h.ticker] = (r.price, f"the run's price ({r.as_of[:10]})")
    return out


def anchor_of(book: Book, run: Path) -> tuple[float | None, str | None]:
    total = 0.0
    for h in book.holdings:
        if not h.declared():
            continue
        r = hedge.record_of(run, h.ticker)
        if r is None or r.status.kind != "Ok" or r.fair_value is None:
            return None, f"the book's anchor is not available: {h.ticker} has no fair value in the run ({'no record' if r is None else r.failed_reason})"
        total += h.shares * r.fair_value
    return total, None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("book", type=Path)
    parser.add_argument("--run", type=Path, default=REPO_ROOT / "output")
    parser.add_argument("--options", type=Path, default=REPO_ROOT / "data" / "options")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "output" / "hedge")
    parser.add_argument("--rf", type=float, default=None)
    args = parser.parse_args(argv)
    book = load_book(args.book)
    chain_path = hedge.latest_chain(args.options, book.index, book.as_of)
    if chain_path is None:
        print(f"{book.index}: not in the options store{' at or before ' + book.as_of if book.as_of else ''}; fetch it with: uv run python/fetch_options.py {book.index}", file=sys.stderr)
        return 1
    chain = boundary.OptionChain.from_json_string(chain_path.read_text())
    rf = args.rf
    if rf is None:
        rates = [r for r in (hedge.rf_of(hedge.record_of(args.run, h.ticker)) for h in book.holdings) if r is not None]
        rf = rates[0] if rates else None
    if rf is None:
        print("no risk-free rate on any holding's record; pass --rf", file=sys.stderr)
        return 1
    smiles = hedge.smiles_of(chain_path, rf)
    spots = spots_of(book, args.options, args.run, chain.snapshot_date)
    anchor, anchor_reason = anchor_of(book, args.run) if book.constraint.kind() == "floor" else (None, None)
    result = hedge_book(book, chain, smiles, spots, anchor=anchor, anchor_reason=anchor_reason)
    out_dir: Path = args.out / args.book.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "book.json").write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
    hedge.draw(result, out_dir / "book.png",
               title=f"book of {len(hedge.points(result['holdings']))} on {book.index}, {smiles.snapshot_date}: value {result['book_value']:,.0f}, "
                     f"exposure {result['book_exposure']:,.0f}, {result['contracts']} contract(s) at index {result['index_spot']}, horizon {book.horizon_days} days")
    sel = hedge.points([result["selection"]])
    head = (f"book on {book.index} {smiles.snapshot_date}: value {result['book_value']:,.0f}, exposure {result['book_exposure']:,.0f}, "
            f"{result['contracts']} contracts (residual {result['residual_exposure']:,.0f}); {len(hedge.points(result['candidates']))} candidates, frontier {len(hedge.points(result['frontier']))}; {result['selectable']}; ")
    if sel:
        s = sel[0]
        fp = hedge.points([s["floor_probability"]])
        print(head + f"selection {s['structure']} {s['expiry']} cost {float(str(s['cost_pct'])):+.4f} floor {float(str(s['floor_pct'])):.4f} cap {s['cap_pct']}, floor probability {fp[0].get('value') if fp else None}")
    else:
        print(head + f"no selection: {result['selection_reason']}")
    for x in hedge.points(result["excluded"]):
        print(f"  excluded {x['ticker']}: {x['reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
