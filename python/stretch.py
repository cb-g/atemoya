"""Stretch (52): how far a price has run from its own path. Six measures from split-corrected
closes and volume, nothing fitted, each with its percentile of the name's own trailing two
years, and two counts against the thresholds declared in reference/stretch.json. A
corroborator for names the holder has a thesis on; it says "stretched" and nothing more.

    uv run python/stretch.py --snapshot data/snapshots/2026-09-21 [TICKER ...]   # add the block to a snapshot's records
    uv run python/stretch.py --ticker PLTR --as-of 2026-06-25                    # the block point-in-time, printed

Measures: dd_120 (close over the 120-day high, minus one), above_120_low (over the 120-day
low, minus one), vs_ma50 and vs_ma200 (over each average, minus one), rsi_14 (Wilder's),
rv_20 (20-day realised volatility, annualised) with rv_ratio (over the name's one-year
median of the same), vol_5_60 (five-day average volume over the prior sixty). stretch_low
counts dd_120, vs_ma50, vs_ma200 and rsi_14 at or beyond the low thresholds; stretch_high
counts above_120_low, vs_ma50, vs_ma200 and rsi_14 at or beyond the high ones. A name with
fewer than 250 closes carries null with the reason. Point-in-time uses no close after the
date. Never a Failed."""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date
from pathlib import Path
from typing import Any, cast

import boundary
import reference

REPO_ROOT = Path(__file__).resolve().parents[1]
THRESHOLDS_PATH = REPO_ROOT / "reference" / "stretch.json"
FIELDS = ("as_of", "why", "history_trading_days", "min_history_days", "low", "high", "notes")
SIDE = ("dd_120", "vs_ma50", "vs_ma200", "rsi_14")
MEASURES = ("dd_120", "above_120_low", "vs_ma50", "vs_ma200", "rsi_14", "rv_20", "rv_ratio", "vol_5_60")


class StretchError(ValueError):
    """A thresholds file that is more, or less, than a declaration."""


def load_thresholds_text(text: str) -> reference.StretchThresholds:
    raw: object = json.loads(text)
    if not isinstance(raw, dict):
        raise StretchError("stretch.json is not an object")
    fields = {str(k): v for k, v in cast(dict[Any, Any], raw).items()}
    unknown = [k for k in fields if k not in FIELDS]
    if unknown:
        raise StretchError(f"stretch.json carries unknown field(s) {', '.join(unknown)}; exactly {', '.join(FIELDS)}")
    missing = [k for k in FIELDS if k != "notes" and k not in fields]
    if missing:
        raise StretchError(f"stretch.json lacks {', '.join(missing)}")
    date.fromisoformat(str(fields["as_of"]))
    if not str(fields["why"]).strip():
        raise StretchError("stretch.json: why must not be empty")
    for side in ("low", "high"):
        s = fields[side]
        if not isinstance(s, dict):
            raise StretchError(f"stretch.json: {side} is not an object")
        keys = {str(k) for k in cast(dict[Any, Any], s)}
        if keys != set(SIDE):
            raise StretchError(f"stretch.json: {side} must carry exactly {', '.join(SIDE)}")
        for k, v in cast(dict[Any, Any], s).items():
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise StretchError(f"stretch.json: {side}.{k} must be a number")
    return reference.StretchThresholds.from_json_string(text)


def load_thresholds(path: Path = THRESHOLDS_PATH) -> reference.StretchThresholds:
    return load_thresholds_text(path.read_text())


# --- the measures on a close series ---

def rsi_wilder(closes: list[float], n: int = 14) -> float | None:
    if len(closes) <= n:
        return None
    gains = [max(closes[i] - closes[i - 1], 0.0) for i in range(1, len(closes))]
    losses = [max(closes[i - 1] - closes[i], 0.0) for i in range(1, len(closes))]
    ag, al = sum(gains[:n]) / n, sum(losses[:n]) / n
    for g, l in zip(gains[n:], losses[n:]):
        ag = (ag * (n - 1) + g) / n
        al = (al * (n - 1) + l) / n
    if al == 0.0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + ag / al)


def realised_vol(closes: list[float], n: int = 20) -> float | None:
    if len(closes) <= n:
        return None
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(len(closes) - n, len(closes))]
    m = sum(rets) / n
    return math.sqrt(sum((r - m) ** 2 for r in rets) / (n - 1) * 252.0)


def measures_at(closes: list[float], volumes: list[float], rv_history: list[float]) -> dict[str, float] | None:
    """The eight measures on the closes up to and including the last; rv_history is the
    trailing year of rv_20 for the ratio. None when 200 closes are not there."""
    if len(closes) < 200 or len(volumes) < 65:
        return None
    last = closes[-1]
    w = closes[-120:]
    rsi = rsi_wilder(closes[-250:])
    rv = realised_vol(closes)
    if rsi is None or rv is None:
        return None
    med = sorted(rv_history)[len(rv_history) // 2] if rv_history else rv
    prior60 = sum(volumes[-65:-5]) / 60.0
    return {"dd_120": last / max(w) - 1.0, "above_120_low": last / min(w) - 1.0, "vs_ma50": last / (sum(closes[-50:]) / 50.0) - 1.0,
            "vs_ma200": last / (sum(closes[-200:]) / 200.0) - 1.0, "rsi_14": rsi, "rv_20": rv, "rv_ratio": rv / med if med > 0 else 1.0,
            "vol_5_60": (sum(volumes[-5:]) / 5.0) / prior60 if prior60 > 0 else 1.0}


def percentile(value: float, history: list[float]) -> float:
    """The share of the history at or below the value, 0 to 100; the value's own reading is in it."""
    return 100.0 * sum(1 for h in history if h <= value) / len(history)


def counts(m: dict[str, float], t: reference.StretchThresholds) -> tuple[int, int]:
    low = sum(1 for k in SIDE if m[k] <= getattr(t.low, k))
    high = sum(1 for k, mk in (("dd_120", "above_120_low"), ("vs_ma50", "vs_ma50"), ("vs_ma200", "vs_ma200"), ("rsi_14", "rsi_14")) if m[mk] >= getattr(t.high, k))
    return low, high


def compute(closes: dict[date, float], volumes: dict[date, float], as_of: date, t: reference.StretchThresholds) -> tuple[boundary.Stretch | None, str | None]:
    """The block from closes on or before as_of only; (None, reason) when the history is short."""
    days = sorted(d for d in closes if d <= as_of)
    if len(days) < t.min_history_days:
        return None, f"price history shorter than {t.min_history_days} trading days on or before {as_of.isoformat()}: {len(days)}"
    c = [closes[d] for d in days]
    v = [volumes.get(d, 0.0) for d in days]
    # the measure at every day of the trailing window, for the percentiles and the rv median
    window = t.history_trading_days
    ends = list(range(max(200, len(c) - window), len(c) + 1))
    rv_series: dict[int, float] = {}
    for e in range(max(21, len(c) - window - 252), len(c) + 1):
        r = realised_vol(c[:e])
        if r is not None:
            rv_series[e] = r
    history: dict[str, list[float]] = {k: [] for k in MEASURES}
    current: dict[str, float] | None = None
    for e in ends:
        rv_hist = [rv_series[i] for i in range(max(21, e - 252), e) if i in rv_series]
        m = measures_at(c[:e], v[:e], rv_hist)
        if m is None:
            continue
        for k in MEASURES:
            history[k].append(m[k])
        if e == len(c):
            current = m
    if current is None:
        return None, f"price history shorter than 200 trading days on or before {as_of.isoformat()}: {len(days)}"
    low, high = counts(current, t)
    now = current

    def sm(k: str) -> boundary.StretchMeasure:
        return boundary.StretchMeasure(value=now[k], percentile=percentile(now[k], history[k]))

    return boundary.Stretch(as_of=days[-1].isoformat(), dd_120=sm("dd_120"), above_120_low=sm("above_120_low"), vs_ma50=sm("vs_ma50"), vs_ma200=sm("vs_ma200"),
                            rsi_14=sm("rsi_14"), rv_20=sm("rv_20"), rv_ratio=sm("rv_ratio"), vol_5_60=sm("vol_5_60"), stretch_low=low, stretch_high=high,
                            thresholds_version=t.as_of, history_days=len(days)), None


def describe(s: boundary.Stretch) -> str:
    def m(x: boundary.StretchMeasure) -> str:
        return f"{x.value:.3f} (p{x.percentile:.0f})"

    return (f"as of {s.as_of}: dd_120 {m(s.dd_120)}, above_120_low {m(s.above_120_low)}, vs_ma50 {m(s.vs_ma50)}, vs_ma200 {m(s.vs_ma200)}, rsi_14 {m(s.rsi_14)}, "
            f"rv_20 {m(s.rv_20)}, rv_ratio {m(s.rv_ratio)}, vol_5_60 {m(s.vol_5_60)}; stretch_low {s.stretch_low}, stretch_high {s.stretch_high} (thresholds {s.thresholds_version}, {s.history_days} closes)")


def main(argv: list[str]) -> int:
    import pit  # noqa: PLC0415

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tickers", nargs="*")
    parser.add_argument("--snapshot", type=Path, default=None, help="add the block to every record in this directory (or the tickers given), as of each record's price date")
    parser.add_argument("--ticker", default=None)
    parser.add_argument("--as-of", default=None)
    args = parser.parse_args(argv)
    t = load_thresholds()
    if args.ticker:
        h = pit.History.fetch(args.ticker)
        d = date.fromisoformat(args.as_of) if args.as_of else max(h.closes)
        block, why = compute(h.closes, h.volumes, d, t)
        print(f"{args.ticker} {d}: {describe(block) if block else why}")
        return 0
    if args.snapshot is None:
        parser.error("give --ticker T [--as-of D] or --snapshot DIR")
    paths = sorted(p for p in args.snapshot.glob("*.json") if ".shadow-" not in p.name and (not args.tickers or p.stem in args.tickers))
    for p in paths:
        r = boundary.Financials.from_json_string(p.read_text())
        h = pit.History.fetch(r.ticker)
        d = date.fromisoformat(r.as_of[:10])
        r.stretch, r.stretch_reason = compute(h.closes, h.volumes, d, t)
        text = r.to_json_string(indent=2, allow_nan=False)
        boundary.Financials.from_json_string(text)
        p.write_text(text + "\n")
        print(f"{r.ticker}: {describe(r.stretch) if r.stretch else r.stretch_reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
