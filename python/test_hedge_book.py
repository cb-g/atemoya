"""A book hedged with index options (41): exposure and whole contracts, the book's floor and
cap on a two-beta fixture by hand, the regression recovering a known beta, and the
declared beta being what the hedge reads even when the regression differs."""

from __future__ import annotations

import math
from datetime import date, timedelta

import beta as beta_mod
import hedge
import hedge_book as hb
import pit
import pytest
from test_hedge import fixture


def holding(ticker: str, shares: float, beta: float | None) -> hb.BookHolding:
    return hb.BookHolding(ticker=ticker, shares=shares, beta=beta, beta_why=None if beta is None else "declared for the test", beta_as_of=None if beta is None else "2026-09-01")


def test_exposure_and_whole_contracts() -> None:
    spots = {"A": (50.0, "test"), "B": (200.0, "test")}
    included, excluded = hb.exposures([holding("A", 100, 2.0), holding("B", 10, 0.5), holding("C", 5, None)], spots)
    assert [e.exposure for e in included] == [100 * 50 * 2.0, 10 * 200 * 0.5] and sum(e.value for e in included) == 7000.0
    assert excluded == [{"ticker": "C", "reason": "no declared beta (beta, beta_why and beta_as_of are all required)"}]
    n, residual = hb.contracts_for(11000.0, 100.0, 100)  # 1.1 contracts rounds to 1, residual 1000
    assert (n, residual) == (1, 1000.0)
    assert hb.contracts_for(14999.0, 100.0, 100)[0] == 1 and hb.contracts_for(15001.0, 100.0, 100)[0] == 2


def test_book_floor_and_cap_by_hand() -> None:
    # two holdings: 100 shares at 50 with beta 2 and 10 at 200 with beta 0.5: value 7000, exposure 11000;
    # index at 100, one contract (100 index shares), residual exposure 1000
    book_value, exposure, index_spot, shares = 7000.0, 11000.0, 100.0, 100.0
    put = hedge.Candidate("protective_put", "e", 365, 90.0, None, None, 3.0, 2.8, 0.03, 0.87, None, 90.0, hedge.Greeks(1, 0, 0, 0))
    b = hb.book_candidate(put, book_value=book_value, exposure=exposure, index_spot=index_spot, index_shares=shares)
    # below the strike the book loses 11000 per unit move while the put on 100 index shares gains
    # 10000, so the worst outcome is where the book reaches zero, m0 = -7000 / 11000, the put
    # then worth 90 - 100 (1 + m0) per index share less the 3 premium
    m0 = -book_value / exposure
    worst = shares * (90.0 - index_spot * (1.0 + m0)) - shares * 3.0
    assert math.isclose(b.floor_pct, worst / book_value) and math.isclose(worst, 5063.636363636364)
    assert math.isclose(b.cost_pct, shares * 3.0 / book_value) and b.cap_pct is None
    # the same put on a book whose exposure the contract fully covers floors at the strike
    small = hb.book_candidate(put, book_value=7000.0, exposure=9000.0, index_spot=index_spot, index_shares=shares)
    assert math.isclose(small.floor_pct, (7000.0 - 9000.0 * 0.10 - shares * 3.0) / 7000.0)
    collar = hedge.Candidate("collar", "e", 365, 90.0, None, 110.0, 1.0, 0.9, 0.01, 0.89, 1.09, 90.0, hedge.Greeks(1, 0, 0, 0))
    c = hb.book_candidate(collar, book_value=book_value, exposure=exposure, index_spot=index_spot, index_shares=shares)
    # the cap is the outcome at the call strike: book up 10% of exposure, the structure costing 1 per index share
    assert c.cap_pct is not None and math.isclose(c.cap_pct, (book_value + exposure * 0.10 - shares * 1.0) / book_value)
    assert math.isclose(c.floor_pct, (shares * (90.0 - index_spot * (1.0 - book_value / exposure)) - shares * 1.0) / book_value)
    # Greeks: the book's delta in index shares is exposure / index spot, plus the structure on 100 shares
    assert math.isclose(c.greeks.delta, exposure / index_spot + shares * (1.0 - 1.0))


def synthetic(beta: float, *, weeks: int = 104, seed: int = 7) -> tuple[dict[date, float], dict[date, float]]:
    """Weekly closes where the asset's log return is beta times the index's plus a small
    deterministic wobble; no sampling, the wobble is a fixed sinusoid."""
    start = date(2024, 1, 5)
    index: dict[date, float] = {}
    asset: dict[date, float] = {}
    pi, pa = 100.0, 50.0
    for w in range(weeks):
        d = start + timedelta(weeks=w)
        ri = 0.01 * math.sin(w * 0.9 + seed) + 0.002 * math.cos(w * 0.31)
        ra = beta * ri + 0.001 * math.sin(w * 2.3)
        pi *= math.exp(ri)
        pa *= math.exp(ra)
        index[d] = pi
        asset[d] = pa
    return asset, index


def test_regression_recovers_a_known_beta() -> None:
    asset, index = synthetic(1.7)
    r = beta_mod.regression(asset, index)
    assert r is not None
    b, se, r2, n = r
    assert abs(b - 1.7) < 0.05 and r2 > 0.9 and n > 80 and se < 0.1
    assert beta_mod.regression({date(2026, 1, 1): 1.0}, index) is None


def test_the_declared_beta_is_what_the_hedge_reads() -> None:
    chain, smiles = fixture()  # the single-name fixture's chain stands in as the index's, spot 100
    asset, index = synthetic(0.5)
    reg = beta_mod.regression(asset, index)
    assert reg is not None and abs(reg[0] - 0.5) < 0.05
    book = hb.Book(index="IDX", horizon_days=300, constraint=hedge.Constraint(min_floor_pct=0.5), holdings=[holding("A", 100, 2.0)])
    result = hb.hedge_book(book, chain, smiles, {"A": (50.0, "test")}, anchor=None, anchor_reason=None)
    assert result["book_exposure"] == 100 * 50.0 * 2.0 and result["contracts"] == 1  # 10000 / (100 x 100)
    text = beta_mod.report(book, {"IDX": pit.History(index, {}), "A": pit.History(asset, {})})
    assert "0.5" in text and "2.00" in text  # the regression beside the declaration, in the report only


def test_an_index_missing_from_the_store_is_refused_and_a_book_file_is_strict(tmp_path: object) -> None:
    from pathlib import Path
    assert isinstance(tmp_path, Path)
    f = tmp_path / "book.json"
    f.write_text('{"index": "IWM", "horizon_days": 90, "constraint": {"max_cost_pct": 0.02}, "holdings": [{"ticker": "A", "shares": 1, "beta": 1.0, "beta_why": "w", "beta_as_of": "2026-09-01"}]}')
    (tmp_path / "options").mkdir()
    rc = hb.main([str(f), "--options", str(tmp_path / "options"), "--run", str(tmp_path), "--out", str(tmp_path / "out")])
    assert rc == 1
    f.write_text('{"index": "SPY", "horizon_days": 90, "constraint": {"max_cost_pct": 0.02}, "holdings": [{"ticker": "A", "shares": 1, "beta": 1.0, "weight": 0.5}]}')
    with pytest.raises(SystemExit):
        hb.load_book(f)
