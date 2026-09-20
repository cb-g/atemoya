"""Hedging currency exposure with CME FX futures (43): a holder of a name whose value moves
with a foreign currency sells that currency forward for the horizon, and for a retail
account that means exchange-traded futures, standard or micro. Nothing here touches a
valuation record; holdings are never tracked.

    uv run python/hedge_fx.py holdings.json [--run output] [--options data/options] [--fetched data/reference] [--out output/hedge] [--no-vendor]

holdings.json: {"horizon_days": 180, "hedge_fraction": 1.0, "holdings": [{"ticker": "SAP",
"shares": 40, "exposure_currency": "EUR", "exposure_fraction": 1.0, "exposure_why": "...",
"exposure_as_of": "2026-09-20"}, ...]}. The exposure fraction is the holder's declaration,
in [0, 1], of the holding's value that moves with the currency; hedge_fraction, of the
exposure to hedge, must be written even at 1.0. A holding without a declared exposure is
listed and excluded; a currency not in reference/fx_futures.json is refused by name.

Value in dollars is shares x spot (the store's latest close, else the run's price). The
fair forward for the horizon is covered interest parity on the two currencies' risk-free
rates at the tenor nearest the horizon from the fetched curves, F = S (1 + r_usd T) /
(1 + r_ccy T), simple compounding; carry = (F - S) / S over the horizon, positive when the
hedged currency yields less than the dollar; a missing curve fails the holding with brief
29's refresher string. The vendor's front futures quote is fetched for the same currency
and compared with the parity forward, the difference recorded and flagged beyond 0.5%,
never used as the input. Contracts are whole: the combination of standard and micro
contracts leaving the smallest residual, the count and the residual reported, the margin
tied up from the table as a percent of the holding's value. The output is a deterministic
payoff grid: currency moves from -20% to +20% in 1% steps, the holding's dollar value at
the horizon unhedged and hedged, with the carry and the margin."""

# pyright: reportUnknownMemberType=false
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from pydantic import BaseModel, ConfigDict, ValidationError  # noqa: E402

import boundary  # noqa: E402
import fx_futures  # noqa: E402
import hedge  # noqa: E402
import reference  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
REFERENCE = REPO_ROOT / "reference"
PARITY_FLAG = 0.005
MOVES = [round(-0.20 + 0.01 * i, 2) for i in range(41)]
SCOPE_LIMITS = [
    "the contract expires on the exchange's schedule and must be rolled if the horizon is longer; rolling is not modelled",
    "margin calls before expiry are not modelled",
    "the exposure fraction is the holder's declaration, not an estimate",
    "the futures leg settles at the spot rate at the horizon; the residual exposure stays with the holder",
]
REFRESH_STRING = "risk-free curve not fetched for {country}: run python/refresh_rates.py with your FRED key"


class FxHolding(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    ticker: str
    shares: float
    exposure_currency: str | None = None
    exposure_fraction: float | None = None
    exposure_why: str | None = None
    exposure_as_of: str | None = None

    def declared(self) -> bool:
        return (self.exposure_currency is not None and self.exposure_fraction is not None and bool(self.exposure_why) and bool(self.exposure_as_of)
                and 0.0 <= self.exposure_fraction <= 1.0)


class FxHoldings(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    horizon_days: int
    hedge_fraction: float
    holdings: list[FxHolding]


def load_holdings(path: Path) -> FxHoldings:
    try:
        h = FxHoldings.model_validate_json(path.read_text())
    except ValidationError as e:
        raise SystemExit(f"{path}: {e}") from e
    if h.horizon_days <= 0 or not 0.0 <= h.hedge_fraction <= 1.0 or any(x.shares <= 0 for x in h.holdings):
        raise SystemExit(f"{path}: horizon_days positive, hedge_fraction in [0, 1], every shares positive")
    return h


# --- parity ---

TENOR_YEARS = {"1y": 1.0, "3y": 3.0, "5y": 5.0, "7y": 7.0, "10y": 10.0}


def nearest_tenor(curve: reference.Curve, t_years: float) -> tuple[str, float]:
    rates = dict(curve.rates)
    tenor = min(rates, key=lambda k: (abs(TENOR_YEARS.get(k, 99.0) - t_years), TENOR_YEARS.get(k, 99.0)))
    return tenor, rates[tenor]


def parity_forward(spot_usd_per_unit: float, r_usd: float, r_ccy: float, t_years: float) -> float:
    """F = S (1 + r_usd T) / (1 + r_ccy T), simple compounding, in dollars per unit."""
    return spot_usd_per_unit * (1.0 + r_usd * t_years) / (1.0 + r_ccy * t_years)


def usd_per_unit(quoted: float, quote: str) -> float:
    """A quote in either convention to dollars per unit of the currency."""
    return quoted if quote == "usd_per_unit" else 1.0 / quoted


# --- sizing ---

def contracts_for(units: float, standard: float, micro: float | None) -> tuple[int, int, float]:
    """The whole standard and micro contracts leaving the smallest absolute residual (in
    units of the currency); ties to fewer contracts; never fractional."""
    best: tuple[float, int, int] | None = None
    base = int(units // standard)
    for n_std in range(max(0, base - 1), base + 2):
        micros = [0] if micro is None else range(0, int(standard // micro) + 2)
        for n_mic in micros:
            residual = units - n_std * standard - n_mic * (micro or 0.0)
            key = (abs(residual), n_std + n_mic)
            if best is None or key < (best[0], best[1] + best[2]):
                best = (abs(residual), n_std, n_mic)
    assert best is not None
    return best[1], best[2], units - best[1] * standard - best[2] * (micro or 0.0)


# --- the grid ---

@dataclass(frozen=True)
class Plan:
    ticker: str
    currency: str
    value_usd: float
    exposure_fraction: float
    hedged_units: float          # units of the currency sold forward on the contracts
    spot: float                  # dollars per unit
    forward: float               # the parity forward, dollars per unit


def grid(p: Plan) -> list[dict[str, float]]:
    """For each currency move m: the holding's dollar value at the horizon unhedged (the
    declared fraction moves with the currency) and hedged (plus the futures leg, short the
    hedged units at the forward, settled at the moved spot)."""
    out: list[dict[str, float]] = []
    for m in MOVES:
        s_t = p.spot * (1.0 + m)
        unhedged = p.value_usd * (1.0 - p.exposure_fraction) + p.value_usd * p.exposure_fraction * (1.0 + m)
        futures = p.hedged_units * (p.forward - s_t)
        out.append({"move": m, "unhedged_usd": unhedged, "hedged_usd": unhedged + futures, "futures_leg_usd": futures})
    return out


# --- the run ---

def curve_of(rates: reference.RiskFreeRates, country: str) -> reference.Curve | None:
    return dict(rates.countries).get(country)


def hedge_one(h: FxHolding, top: FxHoldings, *, value_usd: float, spot_source: str, table: reference.FxFutures,
              rates: reference.RiskFreeRates, fx: reference.FxRates, countries: dict[str, str], vendor_quote: float | None) -> dict[str, object]:
    ccy = str(h.exposure_currency)
    fraction = float(h.exposure_fraction or 0.0)
    products = dict(table.contracts).get(ccy)
    if products is None:
        return {"ticker": h.ticker, "exposure_currency": ccy, "refused": f"{ccy} is not in reference/fx_futures.json: no CME future is transcribed for it; a proxy currency would be a declaration for a later brief"}
    rate = dict(fx.currencies).get(ccy)
    if rate is None:
        return {"ticker": h.ticker, "exposure_currency": ccy, "refused": f"fx not fetched for {ccy}/USD: run python/refresh_fx.py with your FRED key"}
    spot = rate.usd_per_unit
    t = top.horizon_days / 365.0
    us = curve_of(rates, "United States")
    country = countries.get(ccy, "")
    foreign = curve_of(rates, country) if country else None
    if us is None:
        return {"ticker": h.ticker, "exposure_currency": ccy, "refused": REFRESH_STRING.format(country="United States")}
    if foreign is None:
        return {"ticker": h.ticker, "exposure_currency": ccy, "refused": REFRESH_STRING.format(country=country or ccy)}
    tenor_us, r_usd = nearest_tenor(us, t)
    tenor_ccy, r_ccy = nearest_tenor(foreign, t)
    forward = parity_forward(spot, r_usd, r_ccy, t)
    carry = (forward - spot) / spot
    exposure_usd = value_usd * fraction * top.hedge_fraction
    units = exposure_usd / spot
    std, mic = products.standard, products.micro
    n_std, n_mic, residual_units = contracts_for(units, std.size, None if mic is None else mic.size)
    hedged_units = n_std * std.size + n_mic * (mic.size if mic else 0.0)
    margin = n_std * std.initial_margin_usd + n_mic * (mic.initial_margin_usd if mic else 0.0)
    vendor: dict[str, object]
    if vendor_quote is None:
        vendor = {"symbol": products.vendor_symbol, "quote": None, "residual_vs_parity": None, "flag": "vendor quote not fetched"}
    else:
        v_usd = usd_per_unit(vendor_quote, products.quote)
        resid = (v_usd - forward) / spot
        vendor = {"symbol": products.vendor_symbol, "quote": vendor_quote, "usd_per_unit": v_usd, "residual_vs_parity": resid,
                  "flag": (f"vendor front future differs from the parity forward by {resid:+.2%} of spot, beyond {PARITY_FLAG:.1%}; the parity forward is the input" if abs(resid) > PARITY_FLAG else None)}
    plan = Plan(h.ticker, ccy, value_usd, fraction, hedged_units, spot, forward)
    return {
        "ticker": h.ticker, "shares": h.shares, "value_usd": value_usd, "spot_source": spot_source,
        "exposure_currency": ccy, "exposure_fraction": fraction, "exposure_why": h.exposure_why, "exposure_as_of": h.exposure_as_of,
        "hedge_fraction": top.hedge_fraction, "exposure_to_hedge_usd": exposure_usd, "exposure_to_hedge_units": units,
        "fx": {"usd_per_unit": spot, "as_of": rate.as_of, "series": rate.series},
        "carry": {"forward_usd_per_unit": forward, "carry_over_horizon": carry, "carry_usd_on_hedged_units": hedged_units * (forward - spot),
                  "r_usd": r_usd, "tenor_usd": tenor_us, "r_ccy": r_ccy, "tenor_ccy": tenor_ccy, "country": country, "horizon_years": t,
                  "formula": "F = S (1 + r_usd T) / (1 + r_ccy T), simple compounding, from the fetched curves; positive carry when the hedged currency yields less than the dollar"},
        "vendor_check": vendor,
        "contracts": {"standard": {"product": std.product, "count": n_std, "size": std.size, "initial_margin_usd": std.initial_margin_usd},
                      "micro": None if mic is None else {"product": mic.product, "count": n_mic, "size": mic.size, "initial_margin_usd": mic.initial_margin_usd},
                      "hedged_units": hedged_units, "residual_units": residual_units, "residual_usd": residual_units * spot, "residual_pct_of_value": residual_units * spot / value_usd},
        "margin": {"initial_usd": margin, "pct_of_value": margin / value_usd, "as_published": table.as_of},
        "grid": grid(plan),
        "scope_limits": SCOPE_LIMITS,
    }


def spot_of(ticker: str, options: Path, run: Path) -> tuple[float, str] | None:
    p = hedge.latest_chain(options, ticker, None)
    if p is not None:
        return boundary.OptionChain.from_json_string(p.read_text()).underlying_close, f"options store, close on {p.parent.name}"
    r = hedge.record_of(run, ticker)
    if r is not None and r.price is not None:
        return r.price, f"the run's price ({r.as_of[:10]})"
    return None


def vendor_quotes(symbols: list[str]) -> dict[str, float]:
    """The vendor's last close per front-month continuous symbol; a symbol that fails is left out."""
    from typing import Any, cast  # noqa: PLC0415

    import yfinance as yf  # noqa: PLC0415

    out: dict[str, float] = {}
    for s in symbols:
        try:
            frame = cast(Any, yf.Ticker(s)).history(period="5d", auto_adjust=False)
            if not frame.empty:
                out[s] = float(frame["Close"].iloc[-1])
        except Exception:  # noqa: BLE001
            continue
    return out


def draw(results: list[dict[str, object]], png: Path, horizon_days: int) -> None:
    hedged = [r for r in results if "grid" in r]
    if not hedged:
        return
    fig, axes = plt.subplots(1, len(hedged), figsize=(6 * len(hedged), 5), squeeze=False)
    for ax, r in zip(axes[0], hedged):
        g = hedge.points(r["grid"])
        moves = [float(str(x["move"])) * 100 for x in g]
        ax.plot(moves, [float(str(x["unhedged_usd"])) for x in g], color="tab:gray", label="unhedged")
        ax.plot(moves, [float(str(x["hedged_usd"])) for x in g], color="tab:blue", label="hedged (futures leg included)")
        c = hedge.points([r["contracts"]])[0]
        m = hedge.points([r["margin"]])[0]
        ax.set_title(f"{r['ticker']}: {r['exposure_currency']} exposure {float(str(r['exposure_fraction'])):.0%} of {float(str(r['value_usd'])):,.0f} USD; residual {float(str(c['residual_pct_of_value'])):+.1%}, margin {float(str(m['pct_of_value'])):.1%}", fontsize=9)
        ax.set_xlabel(f"{r['exposure_currency']} move against the dollar at {horizon_days} days (%)")
        ax.set_ylabel("holding's dollar value at the horizon")
        ax.grid(True, alpha=0.3)
        ax.legend(loc="upper left", fontsize=8)
    fig.text(0.01, 0.01, "CME futures at the parity forward from the fetched curves; whole contracts; held to the horizon; no forecast.", fontsize=7)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(png, dpi=120)
    plt.close(fig)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("holdings", type=Path)
    parser.add_argument("--run", type=Path, default=REPO_ROOT / "output")
    parser.add_argument("--options", type=Path, default=REPO_ROOT / "data" / "options")
    parser.add_argument("--fetched", type=Path, default=REPO_ROOT / "data" / "reference")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "output" / "hedge")
    parser.add_argument("--no-vendor", action="store_true", help="skip the vendor's front futures quote (offline); the check is then marked not fetched")
    args = parser.parse_args(argv)
    top = load_holdings(args.holdings)
    table = fx_futures.load(REFERENCE / "fx_futures.json")
    rates = reference.RiskFreeRates.from_json_string((args.fetched / "risk_free_rates.json").read_text())
    fx = reference.FxRates.from_json_string((args.fetched / "fx_rates.json").read_text())
    countries = dict(reference.FxSources.from_json_string((REFERENCE / "fx_sources.json").read_text()).currency_countries)
    symbols = sorted({dict(table.contracts)[str(h.exposure_currency)].vendor_symbol for h in top.holdings if h.declared() and str(h.exposure_currency) in dict(table.contracts)})
    quotes = {} if args.no_vendor else vendor_quotes(symbols)
    results: list[dict[str, object]] = []
    for h in top.holdings:
        if not h.declared():
            results.append({"ticker": h.ticker, "excluded": "no declared exposure (exposure_currency, exposure_fraction in [0, 1], exposure_why and exposure_as_of are all required)"})
            continue
        spot = spot_of(h.ticker, args.options, args.run)
        if spot is None:
            results.append({"ticker": h.ticker, "excluded": "no spot: the name is neither in the store nor in the run"})
            continue
        products = dict(table.contracts).get(str(h.exposure_currency))
        vendor = None if products is None else quotes.get(products.vendor_symbol)
        results.append(hedge_one(h, top, value_usd=h.shares * spot[0], spot_source=spot[1], table=table, rates=rates, fx=fx, countries=countries, vendor_quote=vendor))
    out_dir: Path = args.out / args.holdings.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {"horizon_days": top.horizon_days, "hedge_fraction": top.hedge_fraction, "table_as_of": table.as_of, "holdings": results,
               "why_futures_only": "forwards are over the counter; options on FX futures enter when a quote source is declared, never priced at an assumed volatility"}
    (out_dir / "fx.json").write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
    draw(results, out_dir / "fx.png", top.horizon_days)
    for r in results:
        if "refused" in r:
            print(f"{r['ticker']}: refused: {r['refused']}")
        elif "excluded" in r:
            print(f"{r['ticker']}: excluded: {r['excluded']}")
        else:
            c, k, m, v = (hedge.points([r[x]])[0] for x in ("contracts", "carry", "margin", "vendor_check"))
            std, mic = hedge.points([c["standard"]])[0], hedge.points([c["micro"]])
            print(f"{r['ticker']} {r['exposure_currency']}: value {float(str(r['value_usd'])):,.0f} USD, hedge {float(str(r['exposure_to_hedge_units'])):,.0f} {r['exposure_currency']}; "
                  f"{std['count']} x {std['product']}" + (f" + {mic[0]['count']} x {mic[0]['product']}" if mic else "") +
                  f", residual {float(str(c['residual_pct_of_value'])):+.2%} of value; carry {float(str(k['carry_over_horizon'])):+.2%} ({k['tenor_usd']} {float(str(k['r_usd'])):.2%} vs {k['tenor_ccy']} {float(str(k['r_ccy'])):.2%}); "
                  f"margin {float(str(m['pct_of_value'])):.1%}; parity vs vendor {'' if v['residual_vs_parity'] is None else f'{float(str(v['residual_vs_parity'])):+.2%}'}{' FLAG' if v['flag'] and 'beyond' in str(v['flag']) else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
