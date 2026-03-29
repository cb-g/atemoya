#!/usr/bin/env python3
"""
Skew verticals signal scanner — ranks tickers by edge score.

Reads *_skewvert_history.csv files and applies the triple filter from
the OCaml scanner:
  1. Skew z-score < -2.0 (call or put — extreme skew compression)
  2. VRP > 0 AND OTM IV > RV (options overpriced)
  3. Momentum aligned (>0.3 for bull, <-0.3 for bear)

Signals:
- PUT VERTICAL / CALL VERTICAL: all 3 filters pass, with edge score
- LEAN: skew + VRP pass, momentum weak
- WATCH: skew passes only
- NEUTRAL: no extreme skew
"""

import argparse
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Optional macro regime context (enriches output when available)
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
try:
    from lib.python.context import load_macro_regime
except ImportError:
    load_macro_regime = lambda: None

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"
SEGMENT_DIR = Path(__file__).resolve().parents[2] / "liquidity" / "data"

# Filter thresholds (matching OCaml scanner.ml)
SKEW_Z_THRESHOLD = -2.0
MOMENTUM_THRESHOLD = 0.3


def price_to_segment(price: float) -> str:
    """Compute segment label from a spot price."""
    if price <= 0:
        return "unknown"
    bucket = int(price // 10) * 10
    if bucket >= 200:
        return "above $200"
    low = bucket + 1 if bucket > 0 else 1
    high = bucket + 10
    return f"${low}-${high}"


def load_segment_map(segment_dir: Path) -> dict[str, str]:
    """Build ticker -> segment label map from liquid_options_*_USD.txt files."""
    segment_map = {}
    for f in sorted(segment_dir.glob("liquid_options_*_USD.txt")):
        name = f.stem.replace("liquid_options_", "").replace("_USD", "")
        m = re.match(r"(\d+)_to_(\d+)", name)
        if m:
            label = f"${m.group(1)}-${m.group(2)}"
        elif name.startswith("above_"):
            label = f"above ${name.split('_')[1]}"
        else:
            label = name
        tickers = [t.strip() for t in f.read_text().splitlines() if t.strip()]
        for t in tickers:
            segment_map[t] = label
    return segment_map


def load_histories(data_dir: Path, min_days: int) -> dict[str, pd.DataFrame]:
    """Load skew verticals history CSVs from both yfinance and thetadata sources."""
    histories = {}
    ticker_dfs: dict[str, list[pd.DataFrame]] = {}
    for pattern in ("*_skewvert_history_yfinance.csv", "*_skewvert_history_thetadata.csv"):
        for f in sorted(data_dir.glob(pattern)):
            ticker = f.stem.replace("_skewvert_history_yfinance", "").replace("_skewvert_history_thetadata", "")
            try:
                df = pd.read_csv(f)
                if not df.empty:
                    ticker_dfs.setdefault(ticker, []).append(df)
            except Exception:
                continue

    for ticker, dfs in ticker_dfs.items():
        merged = pd.concat(dfs, ignore_index=True)
        merged = merged.drop_duplicates(subset=["date"], keep="first")
        merged = merged.sort_values("date").reset_index(drop=True)
        if len(merged) >= min_days:
            histories[ticker] = merged

    return histories


def compute_z_score(series: pd.Series, window: int = 0) -> float:
    """Compute z-score for latest value against history."""
    series = series.dropna()
    if len(series) < 3:
        return 0.0
    if window > 0 and len(series) > window:
        series = series.iloc[-window:]
    mean = series.iloc[:-1].mean()
    std = series.iloc[:-1].std()
    return (series.iloc[-1] - mean) / std if std > 0 else 0.0


def classify_signal(call_skew_z: float, put_skew_z: float,
                    vrp: float, otm_iv: float, rv: float,
                    momentum_score: float, edge_score: float) -> tuple[str, str]:
    """Classify skew verticals signal using triple filter."""
    passes_skew = call_skew_z < SKEW_Z_THRESHOLD or put_skew_z < SKEW_Z_THRESHOLD
    passes_ivrv = vrp > 0 and otm_iv > rv
    passes_momentum_bull = momentum_score > MOMENTUM_THRESHOLD
    passes_momentum_bear = momentum_score < -MOMENTUM_THRESHOLD
    passes_momentum = passes_momentum_bull or passes_momentum_bear

    if not passes_skew:
        return "NEUTRAL", f"skew z: call={call_skew_z:+.1f} put={put_skew_z:+.1f} (no extreme compression)"

    # Determine direction from momentum
    if passes_momentum_bull:
        direction = "BULL"
        spread = "PUT VERTICAL"  # sell rich put skew
    elif passes_momentum_bear:
        direction = "BEAR"
        spread = "CALL VERTICAL"  # sell rich call skew
    else:
        direction = ""
        spread = ""

    if passes_skew and passes_ivrv and passes_momentum:
        return spread, (
            f"edge={edge_score:.0f} skew_z={min(call_skew_z, put_skew_z):+.1f} "
            f"VRP={vrp*100:.1f}% mom={momentum_score:+.2f} — all filters pass"
        )
    elif passes_skew and passes_ivrv:
        label = f"LEAN {spread}" if spread else "LEAN"
        return label, (
            f"edge={edge_score:.0f} skew_z={min(call_skew_z, put_skew_z):+.1f} "
            f"VRP={vrp*100:.1f}% mom={momentum_score:+.2f} — weak momentum"
        )
    elif passes_skew:
        return "WATCH", (
            f"skew_z={min(call_skew_z, put_skew_z):+.1f} "
            f"VRP={vrp*100:.1f}% mom={momentum_score:+.2f} — skew only"
        )
    else:
        return "NEUTRAL", f"skew z: call={call_skew_z:+.1f} put={put_skew_z:+.1f}"


def scan(data_dir: Path, min_days: int, threshold: float,
         segment_map: dict[str, str] | None = None,
         window: int = 0) -> pd.DataFrame:
    """Run the full scan and return a ranked DataFrame."""
    histories = load_histories(data_dir, min_days)
    if not histories:
        return pd.DataFrame()

    rows = []
    regime = load_macro_regime()
    for ticker, df in histories.items():
        latest = df.iloc[-1]

        # Compute z-scores from history
        call_skew_z = compute_z_score(df["call_skew"], window=window)
        put_skew_z = compute_z_score(df["put_skew"], window=window)

        vrp = latest["vrp"]
        rv = latest["rv_30d"]
        momentum_score = latest["momentum_score"]
        edge_score = latest["edge_score"]

        # OTM IV for IV/RV check: use whichever side has more extreme skew
        otm_iv = latest["put_25d_iv"] if put_skew_z < call_skew_z else latest["call_25d_iv"]

        signal, description = classify_signal(
            call_skew_z, put_skew_z, vrp, otm_iv, rv,
            momentum_score, edge_score
        )

        row = {
            "ticker": ticker,
            "days": len(df),
            "signal": signal,
            "description": description,
            "edge_score": edge_score,
            "call_skew_z": call_skew_z,
            "put_skew_z": put_skew_z,
            "vrp": vrp,
            "momentum_score": momentum_score,
            "atm_iv": latest["atm_iv"],
            "rv_30d": rv,
            "spot": latest["spot"],
        }
        if segment_map is not None:
            seg = segment_map.get(ticker)
            if seg is None:
                seg = price_to_segment(latest["spot"])
            row["segment"] = seg
        if regime:
            row["macro_regime"] = regime["cycle_phase"]
            row["risk_sentiment"] = regime["risk_sentiment"]
        rows.append(row)

    result = pd.DataFrame(rows)
    if result.empty:
        return result

    # Filter by edge score threshold and sort by edge score descending
    result = result[result["edge_score"] >= threshold].sort_values(
        "edge_score", ascending=False
    )
    return result.reset_index(drop=True)


def _segment_sort_key(label: str) -> tuple:
    m = re.match(r"\$(\d+)-\$(\d+)", label)
    if m:
        return (0, int(m.group(1)))
    if label.startswith("above"):
        return (1, 0)
    return (2, 0)


def print_report(df: pd.DataFrame, quiet: bool = False, segments: bool = False):
    """Print a human-readable signal report."""
    if df.empty:
        print("No signals found above threshold.")
        return

    actionable = df[df["signal"].str.contains("VERTICAL")]
    lean = df[df["signal"].str.contains("LEAN")]
    watch = df[df["signal"] == "WATCH"]
    neutral = df[df["signal"] == "NEUTRAL"]

    if not actionable.empty:
        print(f"\n{'='*80}")
        print(f"  ACTIONABLE SIGNALS ({len(actionable)} tickers)")
        print(f"{'='*80}")
        for _, row in actionable.iterrows():
            seg = f"  [{row['segment']}]" if "segment" in row and row.get("segment") != "unknown" else ""
            print(f"\n  {row['ticker']:6s}  {row['signal']}{seg}")
            print(f"         {row['description']}")
            print(f"         ATM IV={row['atm_iv']*100:.1f}%  RV={row['rv_30d']*100:.1f}%  "
                  f"VRP={row['vrp']*100:.1f}%  ({row['days']} days)")

    if not lean.empty:
        print(f"\n{'='*80}")
        print(f"  LEAN ({len(lean)} tickers)")
        print(f"{'='*80}")
        for _, row in lean.iterrows():
            seg = f"  [{row['segment']}]" if "segment" in row and row.get("segment") != "unknown" else ""
            print(f"  {row['ticker']:6s}  {row['signal']}  edge={row['edge_score']:.0f}{seg}")
            print(f"         {row['description']}")

    if segments and "segment" in df.columns:
        seg_actionable = actionable if not actionable.empty else pd.DataFrame()
        segment_order = sorted(df["segment"].unique(), key=_segment_sort_key)

        print(f"\n{'='*80}")
        print(f"  BY SEGMENT")
        print(f"{'='*80}")
        for seg in segment_order:
            seg_act = seg_actionable[seg_actionable["segment"] == seg] if not seg_actionable.empty else pd.DataFrame()
            seg_df = df[df["segment"] == seg]
            print(f"\n  --- {seg} ({len(seg_act)} actionable / {len(seg_df)} scanned) ---")
            if seg_act.empty:
                print(f"    no actionable signals")
                continue
            for _, row in seg_act.iterrows():
                print(f"    {row['ticker']:6s}  {row['signal']}  edge={row['edge_score']:.0f}")
                print(f"           {row['description']}")

    if not quiet and not watch.empty:
        print(f"\n{'='*80}")
        print(f"  WATCH ({len(watch)} tickers)")
        print(f"{'='*80}")
        for _, row in watch.iterrows():
            seg = f"  [{row['segment']}]" if "segment" in row and row.get("segment") != "unknown" else ""
            print(f"  {row['ticker']:6s}  edge={row['edge_score']:.0f}  "
                  f"skew_z={min(row['call_skew_z'], row['put_skew_z']):+.1f}  "
                  f"VRP={row['vrp']*100:.1f}%{seg}")

    print(f"\n  Scanned: {len(df)} tickers above threshold")
    print(f"  Actionable: {len(actionable)}")
    print(f"  Lean: {len(lean)}")
    print(f"  Watch: {len(watch)}")


def main():
    parser = argparse.ArgumentParser(
        description="Scan skew verticals history for spread signals"
    )
    parser.add_argument("--data-dir", type=str, default=str(DATA_DIR))
    parser.add_argument("--min-days", type=int, default=1)
    parser.add_argument("--threshold", type=float, default=0.0,
                        help="Min edge score to include (default: 0.0)")
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--segments", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--window", type=int, default=0,
                        help="Z-score lookback window (0=all history)")

    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"Error: {data_dir} not found", file=sys.stderr)
        sys.exit(1)

    segment_map = None
    if args.segments and SEGMENT_DIR.exists():
        segment_map = load_segment_map(SEGMENT_DIR)
        print(f"Loaded {len(segment_map)} tickers across segments")

    print(f"Skew Verticals Signal Scanner")
    print(f"Data: {data_dir}")
    print(f"Filters: skew_z<{SKEW_Z_THRESHOLD}, VRP>0+OTM_IV>RV, |momentum|>{MOMENTUM_THRESHOLD}")
    if args.window > 0:
        print(f"Z-score window: last {args.window} observations")

    result = scan(data_dir, args.min_days, args.threshold,
                  segment_map=segment_map, window=args.window)
    print_report(result, args.quiet, args.segments)

    if args.output and not result.empty:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(output_path, index=False)
        print(f"\nSaved to {output_path}")


if __name__ == "__main__":
    main()
