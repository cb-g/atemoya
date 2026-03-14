#!/usr/bin/env python3
"""
Volatility arbitrage signal scanner — ranks tickers by IV vs RV divergence.

Reads *_volarb_history.csv files, computes z-scores for IV-RV spread,
and classifies signals.

Key signals:
- IV >> forecast RV: vol is expensive → SELL VOL (short straddle/strangle)
- IV << forecast RV: vol is cheap → BUY VOL (long straddle/strangle)
- Z-scores measure how extreme today's spread is vs history
"""

import argparse
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"
SEGMENT_DIR = Path(__file__).resolve().parents[2] / "liquidity" / "data"


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
    """Load all vol arb history CSVs with at least min_days observations."""
    histories = {}
    for f in sorted(data_dir.glob("*_volarb_history.csv")):
        ticker = f.stem.replace("_volarb_history", "")
        try:
            df = pd.read_csv(f)
            if len(df) >= min_days:
                histories[ticker] = df
        except Exception:
            continue
    return histories


def compute_z_scores(df: pd.DataFrame, window: int = 0) -> dict[str, float]:
    """Compute z-scores for latest observation against history."""
    scores = {}
    for col in ["iv_rv_spread", "iv_rv_ratio", "atm_iv"]:
        if col not in df.columns:
            continue
        series = df[col].dropna()
        if len(series) < 3:
            if len(series) >= 1:
                scores[f"{col}_latest"] = series.iloc[-1]
            continue
        if window > 0 and len(series) > window:
            series = series.iloc[-window:]
        mean = series.iloc[:-1].mean()
        std = series.iloc[:-1].std()
        if std > 0:
            scores[f"{col}_z"] = (series.iloc[-1] - mean) / std
        scores[f"{col}_latest"] = series.iloc[-1]
        scores[f"{col}_mean"] = mean

    return scores


def classify_signal(iv_rv_spread: float, spread_z: float,
                    iv_rv_ratio: float) -> tuple[str, str]:
    """Classify vol arb signal from IV-RV spread z-score."""
    # Use ratio for day-1 classification when no z-score yet
    if abs(spread_z) < 0.001 and not np.isnan(spread_z):
        # Have z-score
        pass

    # Z-score based classification
    if not np.isnan(spread_z) and abs(spread_z) >= 1.0:
        if spread_z > 1.5:
            return "SELL VOL", (
                f"IV-RV z={spread_z:+.2f} — vol expensive, "
                f"spread={iv_rv_spread*100:+.1f}%, ratio={iv_rv_ratio:.2f}"
            )
        if spread_z < -1.5:
            return "BUY VOL", (
                f"IV-RV z={spread_z:+.2f} — vol cheap, "
                f"spread={iv_rv_spread*100:+.1f}%, ratio={iv_rv_ratio:.2f}"
            )
        if spread_z > 1.0:
            return "LEAN SELL VOL", (
                f"IV-RV z={spread_z:+.2f} — vol moderately expensive, "
                f"spread={iv_rv_spread*100:+.1f}%"
            )
        if spread_z < -1.0:
            return "LEAN BUY VOL", (
                f"IV-RV z={spread_z:+.2f} — vol moderately cheap, "
                f"spread={iv_rv_spread*100:+.1f}%"
            )

    # Fallback: ratio-based for day 1 (no z-score history)
    if iv_rv_ratio > 1.5:
        return "LEAN SELL VOL", (
            f"IV/RV={iv_rv_ratio:.2f} — vol elevated, "
            f"spread={iv_rv_spread*100:+.1f}%"
        )
    if iv_rv_ratio < 0.7:
        return "LEAN BUY VOL", (
            f"IV/RV={iv_rv_ratio:.2f} — vol depressed, "
            f"spread={iv_rv_spread*100:+.1f}%"
        )

    return "NEUTRAL", (
        f"IV/RV={iv_rv_ratio:.2f}, spread={iv_rv_spread*100:+.1f}%"
    )


def scan(data_dir: Path, min_days: int, threshold: float,
         segment_map: dict[str, str] | None = None,
         window: int = 0) -> pd.DataFrame:
    """Run the full scan and return a ranked DataFrame."""
    histories = load_histories(data_dir, min_days)
    if not histories:
        return pd.DataFrame()

    rows = []
    for ticker, df in histories.items():
        latest = df.iloc[-1]
        scores = compute_z_scores(df, window=window)

        iv_rv_spread = latest["iv_rv_spread"]
        iv_rv_ratio = latest["iv_rv_ratio"]
        spread_z = scores.get("iv_rv_spread_z", np.nan)

        signal, description = classify_signal(iv_rv_spread, spread_z, iv_rv_ratio)

        max_z = abs(spread_z) if not np.isnan(spread_z) else 0.0

        row = {
            "ticker": ticker,
            "days": len(df),
            "signal": signal,
            "description": description,
            "iv_rv_spread": iv_rv_spread,
            "iv_rv_ratio": iv_rv_ratio,
            "spread_z": spread_z,
            "max_abs_z": max_z,
            "atm_iv": latest["atm_iv"],
            "rv_yang_zhang": latest["rv_yang_zhang"],
            "rv_forecast": latest["rv_forecast"],
            "spot": latest["spot"],
        }
        if segment_map is not None:
            seg = segment_map.get(ticker)
            if seg is None:
                seg = price_to_segment(latest["spot"])
            row["segment"] = seg
        rows.append(row)

    result = pd.DataFrame(rows)
    if result.empty:
        return result

    result = result[result["max_abs_z"] >= threshold].sort_values(
        "max_abs_z", ascending=False
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

    actionable = df[~df["signal"].str.contains("NEUTRAL")]
    neutral = df[df["signal"].str.contains("NEUTRAL")]

    if not actionable.empty:
        print(f"\n{'='*80}")
        print(f"  ACTIONABLE SIGNALS ({len(actionable)} tickers)")
        print(f"{'='*80}")
        for _, row in actionable.iterrows():
            seg = f"  [{row['segment']}]" if "segment" in row and row.get("segment") != "unknown" else ""
            print(f"\n  {row['ticker']:6s}  {row['signal']}{seg}")
            print(f"         {row['description']}")
            z_str = f"  z={row['spread_z']:+.2f}" if not np.isnan(row['spread_z']) else ""
            print(f"         IV={row['atm_iv']*100:.1f}%  RV={row['rv_yang_zhang']*100:.1f}%  "
                  f"Fcast={row['rv_forecast']*100:.1f}%{z_str}  ({row['days']} days)")

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
                print(f"    {row['ticker']:6s}  {row['signal']}  IV/RV={row['iv_rv_ratio']:.2f}")
                print(f"           {row['description']}")

    if not quiet and not neutral.empty:
        print(f"\n{'='*80}")
        print(f"  NEUTRAL ({len(neutral)} tickers)")
        print(f"{'='*80}")
        for _, row in neutral.iterrows():
            seg = f"  [{row['segment']}]" if "segment" in row and row.get("segment") != "unknown" else ""
            print(f"  {row['ticker']:6s}  IV/RV={row['iv_rv_ratio']:.2f}  "
                  f"spread={row['iv_rv_spread']*100:+.1f}%{seg}")

    print(f"\n  Scanned: {len(df)} tickers above threshold")
    print(f"  Actionable: {len(actionable)}")


def main():
    parser = argparse.ArgumentParser(
        description="Scan vol arb history for IV vs RV divergence signals"
    )
    parser.add_argument("--data-dir", type=str, default=str(DATA_DIR))
    parser.add_argument("--min-days", type=int, default=1)
    parser.add_argument("--threshold", type=float, default=0.0,
                        help="Min |z-score| to include (default: 0.0)")
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

    print(f"Volatility Arbitrage Signal Scanner")
    print(f"Data: {data_dir}")
    print(f"Signal: SELL VOL (IV>>RV), BUY VOL (IV<<RV)")
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
