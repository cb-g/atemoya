"""The fill model from the trade tape (50): where option trades print relative to the quoted
spread, per name, as a table of empirical quantiles and nothing fitted.

    uv run python/fill_model.py AAPL NVDA [--tape data/tape] [--store data/options] [--out data/fill_model] [--summary output/fill_model/summary.txt] [--rf 0.04]

Per print, one number: fill_position = (price - bid) / (ask - bid), 0 the bid, 1 the ask,
0.5 the mid, clamped to [-0.5, 1.5] with the clamp count recorded; a print at a locked or
crossed quote (ask <= bid) is excluded and counted. The table holds fill_position at
10/25/50/75/90 per (moneyness bucket by |delta| in thirds, spread width in ticks bucketed,
half-hour of day), the same collapsed per (moneyness, width) over the day, per name and
overall, each cell with its count. |delta| comes from the store's chain on the print's day
(Black on the forward at the mid's implied volatility). Buys and sells are not
distinguishable from the tape alone, so the table is symmetric by construction; a holder's
own fills, once recorded, are the asymmetric truth (python/fills_vs_model.py)."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import hedge

REPO_ROOT = Path(__file__).resolve().parents[1]
CLAMP = (-0.5, 1.5)
QUANTILES = (10, 25, 50, 75, 90)
WIDTH_BUCKETS = ((1, "1 tick"), (3, "2-3 ticks"), (9, "4-9 ticks"), (10**9, "10+ ticks"))
MONEYNESS = ("|delta| < 1/3", "1/3 <= |delta| < 2/3", "|delta| >= 2/3")
SYMMETRY_NOTE = "symmetric by construction: buys and sells are not distinguishable from the tape, so a bought leg's fill is q and a sold leg's 1 - q; a holder's own fills are the asymmetric truth"


def fill_position(price: float, bid: float, ask: float) -> tuple[float | None, str | None]:
    """(position, why excluded): None with the reason at a locked or crossed quote; the
    position clamped to [-0.5, 1.5], the reason 'clamped' when it was."""
    if ask <= bid:
        return None, "locked or crossed quote"
    raw = (price - bid) / (ask - bid)
    if raw < CLAMP[0] or raw > CLAMP[1]:
        return max(CLAMP[0], min(CLAMP[1], raw)), "clamped"
    return raw, None


def tick_size(price: float) -> float:
    """The option tick: a nickel under three dollars and a dime above, as the exchanges quote
    non-penny classes; a penny-pilot class quotes finer and its widths read larger here."""
    return 0.05 if price < 3.0 else 0.10


def width_bucket(bid: float, ask: float) -> str:
    ticks = round((ask - bid) / tick_size((bid + ask) / 2.0))
    for limit, label in WIDTH_BUCKETS:
        if ticks <= limit:
            return label
    return WIDTH_BUCKETS[-1][1]


def moneyness_bucket(abs_delta: float) -> str:
    return MONEYNESS[0] if abs_delta < 1.0 / 3.0 else MONEYNESS[1] if abs_delta < 2.0 / 3.0 else MONEYNESS[2]


def half_hour(stamp: str) -> str:
    """The half-hour of day a print's time falls in, from an HH:MM[:SS] or ISO stamp."""
    t = stamp.split("T")[-1] if "T" in stamp else stamp
    h, m = int(t[0:2]), int(t[3:5])
    return f"{h:02d}:{'00' if m < 30 else '30'}"


def quantiles(values: list[float]) -> dict[str, float]:
    """Empirical quantiles by the nearest-rank rule; nothing interpolated or fitted."""
    xs = sorted(values)
    n = len(xs)
    return {f"q{q}": xs[min(n - 1, max(0, math.ceil(q / 100.0 * n) - 1))] for q in QUANTILES}


def deltas_for_day(store: Path, ticker: str, day: str, rf: float) -> dict[tuple[str, float, str], float]:
    """|delta| per contract from the store's chain on the day: Black on spot compounded at rf,
    at the mid's implied volatility; a quote that does not invert has no delta."""
    p = store / day / f"{ticker}.json"
    if not p.exists():
        return {}
    chain = json.loads(p.read_text())
    spot = float(chain["underlying_close"])
    d0 = date.fromisoformat(str(chain["snapshot_date"]))
    out: dict[tuple[str, float, str], float] = {}
    for q in chain["quotes"]:
        days = (date.fromisoformat(str(q["expiration"])) - d0).days
        if days <= 0 or float(q["bid"]) <= 0.0:
            continue
        t = days / 365.0
        forward = spot * math.exp(rf * t)
        w = hedge.implied_total_variance(str(q["right"]), forward, float(q["strike"]), float(q["mid"]) * math.exp(rf * t))
        if w is None or w <= 0.0:
            continue
        out[(str(q["expiration"]), float(q["strike"]), str(q["right"]))] = abs(hedge.option_greeks(str(q["right"]), spot, forward, float(q["strike"]), t, w, rf).delta)
    return out


def build(ticker: str, tapes: list[dict[str, object]], deltas: dict[str, dict[tuple[str, float, str], float]]) -> dict[str, object]:
    """The name's table from its tape days; [deltas] per day per contract."""
    cells: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    counts = {"prints": 0, "excluded_locked_or_crossed": 0, "clamped": 0, "without_delta": 0}
    for tape in tapes:
        day = str(tape["date"])
        day_deltas = deltas.get(day, {})
        for p in hedge.points(tape["prints"]):
            counts["prints"] += 1
            pos, why = fill_position(float(str(p["price"])), float(str(p["bid"])), float(str(p["ask"])))
            if pos is None:
                counts["excluded_locked_or_crossed"] += 1
                continue
            if why == "clamped":
                counts["clamped"] += 1
            key = (str(p["expiration"]), float(str(p["strike"])), str(p["right"]))
            if key not in day_deltas:
                counts["without_delta"] += 1
                continue
            cells[(moneyness_bucket(day_deltas[key]), width_bucket(float(str(p["bid"])), float(str(p["ask"]))), half_hour(str(p["time"])))].append(pos)
    def cell(values: list[float]) -> dict[str, object]:
        return {"count": len(values), **quantiles(values)}
    by_hour = {f"{m} | {w} | {h}": cell(v) for (m, w, h), v in sorted(cells.items())}
    by_mw: dict[tuple[str, str], list[float]] = defaultdict(list)
    by_m: dict[str, list[float]] = defaultdict(list)
    everything: list[float] = []
    for (m, w, _), v in cells.items():
        by_mw[(m, w)].extend(v)
        by_m[m].extend(v)
        everything.extend(v)
    return {"ticker": ticker, "days": sorted(str(t["date"]) for t in tapes), "counts": counts, "quantiles": list(QUANTILES), "clamp": list(CLAMP),
            "note": SYMMETRY_NOTE, "by_moneyness_width_halfhour": by_hour,
            "by_moneyness_width": {f"{m} | {w}": cell(v) for (m, w), v in sorted(by_mw.items())},
            "by_moneyness": {m: cell(v) for m, v in sorted(by_m.items())},
            "overall": cell(everything) if everything else {"count": 0}}


def summary_line(model: dict[str, object]) -> str:
    o = hedge.points([model["overall"]])[0]
    if int(str(o["count"])) == 0:
        return f"{model['ticker']}: no usable prints"
    parts = [f"{model['ticker']}: {o['count']} prints, median fill position {float(str(o['q50'])):.2f}, 25-75 band {float(str(o['q25'])):.2f} to {float(str(o['q75'])):.2f}"]
    for m, c in hedge.points([model["by_moneyness"]])[0].items():
        cc = hedge.points([c])[0]
        parts.append(f"{m}: median {float(str(cc['q50'])):.2f} ({cc['count']})")
    return "; ".join(parts)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tickers", nargs="+")
    parser.add_argument("--tape", type=Path, default=REPO_ROOT / "data" / "tape")
    parser.add_argument("--store", type=Path, default=REPO_ROOT / "data" / "options")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "data" / "fill_model")
    parser.add_argument("--summary", type=Path, default=REPO_ROOT / "output" / "fill_model" / "summary.txt")
    parser.add_argument("--rf", type=float, default=0.04)
    args = parser.parse_args(argv)
    lines = ["fill model (50): empirical quantiles of (price - bid) / (ask - bid) per print, nothing fitted; " + SYMMETRY_NOTE, ""]
    for ticker in args.tickers:
        days = sorted(d.name for d in args.tape.iterdir() if d.is_dir() and (d / f"{ticker}.json").exists()) if args.tape.exists() else []
        if not days:
            print(f"{ticker}: no tape under {args.tape}; fetch it with uv run python/fetch_tape.py {ticker} --from D1 --to D2", file=sys.stderr)
            continue
        tapes = [json.loads((args.tape / d / f"{ticker}.json").read_text()) for d in days]
        model = build(ticker, tapes, {d: deltas_for_day(args.store, ticker, d, args.rf) for d in days})
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / f"{ticker}.json").write_text(json.dumps(model, indent=1, sort_keys=True) + "\n")
        lines.append(summary_line(model))
        print(lines[-1])
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
