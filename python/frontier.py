"""The value-surplus frontier (35): for an untracked candidate set, the distribution of the
portfolio's value surplus (the margin of safety) under the declared beliefs, and the
long-only weightings that minimise downside risk at each level of expected surplus.

    uv run python/frontier.py candidates.json [--run output] [--out output/frontier]

The candidate file is {"names": [{"ticker": "O", "weight": 0.5}, ...]}; weights are optional
(the current portfolio, when given, is evaluated and drawn as a point). Each name's surplus
curve comes from the latest run's records (41 points over its belief's floor to ceiling);
its marginal is its truncated normal; the joint is a Gaussian copula with the declared
correlation in reference/beliefs.json. Draws and seed come from reference/params.json.
Risk is downside-only: p_negative (the book's), LPM1 at zero, CVaR at 95%; the standard
deviation is reported beside them and never optimised. The frontier minimises CVaR95 at
each target mean by the Rockafellar-Uryasev linear programme. Nothing here touches a
valuation record, and the universe is never the candidate set."""

# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
# scipy ships no type stubs; every call here passes numpy arrays and named arguments.
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
from numpy.typing import NDArray
from scipy import sparse
from scipy.optimize import linprog, minimize
from scipy.stats import norm

import beliefs as beliefs_file
import boundary
import reference

REPO_ROOT = Path(__file__).resolve().parent.parent
REFERENCE = REPO_ROOT / "reference"
Array = NDArray[np.float64]


@dataclass(frozen=True)
class Candidate:
    ticker: str
    weight: float | None
    growth: Array          # the curve's growth points
    surplus: Array         # the surplus at each
    mean: float            # the belief's mean, sd, floor, ceiling in decimals
    sd: float
    floor: float
    ceiling: float


# --- the joint distribution ------------------------------------------------------------


def correlation_matrix(tickers: list[str], common: float, pairs: list[tuple[str, str, float]]) -> Array:
    m = len(tickers)
    c = np.full((m, m), common, dtype=np.float64)
    np.fill_diagonal(c, 1.0)
    index = {t: i for i, t in enumerate(tickers)}
    for a, b, rho in pairs:
        if a in index and b in index:
            c[index[a], index[b]] = rho
            c[index[b], index[a]] = rho
    return c


def truncated_normal_ppf(u: Array, mean: float, sd: float, floor: float, ceiling: float) -> Array:
    """The inverse CDF of the belief's truncated normal at uniform draws u."""
    lo = float(norm.cdf((floor - mean) / sd))
    hi = float(norm.cdf((ceiling - mean) / sd))
    return mean + sd * cast(Array, norm.ppf(lo + u * (hi - lo)))


def sample_growths(candidates: list[Candidate], corr: Array, draws: int, seed: int) -> Array:
    """draws x names long-run growths from the Gaussian copula through each marginal."""
    rng = np.random.default_rng(seed)
    z = rng.multivariate_normal(np.zeros(len(candidates)), corr, size=draws, method="cholesky")
    u = cast(Array, norm.cdf(z))
    columns = [truncated_normal_ppf(u[:, i], c.mean, c.sd, c.floor, c.ceiling) for i, c in enumerate(candidates)]
    return np.column_stack(columns)


def surplus_on_curve(candidate: Candidate, growths: Array) -> Array:
    """The surplus read off the record's curve by linear interpolation."""
    return np.interp(growths, candidate.growth, candidate.surplus)


# --- the measures ----------------------------------------------------------------------


def measures(surplus: Array, level: float = 0.95) -> dict[str, float]:
    worst = np.sort(surplus)[: max(1, int(round((1 - level) * len(surplus))))]
    return {
        "mean": float(surplus.mean()),
        "p_negative": float((surplus < 0).mean()),
        "lpm1": float(np.maximum(0.0, -surplus).mean()),
        "cvar95": float(worst.mean()),
        "std": float(surplus.std()),
    }


# --- the frontier ----------------------------------------------------------------------


def min_cvar_weights(samples: Array, target_mean: float | None, level: float = 0.95) -> Array | None:
    """Rockafellar-Uryasev: minimise alpha + mean(u) / (1 - level) over long-only weights
    summing to one, with u_k >= -(w . s_k) - alpha, u_k >= 0, and w . mean(s) >= target."""
    n, m = samples.shape
    tail = 1.0 / ((1.0 - level) * n)
    cost = np.concatenate([np.zeros(m), [1.0], np.full(n, tail)])
    # -(w . s_k) - alpha - u_k <= 0, one row per draw: sparse, since the u block is an identity
    a_ub = sparse.hstack([sparse.csr_matrix(-samples), sparse.csr_matrix(-np.ones((n, 1))), -sparse.eye(n, format="csr")], format="csr")
    b_ub = np.zeros(n)
    if target_mean is not None:
        a_ub = sparse.vstack([a_ub, sparse.csr_matrix(np.concatenate([-samples.mean(axis=0), [0.0], np.zeros(n)]).reshape(1, -1))], format="csr")
        b_ub = np.concatenate([b_ub, [-target_mean]])
    a_eq = sparse.csr_matrix(np.concatenate([np.ones(m), [0.0], np.zeros(n)]).reshape(1, -1))
    bounds = [(0.0, 1.0)] * m + [(None, None)] + [(0.0, None)] * n
    result = linprog(cost, A_ub=a_ub, b_ub=b_ub, A_eq=a_eq, b_eq=[1.0], bounds=bounds, method="highs")
    if not result.success:
        return None
    w = np.asarray(result.x[:m], dtype=np.float64)
    w = np.maximum(w, 0.0)
    return w / w.sum()


def min_std_weights(samples: Array) -> Array:
    """The minimum-variance long-only portfolio, reported for the book's comparison, never
    the frontier's objective."""
    m = samples.shape[1]
    cov = np.cov(samples, rowvar=False)
    cov = np.atleast_2d(cov)
    def variance(w: Array) -> float:
        return float(w @ cov @ w)

    def budget(w: Array) -> float:
        return float(w.sum() - 1.0)

    result = minimize(variance, np.full(m, 1.0 / m), method="SLSQP", bounds=[(0.0, 1.0)] * m, constraints=[{"type": "eq", "fun": budget}])
    w = np.maximum(np.asarray(result.x, dtype=np.float64), 0.0)
    return w / w.sum()


def frontier(samples: Array, steps: int = 25) -> list[dict[str, object]]:
    means = samples.mean(axis=0)
    base = min_cvar_weights(samples, None)
    if base is None:
        return []
    low = float(base @ means)
    high = float(means.max())
    targets = np.linspace(low, high, steps) if high > low else np.array([low])
    out: list[dict[str, object]] = []
    for target in targets:
        w = min_cvar_weights(samples, float(target))
        if w is None:
            continue
        out.append({"target_mean": float(target), "weights": [float(x) for x in w], **measures(samples @ w)})
    return out


# --- the run ----------------------------------------------------------------------------


def load_candidates(path: Path, records: dict[str, boundary.Valuation]) -> tuple[list[Candidate], list[tuple[str, str]]]:
    raw: object = json.loads(path.read_text())
    names = cast(dict[Any, Any], raw).get("names") if isinstance(raw, dict) else None
    if not isinstance(names, list):
        raise SystemExit(f"{path}: expected {{\"names\": [{{\"ticker\": ..., \"weight\": ...}}, ...]}}")
    kept: list[Candidate] = []
    excluded: list[tuple[str, str]] = []
    for entry in cast(list[Any], names):
        e = cast(dict[Any, Any], entry)
        ticker = str(e["ticker"]).upper()
        weight = float(e["weight"]) if e.get("weight") is not None else None
        record = records.get(ticker)
        if record is None:
            excluded.append((ticker, "not in the latest run"))
        elif record.status.kind != "Ok":
            excluded.append((ticker, f"Failed: {record.failed_reason}"))
        elif record.belief is None or record.surplus_curve is None:
            excluded.append((ticker, record.belief_reason or record.surplus_curve_reason or "no belief"))
        else:
            b = record.belief.declared
            kept.append(Candidate(ticker, weight, np.array([p.growth for p in record.surplus_curve]),
                                  np.array([p.surplus for p in record.surplus_curve]), b.mean, b.sd, b.floor, b.ceiling))
    return kept, excluded


def load_records(run: Path) -> dict[str, boundary.Valuation]:
    return {v.ticker: v for v in (boundary.Valuation.from_json_string(line) for line in (run / "valuations.jsonl").read_text().splitlines() if line.strip())}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("candidates", type=Path)
    parser.add_argument("--run", type=Path, default=REPO_ROOT / "output", help="the batch's --out directory")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "output" / "frontier")
    args = parser.parse_args(argv)
    candidates_path: Path = args.candidates
    run: Path = args.run
    out: Path = args.out / candidates_path.stem
    table = beliefs_file.load_classes(REFERENCE / "beliefs.json")
    if table.correlation is None:
        raise SystemExit("reference/beliefs.json carries no correlation section")
    params = reference.Params.from_json_string((REFERENCE / "params.json").read_text())
    draws, seed = params.frontier_draws.value, params.frontier_seed.value
    records = load_records(run)
    candidates, excluded = load_candidates(candidates_path, records)
    tickers = [c.ticker for c in candidates]
    lines: list[str] = [f"frontier on {candidates_path} against {run}: {draws} draws, seed {seed}, common correlation {table.correlation.common} (as_of {table.correlation.as_of})", ""]
    for ticker, why in excluded:
        lines.append(f"  excluded {ticker}: {why}")
    if len(candidates) == 0:
        lines.append("no candidate has a belief and an Ok record; nothing to draw")
        out.mkdir(parents=True, exist_ok=True)
        (out / "frontier.txt").write_text("\n".join(lines) + "\n")
        print("\n".join(lines))
        return 1
    corr = correlation_matrix(tickers, table.correlation.common, [(p.a, p.b, p.rho) for p in table.correlation.pairs])
    growths = sample_growths(candidates, corr, draws, seed)
    samples = np.column_stack([surplus_on_curve(c, growths[:, i]) for i, c in enumerate(candidates)])
    per_name = {c.ticker: measures(samples[:, i]) for i, c in enumerate(candidates)}
    lines.append("per name (surplus under its belief; cvar95 is the mean of the worst 5% of surpluses, higher is safer):")
    for t, m in per_name.items():
        lines.append(f"  {t:6} mean {m['mean']:+.3f}  p_negative {m['p_negative']:.3f}  lpm1 {m['lpm1']:.3f}  cvar95 {m['cvar95']:+.3f}  std {m['std']:.3f}")
    degenerate = all(m["p_negative"] >= 1.0 for m in per_name.values())
    if degenerate:
        lines += ["", "every candidate is overpaid with certainty under the declared beliefs; the frontier is not informative at these prices"]
    curve = frontier(samples)
    specials: dict[str, dict[str, object]] = {}
    if curve:
        # cvar95 is the mean of the worst 5% of surpluses, so the least tail risk is the highest
        # value: the sweep's first point, the unconstrained Rockafellar-Uryasev minimum
        specials["min_cvar95"] = max(curve, key=lambda r: cast(float, r["cvar95"]))
        specials["min_p_negative"] = min(curve, key=lambda r: cast(float, r["p_negative"]))
    w_std = min_std_weights(samples)
    specials["min_std"] = {"weights": [float(x) for x in w_std], **measures(samples @ w_std)}
    current: dict[str, object] | None = None
    if all(c.weight is not None for c in candidates) and candidates:
        w = np.array([c.weight or 0.0 for c in candidates]); w = w / w.sum()
        current = {"weights": [float(x) for x in w], **measures(samples @ w)}
        specials["current"] = current
    lines += ["", "portfolios (weights in candidate order " + ", ".join(tickers) + "):"]
    for name, r in specials.items():
        lines.append(f"  {name:15} mean {cast(float, r['mean']):+.3f}  p_negative {cast(float, r['p_negative']):.3f}  lpm1 {cast(float, r['lpm1']):.3f}  cvar95 {cast(float, r['cvar95']):+.3f}  std {cast(float, r['std']):.3f}  weights {[round(x, 3) for x in cast(list[float], r['weights'])]}")
    lines += ["", f"frontier, {len(curve)} portfolios minimising the loss's CVaR95 (the highest worst-5% mean surplus) at each target mean:"]
    for r in curve:
        lines.append(f"  target {cast(float, r['target_mean']):+.3f}  mean {cast(float, r['mean']):+.3f}  p_negative {cast(float, r['p_negative']):.3f}  lpm1 {cast(float, r['lpm1']):.3f}  cvar95 {cast(float, r['cvar95']):+.3f}  std {cast(float, r['std']):.3f}  weights {[round(x, 3) for x in cast(list[float], r['weights'])]}")
    out.mkdir(parents=True, exist_ok=True)
    (out / "frontier.json").write_text(json.dumps({
        "candidates": candidates_path.name, "run": str(run), "draws": draws, "seed": seed,
        "correlation_common": table.correlation.common, "correlation_as_of": table.correlation.as_of,
        "tickers": tickers, "excluded": [{"ticker": t, "why": w} for t, w in excluded],
        "per_name": per_name, "degenerate": degenerate, "specials": specials, "frontier": curve,
    }, indent=2) + "\n")
    (out / "frontier.txt").write_text("\n".join(lines) + "\n")
    draw(out / "frontier.png", tickers, per_name, curve, current, degenerate)
    print("\n".join(lines))
    print(f"\nwritten {out}/frontier.json, frontier.txt, frontier.png")
    return 0


def draw(png: Path, tickers: list[str], per_name: dict[str, dict[str, float]], curve: list[dict[str, object]],
         current: dict[str, object] | None, degenerate: bool) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # pyright: ignore[reportUnknownVariableType]

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))  # pyright: ignore[reportUnknownMemberType]
    for ax, key, label in ((axes[0], "p_negative", "probability of a negative surplus"), (axes[1], "cvar95", "CVaR at 95% of the surplus")):
        for t in tickers:
            m = per_name[t]
            ax.scatter(m[key], m["mean"], color="tab:blue")  # pyright: ignore[reportUnknownMemberType]
            ax.annotate(t, (m[key], m["mean"]), textcoords="offset points", xytext=(4, 4))  # pyright: ignore[reportUnknownMemberType]
        if curve:
            ax.plot([cast(float, r[key]) for r in curve], [cast(float, r["mean"]) for r in curve], color="black", label="frontier (min CVaR95 at each mean)")  # pyright: ignore[reportUnknownMemberType]
        if current is not None:
            ax.scatter(cast(float, current[key]), cast(float, current["mean"]), marker="*", s=160, color="tab:red", label="current weights")  # pyright: ignore[reportUnknownMemberType]
        ax.set_xlabel(label)  # pyright: ignore[reportUnknownMemberType]
        ax.set_ylabel("expected value surplus (V - P) / P")  # pyright: ignore[reportUnknownMemberType]
        ax.legend(loc="best")  # pyright: ignore[reportUnknownMemberType]
    fig.suptitle("value-surplus frontier under the declared beliefs" + (" (degenerate: every candidate overpaid with certainty)" if degenerate else ""))  # pyright: ignore[reportUnknownMemberType]
    fig.tight_layout()
    fig.savefig(png, dpi=120)  # pyright: ignore[reportUnknownMemberType]
    plt.close(fig)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
