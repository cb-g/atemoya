"""FX hedging with futures (43): parity and carry by hand in both quote conventions, the
standard-plus-micro selection on a fixture, the refusal of a currency not in the table,
three grid points by hand, the missing-curve string, and the strict loader."""

from __future__ import annotations

import json
import math
from pathlib import Path

import fx_futures
import hedge
import hedge_fx as hx
import pytest
import reference

TABLE = fx_futures.load(Path(__file__).resolve().parent.parent / "reference" / "fx_futures.json")


def curve(rates: dict[str, float]) -> reference.Curve:
    return reference.Curve(source="test", tier="official", as_of="2026-09-01", rates=list(rates.items()), estimated=[], tenor_used=[], notes=[])


def rates(countries: dict[str, dict[str, float]]) -> reference.RiskFreeRates:
    return reference.RiskFreeRates(max_age_days=45, tenors=["1y", "3y", "5y", "7y", "10y"], countries=[(k, curve(v)) for k, v in countries.items()], aliases=[], notes=[])


def fx(usd_per_unit: dict[str, float]) -> reference.FxRates:
    return reference.FxRates(source="test", notes=[], currencies=[(k, reference.FxRate(series="X", direction="usd_per_unit", as_of="2026-09-01", quoted=v, usd_per_unit=v)) for k, v in usd_per_unit.items()])


def holding(ticker: str, ccy: str | None = "EUR", fraction: float | None = 1.0) -> hx.FxHolding:
    return hx.FxHolding(ticker=ticker, shares=100.0, exposure_currency=ccy, exposure_fraction=fraction, exposure_why=None if ccy is None else "declared for the test", exposure_as_of=None if ccy is None else "2026-09-01")


TOP = hx.FxHoldings(horizon_days=365, hedge_fraction=1.0, holdings=[])
US = {"1y": 0.04, "3y": 0.045}


def test_parity_forward_and_carry_by_hand_in_both_conventions() -> None:
    # EUR at 1.10 dollars, one year, 4% dollar and 2% euro: F = 1.10 x 1.04 / 1.02
    assert math.isclose(hx.parity_forward(1.10, 0.04, 0.02, 1.0), 1.10 * 1.04 / 1.02)
    assert math.isclose(hx.usd_per_unit(1.10, "usd_per_unit"), 1.10) and math.isclose(hx.usd_per_unit(150.0, "units_per_usd"), 1.0 / 150.0)
    assert hx.nearest_tenor(curve({"1y": 0.04, "3y": 0.045, "7y": 0.05}), 0.5) == ("1y", 0.04)
    assert hx.nearest_tenor(curve({"7y": 0.05, "10y": 0.052}), 0.5) == ("7y", 0.05)  # the UK-style curve: the nearest available, recorded
    r = hx.hedge_one(holding("X"), TOP, value_usd=110000.0, spot_source="test", table=TABLE, rates=rates({"United States": US, "Germany": {"1y": 0.02}}), fx=fx({"EUR": 1.10}),
                     countries={"EUR": "Germany"}, vendor_quote=None)
    k = hedge.points([r["carry"]])[0]
    assert math.isclose(float(str(k["forward_usd_per_unit"])), 1.10 * 1.04 / 1.02) and math.isclose(float(str(k["carry_over_horizon"])), 1.04 / 1.02 - 1.0)
    assert k["tenor_usd"] == "1y" and k["tenor_ccy"] == "1y" and float(str(k["carry_over_horizon"])) > 0  # the euro yields less: positive carry
    # the vendor's quote is a flag, never the input: a 2% richer future is flagged, the parity forward stays
    v = hx.hedge_one(holding("X"), TOP, value_usd=110000.0, spot_source="test", table=TABLE, rates=rates({"United States": US, "Germany": {"1y": 0.02}}), fx=fx({"EUR": 1.10}),
                     countries={"EUR": "Germany"}, vendor_quote=1.10 * 1.04 / 1.02 * 1.02)
    vc = hedge.points([v["vendor_check"]])[0]
    assert "beyond" in str(vc["flag"]) and v["carry"] == r["carry"]


def test_standard_plus_micro_selection_minimises_the_residual() -> None:
    # 141,000 EUR: one 125,000 standard plus one 12,500 micro leaves 3,500; two micros would leave -9,000
    assert hx.contracts_for(141000.0, 125000.0, 12500.0) == (1, 1, 3500.0)
    # 135,000: one standard plus one micro leaves -2,500, closer than +10,000 with none
    n, m, res = hx.contracts_for(135000.0, 125000.0, 12500.0)
    assert (n, m) == (1, 1) and math.isclose(res, -2500.0)
    # no micro (the peso): whole standard contracts only, nearest
    assert hx.contracts_for(1_240_000.0, 500000.0, None) == (2, 0, 240000.0)
    assert hx.contracts_for(1_260_000.0, 500000.0, None)[0] == 3
    assert hx.contracts_for(0.0, 125000.0, 12500.0) == (0, 0, 0.0)


def test_a_currency_not_in_the_table_is_refused_by_name() -> None:
    r = hx.hedge_one(holding("TSM", "TWD"), TOP, value_usd=1000.0, spot_source="test", table=TABLE, rates=rates({"United States": US, "Taiwan": {"1y": 0.015}}), fx=fx({"TWD": 0.033}),
                     countries={"TWD": "Taiwan"}, vendor_quote=None)
    assert r["refused"] == "TWD is not in reference/fx_futures.json: no CME future is transcribed for it; a proxy currency would be a declaration for a later brief"


def test_the_grid_at_three_points_by_hand() -> None:
    # value 100,000 USD, 80% moving with the euro, 60,000 EUR sold forward at F = 1.12 against spot 1.10
    p = hx.Plan("X", "EUR", 100000.0, 0.8, 60000.0, 1.10, 1.12)
    g = {row["move"]: row for row in hx.grid(p)}
    assert len(g) == 41 and min(g) == -0.2 and max(g) == 0.2
    # at 0: unhedged 100,000; the futures leg earns the carry 60,000 x 0.02
    assert math.isclose(g[0.0]["unhedged_usd"], 100000.0) and math.isclose(g[0.0]["hedged_usd"], 100000.0 + 60000.0 * 0.02)
    # at -10%: unhedged loses 8,000; the leg gains 60,000 x (1.12 - 0.99)
    assert math.isclose(g[-0.1]["unhedged_usd"], 92000.0) and math.isclose(g[-0.1]["hedged_usd"], 92000.0 + 60000.0 * (1.12 - 0.99))
    # at +10%: unhedged gains 8,000; the leg loses 60,000 x (1.21 - 1.12); the residual 20,000 USD of exposure keeps the slope
    assert math.isclose(g[0.1]["unhedged_usd"], 108000.0) and math.isclose(g[0.1]["hedged_usd"], 108000.0 - 60000.0 * (1.21 - 1.12))


def test_a_missing_curve_names_the_refresher() -> None:
    r = hx.hedge_one(holding("X", "JPY"), TOP, value_usd=1000.0, spot_source="test", table=TABLE, rates=rates({"United States": US}), fx=fx({"JPY": 0.0067}),
                     countries={"JPY": "Japan"}, vendor_quote=None)
    assert r["refused"] == "risk-free curve not fetched for Japan: run python/refresh_rates.py with your FRED key"


def test_the_table_loads_strictly() -> None:
    text = json.dumps(json.loads((Path(__file__).resolve().parent.parent / "reference" / "fx_futures.json").read_text()))
    assert dict(fx_futures.load_text(text).contracts)["EUR"].standard.size == 125000
    bad = json.loads(text)
    bad["contracts"]["EUR"]["standard"]["fetched_margin"] = 1
    with pytest.raises(fx_futures.FxFuturesError, match="unknown field"):
        fx_futures.load_text(json.dumps(bad))
    bad = json.loads(text)
    bad["contracts"]["EUR"]["quote"] = "eur_per_usd"
    with pytest.raises(fx_futures.FxFuturesError, match="quote must be one of"):
        fx_futures.load_text(json.dumps(bad))
    bad = json.loads(text)
    del bad["contracts"]["JPY"]["standard"]["initial_margin_usd"]
    with pytest.raises(fx_futures.FxFuturesError, match="lacks initial_margin_usd"):
        fx_futures.load_text(json.dumps(bad))
    # a holding without a declared exposure is not declared; a fraction outside [0, 1] neither
    assert not holding("X", None, None).declared() and not holding("X", "EUR", 1.5).declared() and holding("X").declared()
