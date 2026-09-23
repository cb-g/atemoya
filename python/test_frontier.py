"""The frontier's pieces (35): the copula reproduces the declared correlation, the marginals
are the truncated normals, interpolation reads the curve, the measures on a hand-built
sample, the LP recovers a known two-name optimum, and exclusions carry their reason."""

# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
# scipy ships no type stubs.
from __future__ import annotations

import json
from pathlib import Path

from typing import cast

import numpy as np
import pytest
from scipy.stats import norm

import beliefs
import frontier as fr


def candidate(ticker: str, surplus: list[float], *, mean: float = 0.02, sd: float = 0.005, floor: float = 0.0, ceiling: float = 0.04, weight: float | None = None) -> fr.Candidate:
    growth = np.linspace(floor, ceiling, len(surplus))
    return fr.Candidate(ticker, weight, growth, np.array(surplus, dtype=np.float64), mean, sd, floor, ceiling)


def test_copula_reproduces_the_declared_correlation_and_the_marginals() -> None:
    a = candidate("A", [0.0, 1.0]); b = candidate("B", [0.0, 1.0], mean=0.03, sd=0.01, floor=0.0, ceiling=0.05)
    corr = fr.correlation_matrix(["A", "B"], 0.2, [])
    g = fr.sample_growths([a, b], corr, 20000, 0)
    # the rank correlation of a Gaussian copula at rho = 0.2 is 6/pi asin(rho/2) = 0.191
    from scipy.stats import spearmanr
    rho = float(np.asarray(spearmanr(g[:, 0], g[:, 1])[0], dtype=np.float64))
    assert abs(rho - 6 / np.pi * np.arcsin(0.1)) < 0.02
    # marginals: within the bounds, with the truncated normal's quantiles
    for col, c in ((g[:, 0], a), (g[:, 1], b)):
        assert col.min() >= c.floor and col.max() <= c.ceiling
        for q in (0.1, 0.5, 0.9):
            theory = fr.truncated_normal_ppf(np.array([q]), c.mean, c.sd, c.floor, c.ceiling)[0]
            assert abs(float(np.quantile(col, q)) - theory) < 0.001
    # a pair override replaces the common number for that pair only
    corr = fr.correlation_matrix(["A", "B", "C"], 0.2, [("A", "C", 0.7)])
    assert corr[0, 2] == corr[2, 0] == 0.7 and corr[0, 1] == 0.2 and corr[1, 1] == 1.0
    # seeded: two runs agree
    assert np.array_equal(g, fr.sample_growths([a, b], fr.correlation_matrix(["A", "B"], 0.2, []), 20000, 0))


def test_interpolation_and_measures_on_a_hand_built_sample() -> None:
    c = candidate("A", [-0.5, 0.0, 0.5], floor=0.0, ceiling=0.04)
    assert fr.surplus_on_curve(c, np.array([0.0, 0.01, 0.02, 0.03, 0.04])).tolist() == pytest.approx([-0.5, -0.25, 0.0, 0.25, 0.5])
    s = np.array([-0.2, -0.1, 0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7] * 2)
    m = fr.measures(s, level=0.95)
    assert m["p_negative"] == 0.2 and m["lpm1"] == pytest.approx(0.03) and m["mean"] == pytest.approx(0.25)
    assert m["cvar95"] == pytest.approx(-0.2)  # the worst 5% of 20 draws is the one worst draw
    assert m["std"] == pytest.approx(float(s.std()))


def test_the_lp_recovers_a_known_two_name_optimum() -> None:
    rng = np.random.default_rng(1)
    safe = np.full(2000, 0.10)                       # a constant surplus: no downside at all
    risky = rng.normal(0.30, 0.40, 2000)             # higher mean, deep tail
    samples = np.column_stack([safe, risky])
    w = fr.min_cvar_weights(samples, None)
    assert w is not None and w[0] == pytest.approx(1.0, abs=1e-6) and w.sum() == pytest.approx(1.0) and (w >= 0).all()
    # at a target mean above the safe name's, the LP must take the risky one, as little as needed
    w = fr.min_cvar_weights(samples, 0.20)
    assert w is not None and abs(float(samples.mean(axis=0) @ w) - 0.20) < 1e-6 and (w >= 0).all()
    curve = fr.frontier(samples, steps=5)
    assert len(curve) == 5 and curve[0]["cvar95"] == pytest.approx(0.10)
    assert all(sum(cast(list[float], r["weights"])) == pytest.approx(1.0) for r in curve)
    w_std = fr.min_std_weights(samples)
    assert w_std[0] == pytest.approx(1.0, abs=1e-3)


def test_a_name_without_a_belief_is_excluded_with_its_reason(tmp_path: Path) -> None:
    import boundary
    run = Path(__file__).resolve().parent.parent / "output" / "valuations.jsonl"
    lines = [l for l in run.read_text().splitlines() if l.strip()] if run.exists() else []
    if not lines:
        pytest.skip("no run to read")
    records = {v.ticker: v for v in (boundary.Valuation.from_json_string(l) for l in lines)}
    no_belief = next((t for t, v in records.items() if v.status.kind == "Ok" and v.belief is None), None)
    with_belief = next((t for t, v in records.items() if v.status.kind == "Ok" and v.surplus_curve is not None), None)
    if with_belief is None:
        pytest.skip("run lacks a record with a curve")
    names: list[dict[str, object]] = [{"ticker": with_belief, "weight": 1.0}, {"ticker": "NOPE"}]
    if no_belief is not None:
        names.insert(0, {"ticker": no_belief})
    f = tmp_path / "cands.json"
    f.write_text(json.dumps({"names": names}))
    kept, excluded = fr.load_candidates(f, records)
    assert [c.ticker for c in kept] == [with_belief] and len(kept[0].growth) == 41
    assert dict(excluded)["NOPE"] == "not in the latest run"
    if no_belief is not None:
        assert dict(excluded)[no_belief]  # excluded with whatever reason the record carries


def test_residual_income_names_enter_the_frontier(tmp_path: Path) -> None:
    """(58) Banks and insurers used to be excluded for having no belief. They have one now,
    on the long-run return on equity, and their curve is the same 41 points, so the frontier
    takes them like any other name."""
    import boundary
    run = Path(__file__).resolve().parent.parent / "output" / "valuations.jsonl"
    lines = [l for l in run.read_text().splitlines() if l.strip()] if run.exists() else []
    if not lines:
        pytest.skip("no run to read")
    records = {v.ticker: v for v in (boundary.Valuation.from_json_string(l) for l in lines)}
    banks = [t for t, v in records.items()
             if v.status.kind == "Ok" and v.model is not None
             and v.model.kind in ("ResidualIncome_", "ResidualIncomeInsurer")]
    if len(banks) < 2:
        pytest.skip("run lacks two residual-income records")
    for t in banks:
        v = records[t]
        assert v.belief is not None and v.surplus_curve is not None, t
        assert v.belief.belief_parameter == "long_run_return_on_equity", t
        assert v.belief.implied_roe_target is not None and v.belief.implied_terminal_growth is None, t
        assert len(v.surplus_curve) == 41, t
        # the curve is swept over the belief's own floor-to-ceiling range
        assert v.surplus_curve[0].growth == pytest.approx(v.belief.declared.floor)
        assert v.surplus_curve[-1].growth == pytest.approx(v.belief.declared.ceiling)
        # and the surplus rises with the long-run return, so the interpolation is well posed
        assert v.surplus_curve[0].surplus < v.surplus_curve[-1].surplus, t
    f = tmp_path / "cands.json"
    f.write_text(json.dumps({"names": [{"ticker": banks[0], "weight": 0.5}, {"ticker": banks[1], "weight": 0.5}]}))
    kept, excluded = fr.load_candidates(f, records)
    assert [c.ticker for c in kept] == banks[:2] and excluded == []


def test_correlation_section_loads_strictly() -> None:
    ok = {"classes": {"OperatingCompany": {"mean": 0, "sd": 0.5, "floor": -2, "ceiling": 2, "why": "w", "as_of": "2026-09-19"}}}
    table = beliefs.load_classes_text(json.dumps({**ok, "correlation": {"common": 0.2, "why": "the book's", "as_of": "2026-09-19"}}))
    assert table.correlation is not None and table.correlation.common == 0.2
    with pytest.raises(beliefs.BeliefError, match="unknown field\\(s\\) rho"):
        beliefs.load_classes_text(json.dumps({**ok, "correlation": {"common": 0.2, "why": "w", "as_of": "2026-09-19", "rho": 0.3}}))
    with pytest.raises(beliefs.BeliefError, match="not in \\[0, 1\\)"):
        beliefs.load_classes_text(json.dumps({**ok, "correlation": {"common": 1.0, "why": "w", "as_of": "2026-09-19"}}))
    with pytest.raises(beliefs.BeliefError, match="not exactly a, b, rho, why, as_of"):
        beliefs.load_classes_text(json.dumps({**ok, "correlation": {"common": 0.2, "why": "w", "as_of": "2026-09-19", "pairs": [{"a": "X", "b": "Y", "rho": 0.5, "why": "w"}]}}))
    tracked = beliefs.load_classes(Path(__file__).resolve().parent.parent / "reference" / "beliefs.json")
    assert tracked.correlation is not None and tracked.correlation.common == 0.2 and norm.cdf(0) == 0.5
